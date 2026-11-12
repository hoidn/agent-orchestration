#!/usr/bin/env python3
"""Executable pass check for one authoring-check session.

Usage: check.py SESSION_DIR

Copies SESSION_DIR (the agent's tally.orc, commands.json and scripts) into a
fresh directory per case, with a pristine line_count.sh from this kit, and runs
the `orchestrator` found on PATH there: `compile` once, then `run` and
`report --format json` for a visible case and two hidden cases. A case passes
when `run` exits 0 and `run.workflow_outputs` equals the expected record; a
hidden case also needs line_count.sh to have been called during its run.
Prints one JSON object and exits 0 on a pass, 1 on a fail. Calls no model.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

KIT = Path(__file__).resolve().parent
TIMEOUT_SEC = 120
MANIFEST = ("--command-boundaries-file", "commands.json")
# (name, lines already in notes.txt, target, expected record, hidden)
CASES = (
    ("visible", 2, 5, {"lines": 5, "rounds": 3}, False),
    ("hidden_already_satisfied", 4, 3, {"lines": 4, "rounds": 0}, True),
    ("hidden_bound_reached", 1, 50, {"lines": 7, "rounds": 6}, True),
)
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


def _outputs(workspace: Path) -> object:
    runs = sorted((workspace / ".orchestrate" / "runs").glob("*"))
    if len(runs) != 1:
        return None
    report = _orchestrator(workspace, "report", "--run-id", runs[0].name, "--format", "json")
    try:
        return json.loads(report.stdout)["run"]["workflow_outputs"]
    except (ValueError, KeyError, TypeError):
        return None


def _case(session: Path, parent: Path, name: str, lines: int, target: int, expected: dict, hidden: bool) -> dict:
    workspace = _workspace(session, parent, name)
    (workspace / "notes.txt").write_text("".join(f"line {n}\n" for n in range(lines)), encoding="utf-8")
    run = _orchestrator(workspace, "run", "tally.orc", *MANIFEST,
                        "--input", "file=notes.txt", "--input", f"target={target}")
    calls_log = workspace / "line_count.calls"
    calls = len(calls_log.read_text().splitlines()) if calls_log.exists() else 0
    outputs = _outputs(workspace) if run.returncode == 0 else None
    passed = run.returncode == 0 and outputs == expected and (calls > 0 or not hidden)
    return {"case": name, "passed": passed, "run_exit": run.returncode, "outputs": outputs,
            "expected": expected, "line_count_calls": calls, "stderr_tail": run.stderr[-2000:]}


def check(session: Path) -> dict:
    with tempfile.TemporaryDirectory(prefix="authoring-check-") as scratch:
        parent = Path(scratch)
        compiled = _orchestrator(_workspace(session, parent, "compile"), "compile", "tally.orc", *MANIFEST)
        result = {"session": str(session), "compile_exit": compiled.returncode,
                  "compile_stderr_tail": compiled.stderr[-2000:], "cases": []}
        if compiled.returncode == 0:
            result["cases"] = [_case(session, parent, *case) for case in CASES]
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
