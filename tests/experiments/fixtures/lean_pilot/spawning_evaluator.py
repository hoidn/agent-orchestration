from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path


_DESCENDANT = """
import pathlib
import sys
import time

started = pathlib.Path(sys.argv[1])
late_mutation = pathlib.Path(sys.argv[2])
started.write_text("started\\n", encoding="utf-8")
time.sleep(0.75)
late_mutation.write_text("survived\\n", encoding="utf-8")
"""


def evaluate_workspace(workspace: Path) -> dict[str, object]:
    temporary = Path(os.environ["TMPDIR"])
    started = temporary / "descendant-started.txt"
    late_mutation = temporary / "descendant-late-mutation.txt"
    subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-B",
            "-c",
            _DESCENDANT,
            str(started),
            str(late_mutation),
        ],
        stdin=subprocess.DEVNULL,
    )
    deadline = time.monotonic() + 2
    while not started.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("descendant did not start")
        time.sleep(0.005)

    outcome = (Path(workspace) / "result.txt").read_text(encoding="utf-8")
    if outcome == "timeout\n":
        time.sleep(60)
    passed = outcome == "pass\n"
    return {
        "failure_categories": [] if passed else ["hidden_acceptance_failed"],
        "soft_quality": {"findings": [], "score": 1 if passed else 0},
        "summary": {
            "hidden_tests_passed": passed,
            "score": 1 if passed else 0,
        },
        "verdict": "PASS" if passed else "FAIL",
    }
