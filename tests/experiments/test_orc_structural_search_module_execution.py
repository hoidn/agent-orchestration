"""Offline module episodes, metering and criterion separation; no real providers."""

import json
import os
import subprocess
import sys
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from experiments.orc_structural_search import three_arm
from experiments.orc_structural_search.briefs import episode_brief
from experiments.orc_structural_search.driver import archive, episode_workspace
from experiments.orc_structural_search.config import load_config
from tests.experiments.orc_structural_search_support import world  # noqa: F401
from tests.experiments.test_orc_structural_search_driver import config_of, sandboxed  # noqa: F401


def module_config():
    return config_of(condition="module", models={"claude-sonnet-5-5": ["medium"], "claude-opus-5-5": ["high"]},
                     per_call_timeout_sec=5400)


def check_workspace(world):
    config = module_config()
    _, parent = archive(world.candidate, world.tmp / "evidence", world.runtime)
    tree = world.outside / "episode"
    copy, base = episode_workspace(parent, tree, episode_brief(config, 0), world.runtime, config=config)
    command = [sys.executable, "-P", "-m", "experiments.orc_structural_search.check", "--metadata", "../admission.json"]
    env = {**os.environ, "PYTHONPATH": str(tree / "py"), "PYTHONDONTWRITEBYTECODE": "1"}
    def check():
        done = subprocess.run(command, cwd=copy, env=env, capture_output=True, text=True)
        return done, json.loads(done.stdout)
    return copy, tree, check


def test_workspace_check_refuses_extra_file_then_compiler_error_then_accepts_repair_without_mutation(world):
    copy, tree, check = check_workspace(world)
    extra = copy / "notes.txt"
    extra.write_text("outside scope")
    done, verdict = check()
    assert done.returncode == 1 and verdict["refusal_code"] == "scope_exceeded"
    extra.unlink()
    source = (copy / "direct.orc").read_text()
    (copy / "direct.orc").write_text(source.replace("change.summary", "42"))
    done, verdict = check()
    assert done.returncode == 1 and verdict["diagnostics"]
    assert verdict["compile_diagnostics"] == {
        "schema_version": "workflow_lisp_compile_diagnostics.v1", "status": "rejected",
        "diagnostics": verdict["diagnostics"]}
    assert {"path", "line", "column", "form_path", "notes", "phase", "validation_pass"} <= verdict["diagnostics"][0].keys()
    (copy / "direct.orc").write_text(source)
    before = sorted(p.relative_to(copy) for p in copy.rglob("*") if p.is_file())
    done, verdict = check()
    assert (done.returncode, verdict["outcome"]) == (0, "accepted")
    assert sorted(p.relative_to(copy) for p in copy.rglob("*") if p.is_file()) == before
    for package in ("compare", "orc_structural_search"):
        assert (tree / "py" / "experiments" / package / "__init__.py").is_file()
    assert not list((tree / "py" / "experiments").rglob("*.orc"))
    assert not (tree / "py" / "experiments" / "compare" / "tasks").exists()


def test_module_arm_uses_i1_interface_and_its_own_condition(tmp_path):
    config = module_config()
    path = tmp_path / "config.json"
    path.write_text(json.dumps(asdict(config)))
    got = three_arm.arm_config(path, "I1/module")
    assert (got.interface, got.condition, got.models, got.per_call_timeout_sec) == (
        "I1", "module", config.models, 5400)


