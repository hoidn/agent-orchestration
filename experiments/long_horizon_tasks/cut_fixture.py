"""Cut a fixture from one recorded trial: the stream's init event and last events, the harness's exception class,
the CLI's exit code and the trial's usage figures. Model text, tool input and tool output are dropped (task
content); CLI-made text (a `<synthetic>` message, an error result) is kept; home paths become `<home>`.

Usage: python -I cut_fixture.py <trial dir holding result.json and agent/> <source label> <out.json>
"""

import json
import re
import sys
from pathlib import Path

TAIL = 4


def _cut_message(message):
    keep = {k: message.get(k) for k in ("model", "stop_reason", "stop_details", "usage") if k in message}
    synthetic = message.get("model") == "<synthetic>"
    keep["content"] = [b if synthetic else {"type": b.get("type"), **({"name": b["name"]} if "name" in b else {})}
                       for b in message.get("content") or [] if isinstance(b, dict)]
    return keep


def cut_event(event):
    kind = event.get("type")
    if kind == "assistant":
        cut = {k: v for k, v in event.items() if k not in ("message", "uuid", "session_id")}
        return {**cut, "message": _cut_message(event.get("message") or {})}
    if kind == "user":
        blocks = (event.get("message") or {}).get("content")
        flags = [b.get("is_error") for b in blocks if isinstance(b, dict)] if isinstance(blocks, list) else []
        return {"type": "user", "parent_tool_use_id": event.get("parent_tool_use_id"), "tool_result_is_error": flags}
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
            "init": cut_event(events[0]) if events and events[0].get("subtype") == "init" else None,
            "n_events": len(events),
            "stream_tail": [cut_event(e) for e in events[-TAIL:]]}


def main(trial, source, out):
    text = json.dumps(fixture(Path(trial), source), indent=1)
    Path(out).write_text(re.sub(r"/home/[^/\"\s]+", "<home>", text) + "\n")


if __name__ == "__main__":
    main(*sys.argv[1:])
