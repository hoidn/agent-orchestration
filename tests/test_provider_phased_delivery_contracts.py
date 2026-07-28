from __future__ import annotations

from dataclasses import FrozenInstanceError
import inspect
from pathlib import Path

import pytest

from orchestrator.providers.interactive_terminal import (
    InteractiveMemberHandle,
    InteractiveTerminalStartOutcome,
    NoBackendAllocationProof,
    PhasedFailedCleanupEvidence,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    AdapterReceiptProjection,
    ByteDigestProjection,
    CandidateDigestManifest,
    CandidateDigestRow,
    CompositionProjection,
    CountDigestProjection,
    PhasedLifecycleState,
    PhasedRuntimePolicy,
    ProviderBoundPolicy,
    SubmitReceipt,
    TurnProjection,
    validated_start_outcome,
)


_EMPTY_KEYS_SHA256 = (
    "sha256:"
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def _digest(token: str = "a") -> str:
    return f"sha256:{token * 64}"


def _bytes(size: int, token: str) -> ByteDigestProjection:
    return ByteDigestProjection(bytes=size, sha256=_digest(token))


def _regular_row(
    ordinal: int = 0,
    *,
    role: str = "expected_output",
    logical_name: str = "review_report",
) -> CandidateDigestRow:
    return CandidateDigestRow(
        contract_ordinal=ordinal,
        role=role,
        logical_name=logical_name,
        workspace_relative_path=f"artifacts/{logical_name}.json",
        presence="regular",
        byte_length=12,
        sha256=_digest("d"),
    )


def _structured_row(ordinal: int = 1) -> CandidateDigestRow:
    return _regular_row(
        ordinal,
        role="structured_bundle",
        logical_name="__structured_result_bundle__",
    )


def test_directly_constructed_phased_models_are_closed_and_immutable() -> None:
    policy = PhasedRuntimePolicy(
        delivery="phased",
        materialization_attempts=2,
    )
    composition = CompositionProjection(
        canonical_composed=_bytes(9, "a"),
        task_slice=_bytes(4, "b"),
        materialization_slice=_bytes(5, "c"),
    )
    turn = TurnProjection(
        delivery_ordinal=1,
        phase="initial_materialization",
        submission_ordinal=1,
        protocol_frame=_bytes(3, "d"),
        canonical_slice=composition.materialization_slice,
        delivered_turn=_bytes(8, "e"),
        submit_keys=CountDigestProjection(count=1, sha256=_digest("f")),
    )
    receipt = AdapterReceiptProjection(
        status="offered",
        handle_id_sha256=_digest("1"),
    )
    manifest = CandidateDigestManifest.create(
        submission_ordinal=1,
        disposition="frozen",
        rows=(
            _regular_row(),
            _structured_row(),
        ),
    )
    lifecycle = PhasedLifecycleState(
        phase="LIVE",
        provider_cleanup="PENDING",
        ingress="NOT_ALLOCATED",
        natural_join_proven=False,
        abort_calls=0,
    )

    assert policy.materialization_attempts == 2
    assert turn.delivered_turn.bytes == (
        turn.protocol_frame.bytes + turn.canonical_slice.bytes
    )
    assert receipt.status == "offered"
    assert manifest.rows[1].contract_ordinal == 1
    assert manifest.manifest_sha256.startswith("sha256:")
    assert lifecycle.phase == "LIVE"
    with pytest.raises(FrozenInstanceError):
        policy.delivery = "composed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        PhasedRuntimePolicy(  # type: ignore[call-arg]
            delivery="phased",
            materialization_attempts=2,
            extra=True,
        )


