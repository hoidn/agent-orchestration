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
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow import executor as executor_module
from orchestrator.workflow.call_frame_state import _CallFrameStateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_workflow_result_file_freshness import (
    _Commands,
    _failed_violations,
    _install,
    _run,
    effect_kind,  # noqa: F401 - pytest fixture
)
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv


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


def _plant(outside: Path, relative: str) -> Path:
    victim = outside / relative
    victim.parent.mkdir(parents=True, exist_ok=True)
    victim.write_text("outside", encoding="utf-8")
    return victim


def _workspace_and_outside(tmp_path: Path) -> tuple[Path, Path]:
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    return workspace, outside


@pytest.mark.parametrize("body", ["call", "procedure"])
def test_a_workspace_root_replaced_by_a_link_after_the_run_started_does_not_lead_the_clearing_outside(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, body: str
) -> None:
    """The root is a link to a directory holding a file at the result path while the path is cleared."""

    workspace, outside = _workspace_and_outside(tmp_path)
    effect = _install(workspace, _Commands, body=body)
    effect.writes("every_call")
    monkeypatch.chdir(workspace)
    clear = WorkflowExecutor._prepare_absent_runtime_output_bundle
    victims: list[Path] = []

    def clear_while_the_root_is_a_link(executor, step, bundle):
        if victims:
            return clear(executor, step, bundle)
        victims.append(_plant(outside, bundle["path"]))
        with _RootSwap(workspace, outside):
            return clear(executor, step, bundle)

    with patch.object(WorkflowExecutor, "_prepare_absent_runtime_output_bundle", clear_while_the_root_is_a_link):
        _run_id, state = _run(effect)

    assert (victims[0].exists() and victims[0].read_text(encoding="utf-8"), state["status"], effect.calls) == (
        "outside",
        "completed",
        3,
    )


def test_a_call_frame_executor_created_while_the_workspace_root_is_a_link_clears_inside_the_run_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first run leaves the promoted-call result files; the second run creates every call frame's executor while
    the root is a link to a directory holding files at those paths."""

    workspace, outside = _workspace_and_outside(tmp_path)
    effect = _install(workspace, _Commands, body="procedure")
    effect.writes("every_call")
    monkeypatch.chdir(workspace)
    _run(effect)
    victims = [
        _plant(outside, path.relative_to(workspace).as_posix())
        for path in (workspace / ".orchestrate" / "workflow_lisp" / "calls").rglob("*result_bundle.json")
    ]
    create = WorkflowExecutor.__init__

    def create_while_the_root_is_a_link(executor, *args, **kwargs):
        if not isinstance(kwargs.get("state_manager"), _CallFrameStateManager):
            return create(executor, *args, **kwargs)
        with _RootSwap(workspace, outside):
            return create(executor, *args, **kwargs)

    with patch.object(WorkflowExecutor, "__init__", create_while_the_root_is_a_link):
        _run_id, state = _run(effect)

    assert (len(victims), {victim.read_text(encoding="utf-8") for victim in victims}, state["status"]) == (
        3,
        {"outside"},
        "completed",
    )


def _source_origins(state: dict[str, object]) -> list[tuple[str, list[tuple[str, int]]]]:
    return [
        (violation["type"], [(origin["path"], origin["line"]) for origin in violation.get("source_origins", ())])
        for violation in _failed_violations(state)
    ]


# The line of the call form inside the procedure `tick` in the freshness module's SOURCE.
CALLEE_CALL_LINE = 10


def test_a_missing_result_in_a_call_frame_carries_the_callee_step_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind
) -> None:
    effect = _install(tmp_path, effect_kind, body="procedure")
    effect.writes("first_call_only")
    monkeypatch.chdir(tmp_path)

    _run_id, state = _run(effect)

    assert _source_origins(state) == [("missing_bundle_file", [(str(effect.files["source"]), CALLEE_CALL_LINE)])]


def test_a_result_path_that_cannot_be_cleared_in_a_call_frame_carries_the_callee_step_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, effect_kind
) -> None:
    """The promoted-call path names the iteration but not the run: a directory put where the first run's first
    iteration wrote its result blocks the second run's first call."""

    effect = _install(tmp_path, effect_kind, body="procedure")
    effect.writes("every_call")
    monkeypatch.chdir(tmp_path)
    _run(effect)
    (first,) = [
        path
        for path in (tmp_path / ".orchestrate" / "workflow_lisp" / "calls").rglob("*result_bundle.json")
        if "0" in path.relative_to(tmp_path).parts
    ]
    first.unlink()
    first.mkdir()

    _run_id, state = _run(effect)

    assert _source_origins(state) + [effect.calls] == [
        ("stale_bundle_removal_failed", [(str(effect.files["source"]), CALLEE_CALL_LINE)]),
        3,
    ]


