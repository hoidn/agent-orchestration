"""Private phased-delivery coordinator contracts over synthetic bindings."""

from __future__ import annotations

from concurrent.futures import Future
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
from threading import Event, Lock, Thread
import time
from types import MethodType
from typing import cast, Mapping

import pytest

from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveSessionSupport,
    InteractiveTerminalError,
    InteractiveTerminalStartOutcome,
    NaturalShutdownProof,
    NoBackendAllocationProof,
    OfferReceipt,
    PhasedFailedCleanupEvidence,
)
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.provider_phased_delivery.bindings import (
    AtomicSuccessCommitReceipt,
    AttemptAllocation,
    AttemptComposition,
    CandidatePathBinding,
    CandidatePreflight,
    CandidateResetResult,
    CandidateSnapshot,
    FrozenCandidate,
    FrozenCandidateFile,
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
    ValidatedArtifact,
    ValidatedStructuredResult,
)
from orchestrator.workflow.provider_phased_delivery.coordinator import (
    PhasedProviderAttemptCoordinator,
    _NeedsTerminalization,
)
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DEADLINE_OPERATION_REGISTRY,
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    SOURCE_PROFILES,
    diagnostic_definition,
)
from orchestrator.workflow.provider_phased_delivery.endpoint import (
    PhasedSubmitEndpoint,
    SubmitEndpointEvent,
    SubmitEndpointShutdownOutcome,
)
from orchestrator.workflow.provider_phased_delivery.frames import (
    RenderedProtocolTurn,
    render_initial_materialization_turn,
    render_retry_materialization_turn,
    render_task_turn,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    AdapterReceiptProjection,
    ByteDigestProjection,
    CandidateDigestRow,
    CompositionProjection,
    PhasedLifecycleState,
    SubmitReceipt,
    PhasedRuntimePolicy,
    ProviderBoundPolicy,
)
from orchestrator.workflow.provider_phased_delivery.ledger import (
    ProviderPromptPhaseLedgerWriter,
    validate_ledger_bytes,
)
from orchestrator.workflow.provider_phased_delivery.protocol import (
    PHASED_PROVIDER_BINDING_ENV,
    PhasedSubmitProtocolClosedError,
    PhasedSubmitBinding,
    SubmitEndpointLocator,
    SubmitRequest,
    derive_submit_binding_and_locator,
    send_submit_request,
)
from orchestrator.workflow.provider_phased_delivery.runtime_bindings import (
    _WorkflowPhasedProviderAttemptBindings,
)


