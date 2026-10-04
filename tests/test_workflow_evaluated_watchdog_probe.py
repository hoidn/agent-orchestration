"""Copied watchdog probes read evaluated authority in another workspace."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import signal
import venv
from contextlib import contextmanager

import pytest

from tests.test_workflow_evaluated_readers import _pure_run, _scalar_run
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_resume_kills import _write_command_case
from tests.test_workflow_evaluated_view_publication import _live_writer, _wait_marker
from tests.test_workflow_evaluated_dashboard import _corrupt_authority
from tests.test_workflow_evaluated_providers import _fixture, _cli as _provider_cli
from tests.test_workflow_evaluated_view_publication import _provider_env
from tests.test_workflow_evaluated_invalidate import _cli
from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.test_workflow_evaluated_cli import _run_cli


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = Path("workflows/library/scripts/probe_orchestrator_run.py")


def _probe(workspace, run_root, *, interpreter=sys.executable, package_env=True):
    script = workspace / SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / SCRIPT, script)
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    if package_env:
        guard = _reader_spies(workspace)
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + str(guard)
        env["ORCHESTRATOR_TEST_GUARD_RECEIPT"] = str(guard / "loaded.jsonl")
    origin = subprocess.run([interpreter, "-c", "import orchestrator; print(orchestrator.__file__)"],
        cwd=workspace, env=env, text=True, capture_output=True, timeout=10)
    assert origin.returncode == 0, origin.stderr
    assert Path(origin.stdout.strip()).resolve() == ROOT / "orchestrator/__init__.py"
    result = subprocess.run([interpreter, str(script), "--run-id", run_root.name,
        "--target-workspace", str(run_root.parents[2]), "--output", "state/watchdog/watch.json",
        "--evidence-root", "artifacts/work/watchdog", "--repair-result-target-path",
        "artifacts/work/watchdog/repair-result.json"], cwd=workspace, env=env,
        text=True, capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr
    if package_env:
        assert _guard_loaded(guard, str(script)), "probe startup guard was not installed"
    watch = json.loads((workspace / "state/watchdog/watch.json").read_text())
    evidence = json.loads((workspace / watch["evidence_bundle_path"]).read_text())
    return watch, evidence


def _reader_spies(workspace):
    directory = workspace / "reader-guard"
    directory.mkdir(exist_ok=True)
    (directory / "loaded.jsonl").unlink(missing_ok=True)
    (directory / "sitecustomize.py").write_text('''from pathlib import Path
import json, os, sys
from pytest import MonkeyPatch
from tests.test_workflow_evaluated_views import _forbid_mutable_paths
patches = MonkeyPatch()
_forbid_mutable_paths(patches)
read = Path.read_text
def guarded(path, *args, **kwargs):
    if path.suffix == ".orc" or path.name in {"inputs.json", "prompt.md", "prompt.txt"} or "provider_sessions" in path.parts:
        raise AssertionError("reader opened recipe/source/prompt/session")
    return read(path, *args, **kwargs)
patches.setattr(Path, "read_text", guarded)
with Path(os.environ["ORCHESTRATOR_TEST_GUARD_RECEIPT"]).open("a") as receipt:
    receipt.write(json.dumps({"pid": os.getpid(), "argv": sys.argv}) + "\\n")
''')
    return directory


def _guard_loaded(directory, script):
    receipt = directory / "loaded.jsonl"
    if not receipt.exists():
        return False
    return any(json.loads(line)["argv"][0] == script for line in receipt.read_text().splitlines())


def test_copied_probe_reads_completed_evaluated_target_without_state(tmp_path):
    target = tmp_path / "T"
    target.mkdir()
    run_root = _pure_run(target)
    (run_root / "state.json").unlink()
    workspace = tmp_path / "W"
    workspace.mkdir()
    before = _tree_bytes(target)
    watch, evidence = _probe(workspace, run_root)
    assert (watch["watch_status"], watch["recommended_recovery"]) == ("COMPLETED", "NONE")
    assert evidence["run_status"] == "completed" and evidence["state_load_error"] == ""
    assert _tree_bytes(target) == before


@contextmanager
def _editable_interpreter(tmp_path):
    environment = tmp_path / "environment"
    venv.EnvBuilder(system_site_packages=True, with_pip=False).create(environment)
    interpreter = str(environment / "bin/python")
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
    env.pop("PYTHONPATH", None)
    generated = [ROOT / "orchestrator.egg-info", ROOT / "build"]
    backup = tmp_path / "packaging-before"
    for path in generated:
        assert not path.is_symlink()
        if path.exists():
            shutil.copytree(path, backup / path.name, symlinks=True)
    try:
        install = subprocess.run([interpreter, "-m", "pip", "install", "--no-index", "--no-deps", "--no-build-isolation", "-e", str(ROOT)],
            cwd=tmp_path, env=env, text=True, capture_output=True, timeout=60)
        (tmp_path / "editable-install.stdout.txt").write_text(install.stdout)
        (tmp_path / "editable-install.stderr.txt").write_text(install.stderr)
        assert install.returncode == 0, install.stderr
        yield interpreter
    finally:
        for path in generated:
            if path.exists():
                shutil.rmtree(path)
            if (backup / path.name).exists():
                shutil.copytree(backup / path.name, path, symlinks=True)


def test_copied_probe_uses_documented_editable_install_without_pythonpath(tmp_path):
    with _packaging_marker() as marker, _editable_interpreter(tmp_path) as interpreter:
        target = tmp_path / "T"
        target.mkdir()
        run_root = _pure_run(target)
        (run_root / "state.json").unlink()
        workspace = tmp_path / "W"
        workspace.mkdir()
        before = _tree_bytes(target)
        watch, _evidence = _probe(workspace, run_root, interpreter=interpreter, package_env=False)
        assert watch["watch_status"] == "COMPLETED"
        assert _tree_bytes(target) == before
    # The editable fixture restores pre-existing packaging bytes and modes before marker cleanup.


@contextmanager
def _packaging_marker():
    directory = ROOT / "build"
    existed = directory.exists()
    directory.mkdir(exist_ok=True)
    marker = directory / "task11b-owned-marker"
    assert not marker.exists()
    marker.write_bytes(b"pre-existing packaging fixture")
    marker.chmod(0o600)
    try:
        yield marker
        assert marker.read_bytes() == b"pre-existing packaging fixture"
        assert marker.stat().st_mode & 0o777 == 0o600
    finally:
        marker.unlink(missing_ok=True)
        if not existed:
            directory.rmdir()


@pytest.mark.parametrize("stage,expected", [("started", "running"), ("last", "settling"), ("killed", "interrupted")])
def test_probe_uses_real_writer_lock_without_staleness(tmp_path, stage, expected):
    target = tmp_path / "T"
    args, _hashes = _write_command_case(target)
    workspace = tmp_path / "W"
    workspace.mkdir()
    with _live_writer(target, args) as (process, control):
        _wait_marker(process, control / "started")
        if stage == "last":
            for marker in ("started", "partial", "first"):
                (control / (marker + ".release")).touch()
                _wait_marker(process, control / {"started": "partial", "partial": "first", "first": "last"}[marker])
        if stage == "killed":
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
        run_root, = (target / ".orchestrate/runs").iterdir()
        before = _tree_bytes(target)
        watch, evidence = _probe(workspace, run_root)
        assert evidence["run_status"] == expected
        assert (watch["watch_status"], watch["recommended_recovery"]) == (
            ("CRASHED", "RESUME") if stage == "killed" else ("RUNNING_OK", "NONE"))
        assert _tree_bytes(target) == before


@pytest.mark.parametrize("corruption", ["unknown-schema", "unknown-profile", "missing-header", "bad-journal",
    "bad-terminal", "adjacent-terminal", "missing-all-authority", "bad-artifact"])
def test_probe_corrupt_authority_never_accepts_completed_snapshot(tmp_path, corruption):
    target = tmp_path / "T"
    target.mkdir()
    run_root = _pure_run(target)
    if corruption == "missing-all-authority":
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            (run_root / name).unlink()
    elif corruption == "bad-artifact":
        (run_root / "closed_program.json").write_text("{}")
    else:
        _corrupt_authority(run_root, corruption)
    workspace = tmp_path / "W"
    workspace.mkdir()
    before = _tree_bytes(target)
    watch, evidence = _probe(workspace, run_root)
    assert (watch["watch_status"], watch["recommended_recovery"]) == ("UNKNOWN", "INVESTIGATE")
    assert "memo_inconsistent" in evidence["state_load_error"] and evidence["run_status"] == "missing"
    assert _tree_bytes(target) == before


def test_probe_failed_retry_reports_only_latest_error(tmp_path, monkeypatch):
    target = tmp_path / "T"
    target.mkdir()
    fixture = _fixture(target)
    assert _provider_cli(target, fixture, mode="nonzero").returncode == 1
    run_root, = (target / ".orchestrate/runs").iterdir()
    first, = load_evaluated_view(run_root)["steps"].values()
    old = _tree_bytes(run_root / Path(first["result_path"]).parent)
    _provider_env(monkeypatch, target, "invalid")
    assert _cli(target, "resume", run_root.name).returncode == 1
    second, = load_evaluated_view(run_root)["steps"].values()
    workspace = tmp_path / "W"
    workspace.mkdir()
    before = _tree_bytes(target)
    watch, evidence = _probe(workspace, run_root)
    assert (watch["watch_status"], watch["recommended_recovery"]) == ("FAILED", "RESUME")
    failed, = evidence["failed_steps"]
    assert failed["name"] == second["identity"] and failed["error_type"] == second["error"]["code"]
    assert first["error"]["code"] not in json.dumps(evidence)
    assert _tree_bytes(target) == before and _tree_bytes(run_root / Path(first["result_path"]).parent) == old


@pytest.mark.parametrize("returns,expression,value", [("Int", "0", 0), ("Bool", "false", False),
    ("Optional[Int]", "null", None), ("List[Int]", "(list 1 2)", [1, 2])])
def test_probe_validated_scalar_terminal_keeps_existing_wire(tmp_path, returns, expression, value):
    target = tmp_path / "T"
    target.mkdir()
    root = _scalar_run(target, returns, expression)
    assert load_evaluated_view(root)["workflow_outputs"] == value
    workspace = tmp_path / "W"
    workspace.mkdir()
    before = _tree_bytes(target)
    watch, evidence = _probe(workspace, root)
    assert (watch["watch_status"], watch["recommended_recovery"]) == ("COMPLETED", "NONE")
    assert evidence["run_status"] == "completed" and evidence["failed_steps"] == []
    assert "workflow_outputs" not in watch and "workflow_outputs" not in evidence
    assert _tree_bytes(target) == before


def test_probe_pure_failed_terminal_needs_no_failed_effect_row(tmp_path):
    target = tmp_path / "T"
    target.mkdir()
    source = target / "failed.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule failed) (export run) (defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))''')
    result = _run_cli(target, str(source), "--input", "divisor=0")
    assert result.returncode == 1, result.stderr
    root, = (target / ".orchestrate/runs").iterdir()
    workspace = tmp_path / "W"
    workspace.mkdir()
    before = _tree_bytes(target)
    watch, evidence = _probe(workspace, root)
    assert (watch["watch_status"], watch["recommended_recovery"]) == ("FAILED", "RESUME")
    assert evidence["run_status"] == "failed" and evidence["failed_steps"] == []
    assert _tree_bytes(target) == before


@pytest.mark.parametrize("boundary", ["relative-target", "unsafe-id", "unsafe-output"])
def test_probe_public_path_rejections_preserve_target(tmp_path, boundary):
    target = tmp_path / "T"
    target.mkdir()
    root = _pure_run(target)
    workspace = tmp_path / "W"
    workspace.mkdir()
    options = {"--run-id": root.name, "--target-workspace": str(target), "--output": "state/watch.json",
        "--evidence-root": "artifacts/work/evidence", "--repair-result-target-path": "artifacts/work/result.json"}
    flag, value, diagnostic = {"relative-target": ("--target-workspace", "../T", "must be an absolute path"),
        "unsafe-id": ("--run-id", "../escape", "Unsafe run id"),
        "unsafe-output": ("--output", "../escape.json", "Unsafe relative path")}[boundary]
    options[flag] = value
    argv = [sys.executable, str(ROOT / SCRIPT), *[token for pair in options.items() for token in pair]]
    before = _tree_bytes(target)
    result = subprocess.run(argv, cwd=workspace, env={**os.environ, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, timeout=10)
    assert result.returncode != 0 and diagnostic in result.stderr
    assert _tree_bytes(target) == before and not (tmp_path / "escape.json").exists()