@pytest.mark.parametrize("inside", [True, False], ids=["link-inside", "link-outside"])
def test_a_result_path_through_a_link_fails_before_launch_with_its_code_at_the_step_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, inside: bool
) -> None:
    """`.orchestrate/workflow_lisp` is a link to a directory inside or outside the workspace."""

    workspace, outside = _workspace_and_outside(tmp_path)
    target = workspace / "bundle-home" if inside else outside
    target.mkdir(exist_ok=True)
    (workspace / ".orchestrate").mkdir()
    (workspace / ".orchestrate" / "workflow_lisp").symlink_to(target, target_is_directory=True)
    effect = _install(workspace, _Commands, body="call")
    effect.writes("every_call")
    monkeypatch.chdir(workspace)

    _run_id, state = _run(effect)

    assert (
        [(kind, [path for path, _line in origins]) for kind, origins in _source_origins(state)],
        effect.calls,
        list(target.iterdir()),
    ) == ([("stale_bundle_removal_failed", [str(effect.files["source"])])], 0, [])


def test_a_workspace_whose_state_directory_is_a_link_is_refused_at_run_start_before_any_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """`.orchestrate` is a link to another directory inside the workspace."""

    effect = _install(tmp_path, _Commands, body="call")
    effect.writes("every_call")
    (tmp_path / "state-home").mkdir()
    (tmp_path / ".orchestrate").symlink_to(tmp_path / "state-home", target_is_directory=True)
    monkeypatch.chdir(tmp_path)
    args = _run_args(effect.files)
    args.command_boundaries_file = str(effect.files["commands"])
    argv = [*_run_argv(effect.files), "--command-boundaries-file", str(effect.files["commands"])]

    with caplog.at_level(logging.ERROR), effect.active(), patch.object(sys, "argv", argv):
        result = run_workflow(args)

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert (
        result.exit_code,
        [message.split(":")[0] for message in errors],
        str(tmp_path / ".orchestrate") in errors[0],
        list((tmp_path / "state-home").iterdir()),
        effect.calls,
    ) == (1, ["state_root_symlink"], True, [], 0)


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
    try:
        with monkeypatch.context() as patched:
            patched.setattr(os, "close", close_then_fail_once)
            with pytest.raises(OSError, match="injected"):
                executor_module._clear_workspace_leaf(root_fd, Path("a/b/leaf.json"))
        after = len(os.listdir("/proc/self/fd"))
    finally:
        os.close(root_fd)

    assert (failed != [], after - before) == (True, 0)


def test_the_result_path_walk_creates_missing_parents_and_removes_a_stale_file(tmp_path: Path) -> None:
    stale = tmp_path / "a" / "b" / "result.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("stale", encoding="utf-8")
    root_fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        executor_module._clear_workspace_leaf(root_fd, Path("a/b/result.json"))
        executor_module._clear_workspace_leaf(root_fd, Path("c/d/result.json"))
    finally:
        os.close(root_fd)

    assert (stale.exists(), (tmp_path / "c" / "d").is_dir()) == (False, True)
