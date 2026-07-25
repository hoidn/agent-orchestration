"""Public compile/run acceptance for Workflow Lisp provider supervision."""

from __future__ import annotations

from argparse import Namespace
from concurrent.futures import Future
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys
import threading
from typing import Any, Mapping

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.observability.report import build_status_snapshot
from orchestrator.providers import InputMode
from orchestrator.providers.control import ProviderCancellationResult
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.session_transport import SessionIdentitySnapshot
from orchestrator.providers.types import (
    ProviderInvocation,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.provider_supervision.bindings import (
    WorkflowProviderSupervisionBindings,
)
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle


FIXTURE_ROOT = (
    Path(__file__).parent / "fixtures" / "workflow_lisp" / "provider_supervision"
)
FIXTURE_FILES = (
    "provider_supervision_continue.orc",
    "providers.json",
    "prompts.json",
    "worker.md",
    "supervisor.md",
)


class _InjectedControllerCrash(BaseException):
    pass


class _ObservationHandle:
    def __init__(self, *, target: str, socket_path: Path) -> None:
        self.target = target
        self.socket_path = socket_path
        self.finalized = False

    def check_health(self) -> bool:
        return not self.finalized

    def finalize(self) -> None:
        self.finalized = True


class _ObservationManager:
    def __init__(self, _run_root: Path) -> None:
        self._index = 0
        self.handles: list[_ObservationHandle] = []
        self.closed = False

    def next_invocation_id(self) -> str:
        self._index += 1
        return f"invocation-{self._index}"

    def open_observation(
        self,
        *,
        invocation_id: str,
        member_id: str,
        turn_id: str,
    ) -> _ObservationHandle:
        del invocation_id
        handle = _ObservationHandle(
            target=f"pane:{member_id}:{turn_id}",
            socket_path=Path("/tmp/provider-supervision-e2e.sock"),
        )
        self.handles.append(handle)
        return handle

    def close(self) -> None:
        self.closed = True


class _ScriptedControl:
    def __init__(
        self,
        *,
        snapshot: SessionIdentitySnapshot | None = None,
    ) -> None:
        self.session_snapshot = snapshot
        self.terminal_result: ProviderCancellationResult | None = None
        self.cancel_requested = threading.Event()
        self.execution_done = threading.Event()
        self.future: Future[Any] | None = None
        self.cancel_and_reap_calls = 0

    def attach_execution_future(self, future: Future[Any]) -> None:
        assert self.future is None
        self.future = future

    def request_cancel(
        self,
        *,
        reason: str = "external",
        grace: float | None = None,
    ) -> None:
        del reason, grace
        self.cancel_requested.set()

    def cancel_and_reap(self, grace: float) -> ProviderCancellationResult:
        del grace
        self.cancel_and_reap_calls += 1
        self.cancel_requested.set()
        assert self.execution_done.wait(timeout=1)
        assert self.terminal_result is not None
        return self.terminal_result


@dataclass
class _FakeProviderRuntime:
    managers: list[_ObservationManager] = field(default_factory=list)
    prepared: list[ProviderInvocation] = field(default_factory=list)
    executed: list[ProviderInvocation] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)


def _copy_fixture(workspace: Path) -> dict[str, Path]:
    copied: dict[str, Path] = {}
    for name in FIXTURE_FILES:
        destination = workspace / name
        destination.write_bytes((FIXTURE_ROOT / name).read_bytes())
        copied[name] = destination
    return copied


def _build_request(
    workspace: Path,
    files: dict[str, Path],
) -> FrontendBuildRequest:
    return FrontendBuildRequest(
        source_path=files["provider_supervision_continue.orc"],
        source_roots=(workspace,),
        entry_workflow="orchestrate",
        provider_externs_path=files["providers.json"],
        prompt_externs_path=files["prompts.json"],
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=workspace,
    )


