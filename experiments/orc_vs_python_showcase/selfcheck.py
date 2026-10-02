"""Narrow checks for the original Python recovery illustration.

    python -m experiments.orc_vs_python_showcase.selfcheck

Stands in for the agents with a script whose answers depend on the prompt's
inputs, crashes the controller after its second committed effect, resumes, and
checks that those committed calls are reused; then feeds a malformed answer
and no answer at all. This does not establish full runtime equivalence or
exactly-once external execution.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from experiments.orc_vs_python_showcase import improve_equivalent as program

REPO = Path(__file__).resolve().parents[2]

FAKE_AGENT = '''
import json, os, sys
prompt = sys.stdin.read()
inputs = json.loads(prompt.rsplit("\\n", 1)[1])
open("agent.log", "a").write(json.dumps(inputs) + "\\n")
mode = os.environ.get("FAKE_MODE", "ok")
if mode == "silent":
    sys.exit(0)
if prompt.startswith("Review"):
    if mode == "malformed":
        answer = {"kind": "APPROVE", "evidence": {"notes": 7}}
    elif inputs["hypothesis"].endswith("+r"):
        answer = {"kind": "APPROVE", "evidence": {"notes": "ok"}}
    else:
        answer = {"kind": "REVISE", "feedback": {"notes": "add a control"}}
else:
    answer = {"hypothesis": inputs["hypothesis"] + "+r",
              "parameters": inputs["parameters"] + [{"name": "control", "value": 1}]}
json.dump(answer, open(os.environ["OUTPUT_BUNDLE_PATH"], "w"))
'''

FAKE_LAUNCHER = '''
import json, os, sys
open("launch.log", "a").write(json.dumps(sys.argv[1:]) + "\\n")
json.dump({"status": "launched"}, open(os.environ["OUTPUT_BUNDLE_PATH"], "w"))
'''


class Crash(Exception):
    pass


def crash_after(commits: int):
    """Wrap `Run.effect` so the process 'dies' right after the n-th fresh commit."""
    original = program.Run.effect
    seen = {"fresh": 0}

    def effect(self, name, perform):
        fresh = self.next >= len(self.committed)
        value = original(self, name, perform)
        if fresh:
            seen["fresh"] += 1
            if seen["fresh"] == commits:
                raise Crash
        return value

    program.Run.effect = effect
    return lambda: setattr(program.Run, "effect", original)


def log(name: str) -> list:
    path = Path(name)
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def workspace() -> Path:
    root = Path(tempfile.mkdtemp(prefix="orc-showcase-"))
    prompts = root / program.PROMPTS
    prompts.mkdir(parents=True)
    for name in ("review.md", "revise.md"):
        shutil.copy(REPO / program.PROMPTS / name, prompts / name)
    (root / "fake_agent.py").write_text(FAKE_AGENT)
    (root / "fake_launcher.py").write_text(FAKE_LAUNCHER)
    return root


def main() -> None:
    root = workspace()
    os.chdir(root)
    program.AGENT = [sys.executable, "fake_agent.py"]
    program.LAUNCHER = [sys.executable, "fake_launcher.py"]

    # 1. Crash after the review and the revision are committed; resume.
    run_root = root / "run1"
    run_root.mkdir()
    restore = crash_after(2)
    try:
        program.run_experiment(program.Run(run_root), "q")
        raise AssertionError("the injected crash did not fire")
    except Crash:
        pass
    finally:
        restore()
    assert len(log("agent.log")) == 2, log("agent.log")
    assert log("launch.log") == []

    result = program.run_experiment(program.Run(run_root), "q")

    assert result == {"status": "launched"}
    calls = log("agent.log")
    assert len(calls) == 3, calls  # review, revise, review: nothing repeated
    assert [c["hypothesis"] for c in calls] == ["q", "q", "q+r"]
    launches = log("launch.log")
    assert len(launches) == 1 and launches[0][1] == "approved" and launches[0][5] == "q+r", launches

    # 2. A malformed answer is refused with a pointer, before anything else runs.
    os.environ["FAKE_MODE"] = "malformed"
    run2 = root / "run2"
    run2.mkdir()
    try:
        program.run_experiment(program.Run(run2), "q")
        raise AssertionError("a malformed answer was accepted")
    except program.Violation as violation:
        assert str(violation) == "/evidence/notes: expected str", violation
    assert not (run2 / "journal.jsonl").exists()

    # 3. No answer file is a refusal, not yesterday's answer.
    os.environ["FAKE_MODE"] = "silent"
    run3 = root / "run3"
    run3.mkdir()
    try:
        program.run_experiment(program.Run(run3), "q")
        raise AssertionError("a missing answer was accepted")
    except program.Violation as violation:
        assert "produced no answer file" in str(violation), violation

    shutil.rmtree(root)
    print("selfcheck: ok (committed calls reused; malformed and missing answers refused)")


if __name__ == "__main__":
    main()
