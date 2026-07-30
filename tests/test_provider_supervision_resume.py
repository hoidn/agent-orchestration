"""Pure resume-boundary eligibility tests for provider supervision."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
import logging
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import threading
import time
from typing import Any

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.providers.control import ProviderCancellationResult
from orchestrator.providers.executor import ProviderExecutionResult
from orchestrator.providers.session_transport import SessionIdentitySnapshot
from orchestrator.providers.types import (
    InputMode,
    ProviderInvocation,
    ProviderSessionMode,
    ProviderSessionRequest,
)
from orchestrator.workflow.executable_ir import WorkflowRegion
from orchestrator.workflow.provider_supervision.bindings import (
    ProviderSupervisionAttemptBinding,
    ProviderSupervisionInvocationSnapshot,
    ProviderSupervisionMemberRequest,
    ProviderSupervisionObservationBinding,
    ProviderSupervisionObservationInjection,
    ProviderSupervisionTurnBinding,
)
from orchestrator.workflow.provider_supervision.coordinator import (
    ProviderSupervisionCoordinator,
)
from orchestrator.workflow.provider_supervision import models as supervision_models
from orchestrator.workflow.resume_planner import ResumePlanner
from orchestrator.workflow.state_projection import (
    CompatibilityNodeProjection,
    CompatibilityStepDefinition,
    WorkflowStateProjection,
)


def _ml1_supervision_projection(
    report_kind: str = "provider_supervision",
) -> WorkflowStateProjection:
    entry = CompatibilityNodeProjection(
        node_id="root.live",
        step_id="root.live",
        presentation_key="Live",
        display_name="Live",
        region=WorkflowRegion.BODY,
        compatibility_index=0,
        step_definition=CompatibilityStepDefinition(
            report_kind=report_kind,
        ),
    )
    return WorkflowStateProjection(
        entries_by_node_id=MappingProxyType({"root.live": entry}),
        node_id_by_compatibility_index=MappingProxyType({0: "root.live"}),
        compatibility_index_by_node_id=MappingProxyType({"root.live": 0}),
        presentation_key_by_node_id=MappingProxyType({"root.live": "Live"}),
        node_id_by_step_id=MappingProxyType({"root.live": "root.live"}),
    )


def _ml1_running_supervision_state(
    *,
    result: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "status": "running",
        "steps": {} if result is None else {"Live": result},
        "current_step": {
            "name": "Live",
            "index": 0,
            "type": "provider_supervision",
            "status": "running",
            "step_id": "root.live",
            "visit_count": 2,
        },
    }


def test_interrupted_supervision_visit_requests_fresh_rerun_disposition() -> None:
    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        _ml1_running_supervision_state(),
        projection=_ml1_supervision_projection(),
    )

    assert (guard or {}).get("kind") == "rerun_interrupted_visit"


def test_interrupted_supervision_at_least_once_does_not_claim_completed_same_visit(
) -> None:
    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        _ml1_running_supervision_state(
            result={
                "status": "completed",
                "step_id": "root.live",
                "visit_count": 2,
            }
        ),
        projection=_ml1_supervision_projection(),
    )

    assert guard is None


def test_interrupted_supervision_at_least_once_projection_mismatch_is_integrity_error_before_launch(
) -> None:
    state = _ml1_running_supervision_state()
    current_step = state["current_step"]
    assert isinstance(current_step, dict)
    current_step["type"] = "provider"

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        state,
        projection=_ml1_supervision_projection(),
    )

    assert (guard or {}).get("kind") == "integrity_error"


def test_interrupted_supervision_at_least_once_legacy_quarantine_marker_is_distinct(
) -> None:
    error = {
        "type": "provider_supervision_interrupted_visit_quarantined",
        "message": "historical sticky quarantine",
        "context": {
            "step_name": "Live",
            "step_id": "root.live",
            "visit_count": 2,
        },
    }

    guard = ResumePlanner().detect_interrupted_provider_supervision_visit(
        {"status": "failed", "error": error},
        projection=_ml1_supervision_projection(),
    )

    assert guard == {"kind": "existing_quarantine", "error": error}


def _snapshot(
    *,
    status: str = "unique",
    session_ids: tuple[str, ...] = ("session-1",),
    resume_boundary_seen: bool = True,
    terminal_seen: bool = False,
    error: dict[str, object] | None = None,
) -> SessionIdentitySnapshot:
    return SessionIdentitySnapshot(
        status=status,
        session_ids=session_ids,
        terminal_seen=terminal_seen,
        error=error,
        resume_boundary_seen=resume_boundary_seen,
    )


def _terminal_proof(
    *,
    snapshot: SessionIdentitySnapshot | None = None,
    disposition: str = "natural_exit",
    leader_return_code: int | None = 0,
    proof_complete: bool = True,
    natural_exit_with_lingering_group: bool = False,
) -> ProviderCancellationResult:
    return ProviderCancellationResult(
        disposition=disposition,
        pgid=123,
        leader_return_code=leader_return_code,
        leader_reaped=proof_complete,
        pgid_empty=proof_complete,
        capture_threads_joined=proof_complete,
        execution_joined=proof_complete,
        final_session_snapshot=(
            snapshot
            if snapshot is not None
            else _snapshot(terminal_seen=True)
        ),
        final_identity_valid=proof_complete,
        proof_complete=proof_complete,
        term_sent=disposition == "cancelled",
        kill_sent=False,
        natural_exit_with_lingering_group=(
            natural_exit_with_lingering_group
        ),
    )


def _classify(
    *,
    snapshot: SessionIdentitySnapshot | None,
    terminal_proof: ProviderCancellationResult | None = None,
    execution_promotable: bool | None = None,
    member_deadline_live: bool = True,
    whole_deadline_live: bool = True,
):
    return supervision_models.classify_provider_supervision_resume_boundary(
        snapshot=snapshot,
        terminal_proof=terminal_proof,
        execution_promotable=execution_promotable,
        member_deadline_live=member_deadline_live,
        whole_deadline_live=whole_deadline_live,
    )


def test_supervision_invocation_snapshot_preserves_resume_capability() -> None:
    invocation = ProviderInvocation(
        command=["provider"],
        input_mode=InputMode.STDIN,
        prompt="prompt",
        output_file=None,
        env={},
        timeout_sec=30,
        command_variant="fresh_command",
        metadata_mode="codex_jsonl",
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
        terminate_process_tree=True,
        metadata={},
        turn_boundary_resume=True,
    )

    materialized = ProviderSupervisionInvocationSnapshot.from_invocation(
        invocation
    ).materialize()

    assert materialized.turn_boundary_resume is True


def test_active_resume_boundary_requires_unique_marker_preterminal_and_live_deadlines() -> None:
    assessment = _classify(snapshot=_snapshot())

    assert assessment.outcome == "active_eligible"
    assert assessment.session_id == "session-1"


def test_clean_natural_resume_boundary_requires_complete_terminal_success() -> None:
    terminal_snapshot = _snapshot(terminal_seen=True)

    assessment = _classify(
        snapshot=terminal_snapshot,
        terminal_proof=_terminal_proof(snapshot=terminal_snapshot),
        execution_promotable=True,
        member_deadline_live=False,
    )

    assert assessment.outcome == "clean_natural_eligible"
    assert assessment.session_id == "session-1"


def test_cancelled_active_boundary_after_member_deadline_is_timeout() -> None:
    proof = _cancelled_proof()

    assessment = _classify(
        snapshot=proof.final_session_snapshot,
        terminal_proof=proof,
        execution_promotable=False,
        member_deadline_live=False,
        whole_deadline_live=True,
    )

    assert assessment.outcome == "timeout"
    assert assessment.session_id is None


@pytest.mark.parametrize(
    ("snapshot", "member_deadline_live", "expected"),
    [
        (_snapshot(status="missing", session_ids=()), True, "wait"),
        (
            _snapshot(
                status="ambiguous",
                session_ids=("session-1", "session-2"),
            ),
            True,
            "reject",
        ),
        (
            _snapshot(
                status="invalid",
                session_ids=("session-1",),
                error={"type": "provider_session_transport_error"},
            ),
            True,
            "reject",
        ),
        (_snapshot(resume_boundary_seen=False), True, "wait"),
        (_snapshot(terminal_seen=True), False, "wait"),
    ],
)
def test_active_resume_boundary_refuses_unusable_identity_or_marker(
    snapshot: SessionIdentitySnapshot,
    member_deadline_live: bool,
    expected: str,
) -> None:
    assessment = _classify(
        snapshot=snapshot,
        member_deadline_live=member_deadline_live,
    )

    assert assessment.outcome == expected
    assert assessment.session_id is None


@pytest.mark.parametrize(
    ("terminal_proof", "execution_promotable"),
    [
        (
            _terminal_proof(
                snapshot=_snapshot(
                    status="invalid",
                    terminal_seen=True,
                    error={"type": "provider_session_turn_failed"},
                ),
            ),
            False,
        ),
        (
            _terminal_proof(
                snapshot=_snapshot(terminal_seen=True),
                leader_return_code=3,
            ),
            False,
        ),
        (
            _terminal_proof(
                snapshot=_snapshot(terminal_seen=True),
                proof_complete=False,
            ),
            True,
        ),
        (
            replace(
                _terminal_proof(snapshot=_snapshot(terminal_seen=True)),
                natural_exit_with_lingering_group=True,
            ),
            True,
        ),
        (
            _terminal_proof(snapshot=_snapshot(terminal_seen=False)),
            True,
        ),
    ],
)
def test_clean_natural_resume_boundary_rejects_failed_or_incomplete_terminal_proof(
    terminal_proof: ProviderCancellationResult,
    execution_promotable: bool,
) -> None:
    assessment = _classify(
        snapshot=terminal_proof.final_session_snapshot,
        terminal_proof=terminal_proof,
        execution_promotable=execution_promotable,
    )

    assert assessment.outcome == "reject"
    assert assessment.session_id is None


@pytest.mark.parametrize(
    ("terminal", "member_live", "whole_live"),
    [
        (False, False, True),
        (False, True, False),
        (True, True, False),
    ],
)
def test_resume_boundary_deadline_expiry_wins_for_the_applicable_branch(
    terminal: bool,
    member_live: bool,
    whole_live: bool,
) -> None:
    snapshot = _snapshot(terminal_seen=terminal)
    terminal_proof = (
        _terminal_proof(snapshot=snapshot)
        if terminal
        else None
    )

    assessment = _classify(
        snapshot=snapshot,
        terminal_proof=terminal_proof,
        execution_promotable=True if terminal else None,
        member_deadline_live=member_live,
        whole_deadline_live=whole_live,
    )

    assert assessment.outcome == "timeout"
    assert assessment.session_id is None


def test_result_before_reraises_timeout_error_from_completed_member() -> None:
    future: Future[Any] = Future()
    member_error = TimeoutError("member callable timed out internally")
    future.set_exception(member_error)
    now = time.monotonic()

    with pytest.raises(TimeoutError) as raised:
        ProviderSupervisionCoordinator._result_before(
            future,
            now + 1,
            whole_deadline=now + 2,
            code="provider_supervision_supervisor_timeout",
        )

    assert raised.value is member_error


class _Observation:
    def __init__(self, tmp_path: Path, role: str) -> None:
        self.socket_path = tmp_path / "observation.sock"
        self.target = f"pane:{role}"


class _ScriptedControl:
    def __init__(
        self,
        *,
        snapshot: SessionIdentitySnapshot | None = None,
        terminal_result: ProviderCancellationResult | None = None,
    ) -> None:
        self.session_snapshot = snapshot
        self.terminal_result = terminal_result
        self.cancel_requested = threading.Event()
        self.execution_done = threading.Event()
        self.future: Future[Any] | None = None

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
        self.cancel_requested.set()
        assert self.execution_done.wait(timeout=1)
        assert self.terminal_result is not None
        return self.terminal_result


def _natural_proof(
    *,
    snapshot: SessionIdentitySnapshot | None = None,
) -> ProviderCancellationResult:
    return ProviderCancellationResult(
        disposition="natural_exit",
        pgid=123,
        leader_return_code=0,
        leader_reaped=True,
        pgid_empty=True,
        capture_threads_joined=True,
        execution_joined=True,
        final_session_snapshot=snapshot,
        final_identity_valid=True,
        proof_complete=True,
        term_sent=False,
        kill_sent=False,
        natural_exit_with_lingering_group=False,
    )


def _cancelled_proof() -> ProviderCancellationResult:
    return ProviderCancellationResult(
        disposition="cancelled",
        pgid=123,
        leader_return_code=-15,
        leader_reaped=True,
        pgid_empty=True,
        capture_threads_joined=True,
        execution_joined=True,
        final_session_snapshot=_snapshot(),
        final_identity_valid=True,
        proof_complete=True,
        term_sent=True,
        kill_sent=False,
        natural_exit_with_lingering_group=False,
    )


class _EarlyArbitrationBindings:
    def __init__(
        self,
        tmp_path: Path,
        *,
        directive: dict[str, Any],
        worker_completes_naturally: bool,
        worker_delay: float = 0.0,
        supervisor_delay: float = 0.0,
    ) -> None:
        self.tmp_path = tmp_path
        self.directive = directive
        self.worker_completes_naturally = worker_completes_naturally
        self.worker_delay = worker_delay
        self.supervisor_delay = supervisor_delay
        self.events: list[str] = []
        self._lock = threading.Lock()
        self.controls: dict[str, _ScriptedControl] = {}
        self.requests: dict[str, ProviderSupervisionMemberRequest] = {}
        self.attempt_roles: list[str] = []
        self.blocked_roles: set[str] = set()
        self._active_roles: set[str] = set()

    def _record(self, event: str) -> None:
        with self._lock:
            self.events.append(event)

    def assert_current_step(self, **_kwargs: Any) -> None:
        self._record("current_step")

    def derive_turn_bindings(
        self,
        *,
        config: Any,
        visit_count: int,
    ) -> dict[str, ProviderSupervisionTurnBinding]:
        del visit_count
        return {
            role: ProviderSupervisionTurnBinding(
                member_id=member.member_id,
                turn_role=role,
                runtime_step_id=f"{config.node_id}:{role}",
                evidence_path=self.tmp_path / role / "evidence.json",
                provisional_bundle_path=(
                    self.tmp_path / role / "provisional.json"
                ),
            )
            for role, member in (
                ("worker_fresh", config.worker),
                ("supervisor_directive", config.supervisor),
            )
        }

    def derive_resume_turn_binding(
        self,
        *,
        config: Any,
        visit_count: int,
    ) -> ProviderSupervisionTurnBinding:
        del visit_count
        return ProviderSupervisionTurnBinding(
            member_id=config.worker.member_id,
            turn_role="worker_resume",
            runtime_step_id=f"{config.node_id}:worker_resume",
            evidence_path=self.tmp_path / "worker_resume" / "evidence.json",
            provisional_bundle_path=(
                self.tmp_path / "worker_resume" / "provisional.json"
            ),
        )

    def open_observation(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding:
        handle = _Observation(self.tmp_path, turn.turn_role)
        return ProviderSupervisionObservationBinding(
            member_id=turn.member_id,
            turn_role=turn.turn_role,
            socket_path=handle.socket_path.resolve(),
            target=handle.target,
            handle=handle,
        )

    def compose_prompt(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        observation_injection: ProviderSupervisionObservationInjection | None,
    ) -> str:
        del member, observation_injection
        return f"prompt:{turn.turn_role}"

    def compose_resume_prompt(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        guidance: str,
    ) -> str:
        del member, turn
        self._record("resume_prompt")
        return guidance

    def allocate_attempt(
        self,
        *,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderSupervisionAttemptBinding:
        del prompt
        self.attempt_roles.append(turn.turn_role)
        return ProviderSupervisionAttemptBinding(
            scope_key=f"scope:{turn.turn_role}",
            ordinal=1,
            snapshot_key=f"snapshot:{turn.turn_role}",
        )

    def prepare_invocation(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
    ) -> ProviderInvocation:
        del member
        return ProviderInvocation(
            command=["provider", turn.turn_role],
            input_mode=InputMode.STDIN,
            prompt=prompt,
        )

    def prepare_resume_invocation(
        self,
        *,
        member: Any,
        turn: ProviderSupervisionTurnBinding,
        prompt: str,
        session_id: str,
    ) -> ProviderInvocation:
        del member
        return ProviderInvocation(
            command=["provider", turn.turn_role],
            input_mode=InputMode.STDIN,
            prompt=prompt,
            env={
                "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(
                    turn.provisional_bundle_path
                )
            },
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id=session_id,
            ),
        )

    def create_control(
        self,
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        if turn.turn_role == "worker_fresh":
            control = _ScriptedControl(snapshot=_snapshot())
        elif turn.turn_role == "worker_resume":
            control = _ScriptedControl()
        else:
            control = _ScriptedControl()
        self.controls[turn.turn_role] = control
        return control

    def execute_member(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        self.requests[role] = request
        self._record(f"{role}:start")
        with self._lock:
            self._active_roles.add(role)
        control = request.control
        if role in self.blocked_roles:
            assert control.cancel_requested.wait(timeout=1)
            control.terminal_result = _cancelled_proof()
            result = ProviderExecutionResult(
                -15,
                b"",
                b"",
                0,
                classification="cancelled_provisional",
            )
        elif role == "supervisor_directive":
            time.sleep(self.supervisor_delay)
            result = ProviderExecutionResult(0, b"", b"", 0)
            control.terminal_result = _natural_proof()
        elif role == "worker_fresh" and self.worker_completes_naturally:
            time.sleep(self.worker_delay)
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            result = ProviderExecutionResult(0, b"", b"", 0)
        elif role == "worker_fresh":
            assert control.cancel_requested.wait(timeout=1)
            control.terminal_result = _cancelled_proof()
            self._record("worker_fresh:cancelled")
            result = ProviderExecutionResult(
                -15,
                b"",
                b"",
                0,
                classification="cancelled_provisional",
            )
        else:
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            result = ProviderExecutionResult(0, b"", b"", 0)
        with self._lock:
            self._active_roles.remove(role)
        control.execution_done.set()
        self._record(f"{role}:end")
        return result

    def observation_is_healthy(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> bool:
        del observation
        return True

    def validate_member_bundle(
        self,
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        role = request.turn.turn_role
        self._record(f"{role}:validate")
        if role == "supervisor_directive":
            return self.directive
        if role == "worker_resume":
            return "resumed"
        return "fresh"

    def evaluate_settlement(
        self,
        *,
        config: Any,
        resolved_bindings: dict[str, Any],
    ) -> Any:
        return resolved_bindings[config.worker.member_id]

    def validate_settlement(self, *, config: Any, value: Any) -> Any:
        del config
        return value

    def finalize_settlement(
        self,
        *,
        selected_request: ProviderSupervisionMemberRequest,
        settlement_value: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        self._record("finalize")
        return {
            "status": "completed",
            "selected_role": selected_request.turn.turn_role,
            "value": settlement_value,
        }

    def close_observation(
        self,
        observation: ProviderSupervisionObservationBinding,
    ) -> None:
        self._record(f"{observation.turn_role}:close")

    def failure_result(self, *, code: str, message: str) -> dict[str, Any]:
        del message
        with self._lock:
            active_count = len(self._active_roles)
        self._record(f"failure_active:{active_count}")
        self._record("failure_result")
        return {"status": "failed", "error": {"type": code}}


def _coordinator_config(
    *,
    whole_timeout: float = 1,
    worker_timeout: float = 1,
    supervisor_timeout: float = 1,
    max_steers: int = 1,
) -> Any:
    return SimpleNamespace(
        node_id="root.live",
        common=SimpleNamespace(timeout_sec=whole_timeout),
        worker=SimpleNamespace(
            member_id="worker",
            timeout_sec=worker_timeout,
        ),
        supervisor=SimpleNamespace(
            member_id="supervisor",
            timeout_sec=supervisor_timeout,
        ),
        max_steers=max_steers,
    )


def test_invalid_directive_cancels_and_joins_worker_before_failure_publication(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "INVALID"},
        worker_completes_naturally=False,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert bindings.events.index("supervisor_directive:validate") < (
        bindings.events.index("worker_fresh:cancelled")
    )
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_result")
    )


def test_unexpected_supervisor_exception_cleans_worker_before_failure_result(
    tmp_path: Path,
) -> None:
    class UnexpectedSupervisorFailure(Exception):
        pass

    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "CONTINUE"},
        worker_completes_naturally=False,
    )
    worker_started = threading.Event()
    cancelled_before_worker_exit: list[bool] = []

    def execute_with_unexpected_supervisor_failure(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert worker_started.wait(timeout=1)
            raise UnexpectedSupervisorFailure("unexpected supervisor failure")

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        worker_started.set()
        control = request.control
        cancelled = control.cancel_requested.wait(timeout=0.1)
        cancelled_before_worker_exit.append(cancelled)
        if cancelled:
            control.terminal_result = _cancelled_proof()
            result = ProviderExecutionResult(
                exit_code=-15,
                stdout=b"",
                stderr=b"",
                duration_ms=0,
                classification="cancelled_provisional",
            )
        else:
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            result = ProviderExecutionResult(0, b"", b"", 0)
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        execute_with_unexpected_supervisor_failure
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_failed"
    assert cancelled_before_worker_exit == [True]
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_result")
    )
    assert "failure_active:0" in bindings.events
    assert "finalize" not in bindings.events


def test_incomplete_cleanup_proof_blocks_terminal_failure_publication(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "INVALID"},
        worker_completes_naturally=False,
    )
    create_control = bindings.create_control

    def create_control_with_incomplete_cleanup(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            cancel_and_reap = control.cancel_and_reap

            def return_incomplete_cleanup(
                grace: float,
            ) -> ProviderCancellationResult:
                proof = cancel_and_reap(grace)
                incomplete = replace(
                    proof,
                    pgid_empty=False,
                    proof_complete=False,
                    error="provider process group is not empty",
                )
                control.terminal_result = incomplete
                return incomplete

            control.cancel_and_reap = (  # type: ignore[method-assign]
                return_incomplete_cleanup
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_control_with_incomplete_cleanup
    )

    with pytest.raises(RuntimeError, match="cleanup"):
        ProviderSupervisionCoordinator(bindings).run(
            _coordinator_config(),
            step_name="Live",
            visit_count=1,
        )

    assert "worker_fresh:end" in bindings.events
    assert "failure_result" not in bindings.events
    assert "finalize" not in bindings.events
    assert "worker_fresh:close" in bindings.events
    assert "supervisor_directive:close" in bindings.events


def test_nonjoining_cleanup_times_out_without_failure_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    cleanup_timeout_sec = 0.02
    monkeypatch.setattr(
        coordinator_module,
        "_CLEANUP_TIMEOUT_SEC",
        cleanup_timeout_sec,
        raising=False,
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "INVALID"},
        worker_completes_naturally=False,
    )
    release_worker = threading.Event()
    worker_started = threading.Event()
    cancel_and_reap_started = threading.Event()
    create_control = bindings.create_control

    def create_nonjoining_worker_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":

            def nonjoining_cancel_and_reap(
                grace: float,
            ) -> ProviderCancellationResult:
                del grace
                control.cancel_requested.set()
                cancel_and_reap_started.set()
                assert release_worker.wait(timeout=2)
                assert control.execution_done.wait(timeout=1)
                assert control.terminal_result is not None
                return control.terminal_result

            control.cancel_and_reap = (  # type: ignore[method-assign]
                nonjoining_cancel_and_reap
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_nonjoining_worker_control
    )
    execute_member = bindings.execute_member

    def execute_with_nonjoining_worker(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert worker_started.wait(timeout=1)
            return execute_member(request)
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        worker_started.set()
        assert release_worker.wait(timeout=2)
        control = request.control
        control.terminal_result = _cancelled_proof()
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return ProviderExecutionResult(
            exit_code=-15,
            stdout=b"",
            stderr=b"",
            duration_ms=0,
            classification="cancelled_provisional",
        )

    bindings.execute_member = (  # type: ignore[method-assign]
        execute_with_nonjoining_worker
    )
    outcome: dict[str, Any] = {}
    coordinator_done = threading.Event()

    def run_coordinator() -> None:
        try:
            outcome["result"] = ProviderSupervisionCoordinator(
                bindings
            ).run(
                _coordinator_config(),
                step_name="Live",
                visit_count=1,
            )
        except BaseException as exc:
            outcome["error"] = exc
        finally:
            coordinator_done.set()

    coordinator_thread = threading.Thread(
        target=run_coordinator,
        name="nonjoining-cleanup-test",
        daemon=True,
    )
    coordinator_thread.start()
    cleanup_started = False
    completed_within_budget = False
    try:
        cleanup_started = cancel_and_reap_started.wait(timeout=1)
        if cleanup_started:
            completed_within_budget = coordinator_done.wait(
                timeout=cleanup_timeout_sec + 0.1
            )
    finally:
        release_worker.set()
        coordinator_thread.join(timeout=2)

    assert cleanup_started
    assert completed_within_budget
    assert not coordinator_thread.is_alive()
    assert isinstance(outcome.get("error"), RuntimeError)
    assert "cleanup" in str(outcome["error"]).lower()
    assert "failure_result" not in bindings.events
    assert "finalize" not in bindings.events


def test_early_steer_cancels_active_worker_and_selects_resumed_turn(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    assert bindings.events.index("supervisor_directive:validate") < (
        bindings.events.index("worker_fresh:cancelled")
    )
    assert "worker_fresh:validate" not in bindings.events


def test_steer_resume_observation_allocation_failure_is_evidence_only(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    open_observation = bindings.open_observation

    def fail_only_resume_observation(
        turn: ProviderSupervisionTurnBinding,
    ) -> ProviderSupervisionObservationBinding:
        if turn.turn_role == "worker_resume":
            bindings._record("worker_resume:observation_failed")
            raise RuntimeError("resume observation unavailable")
        return open_observation(turn)

    bindings.open_observation = (  # type: ignore[method-assign]
        fail_only_resume_observation
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    resume_request = bindings.requests["worker_resume"]
    assert resume_request.observation is None
    resume_invocation = resume_request.invocation.materialize()
    assert resume_invocation.session_request == ProviderSessionRequest(
        mode=ProviderSessionMode.RESUME,
        session_id="session-1",
    )
    assert "worker_resume:observation_failed" in bindings.events
    assert "worker_fresh:validate" not in bindings.events
    assert "worker_fresh:close" in bindings.events
    assert "supervisor_directive:close" in bindings.events


def test_early_steer_waits_for_exact_resume_boundary_marker(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    marker_release = threading.Event()
    cancel_calls: list[str] = []
    create_control = bindings.create_control

    def create_control_without_initial_marker(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            control.session_snapshot = _snapshot(
                resume_boundary_seen=False,
            )
            cancel_and_reap = control.cancel_and_reap

            def record_cancel(
                grace: float,
            ) -> ProviderCancellationResult:
                cancel_calls.append(turn.turn_role)
                return cancel_and_reap(grace)

            control.cancel_and_reap = record_cancel  # type: ignore[method-assign]
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_control_without_initial_marker
    )
    execute_member = bindings.execute_member

    def publish_marker_after_supervisor_turn(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            result = execute_member(request)
            marker_release.set()
            return result
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        assert marker_release.wait(timeout=1)
        assert not control.cancel_requested.is_set()
        control.session_snapshot = _snapshot()
        bindings._record("worker_fresh:marker")
        assert control.cancel_requested.wait(timeout=1)
        control.terminal_result = _cancelled_proof()
        bindings._record("worker_fresh:cancelled")
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return ProviderExecutionResult(
            -15,
            b"",
            b"",
            0,
            classification="cancelled_provisional",
        )

    bindings.execute_member = (  # type: ignore[method-assign]
        publish_marker_after_supervisor_turn
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    assert cancel_calls == ["worker_fresh"]
    assert bindings.events.index("worker_fresh:marker") < (
        bindings.events.index("worker_fresh:cancelled")
    )
    assert "worker_fresh:validate" not in bindings.events


def test_early_steer_identity_without_marker_times_out_and_never_resumes(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    create_control = bindings.create_control

    def create_identity_only_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            control.session_snapshot = _snapshot(
                resume_boundary_seen=False,
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_identity_only_control
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(worker_timeout=0.02),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_worker_timeout"
    assert bindings.controls["worker_fresh"].cancel_requested.is_set()
    assert "worker_resume" not in bindings.requests
    assert bindings.events.index("worker_fresh:cancelled") < (
        bindings.events.index("worker_fresh:end")
    )
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_active:0")
    )
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_steer_uses_clean_natural_branch_when_terminal_wins_cancellation_race(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    execute_member = bindings.execute_member

    def complete_naturally_after_cancel_request(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        assert control.cancel_requested.wait(timeout=1)
        terminal_snapshot = _snapshot(terminal_seen=True)
        control.session_snapshot = terminal_snapshot
        control.terminal_result = _natural_proof(
            snapshot=terminal_snapshot,
        )
        bindings._record("worker_fresh:natural_terminal")
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return ProviderExecutionResult(0, b"", b"", 0)

    bindings.execute_member = (  # type: ignore[method-assign]
        complete_naturally_after_cancel_request
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    assert bindings.controls["worker_fresh"].cancel_requested.is_set()
    assert len(
        [
            request
            for role, request in bindings.requests.items()
            if role == "worker_resume"
        ]
    ) == 1
    resume_invocation = bindings.requests[
        "worker_resume"
    ].invocation.materialize()
    assert resume_invocation.session_request == ProviderSessionRequest(
        mode=ProviderSessionMode.RESUME,
        session_id="session-1",
    )
    assert "worker_fresh:natural_terminal" in bindings.events
    assert "worker_fresh:cancelled" not in bindings.events
    assert "worker_fresh:validate" not in bindings.events


def test_steer_cancel_before_bind_latches_until_worker_binds_and_terminalizes(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    lifecycle: list[str] = []

    class _NewThenBoundControl:
        def __init__(self) -> None:
            self.state = "NEW"
            self.session_snapshot = _snapshot()
            self.terminal_result: ProviderCancellationResult | None = None
            self.cancel_requested = threading.Event()
            self.bound = threading.Event()
            self.execution_done = threading.Event()
            self.future: Future[Any] | None = None

        def attach_execution_future(self, future: Future[Any]) -> None:
            self.future = future

        def request_cancel(
            self,
            *,
            reason: str = "external",
            grace: float | None = None,
        ) -> None:
            del reason, grace
            lifecycle.append("cancel_latched")
            self.cancel_requested.set()

        def cancel_and_reap(
            self,
            grace: float,
        ) -> ProviderCancellationResult:
            del grace
            if not self.cancel_requested.is_set():
                lifecycle.append("cancel_latched")
                self.cancel_requested.set()
            assert self.bound.wait(timeout=1)
            assert self.execution_done.wait(timeout=1)
            assert self.terminal_result is not None
            lifecycle.append("cancel_result")
            return self.terminal_result

    create_control = bindings.create_control

    def create_new_worker_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> Any:
        if turn.turn_role != "worker_fresh":
            return create_control(turn)
        control = _NewThenBoundControl()
        bindings.controls[turn.turn_role] = control  # type: ignore[assignment]
        return control

    bindings.create_control = create_new_worker_control  # type: ignore[method-assign]
    execute_member = bindings.execute_member

    def bind_only_after_cancel(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        assert control.state == "NEW"
        assert control.cancel_requested.wait(timeout=1)
        lifecycle.append("bind_after_cancel")
        control.state = "BOUND"
        control.bound.set()
        control.terminal_result = _cancelled_proof()
        lifecycle.append("terminal")
        control.state = "TERMINAL"
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return ProviderExecutionResult(
            -15,
            b"",
            b"",
            0,
            classification="cancelled_provisional",
        )

    bindings.execute_member = bind_only_after_cancel  # type: ignore[method-assign]

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    assert lifecycle == [
        "cancel_latched",
        "bind_after_cancel",
        "terminal",
        "cancel_result",
    ]
    resume_invocation = bindings.requests[
        "worker_resume"
    ].invocation.materialize()
    assert resume_invocation.session_request == ProviderSessionRequest(
        mode=ProviderSessionMode.RESUME,
        session_id="session-1",
    )
    assert "worker_fresh:validate" not in bindings.events


@pytest.mark.parametrize("identity_status", ["invalid", "ambiguous"])
def test_early_steer_rejects_invalid_or_ambiguous_active_identity(
    tmp_path: Path,
    identity_status: str,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    create_control = bindings.create_control

    def create_unusable_identity_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            control.session_snapshot = _snapshot(
                status=identity_status,
                session_ids=(
                    ("session-1", "session-2")
                    if identity_status == "ambiguous"
                    else ("session-1",)
                ),
                error=(
                    {"type": "provider_session_transport_error"}
                    if identity_status == "invalid"
                    else None
                ),
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_unusable_identity_control
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(
            whole_timeout=10,
            worker_timeout=10,
            supervisor_timeout=10,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_resume_boundary_invalid"
    )
    assert bindings.controls["worker_fresh"].cancel_requested.is_set()
    assert "worker_resume" not in bindings.requests
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_active:0")
    )
    assert bindings.events.index("failure_active:0") < (
        bindings.events.index("failure_result")
    )
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


@pytest.mark.parametrize("final_identity_status", ["invalid", "ambiguous"])
def test_steer_revalidates_cancelled_worker_final_identity_snapshot(
    tmp_path: Path,
    final_identity_status: str,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    create_control = bindings.create_control

    def create_control_with_changed_final_identity(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            cancel_and_reap = control.cancel_and_reap

            def return_changed_final_identity(
                grace: float,
            ) -> ProviderCancellationResult:
                proof = cancel_and_reap(grace)
                final_snapshot = _snapshot(
                    status=final_identity_status,
                    session_ids=(
                        ("session-1", "session-2")
                        if final_identity_status == "ambiguous"
                        else ("session-1",)
                    ),
                    error=(
                        {"type": "provider_session_transport_error"}
                        if final_identity_status == "invalid"
                        else None
                    ),
                )
                changed = replace(
                    proof,
                    final_session_snapshot=final_snapshot,
                    final_identity_valid=False,
                )
                control.terminal_result = changed
                return changed

            control.cancel_and_reap = (  # type: ignore[method-assign]
                return_changed_final_identity
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_control_with_changed_final_identity
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_resume_boundary_invalid"
    )
    assert "worker_resume" not in bindings.requests
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_active:0")
    )
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


@pytest.mark.parametrize(
    ("directive", "worker_delay", "supervisor_delay", "selected_role"),
    [
        ({"variant": "CONTINUE"}, 0.0, 0.04, "worker_fresh"),
        ({"variant": "CONTINUE"}, 0.04, 0.0, "worker_fresh"),
        ({"variant": "CONTINUE"}, 0.0, 0.0, "worker_fresh"),
        (
            {"variant": "STEER", "guidance": "revise"},
            0.0,
            0.04,
            "worker_resume",
        ),
    ],
)
def test_initial_worker_and_supervisor_completion_orders_preserve_selection(
    tmp_path: Path,
    directive: dict[str, Any],
    worker_delay: float,
    supervisor_delay: float,
    selected_role: str,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive=directive,
        worker_completes_naturally=True,
        worker_delay=worker_delay,
        supervisor_delay=supervisor_delay,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "completed"
    assert result["selected_role"] == selected_role


def test_hand_built_second_steer_budget_is_rejected_before_resume(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(max_steers=2),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_second_steer_rejected"
    )
    assert bindings.controls["worker_fresh"].cancel_requested.is_set()
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_active:0")
    )
    assert "worker_resume" not in bindings.requests
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_supervisor_timeout_joins_initial_members_before_failure_publication(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "CONTINUE"},
        worker_completes_naturally=False,
    )
    bindings.blocked_roles.add("supervisor_directive")

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(supervisor_timeout=0.02),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == (
        "provider_supervision_supervisor_timeout"
    )
    assert "failure_active:0" in bindings.events
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_result")
    )
    assert bindings.events.index("supervisor_directive:end") < (
        bindings.events.index("failure_result")
    )
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_continue_worker_timeout_joins_worker_before_failure_publication(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "CONTINUE"},
        worker_completes_naturally=False,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(worker_timeout=0.02),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_worker_timeout"
    assert bindings.events.index("worker_fresh:cancelled") < (
        bindings.events.index("worker_fresh:end")
    )
    assert bindings.events.index("worker_fresh:end") < (
        bindings.events.index("failure_active:0")
    )
    assert bindings.events.index("failure_active:0") < (
        bindings.events.index("failure_result")
    )
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_steer_resume_timeout_joins_resume_before_failure_publication(
    tmp_path: Path,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    bindings.blocked_roles.add("worker_resume")

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(worker_timeout=0.04),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_resume_timeout"
    assert "worker_fresh:validate" not in bindings.events
    assert bindings.controls["worker_resume"].cancel_requested.is_set()
    assert bindings.events.index("worker_resume:start") < (
        bindings.events.index("worker_resume:end")
    )
    assert bindings.events.index("worker_resume:end") < (
        bindings.events.index("failure_active:0")
    )
    assert bindings.events.index("failure_active:0") < (
        bindings.events.index("failure_result")
    )
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_cancelled_active_boundary_after_worker_deadline_reports_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    clock = SimpleNamespace(now=0.0)
    real_sleep = time.sleep
    monkeypatch.setattr(
        coordinator_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda _seconds: real_sleep(0.001),
        ),
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    create_control = bindings.create_control

    def create_control_crossing_worker_deadline(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            cancel_and_reap = control.cancel_and_reap

            def cross_worker_deadline(
                grace: float,
            ) -> ProviderCancellationResult:
                proof = cancel_and_reap(grace)
                clock.now = 2.0
                return proof

            control.cancel_and_reap = (  # type: ignore[method-assign]
                cross_worker_deadline
            )
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_control_crossing_worker_deadline
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(
            whole_timeout=10,
            worker_timeout=1,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_worker_timeout"
    assert "worker_resume" not in bindings.requests
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


@pytest.mark.parametrize(
    ("awaited_phase", "directive", "target_wait_call", "target_role"),
    [
        (
            "supervisor_initial",
            {"variant": "CONTINUE"},
            1,
            "supervisor_directive",
        ),
        (
            "fresh_continue",
            {"variant": "CONTINUE"},
            2,
            "worker_fresh",
        ),
        (
            "worker_resume",
            {"variant": "STEER", "guidance": "revise"},
            3,
            "worker_resume",
        ),
    ],
)
def test_whole_step_deadline_precedes_member_timeout_while_awaiting_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    awaited_phase: str,
    directive: dict[str, Any],
    target_wait_call: int,
    target_role: str,
) -> None:
    import importlib

    del awaited_phase
    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    clock = SimpleNamespace(now=0.0)
    real_sleep = time.sleep
    real_monotonic = time.monotonic
    monkeypatch.setattr(
        coordinator_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda _seconds: real_sleep(0.001),
        ),
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive=directive,
        worker_completes_naturally=False,
    )
    if target_role == "supervisor_directive":
        bindings.blocked_roles.add(target_role)
    if target_role == "worker_resume":
        bindings.blocked_roles.add(target_role)

    coordinator = ProviderSupervisionCoordinator(bindings)
    result_before = coordinator._result_before
    wait_calls = 0

    def expire_whole_deadline_at_target_wait(
        future: Future[Any],
        deadline: float,
        *,
        whole_deadline: float,
        code: str,
    ) -> Any:
        nonlocal wait_calls
        wait_calls += 1
        if wait_calls == target_wait_call:
            stop_waiting_at = real_monotonic() + 1
            while f"{target_role}:start" not in bindings.events:
                assert real_monotonic() < stop_waiting_at
                real_sleep(0.001)
            clock.now = 2.0
        return result_before(
            future,
            deadline,
            whole_deadline=whole_deadline,
            code=code,
        )

    monkeypatch.setattr(
        coordinator,
        "_result_before",
        expire_whole_deadline_at_target_wait,
    )

    result = coordinator.run(
        _coordinator_config(
            whole_timeout=1,
            worker_timeout=10,
            supervisor_timeout=10,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert wait_calls == target_wait_call
    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_step_timeout"
    assert "failure_active:0" in bindings.events
    assert all(
        control.execution_done.is_set()
        for control in bindings.controls.values()
    )
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_whole_step_timeout_wins_after_clean_boundary_before_resume_launch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    clock = SimpleNamespace(now=0.0)
    monkeypatch.setattr(
        coordinator_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda _seconds: None,
        ),
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=True,
    )
    worker_done = threading.Event()
    execute_member = bindings.execute_member

    def execute_worker_before_supervisor(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        if request.turn.turn_role == "supervisor_directive":
            assert worker_done.wait(timeout=1)
        result = execute_member(request)
        if request.turn.turn_role == "worker_fresh":
            worker_done.set()
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        execute_worker_before_supervisor
    )
    create_control = bindings.create_control

    def create_control_with_deadline_transition(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        control = create_control(turn)
        if turn.turn_role == "worker_fresh":
            cancel_and_reap = control.cancel_and_reap

            def cross_whole_deadline(
                grace: float,
            ) -> ProviderCancellationResult:
                proof = cancel_and_reap(grace)
                clock.now = 2.0
                return proof

            control.cancel_and_reap = cross_whole_deadline  # type: ignore[method-assign]
        return control

    bindings.create_control = (  # type: ignore[method-assign]
        create_control_with_deadline_transition
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(
            whole_timeout=1,
            worker_timeout=10,
            supervisor_timeout=10,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_step_timeout"
    assert bindings.attempt_roles == [
        "worker_fresh",
        "supervisor_directive",
    ]
    assert "worker_resume" not in bindings.requests
    assert "worker_fresh:validate" not in bindings.events
    assert "failure_active:0" in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


@pytest.mark.parametrize(
    "failure_kind",
    ["natural_nonzero", "turn_failed"],
)
def test_worker_terminal_failure_precedes_valid_delayed_steer(
    tmp_path: Path,
    failure_kind: str,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=True,
    )
    worker_done = threading.Event()
    execute_member = bindings.execute_member

    def execute_worker_failure_before_supervisor(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert worker_done.wait(timeout=1)
            return execute_member(request)
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        if failure_kind == "natural_nonzero":
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _terminal_proof(
                snapshot=terminal_snapshot,
                leader_return_code=3,
            )
            result = ProviderExecutionResult(
                exit_code=3,
                stdout=b"",
                stderr=b"",
                duration_ms=0,
                classification="failed",
            )
        else:
            terminal_snapshot = _snapshot(
                status="invalid",
                terminal_seen=True,
                error={"type": "provider_session_turn_failed"},
            )
            control.session_snapshot = terminal_snapshot
            control.terminal_result = replace(
                _natural_proof(snapshot=terminal_snapshot),
                final_identity_valid=False,
            )
            result = ProviderExecutionResult(
                exit_code=0,
                stdout=b"",
                stderr=b"",
                duration_ms=0,
                error={"type": "provider_session_turn_failed"},
                classification="failed",
            )
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        worker_done.set()
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        execute_worker_failure_before_supervisor
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_member_failed"
    assert not bindings.controls["worker_fresh"].cancel_requested.is_set()
    assert "worker_fresh:cancelled" not in bindings.events
    assert "worker_resume" not in bindings.requests
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_steer_waits_for_frozen_worker_result_after_terminal_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    clock = SimpleNamespace(now=0.0)
    real_sleep = time.sleep
    monkeypatch.setattr(
        coordinator_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda _seconds: real_sleep(0.001),
        ),
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    terminal_observed = threading.Event()
    preproof_classified = threading.Event()
    cancelled_before_frozen_result: list[bool] = []
    terminal_observed_at: list[float] = []
    frozen_result_at: list[float] = []
    classify = (
        coordinator_module.classify_provider_supervision_resume_boundary
    )

    def observe_preproof_classification(**kwargs: Any) -> Any:
        assessment = classify(**kwargs)
        snapshot = kwargs["snapshot"]
        if (
            snapshot is not None
            and snapshot.terminal_seen
            and kwargs["terminal_proof"] is None
        ):
            preproof_classified.set()
        return assessment

    monkeypatch.setattr(
        coordinator_module,
        "classify_provider_supervision_resume_boundary",
        observe_preproof_classification,
    )
    execute_member = bindings.execute_member

    def finish_worker_after_terminal_observation(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert terminal_observed.wait(timeout=1)
            return execute_member(request)
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        control.session_snapshot = _snapshot(terminal_seen=True)
        terminal_observed_at.append(clock.now)
        terminal_observed.set()
        assert preproof_classified.wait(timeout=1)
        clock.now = 2.0
        cancelled_before_frozen_result.append(
            control.cancel_requested.wait(timeout=0.05)
        )
        terminal_snapshot = _snapshot(terminal_seen=True)
        control.session_snapshot = terminal_snapshot
        control.terminal_result = _natural_proof(
            snapshot=terminal_snapshot,
        )
        result = ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=0,
            classification="normal",
        )
        frozen_result_at.append(clock.now)
        bindings._record(f"{role}:frozen_result")
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        finish_worker_after_terminal_observation
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(
            whole_timeout=10,
            worker_timeout=1,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert preproof_classified.is_set()
    assert terminal_observed_at == [0.0]
    assert frozen_result_at == [2.0]
    assert cancelled_before_frozen_result == [False]
    assert result == {
        "status": "completed",
        "selected_role": "worker_resume",
        "value": "resumed",
    }
    assert bindings.attempt_roles.count("worker_resume") == 1
    resume_request = bindings.requests["worker_resume"]
    assert resume_request.invocation.materialize().session_request == (
        ProviderSessionRequest(
            mode=ProviderSessionMode.RESUME,
            session_id="session-1",
        )
    )


def test_steer_waits_for_frozen_turn_failed_result_before_member_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    terminal_observed = threading.Event()
    preproof_classified = threading.Event()
    cancelled_before_frozen_result: list[bool] = []
    classify = (
        coordinator_module.classify_provider_supervision_resume_boundary
    )

    def observe_preproof_classification(**kwargs: Any) -> Any:
        assessment = classify(**kwargs)
        snapshot = kwargs["snapshot"]
        if (
            snapshot is not None
            and snapshot.terminal_seen
            and kwargs["terminal_proof"] is None
        ):
            preproof_classified.set()
        return assessment

    monkeypatch.setattr(
        coordinator_module,
        "classify_provider_supervision_resume_boundary",
        observe_preproof_classification,
    )
    execute_member = bindings.execute_member

    def freeze_turn_failed_after_terminal_observation(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert terminal_observed.wait(timeout=1)
            return execute_member(request)
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        terminal_snapshot = _snapshot(
            status="invalid",
            terminal_seen=True,
            error={"type": "provider_session_turn_failed"},
        )
        control.session_snapshot = terminal_snapshot
        terminal_observed.set()
        assert preproof_classified.wait(timeout=1)
        cancelled_before_frozen_result.append(
            control.cancel_requested.wait(timeout=0.05)
        )
        control.terminal_result = replace(
            _natural_proof(snapshot=terminal_snapshot),
            final_identity_valid=False,
        )
        result = ProviderExecutionResult(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=0,
            error={"type": "provider_session_turn_failed"},
            classification="failed",
        )
        bindings._record(f"{role}:frozen_result")
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        freeze_turn_failed_after_terminal_observation
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert preproof_classified.is_set()
    assert cancelled_before_frozen_result == [False]
    assert result["status"] == "failed"
    assert result["error"]["type"] == "provider_supervision_member_failed"
    assert bindings.events.index("supervisor_directive:validate") < (
        bindings.events.index("worker_fresh:frozen_result")
    )
    assert "worker_resume" not in bindings.requests
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events


@pytest.mark.parametrize(
    "frozen_result_kind",
    ["natural_success", "member_failure"],
)
def test_terminal_proof_waits_for_frozen_worker_execution_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    frozen_result_kind: str,
) -> None:
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=False,
    )
    proof_visible = threading.Event()
    frozen_result_wait_requested = threading.Event()
    waited_for_frozen_result: list[bool] = []
    cancelled_before_frozen_result: list[bool] = []
    execute_member = bindings.execute_member

    def publish_proof_before_frozen_result(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        if role == "supervisor_directive":
            assert proof_visible.wait(timeout=1)
            return execute_member(request)
        if role != "worker_fresh":
            return execute_member(request)

        bindings.requests[role] = request
        bindings._record(f"{role}:start")
        with bindings._lock:
            bindings._active_roles.add(role)
        control = request.control
        terminal_snapshot = _snapshot(terminal_seen=True)
        control.session_snapshot = terminal_snapshot
        control.terminal_result = _natural_proof(
            snapshot=terminal_snapshot,
        )
        proof_visible.set()
        waited_for_frozen_result.append(
            frozen_result_wait_requested.wait(timeout=0.05)
        )
        cancelled_before_frozen_result.append(
            control.cancel_requested.is_set()
        )
        if frozen_result_kind == "natural_success":
            result = ProviderExecutionResult(0, b"", b"", 0)
        else:
            result = ProviderExecutionResult(
                exit_code=1,
                stdout=b"",
                stderr=b"failed",
                duration_ms=0,
                error={"type": "provider_execution_failed"},
                classification="failed",
            )
        bindings._record(f"{role}:frozen_result")
        with bindings._lock:
            bindings._active_roles.remove(role)
        control.execution_done.set()
        bindings._record(f"{role}:end")
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        publish_proof_before_frozen_result
    )
    coordinator = ProviderSupervisionCoordinator(bindings)
    result_before = coordinator._result_before

    def observe_frozen_worker_wait(
        future: Future[Any],
        deadline: float,
        *,
        whole_deadline: float,
        code: str,
    ) -> Any:
        worker_control = bindings.controls.get("worker_fresh")
        if (
            worker_control is not None
            and future is worker_control.future
            and worker_control.terminal_result is not None
            and not future.done()
        ):
            frozen_result_wait_requested.set()
        return result_before(
            future,
            deadline,
            whole_deadline=whole_deadline,
            code=code,
        )

    monkeypatch.setattr(
        coordinator,
        "_result_before",
        observe_frozen_worker_wait,
    )

    result = coordinator.run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert waited_for_frozen_result == [True]
    assert cancelled_before_frozen_result == [False]
    if frozen_result_kind == "natural_success":
        assert result == {
            "status": "completed",
            "selected_role": "worker_resume",
            "value": "resumed",
        }
        resume_request = bindings.requests["worker_resume"]
        assert resume_request.invocation.materialize().session_request == (
            ProviderSessionRequest(
                mode=ProviderSessionMode.RESUME,
                session_id="session-1",
            )
        )
    else:
        assert result["status"] == "failed"
        assert (
            result["error"]["type"]
            == "provider_supervision_member_failed"
        )
        assert "worker_resume" not in bindings.requests


def test_whole_deadline_expiry_during_resume_preparation_prevents_submission(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import importlib

    coordinator_module = importlib.import_module(
        "orchestrator.workflow.provider_supervision.coordinator"
    )
    clock = SimpleNamespace(now=0.0)
    real_sleep = time.sleep
    monkeypatch.setattr(
        coordinator_module,
        "time",
        SimpleNamespace(
            monotonic=lambda: clock.now,
            sleep=lambda _seconds: real_sleep(0.001),
        ),
    )
    bindings = _EarlyArbitrationBindings(
        tmp_path,
        directive={"variant": "STEER", "guidance": "revise"},
        worker_completes_naturally=True,
    )
    worker_done = threading.Event()
    execute_member = bindings.execute_member

    def complete_worker_before_supervisor(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        if request.turn.turn_role == "supervisor_directive":
            assert worker_done.wait(timeout=1)
        result = execute_member(request)
        if request.turn.turn_role == "worker_fresh":
            worker_done.set()
        return result

    bindings.execute_member = (  # type: ignore[method-assign]
        complete_worker_before_supervisor
    )
    prepare_resume_invocation = bindings.prepare_resume_invocation
    preparation_started_at: list[float] = []

    def expire_during_resume_preparation(
        **kwargs: Any,
    ) -> ProviderInvocation:
        invocation = prepare_resume_invocation(**kwargs)
        preparation_started_at.append(clock.now)
        clock.now = 2.0
        return invocation

    bindings.prepare_resume_invocation = (  # type: ignore[method-assign]
        expire_during_resume_preparation
    )
    coordinator = ProviderSupervisionCoordinator(bindings)
    submit = coordinator._submit
    submitted_roles: list[str] = []

    def record_submission(
        members: Any,
        request: ProviderSupervisionMemberRequest,
        futures: dict[int, Future[Any]],
    ) -> Future[Any]:
        submitted_roles.append(request.turn.turn_role)
        return submit(members, request, futures)

    monkeypatch.setattr(coordinator, "_submit", record_submission)

    result = coordinator.run(
        _coordinator_config(
            whole_timeout=1,
            worker_timeout=10,
            supervisor_timeout=10,
        ),
        step_name="Live",
        visit_count=1,
    )

    assert preparation_started_at == [0.0]
    assert result["status"] == "failed"
    assert submitted_roles == [
        "worker_fresh",
        "supervisor_directive",
    ]
    assert result["error"]["type"] == "provider_supervision_step_timeout"
    assert "worker_resume" not in bindings.requests
    assert "worker_resume:start" not in bindings.events
    assert "worker_fresh:validate" not in bindings.events
    assert "finalize" not in bindings.events
    assert "artifacts" not in result


def test_real_binding_rejects_stale_resume_preimage_before_initial_activity(
    tmp_path: Path,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.provider_supervision.bindings import (
        WorkflowProviderSupervisionBindings,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )
    from tests.test_provider_supervision_runtime import (
        _RealBindingExecutor,
        _RealBindingObservationManager,
        _RealBindingProviderExecutor,
        _config_with_prompt_snapshot_owners,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-stale-resume-preimage",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    stale_resume_bundle = (
        Path(manager.run_root).resolve()
        / config.paths.worker_resume.provisional_bundle_relpath.replace(
            "{visit}",
            "1",
        )
    )
    stale_resume_bundle.parent.mkdir(parents=True, exist_ok=True)
    stale_resume_bundle.write_text('"stale"', encoding="utf-8")
    executor = _RealBindingExecutor(tmp_path, manager)
    observation_manager = _RealBindingObservationManager()
    provider_executor = _RealBindingProviderExecutor()
    executor.provider_observation_manager = observation_manager
    executor.provider_executor = provider_executor
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=manager.load().to_dict(),
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )

    with pytest.raises(ValueError, match="provisional path preimage"):
        bindings.derive_turn_bindings(
            config=config,
            visit_count=1,
        )

    assert observation_manager.handles == []
    assert manager.load().provider_attempt_allocations == {}
    assert provider_executor.paths == []


@pytest.mark.parametrize(
    "fresh_bundle_state",
    ["absent", "invalid", "valid_unselected"],
)
def test_real_binding_steer_allocates_and_selects_one_exact_resume_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    fresh_bundle_state: str,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.provider_supervision.bindings import (
        WorkflowProviderSupervisionBindings,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )
    from tests.test_provider_supervision_runtime import (
        _RealBindingExecutor,
        _config_with_prompt_snapshot_owners,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-real-steer",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    executor = _RealBindingExecutor(tmp_path, manager)
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )
    events: list[tuple[Any, ...]] = []
    requests: dict[str, list[ProviderSupervisionMemberRequest]] = {}
    validated_roles: list[str] = []

    class _RecordingControl(_ScriptedControl):
        def __init__(
            self,
            role: str,
            *,
            snapshot: SessionIdentitySnapshot | None = None,
        ) -> None:
            super().__init__(snapshot=snapshot)
            self.role = role

        def cancel_and_reap(
            self,
            grace: float,
        ) -> ProviderCancellationResult:
            proof = super().cancel_and_reap(grace)
            events.append(
                (
                    "cancellation_proof",
                    self.role,
                    len(manager.load().provider_attempt_allocations),
                )
            )
            return proof

    def create_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _RecordingControl:
        control = _RecordingControl(
            turn.turn_role,
            snapshot=(
                _snapshot()
                if turn.turn_role == "worker_fresh"
                else None
            ),
        )
        events.append(
            (
                "create_control",
                turn.turn_role,
                len(manager.load().provider_attempt_allocations),
            )
        )
        return control

    def execute_member(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        requests.setdefault(role, []).append(request)
        control = request.control
        try:
            if role == "worker_fresh":
                assert control.cancel_requested.wait(timeout=1)
                control.terminal_result = _cancelled_proof()
                if fresh_bundle_state == "invalid":
                    request.turn.provisional_bundle_path.write_text(
                        "{",
                        encoding="utf-8",
                    )
                elif fresh_bundle_state == "valid_unselected":
                    request.turn.provisional_bundle_path.write_text(
                        '"fresh-unselected"',
                        encoding="utf-8",
                    )
                return ProviderExecutionResult(
                    exit_code=-15,
                    stdout=b"",
                    stderr=b"",
                    duration_ms=0,
                    classification="cancelled_provisional",
                )
            if role == "supervisor_directive":
                request.turn.provisional_bundle_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                control.terminal_result = _natural_proof()
                return ProviderExecutionResult(0, b"", b"", 0)
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            request.turn.provisional_bundle_path.write_text(
                '"resumed-value"',
                encoding="utf-8",
            )
            return ProviderExecutionResult(0, b"", b"", 0)
        finally:
            control.execution_done.set()

    monkeypatch.setattr(bindings, "create_control", create_control)
    monkeypatch.setattr(bindings, "execute_member", execute_member)
    validate_member_bundle = bindings.validate_member_bundle

    def record_validated_role(
        request: ProviderSupervisionMemberRequest,
    ) -> Any:
        validated_roles.append(request.turn.turn_role)
        return validate_member_bundle(request)

    monkeypatch.setattr(
        bindings,
        "validate_member_bundle",
        record_validated_role,
    )

    result = ProviderSupervisionCoordinator(bindings).run(
        config,
        step_name="Live",
        visit_count=1,
    )

    resume_requests = requests["worker_resume"]
    assert len(resume_requests) == 1
    resume_request = resume_requests[0]
    fresh_request = requests["worker_fresh"][0]
    resume_invocation = resume_request.invocation.materialize()
    assert resume_invocation.session_request == ProviderSessionRequest(
        mode=ProviderSessionMode.RESUME,
        session_id="session-1",
    )
    assert resume_invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"] == str(
        resume_request.turn.provisional_bundle_path
    )
    assert (
        resume_request.turn.provisional_bundle_path
        != fresh_request.turn.provisional_bundle_path
    )
    assert str(resume_request.turn.provisional_bundle_path) in (
        resume_invocation.prompt or ""
    )
    assert validated_roles == [
        "supervisor_directive",
        "worker_resume",
    ]
    assert (
        "cancellation_proof",
        "worker_fresh",
        2,
    ) in events
    assert [
        event
        for event in events
        if event[:2] == ("create_control", "worker_resume")
    ] == [("create_control", "worker_resume", 3)]
    assert len(manager.load().provider_attempt_allocations) == 3
    assert result["status"] == "completed"
    assert result["artifacts"] == {"__result__": "resumed-value"}
    assert result["debug"]["provider_supervision"]["selected_attempt"] == {
        "scope_key": resume_request.attempt.scope_key,
        "ordinal": resume_request.attempt.ordinal,
    }


def test_workflow_executor_dispatches_provider_supervision_to_general_run(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )

    config = _provider_supervision_config()
    workflow_path = tmp_path / "workflow.orc"
    workflow_path.write_text(
        "; provider-supervision dispatch fixture\n",
        encoding="utf-8",
    )
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-general-dispatch",
    )
    manager.initialize(workflow_path.name)
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = manager
    executor._executable_node_for_step = (  # type: ignore[method-assign]
        lambda _step: SimpleNamespace(execution_config=config)
    )
    sentinel = {"status": "sentinel"}
    calls: list[tuple[Any, str, int]] = []

    def record_general_run(
        _coordinator: ProviderSupervisionCoordinator,
        observed_config: Any,
        *,
        step_name: str,
        visit_count: int,
    ) -> dict[str, str]:
        calls.append((observed_config, step_name, visit_count))
        return sentinel

    def reject_legacy_run(
        _coordinator: ProviderSupervisionCoordinator,
        *_args: Any,
        **_kwargs: Any,
    ) -> dict[str, Any]:
        raise AssertionError("legacy CONTINUE-only coordinator was called")

    monkeypatch.setattr(
        ProviderSupervisionCoordinator,
        "run",
        record_general_run,
    )
    monkeypatch.setattr(
        ProviderSupervisionCoordinator,
        "run_continue",
        reject_legacy_run,
    )

    result = WorkflowExecutor._execute_provider_supervision(
        executor,
        {"name": "Live", "step_id": "root.live"},
        {"step_visits": {"Live": 7}},
        step_name="Live",
    )

    assert result is sentinel
    assert calls == [(config, "Live", 7)]


def test_real_binding_rejects_resume_preimage_created_after_initial_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.provider_supervision.bindings import (
        WorkflowProviderSupervisionBindings,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )
    from tests.test_provider_supervision_runtime import (
        _RealBindingExecutor,
        _config_with_prompt_snapshot_owners,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id="provider-supervision-real-steer-negative",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    resume_path = (
        Path(manager.run_root).resolve()
        / config.paths.worker_resume.provisional_bundle_relpath.replace(
            "{visit}",
            "1",
        )
    )
    executor = _RealBindingExecutor(tmp_path, manager)
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )
    requests: dict[str, list[ProviderSupervisionMemberRequest]] = {}

    def create_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        return _ScriptedControl(
            snapshot=(
                _snapshot()
                if turn.turn_role == "worker_fresh"
                else None
            ),
        )

    def execute_member(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        requests.setdefault(role, []).append(request)
        control = request.control
        try:
            if role == "worker_fresh":
                assert control.cancel_requested.wait(timeout=1)
                control.terminal_result = _cancelled_proof()
                return ProviderExecutionResult(
                    exit_code=-15,
                    stdout=b"",
                    stderr=b"",
                    duration_ms=0,
                    classification="cancelled_provisional",
                )
            if role == "supervisor_directive":
                request.turn.provisional_bundle_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                resume_path.parent.mkdir(parents=True, exist_ok=True)
                resume_path.write_text('"stale"', encoding="utf-8")
                control.terminal_result = _natural_proof()
                return ProviderExecutionResult(0, b"", b"", 0)
            raise AssertionError("resume provider process must not launch")
        finally:
            control.execution_done.set()

    monkeypatch.setattr(bindings, "create_control", create_control)
    monkeypatch.setattr(bindings, "execute_member", execute_member)
    result = ProviderSupervisionCoordinator(bindings).run(
        config,
        step_name="Live",
        visit_count=1,
    )

    fresh_path = requests["worker_fresh"][0].turn.provisional_bundle_path
    assert result["status"] == "failed"
    assert "artifacts" not in result
    assert "debug" not in result
    persisted = manager.load()
    assert persisted.steps["Live"]["status"] == "failed"
    assert persisted.steps["Live"].get("artifacts") is None
    assert persisted.steps["Live"].get("debug") is None
    assert persisted.artifact_versions == {}
    assert persisted.private_artifact_versions == {}
    assert len(persisted.provider_attempt_allocations) == 2
    assert "worker_resume" not in requests
    assert resume_path.exists()
    assert not fresh_path.exists()


@pytest.mark.parametrize("resume_bundle_mode", ["missing", "invalid"])
def test_real_binding_rejects_unusable_resume_bundle_without_selected_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resume_bundle_mode: str,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.provider_supervision.bindings import (
        WorkflowProviderSupervisionBindings,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )
    from tests.test_provider_supervision_runtime import (
        _RealBindingExecutor,
        _config_with_prompt_snapshot_owners,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id=f"provider-supervision-resume-{resume_bundle_mode}",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    executor = _RealBindingExecutor(tmp_path, manager)
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )
    requests: dict[str, list[ProviderSupervisionMemberRequest]] = {}

    def create_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        return _ScriptedControl(
            snapshot=(
                _snapshot()
                if turn.turn_role == "worker_fresh"
                else None
            ),
        )

    def execute_member(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        requests.setdefault(role, []).append(request)
        control = request.control
        try:
            if role == "worker_fresh":
                assert control.cancel_requested.wait(timeout=1)
                control.terminal_result = _cancelled_proof()
                return ProviderExecutionResult(
                    exit_code=-15,
                    stdout=b"",
                    stderr=b"",
                    duration_ms=0,
                    classification="cancelled_provisional",
                )
            if role == "supervisor_directive":
                request.turn.provisional_bundle_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                control.terminal_result = _natural_proof()
                return ProviderExecutionResult(0, b"", b"", 0)
            terminal_snapshot = _snapshot(terminal_seen=True)
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            if resume_bundle_mode == "invalid":
                request.turn.provisional_bundle_path.write_text(
                    "42",
                    encoding="utf-8",
                )
            return ProviderExecutionResult(
                exit_code=0,
                stdout=b"",
                stderr=b"",
                duration_ms=0,
                classification="normal",
            )
        finally:
            control.execution_done.set()

    monkeypatch.setattr(bindings, "create_control", create_control)
    monkeypatch.setattr(bindings, "execute_member", execute_member)

    result = ProviderSupervisionCoordinator(bindings).run(
        config,
        step_name="Live",
        visit_count=1,
    )

    fresh_path = requests["worker_fresh"][0].turn.provisional_bundle_path
    assert result["status"] == "failed"
    assert "artifacts" not in result
    assert "debug" not in result
    persisted = manager.load()
    assert persisted.steps["Live"]["status"] == "failed"
    assert persisted.steps["Live"].get("artifacts") is None
    assert persisted.steps["Live"].get("debug") is None
    assert persisted.artifact_versions == {}
    assert persisted.private_artifact_versions == {}
    assert len(persisted.provider_attempt_allocations) == 3
    assert len(requests["worker_resume"]) == 1
    assert not fresh_path.exists()


@pytest.mark.parametrize(
    (
        "resume_failure_mode",
        "terminal_session_id",
        "resume_classification",
        "expected_error",
    ),
    [
        (
            "terminal_identity_mismatch",
            "different-session",
            "normal",
            "provider_supervision_resume_identity_mismatch",
        ),
        (
            "nonpromotable_execution",
            "session-1",
            "failed",
            "provider_supervision_member_failed",
        ),
    ],
)
def test_real_binding_rejects_unusable_native_resume_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    resume_failure_mode: str,
    terminal_session_id: str,
    resume_classification: str,
    expected_error: str,
) -> None:
    from orchestrator.state import StateManager
    from orchestrator.workflow.provider_supervision.bindings import (
        WorkflowProviderSupervisionBindings,
    )
    from tests.test_provider_supervision_ir import (
        _provider_supervision_config,
    )
    from tests.test_provider_supervision_runtime import (
        _RealBindingExecutor,
        _config_with_prompt_snapshot_owners,
    )

    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated test workflow\n", encoding="utf-8")
    manager = StateManager(
        tmp_path,
        run_id=f"provider-supervision-resume-{resume_failure_mode}",
    )
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Live": 1})
    manager.start_step(
        "Live",
        0,
        "provider_supervision",
        step_id="root.live",
        visit_count=1,
    )
    state = manager.load().to_dict()
    state["context"] = {
        "prompt_dependency": "inputs/intentionally-absent.md",
    }
    config = _config_with_prompt_snapshot_owners(
        _provider_supervision_config()
    )
    executor = _RealBindingExecutor(tmp_path, manager)
    bindings = WorkflowProviderSupervisionBindings(
        executor,
        step={"name": "Live", "step_id": "root.live"},
        state=state,
        config=config,
        step_name="Live",
        runtime_step_id="root.live",
    )
    requests: dict[str, list[ProviderSupervisionMemberRequest]] = {}

    def create_control(
        turn: ProviderSupervisionTurnBinding,
    ) -> _ScriptedControl:
        return _ScriptedControl(
            snapshot=(
                _snapshot()
                if turn.turn_role == "worker_fresh"
                else None
            ),
        )

    def execute_member(
        request: ProviderSupervisionMemberRequest,
    ) -> ProviderExecutionResult:
        role = request.turn.turn_role
        requests.setdefault(role, []).append(request)
        control = request.control
        try:
            if role == "worker_fresh":
                assert control.cancel_requested.wait(timeout=1)
                control.terminal_result = _cancelled_proof()
                return ProviderExecutionResult(
                    exit_code=-15,
                    stdout=b"",
                    stderr=b"",
                    duration_ms=0,
                    classification="cancelled_provisional",
                )
            if role == "supervisor_directive":
                request.turn.provisional_bundle_path.write_text(
                    '{"variant":"STEER","guidance":"revise"}',
                    encoding="utf-8",
                )
                control.terminal_result = _natural_proof()
                return ProviderExecutionResult(0, b"", b"", 0)
            terminal_snapshot = _snapshot(
                session_ids=(terminal_session_id,),
                terminal_seen=True,
            )
            control.session_snapshot = terminal_snapshot
            control.terminal_result = _natural_proof(
                snapshot=terminal_snapshot,
            )
            request.turn.provisional_bundle_path.write_text(
                '"resumed-value"',
                encoding="utf-8",
            )
            return ProviderExecutionResult(
                exit_code=0,
                stdout=b"",
                stderr=b"",
                duration_ms=0,
                classification=resume_classification,
            )
        finally:
            control.execution_done.set()

    monkeypatch.setattr(bindings, "create_control", create_control)
    monkeypatch.setattr(bindings, "execute_member", execute_member)

    result = ProviderSupervisionCoordinator(bindings).run(
        config,
        step_name="Live",
        visit_count=1,
    )

    fresh_path = requests["worker_fresh"][0].turn.provisional_bundle_path
    resume_request = requests["worker_resume"][0]
    assert resume_request.invocation.materialize().session_request == (
        ProviderSessionRequest(
            mode=ProviderSessionMode.RESUME,
            session_id="session-1",
        )
    )
    assert result["status"] == "failed"
    assert result["error"]["type"] == expected_error
    assert "artifacts" not in result
    assert "debug" not in result
    persisted = manager.load()
    assert persisted.steps["Live"]["status"] == "failed"
    assert persisted.steps["Live"].get("artifacts") is None
    assert persisted.steps["Live"].get("debug") is None
    assert persisted.artifact_versions == {}
    assert persisted.private_artifact_versions == {}
    assert len(persisted.provider_attempt_allocations) == 3
    assert len(requests["worker_resume"]) == 1
    assert not fresh_path.exists()


def test_live_coordinator_authored_retry_waits_for_durable_failed_visit_and_uses_fresh_identities(
    tmp_path: Path,
) -> None:
    class _RetryBindings(_EarlyArbitrationBindings):
        def __init__(self) -> None:
            super().__init__(
                tmp_path,
                directive={"variant": "INVALID"},
                worker_completes_naturally=False,
            )
            self.durable_failed_visits: list[int] = []
            self.active_visit = 1
            self.requests_by_visit: dict[
                int,
                dict[str, ProviderSupervisionMemberRequest],
            ] = {}

        def derive_turn_bindings(
            self,
            *,
            config: Any,
            visit_count: int,
        ) -> dict[str, ProviderSupervisionTurnBinding]:
            assert visit_count == self.active_visit
            turns = super().derive_turn_bindings(
                config=config,
                visit_count=visit_count,
            )
            return {
                role: replace(
                    turn,
                    runtime_step_id=(
                        f"{turn.runtime_step_id}:visit:{visit_count}"
                    ),
                    evidence_path=(
                        self.tmp_path
                        / f"visit-{visit_count}"
                        / role
                        / "evidence.json"
                    ),
                    provisional_bundle_path=(
                        self.tmp_path
                        / f"visit-{visit_count}"
                        / role
                        / "provisional.json"
                    ),
                )
                for role, turn in turns.items()
            }

        def open_observation(
            self,
            turn: ProviderSupervisionTurnBinding,
        ) -> ProviderSupervisionObservationBinding:
            observation = super().open_observation(turn)
            return replace(
                observation,
                target=f"{observation.target}:visit:{self.active_visit}",
            )

        def allocate_attempt(
            self,
            *,
            turn: ProviderSupervisionTurnBinding,
            prompt: str,
        ) -> ProviderSupervisionAttemptBinding:
            attempt = super().allocate_attempt(turn=turn, prompt=prompt)
            return replace(
                attempt,
                scope_key=f"{attempt.scope_key}:visit:{self.active_visit}",
                snapshot_key=(
                    f"{attempt.snapshot_key}:visit:{self.active_visit}"
                ),
            )

        def create_control(
            self,
            turn: ProviderSupervisionTurnBinding,
        ) -> _ScriptedControl:
            control = super().create_control(turn)
            if turn.turn_role == "worker_fresh":
                control.session_snapshot = _snapshot(
                    session_ids=(f"session-{self.active_visit}",),
                )
            return control

        def execute_member(
            self,
            request: ProviderSupervisionMemberRequest,
        ) -> ProviderExecutionResult:
            visit = self.active_visit
            self.requests_by_visit.setdefault(visit, {})[
                request.turn.turn_role
            ] = request
            self._record(f"visit:{visit}:{request.turn.turn_role}:launch")
            result = super().execute_member(request)
            if (
                request.turn.turn_role == "worker_fresh"
                and self.worker_completes_naturally
            ):
                terminal_snapshot = _snapshot(
                    session_ids=(f"session-{visit}",),
                    terminal_seen=True,
                )
                request.control.session_snapshot = terminal_snapshot
                request.control.terminal_result = _natural_proof(
                    snapshot=terminal_snapshot,
                )
            self._record(f"visit:{visit}:{request.turn.turn_role}:joined")
            return result

        def failure_result(self, *, code: str, message: str) -> dict[str, Any]:
            failed_requests = self.requests_by_visit[self.active_visit]
            assert set(failed_requests) == {
                "worker_fresh",
                "supervisor_directive",
            }
            assert not self._active_roles
            for request in failed_requests.values():
                proof = request.control.terminal_result
                assert request.control.execution_done.is_set()
                assert proof is not None
                assert proof.capture_threads_joined is True
                assert proof.execution_joined is True
                assert proof.proof_complete is True
            result = super().failure_result(code=code, message=message)
            assert self.events[-1] == "failure_result"
            assert f"failure_active:0" in self.events
            self.durable_failed_visits.append(self.active_visit)
            self._record(f"visit:{self.active_visit}:durable_failed")
            return result

        def finalize_settlement(self, **kwargs: Any) -> dict[str, Any]:
            assert self.durable_failed_visits == [1]
            self._record("retry_after_durable_failed_visit")
            return super().finalize_settlement(**kwargs)

    bindings = _RetryBindings()
    first = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=1,
    )

    assert first["status"] == "failed"
    failed_commit_index = bindings.events.index("visit:1:durable_failed")
    assert (
        bindings.events.index("visit:1:worker_fresh:joined")
        < failed_commit_index
    )
    assert (
        bindings.events.index("visit:1:supervisor_directive:joined")
        < failed_commit_index
    )

    bindings.active_visit = 2
    bindings.directive = {"variant": "CONTINUE"}
    bindings.worker_completes_naturally = True
    second = ProviderSupervisionCoordinator(bindings).run(
        _coordinator_config(),
        step_name="Live",
        visit_count=2,
    )

    assert second["status"] == "completed"
    assert "retry_after_durable_failed_visit" in bindings.events
    second_launch_index = min(
        bindings.events.index("visit:2:worker_fresh:launch"),
        bindings.events.index("visit:2:supervisor_directive:launch"),
    )
    assert failed_commit_index < second_launch_index

    first_requests = bindings.requests_by_visit[1]
    retry_requests = bindings.requests_by_visit[2]
    for role in ("worker_fresh", "supervisor_directive"):
        first_request = first_requests[role]
        retry_request = retry_requests[role]
        assert first_request.turn.runtime_step_id != (
            retry_request.turn.runtime_step_id
        )
        assert first_request.turn.evidence_path != (
            retry_request.turn.evidence_path
        )
        assert first_request.attempt.scope_key != (
            retry_request.attempt.scope_key
        )
        assert first_request.attempt.snapshot_key != (
            retry_request.attempt.snapshot_key
        )
        assert first_request.observation is not None
        assert retry_request.observation is not None
        assert first_request.observation.target != (
            retry_request.observation.target
        )
        assert (
            retry_request.invocation.materialize().session_request
            is None
        )
    assert (
        first_requests["worker_fresh"].control.session_snapshot.session_ids
        != retry_requests["worker_fresh"].control.session_snapshot.session_ids
    )


def test_interrupted_supervision_visit_reruns_fresh_members(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import orchestrator.workflow.executor as executor_module
    from orchestrator.state import StateManager
    from orchestrator.workflow_lisp.build import build_frontend_bundle
    from tests.test_workflow_lisp_provider_supervision_e2e import (
        _build_request,
        _copy_fixture,
    )
    from tests.workflow_bundle_helpers import bundle_context_dict

    run_id = "provider-supervision-interrupted-fresh-group"
    fixture_files = _copy_fixture(tmp_path)
    built = build_frontend_bundle(
        _build_request(tmp_path, fixture_files)
    )
    bundle = built.validated_bundle
    [projection_entry] = bundle.projection.entries_by_node_id.values()
    step_name = projection_entry.presentation_key
    step_id = projection_entry.step_id
    node_id = projection_entry.node_id
    workflow_path = fixture_files["provider_supervision_continue.orc"]
    manager = StateManager(tmp_path, run_id=run_id)
    manager.initialize(
        str(workflow_path),
        context=bundle_context_dict(bundle),
    )
    old_visit = 1
    old_member_identities = {
        role: {
            "runtime_step_id": f"{node_id}:{role}:visit:{old_visit}",
            "evidence_path": (
                manager.run_root
                / "provider-supervision"
                / node_id
                / "visits"
                / str(old_visit)
                / role
                / "evidence.json"
            ),
            "provisional_bundle_path": (
                manager.run_root
                / "provider-supervision"
                / node_id
                / "visits"
                / str(old_visit)
                / role
                / "provisional.json"
            ),
            "endpoint": f"pane:{role}:visit:{old_visit}",
            "attempt_scope": f"scope:{role}:visit:{old_visit}",
            "attempt_snapshot": f"snapshot:{role}:visit:{old_visit}",
            "attempt_ordinal": old_visit,
        }
        for role in ("worker_fresh", "supervisor_directive")
    }
    partial_evidence = old_member_identities["worker_fresh"][
        "evidence_path"
    ]
    assert isinstance(partial_evidence, Path)
    partial_evidence.parent.mkdir(parents=True, exist_ok=True)
    partial_evidence.write_text(
        '{"status":"provider_started"}',
        encoding="utf-8",
    )
    metadata_path = (
        manager.run_root
        / "provider-supervision"
        / node_id
        / "visits"
        / str(old_visit)
        / "metadata.json"
    )
    manager.write_runtime_sidecar_json(
        metadata_path,
        {
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": old_visit,
            "status": "interrupted",
            "publication_state": "quarantined_interrupted_visit",
        },
    )
    assert manager.state is not None
    manager.state.status = "failed"
    manager.state.steps = {}
    manager.state.step_visits = {step_name: old_visit}
    manager.state.current_step = None
    manager.state.error = {
        "type": "provider_supervision_interrupted_visit_quarantined",
        "message": "Historical interrupted supervision visit.",
        "context": {
            "step_name": step_name,
            "step_id": step_id,
            "visit_count": old_visit,
            "metadata_path": str(metadata_path),
        },
    }
    manager._write_state()

    created_bindings: list[_FreshResumeBindings] = []

    class _FreshResumeBindings(_EarlyArbitrationBindings):
        def __init__(
            self,
            runtime_executor: Any,
            *,
            step: Any,
            state: dict[str, Any],
            step_name: str,
        ) -> None:
            super().__init__(
                tmp_path / "fresh-supervision-group",
                directive={"variant": "CONTINUE"},
                worker_completes_naturally=True,
            )
            self.runtime_executor = runtime_executor
            self.runtime_step = step
            self.runtime_state = state
            self.step_name = step_name
            self.visit_count: int | None = None

        def derive_turn_bindings(
            self,
            *,
            config: Any,
            visit_count: int,
        ) -> dict[str, ProviderSupervisionTurnBinding]:
            self.visit_count = visit_count
            turns = super().derive_turn_bindings(
                config=config,
                visit_count=visit_count,
            )
            return {
                role: replace(
                    turn,
                    runtime_step_id=(
                        f"{config.node_id}:{role}:visit:{visit_count}"
                    ),
                    evidence_path=(
                        self.tmp_path
                        / f"visit-{visit_count}"
                        / role
                        / "evidence.json"
                    ),
                    provisional_bundle_path=(
                        self.tmp_path
                        / f"visit-{visit_count}"
                        / role
                        / "provisional.json"
                    ),
                )
                for role, turn in turns.items()
            }

        def open_observation(
            self,
            turn: ProviderSupervisionTurnBinding,
        ) -> ProviderSupervisionObservationBinding:
            observation = super().open_observation(turn)
            assert self.visit_count is not None
            return replace(
                observation,
                target=(
                    f"pane:{turn.turn_role}:visit:{self.visit_count}"
                ),
            )

        def allocate_attempt(
            self,
            *,
            turn: ProviderSupervisionTurnBinding,
            prompt: str,
        ) -> ProviderSupervisionAttemptBinding:
            del prompt
            assert self.visit_count is not None
            ordinal = (
                self.visit_count
                if turn.turn_role == "worker_fresh"
                else self.visit_count + 1
            )
            return ProviderSupervisionAttemptBinding(
                scope_key=(
                    f"scope:{turn.turn_role}:visit:{self.visit_count}"
                ),
                ordinal=ordinal,
                snapshot_key=(
                    f"snapshot:{turn.turn_role}:visit:{self.visit_count}"
                ),
            )

        def finalize_settlement(
            self,
            *,
            selected_request: ProviderSupervisionMemberRequest,
            settlement_value: Any,
            **_kwargs: Any,
        ) -> dict[str, Any]:
            return self.runtime_executor._finalize_provider_supervision_settlement(
                self.runtime_step,
                self.runtime_state,
                step_name=self.step_name,
                result={
                    "status": "completed",
                    "exit_code": 0,
                    "duration_ms": 0,
                    "artifacts": {"__result__": settlement_value},
                    "debug": {
                        "provider_supervision": {
                            "selected_attempt": {
                                "scope_key": (
                                    selected_request.attempt.scope_key
                                ),
                                "ordinal": selected_request.attempt.ordinal,
                            }
                        }
                    },
                },
            )

    def build_bindings(
        runtime_executor: Any,
        *,
        step: Any,
        state: dict[str, Any],
        step_name: str,
        **_kwargs: Any,
    ) -> _FreshResumeBindings:
        bindings = _FreshResumeBindings(
            runtime_executor,
            step=step,
            state=state,
            step_name=step_name,
        )
        created_bindings.append(bindings)
        return bindings

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "orchestrator.cli.commands.resume._load_resume_workflow_bundle",
        lambda **_kwargs: bundle,
    )
    monkeypatch.setattr(
        executor_module,
        "WorkflowProviderSupervisionBindings",
        build_bindings,
    )

    with caplog.at_level(logging.WARNING):
        result = resume_workflow(
            run_id=run_id,
            max_retries=0,
            retry_delay_ms=0,
        )

    assert result == 0
    assert len(created_bindings) == 1
    bindings = created_bindings[0]
    assert bindings.visit_count == old_visit + 1
    assert set(bindings.requests) == {
        "worker_fresh",
        "supervisor_directive",
    }
    for role, request in bindings.requests.items():
        old = old_member_identities[role]
        assert request.turn.runtime_step_id != old["runtime_step_id"]
        assert request.turn.evidence_path != old["evidence_path"]
        assert (
            request.turn.provisional_bundle_path
            != old["provisional_bundle_path"]
        )
        assert request.observation is not None
        assert request.observation.target != old["endpoint"]
        assert request.attempt.scope_key != old["attempt_scope"]
        assert request.attempt.snapshot_key != old["attempt_snapshot"]
        assert request.attempt.ordinal != old["attempt_ordinal"]
        assert request.invocation.materialize().session_request is None
    rerun_events = [
        record
        for record in caplog.records
        if record.getMessage() == "provider_attempt_interrupted_rerun"
    ]
    assert len(rerun_events) == 1
    assert rerun_events[0].provider_family == "supervision"
    assert rerun_events[0].provider_step_id == step_id
    assert rerun_events[0].discarded_visit == old_visit
    assert rerun_events[0].next_visit == old_visit + 1
    assert partial_evidence.read_text(encoding="utf-8") == (
        '{"status":"provider_started"}'
    )
