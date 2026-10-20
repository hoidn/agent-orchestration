from tests.experiments.orc_structural_search_support import launch_config
"""Evaluation launch path: a seed runs through the public `run` route in a fresh clone behind the shims,
with scripted providers (no provider is called)."""

import json
import os
import shutil
from difflib import ndiff
from pathlib import Path
from string import Template

import pytest

from experiments.compare import prepare
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.evaluation import (
    EvaluationRecord, evaluate, evaluation_id, is_python, record_env_manifest, resume)
from tests.experiments.compare_harness_support import skip_without_sandbox
from orchestrator.providers.registry import ProviderRegistry
from tests.experiments.orc_structural_search_support import (  # noqa: F401 (pyright and world are fixtures)
    I3_CONFIG, PYTHON_PARENT, SCRIPTED, pyright, script, world)

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


def run(world, timeout_sec=NO_KILL_SEC, candidate=None, config=CONFIG):
    env = {**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}", "SCRIPTED_RESULTS_FILE": str(world.results)}
    record = evaluate(candidate or world.candidate, launch_config(world, config), task_package=world.task, work_root=world.evidence,
                      replicate=1, runtime=world.runtime, env=env, timeout_sec=timeout_sec, criterion=world.criterion)
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
    assert record.planned_perform_sites == [{"identity": site["identity"], "effect_class": site["effect_class"]}
                                          for site in record.realized_perform_sites]
    assert record.unexercised_perform_sites == []


def test_record_carries_the_env_manifest_digest_in_its_identity(sandboxed, world):
    script(world, [CHANGE])
    record, _ = run(world)
    digest = record.env_manifest_digest.removeprefix("sha256:")
    assert (world.evidence / "env-manifests" / f"{digest}.json").is_file()


def test_direct_seed_runs_in_the_clone_with_dev_check_beside_it(sandboxed, world):
    script(world, [CHANGE])
    record, _ = run(world)
    calls = record.records_dir / "calls"
    patch = (calls / "1" / "patch-cand-1.diff").read_text()
    inputs = json.loads((calls.parent / "inputs.json").read_text())
    assert (Path(inputs["repo"]) / "dev_check.py").is_file() and (Path(inputs["repo"]) / "dev-check.json").is_file()
    assert "dev_check.py" not in patch


def test_dev_check_comes_from_the_candidate_root(sandboxed, world):
    (world.candidate / "dev_check.py").write_text((world.candidate / "dev_check.py").read_text() + "# candidate copy\n")
    script(world, [CHANGE])
    record, _ = run(world)
    repo = Path(json.loads((record.records_dir / "inputs.json").read_text())["repo"])
    assert (repo / "dev_check.py").read_text() == (world.candidate / "dev_check.py").read_text()


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
    assert len(record.realized_perform_sites) == 1
    assert (record.realized_perform_sites[0]["status"], record.realized_perform_sites[0]["attempts"]) == ("running", 1)


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
    resumed = resume(first, env=env, timeout_sec=NO_KILL_SEC, criterion=world.criterion)
    assert (resumed.evaluation_id, resumed.run_id, resumed.outcome, resumed.resume_count, resumed.incidents) == (
        first.evaluation_id, first.run_id, "completed", 1, first.incidents)
    assert [(site["identity"], site["attempts"], site["status"]) for site in resumed.realized_perform_sites] == [
        (first.realized_perform_sites[0]["identity"], 2, "completed")]


def test_evaluation_id_changes_with_replicate_and_env_manifest():
    ids = {evaluation_id("sha256:c", "task-1", "v1", digest, replicate)
           for digest in ("sha256:e1", "sha256:e2") for replicate in (1, 2)}
    assert len(ids) == 4


def fake_cli(directory: Path, name: str, output: str) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(f"#!/bin/sh\necho '{output}'\n")
    (directory / name).chmod(0o755)
    return directory


