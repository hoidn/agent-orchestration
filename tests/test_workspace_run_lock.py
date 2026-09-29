"""A workspace has one active execution owner, independent of state-dir."""

from contextlib import contextmanager
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.run_lock import WorkspaceAlreadyActiveError, workspace_run_lock
from tests.test_workflow_resume_after_known_failure import SEQUENCE, _install, _log, _run
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args


LOCK_HOLDER = """
import sys, time
from pathlib import Path
from orchestrator.run_lock import workspace_run_lock
with workspace_run_lock(Path(sys.argv[1]), "active-run"):
    Path(sys.argv[2]).touch()
    time.sleep(60)
"""

GUARD_HOLDER = """
import fcntl, os, sys, time
from pathlib import Path
control = Path(sys.argv[1]) / ".orchestrate"
control.mkdir(exist_ok=True)
fcntl.flock(os.open(control / "workspace.guard", os.O_RDWR | os.O_CREAT), fcntl.LOCK_EX)
Path(sys.argv[2]).touch()
time.sleep(60)
"""


@contextmanager
def _holder(workspace, script=LOCK_HOLDER):
    ready = workspace / "ready"
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(workspace), str(ready)],
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


RACE_STARTERS = 12
RACE_ROUNDS = 20


def _race(workspace, count):
    """Release `count` starters at once; return (winners, run ids the refusals named)."""
    gate, done = threading.Barrier(count), threading.Barrier(count)
    winners, named = [], []

    def start(name):
        gate.wait()
        try:
            with workspace_run_lock(workspace, name):
                winners.append(name)
                done.wait(timeout=10)
        except WorkspaceAlreadyActiveError as error:
            named.append(error.run_id)
            done.wait(timeout=10)

    threads = [threading.Thread(target=start, args=(f"s{index}",)) for index in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    return winners, named


def test_racing_starters_all_name_the_winner_over_a_longer_stale_owner(tmp_path):
    for attempt in range(RACE_ROUNDS):
        workspace = tmp_path / f"round-{attempt}"
        (workspace / ".orchestrate").mkdir(parents=True)
        (workspace / ".orchestrate" / "workspace.lock").write_text("stale-owner-" + "x" * 40)
        winners, named = _race(workspace, RACE_STARTERS)
        assert len(winners) == 1
        assert named == winners * (RACE_STARTERS - 1)


def test_held_start_guard_refuses_within_the_bound(tmp_path):
    with _holder(tmp_path, GUARD_HOLDER):
        with pytest.raises(WorkspaceAlreadyActiveError) as error:
            with workspace_run_lock(tmp_path, "starter", guard_timeout=0.2):
                pytest.fail("starter passed a held start guard")
    assert error.value.code == "workspace_run_already_active"
    assert error.value.run_id is None
    assert "workspace.guard" in str(error.value)


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
    assert result.exit_code == 2
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
        assert resume_workflow(run_id=state_file.parent.name, force_restart=force_restart) == 2
    assert state_file.read_bytes() == before
    assert _log(files["probe"]) == ["prepare", "check"]
    error = capsys.readouterr().err
    assert "workspace_run_already_active" in error and "active-run" in error


def test_dry_run_succeeds_while_another_run_is_active(tmp_path, monkeypatch):
    files = _install(tmp_path, SEQUENCE)
    monkeypatch.chdir(tmp_path)
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


def test_trial_cli_refuses_with_the_same_status_and_one_code(tmp_path, monkeypatch, caplog):
    from orchestrator.cli.main import main
    from tests.test_workflow_lisp_trial_lowering import _write_trial_module

    source = _write_trial_module(tmp_path)
    monkeypatch.chdir(tmp_path)
    with workspace_run_lock(tmp_path, "active-run"):
        exit_code = main([
            "trial", str(source), "--entry-workflow", "compare",
            "--run-ref-root", str((tmp_path / "children").resolve()),
        ])
    assert exit_code == 2
    assert caplog.text.count("workspace_run_already_active") == 1
    assert "active-run" in caplog.text
    assert not (tmp_path / ".orchestrate" / "build").exists()


@pytest.mark.parametrize("path_program", [False, True])
def test_run_ref_child_refuses_an_active_clone_before_decoding_or_compiling(tmp_path, capsys, path_program):
    from tests.test_workflow_run_ref_child import (
        _build_path_fixture, _invoke, _invoke_path, _path_request, _request,
    )

    if path_program:
        fixture = _build_path_fixture(tmp_path)
        payload, request_path, invoke = _path_request(fixture), fixture.request_path, _invoke_path
        run_root = fixture.state_dir / fixture.child_run_id
    else:
        # A request that passes the loader; its capsule is read only after the lock.
        digest = "sha256:" + "0" * 64
        capsule = SimpleNamespace(
            root=tmp_path, capsule_dir=tmp_path, capsule_digest=digest,
            compiler_identity=digest, target_workflow_name="entry::run",
        )
        payload, request_path, state_dir = _request(capsule, case="active")
        invoke = _invoke
        run_root = state_dir / payload["child_run_id"]
    with workspace_run_lock(Path(payload["clone_root"]), "active-run"):
        exit_code, _, stderr = invoke(payload, request_path, capsys)
    assert exit_code == 1
    assert json.loads(stderr)["code"] == "run_ref_child_launch_failed"
    assert not run_root.exists()
