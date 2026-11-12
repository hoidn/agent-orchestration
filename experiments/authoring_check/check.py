#!/usr/bin/env python3
"""Executable pass check for one authoring-check session.

Usage: check.py SESSION_DIR

Copies SESSION_DIR (the agent's tally.orc, commands.json and scripts) into a
fresh directory per case, with a pristine line_count.sh from this kit, and runs
the `orchestrator` found on PATH there: `compile` once, then `run` and
`report --format json` for a visible case, two fixed hidden cases and one
hidden case drawn at random now, whose expected record follows from the rule
in task.md. A case passes when `run` exits 0, `run.workflow_outputs` equals the
expected record, the report shows at least rounds + 1 completed command steps,
and line_count.sh was called exactly rounds + 1 times (one count per round), so
a single script that does the whole loop fails. Prints one JSON object and
exits 0 on a pass, 1 on a fail. Calls no model.
"""

from __future__ import annotations

import json
import secrets
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

KIT = Path(__file__).resolve().parent
TIMEOUT_SEC = 120
MANIFEST = ("--command-boundaries-file", "commands.json")
MAX_ROUNDS = 6
# (name, lines already in notes.txt, target)
FIXED_CASES = (("visible", 2, 5), ("hidden_already_satisfied", 4, 3), ("hidden_bound_reached", 1, 50))


def expected(lines: int, target: int) -> dict:
    """task.md's rule: append until the count reaches target, at most six times."""
    rounds = min(MAX_ROUNDS, max(0, target - lines))
    return {"lines": lines + rounds, "rounds": rounds}


def cases() -> list[tuple[str, int, int]]:
    # Drawn at check time, so a table of the fixed cases fails; target > 5 never equals a fixed case.
    return [*FIXED_CASES, ("hidden_random", secrets.randbelow(5), 6 + secrets.randbelow(7))]
IGNORED = shutil.ignore_patterns(".orchestrate", "line_count.calls")


def _orchestrator(workspace: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["orchestrator", *argv], cwd=workspace, capture_output=True, text=True,
                              timeout=TIMEOUT_SEC, check=False)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(argv, 124, "", f"timed out after {TIMEOUT_SEC} s")


def _workspace(session: Path, parent: Path, name: str) -> Path:
    workspace = parent / name
    shutil.copytree(session, workspace, ignore=IGNORED)
    shutil.copy2(KIT / "line_count.sh", workspace / "line_count.sh")
    return workspace


def _report(workspace: Path) -> tuple[object, int]:
    """(run.workflow_outputs, number of completed command steps) from `report --format json`."""
    runs = sorted((workspace / ".orchestrate" / "runs").glob("*"))
    if len(runs) != 1:
        return None, 0
    report = _orchestrator(workspace, "report", "--run-id", runs[0].name, "--format", "json")
    try:
        shown = json.loads(report.stdout)
        steps = [step for step in shown["steps"] if step.get("kind") == "command" and step.get("status") == "completed"]
        return shown["run"]["workflow_outputs"], len(steps)
    except (ValueError, KeyError, TypeError):
        return None, 0


def _case(session: Path, parent: Path, name: str, lines: int, target: int) -> dict:
    workspace = _workspace(session, parent, name)
    (workspace / "notes.txt").write_text("".join(f"line {n}\n" for n in range(lines)), encoding="utf-8")
    run = _orchestrator(workspace, "run", "tally.orc", *MANIFEST,
                        "--input", "file=notes.txt", "--input", f"target={target}")
    calls_log = workspace / "line_count.calls"
    calls = len(calls_log.read_text().splitlines()) if calls_log.exists() else 0
    outputs, command_steps = _report(workspace) if run.returncode == 0 else (None, 0)
    want = expected(lines, target)
    passed = (run.returncode == 0 and outputs == want and command_steps >= want["rounds"] + 1
              and calls == want["rounds"] + 1)
    return {"case": name, "lines": lines, "target": target, "passed": passed, "run_exit": run.returncode,
            "outputs": outputs, "expected": want, "command_steps": command_steps, "line_count_calls": calls,
            "stderr_tail": run.stderr[-2000:]}


def check(session: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="authoring-check-") as scratch:
        parent = Path(scratch)
        compiled = _orchestrator(_workspace(session, parent, "compile"), "compile", "tally.orc", *MANIFEST)
        result = {"session": str(session), "compile_exit": compiled.returncode,
                  "compile_stderr_tail": compiled.stderr[-2000:], "cases": []}
        if compiled.returncode == 0:
            result["cases"] = [_case(session, parent, *case) for case in cases()]
    result["passed"] = compiled.returncode == 0 and all(case["passed"] for case in result["cases"])
    return result


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not Path(argv[0]).is_dir():
        print("usage: check.py SESSION_DIR", file=sys.stderr)
        return 2
    result = check(Path(argv[0]).resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