@pytest.mark.parametrize("args,forced,allowed,status", [
    (["--model", "claude-opus-5-5"], "claude-opus-5-5", "claude-opus-5-5", 0),
    (["--model=claude-sonnet-5-5"], "claude-opus-5-5", "claude-opus-5-5", 2),
    ([], "claude-opus-5-5", "claude-sonnet-5-5", 2),
    (["--model", "claude-opus-5-5", "--fallback-model=claude-opus-5-5,other"], "claude-opus-5-5", "claude-opus-5-5", 2),
    (["--model", "claude-opus-5-5"], "other", "claude-opus-5-5", 2),
    (["--model", "fable"], "claude-opus-5-5", "fable,claude-opus-5-5", 2),
])
def test_claude_guard_checks_explicit_default_fallback_and_forced_subagent(tmp_path, args, forced, allowed, status):
    from tests.experiments.orc_structural_search_support import REPO
    guard = tmp_path / "guard"
    real = tmp_path / "real"
    guard.mkdir()
    real.mkdir()
    import shutil
    shutil.copyfile(REPO / "experiments/compare/shim/model-guard", guard / "claude")
    (guard / "claude").chmod(0o755)
    (real / "claude").write_text("#!/bin/sh\nexit 0\n")
    (real / "claude").chmod(0o755)
    done = subprocess.run([str(guard / "claude"), *args], capture_output=True, text=True,
                          env={**os.environ, "PATH": f"{guard}:{real}:{os.environ['PATH']}",
                               "ORC_ALLOWED_CLAUDE_MODELS": allowed, "CLAUDE_CODE_SUBAGENT_MODEL": forced})
    assert done.returncode == status, done.stderr


def test_successor_arms_and_subset_refuse_foreign_or_missing_row_hashes():
    from tests.experiments.orc_structural_search_support import REPO
    from tests.experiments.test_orc_structural_search_three_arm import episode_row
    criterion = three_arm.load_criterion(REPO / "experiments/orc_structural_search/criteria/module.json")
    assert tuple(three_arm.arm_specs(criterion)) == ("I1", "I2", "I3", "I1/module")
    rows = [episode_row(arm, n, f"child-{n}", f"skeleton-{n}") |
            {"criterion_sha256": criterion["criterion_sha256"]}
            for n, arm in enumerate(three_arm.arm_specs(criterion))]
    assert {arm: len(items) for arm, items in three_arm.subset(rows, criterion, 1).items()} == {
        "I1": 1, "I2": 1, "I3": 1, "I1/module": 1}
    for invalid in (None, "old-study"):
        rows[-1]["criterion_sha256"] = invalid
        with pytest.raises(ValueError, match="criterion_sha256"):
            three_arm.subset(rows, criterion, 1)


def test_check_run_compares_actual_policy_with_criterion(tmp_path):
    from tests.experiments.orc_structural_search_support import REPO
    import shlex
    criterion = REPO / "experiments/orc_structural_search/criteria/module.json"
    frozen = three_arm.load_criterion(criterion)
    config = replace(module_config(), models=frozen["models"], per_call_timeout_sec=frozen["per_call_timeout_sec"],
                     criterion_sha256=frozen["criterion_sha256"],
                     episode_wall_clock_sec=frozen["envelope"]["episode_wall_clock_sec"])
    path = tmp_path / "config.json"
    for delta in ({"models": {"outside": ["high"]}}, {"per_call_timeout_sec": 99}):
        path.write_text(json.dumps(asdict(replace(config, **delta))))
        with pytest.raises(ValueError, match=next(iter(delta))):
            three_arm.check_run(path, criterion, shlex.split(frozen["envelope"]["mutator"]),
                                frozen["envelope"]["evaluation_wall_clock_sec"])


MUTATOR_REPAIR = '''import json, os, subprocess, sys
from pathlib import Path
command = [sys.executable, "-P", "-m", "experiments.orc_structural_search.check", "--metadata", "../admission.json"]
env = {**os.environ, "PYTHONPATH": "../py"}
def check():
    done = subprocess.run(command, env=env, capture_output=True, text=True)
    verdict = json.loads(done.stdout)
    print(json.dumps(verdict), flush=True)
    return verdict
Path("extra.txt").write_text("scope failure")
assert check()["refusal_code"] == "scope_exceeded"
Path("extra.txt").unlink()
original = Path("direct.orc").read_text()
Path("direct.orc").write_text(original.replace("change.summary", "42"))
assert check()["outcome"] == "rejected"
Path("direct.orc").write_text(original.replace("Implement this change there", "Implement the requested change there"))
assert check()["outcome"] == "accepted"
'''


