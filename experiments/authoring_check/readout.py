#!/usr/bin/env python3
"""Readout of the authoring check: execution outcomes and cost only.

Usage: readout.py SESSIONS_ROOT

Reads every SESSIONS_ROOT/<arm>-<n>/ written by run_session.sh and prints one
JSON object: per arm, sessions passed out of sessions run and the summed cost;
per session, pass, the reasons for a fail, the tokens and cost the CLI
reported, the models it reported, wall time, and how many `orchestrator`
invocations failed. A session passes only when check.py passed, the CLI
finished with a successful result inside the wall limit and the spend cap,
only the bound model was used, and no tool call named a path under the
checkout. Makes no quality claim and calls no model.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else ():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    return events


def _blocks(events: list[dict], kind: str) -> list[dict]:
    return [block for event in events if isinstance(event.get("message"), dict)
            for block in event["message"].get("content") or () if isinstance(block, dict) and block.get("type") == kind]


def _tool_facts(events: list[dict], checkout: str) -> tuple[int, int, bool]:
    """(orchestrator invocations, failed ones, whether any tool call named a checkout path)."""
    uses = _blocks(events, "tool_use")
    invocations = {use["id"] for use in uses if use.get("name") == "Bash"
                   and "orchestrator" in str((use.get("input") or {}).get("command", ""))}
    failed = sum(1 for result in _blocks(events, "tool_result")
                 if result.get("tool_use_id") in invocations and result.get("is_error"))
    reads_checkout = any(checkout in json.dumps(use.get("input")) for use in uses)
    return len(invocations), failed, reads_checkout


def _fail_reasons(meta: dict, check: dict, result: dict, models: list[str], reads_checkout: bool) -> list[str]:
    reasons = [] if check.get("passed") else ["check_failed"]
    if meta["claude_exit"] != 0:
        reasons.append("wall_limit" if meta["claude_exit"] in (124, 137) else f"claude_exit_{meta['claude_exit']}")
    if result.get("subtype") != "success" or result.get("is_error"):
        reasons.append(f"result_{result.get('subtype', 'missing')}")
    if any(model != meta["model"] for model in models):
        reasons.append("other_model")
    if reads_checkout:
        reasons.append("checkout_read")
    return reasons


def session_readout(directory: Path) -> dict:
    meta_path = directory / "session.json"
    if not meta_path.exists():
        return {"session": directory.name, "passed": False, "fail_reasons": ["incomplete"]}
    meta = json.loads(meta_path.read_text())
    check_path = directory / "check.json"
    check = json.loads(check_path.read_text()) if check_path.exists() and check_path.stat().st_size else {}
    events = _events(directory / "transcript.jsonl")
    result = next((event for event in reversed(events) if event.get("type") == "result"), {})
    models = sorted(result.get("modelUsage") or {})
    invocations, failed, reads_checkout = _tool_facts(events, meta["checkout"])
    reasons = _fail_reasons(meta, check, result, models, reads_checkout)
    usage = result.get("usage") or {}
    return {"session": directory.name, "arm": meta["arm"], "passed": not reasons, "fail_reasons": reasons,
            "cost_usd": result.get("total_cost_usd"), "tokens": {key: usage.get(key) for key in TOKEN_FIELDS},
            "models": models, "wall_sec": meta["ended"] - meta["started"],
            "orchestrator_invocations": invocations, "orchestrator_failures": failed}


def readout(root: Path) -> dict:
    sessions = [session_readout(path) for path in sorted(root.iterdir()) if path.is_dir()]
    arms: dict[str, dict] = {}
    for session in sessions:
        arm = arms.setdefault(session.get("arm") or session["session"].rsplit("-", 1)[0],
                              {"run": 0, "passed": 0, "cost_usd": 0.0})
        arm["run"] += 1
        arm["passed"] += session["passed"]
        arm["cost_usd"] += session.get("cost_usd") or 0.0
    return {"arms": arms, "sessions": sessions}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print("usage: readout.py SESSIONS_ROOT", file=sys.stderr)
        return 2
    print(json.dumps(readout(Path(argv[0])), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
