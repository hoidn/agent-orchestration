"""A local stand-in for the model API, to record what the real CLI sends and how it ends a session.

Serves `POST /v1/messages` (streamed or plain) with canned replies chosen by a scenario, and refuses any
model other than the one configured (404 `not_found_error`, as the API does). Every request is appended to
the log as one JSON line: path, model, declared tools, headers (key and token redacted), the request's
top-level parameters (no message text; each system block's length, first 80 characters and cache control,
which stay in the local log: the committed request fixtures drop the characters), the usage served and the
running total. Any other path
answers 404 and is logged too. Standard library only; no request leaves the host.

Usage: python -I stub_api.py ([--host 127.0.0.1] [--port P] | --unix PATH) --model claude-haiku-5-5 --scenario NAME
       --log FILE [--delay SECONDS] [--other-status STATUS]
Prints `listening <host> <port>` (port 0 picks a free port) or `listening <unix path>` once bound. Only a
loopback address or a unix socket is accepted; any other --host is refused.

Scenarios (the reply depends on the request, so side requests and subagents get sensible answers):
  normal    a Bash call (probes the vendor's API host from inside the container), then an end
  budget    Bash calls forever, each reply priced high, until the CLI's budget flag stops it
  refusal   a reply ending with stop_reason "refusal"
  max_tokens  a reply ending with stop_reason "max_tokens"
  context   HTTP 400 "prompt is too long", as the API answers a request over the context window
  context_late  a Bash call reporting a prompt of 990,000 tokens, then HTTP 400 "prompt is too long" for
            every request that declares Bash (a request without it, such as a summary, gets text)
  timeout   `sleep 30` Bash calls forever, until the harness kills the session
  subagent  the main session starts a subagent (Agent or Task tool); the subagent makes SUB_TURNS
            priced Bash calls and ends; then the main session ends
  subagent_override  as subagent, but the call runs in the foreground and asks for model "fable" and
            effort "max" (the Agent tool's own override fields)
  web       a WebFetch call, then a WebSearch call, then an end
Faults and refusals: a Bash call first, then every later request of the main session is answered with
  rate_limit_retry_after  429 rate_limit_error with `retry-after: 5`
  rate_limit              429 rate_limit_error without retry-after
  overloaded              529 overloaded_error
  server_error            500 api_error
  pt_cap, pt_total, pt_stopped  403 permission_error with `x-should-retry: false` (the proposed
            passthrough refusal for a slot at its cap, the tranche's total reached, a stopped tranche)
  pt_model  404 not_found_error with `x-should-retry: false` (proposed: a model other than the bound one)
  pt_tool   400 invalid_request_error with `x-should-retry: false` (proposed: a provider-side tool)
  unauthorized  401 authentication_error (an expired or revoked credential)
  cache_writes  a normal end whose two requests each report 20,000 one-hour cache-write tokens
  drop      the stream is cut after its first content block (no message_delta, no message_stop)
  slow      the response starts only after --delay seconds (default 120), then ends normally
  transient the first three attempts of the second turn get 429 (retry-after 2), 529, 500; then an end
  usage_limit  429 rate_limit_error with `anthropic-ratelimit-unified-status: rejected`, representative claim
            `five_hour` and a reset --delay seconds ahead (the headers the CLI reads for a subscription limit)
  pt_model403, pt_tool403, pt_path, pt_token  403 permission_error with `x-should-retry: false` and an
            `lh-passthrough:` message (the one refusal form, for a model, a provider-side tool, a path, an
            unknown token)
  pt_token_first  the unknown-token refusal on the session's first request (no Bash call before it)
  placeholder  a call of the placeholder tool the deny list leaves (DeferredToolPlaceholder), then an end
  overage   a normal session whose every response carries the headers the CLI reads as paid extra usage:
            `anthropic-ratelimit-unified-status: rejected` with `…-overage-status: allowed` and
            `…-overage-in-use: true`
Any path other than the messages path answers --other-status (default 404) and is logged.
--watch NAMES (comma-separated) counts each name's whole-word occurrences in the system blocks, the tool
definitions and the messages of every request; --expect-bearer VALUE logs whether the authorization
header is `Bearer VALUE` (never the value).
"""

