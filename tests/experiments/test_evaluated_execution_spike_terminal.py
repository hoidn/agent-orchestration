"""Spike of evaluated execution, iteration 3, item A: a view says `completed` only after the run's terminal record.

Throwaway. Review 2, finding 2: the view said `completed` while a coordinator's final
commit was still owed, and while a live evaluator stood at its last commit. The
evaluator now ends a run with a `terminal` record, written after every effect is
committed and every coordinator's effect settled or reconciled; a coordinator's
effect also gets a `settled` record. The view says `completed` only when the memo's
last record is the terminal record; before it, `running`, `settling` or `interrupted`.

Each case runs the evaluator in a child process that blocks at a hook. The test reads
the view while the child is alive, kills the child's process group with SIGKILL, reads
the view again, resumes in a new child, and reads the view a third time.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
ENV = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}


def child(config_path: str) -> None:
    """Run or resume the program under the configuration's root; block at its event."""

    from experiments.evaluated_execution_spike.evaluator import evaluate
    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from tests.experiments.test_evaluated_execution_spike_coordinator import PROGRAM, RunRefCoordinator

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    root = Path(config["root"])
    os.chdir(root)
    seen: Counter[str] = Counter()

    def hook(event: str, identity: str) -> None:
        seen[event] += 1
        if event == config.get("event") and seen[event] == config.get("at"):
            (root / "marker").write_text(event, encoding="utf-8")
            while True:
                time.sleep(0.05)

    if config["program"] == "coordinator":
        program, coordinators = PROGRAM, {"run_ref": RunRefCoordinator(root / "coordinator")}
    else:
        program = ClosedProgram.from_artifact((root / "program.json").read_text(encoding="utf-8"))
        coordinators = {}
    result = evaluate(program, inputs={}, workspace=root, run_root=root / "run", hook=hook, coordinators=coordinators)
    print(json.dumps({"value": result.value}))


def _spawn(root: Path, **config) -> subprocess.Popen:
    path = root / f"config-{time.monotonic_ns()}.json"
    path.write_text(json.dumps({"root": str(root), **config}), encoding="utf-8")
    return subprocess.Popen([sys.executable, __file__, "child", str(path)], cwd=REPO, env=ENV, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def held(root: Path, **config) -> subprocess.Popen:
    """A child standing at its event, alive."""

    process = _spawn(root, **config)
    deadline = time.monotonic() + 60
    while not (root / "marker").exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert (root / "marker").exists(), process.communicate()[1][-2000:]
    return process


def kill(process: subprocess.Popen, root: Path) -> None:
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    (root / "marker").unlink()


def resumed(root: Path, program: str) -> dict:
    out, err = _spawn(root, program=program).communicate(timeout=120)
    assert out.strip(), err[-2000:]
    return json.loads(out.strip().splitlines()[-1])


def seen(state: dict) -> dict:
    """What the view says: the run's status, its outputs, each row's status."""

    return {"status": state["status"], "outputs": state.get("workflow_outputs"),
            "rows": [row["status"] for row in state["steps"].values()]}


def kinds(run_root: Path) -> list[str]:
    from experiments.evaluated_execution_spike.memo import read_records

    return [record["record"] for record in read_records(run_root)]


def settled_by(run_root: Path) -> str:
    from experiments.evaluated_execution_spike.memo import read_records

    (record,) = [record for record in read_records(run_root) if record["record"] == "settled"]
    return record["by"]


@pytest.mark.parametrize("event", ["committed", "settled"])
def test_a_coordinator_effect_killed_before_the_terminal_record_is_not_reported_completed(
    tmp_path: Path, event: str
) -> None:
    """`committed`: after the memo's commit, before the coordinator's final commit (review 2, finding 2).
    `settled`: after the final commit and its `settled` record, before the run's terminal record."""

    from experiments.evaluated_execution_spike.view import derive_state
    from tests.experiments.test_evaluated_execution_spike_coordinator import PROGRAM, SITE, RunRefCoordinator

    process = held(tmp_path, program="coordinator", event=event, at=1)
    live = derive_state(PROGRAM, tmp_path / "run")
    kill(process, tmp_path)
    killed = derive_state(PROGRAM, tmp_path / "run")
    coordinator = RunRefCoordinator(tmp_path / "coordinator")
    ledger_at_kill = coordinator.ledger(SITE)

    value = resumed(tmp_path, "coordinator")

    final = derive_state(PROGRAM, tmp_path / "run")
    row = "settling" if event == "committed" else "completed"
    assert seen(live) == {"status": "settling", "outputs": None, "rows": [row]}
    assert seen(killed) == {"status": "interrupted", "outputs": None, "rows": [row]}
    assert ledger_at_kill[-1] == ((1, "completed_pending_parent_commit") if event == "committed" else (1, "committed"))
    assert value == {"value": "artifacts/work/result.txt"}
    assert seen(final) == {"status": "completed", "outputs": {"return": "artifacts/work/result.txt"},
                           "rows": ["completed"]}
    assert coordinator.ledger(SITE) == [(1, "launched"), (1, "completed_pending_parent_commit"), (1, "committed")]
    assert kinds(tmp_path / "run") == ["started", "committed", "settled", "terminal"]
    assert settled_by(tmp_path / "run") == ("reconcile" if event == "committed" else "settle")


def test_a_live_evaluator_held_at_its_last_commit_is_settling_not_completed(tmp_path: Path) -> None:
    """Review 2's live probe: three commands committed, the evaluator alive at its last `committed` hook."""

    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from experiments.evaluated_execution_spike.view import derive_state
    from tests.experiments.test_evaluated_execution_spike import build, calls, fixture

    program = build(tmp_path, fixture("three_call_sites"))
    (tmp_path / "program.json").write_text(program.artifact(), encoding="utf-8")
    program = ClosedProgram.from_artifact(program.artifact())

    process = held(tmp_path, program="file", event="committed", at=3)
    live = derive_state(program, tmp_path / "run")
    alive = process.poll() is None
    kill(process, tmp_path)
    killed = derive_state(program, tmp_path / "run")

    value = resumed(tmp_path, "file")

    final = derive_state(program, tmp_path / "run")
    assert (alive, seen(live)) == (True, {"status": "settling", "outputs": None, "rows": ["completed"] * 3})
    assert seen(killed) == {"status": "interrupted", "outputs": None, "rows": ["completed"] * 3}
    assert value == {"value": {"n": 6}}
    assert seen(final) == {"status": "completed", "outputs": {"return__n": 6}, "rows": ["completed"] * 3}
    assert calls(tmp_path) == ["fetch 1", "fetch 2", "fetch 3"]
    assert kinds(tmp_path / "run")[-1] == "terminal"


if __name__ == "__main__" and sys.argv[1:2] == ["child"]:
    child(sys.argv[2])