def _run_args(files: dict[str, Path]) -> Namespace:
    return Namespace(
        workflow=str(files["provider_supervision_continue.orc"]),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=0,
        quiet=True,
        verbose=False,
        log_level="error",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow="orchestrate",
        source_root=[str(files["provider_supervision_continue.orc"].parent)],
        provider_externs_file=str(files["providers.json"]),
        prompt_externs_file=str(files["prompts.json"]),
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def _run_argv(files: dict[str, Path]) -> list[str]:
    return [
        "orchestrator",
        "run",
        str(files["provider_supervision_continue.orc"]),
        "--source-root",
        str(files["provider_supervision_continue.orc"].parent),
        "--entry-workflow",
        "orchestrate",
        "--provider-externs-file",
        str(files["providers.json"]),
        "--prompt-externs-file",
        str(files["prompts.json"]),
    ]


def _only_run(workspace: Path) -> tuple[Path, dict[str, object]]:
    run_roots = list((workspace / ".orchestrate" / "runs").iterdir())
    assert len(run_roots) == 1
    run_root = run_roots[0]
    return run_root, json.loads(
        (run_root / "state.json").read_text(encoding="utf-8")
    )


def _install_fake_provider_runtime(
    monkeypatch: pytest.MonkeyPatch,
    *,
    payloads: Mapping[str, str] | None = None,
) -> _FakeProviderRuntime:
    runtime = _FakeProviderRuntime()
    turn_payloads = {
        "worker_fresh": '"fresh-value"',
        "supervisor_directive": '{"variant":"CONTINUE"}',
        **dict(payloads or {}),
    }

    def manager_factory(run_root: Path) -> _ObservationManager:
        manager = _ObservationManager(run_root)
        runtime.managers.append(manager)
        return manager

    def prepare_invocation(
        _self: ProviderExecutor,
        *,
        provider_name: str,
        prompt_content: str,
        env: dict[str, str],
        session_request: object,
        timeout_sec: int,
        **_kwargs: object,
    ) -> tuple[ProviderInvocation, None]:
        invocation = ProviderInvocation(
            command=["fake-provider", provider_name],
            input_mode=InputMode.STDIN,
            prompt=prompt_content,
            env=env,
            timeout_sec=timeout_sec,
            session_request=session_request,
        )
        with runtime.lock:
            runtime.prepared.append(invocation)
        return invocation, None

    def execute_provider(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: object,
    ) -> ProviderExecutionResult:
        with runtime.lock:
            runtime.executed.append(invocation)
        supervision = invocation.metadata["provider_supervision"]
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output_path.write_text(
            turn_payloads[supervision["turn_role"]],
            encoding="utf-8",
        )
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"observability only",
            stderr=b"",
            duration_ms=1,
        )

    monkeypatch.setattr(
        "orchestrator.workflow.executor.ProviderObservationManager",
        manager_factory,
    )
    monkeypatch.setattr(ProviderExecutor, "prepare_invocation", prepare_invocation)
    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)
    return runtime


def _assert_closed_observations(
    runtime: _FakeProviderRuntime,
    *,
    expected_count: int = 2,
) -> None:
    [manager] = runtime.managers
    assert manager.closed is True
    assert len(manager.handles) == expected_count
    assert all(handle.finalized for handle in manager.handles)


def _assert_atomic_failure(
    workspace: Path,
    *,
    error_type: str,
    message: str,
) -> tuple[Path, dict[str, object]]:
    run_root, state = _only_run(workspace)
    assert state["status"] == "failed"
    assert state.get("current_step") is None
    assert state["workflow_outputs"] == {}
    assert state.get("artifact_versions", {}) == {}
    assert state.get("private_artifact_versions", {}) == {}
    [step] = state["steps"].values()
    assert step["status"] == "failed"
    assert step["error"] == {
        "type": error_type,
        "message": message,
    }
    assert not step.get("artifacts")
    return run_root, state


def _session_snapshot(
    *,
    terminal_seen: bool,
    status: str = "unique",
    session_ids: tuple[str, ...] = ("session-1",),
    resume_boundary_seen: bool = True,
) -> SessionIdentitySnapshot:
    return SessionIdentitySnapshot(
        status=status,
        session_ids=session_ids,
        terminal_seen=terminal_seen,
        error=None,
        resume_boundary_seen=resume_boundary_seen,
    )


def _terminal_proof(
    *,
    disposition: str,
    snapshot: SessionIdentitySnapshot,
    return_code: int,
    proof_complete: bool = True,
    final_identity_valid: bool = True,
    pgid_empty: bool = True,
    natural_exit_with_lingering_group: bool = False,
) -> ProviderCancellationResult:
    return ProviderCancellationResult(
        disposition=disposition,
        pgid=123,
        leader_return_code=return_code,
        leader_reaped=proof_complete,
        pgid_empty=pgid_empty,
        capture_threads_joined=proof_complete,
        execution_joined=proof_complete,
        final_session_snapshot=snapshot,
        final_identity_valid=final_identity_valid,
        proof_complete=proof_complete,
        term_sent=disposition == "cancelled",
        kill_sent=False,
        natural_exit_with_lingering_group=(
            natural_exit_with_lingering_group
        ),
    )


