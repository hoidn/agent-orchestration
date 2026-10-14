"""Result-path operations stay inside the workspace the run started in (plan Task 8, second review).

Contract: `specs/io.md`, "Result-file freshness". The executor holds its
workspace root open from its creation, and a call frame's executor uses the
same descriptor, so a workspace root replaced by a symbolic link later cannot
lead the pre-call clearing of a result path outside the workspace. A result
path never passes through a symbolic link: a link on the path fails the call
before launch with `stale_bundle_removal_failed` and the step's source origin,
also inside a call frame, and a `.orchestrate` that is a link is refused at
run start with `state_root_symlink`, before any effect.

Programs, probes and stand-in providers come from
`tests/test_workflow_result_file_freshness.py`.
"""

from __future__ import annotations

import errno
import logging
import os
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.exec.output_capture import OutputCapture
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.workspace_files import WorkspaceFiles


class _RootSwap:
    """Replace the workspace directory by a link to `outside`, and put it back."""

    def __init__(self, workspace: Path, outside: Path) -> None:
        self.workspace, self.outside = workspace, outside
        self.moved = workspace.with_name(workspace.name + ".started")

    def __enter__(self) -> None:
        self.workspace.rename(self.moved)
        self.workspace.symlink_to(self.outside, target_is_directory=True)

    def __exit__(self, *_exc) -> None:
        self.workspace.unlink()
        self.moved.rename(self.workspace)


def _workspace_and_outside(tmp_path: Path) -> tuple[Path, Path]:
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    return workspace, outside


def test_resume_refuses_a_linked_state_root_before_changing_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    from tests.historical_state import write_historical_state
    workflow = tmp_path / "historical.yaml"
    workflow.write_text("steps: []", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="historical")
    write_historical_state(manager, "historical.yaml")
    state_path = manager.state_file
    before = state_path.read_bytes()
    state_root = tmp_path / ".orchestrate"
    moved = tmp_path / ".orchestrate.started"
    state_root.rename(moved)
    state_root.symlink_to(moved, target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    try:
        with caplog.at_level(logging.ERROR):
            result = resume_workflow(run_id="historical", retry_delay_ms=0)
    finally:
        state_root.unlink()
        moved.rename(state_root)
    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert (result, errors[0].split(":")[0], state_path.read_bytes()) == (1, "state_root_symlink", before)


# The line of the call form inside the procedure `tick` in the freshness module's SOURCE.


def test_a_failed_close_while_walking_the_result_path_leaves_no_descriptor_open(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first close fails after the child directory was opened; Linux releases a descriptor even when close
    reports an error, so the injected failure closes it and then raises."""

    (tmp_path / "a" / "b").mkdir(parents=True)
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    close = os.close
    failed: list[int] = []

    def close_then_fail_once(descriptor: int) -> None:
        close(descriptor)
        if not failed:
            failed.append(descriptor)
            raise OSError(errno.EIO, "injected close failure")

    before = len(os.listdir("/proc/self/fd"))
    files = WorkspaceFiles(tmp_path, root_fd=root_fd)
    try:
        with monkeypatch.context() as patched:
            patched.setattr(os, "close", close_then_fail_once)
            with pytest.raises(OSError, match="injected"):
                files.clear(Path("a/b/leaf.json"))
        after = len(os.listdir("/proc/self/fd"))
    finally:
        files.close()
        os.close(root_fd)

    assert (failed != [], after - before) == (True, 0)


def test_the_result_path_walk_creates_missing_parents_and_removes_a_stale_file(tmp_path: Path) -> None:
    stale = tmp_path / "a" / "b" / "result.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    files = WorkspaceFiles(tmp_path, root_fd=root_fd)
    try:
        files.clear(Path("a/b/result.json"))
        files.clear(Path("c/d/result.json"))
    finally:
        files.close()
        os.close(root_fd)

    assert (stale.exists(), (tmp_path / "c" / "d").is_dir()) == (False, True)


def test_output_file_tee_stays_under_the_workspace_descriptor_during_root_replacement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, outside = _workspace_and_outside(tmp_path)
    output_file = workspace / "state" / "stdout.txt"
    owner = WorkspaceFiles(workspace)
    capture = OutputCapture.capture

    def capture_while_root_is_linked(capturer, *args, **kwargs):
        with _RootSwap(workspace, outside):
            return capture(capturer, *args, **kwargs)

    monkeypatch.setattr(OutputCapture, "capture", capture_while_root_is_linked)
    try:
        result = StepExecutor(workspace).execute_command(
            step_name="capture",
            command=["python", "-c", "print('captured')"],
            output_file=output_file,
            workspace_files=owner,
        )
        assert result.exit_code == 0
        assert owner.read("state/stdout.txt") == b"captured\n"
        assert not (outside / "state" / "stdout.txt").exists()
    finally:
        owner.close()
