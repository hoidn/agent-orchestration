"""Cut committed fixtures from local recordings; the raw recordings stay in the local cache.

Stream fixture (one recorded trial): the stream's init event and last events, the count of `api_retry`
events, the harness's exception class, the CLI's exit code, the trial's usage figures and the verifier's
result. Model text, tool input and tool output are dropped (task content); CLI-made text (a `<synthetic>`
message, an error result) is kept; home paths become `<home>`.

Request fixture (one recording's `stub.jsonl`): what the CLI sent, as distinct request shapes plus one row
per request `[shape index, status, number of messages, seconds since the first request, stub fault mode]`.
A shape keeps the method and path, every header name, the values of the headers a rule may match
(`SHOWN_HEADERS`, and the user agent's product token), `model`, effort (`output_config.effort`),
`max_tokens`, `stream`, declared tool names, server-tool types, the names of the other body fields, and each
system block's length and `cache_control`. It never keeps system or message text, `metadata`, or a
credential: `x-api-key` and `authorization` become `<dummy>` (an authorization keeps its scheme).

Usage: python -I cut_fixture.py <trial dir holding result.json and agent/> <source label> <out.json>
       python -I cut_fixture.py requests <stub.jsonl> <source label> <out.json>
"""

import json
import re
import sys
from pathlib import Path

TAIL = 4
SHOWN_HEADERS = ("anthropic-beta", "anthropic-version", "content-type", "x-app")
SECRET_HEADERS = ("x-api-key", "authorization")
NAMED_PARAMS = ("model", "metadata", "max_tokens", "stream", "output_config")


def _cut_message(message):
    keep = {k: message.get(k) for k in ("model", "stop_reason", "stop_details", "usage") if k in message}
    synthetic = message.get("model") == "<synthetic>"
    keep["content"] = [b if synthetic else {"type": b.get("type"), **({"name": b["name"]} if "name" in b else {})}
                       for b in message.get("content") or [] if isinstance(b, dict)]
    return keep


def _cut_user(event):
    blocks = (event.get("message") or {}).get("content")
    blocks = blocks if isinstance(blocks, list) else []
    flags = [b.get("is_error") for b in blocks if isinstance(b, dict)]
    return {"type": "user", "parent_tool_use_id": event.get("parent_tool_use_id"), "tool_result_is_error": flags}


def cut_event(event):
    kind = event.get("type")
    if kind == "assistant":
        cut = {k: v for k, v in event.items() if k not in ("message", "uuid", "session_id")}
        return {**cut, "message": _cut_message(event.get("message") or {})}
    if kind == "user":
        return _cut_user(event)
    if kind == "result" and not event.get("is_error") and event.get("subtype") == "success":
        return {**event, "result": "<cut: model text>"}
    return event


def _exit_code(message):
    found = re.search(r"Command failed \(exit (\d+)\)", message or "")
    return int(found.group(1)) if found else None


def fixture(trial, source):
    result = json.loads((trial / "result.json").read_text())
    exc = result.get("exception_info") or {}
    stream = trial / "agent" / "claude-code.txt"
    events = [json.loads(line) for line in stream.read_text().splitlines() if line.startswith("{")] \
        if stream.exists() else []
    return {"source": source,
            "harness_exception": exc.get("exception_type"),
            "cli_exit_code": _exit_code(exc.get("exception_message")),
            "agent_result": result.get("agent_result"),
            "verifier_result": result.get("verifier_result"),
            "init": next((cut_event(e) for e in events if e.get("subtype") == "init"), None),
            "n_events": len(events),
            "n_api_retry": sum(e.get("subtype") == "api_retry" for e in events),
            "stream_tail": [cut_event(e) for e in events[-TAIL:]]}


def _header(name, value):
    if name in SECRET_HEADERS:
        return value.replace("<redacted>", "<dummy>") if " " in value else "<dummy>"
    if name == "user-agent":
        return value.split(" ", 1)[0]
    return value if name in SHOWN_HEADERS else None


def _body(params):
    return {"effort": (params.get("output_config") or {}).get("effort"), "max_tokens": params.get("max_tokens"),
            "stream": params.get("stream"), "other_params": sorted(k for k in params if k not in NAMED_PARAMS)}


def _shape(row):
    return {"method": row.get("method", "POST"), "path": row.get("path"), "subagent": row.get("subagent"),
            "headers": {k: _header(k, v) for k, v in sorted((row.get("headers") or {}).items())},
            "model": row.get("model"), **_body(row.get("params") or {}),
            "tools": row.get("tools"), "server_tools": [t.get("type") for t in row.get("server_tools") or []],
            "system": [{k: b[k] for k in ("chars", "cache_control") if k in b} for b in row.get("system") or []]}


def requests(log, source):
    rows = [json.loads(line) for line in Path(log).read_text().splitlines() if line.strip()]
    shapes, out = [], []
    start = next((r["time"] for r in rows if "time" in r), None)
    for row in rows:
        shape = _shape(row)
        if shape not in shapes:
            shapes.append(shape)
        since = round(row["time"] - start, 1) if "time" in row else None
        out.append([shapes.index(shape), row.get("status"), row.get("n_messages"), since, row.get("mode")])
    return {"source": source, "shapes": shapes, "requests": out}


def _write(data, out):
    text = json.dumps(data, indent=1)
    Path(out).write_text(re.sub(r"/home/[^/\"\s]+", "<home>", text) + "\n")


def main(argv):
    if argv[0] == "requests":
        _write(requests(argv[1], argv[2]), argv[3])
    else:
        _write(fixture(Path(argv[0]), argv[1]), argv[2])


if __name__ == "__main__":
    main(sys.argv[1:])