import argparse
import collections
import itertools
import json
import os
import re
import socketserver
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SUB_MARK = "stub-subagent-task"
SUB_TURNS = 3
PROBE = ("curl -sS -m 10 -o /dev/null -w 'vendor-api http=%{http_code}\\n' https://api.anthropic.com/v1/messages;"
         " echo curl_rc=$?; echo stub-normal > /tmp/stub-normal.txt")
SMALL = {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
FULL = {"input_tokens": 990000, "output_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
DEAR = {"input_tokens": 20000, "output_tokens": 100000, "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0}
HOUR_WRITES = {**SMALL, "cache_creation_input_tokens": 20000,
               "cache_creation": {"ephemeral_5m_input_tokens": 0, "ephemeral_1h_input_tokens": 20000}}
REDACT = ("x-api-key", "authorization")
LOOPBACK = ("127.0.0.1", "localhost")
NO_RETRY = {"x-should-retry": "false"}
PLACEHOLDER = "DeferredToolPlaceholder"
OVERAGE = {"anthropic-ratelimit-unified-status": "rejected", "anthropic-ratelimit-unified-overage-status": "allowed",
           "anthropic-ratelimit-unified-overage-in-use": "true",
           "anthropic-ratelimit-unified-representative-claim": "five_hour"}
FAULTS = {
    "rate_limit_retry_after": (429, "rate_limit_error", "stub: rate limited", {"retry-after": "5"}),
    "rate_limit": (429, "rate_limit_error", "stub: rate limited", {}),
    "overloaded": (529, "overloaded_error", "Overloaded", {}),
    "server_error": (500, "api_error", "Internal server error", {}),
    "pt_cap": (403, "permission_error", "lh-passthrough: slot cap reached", NO_RETRY),
    "pt_total": (403, "permission_error", "lh-passthrough: tranche total reached", NO_RETRY),
    "pt_stopped": (403, "permission_error", "lh-passthrough: tranche stopped", NO_RETRY),
    "pt_model": (404, "not_found_error", "lh-passthrough: model not allowed", NO_RETRY),
    "pt_tool": (400, "invalid_request_error", "lh-passthrough: provider-side tool refused", NO_RETRY),
    "pt_model403": (403, "permission_error", "lh-passthrough: model not allowed", NO_RETRY),
    "pt_tool403": (403, "permission_error", "lh-passthrough: provider-side tool refused", NO_RETRY),
    "pt_path": (403, "permission_error", "lh-passthrough: path not allowed", NO_RETRY),
    "pt_token": (403, "permission_error", "lh-passthrough: unknown token", NO_RETRY),
    "unauthorized": (401, "authentication_error", "stub: OAuth token has expired", {}),
}
TRANSIENT = [(429, "rate_limit_error", "stub: rate limited", {"retry-after": "2"}),
             (529, "overloaded_error", "Overloaded", {}), (500, "api_error", "Internal server error", {})]
TOO_LONG = (400, "invalid_request_error", "prompt is too long: 250000 tokens > 200000 maximum", {})
_ids = itertools.count(1)
_attempts = collections.Counter()


def _turn(body):
    return sum(1 for m in body.get("messages", []) if m.get("role") == "assistant")


def _first_user_text(body):
    content = (body.get("messages") or [{}])[0].get("content", "")
    return content if isinstance(content, str) else json.dumps(content)


def _declared(body, *names):
    tools = {t.get("name") for t in body.get("tools") or []}
    return next((n for n in names if n in tools), None)


def _tool(name, args):
    return {"type": "tool_use", "id": f"toolu_stub{next(_ids):04d}", "name": name, "input": args}


def _text(text):
    return {"type": "text", "text": text}


def _bash(body, command, usage=SMALL):
    if not _declared(body, "Bash"):
        return [_text("ok")], "end_turn", SMALL
    return [_tool("Bash", {"command": command, "description": "stub step"})], "tool_use", usage


def _subagent(body, turn, override=None):
    if SUB_MARK in _first_user_text(body):
        if turn < SUB_TURNS:
            return _bash(body, f"echo subagent turn {turn}", DEAR)
        return [_text("subagent done")], "end_turn", DEAR
    agent = _declared(body, "Agent", "Task")
    if turn == 0 and agent:
        args = {"description": "stub subagent", "prompt": f"{SUB_MARK}: run three echo commands",
                "subagent_type": "general-purpose", **(override or {})}
        return [_tool(agent, args)], "tool_use", SMALL
    return [_text("main done")], "end_turn", SMALL


def _context_late(body, turn):
    if turn == 0:
        return _bash(body, "true", FULL)
    return TOO_LONG if _declared(body, "Bash") else ([_text("summary")], "end_turn", SMALL)


def _web(body, turn):
    steps = [("WebFetch", {"url": "https://example.com/", "prompt": "Summarize the page."}),
             ("WebSearch", {"query": "terminal bench"})]
    if turn < len(steps) and _declared(body, "Bash"):  # web tools are deferred: called without being declared
        return [_tool(*steps[turn])], "tool_use", SMALL
    return [_text("web done")], "end_turn", SMALL


def _later(body, turn, answer):
    """A Bash call on the first turn, then `answer` (a fault or a special reply)."""
    return _bash(body, "true") if turn == 0 else answer


def _transient(body, turn):
    if turn == 0:
        return _bash(body, "true")
    _attempts[turn] += 1
    if _attempts[turn] <= len(TRANSIENT):
        return TRANSIENT[_attempts[turn] - 1]
    return [_text("done")], "end_turn", SMALL


def _usage_limit(body, turn):
    reset = str(int(time.time() + Stub.cfg.delay))
    headers = {"anthropic-ratelimit-unified-status": "rejected", "anthropic-ratelimit-unified-reset": reset,
               "anthropic-ratelimit-unified-representative-claim": "five_hour"}
    return _later(body, turn, (429, "rate_limit_error", "stub: usage limit reached", headers))


def _normal(body, turn):
    return _bash(body, PROBE) if turn == 0 else ([_text("done")], "end_turn", SMALL)


def _placeholder(body, turn):
    if turn == 0:
        return [_tool(PLACEHOLDER, {})], "tool_use", SMALL
    return [_text("done")], "end_turn", SMALL


def _hour_writes(body, turn):
    return _bash(body, PROBE, HOUR_WRITES) if turn == 0 else ([_text("done")], "end_turn", HOUR_WRITES)


SCENARIOS = {
    "normal": _normal,
    "cache_writes": _hour_writes,
    "placeholder": _placeholder,
    "overage": _normal,
    "context": lambda body, turn: TOO_LONG,
    "context_late": _context_late,
    "refusal": lambda body, turn: ([_text("I can't help with that.")], "refusal", SMALL),
    "max_tokens": lambda body, turn: ([_text("A long answer that stops here")], "max_tokens", SMALL),
    "budget": lambda body, turn: _bash(body, "true", DEAR),
    "timeout": lambda body, turn: _bash(body, "sleep 30"),
    "subagent": _subagent,
    "subagent_override": lambda body, turn: _subagent(
        body, turn, {"run_in_background": False, "model": "fable", "effort": "max"}),
    "web": _web,
    "drop": lambda body, turn: _later(body, turn, ([_text("cut")], "end_turn", SMALL, "drop")),
    "slow": lambda body, turn: _later(body, turn, ([_text("done")], "end_turn", SMALL, "slow")),
    "transient": _transient,
    "usage_limit": _usage_limit,
    **{name: (lambda fault: lambda body, turn: _later(body, turn, fault))(fault) for name, fault in FAULTS.items()},
    "pt_token_first": lambda body, turn: FAULTS["pt_token"],
}


def reply(scenario, body):
    """One request's answer: (content blocks, stop_reason, usage[, "drop" | "slow"]), or a fault as
    (status, error type, message, headers)."""
    return SCENARIOS[scenario](body, _turn(body))


def _message(model, content, stop_reason, usage):
    return {"id": f"msg_stub{next(_ids):04d}", "type": "message", "role": "assistant", "model": model,
            "content": content, "stop_reason": stop_reason, "stop_sequence": None, "usage": usage}


def _block_events(index, block):
    if block["type"] == "text":
        yield "content_block_start", {"index": index, "content_block": _text("")}
        yield "content_block_delta", {"index": index, "delta": {"type": "text_delta", "text": block["text"]}}
    else:
        yield "content_block_start", {"index": index, "content_block": {**block, "input": {}}}
        yield "content_block_delta", {"index": index, "delta": {
            "type": "input_json_delta", "partial_json": json.dumps(block["input"])}}
    yield "content_block_stop", {"index": index}


def sse_events(message):
    """The streamed form of a message, as (event name, data) pairs."""
    start = {**message, "content": [], "stop_reason": None, "usage": {**message["usage"], "output_tokens": 1}}
    yield "message_start", {"message": start}
    for index, block in enumerate(message["content"]):
        yield from _block_events(index, block)
    delta = {"stop_reason": message["stop_reason"], "stop_sequence": None}
    if message["stop_reason"] == "refusal":  # the form a public refusal archive shows (category, explanation)
        delta["stop_details"] = {"type": "refusal", "category": "bio", "explanation": "stub refusal"}
    yield "message_delta", {"delta": delta,
                            "usage": {"output_tokens": message["usage"]["output_tokens"]}}
    yield "message_stop", {}


def _redact(name, value):
    """Keep an authorization scheme ("Bearer"), never the credential."""
    if name.lower() not in REDACT:
        return value
    scheme = value.split(" ", 1)[0] if " " in value else ""
    return f"{scheme} <redacted>".strip()


def _system(body):
    """Each system block's size, first 80 characters (the identity line) and cache control; not the whole prompt."""
    system = body.get("system") or []
    blocks = [{"text": system}] if isinstance(system, str) else system
    return [{"chars": len(b.get("text", "")), "opening": b.get("text", "")[:80],
             **({"cache_control": b["cache_control"]} if "cache_control" in b else {})} for b in blocks]


def _blocks(content):
    blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content or []
    return [{"type": b.get("type"), "chars": len(b["text"]) if "text" in b else len(json.dumps(b)),
             **({"cache_control": b["cache_control"]} if "cache_control" in b else {})} for b in blocks]


def _mentions(body, names):
    """Whole-word occurrences of each name in the system blocks, the tool definitions and the messages."""
    parts = {"system": json.dumps(body.get("system") or ""), "tools": json.dumps(body.get("tools") or []),
             "messages": json.dumps(body.get("messages") or [])}
    return {n: {part: len(re.findall(rf"(?<![\w-]){re.escape(n)}(?![\w-])", text)) for part, text in parts.items()}
            for n in names}


def _tools(tools):
    """Each declared tool's name, size in characters and cache control; server tools whole."""
    return {"tools": [t.get("name") or t.get("type") for t in tools],
            "server_tools": [t for t in tools if "input_schema" not in t],
            "tool_chars": [len(json.dumps(t)) for t in tools],
            "tool_cache": [{"tool": t.get("name"), "cache_control": t["cache_control"]} for t in tools
                           if "cache_control" in t]}


def _record(path, headers, body):
    params = {k: v for k, v in body.items() if k not in ("messages", "system", "tools")}
    return {"path": path, "model": body.get("model"), **_tools(body.get("tools") or []),
            "headers": {k.lower(): _redact(k, v) for k, v in headers.items()},
            "params": params, "n_messages": len(body.get("messages", [])), "turn": _turn(body),
            "subagent": SUB_MARK in _first_user_text(body), "system": _system(body),
            "message_blocks": [[m.get("role"), _blocks(m.get("content"))] for m in body.get("messages") or []]}


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    cfg = None
    totals = dict.fromkeys(SMALL, 0)

    def log_message(self, *args):
        pass

    def _send_json(self, status, payload, headers=None):
        data = json.dumps(payload).encode()
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _log(self, row):
        with open(self.cfg.log, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def do_GET(self):
        self._log({"path": self.path, "method": "GET", "headers": _record(self.path, self.headers, {})["headers"]})
        self._send_json(*self._other())

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.loads(raw or b"{}")
        row = _record(self.path, self.headers, body)
        self._checks(row, body)
        status, payload, extra = self._answer(body)
        row.update(status=status, usage=payload.get("usage"), stop_reason=payload.get("stop_reason"),
                   content=[b.get("name") or b["type"] for b in payload.get("content", [])],
                   total_usage=dict(self.totals), mode=extra if status == 200 else None, time=time.time())
        self._log(row)
        if status != 200:
            self._send_json(status, payload, extra)
        elif body.get("stream"):
            self._stream(payload, extra)
        else:
            self._send_json(status, payload, self._served_headers())

    def _served_headers(self):
        return OVERAGE if self.cfg.scenario == "overage" else {}

    def _checks(self, row, body):
        if self.cfg.watch:
            row["mentions"] = _mentions(body, self.cfg.watch.split(","))
        if self.cfg.expect_bearer is not None:
            row["bearer_matches"] = self.headers.get("authorization") == f"Bearer {self.cfg.expect_bearer}"

    def _other(self):
        status = self.cfg.other_status
        etype = {401: "authentication_error", 403: "permission_error"}.get(status, "not_found_error")
        return _error(status, etype, f"stub: {self.path}", {})

    def _answer(self, body):
        """(status, payload, headers for an error or the mode of a reply)."""
        if not self.path.startswith("/v1/messages") or self.path.startswith("/v1/messages/"):
            return self._other()
        if body.get("model") != self.cfg.model:
            return _error(404, "not_found_error", f"model: {body.get('model')}", {})
        canned = reply(self.cfg.scenario, body)
        if isinstance(canned[0], int):
            return _error(*canned)
        for key in self.totals:
            self.totals[key] += canned[2][key]
        return 200, _message(self.cfg.model, *canned[:3]), canned[3] if len(canned) > 3 else None

    def _stream(self, message, mode):
        if mode == "slow":
            time.sleep(self.cfg.delay)
        self.send_response(200)
        for key, value in self._served_headers().items():
            self.send_header(key, value)
        self.send_header("content-type", "text/event-stream")
        self.send_header("connection", "close")
        self.end_headers()
        for name, data in sse_events(message):
            self.wfile.write(f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n".encode())
            self.wfile.flush()
            if mode == "drop" and name == "content_block_delta":
                break
        self.close_connection = True


def _error(status, etype, message, headers):
    return status, {"type": "error", "error": {"type": etype, "message": message}}, headers


class _UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser()
    for flag in ("--model", "--log"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--scenario", required=True, choices=sorted(SCENARIOS))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--unix")
    parser.add_argument("--delay", type=float, default=120)
    parser.add_argument("--other-status", type=int, default=404)
    parser.add_argument("--watch", default="")
    parser.add_argument("--expect-bearer")
    Stub.cfg = parser.parse_args()
    if Stub.cfg.host not in LOOPBACK:
        parser.error(f"--host {Stub.cfg.host}: the stub binds only a loopback address ({', '.join(LOOPBACK)}) "
                     "or a unix socket (--unix)")
    if Stub.cfg.unix:
        if os.path.exists(Stub.cfg.unix):
            os.unlink(Stub.cfg.unix)
        server = _UnixServer(Stub.cfg.unix, Stub)
        print("listening", Stub.cfg.unix, flush=True)
    else:
        server = ThreadingHTTPServer((Stub.cfg.host, Stub.cfg.port), Stub)
        print("listening", Stub.cfg.host, server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
