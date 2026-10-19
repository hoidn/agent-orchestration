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
from tests.experiments.test_orc_structural_search_driver import config_of


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
    assert verdict["diagnostics_schema_version"] == "workflow_lisp_compile_diagnostics.v1"
    assert verdict["diagnostics"][0]["span"]
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