@pytest.mark.parametrize(
    "factory",
    (
        lambda: ByteDigestProjection(bytes=True, sha256=_digest()),
        lambda: ByteDigestProjection(bytes=1, sha256="SHA256:" + "a" * 64),
        lambda: ByteDigestProjection(bytes=1, sha256="sha256:" + "a" * 63),
        lambda: CountDigestProjection(count=False, sha256=_digest()),
        lambda: PhasedRuntimePolicy(
            delivery="phased",
            materialization_attempts=True,
        ),
        lambda: PhasedRuntimePolicy(
            delivery="phased",
            materialization_attempts=0,
        ),
        lambda: PhasedRuntimePolicy(
            delivery="composed",
            materialization_attempts=1,
        ),
        lambda: CompositionProjection(
            canonical_composed=_bytes(10, "a"),
            task_slice=_bytes(4, "b"),
            materialization_slice=_bytes(5, "c"),
        ),
        lambda: TurnProjection(
            delivery_ordinal=True,
            phase="task",
            submission_ordinal=None,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(
                count=0,
                sha256=_EMPTY_KEYS_SHA256,
            ),
        ),
        lambda: TurnProjection(
            delivery_ordinal=0,
            phase="task",
            submission_ordinal=1,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(
                count=0,
                sha256=_EMPTY_KEYS_SHA256,
            ),
        ),
        lambda: TurnProjection(
            delivery_ordinal=1,
            phase="retry_materialization",
            submission_ordinal=0,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(count=1, sha256=_digest()),
        ),
        lambda: TurnProjection(
            delivery_ordinal=1,
            phase="initial_materialization",
            submission_ordinal=1,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(
                count=0,
                sha256=_EMPTY_KEYS_SHA256,
            ),
        ),
        lambda: TurnProjection(
            delivery_ordinal=7,
            phase="initial_materialization",
            submission_ordinal=1,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(count=1, sha256=_digest()),
        ),
        lambda: TurnProjection(
            delivery_ordinal=1,
            phase="retry_materialization",
            submission_ordinal=3,
            protocol_frame=_bytes(1, "a"),
            canonical_slice=_bytes(1, "b"),
            delivered_turn=_bytes(2, "c"),
            submit_keys=CountDigestProjection(count=1, sha256=_digest()),
        ),
        lambda: AdapterReceiptProjection(
            status="started",
            handle_id_sha256="sha256:not-a-digest",
        ),
        lambda: CandidateDigestRow(
            contract_ordinal=0,
            role="expected_output",
            logical_name="review",
            workspace_relative_path="artifacts/review.json",
            presence="missing",
            byte_length=0,
            sha256=None,
        ),
        lambda: CandidateDigestManifest.create(
            submission_ordinal=1,
            disposition="frozen",
            rows=(
                CandidateDigestRow(
                    contract_ordinal=0,
                    role="expected_output",
                    logical_name="review",
                    workspace_relative_path="artifacts/review.json",
                    presence="missing",
                    byte_length=None,
                    sha256=None,
                ),
                _structured_row(),
            ),
        ),
        lambda: CandidateDigestManifest.create(
            submission_ordinal=1,
            disposition="rejected",
            rows=(_regular_row(),),
        ),
        lambda: PhasedLifecycleState(
            phase="PUBLISHED",
            provider_cleanup="PENDING",
            ingress="COMPLETE",
            natural_join_proven=False,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="LIVE",
            provider_cleanup="PENDING",
            ingress="NOT_ALLOCATED",
            natural_join_proven=False,
            abort_calls=True,
        ),
        lambda: PhasedLifecycleState(
            phase="JOINED_PENDING_COMMIT",
            provider_cleanup="NOT_REQUIRED",
            ingress="STARTED",
            natural_join_proven=True,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="JOINING",
            provider_cleanup="NOT_REQUIRED",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="FAILED",
            provider_cleanup="COMPLETE",
            ingress="COMPLETE",
            natural_join_proven=True,
            abort_calls=1,
        ),
        lambda: PhasedLifecycleState(
            phase="ALLOCATED",
            provider_cleanup="COMPLETE",
            ingress="COMPLETE",
            natural_join_proven=False,
            abort_calls=1,
        ),
        lambda: PhasedLifecycleState(
            phase="FAILED",
            provider_cleanup="PENDING",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="TERMINALIZING",
            provider_cleanup="PENDING",
            ingress="INCOMPLETE",
            natural_join_proven=False,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="TERMINALIZING",
            provider_cleanup="COMPLETE",
            ingress="STARTED",
            natural_join_proven=False,
            abort_calls=0,
        ),
        lambda: PhasedLifecycleState(
            phase="FAILED",
            provider_cleanup="COMPLETE",
            ingress="COMPLETE",
            natural_join_proven=False,
            abort_calls=0,
        ),
    ),
)
def test_model_scalar_and_cross_field_domains_fail_closed(factory) -> None:
    with pytest.raises((TypeError, ValueError)):
        factory()


