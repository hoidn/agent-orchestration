#!/usr/bin/env python3
"""Readout of the authoring check: execution outcomes and cost only.

Usage: readout.py SESSIONS_ROOT

Reads every SESSIONS_ROOT/<before|after>-<1..3>/ written by run_session.sh and
prints one JSON object: per arm, sessions passed out of sessions run, the known
cost, the sessions whose cost is unknown and the ledger charge (known cost plus
the USD 2 cap for each unknown one); per session, pass, the reasons for a fail,
tokens, cost, the models seen, the CLI version, wall time and failed
`orchestrator` invocations.

A session passes only when check.py passed; the CLI ended with a successful
result inside the wall limit and the spend cap; the models seen on the init
event, every assistant event and the result are exactly the bound model; no
tool call starts `claude` or `codex` (in command position) or names another
model; no nested Claude
or Codex session was recorded for its directory; no no-provider stub was
called; and no tool input or output names the checkout (absolute, under `~` or
`$HOME`, or relative), the sessions root, or other sessions' stores. Makes no
quality claim and calls no model.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from experiments.compare import scan  # noqa: E402

CAP_USD = 2.0
SESSION_NAME = re.compile(r"(before|after)-[1-3]")
TOKEN_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
# `claude` or `codex` in command position (line start, after ; & | ( ` or $(, behind exec/env/... or VAR=x).
NESTED_CLI = re.compile(r"(?m)(?:^|[;&|(`]|\$\()\s*(?:(?:exec|env|nohup|command|xargs|sudo|timeout\s+\S+)\s+|\S+=\S*\s+)*"
                        r"(?:\S*/)?(?:claude|codex)(?![\w.-])")
MODEL_ID = re.compile(r"\b(?:claude-[a-z]+-[\w.-]+|gpt-\d[\w.-]*)")
OTHER_SESSIONS = re.compile(r"\.claude/projects|\.codex/(?:sessions|history)|claude-tmux-sockets")


def _rows(path: Path) -> tuple[list[dict], int]:
    rows, undecodable = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if path.exists() else ():
        try:
            rows.append(json.loads(line))
        except ValueError:
            undecodable += 1
    return rows, undecodable


def _blocks(rows: list[dict], kind: str) -> list[dict]:
    return [block for row in rows if isinstance(row.get("message"), dict)
            for block in row["message"].get("content") or () if isinstance(block, dict) and block.get("type") == kind]


def _models(rows: list[dict], result: dict) -> list[str]:
    seen = {row["model"] for row in rows if row.get("type") == "system" and isinstance(row.get("model"), str)}
    seen.update(model for row in rows for model in scan.answering_model(row))
    seen.update(result.get("modelUsage") or {})
    return sorted(seen)


def _forbidden(meta: dict) -> list[tuple[str, re.Pattern]]:
    checkout, home = Path(meta["checkout"]), Path(meta["home"])
    spellings = [re.escape(str(checkout).lstrip("/"))]  # absolute, and relative such as ../home/...
    if checkout.is_relative_to(home):
        spellings.append(re.escape(str(checkout.relative_to(home))))  # ~/..., $HOME/..., cd ~ && ...
    return [("checkout_read", re.compile("|".join(spellings))),
            ("sessions_root_read", re.compile(scan.spelled(meta["sessions_root"], home) + scan.BOUNDARY)),
            ("other_sessions_read", OTHER_SESSIONS)]


def _tool_reasons(rows: list[dict], meta: dict) -> list[str]:
    uses, results = _blocks(rows, "tool_use"), _blocks(rows, "tool_result")
    inputs = [json.dumps(use.get("input"), ensure_ascii=False) for use in uses]
    values = [value for use in uses for value in (use.get("input") or {}).values() if isinstance(value, str)]
    reasons = []
    if any(NESTED_CLI.search(value) for value in values) or any(
            set(MODEL_ID.findall(text)) - {meta["model"]} for text in inputs):
        reasons.append("nested_cli")
    texts = inputs + [json.dumps(result.get("content"), ensure_ascii=False) for result in results]
    reasons += [name for name, pattern in _forbidden(meta) if any(pattern.search(text) for text in texts)]
    return reasons


def _orchestrator_failures(rows: list[dict]) -> tuple[int, int]:
    invocations = {use["id"] for use in _blocks(rows, "tool_use") if use.get("name") == "Bash"
                   and "orchestrator" in str((use.get("input") or {}).get("command", ""))}
    failed = sum(1 for result in _blocks(rows, "tool_result")
                 if result.get("tool_use_id") in invocations and result.get("is_error"))
    return len(invocations), failed


def _nested_sessions(meta: dict) -> list[str]:
    work, home = Path(meta["work_during_session"]), Path(meta["home"])
    found = [*scan.claude_sessions(work, home), *scan.codex_sessions(work, meta["started"], home)]
    return [str(path) for path in found]


def _fail_reasons(directory: Path, meta: dict, rows: list[dict], result: dict, models: list[str]) -> list[str]:
    check_path = directory / "check.json"
    check = json.loads(check_path.read_text()) if check_path.exists() and check_path.stat().st_size else {}
    reasons = [] if check.get("passed") else ["check_failed"]
    if meta["claude_exit"] != 0:
        reasons.append("wall_limit" if meta["claude_exit"] in (124, 137) else f"claude_exit_{meta['claude_exit']}")
    if result.get("subtype") != "success" or result.get("is_error"):
        reasons.append(f"result_{result.get('subtype', 'missing')}")
    if models != [meta["model"]]:
        reasons.append("models_not_exactly_bound")
    if _nested_sessions(meta):
        reasons.append("nested_session")
    if (directory / "no-provider.log").exists():
        reasons.append("provider_stub_called")
    return reasons + _tool_reasons(rows, meta)


def session_readout(directory: Path) -> dict:
    meta_path = directory / "session.json"
    if not meta_path.exists():
        return {"session": directory.name, "arm": directory.name.rsplit("-", 1)[0], "passed": False,
                "fail_reasons": ["incomplete"], "cost_usd": None}
    meta = json.loads(meta_path.read_text())
    rows, undecodable = _rows(directory / "transcript.jsonl")
    result = next((row for row in reversed(rows) if row.get("type") == "result"), {})
    models = _models(rows, result)
    reasons = _fail_reasons(directory, meta, rows, result, models)
    invocations, failed = _orchestrator_failures(rows)
    usage = result.get("usage") or {}
    return {"session": directory.name, "arm": meta["arm"], "passed": not reasons, "fail_reasons": reasons,
            "cost_usd": result.get("total_cost_usd"), "tokens": {key: usage.get(key) for key in TOKEN_FIELDS},
            "models": models, "claude_version": meta.get("claude_version"), "wall_sec": meta["ended"] - meta["started"],
            "orchestrator_invocations": invocations, "orchestrator_failures": failed,
            "undecodable_transcript_lines": undecodable, "nested_sessions": _nested_sessions(meta)}


def readout(root: Path) -> dict:
    sessions = [session_readout(path) for path in sorted(root.iterdir())
                if path.is_dir() and SESSION_NAME.fullmatch(path.name)]
    arms: dict[str, dict] = {}
    for session in sessions:
        arm = arms.setdefault(session["arm"], {"run": 0, "passed": 0, "cost_known_usd": 0.0,
                                               "cost_unknown_sessions": 0, "ledger_charge_usd": 0.0})
        arm["run"] += 1
        arm["passed"] += session["passed"]
        known = session["cost_usd"] is not None
        arm["cost_known_usd"] += session["cost_usd"] if known else 0.0
        arm["cost_unknown_sessions"] += not known
        arm["ledger_charge_usd"] += session["cost_usd"] if known else CAP_USD
    return {"arms": arms, "sessions": sessions}


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print("usage: readout.py SESSIONS_ROOT", file=sys.stderr)
        return 2
    print(json.dumps(readout(Path(argv[0])), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
