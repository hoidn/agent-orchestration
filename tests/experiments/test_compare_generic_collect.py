"""Comparison harness: `collect` on a generic-command run reads the command's terminal.json and the last call's patch.

Behaviour on temporary git repositories with a stand-in agent CLI; see compare_harness_support.
"""

import json
from pathlib import Path

import pytest

from experiments.compare import prepare
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    call, edit, skip_without_sandbox, world,
)

skip_without_sandbox()


def command_run(world):
    """A generic-command run (its command is not run: the test makes its calls through the shim)."""
    root = world.outside / "candidate"
    spec = prepare.ArmSpec(source=root / "direct.py", entry="direct", source_root=root,
                           providers=root / "providers.json", inputs=("task", "intent", "repo"), command=("true",))
    records = prepare.run_arm(world.task, "python", world.root, world.runtime, spec=spec)
    return records, json.loads((records / "record.json").read_text())


def write_terminal(record, **terminal):
    run = Path(record["state_root"]) / "r1"
    run.mkdir(parents=True)
    (run / "terminal.json").write_text(json.dumps(terminal))


def test_collect_reads_a_generic_command_runs_terminal_and_last_patch(world):
    records, record = command_run(world)
    for body in ("a + b", "b + a"):
        assert call(world, record, edit("$PWD", body)).returncode == 0
    write_terminal(record, outcome="completed", value={"variant": "DONE", "summary": "s"}, failure=None,
                   started_at=100.0, finished_at=160.5, calls=2)
    collected = prepare.collect(records)
    assert (collected["outcome"], collected["calls"], collected["wall_clock_sec"],
            (records / collected["patches"]["final"]).read_bytes()) == (
        "completed", 2, 60.5, (records / "calls/2/patch-cand-1.diff").read_bytes())


def test_collect_refuses_a_generic_command_run_without_a_terminal(world):
    records, record = command_run(world)
    (Path(record["state_root"]) / "r1").mkdir(parents=True)
    with pytest.raises(SystemExit, match="finish the run first"):
        prepare.collect(records)


def test_collect_records_a_failed_generic_command_runs_failure_without_patches(world):
    records, record = command_run(world)
    assert call(world, record, "true").returncode == 0
    failure = {"code": "provider_exit_nonzero", "message": "codex exited 1"}
    write_terminal(record, outcome="failed", value=None, failure=failure, started_at=1.0, finished_at=3.0, calls=1)
    collected = prepare.collect(records)
    assert (collected["outcome"], collected["failure"], collected["patches"], collected["calls"]) == (
        "failed", failure, {}, 1)


@pytest.mark.parametrize("calls, keep_patch, message", [
    (2, True, "counts 2 provider calls but the shims recorded 1"),
    (1, False, "is missing: the run is invalid"),
])
def test_collect_refuses_a_generic_command_run_the_shims_did_not_record(world, calls, keep_patch, message):
    records, record = command_run(world)
    assert call(world, record, edit("$PWD", "a + b")).returncode == 0
    if not keep_patch:
        (records / "calls" / "1" / "patch-cand-1.diff").unlink()
    write_terminal(record, outcome="completed", value={"variant": "DONE", "summary": "s"}, failure=None,
                   started_at=1.0, finished_at=2.0, calls=calls)
    with pytest.raises(SystemExit, match=message):
        prepare.collect(records)