def _digest(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "20260728T120000Z-q5-coordinator",
            "resume_scope": {
                "root_workflow_file": "workflows/review.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "Review",
            "enclosing_step": {
                "step_name": "Review",
                "step_id": "Review",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _cut() -> CanonicalPromptCut:
    task = b"review the supplied design\n"
    materialization = b"write the bound result bundle\n"
    canonical = task + materialization
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=canonical,
        projection=CompositionProjection(
            canonical_composed=ByteDigestProjection(
                bytes=len(canonical),
                sha256=_digest(canonical),
            ),
            task_slice=ByteDigestProjection(
                bytes=len(task),
                sha256=_digest(task),
            ),
            materialization_slice=ByteDigestProjection(
                bytes=len(materialization),
                sha256=_digest(materialization),
            ),
        ),
    )


def _support() -> InteractiveSessionSupport:
    return InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=("provider", "${PROMPT}"),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )


def _embedded_prompt_support() -> InteractiveSessionSupport:
    return InteractiveSessionSupport(
        schema_version="interactive_terminal_turn_queue.v1",
        turn_boundary_messages=True,
        command=(
            "provider",
            "--prompt=${PROMPT}",
            "--model=${MODEL}",
        ),
        message_submit_keys=("ENTER",),
        graceful_close_text="/exit",
        graceful_close_submit_keys=("ENTER",),
    )


def _invocation(
    task_turn: RenderedProtocolTurn,
    submit_binding: PhasedSubmitBinding,
) -> InteractiveMemberInvocation:
    return InteractiveMemberInvocation(
        invocation_id="q5-invocation",
        member_id="provider",
        attempt_scope_key=_scope().key,
        attempt_ordinal=1,
        resolved_command=(
            "provider",
            task_turn.delivered_turn.decode("utf-8"),
        ),
        cwd=None,
        env={
            PHASED_PROVIDER_BINDING_ENV: submit_binding.opaque_value,
        },
        support=_support(),
    )


def _handle() -> InteractiveMemberHandle:
    return InteractiveMemberHandle(
        adapter_instance_id="adapter",
        handle_id="handle",
        invocation_id="q5-invocation",
        member_id="provider",
        attempt_scope_key=_scope().key,
        attempt_ordinal=1,
        target="target",
        socket_path=Path("/tmp/q5-provider.sock"),
    )


def _adapter_receipt(status: str) -> AdapterReceiptProjection:
    return AdapterReceiptProjection(
        status=status,
        handle_id_sha256=_digest(b"handle"),
    )


def _diagnostic(reason: str) -> PhasedDeliveryDiagnostic:
    definition = diagnostic_definition(reason)
    profile = SOURCE_PROFILES[definition.source_profile]
    assert profile.primary_owner is not None
    canonical_value = (
        "missing_output_file"
        if reason == "output_validation_failed"
        else (
            "invalid_bundle_field"
            if reason == "structured_result_validation_failed"
            else (
                1 if reason == "materialization_attempts_exhausted" else None
            )
        )
    )
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


def _candidate_preflight() -> CandidatePreflight:
    return CandidatePreflight.create(
        bindings=(
            CandidatePathBinding(
                contract_ordinal=0,
                role="expected_output",
                logical_name="report",
                workspace_relative_path="artifacts/report.md",
            ),
            CandidatePathBinding(
                contract_ordinal=1,
                role="structured_bundle",
                logical_name="__structured_result_bundle__",
                workspace_relative_path="artifacts/result.json",
            ),
        )
    )


def _candidate_snapshot(
    preflight: CandidatePreflight,
    *,
    submission_ordinal: int = 1,
) -> CandidateSnapshot:
    report = b"approved\n"
    result = b'{"decision":"APPROVE"}\n'
    return CandidateSnapshot.create(
        preflight=preflight,
        submission_ordinal=submission_ordinal,
        rows=(
            CandidateDigestRow(
                contract_ordinal=0,
                role="expected_output",
                logical_name="report",
                workspace_relative_path="artifacts/report.md",
                presence="regular",
                byte_length=len(report),
                sha256=_digest(report),
            ),
            CandidateDigestRow(
                contract_ordinal=1,
                role="structured_bundle",
                logical_name="__structured_result_bundle__",
                workspace_relative_path="artifacts/result.json",
                presence="regular",
                byte_length=len(result),
                sha256=_digest(result),
            ),
        ),
    )


class RecordingLedger:
    def __init__(self, owner: "RecordingBindings") -> None:
        self.owner = owner
        self.events: list[tuple[str, Mapping[str, object]]] = []

    def append(
        self,
        event: str,
        payload: Mapping[str, object],
        *,
        observed_at: str,
    ) -> None:
        assert observed_at == "2026-07-28T12:00:00Z"
        self.events.append((event, payload))
        self.owner.actions.append(f"ledger.{event}")
        if event == "join_succeeded":
            assert self.owner.coordinator is not None
            assert (
                self.owner.coordinator.lifecycle.phase
                == "JOINED_PENDING_COMMIT"
            )

    def close(self) -> None:
        self.owner.actions.append("ledger.close")


class OneSubmitEndpoint:
    def __init__(
        self,
        owner: "RecordingBindings",
        requests: tuple[SubmitRequest, ...],
    ) -> None:
        self.owner = owner
        self.binding = owner.composition.submit_binding
        self.events = tuple(
            SubmitEndpointEvent(
                request=request,
                submission_ordinal=ordinal,
                _waiter=Future(),
                _response_sent=Future(),
            )
            for ordinal, request in enumerate(requests, start=1)
        )
        self.receive_index = 0
        self.receipts: list[tuple[SubmitReceipt, bool]] = []

    def start(self) -> None:
        self.owner.actions.append("endpoint.start")

    def open_admission(self, lifecycle: str) -> None:
        assert lifecycle == "INITIAL_MATERIALIZATION_QUEUED"
        self.owner.actions.append("endpoint.open_initial")

    def receive_event(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointEvent:
        assert deadline == self.binding.deadline
        self.owner.actions.append("endpoint.receive")
        event = self.events[self.receive_index]
        self.receive_index += 1
        return event

    def resolve(
        self,
        event: SubmitEndpointEvent,
        receipt: SubmitReceipt,
        *,
        rearm_retry: bool = False,
    ) -> None:
        assert event is self.events[len(self.receipts)]
        if receipt.status == "retry_queued":
            assert rearm_retry is True
        self.receipts.append((receipt, rearm_retry))
        self.owner.actions.append(f"endpoint.resolve.{receipt.status}")

    def stop_admission(self) -> None:
        self.owner.actions.append("endpoint.stop")

    def shutdown(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointShutdownOutcome:
        assert deadline == self.binding.deadline
        self.owner.actions.append("endpoint.shutdown")
        return SubmitEndpointShutdownOutcome(
            queued_requests_rejected=0,
            active_requests_drained=1,
            listener_closed=True,
            workers_joined=1,
            endpoint_zero_survivor_proven=True,
        )


class ScriptedAdapter:
    def __init__(self, owner: "RecordingBindings") -> None:
        self.owner = owner
        self.handle = _handle()

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome:
        assert invocation == self.owner.composition.invocation
        assert deadline == self.owner.composition.deadline
        self.owner.actions.append("adapter.start")
        return InteractiveTerminalStartOutcome(
            status="started",
            handle=self.handle,
        )

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        assert handle == self.handle
        assert deadline == self.owner.composition.deadline
        turn = self.owner.offered_turns[len(self.owner.actual_offers)]
        assert literal_message.encode("utf-8") == turn.delivered_turn
        self.owner.actual_offers.append(turn)
        self.owner.actions.append(f"adapter.offer.{turn.projection.phase}")
        return OfferReceipt(
            status="offered",
            handle_id=handle.handle_id,
            byte_count=len(turn.delivered_turn),
            content_sha256=_digest(turn.delivered_turn),
        )

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        assert handle == self.handle
        assert deadline == self.owner.composition.deadline
        self.owner.actions.append("adapter.offer_close")
        return CloseOfferReceipt(
            status="close_offered",
            handle_id=handle.handle_id,
        )

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        assert handle == self.handle
        assert deadline == self.owner.composition.deadline
        self.owner.actions.append("adapter.join")
        return NaturalShutdownProof(
            disposition="natural_exit",
            handle_id=handle.handle_id,
            return_code=0,
            pane_absent=True,
            server_absent=True,
            proof_complete=True,
        )

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        assert handle == self.handle
        assert deadline == self.owner.composition.deadline
        self.owner.actions.append("adapter.abort")
        return FailedCleanupProof(
            disposition="failed_cleanup",
            handle_id=handle.handle_id,
            pane_absent=True,
            server_absent=True,
            cleanup_complete=True,
            error_code=None,
        )


class RecordingBindings(PhasedProviderAttemptCoordinatorBindings):
    def __init__(
        self,
        *,
        materialization_attempts: int = 1,
        outcomes: tuple[tuple[bool, bool], ...] = ((True, True),),
    ) -> None:
        assert len(outcomes) <= materialization_attempts
        self.actions: list[str] = []
        self.failure_finalization_calls = 0
        self.finalized_failure: tuple[
            PhasedDeliveryDiagnostic,
            PhasedLifecycleState,
        ] | None = None
        self.coordinator: PhasedProviderAttemptCoordinator | None = None
        scope = _scope()
        self.allocation = AttemptAllocation(
            scope=scope,
            attempt_ordinal=1,
        )
        cut = _cut()
        task_turn = render_task_turn(cut=cut)
        initial_turn = render_initial_materialization_turn(
            cut=cut,
            submit_keys=("ENTER",),
        )
        submit_binding, endpoint_locator = (
            derive_submit_binding_and_locator(
                attempt_scope_sha256=scope.key,
                socket_root=Path("/tmp"),
                nonce="q5-coordinator",
                deadline=1000.0,
            )
        )
        self.composition = AttemptComposition(
            cut=cut,
            materialization_attempts=materialization_attempts,
            task_turn=task_turn,
            initial_materialization_turn=initial_turn,
            pre_prompt_command=("provider", "${PROMPT}"),
            invocation=_invocation(task_turn, submit_binding),
            submit_binding=submit_binding,
            endpoint_locator=endpoint_locator,
            deadline=1000.0,
        )
        self.preflight = _candidate_preflight()
        self.snapshots = tuple(
            _candidate_snapshot(
                self.preflight,
                submission_ordinal=ordinal,
            )
            for ordinal in range(1, len(outcomes) + 1)
        )
        self.output_validations = tuple(
            OutputPositionValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                artifacts=(
                    (
                        ValidatedArtifact(
                            logical_name="report",
                            workspace_relative_path="artifacts/report.md",
                        ),
                    )
                    if output_valid
                    else ()
                ),
                diagnostic=(
                    None
                    if output_valid
                    else _diagnostic("output_validation_failed")
                ),
            )
            for snapshot, (output_valid, _structured_valid) in zip(
                self.snapshots,
                outcomes,
                strict=True,
            )
        )
        self.structured_validations = tuple(
            StructuredResultValidation(
                snapshot_sha256=snapshot.snapshot_sha256,
                result=(
                    ValidatedStructuredResult(
                        canonical_bundle=b'{"decision":"APPROVE"}\n',
                    )
                    if structured_valid
                    else None
                ),
                diagnostic=(
                    None
                    if structured_valid
                    else _diagnostic(
                        "structured_result_validation_failed"
                    )
                ),
            )
            for snapshot, (_output_valid, structured_valid) in zip(
                self.snapshots,
                outcomes,
                strict=True,
            )
        )
        final_snapshot = self.snapshots[-1]
        self.frozen = FrozenCandidate.create(
            snapshot=final_snapshot,
            files=(
                FrozenCandidateFile(
                    binding=self.preflight.bindings[0],
                    content=b"approved\n",
                ),
                FrozenCandidateFile(
                    binding=self.preflight.bindings[1],
                    content=b'{"decision":"APPROVE"}\n',
                ),
            ),
        )
        retry_turns: list[RenderedProtocolTurn] = []
        for ordinal, (output_valid, structured_valid) in enumerate(
            outcomes[:-1],
            start=1,
        ):
            diagnostics = tuple(
                diagnostic
                for diagnostic in (
                    (
                        None
                        if output_valid
                        else _diagnostic("output_validation_failed")
                    ),
                    (
                        None
                        if structured_valid
                        else _diagnostic(
                            "structured_result_validation_failed"
                        )
                    ),
                )
                if diagnostic is not None
            )
            retry_turns.append(
                render_retry_materialization_turn(
                    cut=cut,
                    submission_ordinal=ordinal + 1,
                    diagnostics=diagnostics,
                    submit_keys=("ENTER",),
                )
            )
        self.offered_turns = (
            self.composition.initial_materialization_turn,
            *retry_turns,
        )
        self.actual_offers: list[RenderedProtocolTurn] = []
        self.adapter = ScriptedAdapter(self)
        requests = tuple(
            SubmitRequest(
                attempt_scope_sha256=scope.key,
                endpoint_instance_id=submit_binding.endpoint_instance_id,
                binding_token=submit_binding.binding_token,
                client_request_id=f"request-{ordinal}",
                payload_sha256=_digest(b""),
            )
            for ordinal in range(1, len(outcomes) + 1)
        )
        self.endpoint = OneSubmitEndpoint(self, requests)
        self.committed_material = None

    def observed_at(self) -> str:
        return "2026-07-28T12:00:00Z"

    def monotonic_now(self) -> float:
        return 0.0

    def prestart_no_backend_allocation_proof(
        self,
    ) -> NoBackendAllocationProof:
        self.actions.append("bindings.prestart_proof")
        return NoBackendAllocationProof(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        )

    def allocate_attempt(self) -> AttemptAllocation:
        self.actions.append("bindings.allocate")
        return self.allocation

    def derive_attempt_deadline(
        self,
        allocation: AttemptAllocation,
    ) -> float:
        assert allocation == self.allocation
        self.actions.append("bindings.derive_deadline")
        return self.composition.deadline

    def compose_attempt(
        self,
        allocation: AttemptAllocation,
        *,
        deadline: float,
    ) -> AttemptComposition:
        assert allocation == self.allocation
        assert deadline == self.composition.deadline
        self.actions.append("bindings.compose")
        return self.composition

    def receive_attempt_event(
        self,
        *,
        boundary: str,
        endpoint: SubmitEndpoint,
        deadline: float,
    ) -> SerializedAttemptEvent | None:
        assert deadline == self.composition.deadline
        if boundary != "AWAITING_SUBMIT":
            self.actions.append(f"bindings.control_event.{boundary}.none")
            return None
        return SerializedAttemptEvent(
            kind="submit",
            submit=endpoint.receive_event(deadline=deadline),
        )

    def preflight_candidates(
        self,
        composition: AttemptComposition,
    ) -> CandidatePreflight:
        assert composition == self.composition
        self.actions.append("bindings.preflight")
        return self.preflight

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> PhaseLedger:
        assert allocation == self.allocation
        assert composition == self.composition
        self.actions.append("ledger.header")
        self.ledger = RecordingLedger(self)
        return self.ledger

    def create_endpoint(
        self,
        composition: AttemptComposition,
    ) -> SubmitEndpoint:
        assert composition == self.composition
        self.actions.append("bindings.endpoint")
        return self.endpoint

    def snapshot_candidates(
        self,
        preflight: CandidatePreflight,
        submission_ordinal: int,
    ) -> CandidateSnapshot:
        assert preflight == self.preflight
        snapshot = self.snapshots[submission_ordinal - 1]
        self.actions.append("bindings.snapshot")
        return snapshot

    def validate_output_positions(
        self,
        snapshot: CandidateSnapshot,
    ) -> OutputPositionValidation:
        index = snapshot.submission_ordinal - 1
        self.actions.append("bindings.validate_output")
        return self.output_validations[index]

    def validate_structured_result(
        self,
        snapshot: CandidateSnapshot,
    ) -> StructuredResultValidation:
        index = snapshot.submission_ordinal - 1
        self.actions.append("bindings.validate_structured")
        return self.structured_validations[index]

    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult:
        self.actions.append("bindings.reset")
        return CandidateResetResult(
            snapshot_sha256=snapshot.snapshot_sha256,
            preflight_sha256=snapshot.preflight_sha256,
            postcondition="all_bound_paths_absent",
        )

    def freeze_candidate(
        self,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> FrozenCandidate:
        assert snapshot == self.snapshots[-1]
        assert output == self.output_validations[-1]
        assert structured == self.structured_validations[-1]
        self.actions.append("bindings.freeze")
        return self.frozen

    def publish_functional_evidence(
        self,
        frozen: FrozenCandidate,
        actual_deliveries: tuple[RenderedProtocolTurn, ...],
    ) -> FunctionalEvidencePublication:
        assert frozen == self.frozen
        assert actual_deliveries == (
            self.composition.task_turn,
            *self.offered_turns,
        )
        self.actions.append("bindings.publish_evidence")
        return FunctionalEvidencePublication.create(
            frozen=frozen,
            actual_deliveries=actual_deliveries,
            relative_path=(
                "workflow_lisp/prompt_dependencies/review/"
                "attempt-000001.json"
            ),
            evidence_sha256=_digest(b"functional-evidence"),
        )

    def restore_frozen_candidate(
        self,
        frozen: FrozenCandidate,
    ) -> FrozenCandidateRestoration:
        assert frozen == self.frozen
        self.actions.append("bindings.restore")
        return FrozenCandidateRestoration(
            frozen_sha256=frozen.frozen_sha256,
            restored_paths=len(frozen.files),
        )

    def verify_frozen_candidate(
        self,
        frozen: FrozenCandidate,
        restoration: FrozenCandidateRestoration,
    ) -> FrozenCandidateVerification:
        assert frozen == self.frozen
        assert restoration.frozen_sha256 == frozen.frozen_sha256
        self.actions.append("bindings.verify")
        return FrozenCandidateVerification(
            frozen_sha256=frozen.frozen_sha256,
            verified=True,
        )

    def prepare_success_commit(
        self,
        *,
        allocation: AttemptAllocation,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
        frozen: FrozenCandidate,
        evidence: FunctionalEvidencePublication,
        verification: FrozenCandidateVerification,
    ) -> PreparedSuccessCommit:
        self.actions.append("bindings.prepare_commit")
        return PreparedSuccessCommit(
            allocation=allocation,
            output=output,
            structured=structured,
            frozen=frozen,
            evidence=evidence,
            verification=verification,
        )

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt:
        assert deadline == self.composition.deadline
        self.committed_material = (
            prepared.allocation,
            prepared.output,
            prepared.structured,
            prepared.frozen,
            prepared.evidence,
            prepared.verification,
        )
        evidence = prepared.evidence
        frozen = prepared.frozen
        self.actions.append("bindings.atomic_commit")
        return AtomicSuccessCommitReceipt(
            evidence_sha256=evidence.evidence_sha256,
            frozen_sha256=frozen.frozen_sha256,
            status="authoritative_state_committed",
        )

    def finalize_failure(
        self,
        first_diagnostic: PhasedDeliveryDiagnostic,
        lifecycle: PhasedLifecycleState,
    ) -> None:
        assert type(first_diagnostic) is PhasedDeliveryDiagnostic
        assert type(lifecycle) is PhasedLifecycleState
        self.failure_finalization_calls += 1
        self.finalized_failure = (first_diagnostic, lifecycle)
        self.actions.append("bindings.finalize_failure")


class RealDriverAdapter(ScriptedAdapter):
    def __init__(self, owner: "RealIntegrationBindings") -> None:
        super().__init__(owner)
        self.owner = owner

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        receipt = super().offer(
            handle,
            literal_message,
            deadline=deadline,
        )
        if len(self.owner.actual_offers) == 1:
            self.owner.client_thread = Thread(
                target=self.owner.run_client,
                name="q5-real-submit-client",
            )
            self.owner.client_thread.start()
        return receipt


class RealIntegrationBindings(RecordingBindings):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(
            materialization_attempts=2,
            outcomes=((False, True), (True, True)),
        )
        self.run_root = tmp_path / "run"
        self.run_root.mkdir()
        deadline = time.monotonic() + 5
        binding, locator = derive_submit_binding_and_locator(
            attempt_scope_sha256=self.allocation.scope.key,
            socket_root=tmp_path,
            nonce="q5-real-coordinator",
            deadline=deadline,
        )
        self.composition = AttemptComposition(
            cut=self.composition.cut,
            materialization_attempts=2,
            task_turn=self.composition.task_turn,
            initial_materialization_turn=(
                self.composition.initial_materialization_turn
            ),
            pre_prompt_command=self.composition.pre_prompt_command,
            invocation=_invocation(self.composition.task_turn, binding),
            submit_binding=binding,
            endpoint_locator=locator,
            deadline=deadline,
        )
        self.adapter = RealDriverAdapter(self)
        self.endpoint = PhasedSubmitEndpoint(
            binding=binding,
            locator=locator,
            configured_total=2,
        )
        self.client_receipts: list[SubmitReceipt] = []
        self.client_thread: Thread | None = None
        self.final_receipt_received = Event()
        self.ledger_path: Path | None = None

    def run_client(self) -> None:
        for ordinal in (1, 2):
            receipt = send_submit_request(
                SubmitRequest(
                    attempt_scope_sha256=self.allocation.scope.key,
                    endpoint_instance_id=(
                        self.composition.submit_binding.endpoint_instance_id
                    ),
                    binding_token=(
                        self.composition.submit_binding.binding_token
                    ),
                    client_request_id=f"real-request-{ordinal}",
                    payload_sha256=_digest(b""),
                ),
                binding=self.composition.submit_binding,
            )
            self.client_receipts.append(receipt)
            if receipt.status != "retry_queued":
                self.final_receipt_received.set()
                return

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> ProviderPromptPhaseLedgerWriter:
        self.actions.append("ledger.header")
        writer = ProviderPromptPhaseLedgerWriter.create(
            self.run_root,
            scope=allocation.scope,
            ordinal=allocation.attempt_ordinal,
            cut=composition.cut,
            materialization_attempts=composition.materialization_attempts,
            created_at=self.observed_at(),
        )
        self.ledger_path = writer.path
        return writer

    def create_endpoint(
        self,
        composition: AttemptComposition,
    ) -> PhasedSubmitEndpoint:
        assert composition == self.composition
        self.actions.append("bindings.endpoint")
        return self.endpoint


class ReceiptCoupledCloseAdapter(RealDriverAdapter):
    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        assert self.owner.final_receipt_received.wait(timeout=1), (
            "close admission preceded final client receipt completion"
        )
        return super().offer_close(handle, deadline=deadline)


class ReceiptCoupledRealIntegrationBindings(RealIntegrationBindings):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path)
        self.adapter = ReceiptCoupledCloseAdapter(self)


def test_real_endpoint_flushes_final_receipt_before_close_admission(
    tmp_path: Path,
) -> None:
    bindings = ReceiptCoupledRealIntegrationBindings(tmp_path)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert bindings.final_receipt_received.is_set()


def test_real_endpoint_and_ledger_validate_atomic_retry_spine(
    tmp_path: Path,
) -> None:
    bindings = RealIntegrationBindings(tmp_path)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()
    assert type(result) is PhasedProviderAttemptSuccess
    assert bindings.client_thread is not None
    bindings.client_thread.join(timeout=1)

    assert not bindings.client_thread.is_alive()
    assert tuple(receipt.status for receipt in bindings.client_receipts) == (
        "retry_queued",
        "accepted_closing",
    )
    assert result.actual_deliveries == (
        bindings.composition.task_turn,
        *bindings.offered_turns,
    )
    assert bindings.ledger_path is not None
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "complete"
    assert validation["terminal_event"] == "publication_succeeded"


def test_one_submit_happy_path_records_before_actions_and_commits_once() -> None:
    bindings = RecordingBindings()
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert result.lifecycle.phase == "PUBLISHED"
    assert result.submission_ordinal == 1
    assert result.actual_deliveries == (
        bindings.composition.task_turn,
        bindings.composition.initial_materialization_turn,
    )
    assert bindings.committed_material is not None
    assert bindings.failure_finalization_calls == 0
    assert bindings.endpoint.receipts == [
        (
            SubmitReceipt(
                status="accepted_closing",
                attempt_scope_sha256=bindings.allocation.scope.key,
                client_request_id="request-1",
                submission_ordinal=1,
                configured_total=1,
                remaining_submissions=0,
                diagnostic=None,
            ),
            False,
        )
    ]
    assert bindings.actions == [
        "bindings.allocate",
        "bindings.derive_deadline",
        "bindings.compose",
        "bindings.preflight",
        "ledger.header",
        "ledger.task_start_requested",
        "adapter.start",
        "ledger.task_started",
        "bindings.endpoint",
        "endpoint.start",
        "endpoint.open_initial",
        "bindings.control_event.BEFORE_INITIAL_OFFER.none",
        "ledger.turn_offer_requested",
        "adapter.offer.initial_materialization",
        "ledger.turn_offered",
        "endpoint.receive",
        "ledger.submit_received",
        "bindings.snapshot",
        "bindings.validate_output",
        "bindings.validate_structured",
        "bindings.freeze",
        "ledger.candidate_frozen",
        "bindings.control_event.VALID_FROZEN.none",
        "ledger.close_offer_requested",
        "endpoint.resolve.accepted_closing",
        "adapter.offer_close",
        "ledger.close_offered",
        "ledger.ingress_shutdown_started",
        "endpoint.stop",
        "endpoint.shutdown",
        "ledger.ingress_shutdown_finished",
        "ledger.join_started",
        "adapter.join",
        "ledger.join_succeeded",
        "bindings.control_event.JOINED_PENDING_COMMIT.none",
        "ledger.publication_started",
        "bindings.publish_evidence",
        "bindings.restore",
        "bindings.verify",
        "bindings.prepare_commit",
        "bindings.atomic_commit",
        "ledger.publication_succeeded",
        "ledger.close",
    ]


def _direct_success(
    bindings: RecordingBindings,
    *,
    submission_ordinal: int,
    actual_deliveries: tuple[RenderedProtocolTurn, ...],
    evidence: FunctionalEvidencePublication | None = None,
) -> PhasedProviderAttemptSuccess:
    evidence = evidence or FunctionalEvidencePublication.create(
        frozen=bindings.frozen,
        actual_deliveries=actual_deliveries,
        relative_path="artifacts/phased-delivery-evidence.json",
        evidence_sha256=_digest(b"direct-success-evidence"),
    )
    return PhasedProviderAttemptSuccess(
        allocation=bindings.allocation,
        lifecycle=PhasedLifecycleState(
            phase="PUBLISHED",
            provider_cleanup="NOT_REQUIRED",
            ingress="COMPLETE",
            natural_join_proven=True,
            abort_calls=0,
        ),
        submission_ordinal=submission_ordinal,
        actual_deliveries=actual_deliveries,
        frozen=bindings.frozen,
        evidence=evidence,
        commit=AtomicSuccessCommitReceipt(
            evidence_sha256=evidence.evidence_sha256,
            frozen_sha256=bindings.frozen.frozen_sha256,
            status="authoritative_state_committed",
        ),
    )


def test_success_constructor_accepts_exact_delivery_chain() -> None:
    bindings = RecordingBindings(
        materialization_attempts=2,
        outcomes=((False, True), (True, True)),
    )
    deliveries: tuple[RenderedProtocolTurn, ...] = (
        bindings.composition.task_turn,
        *bindings.offered_turns,
    )

    result = _direct_success(
        bindings,
        submission_ordinal=2,
        actual_deliveries=deliveries,
    )

    assert result.actual_deliveries == deliveries


def test_delivery_digest_seals_submit_key_projection() -> None:
    bindings = RecordingBindings()
    task = bindings.composition.task_turn
    enter = render_initial_materialization_turn(
        cut=bindings.composition.cut,
        submit_keys=("ENTER",),
    )
    tab = render_initial_materialization_turn(
        cut=bindings.composition.cut,
        submit_keys=("TAB",),
    )
    assert enter.delivered_turn == tab.delivered_turn
    assert enter.projection != tab.projection

    enter_evidence = FunctionalEvidencePublication.create(
        frozen=bindings.frozen,
        actual_deliveries=(task, enter),
        relative_path="artifacts/enter.json",
        evidence_sha256=_digest(b"enter-evidence"),
    )
    tab_evidence = FunctionalEvidencePublication.create(
        frozen=bindings.frozen,
        actual_deliveries=(task, tab),
        relative_path="artifacts/tab.json",
        evidence_sha256=_digest(b"tab-evidence"),
    )

    assert (
        enter_evidence.actual_deliveries_sha256
        != tab_evidence.actual_deliveries_sha256
    )


def test_success_constructor_rejects_foreign_delivery_evidence() -> None:
    bindings = RecordingBindings()
    task = bindings.composition.task_turn
    enter = bindings.composition.initial_materialization_turn
    tab = render_initial_materialization_turn(
        cut=bindings.composition.cut,
        submit_keys=("TAB",),
    )
    evidence = FunctionalEvidencePublication.create(
        frozen=bindings.frozen,
        actual_deliveries=(task, enter),
        relative_path="artifacts/evidence.json",
        evidence_sha256=_digest(b"evidence"),
    )

    with pytest.raises(ValueError, match="deliver"):
        _direct_success(
            bindings,
            submission_ordinal=1,
            actual_deliveries=(task, tab),
            evidence=evidence,
        )


def test_success_constructor_rejects_submission_predecessor_mismatch() -> None:
    bindings = RecordingBindings()

    with pytest.raises(ValueError, match="submission"):
        _direct_success(
            bindings,
            submission_ordinal=2,
            actual_deliveries=(
                bindings.composition.task_turn,
                bindings.composition.initial_materialization_turn,
            ),
        )


@pytest.mark.parametrize("malformation", ("second_task", "retry_gap"))
def test_success_constructor_rejects_invalid_delivery_grammar(
    malformation: str,
) -> None:
    bindings = RecordingBindings(
        materialization_attempts=3,
        outcomes=((False, True), (False, True), (True, True)),
    )
    task = bindings.composition.task_turn
    initial, retry_two, retry_three = bindings.offered_turns
    deliveries = (
        (task, task, retry_two, retry_three)
        if malformation == "second_task"
        else (task, initial, retry_three)
    )

    with pytest.raises(ValueError, match="delivery"):
        _direct_success(
            bindings,
            submission_ordinal=3,
            actual_deliveries=deliveries,
        )


@pytest.mark.parametrize(
    "first_outcome",
    (
        (False, True),
        (True, False),
    ),
)
def test_invalid_then_valid_runs_both_validators_and_atomically_rearms_retry(
    first_outcome: tuple[bool, bool],
) -> None:
    bindings = RecordingBindings(
        materialization_attempts=2,
        outcomes=(first_outcome, (True, True)),
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    validator_actions = tuple(
        action
        for action in bindings.actions
        if action.startswith("bindings.validate_")
    )
    assert validator_actions == (
        "bindings.validate_output",
        "bindings.validate_structured",
        "bindings.validate_output",
        "bindings.validate_structured",
    )
    assert bindings.actions.count("endpoint.open_initial") == 1
    assert bindings.endpoint.receipts[0][0].status == "retry_queued"
    assert bindings.endpoint.receipts[0][1] is True
    assert bindings.endpoint.receipts[1][0].status == "accepted_closing"
    assert bindings.endpoint.receipts[1][1] is False
    assert result.actual_deliveries == (
        bindings.composition.task_turn,
        *bindings.offered_turns,
    )
    assert result.submission_ordinal == 2

    events = bindings.ledger.events
    event_names = tuple(event for event, _payload in events)
    assert event_names == (
        "task_start_requested",
        "task_started",
        "turn_offer_requested",
        "turn_offered",
        "submit_received",
        "validation_rejected",
        "candidate_reset",
        "retry_queued",
        "turn_offer_requested",
        "turn_offered",
        "submit_received",
        "candidate_frozen",
        "close_offer_requested",
        "close_offered",
        "ingress_shutdown_started",
        "ingress_shutdown_finished",
        "join_started",
        "join_succeeded",
        "publication_started",
        "publication_succeeded",
    )
    rejected_payload = events[5][1]
    assert rejected_payload["candidate_manifest"] == (
        bindings.snapshots[0].manifest("rejected")
    )
    expected_diagnostics = tuple(
        diagnostic
        for diagnostic in (
            bindings.output_validations[0].diagnostic,
            bindings.structured_validations[0].diagnostic,
        )
        if diagnostic is not None
    )
    assert rejected_payload["diagnostics"] == expected_diagnostics
    assert events[7][1]["turn"] == bindings.offered_turns[1].projection
    frozen_payload = events[11][1]
    assert frozen_payload["candidate_manifest"] == (
        bindings.snapshots[1].manifest("frozen")
    )


@pytest.mark.parametrize("cap", (1, 2, 3))
def test_invalid_submissions_exhaust_exact_cap_without_publication(
    cap: int,
) -> None:
    bindings = RecordingBindings(
        materialization_attempts=cap,
        outcomes=((False, False),) * cap,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "materialization_attempts_exhausted"
    )
    assert result.lifecycle.phase == "FAILED"
    assert bindings.actions.count("bindings.validate_output") == cap
    assert bindings.actions.count("bindings.validate_structured") == cap
    assert bindings.actions.count("bindings.reset") == cap
    assert "bindings.freeze" not in bindings.actions
    assert "bindings.publish_evidence" not in bindings.actions
    assert "bindings.atomic_commit" not in bindings.actions
    assert bindings.failure_finalization_calls == 1
    assert tuple(
        (receipt.status, rearm)
        for receipt, rearm in bindings.endpoint.receipts
    ) == (
        *((("retry_queued", True),) * (cap - 1)),
        ("failed", False),
    )
    rejections = tuple(
        payload
        for event, payload in bindings.ledger.events
        if event == "validation_rejected"
    )
    assert tuple(
        payload["candidate_manifest"] for payload in rejections
    ) == tuple(
        snapshot.manifest("rejected")
        for snapshot in bindings.snapshots
    )


@pytest.mark.parametrize(
    "path",
    ("../outside.json", "/absolute.json", "artifacts/../result.json"),
)
def test_candidate_binding_rejects_noncontained_paths(path: str) -> None:
    with pytest.raises(ValueError, match="relative POSIX"):
        CandidatePathBinding(
            contract_ordinal=0,
            role="structured_bundle",
            logical_name="__structured_result_bundle__",
            workspace_relative_path=path,
        )


def test_candidate_preflight_rejects_pairwise_collision() -> None:
    with pytest.raises(ValueError, match="pairwise distinct"):
        CandidatePreflight.create(
            bindings=(
                CandidatePathBinding(
                    contract_ordinal=0,
                    role="expected_output",
                    logical_name="report",
                    workspace_relative_path="artifacts/shared.json",
                ),
                CandidatePathBinding(
                    contract_ordinal=1,
                    role="structured_bundle",
                    logical_name="__structured_result_bundle__",
                    workspace_relative_path="artifacts/shared.json",
                ),
            )
        )


def test_semantic_binding_values_are_frozen_and_predecessor_sealed() -> None:
    bindings = RecordingBindings()

    with pytest.raises(FrozenInstanceError):
        bindings.allocation.attempt_ordinal = 2  # type: ignore[misc]
    with pytest.raises(ValueError, match="preflight"):
        replace(
            bindings.snapshots[0],
            preflight_sha256=_digest(b"different-preflight"),
        )
    with pytest.raises(ValueError, match="does not seal"):
        replace(
            bindings.frozen,
            snapshot_sha256=_digest(b"different-snapshot"),
        )


def test_attempt_composition_carries_exact_task_prompt_and_binding() -> None:
    bindings = RecordingBindings()
    composition = bindings.composition

    assert composition.invocation.resolved_command[1] == (
        composition.task_turn.delivered_turn.decode("utf-8")
    )
    assert composition.invocation.env[PHASED_PROVIDER_BINDING_ENV] == (
        composition.submit_binding.opaque_value
    )


def test_attempt_composition_accepts_embedded_prompt_after_other_substitutions(
) -> None:
    bindings = RecordingBindings()
    task_text = bindings.composition.task_turn.delivered_turn.decode("utf-8")
    invocation = replace(
        bindings.composition.invocation,
        support=_embedded_prompt_support(),
        resolved_command=(
            "provider",
            f"--prompt={task_text}",
            "--model=o3",
        ),
    )

    composition = replace(
        bindings.composition,
        pre_prompt_command=(
            "provider",
            "--prompt=${PROMPT}",
            "--model=o3",
        ),
        invocation=invocation,
    )

    assert composition.invocation == invocation


def test_attempt_composition_rejects_wrong_embedded_prompt() -> None:
    bindings = RecordingBindings()
    invocation = replace(
        bindings.composition.invocation,
        support=_embedded_prompt_support(),
        resolved_command=(
            "provider",
            "--prompt=foreign task turn",
            "--model=o3",
        ),
    )

    with pytest.raises(ValueError, match="task turn"):
        replace(
            bindings.composition,
            pre_prompt_command=(
                "provider",
                "--prompt=${PROMPT}",
                "--model=o3",
            ),
            invocation=invocation,
        )


def test_attempt_composition_rejects_foreign_prompt_carriage() -> None:
    bindings = RecordingBindings()
    invocation = replace(
        bindings.composition.invocation,
        resolved_command=("provider", "foreign task turn"),
    )

    with pytest.raises(ValueError, match="task turn"):
        replace(bindings.composition, invocation=invocation)


def test_attempt_composition_seals_initial_submit_keys() -> None:
    bindings = RecordingBindings()
    projection = (
        bindings.composition.initial_materialization_turn.projection.submit_keys
    )

    assert projection.count == 1
    assert projection.sha256 == _digest(b'[\"ENTER\"]')


def test_attempt_composition_rejects_initial_submit_key_mismatch() -> None:
    bindings = RecordingBindings()
    tab_turn = render_initial_materialization_turn(
        cut=bindings.composition.cut,
        submit_keys=("TAB",),
    )

    with pytest.raises(ValueError, match="submit keys"):
        replace(
            bindings.composition,
            initial_materialization_turn=tab_turn,
        )


@pytest.mark.parametrize(
    "env",
    (
        {},
        {PHASED_PROVIDER_BINDING_ENV: "foreign-binding"},
    ),
)
def test_attempt_composition_rejects_missing_or_foreign_binding_carriage(
    env: Mapping[str, str],
) -> None:
    bindings = RecordingBindings()
    invocation = replace(bindings.composition.invocation, env=env)

    with pytest.raises(ValueError, match="binding"):
        replace(bindings.composition, invocation=invocation)


def test_snapshot_direct_constructor_rejects_preflight_binding_tamper() -> None:
    bindings = RecordingBindings()
    original = bindings.snapshots[0]
    first = original.rows[0]
    tampered_rows = (
        replace(
            first,
            workspace_relative_path="artifacts/different-report.md",
        ),
        *original.rows[1:],
    )
    snapshot_payload = {
        "preflight_sha256": original.preflight_sha256,
        "submission_ordinal": original.submission_ordinal,
        "rows": [row.to_dict() for row in tampered_rows],
    }
    snapshot_sha256 = _digest(
        json.dumps(
            snapshot_payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    )

    with pytest.raises(ValueError, match="preflight"):
        CandidateSnapshot(
            preflight_sha256=original.preflight_sha256,
            submission_ordinal=original.submission_ordinal,
            rows=tampered_rows,
            snapshot_sha256=snapshot_sha256,
        )


class TerminalBoundaryLedger(RecordingLedger):
    owner: "TerminalBoundaryBindings"

    def append(
        self,
        event: str,
        payload: Mapping[str, object],
        *,
        observed_at: str,
    ) -> None:
        super().append(event, payload, observed_at=observed_at)
        boundary = f"ledger_{event}"
        configured = {
            self.owner.fail_at,
            self.owner.ledger_fail_at,
        }
        if boundary in configured and boundary not in (
            self.owner.consumed_failures
        ):
            self.owner.consumed_failures.add(boundary)
            raise PhasedOperationFailure(_diagnostic("evidence_append_failed"))


class TerminalBoundaryEndpoint(OneSubmitEndpoint):
    owner: "TerminalBoundaryBindings"

    def start(self) -> None:
        super().start()
        if self.owner.fail_at == "endpoint_native":
            raise FileExistsError("endpoint address already exists")
        if self.owner.fail_at in {"endpoint", "endpoint_terminal_ingress"}:
            raise PhasedOperationFailure(
                _diagnostic("submit_endpoint_allocation_failed")
            )

    def open_admission(self, lifecycle: str) -> None:
        super().open_admission(lifecycle)
        if self.owner.fail_at == "admission_native":
            raise RuntimeError("endpoint admission failed")

    def receive_event(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointEvent:
        if self.owner.fail_at == "submit":
            self.owner.actions.append("endpoint.receive")
            raise PhasedOperationFailure(
                _diagnostic("submit_lifecycle_invalid")
            )
        return super().receive_event(deadline=deadline)

    def resolve(
        self,
        event: SubmitEndpointEvent,
        receipt: SubmitReceipt,
        *,
        rearm_retry: bool = False,
    ) -> None:
        super().resolve(event, receipt, rearm_retry=rearm_retry)
        if receipt.status != "accepted_closing":
            return
        if self.owner.fail_at == "final_receipt_protocol_closed":
            raise PhasedSubmitProtocolClosedError(
                "submit receipt could not be flushed to its client"
            )
        if self.owner.fail_at == "final_receipt_timeout":
            raise TimeoutError(
                "whole-attempt deadline exhausted before receipt flush"
            )

    def shutdown(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointShutdownOutcome:
        outcome = super().shutdown(deadline=deadline)
        if self.owner.fail_at in {
            "ingress",
            "terminal_ingress",
            "endpoint_terminal_ingress",
        }:
            return SubmitEndpointShutdownOutcome(
                queued_requests_rejected=outcome.queued_requests_rejected,
                active_requests_drained=outcome.active_requests_drained,
                listener_closed=False,
                workers_joined=outcome.workers_joined,
                endpoint_zero_survivor_proven=False,
            )
        return outcome


class TerminalBoundaryAdapter(ScriptedAdapter):
    owner: "TerminalBoundaryBindings"

    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome:
        if self.owner.fail_at == "start":
            self.owner.actions.append("adapter.start")
            if self.owner.cleanup_mode == "start_completed":
                return InteractiveTerminalStartOutcome(
                    status="failed",
                    error_code="pane_start_failed",
                    backend_allocation="possible_or_allocated",
                    cleanup_status="completed",
                    provider_zero_survivor_proven=True,
                    proof=PhasedFailedCleanupEvidence(
                        disposition="failed_cleanup",
                        pane_absent=True,
                        server_absent=True,
                        cleanup_complete=True,
                        error_code=None,
                    ),
                )
            if self.owner.cleanup_mode == "start_incomplete":
                return InteractiveTerminalStartOutcome(
                    status="failed",
                    error_code=(
                        "interactive_terminal_start_cleanup_incomplete"
                    ),
                    backend_allocation="possible_or_allocated",
                    cleanup_status="incomplete",
                    provider_zero_survivor_proven=False,
                    proof=PhasedFailedCleanupEvidence(
                        disposition="failed_cleanup",
                        pane_absent=False,
                        server_absent=False,
                        cleanup_complete=False,
                        error_code=(
                            "interactive_terminal_start_cleanup_incomplete"
                        ),
                    ),
                )
            return InteractiveTerminalStartOutcome(
                status="failed",
                error_code="pane_start_failed",
                backend_allocation="none",
                cleanup_status="not_required",
                provider_zero_survivor_proven=True,
                proof=NoBackendAllocationProof(
                    disposition="no_backend_allocation",
                    backend_resource_allocated=False,
                    proof_complete=True,
                ),
            )
        return super().start(invocation, deadline=deadline)

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        phase = self.owner.offered_turns[
            len(self.owner.actual_offers)
        ].projection.phase
        if self.owner.fail_at == phase:
            self.owner.actions.append(f"adapter.offer.{phase}")
            raise InteractiveTerminalError("literal_offer_failed")
        return super().offer(
            handle,
            literal_message,
            deadline=deadline,
        )

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt:
        if self.owner.fail_at == "close":
            self.owner.actions.append("adapter.offer_close")
            raise InteractiveTerminalError("literal_offer_failed")
        return super().offer_close(handle, deadline=deadline)

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof:
        if self.owner.fail_at == "join":
            self.owner.actions.append("adapter.join")
            raise InteractiveTerminalError("natural_shutdown_timeout")
        return super().join(handle, deadline)

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof:
        self.owner.actions.append("adapter.abort")
        mode = self.owner.cleanup_mode
        if mode == "raise":
            raise InteractiveTerminalError("cleanup_backend_error")
        if mode == "timeout":
            raise InteractiveTerminalError("cleanup_timeout")
        if mode == "missing":
            return cast(FailedCleanupProof, None)
        if mode == "wrong_type":
            return cast(FailedCleanupProof, object())
        handle_id = (
            "foreign-handle"
            if mode == "mismatched"
            else handle.handle_id
        )
        complete = mode != "incomplete"
        return FailedCleanupProof(
            disposition="failed_cleanup",
            handle_id=handle_id,
            pane_absent=complete,
            server_absent=complete,
            cleanup_complete=complete,
            error_code=None if complete else "cleanup_backend_error",
        )


class TerminalBoundaryBindings(RecordingBindings):
    def __init__(
        self,
        *,
        fail_at: str,
        cleanup_mode: str = "complete",
        ledger_fail_at: str | None = None,
        force_retry: bool = False,
    ) -> None:
        retry = force_retry or fail_at in {"retry_materialization", "reset"}
        super().__init__(
            materialization_attempts=2 if retry else 1,
            outcomes=(
                ((False, True), (True, True))
                if retry
                else ((True, True),)
            ),
        )
        self.fail_at = fail_at
        self.ledger_fail_at = ledger_fail_at
        self.cleanup_mode = cleanup_mode
        self.consumed_failures: set[str] = set()
        self.adapter = TerminalBoundaryAdapter(self)
        self.endpoint = TerminalBoundaryEndpoint(
            self,
            tuple(event.request for event in self.endpoint.events),
        )

    def preflight_candidates(
        self,
        composition: AttemptComposition,
    ) -> CandidatePreflight:
        if self.fail_at == "preparation":
            self.actions.append("bindings.preflight")
            raise PhasedOperationFailure(_diagnostic("preparation_failed"))
        return super().preflight_candidates(composition)

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> PhaseLedger:
        assert allocation == self.allocation
        assert composition == self.composition
        self.actions.append("ledger.header")
        self.ledger = TerminalBoundaryLedger(self)
        return self.ledger

    def validate_output_positions(
        self,
        snapshot: CandidateSnapshot,
    ) -> OutputPositionValidation:
        if self.fail_at == "output_validation":
            self.actions.append("bindings.validate_output")
            raise PhasedOperationFailure(
                _diagnostic("output_validation_failed")
            )
        return super().validate_output_positions(snapshot)

    def validate_structured_result(
        self,
        snapshot: CandidateSnapshot,
    ) -> StructuredResultValidation:
        if self.fail_at == "structured_validation":
            self.actions.append("bindings.validate_structured")
            raise PhasedOperationFailure(
                _diagnostic("structured_result_validation_failed")
            )
        return super().validate_structured_result(snapshot)

    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult:
        if self.fail_at == "reset":
            self.actions.append("bindings.reset")
            raise PhasedOperationFailure(
                _diagnostic("candidate_reset_failed")
            )
        return super().reset_candidates(snapshot)

    def freeze_candidate(
        self,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> FrozenCandidate:
        if self.fail_at == "freeze":
            self.actions.append("bindings.freeze")
            raise PhasedOperationFailure(
                _diagnostic("candidate_freeze_failed")
            )
        return super().freeze_candidate(snapshot, output, structured)

    def publish_functional_evidence(
        self,
        frozen: FrozenCandidate,
        actual_deliveries: tuple[RenderedProtocolTurn, ...],
    ) -> FunctionalEvidencePublication:
        if self.fail_at == "publication":
            self.actions.append("bindings.publish_evidence")
            raise PhasedOperationFailure(
                _diagnostic("evidence_publication_failed")
            )
        return super().publish_functional_evidence(
            frozen,
            actual_deliveries,
        )

    def restore_frozen_candidate(
        self,
        frozen: FrozenCandidate,
    ) -> FrozenCandidateRestoration:
        if self.fail_at == "restoration":
            self.actions.append("bindings.restore")
            raise PhasedOperationFailure(
                _diagnostic("frozen_restoration_failed")
            )
        return super().restore_frozen_candidate(frozen)

    def verify_frozen_candidate(
        self,
        frozen: FrozenCandidate,
        restoration: FrozenCandidateRestoration,
    ) -> FrozenCandidateVerification:
        if self.fail_at == "verification":
            self.actions.append("bindings.verify")
            raise PhasedOperationFailure(
                _diagnostic("frozen_verification_failed")
            )
        return super().verify_frozen_candidate(frozen, restoration)

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt:
        if self.fail_at == "commit":
            self.actions.append("bindings.atomic_commit")
            raise PhasedOperationFailure(
                _diagnostic("workflow_state_commit_failed")
            )
        return super().atomic_success_commit(
            prepared,
            deadline=deadline,
        )


class RealTerminalBoundaryBindings(TerminalBoundaryBindings):
    def __init__(self, tmp_path: Path, *, fail_at: str) -> None:
        super().__init__(fail_at=fail_at)
        self.run_root = tmp_path / f"run-{fail_at}"
        self.run_root.mkdir()
        self.ledger_path: Path | None = None
        self.real_ledger: ProviderPromptPhaseLedgerWriter | None = None

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> ProviderPromptPhaseLedgerWriter:
        self.actions.append("ledger.header")
        writer = ProviderPromptPhaseLedgerWriter.create(
            self.run_root,
            scope=allocation.scope,
            ordinal=allocation.attempt_ordinal,
            cut=composition.cut,
            materialization_attempts=composition.materialization_attempts,
            created_at=self.observed_at(),
        )
        self.ledger_path = writer.path
        self.real_ledger = writer
        return writer


class DeadlineMatrixBindings(TerminalBoundaryBindings):
    def __init__(self, *, operation: str, phase: str) -> None:
        force_retry = operation in {"retry_offer", "candidate_reset"}
        super().__init__(
            fail_at=(
                "initial_materialization"
                if operation == "adapter_cleanup"
                else "none"
            ),
            force_retry=force_retry,
        )
        self.deadline_operation = operation
        self.deadline_phase = phase
        self.clock_probes: list[tuple[str, str]] = []
        self.deadline_expired = False

    def monotonic_now(self) -> float:
        coordinator = self.coordinator
        probe = (
            None
            if coordinator is None
            else getattr(coordinator._session, "deadline_probe", None)
        )
        if probe is not None:
            self.clock_probes.append(probe)
        if probe == (self.deadline_operation, self.deadline_phase):
            self.deadline_expired = True
        if self.deadline_expired:
            return self.composition.deadline
        return self.composition.deadline - 1.0


class ComposeFailureBindings(TerminalBoundaryBindings):
    def __init__(self, *, crosses_deadline: bool) -> None:
        super().__init__(fail_at="none")
        self.crosses_deadline = crosses_deadline

    def monotonic_now(self) -> float:
        coordinator = self.coordinator
        probe = (
            None
            if coordinator is None
            else getattr(coordinator._session, "deadline_probe", None)
        )
        if self.crosses_deadline and probe == ("preparation", "during"):
            return self.composition.deadline
        return self.composition.deadline - 1.0

    def compose_attempt(
        self,
        allocation: AttemptAllocation,
        *,
        deadline: float,
    ) -> AttemptComposition:
        assert allocation == self.allocation
        assert deadline == self.composition.deadline
        self.actions.append("bindings.compose")
        raise PhasedOperationFailure(_diagnostic("preparation_failed"))


class PhysicalOperationalFailureBindings(TerminalBoundaryBindings):
    def __init__(self, *, operation: str) -> None:
        super().__init__(
            fail_at=(
                operation if operation in {"reset", "freeze"} else "none"
            ),
            force_retry=operation == "reset",
        )
        self.operation = operation
        self.closed_result: (
            PhasedProviderAttemptSuccess
            | PhasedProviderAttemptFailure
            | None
        ) = None

    def compose_attempt(
        self,
        allocation: AttemptAllocation,
        *,
        deadline: float,
    ) -> AttemptComposition:
        if self.operation != "compose":
            return super().compose_attempt(
                allocation,
                deadline=deadline,
            )
        assert allocation == self.allocation
        assert deadline == self.composition.deadline
        self.actions.append("bindings.compose")
        raise PhasedOperationFailure(_diagnostic("preparation_failed"))

    def snapshot_candidates(
        self,
        preflight: CandidatePreflight,
        submission_ordinal: int,
    ) -> CandidateSnapshot:
        if self.operation != "snapshot":
            return super().snapshot_candidates(
                preflight,
                submission_ordinal,
            )
        assert preflight == self.preflight
        assert submission_ordinal == 1
        self.actions.append("bindings.snapshot")
        raise PhasedOperationFailure(
            _diagnostic("candidate_freeze_failed")
        )

    def runtime_result(
        self,
        result: PhasedProviderAttemptSuccess | PhasedProviderAttemptFailure,
    ) -> dict[str, object]:
        self.closed_result = result
        return _WorkflowPhasedProviderAttemptBindings.runtime_result(
            self,
            result,
        )


class InvalidDeadlineBindings(RecordingBindings):
    def __init__(self, deadline: object) -> None:
        super().__init__()
        self.invalid_deadline = deadline

    def derive_attempt_deadline(
        self,
        allocation: AttemptAllocation,
    ) -> float:
        assert allocation == self.allocation
        self.actions.append("bindings.derive_deadline")
        return cast(float, self.invalid_deadline)


class InvalidMonotonicBindings(RecordingBindings):
    def __init__(self, now: object) -> None:
        super().__init__()
        self.invalid_now = now

    def monotonic_now(self) -> float:
        return cast(float, self.invalid_now)


class RealDeadlineHeaderBindings(RealTerminalBoundaryBindings):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path, fail_at="none")
        self.deadline_expired = False

    def monotonic_now(self) -> float:
        coordinator = self.coordinator
        probe = (
            None
            if coordinator is None
            else getattr(coordinator._session, "deadline_probe", None)
        )
        if probe == ("ledger_append", "during"):
            self.deadline_expired = True
        if self.deadline_expired:
            return self.composition.deadline
        return self.composition.deadline - 1.0


class OrdinaryFailureDeadlineBindings(RealTerminalBoundaryBindings):
    def __init__(self, tmp_path: Path) -> None:
        super().__init__(tmp_path, fail_at="initial_materialization")
        self.deadline_expired = False

    def monotonic_now(self) -> float:
        if self.deadline_expired:
            return self.composition.deadline
        return self.composition.deadline - 1.0


class MalformedStartAdapter(TerminalBoundaryAdapter):
    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome:
        self.owner.actions.append("adapter.start")
        return cast(InteractiveTerminalStartOutcome, object())


class MalformedIngressEndpoint(TerminalBoundaryEndpoint):
    def __init__(
        self,
        owner: "MalformedOperationBindings",
        requests: tuple[SubmitRequest, ...],
    ) -> None:
        super().__init__(owner, requests)
        self.return_malformed_once = True

    def shutdown(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointShutdownOutcome:
        outcome = super().shutdown(deadline=deadline)
        if self.return_malformed_once:
            self.return_malformed_once = False
            return cast(SubmitEndpointShutdownOutcome, object())
        return outcome


class MalformedOperationBindings(TerminalBoundaryBindings):
    def __init__(self, *, operation: str, crosses_deadline: bool) -> None:
        super().__init__(
            fail_at="none",
            force_retry=operation == "candidate_reset",
        )
        self.malformed_operation = operation
        self.deadline_operation = {
            "submit_snapshot": "submit",
            "validation_output": "validation",
            "validation_structured": "validation",
        }.get(operation, operation)
        self.crosses_deadline = crosses_deadline
        if operation == "adapter_start":
            self.adapter = MalformedStartAdapter(self)
        if operation == "ingress_shutdown":
            self.endpoint = MalformedIngressEndpoint(
                self,
                tuple(event.request for event in self.endpoint.events),
            )

    def monotonic_now(self) -> float:
        coordinator = self.coordinator
        probe = (
            None
            if coordinator is None
            else getattr(coordinator._session, "deadline_probe", None)
        )
        if (
            self.crosses_deadline
            and probe == (self.deadline_operation, "during")
        ):
            return self.composition.deadline
        return self.composition.deadline - 1.0

    def receive_attempt_event(
        self,
        *,
        boundary: str,
        endpoint: SubmitEndpoint,
        deadline: float,
    ) -> SerializedAttemptEvent | None:
        if (
            self.malformed_operation == "submit"
            and boundary == "AWAITING_SUBMIT"
        ):
            self.actions.append("bindings.control_event.malformed")
            return cast(SerializedAttemptEvent, object())
        return super().receive_attempt_event(
            boundary=boundary,
            endpoint=endpoint,
            deadline=deadline,
        )

    def snapshot_candidates(
        self,
        preflight: CandidatePreflight,
        submission_ordinal: int,
    ) -> CandidateSnapshot:
        if self.malformed_operation == "submit_snapshot":
            self.actions.append("bindings.snapshot")
            return cast(CandidateSnapshot, object())
        return super().snapshot_candidates(preflight, submission_ordinal)

    def validate_output_positions(
        self,
        snapshot: CandidateSnapshot,
    ) -> OutputPositionValidation:
        if self.malformed_operation == "validation_output":
            self.actions.append("bindings.validate_output")
            return cast(OutputPositionValidation, object())
        return super().validate_output_positions(snapshot)

    def validate_structured_result(
        self,
        snapshot: CandidateSnapshot,
    ) -> StructuredResultValidation:
        if self.malformed_operation == "validation_structured":
            self.actions.append("bindings.validate_structured")
            return cast(StructuredResultValidation, object())
        return super().validate_structured_result(snapshot)

    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult:
        if self.malformed_operation == "candidate_reset":
            self.actions.append("bindings.reset")
            return cast(CandidateResetResult, object())
        return super().reset_candidates(snapshot)

    def freeze_candidate(
        self,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> FrozenCandidate:
        if self.malformed_operation == "candidate_freeze":
            self.actions.append("bindings.freeze")
            return cast(FrozenCandidate, object())
        return super().freeze_candidate(snapshot, output, structured)

    def prepare_success_commit(
        self,
        *,
        allocation: AttemptAllocation,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
        frozen: FrozenCandidate,
        evidence: FunctionalEvidencePublication,
        verification: FrozenCandidateVerification,
    ) -> PreparedSuccessCommit:
        if self.malformed_operation == "state_commit":
            self.actions.append("bindings.prepare_commit")
            return cast(PreparedSuccessCommit, object())
        return super().prepare_success_commit(
            allocation=allocation,
            output=output,
            structured=structured,
            frozen=frozen,
            evidence=evidence,
            verification=verification,
        )


class NativeHeaderFailureBindings(TerminalBoundaryBindings):
    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> PhaseLedger:
        assert allocation == self.allocation
        assert composition == self.composition
        self.actions.append("ledger.header")
        raise OSError("synthetic durable-header failure")


class ControlEventBindings(TerminalBoundaryBindings):
    def __init__(
        self,
        *,
        boundary: str,
        kind: str,
        force_retry: bool = False,
    ) -> None:
        super().__init__(
            fail_at="none",
            force_retry=force_retry,
        )
        self.control_boundary = boundary
        self.control_kind = kind

    def receive_attempt_event(
        self,
        *,
        boundary: str,
        endpoint: SubmitEndpoint,
        deadline: float,
    ) -> SerializedAttemptEvent | None:
        if boundary == self.control_boundary:
            self.actions.append(
                f"bindings.control_event.{boundary}.{self.control_kind}"
            )
            return SerializedAttemptEvent(kind=self.control_kind)
        return super().receive_attempt_event(
            boundary=boundary,
            endpoint=endpoint,
            deadline=deadline,
        )


class FinalStateDeadlineBindings(TerminalBoundaryBindings):
    def __init__(self, *, commit_wins: bool) -> None:
        super().__init__(fail_at="none")
        self.commit_wins = commit_wins
        self.state_lock = Lock()
        self.final_clock_checks = 0
        self.deadline_expired = False

    def monotonic_now(self) -> float:
        if self.deadline_expired:
            return self.composition.deadline
        return self.composition.deadline - 1.0

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt:
        self.actions.append("bindings.atomic_commit")
        with self.state_lock:
            self.final_clock_checks += 1
            if not self.commit_wins:
                self.deadline_expired = True
            if self.monotonic_now() >= deadline:
                raise PhasedOperationFailure(
                    _diagnostic("deadline_exhausted_before_state_commit")
                )
            self.committed_material = (
                prepared.allocation,
                prepared.output,
                prepared.structured,
                prepared.frozen,
                prepared.evidence,
                prepared.verification,
            )
            receipt = AtomicSuccessCommitReceipt(
                evidence_sha256=prepared.evidence.evidence_sha256,
                frozen_sha256=prepared.frozen.frozen_sha256,
                status="authoritative_state_committed",
            )
        if self.commit_wins:
            self.deadline_expired = True
        return receipt


class FinalStateInterruptionBindings(TerminalBoundaryBindings):
    def __init__(self, *, interruption_before_commit: bool) -> None:
        super().__init__(fail_at="none")
        self.interruption_before_commit = interruption_before_commit
        self.state_lock = Lock()
        self.interruption_observed = False

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt:
        assert deadline == self.composition.deadline
        self.actions.append("bindings.atomic_commit")
        with self.state_lock:
            if self.interruption_before_commit:
                self.interruption_observed = True
                raise PhasedOperationFailure(
                    _diagnostic("interrupted_nonterminal_visit")
                )
            self.committed_material = (
                prepared.allocation,
                prepared.output,
                prepared.structured,
                prepared.frozen,
                prepared.evidence,
                prepared.verification,
            )
            receipt = AtomicSuccessCommitReceipt(
                evidence_sha256=prepared.evidence.evidence_sha256,
                frozen_sha256=prepared.frozen.frozen_sha256,
                status="authoritative_state_committed",
            )
            self.interruption_observed = True
            return receipt


class TamperedPreparedCommitBindings(TerminalBoundaryBindings):
    def __init__(self, field: str) -> None:
        super().__init__(fail_at="none")
        self.tampered_field = field
        self.atomic_commit_calls = 0

    def prepare_success_commit(
        self,
        *,
        allocation: AttemptAllocation,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
        frozen: FrozenCandidate,
        evidence: FunctionalEvidencePublication,
        verification: FrozenCandidateVerification,
    ) -> PreparedSuccessCommit:
        self.actions.append("bindings.prepare_commit")
        fake_snapshot = CandidateSnapshot.create(
            preflight=self.preflight,
            submission_ordinal=self.snapshots[-1].submission_ordinal + 1,
            rows=self.snapshots[-1].rows,
        )
        replacements = {
            "allocation": replace(
                allocation,
                attempt_ordinal=allocation.attempt_ordinal + 1,
            ),
            "output": replace(
                output,
                snapshot_sha256=fake_snapshot.snapshot_sha256,
            ),
            "structured": replace(
                structured,
                snapshot_sha256=fake_snapshot.snapshot_sha256,
            ),
            "frozen": FrozenCandidate.create(
                snapshot=fake_snapshot,
                files=frozen.files,
            ),
            "evidence": replace(
                evidence,
                evidence_sha256=_digest(b"substituted-evidence"),
            ),
            "verification": replace(
                verification,
                frozen_sha256=_digest(b"substituted-verification"),
            ),
        }
        values = {
            "allocation": allocation,
            "output": output,
            "structured": structured,
            "frozen": frozen,
            "evidence": evidence,
            "verification": verification,
        }
        values[self.tampered_field] = replacements[self.tampered_field]
        return PreparedSuccessCommit(
            allocation=cast(AttemptAllocation, values["allocation"]),
            output=cast(OutputPositionValidation, values["output"]),
            structured=cast(StructuredResultValidation, values["structured"]),
            frozen=cast(FrozenCandidate, values["frozen"]),
            evidence=cast(FunctionalEvidencePublication, values["evidence"]),
            verification=cast(
                FrozenCandidateVerification,
                values["verification"],
            ),
        )

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt:
        self.atomic_commit_calls += 1
        return super().atomic_success_commit(
            prepared,
            deadline=deadline,
        )


@pytest.mark.parametrize(
    ("operation", "phase", "expected_reason"),
    tuple(
        (
            row.operation,
            phase,
            row.before_reason if phase == "before" else row.during_reason,
        )
        for row in DEADLINE_OPERATION_REGISTRY
        for phase in ("before", "during")
    ),
)
def test_whole_attempt_deadline_matrix(
    operation: str,
    phase: str,
    expected_reason: str,
) -> None:
    bindings = DeadlineMatrixBindings(
        operation=operation,
        phase=phase,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    if operation == "adapter_cleanup":
        assert result.first_diagnostic.reason == "initial_offer_failed"
        assert result.cleanup_diagnostic is not None
        assert result.cleanup_diagnostic.reason == expected_reason
    else:
        assert result.first_diagnostic.reason == expected_reason
    assert (operation, phase) in bindings.clock_probes
    assert bindings.committed_material is None
    operation_action = {
        "preparation": "bindings.preflight",
        "ledger_append": "ledger.header",
        "adapter_start": "adapter.start",
        "submit_endpoint_allocation": "bindings.endpoint",
        "initial_offer": "adapter.offer.initial_materialization",
        "retry_offer": "adapter.offer.retry_materialization",
        "submit": "endpoint.receive",
        "validation": "bindings.validate_output",
        "candidate_reset": "bindings.reset",
        "candidate_freeze": "bindings.freeze",
        "close_offer": "adapter.offer_close",
        "ingress_shutdown": "endpoint.shutdown",
        "natural_join": "adapter.join",
        "evidence_publication": "bindings.publish_evidence",
        "frozen_restoration": "bindings.restore",
        "frozen_verification": "bindings.verify",
        "state_commit": "bindings.prepare_commit",
        "adapter_cleanup": "adapter.abort",
    }[operation]
    calls = bindings.actions.count(operation_action)
    if operation == "ingress_shutdown" and phase == "before":
        assert calls == 1
    else:
        assert calls == (0 if phase == "before" else 1)
    if operation == "validation" and phase == "during":
        assert bindings.actions.count("bindings.validate_structured") == 1


@pytest.mark.parametrize(
    ("crosses_deadline", "expected_reason"),
    (
        (False, "preparation_failed"),
        (True, "deadline_exhausted_during_preparation"),
    ),
)
def test_compose_failure_obeys_preparation_after_check_precedence(
    crosses_deadline: bool,
    expected_reason: str,
) -> None:
    bindings = ComposeFailureBindings(
        crosses_deadline=crosses_deadline,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == expected_reason
    assert bindings.actions.count("bindings.compose") == 1
    assert "bindings.preflight" not in bindings.actions
    assert "ledger.header" not in bindings.actions
    assert "adapter.start" not in bindings.actions


@pytest.mark.parametrize(
    ("operation", "reason", "code", "tier"),
    (
        (
            "compose",
            "preparation_failed",
            "provider_phased_preparation_failed",
            "T0",
        ),
        (
            "snapshot",
            "candidate_freeze_failed",
            "provider_phased_candidate_freeze_failed",
            "T1",
        ),
        (
            "reset",
            "candidate_reset_failed",
            "provider_phased_candidate_reset_failed",
            "T1",
        ),
        (
            "freeze",
            "candidate_freeze_failed",
            "provider_phased_candidate_freeze_failed",
            "T1",
        ),
    ),
)
def test_physical_operational_failure_returns_closed_public_result(
    operation: str,
    reason: str,
    code: str,
    tier: str,
) -> None:
    bindings = PhysicalOperationalFailureBindings(operation=operation)
    executor = object.__new__(WorkflowExecutor)
    executor._build_phased_provider_attempt_bindings = MethodType(
        lambda self, **kwargs: bindings,
        executor,
    )

    result = executor._execute_phased_provider_with_context(
        {"name": "Review"},
        {},
        {},
        provider_bound_policy=ProviderBoundPolicy(model="model"),
        runtime_policy=PhasedRuntimePolicy(
            delivery="phased",
            materialization_attempts=2,
        ),
    )

    assert result == {
        "status": "failed",
        "exit_code": 1,
        "duration_ms": 0,
        "error": {
            "type": code,
            "message": reason,
            "context": {
                "reason": reason,
                "terminalization_tier": tier,
                "sticky": False,
            },
        },
    }
    assert type(bindings.closed_result) is PhasedProviderAttemptFailure
    assert bindings.closed_result.first_diagnostic == _diagnostic(reason)
    assert bindings.closed_result.frozen is None
    assert bindings.closed_result.evidence is None
    assert bindings.failure_finalization_calls == 1
    assert bindings.committed_material is None
    assert "bindings.publish_evidence" not in bindings.actions
    assert "bindings.atomic_commit" not in bindings.actions


@pytest.mark.parametrize(
    ("operation", "structural_error"),
    (
        ("adapter_start", TypeError),
        ("submit", TypeError),
        ("submit_snapshot", ValueError),
        ("validation_output", ValueError),
        ("validation_structured", ValueError),
        ("candidate_reset", ValueError),
        ("candidate_freeze", ValueError),
        ("ingress_shutdown", TypeError),
        ("state_commit", TypeError),
    ),
)
def test_malformed_operation_return_wins_with_positive_budget(
    operation: str,
    structural_error: type[Exception],
) -> None:
    bindings = MalformedOperationBindings(
        operation=operation,
        crosses_deadline=False,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(structural_error):
        coordinator.run()

    assert bindings.committed_material is None


@pytest.mark.parametrize(
    ("operation", "expected_reason"),
    (
        ("adapter_start", "deadline_exhausted_during_start"),
        ("submit", "deadline_exhausted_during_submit"),
        ("submit_snapshot", "deadline_exhausted_during_submit"),
        ("validation_output", "deadline_exhausted_during_validation"),
        ("validation_structured", "deadline_exhausted_during_validation"),
        ("candidate_reset", "deadline_exhausted_during_candidate_reset"),
        ("candidate_freeze", "deadline_exhausted_during_candidate_freeze"),
        (
            "ingress_shutdown",
            "deadline_exhausted_during_ingress_shutdown",
        ),
        (
            "state_commit",
            "deadline_exhausted_during_state_commit_preparation",
        ),
    ),
)
def test_crossed_deadline_precedes_malformed_operation_return(
    operation: str,
    expected_reason: str,
) -> None:
    bindings = MalformedOperationBindings(
        operation=operation,
        crosses_deadline=True,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == expected_reason
    assert bindings.committed_material is None


@pytest.mark.parametrize(
    "deadline",
    (True, 1, float("nan"), float("inf"), float("-inf")),
)
def test_derived_attempt_deadline_requires_one_exact_finite_float(
    deadline: object,
) -> None:
    bindings = InvalidDeadlineBindings(deadline)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(
        TypeError,
        match="derived deadline must be a finite number",
    ):
        coordinator.run()

    assert bindings.actions == [
        "bindings.allocate",
        "bindings.derive_deadline",
    ]


@pytest.mark.parametrize(
    "now",
    (True, 1, float("nan"), float("inf"), float("-inf")),
)
def test_monotonic_clock_requires_an_exact_finite_float(now: object) -> None:
    bindings = InvalidMonotonicBindings(now)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(
        TypeError,
        match="monotonic clock must return a finite float",
    ):
        coordinator.run()

    assert bindings.actions == [
        "bindings.allocate",
        "bindings.derive_deadline",
    ]


def test_during_ledger_header_records_t0_terminalization_and_closes(
    tmp_path: Path,
) -> None:
    bindings = RealDeadlineHeaderBindings(tmp_path)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "deadline_exhausted_during_ledger_append"
    )
    assert bindings.ledger_path is not None
    # Post-expiry fail-safe terminalization still records the T0 production
    # (header -> cleanup_finished -> terminal_failed) in the ledger.
    rows = [
        json.loads(line)
        for line in bindings.ledger_path.read_bytes().splitlines()
    ]
    assert [
        row["event"] for row in rows if row.get("record_kind") == "event"
    ] == ["cleanup_finished", "terminal_failed"]
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "complete"
    assert validation["reason"] == "complete"
    assert validation["terminal_event"] == "terminal_failed"
    assert bindings.real_ledger is not None
    assert bindings.real_ledger._closed is True
    assert "adapter.start" not in bindings.actions


def test_expired_ordinary_failure_row_is_dropped_before_failsafe_rows(
    tmp_path: Path,
) -> None:
    bindings = OrdinaryFailureDeadlineBindings(tmp_path)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator
    original_safe_append = coordinator._safe_append

    def expire_before_failure_row(
        _self: PhasedProviderAttemptCoordinator,
        event: str,
        payload: dict[str, object],
        **kwargs: object,
    ) -> bool:
        if event == "turn_offer_failed":
            bindings.deadline_expired = True
        return original_safe_append(event, payload, **kwargs)

    coordinator._safe_append = MethodType(
        expire_before_failure_row,
        coordinator,
    )

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "initial_offer_failed"
    assert bindings.ledger_path is not None
    events = [
        json.loads(line)["event"]
        for line in bindings.ledger_path.read_bytes().splitlines()
        if json.loads(line).get("record_kind") == "event"
    ]
    assert "turn_offer_failed" not in events
    assert events[-4:] == [
        "cleanup_finished",
        "ingress_shutdown_started",
        "ingress_shutdown_finished",
        "terminal_failed",
    ]
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "complete"
    assert validation["terminal_event"] == "terminal_failed"


def test_native_ledger_header_failure_enters_typed_t0_terminalizer() -> None:
    bindings = NativeHeaderFailureBindings(fail_at="none")
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "evidence_append_failed"
    assert result.terminalization_tier == "T0"
    assert "adapter.start" not in bindings.actions
    assert bindings.actions.count("bindings.prestart_proof") == 1
    assert bindings.actions.count("bindings.finalize_failure") == 1
    assert coordinator._session.ledger is None
    assert coordinator._session.ledger_channel == "ABSENT"


def test_poisoned_required_ledger_row_blocks_action_and_later_appends() -> None:
    bindings = TerminalBoundaryBindings(
        fail_at="ledger_turn_offer_requested",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "evidence_append_failed"
    assert coordinator._session.ledger_channel == "POISONED"
    assert "adapter.offer.initial_materialization" not in bindings.actions
    assert tuple(event for event, _payload in bindings.ledger.events)[-1] == (
        "turn_offer_requested"
    )
    assert not any(
        event in {"cleanup_finished", "terminal_failed"}
        for event, _payload in bindings.ledger.events
    )
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.actions.count("endpoint.shutdown") == 1


@pytest.mark.parametrize(
    ("boundary", "force_retry", "forbidden_action"),
    (
        (
            "BEFORE_INITIAL_OFFER",
            False,
            "adapter.offer.initial_materialization",
        ),
        (
            "BEFORE_RETRY_OFFER",
            True,
            "adapter.offer.retry_materialization",
        ),
        ("VALID_FROZEN", False, "adapter.offer_close"),
    ),
)
def test_serialized_preproof_interruption_stops_before_next_action(
    boundary: str,
    force_retry: bool,
    forbidden_action: str,
) -> None:
    bindings = ControlEventBindings(
        boundary=boundary,
        kind="interrupted",
        force_retry=force_retry,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "interrupted_nonterminal_visit"
    assert forbidden_action not in bindings.actions
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.committed_material is None


def test_serialized_provider_exit_before_submit_maps_exact_boundary() -> None:
    bindings = ControlEventBindings(
        boundary="AWAITING_SUBMIT",
        kind="provider_exit",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "provider_exited_before_submit"
    assert "bindings.snapshot" not in bindings.actions
    assert bindings.actions.count("adapter.abort") == 1


def test_serialized_submit_timer_maps_to_exact_during_reason() -> None:
    bindings = ControlEventBindings(
        boundary="AWAITING_SUBMIT",
        kind="deadline",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "deadline_exhausted_during_submit"
    )
    assert "bindings.snapshot" not in bindings.actions
    assert "bindings.validate_output" not in bindings.actions
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.committed_material is None


@pytest.mark.parametrize(
    "boundary",
    ("VALID_FROZEN", "JOINED_PENDING_COMMIT"),
)
def test_serialized_provider_exit_after_freeze_cannot_bypass_join_or_commit(
    boundary: str,
) -> None:
    bindings = ControlEventBindings(
        boundary=boundary,
        kind="provider_exit",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert bindings.actions.count("adapter.join") == 1
    assert bindings.actions.count("bindings.atomic_commit") == 1
    assert bindings.committed_material is not None


def test_postjoin_interruption_is_t4_and_never_aborts_or_commits() -> None:
    bindings = ControlEventBindings(
        boundary="JOINED_PENDING_COMMIT",
        kind="interrupted",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "interrupted_nonterminal_visit"
    assert result.terminalization_tier == "T4"
    assert result.lifecycle.natural_join_proven is True
    assert bindings.actions.count("adapter.abort") == 0
    assert "bindings.publish_evidence" not in bindings.actions
    assert bindings.committed_material is None


def test_postjoin_timer_precedes_late_interruption_and_commit() -> None:
    bindings = ControlEventBindings(
        boundary="JOINED_PENDING_COMMIT",
        kind="deadline",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "deadline_exhausted_before_ledger_append"
    )
    assert result.terminalization_tier == "T4"
    assert bindings.actions.count("adapter.abort") == 0
    assert "bindings.publish_evidence" not in bindings.actions
    assert bindings.committed_material is None


def test_final_state_lock_deadline_check_writes_no_authority() -> None:
    bindings = FinalStateDeadlineBindings(commit_wins=False)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "deadline_exhausted_before_state_commit"
    )
    assert bindings.final_clock_checks == 1
    assert bindings.committed_material is None


def test_atomic_commit_wins_over_later_deadline_sample() -> None:
    bindings = FinalStateDeadlineBindings(commit_wins=True)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert bindings.final_clock_checks == 1
    assert bindings.committed_material is not None
    assert "ledger.publication_succeeded" not in bindings.actions


def test_state_lock_interruption_before_commit_writes_no_authority() -> None:
    bindings = FinalStateInterruptionBindings(
        interruption_before_commit=True,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "interrupted_nonterminal_visit"
    assert result.terminalization_tier == "T4"
    assert bindings.interruption_observed is True
    assert bindings.committed_material is None
    assert bindings.actions.count("adapter.abort") == 0


def test_state_lock_commit_wins_over_later_interruption() -> None:
    bindings = FinalStateInterruptionBindings(
        interruption_before_commit=False,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert bindings.interruption_observed is True
    assert bindings.committed_material is not None
    assert bindings.actions.count(
        "bindings.control_event.JOINED_PENDING_COMMIT.none"
    ) == 1


@pytest.mark.parametrize(
    "field",
    (
        "allocation",
        "output",
        "structured",
        "frozen",
        "evidence",
        "verification",
    ),
)
def test_tampered_exact_prepared_record_cannot_reach_atomic_commit(
    field: str,
) -> None:
    bindings = TamperedPreparedCommitBindings(field)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(
        ValueError,
        match="prepared success commit predecessor is invalid",
    ):
        coordinator.run()

    assert bindings.atomic_commit_calls == 0
    assert bindings.committed_material is None


@pytest.mark.parametrize(
    (
        "fail_at",
        "reason",
        "tier",
        "abort_calls",
        "shutdown_calls",
        "terminal_suffix",
    ),
    (
        (
            "preparation",
            "preparation_failed",
            "T0",
            0,
            0,
            (),
        ),
        (
            "ledger_task_start_requested",
            "evidence_append_failed",
                "T0",
                0,
                0,
                ("task_start_requested",),
        ),
        (
            "start",
            "adapter_start_failed",
            "T0",
            0,
            0,
            (
                "task_start_failed",
                "cleanup_finished",
                "terminal_failed",
            ),
        ),
        (
            "endpoint",
            "submit_endpoint_allocation_failed",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "initial_materialization",
            "initial_offer_failed",
            "T1",
            1,
            1,
            (
                "turn_offer_failed",
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "submit",
            "submit_lifecycle_invalid",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "output_validation",
            "output_validation_failed",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "structured_validation",
            "structured_result_validation_failed",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "reset",
            "candidate_reset_failed",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "retry_materialization",
            "retry_offer_failed",
            "T1",
            1,
            1,
            (
                "turn_offer_failed",
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "freeze",
            "candidate_freeze_failed",
            "T1",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "close",
            "close_offer_failed",
            "T1",
            1,
            1,
            (
                "close_offer_failed",
                "cleanup_finished",
                "ingress_shutdown_started",
                "ingress_shutdown_finished",
                "terminal_failed",
            ),
        ),
        (
            "ingress",
            "ingress_shutdown_failed",
            "T2a",
            1,
            1,
            (
                "cleanup_finished",
                "ingress_shutdown_failed",
                "terminal_failed",
            ),
        ),
        (
            "join",
            "natural_join_failed",
            "T3",
            1,
            1,
            (
                "join_failed",
                "cleanup_finished",
                "terminal_failed",
            ),
        ),
        (
            "publication",
            "evidence_publication_failed",
            "T4",
            0,
            1,
            ("publication_failed", "terminal_failed"),
        ),
        (
            "restoration",
            "frozen_restoration_failed",
            "T4",
            0,
            1,
            ("publication_failed", "terminal_failed"),
        ),
        (
            "verification",
            "frozen_verification_failed",
            "T4",
            0,
            1,
            ("publication_failed", "terminal_failed"),
        ),
        (
            "commit",
            "workflow_state_commit_failed",
            "T4",
            0,
            1,
            ("publication_failed", "terminal_failed"),
        ),
    ),
)
def test_terminal_failure_boundary_trace(
    fail_at: str,
    reason: str,
    tier: str,
    abort_calls: int,
    shutdown_calls: int,
    terminal_suffix: tuple[str, ...],
) -> None:
    bindings = TerminalBoundaryBindings(fail_at=fail_at)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == reason
    assert result.lifecycle.phase == "FAILED"
    assert result.terminalization_tier == tier
    assert bindings.actions.count("adapter.abort") == abort_calls
    assert bindings.actions.count("endpoint.shutdown") == shutdown_calls
    assert bindings.failure_finalization_calls == 1
    assert bindings.finalized_failure == (
        result.first_diagnostic,
        result.lifecycle,
    )
    assert bindings.committed_material is None
    assert "ledger.publication_succeeded" not in bindings.actions
    if hasattr(bindings, "ledger"):
        event_names = tuple(event for event, _payload in bindings.ledger.events)
        assert event_names[-len(terminal_suffix):] == terminal_suffix


@pytest.mark.parametrize(
    ("fail_at", "expected_reason"),
    (
        ("final_receipt_protocol_closed", "submit_lifecycle_invalid"),
        ("final_receipt_timeout", "deadline_exhausted_during_submit"),
    ),
)
def test_final_receipt_flush_failure_terminalizes_without_graceful_close(
    fail_at: str,
    expected_reason: str,
) -> None:
    bindings = TerminalBoundaryBindings(fail_at=fail_at)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == expected_reason
    assert result.lifecycle.phase == "FAILED"
    assert result.terminalization_tier == "T1"
    assert result.endpoint_shutdown_status == "complete"
    assert bindings.actions.count("endpoint.resolve.accepted_closing") == 1
    assert bindings.actions.count("adapter.offer_close") == 0
    assert bindings.actions.count("endpoint.stop") == 1
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.actions.count("bindings.finalize_failure") == 1
    assert bindings.actions.count("ledger.close") == 1
    assert tuple(event for event, _payload in bindings.ledger.events)[-4:] == (
        "cleanup_finished",
        "ingress_shutdown_started",
        "ingress_shutdown_finished",
        "terminal_failed",
    )


@pytest.mark.parametrize(
    ("fail_at", "tier"),
    (
        ("start", "T0"),
        ("endpoint", "T1"),
        ("initial_materialization", "T1"),
        ("ingress", "T2a"),
        ("join", "T3"),
        ("publication", "T4"),
    ),
)
def test_real_ledger_validates_representative_terminal_trace(
    tmp_path: Path,
    fail_at: str,
    tier: str,
) -> None:
    bindings = RealTerminalBoundaryBindings(
        tmp_path,
        fail_at=fail_at,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.terminalization_tier == tier
    assert bindings.ledger_path is not None
    validation = validate_ledger_bytes(bindings.ledger_path.read_bytes())
    assert validation["status"] == "complete"
    assert validation["terminal_event"] == "terminal_failed"


@pytest.mark.parametrize(
    ("cleanup_mode", "complete", "proof_retained"),
    (
        ("complete", True, True),
        ("incomplete", False, True),
        ("mismatched", False, False),
        ("wrong_type", False, False),
        ("missing", False, False),
        ("raise", False, False),
        ("timeout", False, False),
    ),
)
def test_live_cleanup_projects_only_exact_handle_bound_proof(
    cleanup_mode: str,
    complete: bool,
    proof_retained: bool,
) -> None:
    bindings = TerminalBoundaryBindings(
        fail_at="initial_materialization",
        cleanup_mode=cleanup_mode,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert bindings.actions.count("adapter.abort") == 1
    assert result.lifecycle.abort_calls == 1
    assert result.lifecycle.provider_cleanup == (
        "COMPLETE" if complete else "INCOMPLETE"
    )
    assert (result.cleanup_diagnostic is None) is complete
    if proof_retained:
        assert type(result.provider_cleanup_proof) is (
            PhasedFailedCleanupEvidence
        )
        assert not hasattr(result.provider_cleanup_proof, "handle_id")
        assert result.provider_cleanup_proof.cleanup_complete is complete
    else:
        assert result.provider_cleanup_proof is None
    cleanup_payload = next(
        payload
        for event, payload in bindings.ledger.events
        if event == "cleanup_finished"
    )
    assert (
        cleanup_payload["provider_cleanup_proof"]
        is result.provider_cleanup_proof
    )


@pytest.mark.parametrize(
    ("cleanup_mode", "cleanup_state", "supplemental_reason"),
    (
        ("start_not_required", "NOT_REQUIRED", None),
        ("start_completed", "COMPLETE", None),
        (
            "start_incomplete",
            "INCOMPLETE",
            "adapter_start_cleanup_incomplete",
        ),
    ),
)
def test_failed_start_reuses_validated_closed_outcome_without_abort(
    cleanup_mode: str,
    cleanup_state: str,
    supplemental_reason: str | None,
) -> None:
    bindings = TerminalBoundaryBindings(
        fail_at="start",
        cleanup_mode=cleanup_mode,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.terminalization_tier == "T0"
    assert bindings.actions.count("adapter.abort") == 0
    assert result.lifecycle.abort_calls == 0
    assert result.lifecycle.provider_cleanup == cleanup_state
    start_failure = coordinator._session.start_failure_outcome
    assert start_failure is not None
    assert result.provider_cleanup_proof is (
        start_failure.proof
    )
    assert (
        None
        if result.cleanup_diagnostic is None
        else result.cleanup_diagnostic.reason
    ) == supplemental_reason


def test_t2b_reuses_failed_endpoint_shutdown_without_duplicate_calls() -> None:
    bindings = TerminalBoundaryBindings(
        fail_at="terminal_ingress",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator
    allocation = bindings.allocate_attempt()
    coordinator._session.allocation = allocation
    composition = bindings.compose_attempt(
        allocation,
        deadline=bindings.composition.deadline,
    )
    coordinator._session.composition = composition
    coordinator._session.attempt_deadline = composition.deadline
    coordinator._session.preflight = bindings.preflight_candidates(
        composition
    )
    coordinator._session.ledger = bindings.create_ledger(
        allocation,
        composition,
    )
    coordinator._session.ledger_channel = "WRITABLE"
    coordinator._prepare_and_offer_initial()
    first = _diagnostic("submit_lifecycle_invalid")
    coordinator._finish_cleanup_once()
    coordinator._start_ingress_shutdown_once(fail_safe=True)

    result = coordinator._terminalize(
        _NeedsTerminalization(first, coordinator.lifecycle)
    )

    assert type(result) is PhasedProviderAttemptFailure
    assert result.terminalization_tier == "T2b"
    assert result.endpoint_shutdown_status == "incomplete"
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert tuple(
        event
        for event, _payload in bindings.ledger.events
        if event
        in {
            "cleanup_finished",
            "ingress_shutdown_started",
            "ingress_shutdown_finished",
            "ingress_shutdown_failed",
            "terminal_failed",
        }
    ) == (
        "cleanup_finished",
        "ingress_shutdown_started",
        "ingress_shutdown_failed",
        "terminal_failed",
    )


@pytest.mark.parametrize(
    "fail_at",
    ("endpoint_native", "admission_native"),
)
def test_native_endpoint_allocation_failure_terminalizes_once(
    fail_at: str,
) -> None:
    bindings = TerminalBoundaryBindings(fail_at=fail_at)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "submit_endpoint_allocation_failed"
    )
    assert result.terminalization_tier == "T1"
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert bindings.failure_finalization_calls == 1


@pytest.mark.parametrize(
    ("fail_at", "evidence_retained"),
    (
        ("publication", False),
        ("restoration", True),
        ("verification", True),
        ("commit", True),
    ),
)
def test_post_proof_failure_retains_provisional_material_without_authority(
    fail_at: str,
    evidence_retained: bool,
) -> None:
    bindings = TerminalBoundaryBindings(fail_at=fail_at)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.terminalization_tier == "T4"
    assert result.lifecycle.natural_join_proven is True
    assert result.lifecycle.provider_cleanup == "NOT_REQUIRED"
    assert type(result.natural_shutdown_proof) is (
        PhasedNaturalShutdownEvidence
    )
    assert result.frozen is bindings.frozen
    assert (result.evidence is not None) is evidence_retained
    assert result.provider_cleanup_proof is None
    assert result.cleanup_diagnostic is None
    assert bindings.actions.count("adapter.abort") == 0
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert bindings.committed_material is None


@pytest.mark.parametrize(
    ("fail_at", "publication_started"),
    (
        ("ledger_join_succeeded", False),
        ("ledger_publication_started", True),
    ),
)
def test_post_join_ledger_failure_uses_prior_natural_proof_and_zero_abort(
    fail_at: str,
    publication_started: bool,
) -> None:
    bindings = TerminalBoundaryBindings(fail_at=fail_at)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "evidence_append_failed"
    assert result.terminalization_tier == "T4"
    assert result.lifecycle.natural_join_proven is True
    assert type(result.natural_shutdown_proof) is (
        PhasedNaturalShutdownEvidence
    )
    assert bindings.actions.count("adapter.abort") == 0
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert bindings.failure_finalization_calls == 1
    assert ("bindings.publish_evidence" in bindings.actions) is False
    assert (
        "ledger.publication_started" in bindings.actions
    ) is publication_started


@pytest.mark.parametrize(
    ("fail_at", "ledger_event", "first_reason"),
    (
        ("start", "task_start_failed", "adapter_start_failed"),
        (
            "initial_materialization",
            "turn_offer_failed",
            "initial_offer_failed",
        ),
        ("close", "close_offer_failed", "close_offer_failed"),
        ("join", "join_failed", "natural_join_failed"),
        (
            "publication",
            "publication_failed",
            "evidence_publication_failed",
        ),
    ),
)
def test_failure_event_append_failure_preserves_first_diagnostic(
    fail_at: str,
    ledger_event: str,
    first_reason: str,
) -> None:
    bindings = TerminalBoundaryBindings(
        fail_at=fail_at,
        ledger_fail_at=f"ledger_{ledger_event}",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == first_reason
    assert bindings.failure_finalization_calls == 1


def test_post_commit_evidence_append_failure_preserves_success_authority() -> None:
    bindings = TerminalBoundaryBindings(
        fail_at="ledger_publication_succeeded",
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptSuccess
    assert result.lifecycle.phase == "PUBLISHED"
    assert bindings.committed_material is not None
    assert bindings.failure_finalization_calls == 0


class PreflightFailureBindings(RecordingBindings):
    def preflight_candidates(
        self,
        composition: AttemptComposition,
    ) -> CandidatePreflight:
        self.actions.append("bindings.preflight")
        raise PhasedOperationFailure(_diagnostic("candidate_path_preexisting"))


def test_preexisting_candidate_hands_off_before_start_or_publication() -> None:
    bindings = PreflightFailureBindings()
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "candidate_path_preexisting"
    assert result.lifecycle.phase == "FAILED"
    assert "adapter.start" not in bindings.actions
    assert "bindings.atomic_commit" not in bindings.actions
    assert bindings.failure_finalization_calls == 1


def test_failure_finalization_is_an_explicit_binding_contract() -> None:
    assert (
        "finalize_failure"
        in PhasedProviderAttemptCoordinatorBindings.__dict__
    )


class _BindingLookalike:
    def __init__(self, binding: PhasedSubmitBinding) -> None:
        self.attempt_scope_sha256 = binding.attempt_scope_sha256
        self.endpoint_instance_id = binding.endpoint_instance_id
        self.binding_token = binding.binding_token
        self.socket_path = binding.socket_path
        self.deadline = binding.deadline


class ForeignEndpointBindingBindings(RecordingBindings):
    def __init__(self, *, kind: str) -> None:
        super().__init__()
        if kind == "lookalike":
            self.endpoint.binding = cast(
                PhasedSubmitBinding,
                _BindingLookalike(self.composition.submit_binding),
            )
            return
        foreign, _locator = derive_submit_binding_and_locator(
            attempt_scope_sha256=self.allocation.scope.key,
            socket_root=Path("/tmp"),
            nonce="foreign-endpoint",
            deadline=self.composition.deadline,
        )
        self.endpoint.binding = foreign


@pytest.mark.parametrize("kind", ("lookalike", "foreign"))
def test_endpoint_binding_is_exact_and_equal_before_start(kind: str) -> None:
    bindings = ForeignEndpointBindingBindings(kind=kind)
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == (
        "submit_endpoint_allocation_failed"
    )
    assert result.terminalization_tier == "T1"
    assert "endpoint.start" not in bindings.actions
    assert bindings.actions.count("adapter.abort") == 1
    assert bindings.actions.count("endpoint.shutdown") == 1
    assert bindings.failure_finalization_calls == 1


class _ResetLookalike:
    def __init__(self, snapshot: CandidateSnapshot) -> None:
        self.snapshot_sha256 = snapshot.snapshot_sha256
        self.preflight_sha256 = snapshot.preflight_sha256
        self.postcondition = "all_bound_paths_absent"


class DuckResetBindings(RecordingBindings):
    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult:
        self.actions.append("bindings.reset")
        return cast(CandidateResetResult, _ResetLookalike(snapshot))


def test_duck_typed_reset_cannot_reach_publication() -> None:
    bindings = DuckResetBindings(
        materialization_attempts=2,
        outcomes=((False, True), (True, True)),
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(ValueError, match="reset predecessor"):
        coordinator.run()

    assert "ledger.publication_started" not in bindings.actions
    assert "bindings.atomic_commit" not in bindings.actions
    assert bindings.failure_finalization_calls == 0


class _RestorationLookalike:
    def __init__(self, frozen: FrozenCandidate) -> None:
        self.frozen_sha256 = frozen.frozen_sha256
        self.restored_paths = len(frozen.files)


class DuckRestorationBindings(RecordingBindings):
    def restore_frozen_candidate(
        self,
        frozen: FrozenCandidate,
    ) -> FrozenCandidateRestoration:
        self.actions.append("bindings.restore")
        return cast(
            FrozenCandidateRestoration,
            _RestorationLookalike(frozen),
        )


def test_duck_typed_restoration_cannot_publish_success() -> None:
    bindings = DuckRestorationBindings()
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(ValueError, match="restoration predecessor"):
        coordinator.run()

    assert "bindings.atomic_commit" not in bindings.actions
    assert "ledger.publication_succeeded" not in bindings.actions
    assert bindings.failure_finalization_calls == 0


class _FalseVerificationLookalike:
    def __init__(self, frozen: FrozenCandidate) -> None:
        self.frozen_sha256 = frozen.frozen_sha256
        self.verified = False


class FalseVerificationBindings(RecordingBindings):
    def verify_frozen_candidate(
        self,
        frozen: FrozenCandidate,
        restoration: FrozenCandidateRestoration,
    ) -> FrozenCandidateVerification:
        assert restoration.frozen_sha256 == frozen.frozen_sha256
        self.actions.append("bindings.verify")
        return cast(
            FrozenCandidateVerification,
            _FalseVerificationLookalike(frozen),
        )


def test_duck_typed_false_verification_cannot_publish_success() -> None:
    bindings = FalseVerificationBindings()
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    with pytest.raises(ValueError, match="verification predecessor"):
        coordinator.run()

    assert "bindings.atomic_commit" not in bindings.actions
    assert "ledger.publication_succeeded" not in bindings.actions
    assert bindings.failure_finalization_calls == 0


class ResetFailureBindings(RecordingBindings):
    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult:
        self.actions.append("bindings.reset")
        raise PhasedOperationFailure(_diagnostic("candidate_reset_failed"))


def test_nonregular_retry_replacement_hands_off_without_retry_offer() -> None:
    bindings = ResetFailureBindings(
        materialization_attempts=2,
        outcomes=((False, True), (True, True)),
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "candidate_reset_failed"
    assert result.lifecycle.phase == "FAILED"
    assert bindings.endpoint.receipts[0][0].status == "failed"
    assert bindings.endpoint.receipts[0][1] is False
    assert "ledger.retry_queued" not in bindings.actions
    assert "bindings.atomic_commit" not in bindings.actions


class FreezeFailureBindings(RecordingBindings):
    def freeze_candidate(
        self,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> FrozenCandidate:
        self.actions.append("bindings.freeze")
        raise PhasedOperationFailure(_diagnostic("candidate_freeze_failed"))


def test_incomplete_recreation_hands_off_without_close_or_publication() -> None:
    bindings = FreezeFailureBindings()
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == "candidate_freeze_failed"
    assert result.lifecycle.phase == "FAILED"
    assert bindings.endpoint.receipts[0][0].status == "failed"
    assert "adapter.offer_close" not in bindings.actions
    assert "bindings.publish_evidence" not in bindings.actions


class FailedOfferAdapter(ScriptedAdapter):
    def __init__(
        self,
        owner: "FailedOfferBindings",
        *,
        failed_call: int,
    ) -> None:
        super().__init__(owner)
        self.failed_call = failed_call
        self.calls = 0

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt:
        self.calls += 1
        if self.calls != self.failed_call:
            return super().offer(
                handle,
                literal_message,
                deadline=deadline,
            )
        turn = self.owner.offered_turns[self.calls - 1]
        assert literal_message.encode("utf-8") == turn.delivered_turn
        self.owner.actions.append(
            f"adapter.offer.{turn.projection.phase}"
        )
        return OfferReceipt(
            status="offered",
            handle_id=handle.handle_id,
            byte_count=len(turn.delivered_turn),
            content_sha256=_digest(b"wrong-delivery"),
        )


class FailedOfferBindings(RecordingBindings):
    def __init__(
        self,
        *,
        failed_call: int,
        outcomes: tuple[tuple[bool, bool], ...],
    ) -> None:
        super().__init__(
            materialization_attempts=len(outcomes),
            outcomes=outcomes,
        )
        self.adapter = FailedOfferAdapter(
            self,
            failed_call=failed_call,
        )


@pytest.mark.parametrize(
    ("failed_call", "outcomes", "expected_reason", "expected_phases"),
    (
        (
            1,
            ((True, True),),
            "initial_offer_failed",
            ("task",),
        ),
        (
            2,
            ((False, True), (True, True)),
            "retry_offer_failed",
            ("task", "initial_materialization"),
        ),
    ),
)
def test_failed_offer_is_not_an_actual_delivery(
    failed_call: int,
    outcomes: tuple[tuple[bool, bool], ...],
    expected_reason: str,
    expected_phases: tuple[str, ...],
) -> None:
    bindings = FailedOfferBindings(
        failed_call=failed_call,
        outcomes=outcomes,
    )
    coordinator = PhasedProviderAttemptCoordinator(bindings)
    bindings.coordinator = coordinator

    result = coordinator.run()

    assert type(result) is PhasedProviderAttemptFailure
    assert result.first_diagnostic.reason == expected_reason
    assert tuple(
        turn.projection.phase
        for turn in coordinator._session.actual_deliveries
    ) == expected_phases
    assert "bindings.atomic_commit" not in bindings.actions