def test_public_compile_emits_one_atomic_provider_supervision_node(
    tmp_path: Path,
) -> None:
    files = _copy_fixture(tmp_path)

    built = build_frontend_bundle(_build_request(tmp_path, files))

    [node] = built.validated_bundle.ir.nodes.values()
    assert node.kind is ExecutableNodeKind.PROVIDER_SUPERVISION
    assert all(
        candidate.kind is not ExecutableNodeKind.PROVIDER
        for candidate in built.validated_bundle.ir.nodes.values()
    )


def test_public_run_completes_continue_settlement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)
    built = build_frontend_bundle(_build_request(tmp_path, files))

    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(monkeypatch)

    assert run_workflow(_run_args(files)) == 0

    run_root, state = _only_run(tmp_path)
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": "fresh-value"}
    [step] = state["steps"].values()
    assert step["status"] == "completed"
    assert step["artifacts"] == {"__result__": "fresh-value"}
    assert set(step["debug"]["provider_supervision"]) == {
        "directive_attempt",
        "selected_attempt",
    }
    assert {
        invocation.metadata["provider_supervision"]["turn_role"]
        for invocation in runtime.executed
    } == {"worker_fresh", "supervisor_directive"}
    _assert_closed_observations(runtime)

    snapshot = build_status_snapshot(
        built.validated_bundle,
        state,
        run_root,
    )
    [reported_step] = snapshot["steps"]
    assert reported_step["kind"] == "provider_supervision"
    assert reported_step["output"]["artifacts"] == {
        "__result__": "fresh-value"
    }
    attempt_debug = reported_step["output"]["debug"]["provider_supervision"]
    assert set(attempt_debug) == {"directive_attempt", "selected_attempt"}
    assert all(
        set(attempt_debug[key]) == {"ordinal", "scope_key"}
        for key in ("directive_attempt", "selected_attempt")
    )


def test_public_run_rejects_invalid_directive_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(
        monkeypatch,
        payloads={
            "supervisor_directive": (
                '{"variant":"CONTINUE","unexpected":true}'
            )
        },
    )

    assert run_workflow(_run_args(files)) == 1

    _assert_atomic_failure(
        tmp_path,
        error_type="provider_supervision_directive_invalid",
        message=(
            "CONTINUE directive must be a closed object with keys "
            "['variant']"
        ),
    )
    assert len(runtime.executed) == 2
    _assert_closed_observations(runtime)


def test_public_run_rejects_stale_provisional_bundle_before_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)
    original_derive = WorkflowProviderSupervisionBindings.derive_turn_bindings

    def inject_stale_preimage(
        self: WorkflowProviderSupervisionBindings,
        *,
        config: object,
        visit_count: int,
    ) -> object:
        relative = config.paths.worker_resume.provisional_bundle_relpath.replace(
            "{visit}",
            str(visit_count),
        )
        stale_path = Path(self.executor.state_manager.run_root) / relative
        stale_path.parent.mkdir(parents=True, exist_ok=True)
        stale_path.write_text('"stale-value"', encoding="utf-8")
        return original_derive(
            self,
            config=config,
            visit_count=visit_count,
        )

    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(monkeypatch)
    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "derive_turn_bindings",
        inject_stale_preimage,
    )

    assert run_workflow(_run_args(files)) == 1

    run_root, _state = _assert_atomic_failure(
        tmp_path,
        error_type="provider_supervision_failed",
        message="provider supervision provisional path preimage exists",
    )
    assert runtime.prepared == []
    assert runtime.executed == []
    assert runtime.managers == []
    assert list(run_root.rglob("evidence.json")) == []


def test_public_run_rejects_settlement_evaluation_failure_without_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)

    def fail_settlement(*_args: object, **_kwargs: object) -> object:
        raise ValueError("injected settlement evaluation failure")

    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(monkeypatch)
    monkeypatch.setattr(
        "orchestrator.workflow.provider_supervision.bindings.evaluate_pure_expr",
        fail_settlement,
    )

    assert run_workflow(_run_args(files)) == 1

    _assert_atomic_failure(
        tmp_path,
        error_type="provider_supervision_failed",
        message="injected settlement evaluation failure",
    )
    assert len(runtime.executed) == 2
    _assert_closed_observations(runtime)