def test_manifest_rejects_noncontiguous_rows_and_a_tampered_seal() -> None:
    with pytest.raises(ValueError):
        CandidateDigestManifest.create(
            submission_ordinal=1,
            disposition="rejected",
            rows=(_regular_row(1), _structured_row(2)),
        )

    valid = CandidateDigestManifest.create(
        submission_ordinal=1,
        disposition="rejected",
        rows=(_regular_row(), _structured_row()),
    )
    with pytest.raises(ValueError):
        CandidateDigestManifest(
            submission_ordinal=valid.submission_ordinal,
            disposition=valid.disposition,
            rows=valid.rows,
            manifest_sha256=_digest("0"),
        )


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "phase": "ALLOCATED",
            "provider_cleanup": "NOT_REQUIRED",
            "ingress": "NOT_ALLOCATED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "STARTING",
            "provider_cleanup": "PENDING",
            "ingress": "NOT_ALLOCATED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "LIVE",
            "provider_cleanup": "PENDING",
            "ingress": "NOT_STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "INITIAL_MATERIALIZATION_QUEUED",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "VALIDATING",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "RETRY_QUEUED",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "VALID_FROZEN",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "CLOSING",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "INGRESS_STOPPING",
            "provider_cleanup": "PENDING",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "JOINING",
            "provider_cleanup": "PENDING",
            "ingress": "COMPLETE",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "JOINED_PENDING_COMMIT",
            "provider_cleanup": "NOT_REQUIRED",
            "ingress": "COMPLETE",
            "natural_join_proven": True,
            "abort_calls": 0,
        },
        {
            "phase": "PUBLISHED",
            "provider_cleanup": "NOT_REQUIRED",
            "ingress": "COMPLETE",
            "natural_join_proven": True,
            "abort_calls": 0,
        },
        {
            "phase": "TERMINALIZING",
            "provider_cleanup": "COMPLETE",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 1,
        },
        {
            "phase": "TERMINALIZING",
            "provider_cleanup": "COMPLETE",
            "ingress": "NOT_ALLOCATED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "FAILED",
            "provider_cleanup": "COMPLETE",
            "ingress": "NOT_ALLOCATED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "FAILED",
            "provider_cleanup": "INCOMPLETE",
            "ingress": "INCOMPLETE",
            "natural_join_proven": False,
            "abort_calls": 1,
        },
        {
            "phase": "TERMINALIZING",
            "provider_cleanup": "INCOMPLETE",
            "ingress": "STARTED",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "FAILED",
            "provider_cleanup": "INCOMPLETE",
            "ingress": "INCOMPLETE",
            "natural_join_proven": False,
            "abort_calls": 0,
        },
        {
            "phase": "FAILED",
            "provider_cleanup": "NOT_REQUIRED",
            "ingress": "COMPLETE",
            "natural_join_proven": True,
            "abort_calls": 0,
        },
    ),
)
def test_lifecycle_model_accepts_each_reachable_phase_class(kwargs) -> None:
    assert PhasedLifecycleState(**kwargs).phase == kwargs["phase"]


def test_submit_receipt_closes_ordinals_counts_and_diagnostic_pairing() -> None:
    retry = SubmitReceipt(
        status="retry_queued",
        attempt_scope_sha256=_digest("a"),
        client_request_id="request-1",
        submission_ordinal=1,
        configured_total=2,
        remaining_submissions=1,
        diagnostic=None,
    )
    assert retry.remaining_submissions == 1

    with pytest.raises(ValueError):
        SubmitReceipt(
            status="retry_queued",
            attempt_scope_sha256=_digest("a"),
            client_request_id="request-1",
            submission_ordinal=1,
            configured_total=2,
            remaining_submissions=0,
            diagnostic=None,
        )
    with pytest.raises(TypeError):
        SubmitReceipt(
            status="failed",
            attempt_scope_sha256=_digest("a"),
            client_request_id="request-1",
            submission_ordinal=True,
            configured_total=2,
            remaining_submissions=1,
            diagnostic=object(),
        )
    with pytest.raises(ValueError):
        SubmitReceipt(
            status="failed",
            attempt_scope_sha256=_digest("a"),
            client_request_id="request-1",
            submission_ordinal=1,
            configured_total=2,
            remaining_submissions=1,
            diagnostic=None,
        )


def test_exact_p1_start_union_is_revalidated_without_handle_invention() -> None:
    started = InteractiveTerminalStartOutcome(
        status="started",
        handle=InteractiveMemberHandle(
            adapter_instance_id="adapter-1",
            handle_id="handle-1",
            invocation_id="invocation-1",
            member_id="member-1",
            attempt_scope_key="scope-1",
            attempt_ordinal=1,
            target="session-1",
            socket_path=Path("/tmp/provider.sock"),
        ),
    )
    no_allocation = InteractiveTerminalStartOutcome(
        status="failed",
        error_code="start_timeout",
        backend_allocation="none",
        cleanup_status="not_required",
        provider_zero_survivor_proven=True,
        proof=NoBackendAllocationProof(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        ),
    )
    completed = InteractiveTerminalStartOutcome(
        status="failed",
        error_code="server_start_failed",
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
    incomplete = InteractiveTerminalStartOutcome(
        status="failed",
        error_code="interactive_terminal_start_cleanup_incomplete",
        backend_allocation="possible_or_allocated",
        cleanup_status="incomplete",
        provider_zero_survivor_proven=False,
        proof=PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=False,
            server_absent=False,
            cleanup_complete=False,
            error_code="interactive_terminal_start_cleanup_incomplete",
        ),
    )

    assert validated_start_outcome(started) is started
    assert validated_start_outcome(no_allocation) is no_allocation
    assert validated_start_outcome(completed) is completed
    assert validated_start_outcome(incomplete) is incomplete
    with pytest.raises(TypeError):
        validated_start_outcome(object())