@pytest.mark.parametrize("ending,expected", [("", "accepted"),
    ('Path("extra.txt").write_text("invalid final state")\n', "rejected"),
    ("import time\ntime.sleep(600)\n", "exhausted")])
def test_episode_rechecks_final_state_after_development_repair(world, ending, expected):
    from tests.experiments.test_orc_structural_search_driver import episode
    from experiments.orc_structural_search.records import read_records
    from experiments.orc_structural_search.candidates import candidate_id
    from experiments.compare.repos import runtime_commit
    config = replace(module_config(), criterion_sha256="criterion", episode_wall_clock_sec=20 if ending.startswith("import time") else 120)
    row, evidence = episode(world, MUTATOR_REPAIR + ending, config)
    assert (row["outcome"], row["criterion_sha256"]) == (expected, "criterion")
    assert [r["kind"] for r in read_records(evidence / "log.jsonl")] == ["episode"]
    if expected == "accepted":
        assert candidate_id(Path(row["candidate_root"]), orchestrator_commit=runtime_commit(world.runtime)) == row["candidate_id"]
    if expected == "rejected":
        assert row["refusal_code"] == "scope_exceeded"
    if expected == "exhausted":
        assert not row.get("candidate_root") and not row.get("program_digest")


def test_evaluation_hash_cannot_be_spoofed_and_snapshot_still_has_candidate_id(sandboxed, world):
    from tests.experiments.orc_structural_search_support import script
    from experiments.orc_structural_search.driver import evaluate_and_scan
    from experiments.orc_structural_search.candidates import candidate_id
    from experiments.compare.repos import runtime_commit
    script(world, [{"match": "Implement this change", "result": {"summary": "done", "account": "done"}}])
    config = replace(module_config(), criterion_sha256="actual-study")
    evidence = world.tmp / "evidence"
    cid, root = archive(world.candidate, evidence, world.runtime)
    row = evaluate_and_scan(root, config, task=world.task, replicate=1, work_root=world.outside / "work",
                            evidence_root=evidence, runtime=world.runtime,
                            env={**os.environ, "PATH": f"{world.fakebin}:{os.environ['PATH']}",
                                 "SCRIPTED_RESULTS_FILE": str(world.results)}, timeout_sec=600,
                            solutions={world.task.name: world.solution}, holdouts=(),
                            fields={"criterion_sha256": "spoofed"}, call_cap=160)
    assert (row["outcome"], row["criterion_sha256"], candidate_id(root, orchestrator_commit=runtime_commit(world.runtime))) == (
        "completed", "actual-study", cid)
    assert "native_session_paths" not in row


