#!/usr/bin/env python3
from __future__ import annotations

import json
import sys


SESSION_ID = "019f929b-bea9-76a2-955d-5991618b6f34"


if sys.argv[1:] == ["--version"]:
    print("codex-cli 0.145.0")
    raise SystemExit(0)

arguments = sys.argv[1:]
if not arguments or arguments[0] != "exec":
    raise SystemExit(64)
if arguments.count("--json") != 1:
    raise SystemExit(65)
if arguments.count("--dangerously-bypass-approvals-and-sandbox") != 1:
    raise SystemExit(66)
if arguments.count("--skip-git-repo-check") != 1:
    raise SystemExit(67)
if "resume" in arguments:
    raise SystemExit(68)

rows = [
    {"type": "thread.started", "thread_id": SESSION_ID},
    {"type": "turn.started"},
    {
        "type": "item.completed",
        "item": {"id": "item_0", "type": "agent_message", "text": "OK"},
    },
    {
        "type": "turn.completed",
        "usage": {
            "input_tokens": 13,
            "cached_input_tokens": 5,
            "cache_write_input_tokens": 2,
            "output_tokens": 3,
            "reasoning_output_tokens": 1,
        },
    },
]
for row in rows:
    print(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
raise SystemExit(7 if "exit-7" in arguments else 0)