@pytest.mark.parametrize(
    "kwargs",
    (
        {
            "status": "failed",
            "error_code": "start_timeout",
            "backend_allocation": "none",
            "cleanup_status": "completed",
            "provider_zero_survivor_proven": True,
            "proof": NoBackendAllocationProof(
                disposition="no_backend_allocation",
                backend_resource_allocated=False,
                proof_complete=True,
            ),
        },
        {
            "status": "failed",
            "error_code": "server_start_failed",
            "backend_allocation": "possible_or_allocated",
            "cleanup_status": "completed",
            "provider_zero_survivor_proven": True,
            "proof": PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=False,
                server_absent=True,
                cleanup_complete=False,
                error_code=None,
            ),
        },
    ),
)
def test_impossible_p1_start_union_combinations_are_rejected(kwargs) -> None:
    with pytest.raises(ValueError):
        InteractiveTerminalStartOutcome(**kwargs)


def test_foundational_record_constructor_surfaces_are_exact_and_closed() -> None:
    manifest = CandidateDigestManifest.create(
        submission_ordinal=1,
        disposition="frozen",
        rows=(_regular_row(), _structured_row()),
    )
    records = (
        (ProviderBoundPolicy, {"model": "model", "effort": "high"}),
        (
            PhasedRuntimePolicy,
            {"delivery": "phased", "materialization_attempts": 1},
        ),
        (ByteDigestProjection, {"bytes": 1, "sha256": _digest()}),
        (CountDigestProjection, {"count": 1, "sha256": _digest()}),
        (
            CompositionProjection,
            {
                "canonical_composed": _bytes(2, "a"),
                "task_slice": _bytes(1, "b"),
                "materialization_slice": _bytes(1, "c"),
            },
        ),
        (
            TurnProjection,
            {
                "delivery_ordinal": 0,
                "phase": "task",
                "submission_ordinal": None,
                "protocol_frame": _bytes(1, "a"),
                "canonical_slice": _bytes(1, "b"),
                "delivered_turn": _bytes(2, "c"),
                "submit_keys": CountDigestProjection(
                    count=0,
                    sha256=_EMPTY_KEYS_SHA256,
                ),
            },
        ),
        (
            AdapterReceiptProjection,
            {"status": "started", "handle_id_sha256": _digest()},
        ),
        (
            CandidateDigestRow,
            {
                "contract_ordinal": 0,
                "role": "expected_output",
                "logical_name": "review",
                "workspace_relative_path": "artifacts/review.json",
                "presence": "regular",
                "byte_length": 1,
                "sha256": _digest(),
            },
        ),
        (
            CandidateDigestManifest,
            {
                "submission_ordinal": manifest.submission_ordinal,
                "disposition": manifest.disposition,
                "rows": manifest.rows,
                "manifest_sha256": manifest.manifest_sha256,
            },
        ),
        (
            PhasedLifecycleState,
            {
                "phase": "LIVE",
                "provider_cleanup": "PENDING",
                "ingress": "NOT_ALLOCATED",
                "natural_join_proven": False,
                "abort_calls": 0,
            },
        ),
        (
            SubmitReceipt,
            {
                "status": "retry_queued",
                "attempt_scope_sha256": _digest(),
                "client_request_id": "request-1",
                "submission_ordinal": 1,
                "configured_total": 2,
                "remaining_submissions": 1,
                "diagnostic": None,
            },
        ),
    )

    for record_type, kwargs in records:
        assert tuple(inspect.signature(record_type).parameters) == tuple(kwargs)
        assert record_type(**kwargs) is not None
        with pytest.raises(TypeError):
            record_type(**kwargs, unexpected=True)
        required = next(
            (
                name
                for name, parameter in inspect.signature(
                    record_type
                ).parameters.items()
                if parameter.default is inspect.Parameter.empty
            ),
            None,
        )
        if required is not None:
            missing = dict(kwargs)
            missing.pop(required)
            with pytest.raises(TypeError):
                record_type(**missing)
