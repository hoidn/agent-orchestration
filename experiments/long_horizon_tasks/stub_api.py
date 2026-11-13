"""A local stand-in for the model API, to record what the real CLI sends and how it ends a session.

Serves `POST /v1/messages` (streamed or plain) with canned replies chosen by a scenario, and refuses any
model other than the one configured (404 `not_found_error`, as the API does). Every request is appended to
the log as one JSON line: path, model, declared tools, headers (key and token redacted), the request's
top-level parameters (no message or system text), the usage served and the running total. Any other path
answers 404 and is logged too. Standard library only; no request leaves the host.

Usage: python -I stub_api.py --host H --port P --model claude-haiku-5-5 --scenario NAME --log FILE
Prints `listening <host> <port>` once bound (port 0 picks a free port).

Scenarios (the reply depends on the request, so side requests and subagents get sensible answers):
  normal    a Bash call (probes the vendor's API host from inside the container), then an end
  budget    Bash calls forever, each reply priced high, until the CLI's budget flag stops it
  refusal   a reply ending with stop_reason "refusal"
  max_tokens  a reply ending with stop_reason "max_tokens"
  context   HTTP 400 "prompt is too long", as the API answers a request over the context window
  timeout   `sleep 30` Bash calls forever, until the harness kills the session
  subagent  the main session starts a subagent (Agent or Task tool); the subagent makes SUB_TURNS
            priced Bash calls and ends; then the main session ends
  web       a WebFetch call, then a WebSearch call, then an end
"""

import argparse
import itertools
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SUB_MARK = "stub-subagent-task"
SUB_TURNS = 3
PROBE = ("curl -sS -m 10 -o /dev/null -w 'vendor-api http=%{http_code}\\n' https://api.anthropic.com/v1/messages;"
         " echo curl_rc=$?; echo stub-normal > /tmp/stub-normal.txt")
SMALL = {"input_tokens": 1000, "output_tokens": 100, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
DEAR = {"input_tokens": 20000, "output_tokens": 100000, "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0}
REDACT = ("x-api-key", "authorization")
_ids = itertools.count(1)


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


def _subagent(body, turn):
    if SUB_MARK in _first_user_text(body):
        if turn < SUB_TURNS:
            return _bash(body, f"echo subagent turn {turn}", DEAR)
        return [_text("subagent done")], "end_turn", DEAR
    agent = _declared(body, "Agent", "Task")
    if turn == 0 and agent:
        args = {"description": "stub subagent", "prompt": f"{SUB_MARK}: run three echo commands",
                "subagent_type": "general-purpose"}
        return [_tool(agent, args)], "tool_use", SMALL
    return [_text("main done")], "end_turn", SMALL


def _web(body, turn):
    steps = [("WebFetch", {"url": "https://example.com/", "prompt": "Summarize the page."}),
             ("WebSearch", {"query": "terminal bench"})]
    if turn < len(steps) and _declared(body, steps[turn][0]):
        return [_tool(*steps[turn])], "tool_use", SMALL
    return [_text("web done")], "end_turn", SMALL


def reply(scenario, body):
    """Return (content blocks, stop_reason, usage) for one request, or None for a context-limit error."""
    turn = _turn(body)
    if scenario == "context":
        return None
    if scenario == "refusal":
        return [_text("I can't help with that.")], "refusal", SMALL
    if scenario == "max_tokens":
        return [_text("A long answer that stops here")], "max_tokens", SMALL
    if scenario == "budget":
        return _bash(body, "true", DEAR)
    if scenario == "timeout":
        return _bash(body, "sleep 30")
    if scenario == "subagent":
        return _subagent(body, turn)
    if scenario == "web":
        return _web(body, turn)
    if turn == 0:
        return _bash(body, PROBE)
    return [_text("done")], "end_turn", SMALL


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


def _record(path, headers, body):
    params = {k: v for k, v in body.items() if k not in ("messages", "system", "tools")}
    return {"path": path, "model": body.get("model"),
            "tools": [t.get("name") or t.get("type") for t in body.get("tools") or []],
            "server_tools": [t for t in body.get("tools") or [] if "input_schema" not in t],
            "headers": {k.lower(): ("<redacted>" if k.lower() in REDACT else v) for k, v in headers.items()},
            "params": params, "n_messages": len(body.get("messages", [])), "turn": _turn(body),
            "subagent": SUB_MARK in _first_user_text(body)}


class Stub(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    cfg = None
    totals = dict.fromkeys(SMALL, 0)

    def log_message(self, *args):
        pass

    def _send_json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _log(self, row):
        with open(self.cfg.log, "a") as fh:
            fh.write(json.dumps(row) + "\n")

    def do_GET(self):
        self._log({"path": self.path, "method": "GET", "headers": _record(self.path, self.headers, {})["headers"]})
        self._send_json(404, {"type": "error", "error": {"type": "not_found_error", "message": "stub: no route"}})

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get("content-length", 0)))
        body = json.loads(raw or b"{}")
        row = _record(self.path, self.headers, body)
        status, payload = self._answer(body)
        row.update(status=status, usage=payload.get("usage"), stop_reason=payload.get("stop_reason"),
                   content=[b.get("name") or b["type"] for b in payload.get("content", [])],
                   total_usage=dict(self.totals))
        self._log(row)
        if status == 200 and body.get("stream"):
            self._stream(payload)
        else:
            self._send_json(status, payload)

    def _answer(self, body):
        if not self.path.startswith("/v1/messages") or self.path.startswith("/v1/messages/"):
            return 404, {"type": "error", "error": {"type": "not_found_error", "message": f"stub: {self.path}"}}
        if body.get("model") != self.cfg.model:
            return 404, {"type": "error", "error": {"type": "not_found_error", "message": f"model: {body.get('model')}"}}
        canned = reply(self.cfg.scenario, body)
        if canned is None:
            return 400, {"type": "error", "error": {"type": "invalid_request_error",
                                                    "message": "prompt is too long: 250000 tokens > 200000 maximum"}}
        for key, value in canned[2].items():
            self.totals[key] += value
        return 200, _message(self.cfg.model, *canned)

    def _stream(self, message):
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("connection", "close")
        self.end_headers()
        for name, data in sse_events(message):
            self.wfile.write(f"event: {name}\ndata: {json.dumps({'type': name, **data})}\n\n".encode())
        self.wfile.flush()
        self.close_connection = True


def main():
    parser = argparse.ArgumentParser()
    for flag in ("--host", "--model", "--scenario", "--log"):
        parser.add_argument(flag, required=True)
    parser.add_argument("--port", type=int, required=True)
    Stub.cfg = parser.parse_args()
    server = ThreadingHTTPServer((Stub.cfg.host, Stub.cfg.port), Stub)
    print("listening", Stub.cfg.host, server.server_address[1], flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
