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
import json
import os
import sys
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.providers.types import ProviderSessionMetadataMode
from orchestrator.exec.output_capture import OutputCapture
from orchestrator.exec.step_executor import StepExecutor
from orchestrator.state import StateManager
from orchestrator.workflow import executor as executor_module
from orchestrator.workflow.call_frame_state import _CallFrameStateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_result_file_freshness import (
    _Commands,
    _Interrupted,
    _failed_violations,
    _install,
    _run,
    _runs,
    _violations,
    _Providers,
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


def test_a_workspace_root_replaced_during_a_call_cannot_supply_its_result_by_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace, outside = _workspace_and_outside(tmp_path)
    effect = _install(workspace, _Providers, body="call")
    effect.writes("nothing")
    monkeypatch.chdir(workspace)
    moved = workspace.with_name(workspace.name + ".started")
    victims: list[Path] = []
    clear = WorkflowExecutor._prepare_absent_runtime_output_bundle
    apply_contract = WorkflowExecutor._apply_expected_outputs_contract
    execute_provider = effect.execute

    def clear_then_plant(executor, step, bundle):
        error = clear(executor, step, bundle)
        if not victims:
            relative = Path(bundle["path"])
            if relative.is_absolute():
                relative = relative.relative_to(workspace)
            victim = outside / relative
            victim.parent.mkdir(parents=True, exist_ok=True)
            victim.write_text('{"n":1,"stop":true}', encoding="utf-8")
            victims.append(victim)
        return error

    def execute_and_swap_root(_provider_executor, invocation, **kwargs):
        result = execute_provider(invocation, **kwargs)
        if effect.calls == 1:
            workspace.rename(moved)
            workspace.symlink_to(outside, target_is_directory=True)
        return result

    def validate_and_restore(executor, *args, **kwargs):
        try:
            return apply_contract(executor, *args, **kwargs)
        finally:
            if workspace.is_symlink():
                workspace.unlink()
                moved.rename(workspace)

    effect.execute = execute_and_swap_root
    with (
        patch.object(WorkflowExecutor, "_prepare_absent_runtime_output_bundle", clear_then_plant),
        patch.object(WorkflowExecutor, "_apply_expected_outputs_contract", validate_and_restore),
    ):
        _run_id, state = _run(effect)

    assert (state["status"], _violations(state), effect.calls, victims[0].read_text(encoding="utf-8")) == (
        "failed",
        ["missing_bundle_file"],
        1,
        '{"n":1,"stop":true}',
    )


def test_omp_bundle_creation_stays_in_the_workspace_after_an_ancestor_becomes_a_link(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ancestor = tmp_path / "ancestor"
    workspace = ancestor / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir(parents=True)
    outside_workspace = outside / "workspace"
    outside_workspace.mkdir(parents=True)
    effect = _install(workspace, _Providers, body="call")
    effect.writes("nothing")
    execute_provider = effect.execute

    def execute_with_omp_json(_provider_executor, invocation, **kwargs):
        result = execute_provider(invocation, **kwargs)
        result.stdout = b'{"n":1,"stop":true}'
        return result

    effect.execute = execute_with_omp_json
    moved = ancestor.with_name(ancestor.name + ".started")
    created_outside: list[Path] = []
    materialize = WorkflowExecutor._materialize_omp_output_bundle
    registry_get = ProviderRegistry.get

    def get_omp_template(registry, name):
        template = registry_get(registry, name)
        if name == "codex" and template is not None:
            return replace(
                template,
                command_metadata_mode=ProviderSessionMetadataMode.OMP_JSON_STDOUT.value,
            )
        return template

    def swap_ancestor_then_materialize(executor, bundle, payload):
        ancestor.rename(moved)
        ancestor.symlink_to(outside, target_is_directory=True)
        try:
            result = materialize(executor, bundle, payload)
            relative = Path(bundle["path"])
            if relative.is_absolute():
                relative = relative.relative_to(workspace)
            created_outside.append(outside_workspace / relative)
            return result
        finally:
            ancestor.unlink()
            moved.rename(ancestor)

    monkeypatch.chdir(workspace)
    with (
        effect.active(),
        patch.object(ProviderRegistry, "get", get_omp_template),
        patch.object(
            WorkflowExecutor,
            "_materialize_omp_output_bundle",
            swap_ancestor_then_materialize,
        ),
        patch.object(sys, "argv", [*_run_argv(effect.files), "--command-boundaries-file", str(effect.files["commands"])]),
    ):
        result = run_workflow(_run_args(effect.files))

    state = json.loads(next((workspace / ".orchestrate" / "runs").iterdir()).joinpath("state.json").read_text(encoding="utf-8"))
    assert (result.exit_code, state["status"], effect.calls, created_outside[0].exists()) == (
        0,
        "completed",
        1,
        False,
    )


def test_resume_refuses_a_linked_state_root_before_changing_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    effect = _install(tmp_path, _Commands, body="call")
    effect.writes("every_call")
    effect.interrupt_first_call = True
    monkeypatch.chdir(tmp_path)
    with pytest.raises(_Interrupted):
        _run(effect)
    (run_dir,) = _runs(tmp_path)
    effect.interrupt_first_call = False
    state_path = run_dir / "state.json"
    before = state_path.read_bytes()
    state_root = tmp_path / ".orchestrate"
    moved = tmp_path / ".orchestrate.started"
    state_root.rename(moved)
    state_root.symlink_to(moved, target_is_directory=True)
    try:
        with caplog.at_level(logging.ERROR), effect.active():
            result = resume_workflow(run_id=run_dir.name, retry_delay_ms=0)
    finally:
        state_root.unlink()
        moved.rename(state_root)

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    assert (result, errors[0].split(":")[0], state_path.read_bytes(), effect.calls) == (
        1,
        "state_root_symlink",
        before,
        1,
    )


def test_phased_delivery_refusal_in_a_call_frame_keeps_the_authored_location(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _PhasedProviders(_Providers):
        call = (
            '(provider-result providers.tick :prompt (tick-prompt :subject "tick") '
            ":delivery :phased :materialization-attempts 1)"
        )

    effect = _install(tmp_path, _PhasedProviders, body="procedure")
    effect.writes("nothing")
    source = effect.files["source"]
    source_text = source.read_text(encoding="utf-8")
    prompt = '''  (defprompt tick-prompt
    (:fills (subject :text))
    -> Count
    "Advance {subject}")
'''
    source.write_text(source_text.replace("  (defproc tick", prompt + "  (defproc tick"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    original_partition = executor_module.partition_provider_call_policy

    def reject_runtime_policy(policy):
        if isinstance(policy, dict) and policy.get("delivery") == "phased":
            raise ValueError("injected malformed runtime policy")
        return original_partition(policy)

    with (
        effect.active(),
        patch.object(executor_module, "partition_provider_call_policy", reject_runtime_policy),
        patch.object(
            WorkflowExecutor,
            "_phased_policy_refusal",
            staticmethod(lambda _policy: ("delivery_type_invalid", None)),
        ),
    ):
        _run_id, state = _run(effect)

    frame_states = [frame["state"] for frame in state.get("call_frames", {}).values()]
    errors = [
        step["error"]
        for frame_state in frame_states
        for step in frame_state.get("steps", {}).values()
        if isinstance(step, dict) and isinstance(step.get("error"), dict)
    ]
    error = next(item for item in errors if item.get("type") == "provider_phased_delivery_policy_invalid")
    diagnostic = error["context"]["diagnostic"]
    authored_sources = [
        source
        for source in [diagnostic["primary_source"], *diagnostic["related_sources"]]
        if source["kind"] == "authored_span"
    ]
    expected_line = next(
        index
        for index, line in enumerate(source.read_text(encoding="utf-8").splitlines(), 1)
        if ":delivery :phased" in line
    )
    assert any(
        source["path"] == "grt/entry.orc"
        and source["span"]["start_line"] == expected_line
        for source in authored_sources
    )


def test_three_hundred_result_calls_close_the_workspace_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    effect = _install(tmp_path, _Providers, body="call")
    effect.writes("every_call")
    source = effect.files["source"]
    source.write_text(source.read_text(encoding="utf-8").replace(":max 3", ":max 300"), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    before = len(os.listdir("/proc/self/fd"))

    _run_id, state = _run(effect)

    after = len(os.listdir("/proc/self/fd"))
    assert (state["status"], effect.calls, after - before) == ("completed", 300, 0)


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


def test_external_call_frame_result_owner_derives_from_parent_run_descriptor(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    run_root = tmp_path / "external-state" / "run"
    call_root = run_root / "call_frames" / "frame-1"
    workspace.mkdir()
    call_root.mkdir(parents=True)
    parent_fd = os.open(run_root, os.O_RDONLY | os.O_DIRECTORY)
    workspace_files = WorkspaceFiles(workspace)
    parent_manager = type(
        "ParentManager",
        (),
        {"logical_run_root": run_root, "_run_root_fd": parent_fd},
    )()
    frame_manager = type(
        "FrameManager",
        (),
        {
            "logical_run_root": call_root,
            "io_run_root": Path(
                f"/proc/self/fd/{parent_fd}/call_frames/frame-1"
            ),
            "parent_manager": parent_manager,
        },
    )()
    executor = WorkflowExecutor.__new__(WorkflowExecutor)
    executor.workspace_files = workspace_files
    executor.state_manager = frame_manager
    (call_root / "result.json").write_text('{"ok":true}\n', encoding="utf-8")

    call_files = executor._run_root_workspace_files()
    try:
        assert call_files.workspace == call_root
        assert call_files.read("result.json") == b'{"ok":true}\n'
    finally:
        call_files.close()
        aggregate_owner = getattr(executor, "_aggregate_run_files_owner", None)
        if isinstance(aggregate_owner, WorkspaceFiles):
            aggregate_owner.close()
        workspace_files.close()
        os.close(parent_fd)


def test_external_run_root_lease_is_inherited_after_path_replacement(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workflow = workspace / "workflow.orc"
    workspace.mkdir()
    workflow.write_text("; external run-root fixture\n", encoding="utf-8")
    manager = StateManager(
        workspace,
        state_dir=tmp_path / "external-state",
        run_id="external-run-root-lease",
    )
    manager.initialize("workflow.orc")
    run_root = manager.run_root
    frame_root = run_root / "call_frames" / "frame-1"
    frame_root.mkdir(parents=True)
    (frame_root / "result.json").write_text("original\n", encoding="utf-8")

    workspace_files = WorkspaceFiles(workspace)
    parent = WorkflowExecutor.__new__(WorkflowExecutor)
    parent.workspace_files = workspace_files
    parent._owns_workspace_files = False
    parent.state_manager = manager
    parent._aggregate_run_files_owner = None
    inherited_run_files = parent._aggregate_run_workspace_files()
    detached_run_root = run_root.with_name("detached-run-root")
    run_root.rename(detached_run_root)
    replacement_frame = run_root / "call_frames" / "frame-1"
    replacement_frame.mkdir(parents=True)
    (replacement_frame / "result.json").write_text(
        "replacement\n",
        encoding="utf-8",
    )

    child = WorkflowExecutor.__new__(WorkflowExecutor)
    child.workspace_files = workspace_files
    child._owns_workspace_files = False
    child.state_manager = type(
        "CallFrameManager",
        (),
        {
            "logical_run_root": replacement_frame,
            "parent_manager": manager,
        },
    )()
    child._aggregate_run_files_owner = inherited_run_files
    frame_files = child._run_root_workspace_files()
    try:
        assert frame_files.read("result.json") == b"original\n"
    finally:
        frame_files.close()
        child.close()
        parent.close()
        workspace_files.close()
        manager.close()