def test_public_run_steers_and_selects_exact_resumed_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(monkeypatch)
    controls: dict[str, _ScriptedControl] = {}
    output_paths: dict[str, Path] = {}

    def create_control(
        _self: WorkflowProviderSupervisionBindings,
        turn: object,
    ) -> _ScriptedControl:
        control = _ScriptedControl(
            snapshot=(
                _session_snapshot(terminal_seen=False)
                if turn.turn_role == "worker_fresh"
                else None
            )
        )
        controls[turn.turn_role] = control
        return control

    def execute_provider(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **kwargs: object,
    ) -> ProviderExecutionResult:
        control = kwargs["control"]
        assert isinstance(control, _ScriptedControl)
        role = invocation.metadata["provider_supervision"]["turn_role"]
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        output_paths[role] = output_path
        with runtime.lock:
            runtime.executed.append(invocation)
        try:
            if role == "worker_fresh":
                assert control.cancel_requested.wait(timeout=1)
                control.terminal_result = _terminal_proof(
                    disposition="cancelled",
                    snapshot=_session_snapshot(terminal_seen=False),
                    return_code=-15,
                )
                return ProviderExecutionResult(
                    exit_code=-15,
                    stdout=b"",
                    stderr=b"",
                    duration_ms=1,
                    classification="cancelled_provisional",
                )
            if role == "supervisor_directive":
                output_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                control.terminal_result = _terminal_proof(
                    disposition="natural_exit",
                    snapshot=_session_snapshot(terminal_seen=True),
                    return_code=0,
                )
                return ProviderExecutionResult(0, b"", b"", 1)

            assert role == "worker_resume"
            assert invocation.session_request == ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="session-1",
            )
            output_path.write_text('"resumed-value"', encoding="utf-8")
            terminal_snapshot = _session_snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _terminal_proof(
                disposition="natural_exit",
                snapshot=terminal_snapshot,
                return_code=0,
            )
            return ProviderExecutionResult(0, b"", b"", 1)
        finally:
            control.execution_done.set()

    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "create_control",
        create_control,
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)

    assert run_workflow(_run_args(files)) == 0

    _run_root, state = _only_run(tmp_path)
    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"__result__": "resumed-value"}
    [step] = state["steps"].values()
    assert step["artifacts"] == {"__result__": "resumed-value"}
    assert set(output_paths) == {
        "worker_fresh",
        "supervisor_directive",
        "worker_resume",
    }
    assert not output_paths["worker_fresh"].exists()
    assert controls["worker_fresh"].cancel_and_reap_calls == 1
    allocations = state["provider_attempt_allocations"]
    assert len(allocations) == 3
    selected = step["debug"]["provider_supervision"]["selected_attempt"]
    assert selected["scope_key"] in allocations
    resume_invocation = next(
        invocation
        for invocation in runtime.executed
        if invocation.metadata["provider_supervision"]["turn_role"]
        == "worker_resume"
    )
    assert selected == {
        "scope_key": resume_invocation.metadata["provider_supervision"][
            "attempt_scope_key"
        ],
        "ordinal": allocations[selected["scope_key"]][
            "last_allocated_ordinal"
        ],
    }
    _assert_closed_observations(runtime, expected_count=3)


