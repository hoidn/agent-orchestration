"""Private forward-only coordinator spine for phased provider delivery."""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import time
from typing import NoReturn

from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    InteractiveMemberHandle,
    InteractiveTerminalError,
    InteractiveTerminalStartOutcome,
    NaturalShutdownProof,
    OfferReceipt,
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
    PhasedProviderAttemptCoordinatorBindings,
    PhasedProviderAttemptSuccess,
    StructuredResultValidation,
    SubmitEndpoint,
)
from .protocol import PhasedSubmitBinding
from .diagnostics import (
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
) -> dict[str, object]:
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
    return {
        "disposition": "natural_exit",
        "return_code": 0,
        "pane_absent": True,
        "server_absent": True,
        "proof_complete": True,
    }


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
    """Execute only Task-8's success/retry/publication forward spine."""

    def __init__(
        self,
        bindings: PhasedProviderAttemptCoordinatorBindings,
    ) -> None:
        self._bindings = bindings
        self._session = _CoordinatorSession()

    @property
    def lifecycle(self) -> PhasedLifecycleState:
        return self._session.lifecycle

    def _append(self, event: str, payload: dict[str, object]) -> None:
        ledger = self._session.ledger
        if ledger is None:
            raise RuntimeError("phase ledger is not prepared")
        ledger.append(
            event,
            payload,
            observed_at=self._bindings.observed_at(),
        )

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
        start = validated_start_outcome(
            self._bindings.adapter.start(
                composition.invocation,
                deadline=composition.deadline,
            )
        )
        if start.status != "started":
            raise RuntimeError("Task 9 owns failed-start terminalization")
        handle = _validate_handle(
            start.handle,
            allocation=allocation,
            composition=composition,
        )
        session.handle = handle
        session.actual_deliveries.append(composition.task_turn)
        session.lifecycle = PhasedLifecycleState(
            phase="LIVE",
            provider_cleanup="PENDING",
            ingress="NOT_ALLOCATED",
            natural_join_proven=False,
            abort_calls=0,
        )
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

        endpoint = self._bindings.create_endpoint(composition)
        if (
            type(endpoint.binding) is not PhasedSubmitBinding
            or endpoint.binding != composition.submit_binding
        ):
            raise ValueError(
                "endpoint binding must be exact and equal composition binding"
            )
        session.endpoint = endpoint
        session.lifecycle = PhasedLifecycleState(
            phase="LIVE",
            provider_cleanup="PENDING",
            ingress="NOT_STARTED",
            natural_join_proven=False,
            abort_calls=0,
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
        initial = composition.initial_materialization_turn
        session.lifecycle = PhasedLifecycleState(
            phase="INITIAL_MATERIALIZATION_QUEUED",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        )
        self._append(
            "turn_offer_requested",
            {"turn": initial.projection},
        )
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
            failure = _runtime_diagnostic("initial_offer_failed")
            self._append(
                "turn_offer_failed",
                {"turn": initial.projection, "diagnostic": failure},
            )
            raise _NeedsTerminalization(
                failure,
                session.lifecycle,
            ) from exc
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
        event = endpoint.receive_event(deadline=composition.deadline)
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
            self._handoff_active(event, failure)
        if (
            type(snapshot) is not CandidateSnapshot
            or snapshot.preflight_sha256 != preflight.preflight_sha256
            or snapshot.submission_ordinal != event.submission_ordinal
        ):
            raise ValueError("candidate snapshot predecessor is invalid")
        try:
            output = self._bindings.validate_output_positions(snapshot)
        except PhasedOperationFailure as failure:
            self._handoff_active(event, failure)
        if (
            type(output) is not OutputPositionValidation
            or output.snapshot_sha256 != snapshot.snapshot_sha256
        ):
            raise ValueError("output validation predecessor is invalid")
        try:
            structured = self._bindings.validate_structured_result(snapshot)
        except PhasedOperationFailure as failure:
            self._handoff_active(event, failure)
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
        try:
            frozen = self._bindings.freeze_candidate(
                snapshot,
                output,
                structured,
            )
        except PhasedOperationFailure as failure:
            self._handoff_active(event, failure)
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
        try:
            reset = self._bindings.reset_candidates(snapshot)
        except PhasedOperationFailure as failure:
            self._handoff_active(event, failure)
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
            failure = _runtime_diagnostic("retry_offer_failed")
            self._append(
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
        close = self._bindings.adapter.offer_close(
            handle,
            deadline=composition.deadline,
        )
        close_receipt = _validate_close_offer(close, handle=handle)
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
        self._append(
            "ingress_shutdown_started",
            {"terminal_response": terminal_response},
        )
        endpoint.stop_admission()
        outcome = endpoint.shutdown(deadline=composition.deadline)
        if (
            type(outcome) is not SubmitEndpointShutdownOutcome
            or outcome.endpoint_zero_survivor_proven is not True
        ):
            raise RuntimeError("Task 9 owns incomplete ingress terminalization")
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
                    int((composition.deadline - time.monotonic()) * 1000),
                ),
            },
        )
        natural = self._bindings.adapter.join(
            handle,
            composition.deadline,
        )
        natural_projection = _validate_natural_shutdown(
            natural,
            handle=handle,
        )
        session.lifecycle = PhasedLifecycleState(
            phase="JOINED_PENDING_COMMIT",
            provider_cleanup="NOT_REQUIRED",
            ingress="COMPLETE",
            natural_join_proven=True,
            abort_calls=0,
        )
        self._append(
            "join_succeeded",
            {
                "submission_ordinal": event.submission_ordinal,
                "natural_shutdown_proof": natural_projection,
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
        self._append(
            "publication_started",
            {"submission_ordinal": session.submission_ordinal},
        )
        deliveries = tuple(session.actual_deliveries)
        try:
            evidence = self._bindings.publish_functional_evidence(
                frozen,
                deliveries,
            )
        except PhasedOperationFailure as failure:
            raise _NeedsTerminalization(
                failure.diagnostic,
                session.lifecycle,
            ) from failure
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
        try:
            restoration = self._bindings.restore_frozen_candidate(frozen)
        except PhasedOperationFailure as failure:
            raise _NeedsTerminalization(
                failure.diagnostic,
                session.lifecycle,
            ) from failure
        if (
            type(restoration) is not FrozenCandidateRestoration
            or restoration.frozen_sha256 != frozen.frozen_sha256
            or restoration.restored_paths != len(frozen.files)
        ):
            raise ValueError("restoration predecessor is invalid")
        try:
            verification = self._bindings.verify_frozen_candidate(
                frozen,
                restoration,
            )
        except PhasedOperationFailure as failure:
            raise _NeedsTerminalization(
                failure.diagnostic,
                session.lifecycle,
            ) from failure
        if (
            type(verification) is not FrozenCandidateVerification
            or verification.frozen_sha256 != frozen.frozen_sha256
            or verification.verified is not True
        ):
            raise ValueError("verification predecessor is invalid")
        try:
            commit = self._bindings.atomic_success_commit(
                allocation=allocation,
                output=output,
                structured=structured,
                frozen=frozen,
                evidence=evidence,
                verification=verification,
            )
        except PhasedOperationFailure as failure:
            raise _NeedsTerminalization(
                failure.diagnostic,
                session.lifecycle,
            ) from failure
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
        self._append(
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

    def run(self) -> PhasedProviderAttemptSuccess:
        allocation = self._bindings.allocate_attempt()
        if type(allocation) is not AttemptAllocation:
            raise TypeError("allocate_attempt must return an exact allocation")
        self._session.allocation = allocation
        composition = self._bindings.compose_attempt(allocation)
        if type(composition) is not AttemptComposition:
            raise TypeError("compose_attempt must return an exact composition")
        self._session.composition = composition
        try:
            preflight = self._bindings.preflight_candidates(composition)
        except PhasedOperationFailure as failure:
            raise _NeedsTerminalization(
                failure.diagnostic,
                self._session.lifecycle,
            ) from failure
        if type(preflight) is not CandidatePreflight:
            raise TypeError("preflight_candidates must return exact preflight")
        self._session.preflight = preflight
        self._session.ledger = self._bindings.create_ledger(
            allocation,
            composition,
        )
        self._prepare_and_offer_initial()
        event = self._validate_submission()
        self._close_and_join(event)
        result = self._publish()
        ledger = self._session.ledger
        if ledger is not None:
            ledger.close()
        return result


__all__ = ["PhasedProviderAttemptCoordinator"]