def test_successor_readout_keeps_module_and_legacy_arms_separate_and_checks_hashes(tmp_path):
    from experiments.orc_structural_search import three_arm_readout
    from experiments.orc_structural_search.records import append_record
    from tests.experiments.orc_structural_search_support import REPO
    source = REPO / "experiments/orc_structural_search/criteria/module.json"
    criterion = tmp_path / "criterion.json"
    criterion.write_text(json.dumps(json.loads(source.read_text()) | {"tasks": ["tasks/t1"]}))
    frozen = three_arm.load_criterion(criterion)
    digest = frozen["criterion_sha256"]
    log, driver = tmp_path / "log.jsonl", tmp_path / "driver.json"
    for n, arm in enumerate(three_arm.arm_specs(frozen)):
        append_record(log, {"kind": "evaluation", "mode": "three_arm", "arm": arm, "evaluation_id": f"e{n}",
                            "candidate_id": f"c{n}", "task_id": "t1", "replicate": 1, "outcome": "failed",
                            "criterion_sha256": digest, "split": "unavailable", "provider_calls": n,
                            "wall_clock_sec": 3, "incidents": [],
                            "realized_perform_sites": [{"identity": "named.then", "effect_class": "command",
                                                        "attempts": 2, "status": "failed"}],
                            "exercised_branches": "unavailable", "branch_coverage_reason": "memo_records_effects_only"})
    driver.write_text(json.dumps({"criterion_sha256": digest, "arms": {
        arm: {"subset": [f"c{n}"]} for n, arm in enumerate(three_arm.arm_specs(frozen))}}))
    result = three_arm_readout.readout(log, driver, criterion, [])
    figures = result["tasks"]["t1"]["arms"]
    assert {arm: list(value["children"]) for arm, value in figures.items()} == {
        "I1": ["c0"], "I2": ["c1"], "I3": ["c2"], "I1/module": ["c3"]}
    assert figures["I1/module"]["evaluations"] == [{
        "evaluation_id": "e3", "candidate_id": "c3", "provider_calls": 3,
        "realized_perform_sites": [{"identity": "named.then", "effect_class": "command", "attempts": 2,
                                    "status": "failed"}],
        "exercised_branches": "unavailable", "branch_coverage_reason": "memo_records_effects_only"}]
    rows = log.read_text()
    log.write_text(rows.replace(digest, "foreign", 1))
    with pytest.raises(ValueError, match="criterion_sha256"):
        three_arm_readout.readout(log, driver, criterion, [])


def test_original_criterion_accepts_historical_rows_without_hash():
    from tests.experiments.orc_structural_search_support import REPO
    original = three_arm.load_criterion(REPO / "experiments/orc_structural_search/criteria/three_arm.json")
    assert original["criterion_sha256"] == three_arm.HISTORICAL_CRITERION_SHA256
    three_arm.check_row_criteria([{"kind": "episode", "mode": "three_arm", "arm": "I1"}], original)


@pytest.mark.parametrize("args,allowed,expected", [
    (["--model", "outside"], {"claude-opus-5-5": ["high"]}, "incident"),
    ([], {"claude-sonnet-5-5": ["medium"]}, "incident"),
    (["--model", "claude-opus-5-5"], {"claude-opus-5-5": ["high"], "claude-sonnet-5-5": ["medium"]}, "accepted"),
])
def test_initial_claude_launch_enforces_allowlist_after_compare_environment_is_stripped(sandboxed, world, args,
                                                                                       allowed, expected):
    from experiments.orc_structural_search.driver import run_episode
    from tests.experiments.test_orc_structural_search_driver import fake_claude
    source = f'''#!{sys.executable} -I
import os
assert "COMPARE_CLAUDE_MODELS" not in os.environ
assert os.environ["ORC_ALLOWED_CLAUDE_MODELS"]
print("real CLI launched")
'''
    env = fake_claude(world, source)
    evidence = world.tmp / "evidence"
    _, parent = archive(world.candidate, evidence, world.runtime)
    row = run_episode(parent, replace(module_config(), models=allowed), interface="I1", mode="unguided",
                      agent_cmd=["claude", "-p", *args], work_root=world.outside / "work", evidence_root=evidence,
                      episode_index=0, runtime=world.runtime, env=env, solutions={world.task.name: world.solution},
                      call_cap=160)
    assert row["outcome"] == expected
    output = (evidence / "episodes" / row["episode_id"] / "calls/1/stdout.txt").read_text()
    assert ("real CLI launched" in output) == (expected == "accepted")