def test_env_manifest_digest_changes_with_cli_versions(tmp_path):
    shim = fake_cli(tmp_path / "shim", "claude", "the shim")  # a directory holding model-guard is skipped
    (shim / "model-guard").write_text("")
    digests = [record_env_manifest(tmp_path / "work", {"PATH": f"{shim}:{fake_cli(tmp_path / v, 'claude', v)}:"
                                                               f"{os.environ['PATH']}"})
               for v in ("claude 1.0.0", "claude 1.0.1")]
    manifest = json.loads((tmp_path / "work" / "env-manifests" / f"{digests[1].removeprefix('sha256:')}.json").read_text())
    assert (digests[0] != digests[1], manifest["cli"]["claude"], sorted(manifest["cli"])) == (
        True, "claude 1.0.1", ["bwrap", "claude", "codex", "git"])


def test_only_a_python_entry_module_is_python():
    assert (is_python(I3_CONFIG), is_python(CONFIG)) == (True, False)


def three_arm_parent(world, arm):
    """A copy of the three-arm parent `arm` ("orc", the rebound direct seed, or "python", its I3 counterpart)."""
    root = world.tmp / arm
    shutil.copytree(PYTHON_PARENT.parent / arm, root, ignore=shutil.ignore_patterns("__pycache__"))
    return root


def run_python(world, timeout_sec=NO_KILL_SEC):
    return run(world, timeout_sec, candidate=three_arm_parent(world, "python"), config=I3_CONFIG)[0]


def scripted_codex(world, code):
    """Make the scripted codex run `code` first, once it has read its prompt."""
    anchor = "prompt = sys.stdin.read()\n"
    assert SCRIPTED.count(anchor) == 1
    (world.fakebin / "codex").write_text(SCRIPTED.replace(anchor, anchor + code))


PRINT_ARGV = "print(json.dumps(sys.argv[1:]))\n"  # the shim keeps it in calls/<n>/stdout.txt
# an orchestrator run the coder starts from the clone root: a completed memo in the default state directory
CODER_RUN = ('os.makedirs(".orchestrate/runs/coder-run")\n'
             'open(".orchestrate/runs/coder-run/memo.jsonl", "w").write(json.dumps('
             '{"record": "terminal", "outcome": "completed", "value": {"x": 1}}) + "\\n")\n')


def coder_prompt(record):
    """The run's first prompt as lines, its own clone (the `repo` input, one per evaluation) replaced by a token."""
    repo = json.loads((record.records_dir / "inputs.json").read_text())["repo"]
    return (record.records_dir / "calls" / "1" / "prompt.txt").read_text().replace(repo, "<repo>").splitlines(True)


def test_i3_parent_sends_the_orc_parents_prompt_except_the_result_path(sandboxed, world, pyright):
    script(world, [CHANGE])
    scripted_codex(world, PRINT_ARGV)
    orc, _ = run(world, candidate=three_arm_parent(world, "orc"))
    python = run_python(world)
    changed = [line[2:] for line in ndiff(coder_prompt(orc), coder_prompt(python)) if line[:2] in ("- ", "+ ")]
    argv = json.loads((python.records_dir / "calls" / "1" / "stdout.txt").read_text().splitlines()[0])
    template = ProviderRegistry().get("codex_unrestricted_workspace")
    expected = [Template(arg).substitute(model="gpt-6.1-sol", reasoning_effort="high") for arg in template.command[1:]]
    assert ([line.startswith("- path:") for line in changed], python.value, argv) == (
        [True, True], orc.value, expected)


def test_i3_evaluation_runs_the_generic_command_arm_and_records_a_completed_terminal(sandboxed, world, pyright):
    script(world, [CHANGE])
    record = run_python(world)
    arm = json.loads((record.records_dir / "record.json").read_text())
    collected = prepare.collect(record.records_dir)
    assert (record.outcome, record.value, record.provider_calls, arm["arm_kind"], record.state_dir,
            (record.records_dir / collected["patches"]["final"]).is_file()) == (
        "completed", {"variant": "DONE", "summary": "set VALUE"}, 1, "generic-command", Path(arm["state_root"]), True)


