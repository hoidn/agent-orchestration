"""Private forward-only coordinator spine for phased provider delivery."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import math
from typing import Literal, NoReturn

from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    InteractiveMemberHandle,
    InteractiveTerminalError,
    InteractiveTerminalStartOutcome,
    NaturalShutdownProof,
    NoBackendAllocationProof,
    OfferReceipt,
    PhasedFailedCleanupEvidence,
    project_phased_failed_cleanup_evidence,
)

from .bindings import (
    AtomicSuccessCommitReceipt,
    AttemptAllocation,
    AttemptComposition,
    CandidatePreflight,
    CandidateResetResult,
    CandidateSnapshot,
    FrozenCandidate,
    FrozenCandidateRestoration,
    FrozenCandidateVerification,
    FunctionalEvidencePublication,
    OutputPositionValidation,
    PhaseLedger,
    PhasedOperationFailure,
    PhasedNaturalShutdownEvidence,
    PhasedProviderAttemptCoordinatorBindings,
    PhasedProviderAttemptFailure,
    PhasedProviderAttemptSuccess,
    PreparedSuccessCommit,
    SerializedAttemptEvent,
    StructuredResultValidation,
    SubmitEndpoint,
)
from .protocol import PhasedSubmitBinding
from .diagnostics import (
    DEADLINE_OPERATION_REGISTRY,
    DeadlineOperationDefinition,
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    SOURCE_PROFILES,
    diagnostic_definition,
)
from .endpoint import SubmitEndpointEvent, SubmitEndpointShutdownOutcome
from .frames import RenderedProtocolTurn, render_retry_materialization_turn
from .models import (
    AdapterReceiptProjection,
    ByteDigestProjection,
    CountDigestProjection,
    PhasedLifecycleState,
    SubmitReceipt,
    validated_start_outcome,
)


def _sha256(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _adapter_projection(
    *,
    status: str,
    handle: InteractiveMemberHandle,
) -> AdapterReceiptProjection:
    return AdapterReceiptProjection(
        status=status,
        handle_id_sha256=_sha256(handle.handle_id.encode("utf-8")),
    )


def _validate_handle(
    value: object,
    *,
    allocation: AttemptAllocation,
    composition: AttemptComposition,
) -> InteractiveMemberHandle:
    if type(value) is not InteractiveMemberHandle:
        raise TypeError("adapter start did not return an exact handle")
    handle = value
    invocation = composition.invocation
    if (
        handle.invocation_id != invocation.invocation_id
        or handle.member_id != invocation.member_id
        or handle.attempt_scope_key != allocation.scope.key
        or handle.attempt_ordinal != allocation.attempt_ordinal
    ):
        raise ValueError("adapter handle does not bind the exact attempt")
    return handle


def _validate_offer(
    value: object,
    *,
    handle: InteractiveMemberHandle,
    turn: RenderedProtocolTurn,
) -> AdapterReceiptProjection:
    if (
        type(value) is not OfferReceipt
        or value.status != "offered"
        or value.handle_id != handle.handle_id
        or value.byte_count != len(turn.delivered_turn)
        or value.content_sha256 != _sha256(turn.delivered_turn)
    ):
        raise ValueError("adapter offer receipt is invalid")
    return _adapter_projection(status="offered", handle=handle)


def _validate_close_offer(
    value: object,
    *,
    handle: InteractiveMemberHandle,
) -> AdapterReceiptProjection:
    if (
        type(value) is not CloseOfferReceipt
        or value.status != "close_offered"
        or value.handle_id != handle.handle_id
    ):
        raise ValueError("adapter close receipt is invalid")
    return _adapter_projection(status="close_offered", handle=handle)


def _validate_natural_shutdown(
    value: object,
    *,
    handle: InteractiveMemberHandle,
) -> PhasedNaturalShutdownEvidence:
    if (
        type(value) is not NaturalShutdownProof
        or value.handle_id != handle.handle_id
        or value.disposition != "natural_exit"
        or value.return_code != 0
        or value.pane_absent is not True
        or value.server_absent is not True
        or value.proof_complete is not True
    ):
        raise ValueError("natural shutdown proof is invalid")
    return PhasedNaturalShutdownEvidence(
        disposition="natural_exit",
        return_code=0,
        pane_absent=True,
        server_absent=True,
        proof_complete=True,
    )


def _close_projection(
    composition: AttemptComposition,
) -> dict[str, object]:
    close_text = composition.invocation.support.graceful_close_text.encode(
        "utf-8",
        errors="strict",
    )
    submit_keys = composition.invocation.support.graceful_close_submit_keys
    encoded_keys = json.dumps(
        list(submit_keys),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    return {
        "close_text": ByteDigestProjection(
            bytes=len(close_text),
            sha256=_sha256(close_text),
        ),
        "submit_keys": CountDigestProjection(
            count=len(submit_keys),
            sha256=_sha256(encoded_keys),
        ),
    }


def _terminal_response() -> dict[str, str]:
    return {
        "status": "failed",
        "code": "provider_phased_submit_protocol_invalid",
        "reason": "submit_lifecycle_invalid",
    }


def _runtime_diagnostic(
    reason: str,
    *,
    canonical_value: bool | int | str | None = None,
) -> PhasedDeliveryDiagnostic:
    definition = diagnostic_definition(reason)
    profile = SOURCE_PROFILES[definition.source_profile]
    if profile.primary_owner is None:
        raise ValueError("runtime diagnostic requires one primary owner")
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=canonical_value,
            summary=reason,
        ),
        primary_source=DiagnosticSource(
            kind=(
                "adapter_operation"
                if profile.primary_owner == "interactive_adapter"
                else (
                    "state_commit"
                    if profile.primary_owner == "workflow_state_commit"
                    else "runtime_attempt"
                )
            ),
            owner=profile.primary_owner,
            path=None,
            span=None,
        ),
        related_sources=tuple(
            DiagnosticSource(
                kind=(
                    "state_commit"
                    if owner == "workflow_state_commit"
                    else "runtime_attempt"
                ),
                owner=owner,
                path=None,
                span=None,
            )
            for owner in profile.related_owners
        ),
    )


_DEADLINE_OPERATIONS = {
    row.operation: row for row in DEADLINE_OPERATION_REGISTRY
}


@dataclass(frozen=True, slots=True)
class _DeadlineAdmission:
    definition: DeadlineOperationDefinition
    deadline: float


@dataclass(frozen=True, slots=True)
class _CleanupOutcome:
    status: str
    abort_calls: int
    proof: NoBackendAllocationProof | PhasedFailedCleanupEvidence | None
    diagnostic: PhasedDeliveryDiagnostic | None
    provider_zero_survivor_proven: bool


@dataclass(slots=True)
class _CoordinatorSession:
    lifecycle: PhasedLifecycleState = field(
        default_factory=lambda: PhasedLifecycleState(
            phase="ALLOCATED",
            provider_cleanup="NOT_REQUIRED",
            ingress="NOT_ALLOCATED",
            natural_join_proven=False,
            abort_calls=0,
        )
    )
    allocation: AttemptAllocation | None = None
    composition: AttemptComposition | None = None
    preflight: CandidatePreflight | None = None
    ledger: PhaseLedger | None = None
    handle: InteractiveMemberHandle | None = None
    endpoint: SubmitEndpoint | None = None
    actual_deliveries: list[RenderedProtocolTurn] = field(default_factory=list)
    output: OutputPositionValidation | None = None
    structured: StructuredResultValidation | None = None
    frozen: FrozenCandidate | None = None
    evidence: FunctionalEvidencePublication | None = None
    submission_ordinal: int = 0
    attempt_deadline: float | None = None
    start_failure_outcome: InteractiveTerminalStartOutcome | None = None
    cleanup_outcome: _CleanupOutcome | None = None
    ingress_outcome: SubmitEndpointShutdownOutcome | None = None
    ingress_shutdown_action: Literal["NOT_STARTED", "STARTED"] = (
        "NOT_STARTED"
    )
    natural_shutdown_proof: PhasedNaturalShutdownEvidence | None = None
    deadline_probe: tuple[str, str] | None = None
    ledger_channel: Literal["ABSENT", "WRITABLE", "POISONED"] = "ABSENT"


class _NeedsTerminalization(RuntimeError):
    """Private Task-9 handoff retaining the first failure and exact state."""

    def __init__(
        self,
        first_diagnostic: PhasedDeliveryDiagnostic,
        lifecycle: PhasedLifecycleState,
    ) -> None:
        if type(first_diagnostic) is not PhasedDeliveryDiagnostic:
            raise TypeError("first_diagnostic must be exact")
        if type(lifecycle) is not PhasedLifecycleState:
            raise TypeError("lifecycle must be exact")
        super().__init__(first_diagnostic.code)
        self.first_diagnostic = first_diagnostic
        self.lifecycle = lifecycle


class PhasedProviderAttemptCoordinator:
    """Execute the phased attempt spine and its closed terminalizer."""

    def __init__(
        self,
        bindings: PhasedProviderAttemptCoordinatorBindings,
    ) -> None:
        self._bindings = bindings
        self._session = _CoordinatorSession()

    @property
    def lifecycle(self) -> PhasedLifecycleState:
        return self._session.lifecycle

    def _monotonic_now(self) -> float:
        now = self._bindings.monotonic_now()
        if type(now) is not float or not math.isfinite(now):
            raise TypeError("monotonic clock must return a finite float")
        return now

    def _append(self, event: str, payload: dict[str, object]) -> None:
        if self._session.ledger_channel != "WRITABLE":
            raise PhasedOperationFailure(
                _runtime_diagnostic("evidence_append_failed")
            )
        ledger = self._session.ledger
        if ledger is None:
            raise RuntimeError("phase ledger is not prepared")
        admission = self._admit_deadline("ledger_append")
        try:
            ledger.append(
                event,
                payload,
                observed_at=self._bindings.observed_at(),
            )
        except PhasedOperationFailure:
            self._session.ledger_channel = "POISONED"
            raise
        except (OSError, RuntimeError) as exc:
            self._session.ledger_channel = "POISONED"
            raise PhasedOperationFailure(
                _runtime_diagnostic("evidence_append_failed")
            ) from exc
        self._finish_deadline(admission)

    def _safe_append(
        self,
        event: str,
        payload: dict[str, object],
    ) -> bool:
        if (
            self._session.ledger is None
            or self._session.ledger_channel != "WRITABLE"
        ):
            return False
        try:
            self._append(event, payload)
        except PhasedOperationFailure:
            return False
        return True

    def _admit_deadline(self, operation: str) -> _DeadlineAdmission:
        session = self._session
        deadline = session.attempt_deadline
        if deadline is None:
            raise RuntimeError("deadline admission requires derived deadline")
        definition = _DEADLINE_OPERATIONS[operation]
        session.deadline_probe = (operation, "before")
        try:
            now = self._monotonic_now()
        finally:
            session.deadline_probe = None
        if now >= deadline:
            raise PhasedOperationFailure(
                _runtime_diagnostic(definition.before_reason)
            )
        return _DeadlineAdmission(
            definition=definition,
            deadline=deadline,
        )

    def _finish_deadline(self, admission: _DeadlineAdmission) -> None:
        operation = admission.definition.operation
        self._session.deadline_probe = (operation, "during")
        try:
            now = self._monotonic_now()
        finally:
            self._session.deadline_probe = None
        if now >= admission.deadline:
            raise PhasedOperationFailure(
                _runtime_diagnostic(admission.definition.during_reason)
            )

    def _receive_control_event(
        self,
        *,
        boundary: str,
        deadline_operation: str,
        provider_exit_is_failure: bool,
    ) -> None:
        session = self._session
        endpoint = session.endpoint
        deadline = session.attempt_deadline
        if endpoint is None or deadline is None:
            raise RuntimeError("control-event state is incomplete")
        event = self._bindings.receive_attempt_event(
            boundary=boundary,
            endpoint=endpoint,
            deadline=deadline,
        )
        if event is None:
            return
        if type(event) is not SerializedAttemptEvent:
            raise TypeError("control boundary event must be exact")
        if event.kind == "deadline":
            definition = _DEADLINE_OPERATIONS[deadline_operation]
            raise PhasedOperationFailure(
                _runtime_diagnostic(definition.before_reason)
            )
        if event.kind == "interrupted":
            raise _NeedsTerminalization(
                _runtime_diagnostic("interrupted_nonterminal_visit"),
                session.lifecycle,
            )
        if event.kind == "provider_exit":
            if provider_exit_is_failure:
                raise _NeedsTerminalization(
                    _runtime_diagnostic("provider_exited_before_submit"),
                    session.lifecycle,
                )
            return
        raise ValueError("control boundary received an inadmissible event")

    def _terminalization_tier(self) -> str:
        session = self._session
        lifecycle = session.lifecycle
        if lifecycle.natural_join_proven:
            return "T4"
        if lifecycle.ingress == "COMPLETE":
            return "T3"
        if session.ingress_shutdown_action == "STARTED":
            if session.cleanup_outcome is None:
                return "T2a"
            return "T2b"
        if lifecycle.ingress != "NOT_ALLOCATED":
            return "T1"
        return "T0"

    def _start_ingress_shutdown_once(
        self,
        *,
        fail_safe: bool,
    ) -> None:
        session = self._session
        if session.ingress_shutdown_action == "STARTED":
            return
        payload: dict[str, object] = {
            "terminal_response": _terminal_response()
        }
        if fail_safe:
            self._safe_append("ingress_shutdown_started", payload)
        else:
            self._append("ingress_shutdown_started", payload)
        session.ingress_shutdown_action = "STARTED"

    def _finish_cleanup_once(self) -> _CleanupOutcome:
        session = self._session
        if session.cleanup_outcome is not None:
            return session.cleanup_outcome
        lifecycle = session.lifecycle
        if lifecycle.natural_join_proven:
            raise RuntimeError("post-proof cleanup is forbidden")
        proof: NoBackendAllocationProof | PhasedFailedCleanupEvidence | None
        diagnostic: PhasedDeliveryDiagnostic | None = None
        abort_calls = 0
        if session.handle is None:
            start_failure = session.start_failure_outcome
            if start_failure is None:
                candidate = (
                    self._bindings.prestart_no_backend_allocation_proof()
                )
                if type(candidate) is NoBackendAllocationProof:
                    status = "not_required"
                    proof = candidate
                    zero_survivor = True
                else:
                    status = "incomplete"
                    proof = None
                    diagnostic = _runtime_diagnostic(
                        "adapter_cleanup_failed"
                    )
                    zero_survivor = False
            else:
                proof = start_failure.proof
                if start_failure.cleanup_status == "not_required":
                    status = "not_required"
                    zero_survivor = True
                elif start_failure.cleanup_status == "completed":
                    status = "complete"
                    zero_survivor = True
                else:
                    status = "incomplete"
                    diagnostic = _runtime_diagnostic(
                        (
                            "adapter_start_cleanup_incomplete"
                            if start_failure.error_code
                            == "interactive_terminal_start_cleanup_incomplete"
                            else "provider_zero_survivor_unproven"
                        )
                    )
                    zero_survivor = False
        else:
            composition = session.composition
            if composition is None:
                raise RuntimeError("live cleanup requires attempt composition")
            try:
                cleanup_admission = self._admit_deadline(
                    "adapter_cleanup"
                )
            except PhasedOperationFailure as failure:
                abort_calls = 0
                raw_proof = None
                projected = None
                status = "incomplete"
                diagnostic = failure.diagnostic
                zero_survivor = False
            else:
                abort_calls = 1
                try:
                    raw_proof = self._bindings.adapter.abort(
                        session.handle,
                        composition.deadline,
                    )
                except InteractiveTerminalError:
                    raw_proof = None
                try:
                    self._finish_deadline(cleanup_admission)
                except PhasedOperationFailure as failure:
                    raw_proof = None
                    projected = None
                    status = "incomplete"
                    diagnostic = failure.diagnostic
                    zero_survivor = False
                else:
                    projected = project_phased_failed_cleanup_evidence(
                        raw_proof,
                        active_handle_id=session.handle.handle_id,
                    )
                    if (
                        projected is not None
                        and projected.cleanup_complete
                    ):
                        status = "complete"
                        zero_survivor = True
                    else:
                        status = "incomplete"
                        diagnostic = _runtime_diagnostic(
                            "adapter_cleanup_failed"
                        )
                        zero_survivor = False
            proof = projected
        cleanup_state = {
            "not_required": "NOT_REQUIRED",
            "complete": "COMPLETE",
            "incomplete": "INCOMPLETE",
        }[status]
        session.lifecycle = PhasedLifecycleState(
            phase="TERMINALIZING",
            provider_cleanup=cleanup_state,
            ingress=lifecycle.ingress,
            natural_join_proven=False,
            abort_calls=abort_calls,
        )
        outcome = _CleanupOutcome(
            status=status,
            abort_calls=abort_calls,
            proof=proof,
            diagnostic=diagnostic,
            provider_zero_survivor_proven=zero_survivor,
        )
        session.cleanup_outcome = outcome
        self._safe_append(
            "cleanup_finished",
            {
                "cleanup_status": outcome.status,
                "abort_calls": outcome.abort_calls,
                "provider_cleanup_proof": outcome.proof,
                "cleanup_diagnostic": outcome.diagnostic,
                "provider_zero_survivor_proven": (
                    outcome.provider_zero_survivor_proven
                ),
            },
        )
        return outcome

    def _finish_ingress_once(self) -> str:
        session = self._session
        lifecycle = session.lifecycle
        if lifecycle.ingress == "NOT_ALLOCATED":
            return "not_allocated"
        if lifecycle.ingress == "COMPLETE":
            return "complete"
        if lifecycle.ingress == "INCOMPLETE":
            return "incomplete"
        endpoint = session.endpoint
        composition = session.composition
        if endpoint is None or composition is None:
            raise RuntimeError("allocated ingress state is incomplete")
        terminal_response = _terminal_response()
        self._start_ingress_shutdown_once(fail_safe=True)
        outcome = session.ingress_outcome
        if outcome is None:
            endpoint.stop_admission()
            outcome = endpoint.shutdown(deadline=composition.deadline)
            if type(outcome) is not SubmitEndpointShutdownOutcome:
                raise TypeError("endpoint shutdown outcome must be exact")
            session.ingress_outcome = outcome
        complete = outcome.endpoint_zero_survivor_proven is True
        ingress_state = "COMPLETE" if complete else "INCOMPLETE"
        session.lifecycle = PhasedLifecycleState(
            phase="TERMINALIZING",
            provider_cleanup=lifecycle.provider_cleanup,
            ingress=ingress_state,
            natural_join_proven=False,
            abort_calls=lifecycle.abort_calls,
        )
        payload: dict[str, object] = {
            "terminal_response": terminal_response,
            "queued_requests_rejected": outcome.queued_requests_rejected,
            "active_requests_drained": outcome.active_requests_drained,
            "listener_closed": outcome.listener_closed,
            "workers_joined": outcome.workers_joined,
            "endpoint_zero_survivor_proven": complete,
        }
        if complete:
            self._safe_append("ingress_shutdown_finished", payload)
            return "complete"
        payload["diagnostic"] = _runtime_diagnostic(
            "ingress_shutdown_failed"
        )
        self._safe_append("ingress_shutdown_failed", payload)
        return "incomplete"

    def _terminalize(
        self,
        handoff: _NeedsTerminalization,
    ) -> PhasedProviderAttemptFailure:
        session = self._session
        allocation = session.allocation
        if allocation is None:
            raise RuntimeError("terminalization requires attempt allocation")
        tier = self._terminalization_tier()
        if session.lifecycle.natural_join_proven:
            cleanup = None
            endpoint_status = self._finish_ingress_once()
            cleanup_status = "not_permitted"
            cleanup_diagnostic = None
            cleanup_proof = None
        else:
            cleanup = self._finish_cleanup_once()
            endpoint_status = self._finish_ingress_once()
            cleanup_status = cleanup.status
            cleanup_diagnostic = cleanup.diagnostic
            cleanup_proof = cleanup.proof
        lifecycle = session.lifecycle
        session.lifecycle = PhasedLifecycleState(
            phase="FAILED",
            provider_cleanup=(
                "NOT_REQUIRED"
                if lifecycle.natural_join_proven
                else lifecycle.provider_cleanup
            ),
            ingress=lifecycle.ingress,
            natural_join_proven=lifecycle.natural_join_proven,
            abort_calls=lifecycle.abort_calls,
        )
        natural = session.natural_shutdown_proof
        self._safe_append(
            "terminal_failed",
            {
                "diagnostic": handoff.first_diagnostic,
                "cleanup_status": cleanup_status,
                "cleanup_diagnostic": cleanup_diagnostic,
                "endpoint_shutdown_status": endpoint_status,
                "natural_shutdown_proof": (
                    None if natural is None else natural.to_dict()
                ),
            },
        )
        failure = PhasedProviderAttemptFailure(
            allocation=allocation,
            lifecycle=session.lifecycle,
            first_diagnostic=handoff.first_diagnostic,
            cleanup_diagnostic=cleanup_diagnostic,
            provider_cleanup_proof=cleanup_proof,
            endpoint_shutdown_status=endpoint_status,
            natural_shutdown_proof=natural,
            terminalization_tier=tier,
            frozen=session.frozen,
            evidence=session.evidence,
        )
        self._bindings.finalize_failure(
            failure.first_diagnostic,
            failure.lifecycle,
        )
        if session.ledger is not None:
            session.ledger.close()
        return failure

    def _handoff_active(
        self,
        event: SubmitEndpointEvent,
        failure: PhasedOperationFailure,
    ) -> NoReturn:
        session = self._session
        allocation = session.allocation
        composition = session.composition
        endpoint = session.endpoint
        if allocation is None or composition is None or endpoint is None:
            raise RuntimeError("active failure state is incomplete")
        endpoint.resolve(
            event,
            SubmitReceipt(
                status="failed",
                attempt_scope_sha256=allocation.scope.key,
                client_request_id=event.request.client_request_id,
                submission_ordinal=event.submission_ordinal,
                configured_total=composition.materialization_attempts,
                remaining_submissions=(
                    composition.materialization_attempts
                    - event.submission_ordinal
                ),
                diagnostic=failure.diagnostic,
            ),
        )
        raise _NeedsTerminalization(
            failure.diagnostic,
            session.lifecycle,
        )

    def _prepare_and_offer_initial(self) -> None:
        session = self._session
        allocation = session.allocation
        composition = session.composition
        if allocation is None or composition is None:
            raise RuntimeError("attempt preparation is incomplete")
        if (
            composition.submit_binding.attempt_scope_sha256
            != allocation.scope.key
            or composition.invocation.attempt_scope_key
            != allocation.scope.key
            or composition.invocation.attempt_ordinal
            != allocation.attempt_ordinal
        ):
            raise ValueError("attempt composition identity is inconsistent")

        session.lifecycle = PhasedLifecycleState(
            phase="STARTING",
            provider_cleanup="PENDING",
            ingress="NOT_ALLOCATED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "task_start_requested",
            {"turn": composition.task_turn.projection},
        )
        start_admission = self._admit_deadline("adapter_start")
        try:
            start = validated_start_outcome(
                self._bindings.adapter.start(
                    composition.invocation,
                    deadline=composition.deadline,
                )
            )
            handle = (
                None
                if start.status != "started"
                else _validate_handle(
                    start.handle,
                    allocation=allocation,
                    composition=composition,
                )
            )
        except (TypeError, ValueError):
            self._finish_deadline(start_admission)
            raise
        if start.status != "started":
            session.start_failure_outcome = start
            self._finish_deadline(start_admission)
            failure = _runtime_diagnostic("adapter_start_failed")
            self._safe_append(
                "task_start_failed",
                {
                    "turn": composition.task_turn.projection,
                    "diagnostic": failure,
                    "start_failure_outcome": start,
                },
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            )
        assert handle is not None
        session.handle = handle
        session.actual_deliveries.append(composition.task_turn)
        session.lifecycle = PhasedLifecycleState(
            phase="LIVE",
            provider_cleanup="PENDING",
            ingress="NOT_ALLOCATED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._finish_deadline(start_admission)
        self._append(
            "task_started",
            {
                "turn": composition.task_turn.projection,
                "receipt": _adapter_projection(
                    status="started",
                    handle=handle,
                ),
            },
        )

        endpoint_admission = self._admit_deadline(
            "submit_endpoint_allocation"
        )
        try:
            endpoint = self._bindings.create_endpoint(composition)
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._finish_deadline(endpoint_admission)
            failure = _runtime_diagnostic(
                "submit_endpoint_allocation_failed"
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
        session.endpoint = endpoint
        session.lifecycle = PhasedLifecycleState(
            phase="LIVE",
            provider_cleanup="PENDING",
            ingress="NOT_STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        try:
            if (
                type(endpoint.binding) is not PhasedSubmitBinding
                or endpoint.binding != composition.submit_binding
            ):
                raise ValueError(
                    "endpoint binding must be exact and equal "
                    "composition binding"
                )
            endpoint.start()
            session.lifecycle = PhasedLifecycleState(
                phase="LIVE",
                provider_cleanup="PENDING",
                ingress="STARTED",
                natural_join_proven=False,
                abort_calls=0,
            )
            endpoint.open_admission("INITIAL_MATERIALIZATION_QUEUED")
        except PhasedOperationFailure:
            self._finish_deadline(endpoint_admission)
            raise
        except (OSError, RuntimeError, TypeError, ValueError) as exc:
            self._finish_deadline(endpoint_admission)
            failure = _runtime_diagnostic(
                "submit_endpoint_allocation_failed"
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
        self._finish_deadline(endpoint_admission)
        initial = composition.initial_materialization_turn
        session.lifecycle = PhasedLifecycleState(
            phase="INITIAL_MATERIALIZATION_QUEUED",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._receive_control_event(
            boundary="BEFORE_INITIAL_OFFER",
            deadline_operation="initial_offer",
            provider_exit_is_failure=True,
        )
        self._append(
            "turn_offer_requested",
            {"turn": initial.projection},
        )
        offer_admission = self._admit_deadline("initial_offer")
        try:
            offered = self._bindings.adapter.offer(
                handle,
                initial.delivered_turn.decode("utf-8", errors="strict"),
                deadline=composition.deadline,
            )
            projection = _validate_offer(
                offered,
                handle=handle,
                turn=initial,
            )
        except (InteractiveTerminalError, TypeError, ValueError) as exc:
            self._finish_deadline(offer_admission)
            failure = _runtime_diagnostic("initial_offer_failed")
            self._safe_append(
                "turn_offer_failed",
                {"turn": initial.projection, "diagnostic": failure},
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
        self._finish_deadline(offer_admission)
        session.actual_deliveries.append(initial)
        self._append(
            "turn_offered",
            {"turn": initial.projection, "receipt": projection},
        )

    def _validate_submission(self) -> SubmitEndpointEvent:
        session = self._session
        composition = session.composition
        preflight = session.preflight
        endpoint = session.endpoint
        if composition is None or preflight is None or endpoint is None:
            raise RuntimeError("submit validation state is incomplete")
        submit_admission = self._admit_deadline("submit")
        try:
            serialized = self._bindings.receive_attempt_event(
                boundary="AWAITING_SUBMIT",
                endpoint=endpoint,
                deadline=composition.deadline,
            )
        except PhasedOperationFailure:
            self._finish_deadline(submit_admission)
            raise
        if type(serialized) is not SerializedAttemptEvent:
            self._finish_deadline(submit_admission)
            raise TypeError("submit boundary requires exact attempt event")
        if serialized.kind == "provider_exit":
            self._finish_deadline(submit_admission)
            raise _NeedsTerminalization(
                _runtime_diagnostic("provider_exited_before_submit"),
                session.lifecycle,
            )
        if serialized.kind == "interrupted":
            self._finish_deadline(submit_admission)
            raise _NeedsTerminalization(
                _runtime_diagnostic("interrupted_nonterminal_visit"),
                session.lifecycle,
            )
        if serialized.kind == "deadline":
            raise _NeedsTerminalization(
                _runtime_diagnostic(
                    submit_admission.definition.during_reason
                ),
                session.lifecycle,
            )
        event = serialized.submit
        assert event is not None
        session.submission_ordinal = event.submission_ordinal
        session.lifecycle = PhasedLifecycleState(
            phase="VALIDATING",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "submit_received",
            {
                "client_request_id_sha256": _sha256(
                    event.request.client_request_id.encode("utf-8")
                ),
                "submission_ordinal": event.submission_ordinal,
                "configured_total": composition.materialization_attempts,
                "remaining_before": (
                    composition.materialization_attempts
                    - event.submission_ordinal
                    + 1
                ),
            },
        )
        try:
            snapshot = self._bindings.snapshot_candidates(
                preflight,
                event.submission_ordinal,
            )
        except PhasedOperationFailure as failure:
            self._finish_deadline(submit_admission)
            self._handoff_active(event, failure)
        self._finish_deadline(submit_admission)
        if (
            type(snapshot) is not CandidateSnapshot
            or snapshot.preflight_sha256 != preflight.preflight_sha256
            or snapshot.submission_ordinal != event.submission_ordinal
        ):
            raise ValueError("candidate snapshot predecessor is invalid")
        validation_admission = self._admit_deadline("validation")
        try:
            output = self._bindings.validate_output_positions(snapshot)
        except PhasedOperationFailure as failure:
            self._finish_deadline(validation_admission)
            self._handoff_active(event, failure)
        try:
            structured = self._bindings.validate_structured_result(snapshot)
        except PhasedOperationFailure as failure:
            self._finish_deadline(validation_admission)
            self._handoff_active(event, failure)
        self._finish_deadline(validation_admission)
        if (
            type(output) is not OutputPositionValidation
            or output.snapshot_sha256 != snapshot.snapshot_sha256
        ):
            raise ValueError("output validation predecessor is invalid")
        if (
            type(structured) is not StructuredResultValidation
            or structured.snapshot_sha256 != snapshot.snapshot_sha256
        ):
            raise ValueError("structured validation predecessor is invalid")
        if not output.valid or not structured.valid:
            self._reject_or_retry(
                event,
                snapshot,
                output,
                structured,
            )
            return self._validate_submission()
        freeze_admission = self._admit_deadline("candidate_freeze")
        try:
            frozen = self._bindings.freeze_candidate(
                snapshot,
                output,
                structured,
            )
        except PhasedOperationFailure as failure:
            self._finish_deadline(freeze_admission)
            self._handoff_active(event, failure)
        self._finish_deadline(freeze_admission)
        if (
            type(frozen) is not FrozenCandidate
            or frozen.snapshot_sha256 != snapshot.snapshot_sha256
            or frozen.manifest != snapshot.manifest("frozen")
        ):
            raise ValueError("frozen candidate predecessor is invalid")
        session.output = output
        session.structured = structured
        session.frozen = frozen
        session.lifecycle = PhasedLifecycleState(
            phase="VALID_FROZEN",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "candidate_frozen",
            {
                "submission_ordinal": event.submission_ordinal,
                "candidate_manifest": frozen.manifest,
            },
        )
        return event

    def _reject_or_retry(
        self,
        event: SubmitEndpointEvent,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> None:
        session = self._session
        allocation = session.allocation
        composition = session.composition
        endpoint = session.endpoint
        handle = session.handle
        if (
            allocation is None
            or composition is None
            or endpoint is None
            or handle is None
        ):
            raise RuntimeError("retry state is incomplete")
        diagnostics = tuple(
            diagnostic
            for diagnostic in (output.diagnostic, structured.diagnostic)
            if diagnostic is not None
        )
        if not diagnostics:
            raise ValueError("rejected validation requires diagnostics")
        self._append(
            "validation_rejected",
            {
                "submission_ordinal": event.submission_ordinal,
                "diagnostics": diagnostics,
                "candidate_manifest": snapshot.manifest("rejected"),
            },
        )
        reset_admission = self._admit_deadline("candidate_reset")
        try:
            reset = self._bindings.reset_candidates(snapshot)
        except PhasedOperationFailure as failure:
            self._finish_deadline(reset_admission)
            self._handoff_active(event, failure)
        self._finish_deadline(reset_admission)
        if (
            type(reset) is not CandidateResetResult
            or reset.snapshot_sha256 != snapshot.snapshot_sha256
            or reset.preflight_sha256 != snapshot.preflight_sha256
            or reset.postcondition != "all_bound_paths_absent"
        ):
            raise ValueError("candidate reset predecessor is invalid")
        self._append(
            "candidate_reset",
            {
                "submission_ordinal": event.submission_ordinal,
                "postcondition": reset.postcondition,
            },
        )
        if event.submission_ordinal == composition.materialization_attempts:
            failure = _runtime_diagnostic(
                "materialization_attempts_exhausted",
                canonical_value=composition.materialization_attempts,
            )
            endpoint.resolve(
                event,
                SubmitReceipt(
                    status="failed",
                    attempt_scope_sha256=allocation.scope.key,
                    client_request_id=event.request.client_request_id,
                    submission_ordinal=event.submission_ordinal,
                    configured_total=composition.materialization_attempts,
                    remaining_submissions=0,
                    diagnostic=failure,
                ),
            )
            raise _NeedsTerminalization(failure, session.lifecycle)

        next_ordinal = event.submission_ordinal + 1
        self._receive_control_event(
            boundary="BEFORE_RETRY_OFFER",
            deadline_operation="retry_offer",
            provider_exit_is_failure=True,
        )
        retry_turn = render_retry_materialization_turn(
            cut=composition.cut,
            submission_ordinal=next_ordinal,
            diagnostics=diagnostics,
            submit_keys=(
                composition.invocation.support.message_submit_keys
            ),
        )
        session.lifecycle = PhasedLifecycleState(
            phase="RETRY_QUEUED",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "retry_queued",
            {
                "rejected_submission_ordinal": event.submission_ordinal,
                "next_submission_ordinal": next_ordinal,
                "turn": retry_turn.projection,
            },
        )
        self._append(
            "turn_offer_requested",
            {"turn": retry_turn.projection},
        )
        offer_admission = self._admit_deadline("retry_offer")
        try:
            offered = self._bindings.adapter.offer(
                handle,
                retry_turn.delivered_turn.decode("utf-8", errors="strict"),
                deadline=composition.deadline,
            )
            projection = _validate_offer(
                offered,
                handle=handle,
                turn=retry_turn,
            )
        except (InteractiveTerminalError, TypeError, ValueError) as exc:
            self._finish_deadline(offer_admission)
            failure = _runtime_diagnostic("retry_offer_failed")
            self._safe_append(
                "turn_offer_failed",
                {"turn": retry_turn.projection, "diagnostic": failure},
            )
            try:
                self._handoff_active(
                    event,
                    PhasedOperationFailure(failure),
                )
            except _NeedsTerminalization as handoff:
                raise handoff from exc
        self._finish_deadline(offer_admission)
        session.actual_deliveries.append(retry_turn)
        self._append(
            "turn_offered",
            {"turn": retry_turn.projection, "receipt": projection},
        )
        endpoint.resolve(
            event,
            SubmitReceipt(
                status="retry_queued",
                attempt_scope_sha256=allocation.scope.key,
                client_request_id=event.request.client_request_id,
                submission_ordinal=event.submission_ordinal,
                configured_total=composition.materialization_attempts,
                remaining_submissions=(
                    composition.materialization_attempts
                    - event.submission_ordinal
                ),
                diagnostic=None,
            ),
            rearm_retry=True,
        )

    def _close_and_join(self, event: SubmitEndpointEvent) -> None:
        session = self._session
        allocation = session.allocation
        composition = session.composition
        handle = session.handle
        endpoint = session.endpoint
        if (
            allocation is None
            or composition is None
            or handle is None
            or endpoint is None
        ):
            raise RuntimeError("close state is incomplete")
        self._receive_control_event(
            boundary="VALID_FROZEN",
            deadline_operation="close_offer",
            provider_exit_is_failure=False,
        )
        close_projection = _close_projection(composition)
        session.lifecycle = PhasedLifecycleState(
            phase="CLOSING",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "close_offer_requested",
            {
                "submission_ordinal": event.submission_ordinal,
                "close_projection": close_projection,
            },
        )
        close_admission = self._admit_deadline("close_offer")
        try:
            close = self._bindings.adapter.offer_close(
                handle,
                deadline=composition.deadline,
            )
            close_receipt = _validate_close_offer(close, handle=handle)
        except (InteractiveTerminalError, TypeError, ValueError) as exc:
            self._finish_deadline(close_admission)
            failure = _runtime_diagnostic("close_offer_failed")
            self._safe_append(
                "close_offer_failed",
                {
                    "submission_ordinal": event.submission_ordinal,
                    "close_projection": close_projection,
                    "diagnostic": failure,
                },
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
        self._finish_deadline(close_admission)
        self._append(
            "close_offered",
            {
                "submission_ordinal": event.submission_ordinal,
                "close_projection": close_projection,
                "receipt": close_receipt,
            },
        )
        endpoint.resolve(
            event,
            SubmitReceipt(
                status="accepted_closing",
                attempt_scope_sha256=allocation.scope.key,
                client_request_id=event.request.client_request_id,
                submission_ordinal=event.submission_ordinal,
                configured_total=composition.materialization_attempts,
                remaining_submissions=(
                    composition.materialization_attempts
                    - event.submission_ordinal
                ),
                diagnostic=None,
            ),
        )
        session.lifecycle = PhasedLifecycleState(
            phase="INGRESS_STOPPING",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        terminal_response = _terminal_response()
        ingress_admission = self._admit_deadline("ingress_shutdown")
        self._start_ingress_shutdown_once(fail_safe=False)
        endpoint.stop_admission()
        outcome = endpoint.shutdown(deadline=composition.deadline)
        if type(outcome) is not SubmitEndpointShutdownOutcome:
            self._finish_deadline(ingress_admission)
            raise TypeError("endpoint shutdown outcome must be exact")
        session.ingress_outcome = outcome
        self._finish_deadline(ingress_admission)
        if (
            outcome.endpoint_zero_survivor_proven is not True
        ):
            failure = _runtime_diagnostic("ingress_shutdown_failed")
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            )
        session.lifecycle = PhasedLifecycleState(
            phase="JOINING",
            provider_cleanup="PENDING",
            ingress="COMPLETE",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "ingress_shutdown_finished",
            {
                "terminal_response": terminal_response,
                "queued_requests_rejected": outcome.queued_requests_rejected,
                "active_requests_drained": outcome.active_requests_drained,
                "listener_closed": outcome.listener_closed,
                "workers_joined": outcome.workers_joined,
                "endpoint_zero_survivor_proven": True,
            },
        )
        self._append(
            "join_started",
            {
                "submission_ordinal": event.submission_ordinal,
                "remaining_budget_ms": max(
                    0,
                    int(
                        (
                            composition.deadline
                            - self._monotonic_now()
                        )
                        * 1000
                    ),
                ),
            },
        )
        join_admission = self._admit_deadline("natural_join")
        try:
            natural = self._bindings.adapter.join(
                handle,
                composition.deadline,
            )
            natural_projection = _validate_natural_shutdown(
                natural,
                handle=handle,
            )
        except (InteractiveTerminalError, TypeError, ValueError) as exc:
            self._finish_deadline(join_admission)
            failure = _runtime_diagnostic("natural_join_failed")
            self._safe_append(
                "join_failed",
                {
                    "submission_ordinal": event.submission_ordinal,
                    "diagnostic": failure,
                },
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
        session.natural_shutdown_proof = natural_projection
        session.lifecycle = PhasedLifecycleState(
            phase="JOINED_PENDING_COMMIT",
            provider_cleanup="NOT_REQUIRED",
            ingress="COMPLETE",
            natural_join_proven=True,
            abort_calls=0,
        )
        self._finish_deadline(join_admission)
        self._append(
            "join_succeeded",
            {
                "submission_ordinal": event.submission_ordinal,
                "natural_shutdown_proof": natural_projection.to_dict(),
            },
        )

    def _publish(self) -> PhasedProviderAttemptSuccess:
        session = self._session
        allocation = session.allocation
        output = session.output
        structured = session.structured
        frozen = session.frozen
        if (
            allocation is None
            or output is None
            or structured is None
            or structured.result is None
            or frozen is None
        ):
            raise RuntimeError("publication state is incomplete")
        endpoint = session.endpoint
        composition = session.composition
        if endpoint is None or composition is None:
            raise RuntimeError("publication event state is incomplete")
        self._receive_control_event(
            boundary="JOINED_PENDING_COMMIT",
            deadline_operation="ledger_append",
            provider_exit_is_failure=False,
        )
        self._append(
            "publication_started",
            {"submission_ordinal": session.submission_ordinal},
        )
        deliveries = tuple(session.actual_deliveries)
        evidence_admission = self._admit_deadline(
            "evidence_publication"
        )
        try:
            evidence = self._bindings.publish_functional_evidence(
                frozen,
                deliveries,
            )
        except PhasedOperationFailure as failure:
            self._finish_deadline(evidence_admission)
            self._handoff_publication(failure)
        self._finish_deadline(evidence_admission)
        if type(evidence) is not FunctionalEvidencePublication:
            raise TypeError("evidence publication result must be exact")
        expected_evidence = FunctionalEvidencePublication.create(
            frozen=frozen,
            actual_deliveries=deliveries,
            relative_path=evidence.relative_path,
            evidence_sha256=evidence.evidence_sha256,
        )
        if evidence != expected_evidence:
            raise ValueError("evidence publication predecessor is invalid")
        session.evidence = evidence
        restoration_admission = self._admit_deadline(
            "frozen_restoration"
        )
        try:
            restoration = self._bindings.restore_frozen_candidate(frozen)
        except PhasedOperationFailure as failure:
            self._finish_deadline(restoration_admission)
            self._handoff_publication(failure)
        self._finish_deadline(restoration_admission)
        if (
            type(restoration) is not FrozenCandidateRestoration
            or restoration.frozen_sha256 != frozen.frozen_sha256
            or restoration.restored_paths != len(frozen.files)
        ):
            raise ValueError("restoration predecessor is invalid")
        verification_admission = self._admit_deadline(
            "frozen_verification"
        )
        try:
            verification = self._bindings.verify_frozen_candidate(
                frozen,
                restoration,
            )
        except PhasedOperationFailure as failure:
            self._finish_deadline(verification_admission)
            self._handoff_publication(failure)
        self._finish_deadline(verification_admission)
        if (
            type(verification) is not FrozenCandidateVerification
            or verification.frozen_sha256 != frozen.frozen_sha256
            or verification.verified is not True
        ):
            raise ValueError("verification predecessor is invalid")
        state_admission = self._admit_deadline("state_commit")
        try:
            prepared = self._bindings.prepare_success_commit(
                allocation=allocation,
                output=output,
                structured=structured,
                frozen=frozen,
                evidence=evidence,
                verification=verification,
            )
        except PhasedOperationFailure as failure:
            self._finish_deadline(state_admission)
            self._handoff_publication(failure)
        self._finish_deadline(state_admission)
        expected_prepared = PreparedSuccessCommit(
            allocation=allocation,
            output=output,
            structured=structured,
            frozen=frozen,
            evidence=evidence,
            verification=verification,
        )
        if type(prepared) is not PreparedSuccessCommit:
            raise TypeError("prepared success commit must be exact")
        if prepared != expected_prepared:
            raise ValueError(
                "prepared success commit predecessor is invalid"
            )
        try:
            commit = self._bindings.atomic_success_commit(
                prepared,
                deadline=composition.deadline,
            )
        except PhasedOperationFailure as failure:
            self._handoff_publication(failure)
        if (
            type(commit) is not AtomicSuccessCommitReceipt
            or commit.evidence_sha256 != evidence.evidence_sha256
            or commit.frozen_sha256 != frozen.frozen_sha256
        ):
            raise ValueError("atomic commit predecessor is invalid")
        session.lifecycle = PhasedLifecycleState(
            phase="PUBLISHED",
            provider_cleanup="NOT_REQUIRED",
            ingress="COMPLETE",
            natural_join_proven=True,
            abort_calls=0,
        )
        self._safe_append(
            "publication_succeeded",
            {
                "submission_ordinal": session.submission_ordinal,
                "commit_status": commit.status,
            },
        )
        return PhasedProviderAttemptSuccess(
            allocation=allocation,
            lifecycle=session.lifecycle,
            submission_ordinal=session.submission_ordinal,
            actual_deliveries=deliveries,
            frozen=frozen,
            evidence=evidence,
            commit=commit,
        )

    def _handoff_publication(
        self,
        failure: PhasedOperationFailure,
    ) -> NoReturn:
        self._safe_append(
            "publication_failed",
            {
                "submission_ordinal": self._session.submission_ordinal,
                "diagnostic": failure.diagnostic,
            },
        )
        raise _NeedsTerminalization(
            failure.diagnostic,
            self._session.lifecycle,
        ) from failure

    def run(
        self,
    ) -> PhasedProviderAttemptSuccess | PhasedProviderAttemptFailure:
        allocation = self._bindings.allocate_attempt()
        if type(allocation) is not AttemptAllocation:
            raise TypeError("allocate_attempt must return an exact allocation")
        self._session.allocation = allocation
        deadline = self._bindings.derive_attempt_deadline(allocation)
        if type(deadline) is not float or not math.isfinite(deadline):
            raise TypeError("derived deadline must be a finite number")
        self._session.attempt_deadline = deadline
        try:
            preparation_admission = self._admit_deadline("preparation")
            try:
                composition = self._bindings.compose_attempt(
                    allocation,
                    deadline=deadline,
                )
                if type(composition) is not AttemptComposition:
                    raise TypeError(
                        "compose_attempt must return an exact composition"
                    )
                if composition.deadline != deadline:
                    raise ValueError(
                        "composition deadline must equal derived deadline"
                    )
                self._session.composition = composition
                preflight = self._bindings.preflight_candidates(composition)
                if type(preflight) is not CandidatePreflight:
                    raise TypeError(
                        "preflight_candidates must return exact preflight"
                    )
            except PhasedOperationFailure as failure:
                self._finish_deadline(preparation_admission)
                raise _NeedsTerminalization(
                    failure.diagnostic,
                    self._session.lifecycle,
                ) from failure
            except (TypeError, ValueError):
                self._finish_deadline(preparation_admission)
                raise
            self._finish_deadline(preparation_admission)
            self._session.preflight = preflight
            ledger_admission = self._admit_deadline("ledger_append")
            try:
                ledger = self._bindings.create_ledger(
                    allocation,
                    composition,
                )
            except (OSError, RuntimeError) as exc:
                self._finish_deadline(ledger_admission)
                raise PhasedOperationFailure(
                    _runtime_diagnostic("evidence_append_failed")
                ) from exc
            self._session.ledger = ledger
            self._session.ledger_channel = "WRITABLE"
            self._finish_deadline(ledger_admission)
            self._prepare_and_offer_initial()
            event = self._validate_submission()
            self._close_and_join(event)
            result = self._publish()
        except PhasedOperationFailure as failure:
            handoff = _NeedsTerminalization(
                failure.diagnostic,
                self._session.lifecycle,
            )
            return self._terminalize(handoff)
        except _NeedsTerminalization as handoff:
            return self._terminalize(handoff)
        ledger = self._session.ledger
        if ledger is not None:
            ledger.close()
        return result


__all__ = ["PhasedProviderAttemptCoordinator"]
