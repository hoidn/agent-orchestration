"""A workspace has one active execution owner, independent of state-dir."""

from contextlib import contextmanager
import subprocess
import sys
import time
from types import SimpleNamespace

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.run_lock import WorkspaceAlreadyActiveError, workspace_run_lock
from tests.test_workflow_resume_after_known_failure import SEQUENCE, _install, _log, _run
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args


@contextmanager
def _holder(workspace):
    ready = workspace / "ready"
    process = subprocess.Popen(
        [sys.executable, "-c", """
import sys, time
from pathlib import Path
from orchestrator.run_lock import workspace_run_lock
with workspace_run_lock(Path(sys.argv[1]), "active-run"):
    Path(sys.argv[2]).touch()
    time.sleep(60)
""", str(workspace), str(ready)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists():
            if process.poll() is not None:
                pytest.fail(str(process.communicate()))
            if time.monotonic() >= deadline:
                pytest.fail("workspace lock holder did not start")
            time.sleep(0.01)
        yield process
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=5)


def test_workspace_lock_names_owner_and_is_released_on_kill(tmp_path):
    with _holder(tmp_path) as process:
        with pytest.raises(WorkspaceAlreadyActiveError) as error:
            with workspace_run_lock(tmp_path, "second"):
                pytest.fail("second execution acquired workspace")
        assert error.value.code == "workspace_run_already_active"
        assert error.value.run_id == "active-run"
        assert "active-run" in str(error.value)
        process.kill()
        process.wait(timeout=5)
        with workspace_run_lock(tmp_path, "after-kill"):
            pass


def test_stale_metadata_and_different_workspaces_do_not_block(tmp_path):
    control = tmp_path / ".orchestrate"
    control.mkdir()
    (control / "workspace.lock").write_text("dead-run\n")
    other = tmp_path / "other"
    other.mkdir()
    with workspace_run_lock(tmp_path, "first"):
        with workspace_run_lock(other, "second"):
            pass
    with workspace_run_lock(tmp_path, "third"):
        pass


@pytest.mark.parametrize("separate_state_dir", [False, True])
def test_run_refuses_before_build_or_effect_and_preserves_requested_identity(
    tmp_path, monkeypatch, caplog, separate_state_dir,
):
    files = _install(tmp_path, SEQUENCE)
    monkeypatch.chdir(tmp_path)
    args = _run_args(files)
    args.command_boundaries_file = str(files["commands"])
    if separate_state_dir:
        args.state_dir = str(tmp_path / "external-runs")
    with workspace_run_lock(tmp_path, "active-run"):
        result = run_workflow(args, run_id="requested-run")
    assert result.exit_code == 1
    assert result.run_id == "requested-run"
    assert "workspace_run_already_active" in caplog.text
    assert "active-run" in caplog.text
    assert not (tmp_path / ".orchestrate" / "build").exists()
    assert not files["probe"].with_suffix(".log").exists()


@pytest.mark.parametrize("force_restart", [False, True])
def test_resume_refuses_before_mutating_other_run(tmp_path, monkeypatch, capsys, force_restart):
    files = _install(tmp_path, SEQUENCE, broken=("check",))
    monkeypatch.chdir(tmp_path)
    assert _run(files) == 1
    state_file = next((tmp_path / ".orchestrate" / "runs").glob("*/state.json"))
    before = state_file.read_bytes()
    with workspace_run_lock(tmp_path, "active-run"):
        assert resume_workflow(run_id=state_file.parent.name, force_restart=force_restart) == 1
    assert state_file.read_bytes() == before
    assert _log(files["probe"]) == ["prepare", "check"]
    error = capsys.readouterr().err
    assert "workspace_run_already_active" in error and "active-run" in error


def test_dry_run_ignores_workspace_lock_and_takes_none(tmp_path, monkeypatch):
    from orchestrator.cli.commands import run as run_module

    files = _install(tmp_path, SEQUENCE)
    monkeypatch.chdir(tmp_path)
    def unexpected_lock(*args, **kwargs):
        pytest.fail("dry-run attempted to take a workspace lock")
    monkeypatch.setattr(run_module, "workspace_run_lock", unexpected_lock)
    args = _run_args(files)
    args.command_boundaries_file = str(files["commands"])
    args.dry_run = True
    with workspace_run_lock(tmp_path, "active-run"):
        result = run_workflow(args)
    assert result.exit_code == 0
    assert not files["probe"].with_suffix(".log").exists()


@pytest.mark.parametrize("broken", [(), ("check",)])
def test_public_run_releases_workspace_after_success_or_failure(tmp_path, monkeypatch, broken):
    files = _install(tmp_path, SEQUENCE, broken=broken)
    monkeypatch.chdir(tmp_path)
    assert _run(files) == bool(broken)
    with workspace_run_lock(tmp_path, "next-run"):
        pass
    assert _log(files["probe"]) == (["prepare", "check"] if broken else ["prepare", "check", "finish"])


def test_trial_sdk_obeys_same_workspace_lock(tmp_path):
    from orchestrator.workflow.trial.sdk import TrialEntryRequestError, run_trial_entry
    from tests.test_cli_trial import _options
    from tests.test_workflow_lisp_trial_lowering import _write_trial_module

    source = _write_trial_module(tmp_path)
    with workspace_run_lock(tmp_path, "active-run"):
        with pytest.raises(TrialEntryRequestError) as error:
            run_trial_entry(
                workflow_file=source, entry_workflow="compare", inputs={},
                workspace=tmp_path, state_dir=None, run_ref_root=tmp_path / "children",
                options=_options(tmp_path),
            )
    assert error.value.code == "workspace_run_already_active"
    assert "active-run" in str(error.value)
    assert not (tmp_path / ".orchestrate" / "build").exists()


@pytest.mark.parametrize("path_program", [False, True])
def test_run_ref_child_owns_clone_before_compilation(tmp_path, monkeypatch, path_program):
    from orchestrator.workflow.run_ref import child

    request = SimpleNamespace(
        clone_root=tmp_path, child_run_id="child-run",
        materialized_source=None, step_config=None,
    )
    def unexpected_compile(*args, **kwargs):
        pytest.fail("child compilation ran in an active workspace")
    monkeypatch.setattr(child, "_target_bundle", unexpected_compile)
    monkeypatch.setattr(child, "compile_and_admit_path_program", unexpected_compile)
    loader = "load_path_request" if path_program else "load_request"
    monkeypatch.setattr(child, loader, lambda _: request)
    diagnostics = []
    monkeypatch.setattr(child, "_write_document", lambda _, payload: diagnostics.append(payload))
    with workspace_run_lock(tmp_path, "active-run"):
        assert child.main(["--path-request" if path_program else "--request", "request.json"]) == 1
    assert diagnostics[0]["code"] == "run_ref_child_launch_failed"