@pytest.mark.parametrize("complete", [True, False])
def test_episode_records_identified_native_path_even_without_complete_usage(sandboxed, world, monkeypatch, complete):
    from experiments.orc_structural_search.driver import run_episode
    from tests.experiments.test_orc_structural_search_driver import fake_claude
    from tests.experiments.test_orc_structural_search_metering import FULL
    home = world.outside / "home"
    monkeypatch.setenv("HOME", str(home))
    source = f'''#!{sys.executable} -I
import json, os, re, sys
from pathlib import Path
prompt = sys.stdin.read()
root = Path(os.environ["HOME"]) / ".claude/projects" / re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
root.mkdir(parents=True)
rows = [{{"type": "user", "message": {{"content": prompt}}}},
        {{"type": "assistant", "message": {{"id": "m", "model": "claude-opus-5-5", "usage": {FULL if complete else {}!r}}}}}]
(root / "session.jsonl").write_text("".join(json.dumps(row) + "\\n" for row in rows))
'''
    env = fake_claude(world, source)
    evidence = world.tmp / "evidence"
    _, parent = archive(world.candidate, evidence, world.runtime)
    row = run_episode(parent, replace(module_config(), criterion_sha256="actual"), interface="I1", mode="unguided",
                      agent_cmd=["claude", "-p"], work_root=world.outside / "work", evidence_root=evidence,
                      episode_index=0, runtime=world.runtime, env=env, solutions={world.task.name: world.solution},
                      call_cap=160, fields={"criterion_sha256": "spoof"})
    assert (row["outcome"], row["criterion_sha256"], len(row["native_session_paths"])) == ("accepted", "actual", 1)
    assert Path(row["native_session_paths"][0]).is_file()
    if complete:
        assert row["consumption"]["claude"]["tokens"] == 20
    else:
        assert row["consumption"] == "unavailable"


@pytest.mark.parametrize("digest", [None, "foreign"])
def test_successor_pool_refuses_missing_or_foreign_source_hash_before_collect(tmp_path, monkeypatch, digest):
    from experiments.orc_structural_search import scoring
    from experiments.orc_structural_search.records import append_record
    from tests.experiments.orc_structural_search_support import REPO
    criterion = REPO / "experiments/orc_structural_search/criteria/module.json"
    evidence, task = tmp_path / "evidence", tmp_path / "task"
    evidence.mkdir()
    append_record(evidence / "log.jsonl", {"kind": "evaluation", "task_id": task.name, "outcome": "completed",
        "records_dir": str(tmp_path / "foreign-record"), "mode": "three_arm", "candidate_id": "foreign-child",
        "criterion_sha256": digest})
    def unexpected(*args, **kwargs):
        pytest.fail("invalid criterion reached collect")
    monkeypatch.setattr(scoring.prepare, "collect", unexpected)
    with pytest.raises(ValueError, match="criterion_sha256"):
        scoring.pool_evaluations(evidence, task, out=tmp_path / "pool", criterion=criterion,
                                judges=json.loads(criterion.read_text())["judges"])


@pytest.mark.parametrize("pool_hash,row_hash", [(None, "correct"), ("foreign", "correct"),
                                                ("correct", None), ("correct", "foreign")])
def test_successor_judge_refuses_invalid_pool_or_source_hash_before_dispatch(tmp_path, monkeypatch, pool_hash, row_hash):
    from experiments.orc_structural_search.records import append_record
    from tests.experiments.orc_structural_search_support import REPO
    criterion = REPO / "experiments/orc_structural_search/criteria/module.json"
    digest = three_arm.load_criterion(criterion)["criterion_sha256"]
    evidence, pool = tmp_path / "evidence", tmp_path / "pool"
    evidence.mkdir()
    (pool / "records").mkdir(parents=True)
    (pool / "records/mapping.json").write_text(json.dumps({"criterion_sha256": digest if pool_hash == "correct" else pool_hash}))
    append_record(evidence / "log.jsonl", {"kind": "evaluation", "task_id": "task", "mode": "three_arm", "arm": "I1/module",
                                          "criterion_sha256": digest if row_hash == "correct" else row_hash})
    def unexpected(*args, **kwargs):
        pytest.fail("invalid criterion reached provider dispatch")
    monkeypatch.setattr(three_arm.judging, "score_pool", unexpected)
    with pytest.raises(ValueError, match="criterion_sha256"):
        three_arm.judge(evidence, pool, tmp_path / "task", criterion=criterion,
                        judges=json.loads(criterion.read_text())["judges"], solution="solution", call_cap=100)
