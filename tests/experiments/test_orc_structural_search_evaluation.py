"""Evaluation launch path: a seed runs through the public `run` route in a fresh clone behind the shims,
with scripted providers (no provider is called)."""

import json
import os
from pathlib import Path

import pytest

from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.evaluation import evaluate, evaluation_id, resume
from tests.experiments.compare_harness_support import skip_without_sandbox
from tests.experiments.orc_structural_search_support import script, world  # noqa: F401 (fixture)

CONFIG = ExperimentConfig(
    mutable_files=("direct.orc",), mutable_definitions=("run",), condition="topology-only", interface="I1",
    entry_workflow="direct::run", source_root=".", providers_file="providers.json",
    command_boundaries_file="commands.json", episode_wall_clock_sec=600, criterion_sha256=None)
CHANGE = {"match": "Implement this change", "result": {"summary": "set VALUE", "account": "edited pkg"}}
# a provider exiting nonzero makes the runtime write a failed terminal; an incident is a run killed before any
# terminal, here by evaluate's wall-clock limit while the provider sleeps
HANG = {"match": "Implement this change", "sleep": 600, "exit": 1}
KILL_AFTER_SEC = 20
NO_KILL_SEC = 600


@pytest.fixture
def sandboxed():
    skip_without_sandbox()


def run(world, timeout_sec=NO_KILL_SEC):
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    record = evaluate(world.candidate, CONFIG, task_package=world.task, evidence_root=world.evidence,
                      replicate=1, runtime=world.runtime, env=env, timeout_sec=timeout_sec)
    return record, env


def memo_rows(record):
    return [json.loads(line) for line in (record.state_dir / record.run_id / "memo.jsonl").read_text().splitlines()]


def test_direct_seed_runs_in_fresh_clone_and_records_run_id(sandboxed, world):
    script(world, [CHANGE])
    record, _ = run(world)
    assert (record.outcome, record.value, record.state_dir, record.records_dir, memo_rows(record)[-1]["record"],
            record.provider_calls) == (
        "completed", {"variant": "DONE", "summary": "set VALUE"},
        world.evidence.resolve() / "runs" / record.evaluation_id,
        world.evidence.resolve() / "records" / record.evaluation_id / "run-1", "terminal", 1)


def test_direct_seed_runs_in_the_clone_with_dev_check_beside_it(sandboxed, world):
    script(world, [CHANGE])
    record, _ = run(world)
    calls = record.records_dir / "calls"
    patch = (calls / "1" / "patch-cand-1.diff").read_text()
    inputs = json.loads((calls.parent / "inputs.json").read_text())
    assert (Path(inputs["repo"]) / "dev_check.py").is_file() and (Path(inputs["repo"]) / "dev-check.json").is_file()
    assert "dev_check.py" not in patch


def test_provider_failure_terminal_is_recorded_as_failed(sandboxed, world):
    script(world, [{"match": "Implement this change", "exit": 1}])
    record, _ = run(world)
    assert (record.outcome, record.value, memo_rows(record)[-1]["outcome"]) == ("failed", None, "failed")


def surviving(marker):
    """Pids of live processes whose command line mentions `marker`."""
    found = []
    for cmdline in Path("/proc").glob("[0-9]*/cmdline"):
        try:
            if str(marker).encode() in cmdline.read_bytes():
                found.append(cmdline.parent.name)
        except OSError:  # the process exited while we looked
            continue
    return found


def test_unfinished_memo_is_recorded_as_incident(sandboxed, world):
    script(world, [HANG])
    record, _ = run(world, timeout_sec=KILL_AFTER_SEC)
    assert (record.outcome, record.resume_count, len(record.incidents), record.run_id != "unavailable") == (
        "incident", 0, 1, True)


def test_killed_launch_leaves_no_process_of_the_run(sandboxed, world):
    script(world, [HANG])
    run(world, timeout_sec=KILL_AFTER_SEC)
    assert surviving(world.fakebin) == []


def test_launch_killed_before_its_run_started_still_blocks_a_rerun(sandboxed, world):
    script(world, [CHANGE])
    record, _ = run(world, timeout_sec=0)
    with pytest.raises(FileExistsError, match=str(record.records_dir.parent)):
        run(world)


def test_resume_keeps_evaluation_id_and_completes(sandboxed, world):
    script(world, [HANG])
    first, env = run(world, timeout_sec=KILL_AFTER_SEC)
    script(world, [CHANGE])
    resumed = resume(first, env=env, timeout_sec=NO_KILL_SEC)
    assert (resumed.evaluation_id, resumed.run_id, resumed.outcome, resumed.resume_count, resumed.incidents) == (
        first.evaluation_id, first.run_id, "completed", 1, first.incidents)


def test_evaluation_id_changes_with_replicate_and_env_manifest():
    ids = {evaluation_id("sha256:c", "task-1", "v1", digest, replicate)
           for digest in ("sha256:e1", "sha256:e2") for replicate in (1, 2)}
    assert len(ids) == 4