@pytest.mark.parametrize(
    ("failure_mode", "expected_cancel_calls", "expected_message"),
    (
        pytest.param(
            "missing_identity",
            0,
            "worker resume boundary is not eligible",
            id="missing-identity",
        ),
        pytest.param(
            "lingering_child",
            1,
            "worker final resume boundary is not eligible",
            id="lingering-child",
        ),
    ),
)
def test_public_run_rejects_unusable_steer_resume_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_mode: str,
    expected_cancel_calls: int,
    expected_message: str,
) -> None:
    files = _copy_fixture(tmp_path)
    monkeypatch.chdir(tmp_path)
    runtime = _install_fake_provider_runtime(monkeypatch)
    controls: dict[str, _ScriptedControl] = {}

    def create_control(
        _self: WorkflowProviderSupervisionBindings,
        turn: object,
    ) -> _ScriptedControl:
        snapshot = None
        if turn.turn_role == "worker_fresh":
            snapshot = (
                _session_snapshot(
                    terminal_seen=True,
                    status="missing",
                    session_ids=(),
                    resume_boundary_seen=False,
                )
                if failure_mode == "missing_identity"
                else _session_snapshot(terminal_seen=False)
            )
        control = _ScriptedControl(snapshot=snapshot)
        controls[turn.turn_role] = control
        return control

    def execute_provider(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **kwargs: object,
    ) -> ProviderExecutionResult:
        control = kwargs["control"]
        assert isinstance(control, _ScriptedControl)
        role = invocation.metadata["provider_supervision"]["turn_role"]
        output_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        with runtime.lock:
            runtime.executed.append(invocation)
        try:
            if role == "supervisor_directive":
                output_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                control.terminal_result = _terminal_proof(
                    disposition="natural_exit",
                    snapshot=_session_snapshot(terminal_seen=True),
                    return_code=0,
                )
                return ProviderExecutionResult(0, b"", b"", 1)

            assert role == "worker_fresh"
            if failure_mode == "missing_identity":
                missing = _session_snapshot(
                    terminal_seen=True,
                    status="missing",
                    session_ids=(),
                    resume_boundary_seen=False,
                )
                control.session_snapshot = missing
                control.terminal_result = _terminal_proof(
                    disposition="natural_exit",
                    snapshot=missing,
                    return_code=0,
                    final_identity_valid=False,
                )
                return ProviderExecutionResult(0, b"", b"", 1)

            assert control.cancel_requested.wait(timeout=1)
            control.terminal_result = _terminal_proof(
                disposition="cancelled",
                snapshot=_session_snapshot(terminal_seen=False),
                return_code=-15,
                proof_complete=False,
                final_identity_valid=False,
                pgid_empty=False,
                natural_exit_with_lingering_group=True,
            )
            return ProviderExecutionResult(
                exit_code=-15,
                stdout=b"",
                stderr=b"",
                duration_ms=1,
                classification="cancelled_provisional",
            )
        finally:
            control.execution_done.set()

    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "create_control",
        create_control,
    )
    monkeypatch.setattr(ProviderExecutor, "execute", execute_provider)

    assert run_workflow(_run_args(files)) == 1

    _run_root, state = _assert_atomic_failure(
        tmp_path,
        error_type="provider_supervision_resume_boundary_invalid",
        message=expected_message,
    )
    assert {
        invocation.metadata["provider_supervision"]["turn_role"]
        for invocation in runtime.executed
    } == {"worker_fresh", "supervisor_directive"}
    assert len(state["provider_attempt_allocations"]) == 2
    assert controls["worker_fresh"].cancel_and_reap_calls == (
        expected_cancel_calls
    )
    _assert_closed_observations(runtime)


def test_public_resume_quarantines_interrupted_visit_before_provider_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = _copy_fixture(tmp_path)
    original_derive = WorkflowProviderSupervisionBindings.derive_turn_bindings
    launches: list[str] = []

    def crash_after_running_visit(
        _self: WorkflowProviderSupervisionBindings,
        *,
        config: object,
        visit_count: int,
    ) -> object:
        del config, visit_count
        raise _InjectedControllerCrash

    def unexpected_provider_launch(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: object,
    ) -> ProviderExecutionResult:
        launches.append(
            invocation.metadata["provider_supervision"]["turn_role"]
        )
        raise AssertionError(
            "interrupted visit quarantine must precede provider launch"
        )

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", _run_argv(files))
    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "derive_turn_bindings",
        crash_after_running_visit,
    )
    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        unexpected_provider_launch,
    )

    with pytest.raises(_InjectedControllerCrash):
        run_workflow(_run_args(files))

    run_root, interrupted = _only_run(tmp_path)
    run_id = run_root.name
    current_step = interrupted["current_step"]
    assert interrupted["status"] == "running"
    assert current_step["status"] == "running"
    assert current_step["type"] == "provider_supervision"
    assert current_step["visit_count"] == 1
    assert launches == []

    monkeypatch.setattr(
        WorkflowProviderSupervisionBindings,
        "derive_turn_bindings",
        original_derive,
    )

    assert resume_workflow(run_id=run_id, force_restart=False) == 1

    _run_root, quarantined = _only_run(tmp_path)
    assert quarantined["status"] == "failed"
    assert quarantined.get("current_step") is None
    error = quarantined["error"]
    assert error["type"] == (
        "provider_supervision_interrupted_visit_quarantined"
    )
    assert error["context"]["step_id"] == current_step["step_id"]
    assert error["context"]["visit_count"] == current_step["visit_count"]
    metadata_path = Path(error["context"]["metadata_path"])
    if not metadata_path.is_absolute():
        metadata_path = tmp_path / metadata_path
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert metadata["status"] == "interrupted"
    assert metadata["publication_state"] == (
        "quarantined_interrupted_visit"
    )
    assert launches == []

    frozen_error = json.loads(json.dumps(error))
    assert resume_workflow(run_id=run_id, force_restart=False) == 1
    _run_root, repeated = _only_run(tmp_path)
    assert repeated["error"] == frozen_error
    assert repeated.get("current_step") is None
    assert launches == []