def test_i3_provider_failure_is_recorded_as_failed(sandboxed, world, pyright):
    script(world, [{"match": "Implement this change", "exit": 1}])
    record = run_python(world)
    assert (record.outcome, record.value) == ("failed", None)


def test_i3_launch_killed_before_its_terminal_is_an_incident(sandboxed, world, pyright):
    script(world, [HANG])
    record = run_python(world, timeout_sec=KILL_AFTER_SEC)
    assert (record.outcome, len(record.incidents)) == ("incident", 1)


def test_i3_launch_killed_beside_an_orchestrator_run_of_the_coder_is_an_incident(sandboxed, world, pyright):
    script(world, [HANG])
    scripted_codex(world, CODER_RUN)
    record = run_python(world, timeout_sec=KILL_AFTER_SEC)
    assert (record.outcome, record.run_id) == ("incident", "unavailable")


def test_a_generic_command_incident_is_not_resumable(tmp_path):
    record = EvaluationRecord("e", "unavailable", tmp_path, tmp_path, "sha256:e", "incident", None, 0.0, 0, 0, ())
    with pytest.raises(ValueError, match="no resume.sh"):
        resume(record, env={}, timeout_sec=1)


def test_effect_evidence_distinguishes_not_started_generic_and_pure_zero(sandboxed, world):
    from experiments.orc_structural_search import evaluation
    absent = evaluation.realized_effects(world.tmp / "absent", "unavailable", generic=False)
    generic = evaluation.realized_effects(world.tmp / "absent", "unavailable", generic=True)
    source = world.candidate / "direct.orc"
    text = source.read_text()
    begin = text.index("    (let* ((change")
    source.write_text(text[:begin] + '    (variant Outcome DONE :summary "pure"))\n)\n')
    record, _ = run(world)
    assert (absent["realized_perform_sites"], generic["branch_coverage_reason"],
            record.realized_perform_sites, record.exercised_branches, record.branch_coverage_reason) == (
        "unavailable", "generic_command_has_no_orc_memo", [], "unavailable", "memo_records_effects_only")


@pytest.mark.parametrize("fails,expected_calls,expected_classes", [
    (False, 1, ["provider", "command"]),
    (True, 3, ["provider", "command", "provider", "provider"]),
])
def test_public_run_realizes_repair_only_after_failed_development_check(sandboxed, world, fails, expected_calls,
                                                                        expected_classes):
    from dataclasses import replace
    from experiments.orc_structural_search import evaluation
    # The task-visible check is deterministic and fails at the base only in the repair case.
    (world.task / "seed/dev-check.json").write_text(json.dumps({
        "argv": [__import__("sys").executable, "-c", "raise SystemExit(1)" if fails else "import pkg"],
        "timeout_sec": 30}))
    script(world, [CHANGE, {"match": "diagnose why", "result": {"findings": ["base check fails"]}},
                   {"match": "Fix the root causes", "result": {"summary": "repaired", "account": "repair"}}])
    config = replace(CONFIG, entry_workflow="implement_check_diagnose_repair::run",
                     mutable_files=("implement_check_diagnose_repair.orc",))
    record, _ = run(world, config=config)
    assert (record.outcome, record.provider_calls,
            [site["effect_class"] for site in record.realized_perform_sites]) == (
        "completed", expected_calls, expected_classes)
    assert all(site["attempts"] == 1 and site["status"] == "completed" for site in record.realized_perform_sites)
    assert record.exercised_branches == "unavailable"
    memo = record.state_dir / record.run_id / "memo.jsonl"
    memo.write_text(memo.read_text() + '{"invalid":true}\n')
    with pytest.raises(ValueError):
        evaluation.realized_effects(record.state_dir, record.run_id, generic=False)
