"""Physical encoding and local writer tests for phased provider ledgers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

import pytest

from orchestrator.providers.interactive_terminal import (
    FailedCleanupProof,
    InteractiveTerminalStartOutcome,
    NoBackendAllocationProof,
    PhasedFailedCleanupEvidence,
    project_phased_failed_cleanup_evidence,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    SOURCE_PROFILES,
    diagnostic_definition,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    AdapterReceiptProjection,
    ByteDigestProjection,
    CandidateDigestManifest,
    CandidateDigestRow,
    CompositionProjection,
    CountDigestProjection,
    TurnProjection,
)


_EMPTY_KEYS_DIGEST = (
    "sha256:"
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
_CREATED_AT = "2026-07-27T12:34:56.123456Z"
_OBSERVED_AT = "2026-07-27T12:35:00Z"


def _digest(token: str = "a") -> str:
    return "sha256:" + token * 64


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "20260727T123456Z-q5-ledger",
            "resume_scope": {
                "root_workflow_file": "workflows/review.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "Réview",
            "enclosing_step": {
                "step_name": "Review",
                "step_id": "Review",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _composition() -> CompositionProjection:
    task = b"task\n"
    materialization = b"inputs\n"
    return CompositionProjection(
        canonical_composed=ByteDigestProjection(
            bytes=len(task + materialization),
            sha256=(
                "sha256:" + hashlib.sha256(task + materialization).hexdigest()
            ),
        ),
        task_slice=ByteDigestProjection(
            bytes=len(task),
            sha256="sha256:" + hashlib.sha256(task).hexdigest(),
        ),
        materialization_slice=ByteDigestProjection(
            bytes=len(materialization),
            sha256="sha256:" + hashlib.sha256(materialization).hexdigest(),
        ),
    )


def _cut() -> CanonicalPromptCut:
    task = b"task\n"
    materialization = b"inputs\n"
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=task + materialization,
        projection=_composition(),
    )


def _custom_cut(
    task: bytes,
    materialization: bytes,
) -> CanonicalPromptCut:
    canonical = task + materialization
    projection = CompositionProjection(
        canonical_composed=ByteDigestProjection(
            bytes=len(canonical),
            sha256="sha256:" + hashlib.sha256(canonical).hexdigest(),
        ),
        task_slice=ByteDigestProjection(
            bytes=len(task),
            sha256="sha256:" + hashlib.sha256(task).hexdigest(),
        ),
        materialization_slice=ByteDigestProjection(
            bytes=len(materialization),
            sha256=(
                "sha256:" + hashlib.sha256(materialization).hexdigest()
            ),
        ),
    )
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=canonical,
        projection=projection,
    )


def _turn(
    phase: str = "task",
    submission_ordinal: int | None = None,
) -> TurnProjection:
    if phase == "task":
        delivery_ordinal = 0
        keys = CountDigestProjection(
            count=0,
            sha256=_EMPTY_KEYS_DIGEST,
        )
        slice_projection = _composition().task_slice
    else:
        assert submission_ordinal is not None
        delivery_ordinal = submission_ordinal
        keys = CountDigestProjection(count=1, sha256=_digest("e"))
        slice_projection = _composition().materialization_slice
    return TurnProjection(
        delivery_ordinal=delivery_ordinal,
        phase=phase,
        submission_ordinal=submission_ordinal,
        protocol_frame=ByteDigestProjection(
            bytes=3,
            sha256=_digest("d"),
        ),
        canonical_slice=slice_projection,
        delivered_turn=ByteDigestProjection(
            bytes=3 + slice_projection.bytes,
            sha256=_digest("f"),
        ),
        submit_keys=keys,
    )


def _diagnostic_for_reason(reason: str) -> PhasedDeliveryDiagnostic:
    definition = diagnostic_definition(reason)
    profile = SOURCE_PROFILES[definition.source_profile]
    assert profile.primary_owner is not None
    canonical_value = (
        "missing_output_file"
        if reason == "output_validation_failed"
        else (
            "invalid_bundle_field"
            if reason == "structured_result_validation_failed"
            else None
        )
    )

    def source(owner: str) -> DiagnosticSource:
        kind = (
            "adapter_operation"
            if owner == "interactive_adapter"
            else (
                "state_commit"
                if owner == "workflow_state_commit"
                else "runtime_attempt"
            )
        )
        return DiagnosticSource(
            kind=kind,
            owner=owner,
            path=None,
            span=None,
        )

    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value=canonical_value,
            summary=reason,
        ),
        primary_source=source(profile.primary_owner),
        related_sources=tuple(
            source(owner) for owner in profile.related_owners
        ),
    )


def _diagnostic() -> PhasedDeliveryDiagnostic:
    return _diagnostic_for_reason("output_validation_failed")


def _adapter_cleanup_diagnostic(
    reason: str,
) -> PhasedDeliveryDiagnostic:
    return _diagnostic_for_reason(reason)


def _adapter_start_cleanup_incomplete_diagnostic(
) -> PhasedDeliveryDiagnostic:
    return _adapter_cleanup_diagnostic(
        "adapter_start_cleanup_incomplete"
    )


def _rows(*, regular: bool) -> tuple[CandidateDigestRow, ...]:
    presence = "regular" if regular else "missing"
    byte_length = 11 if regular else None
    digest = _digest("8") if regular else None
    return (
        CandidateDigestRow(
            contract_ordinal=0,
            role="expected_output",
            logical_name="review_report",
            workspace_relative_path="artifacts/review.json",
            presence=presence,
            byte_length=byte_length,
            sha256=digest,
        ),
        CandidateDigestRow(
            contract_ordinal=1,
            role="expected_output",
            logical_name="summary",
            workspace_relative_path="artifacts/summary.txt",
            presence="regular",
            byte_length=7,
            sha256=_digest("9"),
        ),
        CandidateDigestRow(
            contract_ordinal=2,
            role="structured_bundle",
            logical_name="__structured_result_bundle__",
            workspace_relative_path="artifacts/result.json",
            presence="regular",
            byte_length=13,
            sha256=_digest("0"),
        ),
    )


def _manifest(disposition: str) -> CandidateDigestManifest:
    return CandidateDigestManifest.create(
        submission_ordinal=1,
        disposition=disposition,
        rows=_rows(regular=disposition == "frozen"),
    )


def _receipt(status: str) -> AdapterReceiptProjection:
    return AdapterReceiptProjection(
        status=status,
        handle_id_sha256=_digest("1"),
    )


def _close_projection() -> dict[str, object]:
    return {
        "close_text": ByteDigestProjection(
            bytes=4,
            sha256=_digest("2"),
        ),
        "submit_keys": CountDigestProjection(
            count=1,
            sha256=_digest("3"),
        ),
    }


def _natural_proof() -> dict[str, object]:
    return {
        "disposition": "natural_exit",
        "return_code": 0,
        "pane_absent": True,
        "server_absent": True,
        "proof_complete": True,
    }


def _no_allocation_start_failure(
    error_code: str = "tmux_unavailable",
) -> InteractiveTerminalStartOutcome:
    return InteractiveTerminalStartOutcome(
        status="failed",
        error_code=error_code,
        backend_allocation="none",
        cleanup_status="not_required",
        provider_zero_survivor_proven=True,
        proof=NoBackendAllocationProof(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        ),
    )


def _allocated_start_failure(
    *,
    error_code: str,
    cleanup_status: str = "completed",
) -> InteractiveTerminalStartOutcome:
    incomplete = cleanup_status == "incomplete"
    proof = PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=not incomplete,
        server_absent=True,
        cleanup_complete=not incomplete,
        error_code=(
            "interactive_terminal_start_cleanup_incomplete"
            if incomplete
            else None
        ),
    )
    return InteractiveTerminalStartOutcome(
        status="failed",
        error_code=error_code,
        backend_allocation="possible_or_allocated",
        cleanup_status=cleanup_status,
        provider_zero_survivor_proven=not incomplete,
        proof=proof,
    )


def _event_payloads() -> dict[str, dict[str, object]]:
    validation_diagnostic = _diagnostic()
    start_diagnostic = _diagnostic_for_reason("adapter_start_failed")
    task = _turn()
    materialization = _turn("initial_materialization", 1)
    terminal_response = {
        "status": "failed",
        "code": "provider_phased_submit_protocol_invalid",
        "reason": "submit_lifecycle_invalid",
    }
    return {
        "task_start_requested": {"turn": task},
        "task_started": {
            "turn": task,
            "receipt": _receipt("started"),
        },
        "task_start_failed": {
            "turn": task,
            "diagnostic": start_diagnostic,
            "start_failure_outcome": _no_allocation_start_failure(),
        },
        "turn_offer_requested": {"turn": materialization},
        "turn_offered": {
            "turn": materialization,
            "receipt": _receipt("offered"),
        },
        "turn_offer_failed": {
            "turn": materialization,
            "diagnostic": _diagnostic_for_reason(
                "initial_offer_failed"
            ),
        },
        "submit_received": {
            "client_request_id_sha256": _digest("4"),
            "submission_ordinal": 1,
            "configured_total": 2,
            "remaining_before": 2,
        },
        "validation_rejected": {
            "submission_ordinal": 1,
            "diagnostics": (validation_diagnostic,),
            "candidate_manifest": _manifest("rejected"),
        },
        "candidate_reset": {
            "submission_ordinal": 1,
            "postcondition": "all_bound_paths_absent",
        },
        "retry_queued": {
            "rejected_submission_ordinal": 1,
            "next_submission_ordinal": 2,
            "turn": _turn("retry_materialization", 2),
        },
        "candidate_frozen": {
            "submission_ordinal": 1,
            "candidate_manifest": _manifest("frozen"),
        },
        "close_offer_requested": {
            "submission_ordinal": 1,
            "close_projection": _close_projection(),
        },
        "close_offered": {
            "submission_ordinal": 1,
            "close_projection": _close_projection(),
            "receipt": _receipt("close_offered"),
        },
        "close_offer_failed": {
            "submission_ordinal": 1,
            "close_projection": _close_projection(),
            "diagnostic": _diagnostic_for_reason("close_offer_failed"),
        },
        "ingress_shutdown_started": {
            "terminal_response": terminal_response,
        },
        "ingress_shutdown_finished": {
            "terminal_response": terminal_response,
            "queued_requests_rejected": 0,
            "active_requests_drained": 1,
            "listener_closed": True,
            "workers_joined": 1,
            "endpoint_zero_survivor_proven": True,
        },
        "ingress_shutdown_failed": {
            "terminal_response": terminal_response,
            "queued_requests_rejected": 0,
            "active_requests_drained": 1,
            "listener_closed": False,
            "workers_joined": 0,
            "endpoint_zero_survivor_proven": False,
            "diagnostic": _diagnostic_for_reason(
                "ingress_shutdown_failed"
            ),
        },
        "join_started": {
            "submission_ordinal": 1,
            "remaining_budget_ms": 100,
        },
        "join_succeeded": {
            "submission_ordinal": 1,
            "natural_shutdown_proof": _natural_proof(),
        },
        "join_failed": {
            "submission_ordinal": 1,
            "diagnostic": _diagnostic_for_reason("natural_join_failed"),
        },
        "publication_started": {"submission_ordinal": 1},
        "publication_succeeded": {
            "submission_ordinal": 1,
            "commit_status": "authoritative_state_committed",
        },
        "publication_failed": {
            "submission_ordinal": 1,
            "diagnostic": _diagnostic_for_reason(
                "workflow_state_commit_failed"
            ),
        },
        "cleanup_finished": {
            "cleanup_status": "not_required",
            "abort_calls": 0,
            "provider_cleanup_proof": NoBackendAllocationProof(
                disposition="no_backend_allocation",
                backend_resource_allocated=False,
                proof_complete=True,
            ),
            "cleanup_diagnostic": None,
            "provider_zero_survivor_proven": True,
        },
        "terminal_failed": {
            "diagnostic": start_diagnostic,
            "cleanup_status": "not_required",
            "cleanup_diagnostic": None,
            "endpoint_shutdown_status": "not_allocated",
            "natural_shutdown_proof": None,
        },
    }


def _attempt() -> dict[str, Any]:
    from orchestrator.workflow.prompt_dependency_evidence import _attempt

    return _attempt(_scope(), 1)


def _decode(line: bytes) -> dict[str, Any]:
    assert line.endswith(b"\n")
    assert not line.endswith(b"\n\n")
    return json.loads(line)


def test_header_encoding_is_exact_canonical_ascii_jsonl() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_header,
    )

    encoded = encode_header(
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    row = _decode(encoded)

    assert encoded == (
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        + b"\n"
    )
    assert b"\\u00e9" in encoded
    assert set(row) == {
        "schema_version",
        "record_kind",
        "seq",
        "attempt",
        "target_dsl",
        "delivery",
        "materialization_attempts",
        "prompt_attempt_identity_version",
        "protocol_schema_version",
        "canonical_composed",
        "task_slice",
        "materialization_slice",
        "created_at",
    }
    assert row["seq"] == 0
    assert row["attempt"] == _attempt()


def test_physical_path_is_derived_from_exact_scope_and_ordinal() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        ledger_relative_path,
    )

    attempt = _attempt()

    assert ledger_relative_path(_scope(), 1) == Path(
        "workflow_lisp",
        "prompt_dependencies",
        attempt["step_key"],
        attempt["visit_key"],
        "attempt-000001-provider-prompt-phases.jsonl",
    )
    assert ledger_relative_path(_scope(), 1_000_000).name == (
        "attempt-1000000-provider-prompt-phases.jsonl"
    )


@pytest.mark.parametrize("event", tuple(_event_payloads()))
def test_every_event_encoding_has_exact_common_and_payload_keys(
    event: str,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    line = encode_event(
        seq=1,
        event=event,
        attempt=_attempt(),
        observed_at=_OBSERVED_AT,
        payload=_event_payloads()[event],
    )
    row = _decode(line)

    assert set(row) == {
        "schema_version",
        "record_kind",
        "seq",
        "event",
        "attempt",
        "observed_at",
        "payload",
    }
    assert row["schema_version"] == "provider_prompt_phase_ledger.v1"
    assert row["record_kind"] == "event"
    assert row["seq"] == 1
    assert row["event"] == event
    assert row["attempt"] == _attempt()


@pytest.mark.parametrize("event", tuple(_event_payloads()))
@pytest.mark.parametrize("mutation", ("missing", "extra"))
def test_event_encoding_payload_keys_are_closed(
    event: str,
    mutation: str,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    payload = _event_payloads()[event]
    if mutation == "missing":
        payload.pop(next(iter(payload)))
    else:
        payload["extra"] = None

    with pytest.raises((TypeError, ValueError), match="payload"):
        encode_event(
            seq=1,
            event=event,
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("seq", True),
        ("seq", 0),
        ("seq", 2**63),
        ("event", "unknown"),
        ("observed_at", "2026-07-27T12:35:00+00:00"),
        ("observed_at", "2026-07-27T12:35:00.1Z"),
        ("observed_at", "2026-02-30T12:35:00Z"),
    ),
)
def test_event_encoding_rejects_wrong_scalars(
    field: str,
    value: object,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    arguments: dict[str, Any] = {
        "seq": 1,
        "event": "task_start_requested",
        "attempt": _attempt(),
        "observed_at": _OBSERVED_AT,
        "payload": _event_payloads()["task_start_requested"],
    }
    arguments[field] = value

    with pytest.raises((TypeError, ValueError)):
        encode_event(**arguments)


@pytest.mark.parametrize(
    "created_at",
    (
        "2026-07-27T12:34:56+00:00",
        "2026-07-27T12:34:56.123Z",
        "2026-07-27T12:34:60Z",
        "2026-07-27T12:34:56Z ",
    ),
)
def test_header_encoding_rejects_noncanonical_or_invalid_timestamp(
    created_at: str,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_header,
    )

    with pytest.raises(ValueError, match="created_at"):
        encode_header(
            scope=_scope(),
            ordinal=1,
            cut=_cut(),
            materialization_attempts=2,
            created_at=created_at,
        )


def test_header_encoding_requires_only_the_materialization_slice_nonempty(
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_header,
    )

    assert _decode(
        encode_header(
            scope=_scope(),
            ordinal=1,
            cut=_custom_cut(b"", b"materials"),
            materialization_attempts=2,
            created_at=_CREATED_AT,
        )
    )["task_slice"]["bytes"] == 0

    with pytest.raises(ValueError, match="materialization_slice"):
        encode_header(
            scope=_scope(),
            ordinal=1,
            cut=_custom_cut(b"task", b""),
            materialization_attempts=2,
            created_at=_CREATED_AT,
        )


def test_turn_encoding_requires_protocol_and_materialization_bytes_nonempty(
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    empty = ByteDigestProjection(
        bytes=0,
        sha256="sha256:" + hashlib.sha256(b"").hexdigest(),
    )
    task_with_empty_canonical = TurnProjection(
        delivery_ordinal=0,
        phase="task",
        submission_ordinal=None,
        protocol_frame=ByteDigestProjection(
            bytes=3,
            sha256=_digest("a"),
        ),
        canonical_slice=empty,
        delivered_turn=ByteDigestProjection(
            bytes=3,
            sha256=_digest("b"),
        ),
        submit_keys=CountDigestProjection(
            count=0,
            sha256=_EMPTY_KEYS_DIGEST,
        ),
    )
    assert _decode(
        encode_event(
            seq=1,
            event="task_start_requested",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload={"turn": task_with_empty_canonical},
        )
    )["payload"]["turn"]["canonical_slice"]["bytes"] == 0

    zero_protocol = TurnProjection(
        delivery_ordinal=0,
        phase="task",
        submission_ordinal=None,
        protocol_frame=empty,
        canonical_slice=ByteDigestProjection(
            bytes=2,
            sha256=_digest("c"),
        ),
        delivered_turn=ByteDigestProjection(
            bytes=2,
            sha256=_digest("d"),
        ),
        submit_keys=CountDigestProjection(
            count=0,
            sha256=_EMPTY_KEYS_DIGEST,
        ),
    )
    with pytest.raises(ValueError, match="protocol_frame"):
        encode_event(
            seq=1,
            event="task_start_requested",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload={"turn": zero_protocol},
        )

    empty_materialization = TurnProjection(
        delivery_ordinal=1,
        phase="initial_materialization",
        submission_ordinal=1,
        protocol_frame=ByteDigestProjection(
            bytes=2,
            sha256=_digest("e"),
        ),
        canonical_slice=empty,
        delivered_turn=ByteDigestProjection(
            bytes=2,
            sha256=_digest("f"),
        ),
        submit_keys=CountDigestProjection(
            count=1,
            sha256=_digest("1"),
        ),
    )
    with pytest.raises(ValueError, match="canonical_slice"):
        encode_event(
            seq=1,
            event="turn_offer_requested",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload={"turn": empty_materialization},
        )


def test_event_encoding_rejects_attempt_scope_digest_mismatch() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    attempt = _attempt()
    attempt["scope_sha256"] = _digest("f")

    with pytest.raises(ValueError, match="attempt"):
        encode_event(
            seq=1,
            event="task_start_requested",
            attempt=attempt,
            observed_at=_OBSERVED_AT,
            payload=_event_payloads()["task_start_requested"],
        )


def test_encoding_revalidates_tampered_frozen_nested_values() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    turn = _turn()
    object.__setattr__(turn, "delivery_ordinal", True)
    payload = _event_payloads()["task_start_requested"]
    payload["turn"] = turn
    with pytest.raises(TypeError, match="delivery_ordinal"):
        encode_event(
            seq=1,
            event="task_start_requested",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )

    manifest = _manifest("frozen")
    object.__setattr__(manifest, "manifest_sha256", "sha256:" + "A" * 64)
    payload = _event_payloads()["candidate_frozen"]
    payload["candidate_manifest"] = manifest
    with pytest.raises(ValueError, match="manifest"):
        encode_event(
            seq=1,
            event="candidate_frozen",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )


@pytest.mark.parametrize(
    ("event", "field", "value"),
    (
        ("submit_received", "submission_ordinal", True),
        ("submit_received", "configured_total", 4),
        ("submit_received", "remaining_before", 1),
        ("retry_queued", "next_submission_ordinal", 3),
        ("candidate_reset", "postcondition", "paths_absent"),
        ("publication_succeeded", "commit_status", "committed"),
        ("join_started", "remaining_budget_ms", False),
        (
            "ingress_shutdown_finished",
            "endpoint_zero_survivor_proven",
            False,
        ),
        (
            "ingress_shutdown_failed",
            "endpoint_zero_survivor_proven",
            True,
        ),
    ),
)
def test_event_encoding_rejects_scalar_and_ordinal_contract_errors(
    event: str,
    field: str,
    value: object,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    payload = _event_payloads()[event]
    payload[field] = value

    with pytest.raises((TypeError, ValueError)):
        encode_event(
            seq=1,
            event=event,
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )


def test_encoding_receipt_status_and_manifest_are_event_specific() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    started = _event_payloads()["task_started"]
    started["receipt"] = _receipt("offered")
    with pytest.raises(ValueError, match="receipt"):
        encode_event(
            seq=1,
            event="task_started",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=started,
        )

    rejected = _event_payloads()["validation_rejected"]
    rejected["candidate_manifest"] = _manifest("frozen")
    with pytest.raises(ValueError, match="manifest"):
        encode_event(
            seq=1,
            event="validation_rejected",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=rejected,
        )


@pytest.mark.parametrize(
    "candidate_manifest",
    (
        _digest("a"),
        {"manifest_sha256": _digest("a")},
        "artifacts/candidate-manifest.json",
    ),
)
def test_manifest_events_reject_digest_only_or_external_manifest(
    candidate_manifest: object,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    payload = _event_payloads()["candidate_frozen"]
    payload["candidate_manifest"] = candidate_manifest

    with pytest.raises((TypeError, ValueError), match="manifest"):
        encode_event(
            seq=1,
            event="candidate_frozen",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )


def test_embedded_manifest_is_complete_ordered_and_recomputably_sealed() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    payload = _decode(
        encode_event(
            seq=1,
            event="candidate_frozen",
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=_event_payloads()["candidate_frozen"],
        )
    )["payload"]
    manifest = payload["candidate_manifest"]
    without_seal = {
        key: value
        for key, value in manifest.items()
        if key != "manifest_sha256"
    }
    expected = "sha256:" + hashlib.sha256(
        json.dumps(
            without_seal,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()

    assert [row["role"] for row in manifest["rows"]] == [
        "expected_output",
        "expected_output",
        "structured_bundle",
    ]
    assert [row["contract_ordinal"] for row in manifest["rows"]] == [
        0,
        1,
        2,
    ]
    assert all(row["presence"] == "regular" for row in manifest["rows"])
    assert manifest["manifest_sha256"] == expected


def test_manifest_model_rejects_tamper_order_and_nonregular_frozen_rows() -> None:
    rows = _rows(regular=True)
    with pytest.raises(ValueError, match="ordinals"):
        CandidateDigestManifest.create(
            submission_ordinal=1,
            disposition="rejected",
            rows=(
                CandidateDigestRow(
                    contract_ordinal=4,
                    role=rows[0].role,
                    logical_name=rows[0].logical_name,
                    workspace_relative_path=rows[0].workspace_relative_path,
                    presence=rows[0].presence,
                    byte_length=rows[0].byte_length,
                    sha256=rows[0].sha256,
                ),
                *rows[1:],
            ),
        )
    with pytest.raises(ValueError, match="frozen"):
        CandidateDigestManifest.create(
            submission_ordinal=1,
            disposition="frozen",
            rows=_rows(regular=False),
        )


def test_writer_creates_exact_path_and_fsyncs_each_contiguous_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    fsync_calls: list[int] = []
    real_fsync = os.fsync

    def recording_fsync(descriptor: int) -> None:
        fsync_calls.append(descriptor)
        real_fsync(descriptor)

    monkeypatch.setattr(ledger.os, "fsync", recording_fsync)
    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    creation_fsyncs = len(fsync_calls)
    assert creation_fsyncs >= 2

    writer.append(
        "task_start_requested",
        _event_payloads()["task_start_requested"],
        observed_at=_OBSERVED_AT,
    )
    order = ["append_returned"]
    writer.append(
        "task_started",
        _event_payloads()["task_started"],
        observed_at=_OBSERVED_AT,
    )
    order.append("dependent_action")
    writer.close()

    rows = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
    ]
    assert writer.path == tmp_path / ledger.ledger_relative_path(_scope(), 1)
    assert [row["seq"] for row in rows] == [0, 1, 2]
    assert len(fsync_calls) >= creation_fsyncs + 2
    assert order == ["append_returned", "dependent_action"]


def test_writer_construction_is_factory_only() -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        ProviderPromptPhaseLedgerWriter,
    )

    with pytest.raises(TypeError, match="factory-only"):
        ProviderPromptPhaseLedgerWriter()


def test_writer_serializes_concurrent_appends_and_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    real_encode = ledger.encode_event
    active = 0
    maximum_active = 0
    activity_lock = threading.Lock()

    def probing_encode(**arguments: Any) -> bytes:
        nonlocal active, maximum_active
        with activity_lock:
            active += 1
            maximum_active = max(maximum_active, active)
        time.sleep(0.01)
        try:
            return real_encode(**arguments)
        finally:
            with activity_lock:
                active -= 1

    monkeypatch.setattr(ledger, "encode_event", probing_encode)
    errors: list[BaseException] = []

    def append_one() -> None:
        try:
            writer.append(
                "task_start_requested",
                _event_payloads()["task_start_requested"],
                observed_at=_OBSERVED_AT,
            )
        except BaseException as exc:
            errors.append(exc)

    append_threads = [
        threading.Thread(target=append_one)
        for _index in range(8)
    ]
    for thread in append_threads:
        thread.start()
    for thread in append_threads:
        thread.join(timeout=2)

    assert all(not thread.is_alive() for thread in append_threads)
    assert errors == []
    assert maximum_active == 1

    entered_write = threading.Event()
    release_write = threading.Event()
    real_write_all = ledger._write_all

    def controlled_write(descriptor: int, payload: bytes) -> None:
        entered_write.set()
        assert release_write.wait(timeout=2)
        real_write_all(descriptor, payload)

    monkeypatch.setattr(ledger, "_write_all", controlled_write)
    append_thread = threading.Thread(target=append_one)
    close_thread = threading.Thread(target=writer.close)
    append_thread.start()
    assert entered_write.wait(timeout=2)
    close_thread.start()
    time.sleep(0.02)
    assert close_thread.is_alive()
    release_write.set()
    append_thread.join(timeout=2)
    close_thread.join(timeout=2)

    assert errors == []
    assert not append_thread.is_alive()
    assert not close_thread.is_alive()
    rows = [
        json.loads(line)
        for line in writer.path.read_text(encoding="utf-8").splitlines()
    ]
    assert [row["seq"] for row in rows] == list(range(10))


def test_writer_durably_establishes_each_directory_component_in_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    real_fsync = os.fsync
    fsynced: list[Path] = []

    def recording_fsync(descriptor: int) -> None:
        target = Path(os.readlink(f"/proc/self/fd/{descriptor}"))
        fsynced.append(target)
        real_fsync(descriptor)

    monkeypatch.setattr(ledger.os, "fsync", recording_fsync)
    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    writer.close()

    relative_parent = ledger.ledger_relative_path(
        _scope(),
        1,
    ).parent
    expected_fsync_order = [tmp_path]
    components: list[Path] = []
    current = tmp_path
    for part in relative_parent.parts:
        child = current / part
        components.append(child)
        expected_fsync_order.extend((child, current))
        current = child
    expected_fsync_order.extend((writer.path, writer.path.parent))

    assert fsynced == expected_fsync_order

    fsynced.clear()
    reused_writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=2,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    reused_writer.close()

    assert fsynced == [
        tmp_path,
        *components,
        reused_writer.path,
        reused_writer.path.parent,
    ]


def test_writer_completes_binary_short_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    real_write = os.write

    def short_write(descriptor: int, payload: bytes) -> int:
        return real_write(descriptor, payload[:7])

    monkeypatch.setattr(ledger.os, "write", short_write)
    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    writer.append(
        "task_start_requested",
        _event_payloads()["task_start_requested"],
        observed_at=_OBSERVED_AT,
    )
    writer.close()

    assert [
        json.loads(line)["seq"]
        for line in writer.path.read_bytes().splitlines()
    ] == [0, 1]


def test_writer_is_poisoned_after_append_fsync_ambiguity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("uncertain")

    monkeypatch.setattr(ledger.os, "fsync", fail_fsync)
    with pytest.raises(RuntimeError, match="durability is uncertain"):
        writer.append(
            "task_start_requested",
            _event_payloads()["task_start_requested"],
            observed_at=_OBSERVED_AT,
        )
    with pytest.raises(RuntimeError, match="poisoned"):
        writer.append(
            "task_start_requested",
            _event_payloads()["task_start_requested"],
            observed_at=_OBSERVED_AT,
        )
    writer.close()


def test_writer_close_retires_descriptor_before_delayed_close_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    writer = ledger.ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    bound_descriptor = writer._descriptor
    real_close = os.close
    delayed_error_pending = True

    def release_then_raise(descriptor: int) -> None:
        nonlocal delayed_error_pending
        if descriptor == bound_descriptor and delayed_error_pending:
            delayed_error_pending = False
            real_close(descriptor)
            raise OSError("delayed close failure")
        real_close(descriptor)

    monkeypatch.setattr(ledger.os, "close", release_then_raise)
    with pytest.raises(OSError, match="delayed close failure"):
        writer.close()

    unrelated_path = tmp_path / "unrelated"
    unrelated_descriptor = os.open(
        unrelated_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    try:
        assert unrelated_descriptor == bound_descriptor
        os.write(unrelated_descriptor, b"unrelated")

        writer.close()
        with pytest.raises(RuntimeError, match="closed"):
            writer.append(
                "task_start_requested",
                _event_payloads()["task_start_requested"],
                observed_at=_OBSERVED_AT,
            )

        os.write(unrelated_descriptor, b"-still-open")
    finally:
        real_close(unrelated_descriptor)

    assert unrelated_path.read_bytes() == b"unrelated-still-open"


def test_writer_create_preserves_primary_error_when_cleanup_close_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    class PrimaryHeaderError(RuntimeError):
        pass

    opened_file_descriptor: int | None = None
    real_close = os.close

    def fail_header_write(descriptor: int, _payload: bytes) -> None:
        nonlocal opened_file_descriptor
        opened_file_descriptor = descriptor
        raise PrimaryHeaderError("primary header failure")

    def fail_cleanup_close(descriptor: int) -> None:
        if descriptor == opened_file_descriptor:
            real_close(descriptor)
            raise OSError("secondary cleanup failure")
        real_close(descriptor)

    monkeypatch.setattr(ledger, "_write_all", fail_header_write)
    monkeypatch.setattr(ledger.os, "close", fail_cleanup_close)

    with pytest.raises(
        PrimaryHeaderError,
        match="primary header failure",
    ) as raised:
        ledger.ProviderPromptPhaseLedgerWriter.create(
            tmp_path,
            scope=_scope(),
            ordinal=1,
            cut=_cut(),
            materialization_attempts=2,
            created_at=_CREATED_AT,
        )

    assert any(
        "secondary cleanup failure" in note
        for note in getattr(raised.value, "__notes__", ())
    )


@pytest.mark.parametrize(
    "terminal_event",
    ("publication_succeeded", "terminal_failed"),
)
def test_writer_rejects_append_after_locally_recorded_terminal(
    tmp_path: Path,
    terminal_event: str,
) -> None:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        ProviderPromptPhaseLedgerWriter,
    )

    writer = ProviderPromptPhaseLedgerWriter.create(
        tmp_path,
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )
    writer.append(
        terminal_event,
        _event_payloads()[terminal_event],
        observed_at=_OBSERVED_AT,
    )

    with pytest.raises(RuntimeError, match="terminal"):
        writer.append(
            "task_start_requested",
            _event_payloads()["task_start_requested"],
            observed_at=_OBSERVED_AT,
        )
    writer.close()


def test_writer_does_not_parse_history_or_expose_runtime_authority() -> None:
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    public_names = {
        name
        for name in vars(ledger)
        if not name.startswith("_")
    }

    assert not {
        "parse",
        "validate_history",
        "resume",
        "retry",
        "result",
        "settle",
        "reconstruct",
    }.intersection(public_names)


def _ledger_header_bytes() -> bytes:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_header,
    )

    return encode_header(
        scope=_scope(),
        ordinal=1,
        cut=_cut(),
        materialization_attempts=2,
        created_at=_CREATED_AT,
    )


def _ledger_bytes(
    events: list[tuple[str, dict[str, object]]],
) -> bytes:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        encode_event,
    )

    rows = [_ledger_header_bytes()]
    rows.extend(
        encode_event(
            seq=index,
            event=event,
            attempt=_attempt(),
            observed_at=_OBSERVED_AT,
            payload=payload,
        )
        for index, (event, payload) in enumerate(events, start=1)
    )
    return b"".join(rows)


_EVENT_DIAGNOSTIC_REASONS = {
    "task_start_failed": (
        "adapter_start_failed",
        "deadline_exhausted_before_start",
        "deadline_exhausted_during_start",
    ),
    "initial_turn_offer_failed": (
        "initial_offer_failed",
        "deadline_exhausted_before_initial_offer",
        "deadline_exhausted_during_initial_offer",
    ),
    "retry_turn_offer_failed": (
        "retry_offer_failed",
        "deadline_exhausted_before_retry_offer",
        "deadline_exhausted_during_retry_offer",
    ),
    "close_offer_failed": (
        "close_offer_failed",
        "deadline_exhausted_before_close_offer",
        "deadline_exhausted_during_close_offer",
    ),
    "ingress_shutdown_failed": (
        "ingress_shutdown_failed",
        "deadline_exhausted_before_ingress_shutdown",
        "deadline_exhausted_during_ingress_shutdown",
    ),
    "join_failed": (
        "natural_join_failed",
        "deadline_exhausted_before_join",
        "deadline_exhausted_during_join",
    ),
    "publication_failed": (
        "deadline_exhausted_before_evidence_publication",
        "deadline_exhausted_during_evidence_publication",
        "deadline_exhausted_before_frozen_restoration",
        "deadline_exhausted_during_frozen_restoration",
        "deadline_exhausted_before_frozen_verification",
        "deadline_exhausted_during_frozen_verification",
        "deadline_exhausted_before_state_commit",
        "deadline_exhausted_during_state_commit_preparation",
        "evidence_publication_failed",
        "frozen_restoration_failed",
        "frozen_verification_failed",
        "workflow_state_commit_failed",
    ),
}


def _payload_diagnostic(
    payload: dict[str, object],
    reason: str,
) -> dict[str, object]:
    return {
        **payload,
        "diagnostic": _diagnostic_for_reason(reason),
    }


def _diagnostic_event_ledger(
    family: str,
    reason: str,
) -> bytes:
    payloads = _event_payloads()
    if family == "task_start_failed":
        start_failure = payloads["task_start_failed"][
            "start_failure_outcome"
        ]
        if reason == "deadline_exhausted_before_start":
            start_failure = _no_allocation_start_failure("start_timeout")
        elif reason == "deadline_exhausted_during_start":
            start_failure = _allocated_start_failure(
                error_code="start_timeout",
            )
        events = [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    **_payload_diagnostic(
                        payloads["task_start_failed"],
                        reason,
                    ),
                    "start_failure_outcome": start_failure,
                },
            ),
        ]
    elif family == "initial_turn_offer_failed":
        events = [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("turn_offer_requested", payloads["turn_offer_requested"]),
            (
                "turn_offer_failed",
                _payload_diagnostic(
                    payloads["turn_offer_failed"],
                    reason,
                ),
            ),
        ]
    elif family == "retry_turn_offer_failed":
        retry_turn = payloads["retry_queued"]["turn"]
        events = [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("turn_offer_requested", payloads["turn_offer_requested"]),
            ("turn_offered", payloads["turn_offered"]),
            ("submit_received", payloads["submit_received"]),
            ("validation_rejected", payloads["validation_rejected"]),
            ("candidate_reset", payloads["candidate_reset"]),
            ("retry_queued", payloads["retry_queued"]),
            ("turn_offer_requested", {"turn": retry_turn}),
            (
                "turn_offer_failed",
                {
                    "turn": retry_turn,
                    "diagnostic": _diagnostic_for_reason(reason),
                },
            ),
        ]
    elif family == "close_offer_failed":
        events = [
            *_normal_until_close()[:-1],
            (
                "close_offer_failed",
                _payload_diagnostic(
                    payloads["close_offer_failed"],
                    reason,
                ),
            ),
        ]
    elif family == "ingress_shutdown_failed":
        events = [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("turn_offer_requested", payloads["turn_offer_requested"]),
            (
                "turn_offer_failed",
                _payload_diagnostic(
                    payloads["turn_offer_failed"],
                    "initial_offer_failed",
                ),
            ),
            ("cleanup_finished", _complete_cleanup()),
            (
                "ingress_shutdown_started",
                payloads["ingress_shutdown_started"],
            ),
            (
                "ingress_shutdown_failed",
                _payload_diagnostic(
                    payloads["ingress_shutdown_failed"],
                    reason,
                ),
            ),
        ]
    elif family == "join_failed":
        events = [
            *_normal_until_join_started(),
            (
                "join_failed",
                _payload_diagnostic(payloads["join_failed"], reason),
            ),
        ]
    elif family == "publication_failed":
        events = [
            *_normal_until_join_started(),
            ("join_succeeded", payloads["join_succeeded"]),
            ("publication_started", payloads["publication_started"]),
            (
                "publication_failed",
                _payload_diagnostic(
                    payloads["publication_failed"],
                    reason,
                ),
            ),
        ]
    else:
        raise AssertionError(f"unknown diagnostic family: {family}")
    return _ledger_bytes(events)


def _canonical_line(row: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("ascii")
        + b"\n"
    )


def _replace_row(
    ledger_bytes: bytes,
    ordinal: int,
    mutation: Any,
) -> bytes:
    lines = ledger_bytes.splitlines(keepends=True)
    row = json.loads(lines[ordinal])
    mutation(row)
    lines[ordinal] = _canonical_line(row)
    return b"".join(lines)


def _validate(ledger_bytes: bytes) -> dict[str, Any]:
    from orchestrator.workflow.provider_phased_delivery.ledger import (
        validate_ledger_bytes,
    )

    return validate_ledger_bytes(ledger_bytes)


def _complete_cleanup() -> dict[str, object]:
    return {
        "cleanup_status": "complete",
        "abort_calls": 1,
        "provider_cleanup_proof": PhasedFailedCleanupEvidence(
            disposition="failed_cleanup",
            pane_absent=True,
            server_absent=True,
            cleanup_complete=True,
            error_code=None,
        ),
        "cleanup_diagnostic": None,
        "provider_zero_survivor_proven": True,
    }


def _incomplete_cleanup(
    *,
    proof: PhasedFailedCleanupEvidence | None,
) -> dict[str, object]:
    if proof is None or proof.error_code is not None:
        reason = "adapter_cleanup_failed"
    else:
        reason = "provider_zero_survivor_unproven"
    return {
        "cleanup_status": "incomplete",
        "abort_calls": 1,
        "provider_cleanup_proof": proof,
        "cleanup_diagnostic": _adapter_cleanup_diagnostic(reason),
        "provider_zero_survivor_proven": False,
    }


def _null_cleanup(
    *,
    abort_calls: int,
    reason: str,
) -> dict[str, object]:
    return {
        "cleanup_status": "incomplete",
        "abort_calls": abort_calls,
        "provider_cleanup_proof": None,
        "cleanup_diagnostic": _adapter_cleanup_diagnostic(reason),
        "provider_zero_survivor_proven": False,
    }


def _terminal_from_cleanup(
    cleanup: dict[str, object],
    *,
    endpoint: str,
    diagnostic: PhasedDeliveryDiagnostic | None = None,
) -> dict[str, object]:
    return {
        "diagnostic": (
            _diagnostic() if diagnostic is None else diagnostic
        ),
        "cleanup_status": cleanup["cleanup_status"],
        "cleanup_diagnostic": cleanup["cleanup_diagnostic"],
        "endpoint_shutdown_status": endpoint,
        "natural_shutdown_proof": None,
    }


def _exact_diagnostic(value: object) -> PhasedDeliveryDiagnostic:
    assert type(value) is PhasedDeliveryDiagnostic
    return value


def _normal_until_close() -> list[tuple[str, dict[str, object]]]:
    payloads = _event_payloads()
    return [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offered", payloads["turn_offered"]),
        ("submit_received", payloads["submit_received"]),
        ("candidate_frozen", payloads["candidate_frozen"]),
        ("close_offer_requested", payloads["close_offer_requested"]),
        ("close_offered", payloads["close_offered"]),
    ]


def _normal_until_join_started() -> list[tuple[str, dict[str, object]]]:
    payloads = _event_payloads()
    return [
        *_normal_until_close(),
        (
            "ingress_shutdown_started",
            payloads["ingress_shutdown_started"],
        ),
        (
            "ingress_shutdown_finished",
            payloads["ingress_shutdown_finished"],
        ),
        ("join_started", payloads["join_started"]),
    ]


def _assert_complete(
    events: list[tuple[str, dict[str, object]]],
    terminal_event: str,
) -> None:
    result = _validate(_ledger_bytes(events))

    assert result == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "complete",
        "reason": "complete",
        "row_count": len(events) + 1,
        "last_contiguous_seq": len(events),
        "terminal_event": terminal_event,
    }


def test_validator_accepts_normal_success_and_header_only_prefix() -> None:
    payloads = _event_payloads()
    success = [
        *_normal_until_join_started(),
        ("join_succeeded", payloads["join_succeeded"]),
        ("publication_started", payloads["publication_started"]),
        ("publication_succeeded", payloads["publication_succeeded"]),
    ]

    _assert_complete(success, "publication_succeeded")
    assert _validate(_ledger_header_bytes()) == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "valid_prefix",
        "reason": "nonterminal_prefix",
        "row_count": 1,
        "last_contiguous_seq": 0,
        "terminal_event": None,
    }


def test_validator_grammar_accepts_t0_through_t4_terminalization() -> None:
    payloads = _event_payloads()
    cleanup = _complete_cleanup()

    t0 = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_start_failed", payloads["task_start_failed"]),
        ("cleanup_finished", payloads["cleanup_finished"]),
        ("terminal_failed", payloads["terminal_failed"]),
    ]
    t1 = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offer_failed", payloads["turn_offer_failed"]),
        ("cleanup_finished", cleanup),
        (
            "ingress_shutdown_started",
            payloads["ingress_shutdown_started"],
        ),
        (
            "ingress_shutdown_finished",
            payloads["ingress_shutdown_finished"],
        ),
        (
            "terminal_failed",
            _terminal_from_cleanup(
                cleanup,
                endpoint="complete",
                diagnostic=_exact_diagnostic(
                    payloads["turn_offer_failed"]["diagnostic"]
                ),
            ),
        ),
    ]
    t2a = [
        *_normal_until_close(),
        (
            "ingress_shutdown_started",
            payloads["ingress_shutdown_started"],
        ),
        ("cleanup_finished", cleanup),
        (
            "ingress_shutdown_finished",
            payloads["ingress_shutdown_finished"],
        ),
        (
            "terminal_failed",
            _terminal_from_cleanup(cleanup, endpoint="complete"),
        ),
    ]
    t2b_cleanup = _incomplete_cleanup(proof=None)
    t2b = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offer_failed", payloads["turn_offer_failed"]),
        ("cleanup_finished", t2b_cleanup),
        (
            "ingress_shutdown_started",
            payloads["ingress_shutdown_started"],
        ),
        (
            "ingress_shutdown_failed",
            payloads["ingress_shutdown_failed"],
        ),
        (
            "terminal_failed",
            _terminal_from_cleanup(
                t2b_cleanup,
                endpoint="incomplete",
                diagnostic=_exact_diagnostic(
                    payloads["turn_offer_failed"]["diagnostic"]
                ),
            ),
        ),
    ]
    t3 = [
        *_normal_until_join_started(),
        ("join_failed", payloads["join_failed"]),
        ("cleanup_finished", cleanup),
        (
            "terminal_failed",
            _terminal_from_cleanup(
                cleanup,
                endpoint="complete",
                diagnostic=_exact_diagnostic(
                    payloads["join_failed"]["diagnostic"]
                ),
            ),
        ),
    ]
    post_proof_terminal = {
        "diagnostic": _diagnostic(),
        "cleanup_status": "not_permitted",
        "cleanup_diagnostic": None,
        "endpoint_shutdown_status": "complete",
        "natural_shutdown_proof": _natural_proof(),
    }
    t4_after_join = [
        *_normal_until_join_started(),
        ("join_succeeded", payloads["join_succeeded"]),
        ("terminal_failed", post_proof_terminal),
    ]
    t4_direct = [
        *_normal_until_join_started(),
        ("terminal_failed", post_proof_terminal),
    ]

    for events in (t0, t1, t2a, t2b, t3, t4_after_join, t4_direct):
        _assert_complete(events, "terminal_failed")


def test_validator_distinguishes_t0_from_implicit_t1_allocation() -> None:
    payloads = _event_payloads()
    no_allocation = payloads["cleanup_finished"]
    no_endpoint_terminal = payloads["terminal_failed"]
    live_cleanup = _complete_cleanup()
    live_no_endpoint_terminal = _terminal_from_cleanup(
        live_cleanup,
        endpoint="not_allocated",
    )
    complete_endpoint_terminal = _terminal_from_cleanup(
        live_cleanup,
        endpoint="complete",
    )
    cases = (
        [
            ("cleanup_finished", no_allocation),
            ("terminal_failed", no_endpoint_terminal),
        ],
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("cleanup_finished", no_allocation),
            ("terminal_failed", no_endpoint_terminal),
        ],
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("cleanup_finished", live_cleanup),
            ("terminal_failed", live_no_endpoint_terminal),
        ],
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("cleanup_finished", live_cleanup),
            (
                "ingress_shutdown_started",
                payloads["ingress_shutdown_started"],
            ),
            (
                "ingress_shutdown_finished",
                payloads["ingress_shutdown_finished"],
            ),
            ("terminal_failed", complete_endpoint_terminal),
        ],
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            (
                "turn_offer_requested",
                payloads["turn_offer_requested"],
            ),
            ("cleanup_finished", live_cleanup),
            (
                "ingress_shutdown_started",
                payloads["ingress_shutdown_started"],
            ),
            (
                "ingress_shutdown_finished",
                payloads["ingress_shutdown_finished"],
            ),
            ("terminal_failed", complete_endpoint_terminal),
        ],
    )

    for events in cases:
        _assert_complete(events, "terminal_failed")


def test_validator_rejects_t0_t1_endpoint_inconsistency() -> None:
    payloads = _event_payloads()
    live_cleanup = _complete_cleanup()
    cases = (
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("cleanup_finished", live_cleanup),
            (
                "terminal_failed",
                _terminal_from_cleanup(live_cleanup, endpoint="complete"),
            ),
        ],
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            (
                "turn_offer_requested",
                payloads["turn_offer_requested"],
            ),
            ("cleanup_finished", live_cleanup),
            (
                "terminal_failed",
                _terminal_from_cleanup(
                    live_cleanup,
                    endpoint="not_allocated",
                ),
            ),
        ],
        [
            ("cleanup_finished", live_cleanup),
            (
                "terminal_failed",
                _terminal_from_cleanup(
                    live_cleanup,
                    endpoint="not_allocated",
                ),
            ),
        ],
    )

    for events in cases:
        assert _validate(_ledger_bytes(events))["reason"] in {
            "payload_invalid",
            "event_order_invalid",
        }


def test_validator_grammar_rejects_duplicate_cleanup_ingress_and_post_terminal(
) -> None:
    payloads = _event_payloads()
    cleanup = _complete_cleanup()
    base = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offer_failed", payloads["turn_offer_failed"]),
        ("cleanup_finished", cleanup),
    ]
    cases = (
        [*base, ("cleanup_finished", cleanup)],
        [
            *base,
            (
                "ingress_shutdown_started",
                payloads["ingress_shutdown_started"],
            ),
            (
                "ingress_shutdown_started",
                payloads["ingress_shutdown_started"],
            ),
        ],
        [
            *_normal_until_join_started(),
            ("join_succeeded", payloads["join_succeeded"]),
            ("publication_started", payloads["publication_started"]),
            (
                "publication_succeeded",
                payloads["publication_succeeded"],
            ),
            ("terminal_failed", payloads["terminal_failed"]),
        ],
    )

    for events in cases:
        assert _validate(_ledger_bytes(events))["reason"] == (
            "event_order_invalid"
        )


@pytest.mark.parametrize(
    "cleanup",
    (
        _complete_cleanup(),
        _incomplete_cleanup(
            proof=PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=False,
                server_absent=True,
                cleanup_complete=False,
                error_code=None,
            )
        ),
        _incomplete_cleanup(proof=None),
    ),
)
def test_validator_proof_unions_accept_live_cleanup_projections(
    cleanup: dict[str, object],
) -> None:
    payloads = _event_payloads()
    endpoint = (
        "complete"
        if cleanup["cleanup_status"] == "complete"
        else "incomplete"
    )
    outcome = (
        payloads["ingress_shutdown_finished"]
        if endpoint == "complete"
        else payloads["ingress_shutdown_failed"]
    )
    outcome_event = (
        "ingress_shutdown_finished"
        if endpoint == "complete"
        else "ingress_shutdown_failed"
    )
    events = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offer_failed", payloads["turn_offer_failed"]),
        ("cleanup_finished", cleanup),
        (
            "ingress_shutdown_started",
            payloads["ingress_shutdown_started"],
        ),
        (outcome_event, outcome),
        (
            "terminal_failed",
            _terminal_from_cleanup(
                cleanup,
                endpoint=endpoint,
                diagnostic=_exact_diagnostic(
                    payloads["turn_offer_failed"]["diagnostic"]
                ),
            ),
        ),
    ]

    _assert_complete(events, "terminal_failed")


@pytest.mark.parametrize(
    "cleanup",
    (
        _null_cleanup(
            abort_calls=0,
            reason="deadline_exhausted_before_adapter_cleanup",
        ),
        _null_cleanup(
            abort_calls=1,
            reason="deadline_exhausted_during_adapter_cleanup",
        ),
        _null_cleanup(
            abort_calls=1,
            reason="adapter_cleanup_failed",
        ),
        _incomplete_cleanup(
            proof=PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=False,
                server_absent=True,
                cleanup_complete=False,
                error_code=None,
            )
        ),
        _incomplete_cleanup(
            proof=PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=False,
                server_absent=True,
                cleanup_complete=False,
                error_code="tmux_unavailable",
            )
        ),
    ),
)
def test_validator_accepts_exact_live_cleanup_failure_matrix(
    cleanup: dict[str, object],
) -> None:
    payloads = _event_payloads()
    _assert_complete(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("cleanup_finished", cleanup),
            (
                "terminal_failed",
                _terminal_from_cleanup(
                    cleanup,
                    endpoint="not_allocated",
                ),
            ),
        ],
        "terminal_failed",
    )


def test_validator_rejects_cleanup_source_and_diagnostic_mismatches() -> None:
    payloads = _event_payloads()
    incomplete_proof = PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=False,
        server_absent=True,
        cleanup_complete=False,
        error_code=None,
    )
    invalid_cleanups = (
        _null_cleanup(
            abort_calls=0,
            reason="adapter_cleanup_failed",
        ),
        _null_cleanup(
            abort_calls=1,
            reason="deadline_exhausted_before_adapter_cleanup",
        ),
        {
            **_null_cleanup(
                abort_calls=1,
                reason="adapter_cleanup_failed",
            ),
            "cleanup_diagnostic": _diagnostic(),
        },
        {
            **_incomplete_cleanup(proof=incomplete_proof),
            "abort_calls": 0,
        },
        {
            **_incomplete_cleanup(proof=incomplete_proof),
            "cleanup_diagnostic": _adapter_cleanup_diagnostic(
                "adapter_cleanup_failed"
            ),
        },
        {
            **_complete_cleanup(),
            "abort_calls": 0,
        },
        payloads["cleanup_finished"],
    )

    for cleanup in invalid_cleanups:
        ledger = _ledger_bytes(
            [
                (
                    "task_start_requested",
                    payloads["task_start_requested"],
                ),
                ("task_started", payloads["task_started"]),
                ("cleanup_finished", cleanup),
            ]
        )
        assert _validate(ledger)["reason"] == "payload_invalid"


def test_validator_accepts_only_active_handle_cleanup_projection() -> None:
    payloads = _event_payloads()
    raw = FailedCleanupProof(
        disposition="failed_cleanup",
        handle_id="active-handle",
        pane_absent=False,
        server_absent=True,
        cleanup_complete=False,
        error_code=None,
    )
    projected = project_phased_failed_cleanup_evidence(
        raw,
        active_handle_id="active-handle",
    )
    mismatched = project_phased_failed_cleanup_evidence(
        raw,
        active_handle_id="different-handle",
    )

    assert type(projected) is PhasedFailedCleanupEvidence
    assert mismatched is None
    _assert_complete(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("cleanup_finished", _incomplete_cleanup(proof=projected)),
            (
                "terminal_failed",
                _terminal_from_cleanup(
                    _incomplete_cleanup(proof=projected),
                    endpoint="not_allocated",
                ),
            ),
        ],
        "terminal_failed",
    )


def test_validator_failed_start_requires_exact_cleanup_proof_copy() -> None:
    payloads = _event_payloads()
    valid = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_start_failed", payloads["task_start_failed"]),
        ("cleanup_finished", payloads["cleanup_finished"]),
        ("terminal_failed", payloads["terminal_failed"]),
    ]
    corrupted = _replace_row(
        _ledger_bytes(valid),
        3,
        lambda row: row["payload"]["provider_cleanup_proof"].__setitem__(
            "proof_complete",
            False,
        ),
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    ("cleanup_status", "proof", "survivor"),
    (
        (
            "completed",
            PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=True,
                server_absent=True,
                cleanup_complete=True,
                error_code=None,
            ),
            True,
        ),
        (
            "incomplete",
            PhasedFailedCleanupEvidence(
                disposition="failed_cleanup",
                pane_absent=False,
                server_absent=True,
                cleanup_complete=False,
                error_code=(
                    "interactive_terminal_start_cleanup_incomplete"
                ),
            ),
            False,
        ),
    ),
)
def test_validator_accepts_allocated_failed_start_exact_cleanup_copy(
    cleanup_status: str,
    proof: PhasedFailedCleanupEvidence,
    survivor: bool,
) -> None:
    payloads = _event_payloads()
    start_failure = InteractiveTerminalStartOutcome(
        status="failed",
        error_code=(
            "interactive_terminal_start_cleanup_incomplete"
            if cleanup_status == "incomplete"
            else "tmux_unavailable"
        ),
        backend_allocation="possible_or_allocated",
        cleanup_status=cleanup_status,
        provider_zero_survivor_proven=survivor,
        proof=proof,
    )
    ledger_cleanup_status = (
        "complete" if cleanup_status == "completed" else cleanup_status
    )
    cleanup = {
        "cleanup_status": ledger_cleanup_status,
        "abort_calls": 0,
        "provider_cleanup_proof": proof,
        "cleanup_diagnostic": (
            None
            if cleanup_status == "completed"
            else _adapter_start_cleanup_incomplete_diagnostic()
        ),
        "provider_zero_survivor_proven": survivor,
    }

    _assert_complete(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    "turn": payloads["task_start_failed"]["turn"],
                    "diagnostic": payloads["task_start_failed"][
                        "diagnostic"
                    ],
                    "start_failure_outcome": start_failure,
                },
            ),
            ("cleanup_finished", cleanup),
            (
                "terminal_failed",
                _terminal_from_cleanup(
                    cleanup,
                    endpoint="not_allocated",
                    diagnostic=_exact_diagnostic(
                        payloads["task_start_failed"]["diagnostic"]
                    ),
                ),
            ),
        ],
        "terminal_failed",
    )


def test_validator_rejects_allocated_failed_start_cleanup_proof_mismatch(
) -> None:
    payloads = _event_payloads()
    start_proof = PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=False,
        server_absent=True,
        cleanup_complete=False,
        error_code="interactive_terminal_start_cleanup_incomplete",
    )
    different_cleanup_proof = PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=True,
        server_absent=False,
        cleanup_complete=False,
        error_code="interactive_terminal_start_cleanup_incomplete",
    )
    start_failure = InteractiveTerminalStartOutcome(
        status="failed",
        error_code="interactive_terminal_start_cleanup_incomplete",
        backend_allocation="possible_or_allocated",
        cleanup_status="incomplete",
        provider_zero_survivor_proven=False,
        proof=start_proof,
    )
    cleanup = {
        "cleanup_status": "incomplete",
        "abort_calls": 0,
        "provider_cleanup_proof": different_cleanup_proof,
        "cleanup_diagnostic": (
            _adapter_start_cleanup_incomplete_diagnostic()
        ),
        "provider_zero_survivor_proven": False,
    }
    corrupted = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    "turn": payloads["task_start_failed"]["turn"],
                    "diagnostic": payloads["task_start_failed"][
                        "diagnostic"
                    ],
                    "start_failure_outcome": start_failure,
                },
            ),
            ("cleanup_finished", cleanup),
        ]
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


def test_validator_rejects_raw_or_handle_mismatched_cleanup_proof() -> None:
    payloads = _event_payloads()
    cleanup = _complete_cleanup()
    events = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offer_failed", payloads["turn_offer_failed"]),
        ("cleanup_finished", cleanup),
    ]
    raw_proof = FailedCleanupProof(
        disposition="failed_cleanup",
        handle_id="foreign-handle",
        pane_absent=True,
        server_absent=True,
        cleanup_complete=True,
        error_code=None,
    )
    corrupted = _replace_row(
        _ledger_bytes(events),
        5,
        lambda row: row["payload"].__setitem__(
            "provider_cleanup_proof",
            {
                "disposition": raw_proof.disposition,
                "handle_id": raw_proof.handle_id,
                "pane_absent": raw_proof.pane_absent,
                "server_absent": raw_proof.server_absent,
                "cleanup_complete": raw_proof.cleanup_complete,
                "error_code": raw_proof.error_code,
            },
        ),
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


def test_validator_returns_closed_physical_failure_results() -> None:
    header = _ledger_header_bytes()
    invalid_utf8 = header + b"\xff\n"
    invalid_json = header + b"{\n"
    noncanonical = header + b'{ "record_kind": "event" }\n'
    truncated = header + b'{"record_kind":'

    assert _validate(b"")["reason"] == "missing_header"
    assert _validate(invalid_utf8)["reason"] == "invalid_utf8"
    assert _validate(invalid_json)["reason"] == "invalid_json"
    assert _validate(noncanonical)["reason"] == "noncanonical_json"
    assert _validate(truncated) == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "truncated",
        "reason": "truncated_final_row",
        "row_count": 1,
        "last_contiguous_seq": 0,
        "terminal_event": None,
    }


@pytest.mark.parametrize("shape", ("array", "object"))
def test_validator_closes_deep_json_decode_recursion_after_valid_header(
    shape: str,
) -> None:
    depth = 10_000
    nested = (
        b"[" * depth + b"0" + b"]" * depth
        if shape == "array"
        else b'{"a":' * depth + b"0" + b"}" * depth
    )

    assert _validate(_ledger_header_bytes() + nested + b"\n") == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "malformed",
        "reason": "invalid_json",
        "row_count": 1,
        "last_contiguous_seq": 0,
        "terminal_event": None,
    }


@pytest.mark.parametrize("shape", ("array", "object"))
def test_validator_closes_deep_json_canonicalization_recursion_after_header(
    shape: str,
) -> None:
    depth = 500
    nested = (
        b"[" * depth + b"0" + b"]" * depth
        if shape == "array"
        else b'{"a":' * depth + b"0" + b"}" * depth
    )

    assert _validate(_ledger_header_bytes() + nested + b"\n") == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "malformed",
        "reason": "noncanonical_json",
        "row_count": 2,
        "last_contiguous_seq": 0,
        "terminal_event": None,
    }


def test_validator_first_object_header_classification_precedes_keys() -> None:
    event_with_extra = json.loads(
        _ledger_bytes(
            [
                (
                    "task_start_requested",
                    _event_payloads()["task_start_requested"],
                )
            ]
        ).splitlines()[1]
    )
    event_with_extra["extra"] = None
    header_with_extra = json.loads(_ledger_header_bytes())
    header_with_extra["extra"] = None
    header_missing_key = json.loads(_ledger_header_bytes())
    del header_missing_key["created_at"]

    assert _validate(_canonical_line({}))["reason"] == "missing_header"
    assert _validate(_canonical_line(event_with_extra))["reason"] == (
        "missing_header"
    )
    assert _validate(_canonical_line(header_with_extra))["reason"] == (
        "unknown_key"
    )
    assert _validate(_canonical_line(header_missing_key))["reason"] == (
        "unknown_key"
    )


@pytest.mark.parametrize(
    "event_value",
    (
        [{}],
        [],
        None,
        True,
        False,
        "event",
        7,
        1.5,
    ),
)
def test_validator_non_object_event_rows_are_closed_unknown_key(
    event_value: object,
) -> None:
    encoded = (
        json.dumps(
            event_value,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )

    assert _validate(_ledger_header_bytes() + encoded) == {
        "schema_version": "provider_prompt_phase_ledger_validation.v1",
        "status": "malformed",
        "reason": "unknown_key",
        "row_count": 2,
        "last_contiguous_seq": 0,
        "terminal_event": None,
    }


@pytest.mark.parametrize(
    ("family", "reason"),
    tuple(
        (family, reason)
        for family, reasons in _EVENT_DIAGNOSTIC_REASONS.items()
        for reason in reasons
    ),
)
def test_validator_accepts_exact_event_diagnostic_reason_classes(
    family: str,
    reason: str,
) -> None:
    assert _validate(_diagnostic_event_ledger(family, reason))["reason"] == (
        "nonterminal_prefix"
    )


@pytest.mark.parametrize(
    ("reason", "start_failure"),
    (
        (
            "deadline_exhausted_before_start",
            _allocated_start_failure(error_code="start_timeout"),
        ),
        (
            "deadline_exhausted_during_start",
            _no_allocation_start_failure("start_timeout"),
        ),
        (
            "adapter_start_failed",
            _no_allocation_start_failure("start_timeout"),
        ),
        (
            "deadline_exhausted_before_start",
            _no_allocation_start_failure("tmux_unavailable"),
        ),
        (
            "deadline_exhausted_during_start",
            _allocated_start_failure(error_code="tmux_unavailable"),
        ),
        (
            "adapter_start_failed",
            _allocated_start_failure(error_code="start_timeout"),
        ),
        (
            "adapter_start_failed",
            _allocated_start_failure(
                error_code="tmux_unavailable",
                cleanup_status="incomplete",
            ),
        ),
        (
            "deadline_exhausted_during_start",
            _allocated_start_failure(
                error_code="start_timeout",
                cleanup_status="incomplete",
            ),
        ),
    ),
)
def test_validator_rejects_start_failure_cross_field_mismatch(
    reason: str,
    start_failure: InteractiveTerminalStartOutcome,
) -> None:
    payloads = _event_payloads()
    corrupted = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    **payloads["task_start_failed"],
                    "diagnostic": _diagnostic_for_reason(reason),
                    "start_failure_outcome": start_failure,
                },
            ),
        ]
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    "reason",
    (
        "adapter_start_failed",
        "deadline_exhausted_during_start",
    ),
)
def test_validator_accepts_exact_incomplete_start_cleanup_binding(
    reason: str,
) -> None:
    payloads = _event_payloads()
    ledger = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    **payloads["task_start_failed"],
                    "diagnostic": _diagnostic_for_reason(reason),
                    "start_failure_outcome": _allocated_start_failure(
                        error_code=(
                            "interactive_terminal_start_cleanup_incomplete"
                        ),
                        cleanup_status="incomplete",
                    ),
                },
            ),
        ]
    )

    assert _validate(ledger)["reason"] == "nonterminal_prefix"


@pytest.mark.parametrize(
    ("outcome_error", "proof_error"),
    (
        (
            "interactive_terminal_start_cleanup_incomplete",
            "tmux_unavailable",
        ),
        (
            "tmux_unavailable",
            "interactive_terminal_start_cleanup_incomplete",
        ),
    ),
)
def test_validator_rejects_one_sided_incomplete_start_cleanup_token(
    outcome_error: str,
    proof_error: str,
) -> None:
    payloads = _event_payloads()
    proof = PhasedFailedCleanupEvidence(
        disposition="failed_cleanup",
        pane_absent=False,
        server_absent=True,
        cleanup_complete=False,
        error_code=proof_error,
    )
    start_failure = InteractiveTerminalStartOutcome(
        status="failed",
        error_code=outcome_error,
        backend_allocation="possible_or_allocated",
        cleanup_status="incomplete",
        provider_zero_survivor_proven=False,
        proof=proof,
    )
    corrupted = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            (
                "task_start_failed",
                {
                    **payloads["task_start_failed"],
                    "start_failure_outcome": start_failure,
                },
            ),
        ]
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    ("family", "wrong_reason"),
    (
        ("task_start_failed", "initial_offer_failed"),
        ("initial_turn_offer_failed", "retry_offer_failed"),
        ("retry_turn_offer_failed", "initial_offer_failed"),
        ("close_offer_failed", "natural_join_failed"),
        ("ingress_shutdown_failed", "close_offer_failed"),
        ("join_failed", "ingress_shutdown_failed"),
        ("publication_failed", "natural_join_failed"),
    ),
)
def test_validator_rejects_cross_event_diagnostic_reason_classes(
    family: str,
    wrong_reason: str,
) -> None:
    assert _validate(
        _diagnostic_event_ledger(family, wrong_reason)
    )["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    "reasons",
    (
        ("output_validation_failed",),
        ("structured_result_validation_failed",),
        (
            "output_validation_failed",
            "structured_result_validation_failed",
        ),
    ),
)
def test_validator_accepts_closed_validation_rejection_sequence(
    reasons: tuple[str, ...],
) -> None:
    payloads = _event_payloads()
    rejection = {
        **payloads["validation_rejected"],
        "diagnostics": tuple(
            _diagnostic_for_reason(reason) for reason in reasons
        ),
    }
    events = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offered", payloads["turn_offered"]),
        ("submit_received", payloads["submit_received"]),
        ("validation_rejected", rejection),
    ]

    assert _validate(_ledger_bytes(events))["reason"] == (
        "nonterminal_prefix"
    )


@pytest.mark.parametrize(
    "reasons",
    (
        (
            "structured_result_validation_failed",
            "output_validation_failed",
        ),
        ("output_validation_failed", "output_validation_failed"),
        (
            "structured_result_validation_failed",
            "structured_result_validation_failed",
        ),
        ("initial_offer_failed",),
    ),
)
def test_validator_rejects_open_validation_rejection_sequence(
    reasons: tuple[str, ...],
) -> None:
    payloads = _event_payloads()
    rejection = {
        **payloads["validation_rejected"],
        "diagnostics": tuple(
            _diagnostic_for_reason(reason) for reason in reasons
        ),
    }
    events = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offered", payloads["turn_offered"]),
        ("submit_received", payloads["submit_received"]),
        ("validation_rejected", rejection),
    ]

    assert _validate(_ledger_bytes(events))["reason"] == "payload_invalid"


def test_validator_large_integer_category_is_host_limit_independent() -> None:
    digits = b"9" * 5000
    sequence = _ledger_bytes(
        [
            (
                "task_start_requested",
                _event_payloads()["task_start_requested"],
            )
        ]
    ).replace(b'"seq":1', b'"seq":' + digits, 1)
    payload = _ledger_bytes(
        [("submit_received", _event_payloads()["submit_received"])]
    ).replace(b'"configured_total":2', b'"configured_total":' + digits, 1)

    assert _validate(sequence)["reason"] == "sequence_invalid"
    assert _validate(payload)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    "suffix",
    (
        b'{"a":1,"a":2}\n',
        b'{"value":NaN}\n',
        b'{"value":Infinity}\n',
        b'{"value":-Infinity}\n',
    ),
)
def test_validator_rejects_duplicate_keys_and_non_json_constants(
    suffix: bytes,
) -> None:
    result = _validate(_ledger_header_bytes() + suffix)

    assert result["status"] == "malformed"
    assert result["reason"] == "invalid_json"


def test_validator_reason_precedence_is_closed_and_row_local() -> None:
    payloads = _event_payloads()
    base = _ledger_bytes(
        [("task_start_requested", payloads["task_start_requested"])]
    )
    mutations = (
        (
            "unknown_key",
            lambda row: (
                row.__setitem__("extra", None),
                row.__setitem__("seq", 9),
            ),
        ),
        (
            "unknown_event",
            lambda row: row.__setitem__("event", "unknown"),
        ),
        (
            "sequence_invalid",
            lambda row: (
                row.__setitem__("seq", 9),
                row.__setitem__("attempt", {}),
            ),
        ),
        (
            "attempt_mismatch",
            lambda row: (
                row["attempt"].__setitem__("ordinal", 2),
                row.__setitem__("payload", {}),
            ),
        ),
        (
            "payload_invalid",
            lambda row: (
                row.__setitem__("payload", {}),
                row.__setitem__("event", "task_started"),
            ),
        ),
        (
            "event_order_invalid",
            lambda row: (
                row.__setitem__("event", "task_started"),
                row.__setitem__(
                    "payload",
                    json.loads(
                        _ledger_bytes(
                            [
                                (
                                    "task_started",
                                    _event_payloads()["task_started"],
                                )
                            ]
                        ).splitlines()[1]
                    )["payload"],
                ),
            ),
        ),
    )

    for reason, mutation in mutations:
        assert _validate(_replace_row(base, 1, mutation))["reason"] == reason


def test_validator_rejects_boolean_header_sequence_as_sequence_invalid() -> None:
    corrupted = _replace_row(
        _ledger_header_bytes(),
        0,
        lambda row: row.__setitem__("seq", False),
    )

    assert _validate(corrupted)["reason"] == "sequence_invalid"


def test_validator_distinguishes_opaque_order_and_equality_mismatch() -> None:
    payloads = _event_payloads()
    base = _ledger_bytes(
        [("task_start_requested", payloads["task_start_requested"])]
    )
    header = json.loads(base.splitlines()[0])
    ordered = _replace_row(
        base,
        1,
        lambda row: row["payload"]["turn"]["canonical_slice"].__setitem__(
            "sha256",
            header["materialization_slice"]["sha256"],
        ),
    )
    unequal = _replace_row(
        base,
        1,
        lambda row: row["payload"]["turn"]["canonical_slice"].__setitem__(
            "sha256",
            _digest("7"),
        ),
    )

    assert _validate(ordered)["reason"] == "opaque_digest_order_mismatch"
    assert _validate(unequal)["reason"] == (
        "opaque_digest_equality_mismatch"
    )


def test_validator_opaque_order_is_scoped_to_one_semantic_family() -> None:
    payloads = _event_payloads()
    base = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            ("turn_offer_requested", payloads["turn_offer_requested"]),
            ("turn_offered", payloads["turn_offered"]),
        ]
    )
    header = json.loads(base.splitlines()[0])
    corrupted = _replace_row(
        base,
        4,
        lambda row: row["payload"]["turn"]["protocol_frame"].__setitem__(
            "sha256",
            header["task_slice"]["sha256"],
        ),
    )

    assert _validate(corrupted)["reason"] == (
        "opaque_digest_equality_mismatch"
    )


def test_validator_scalar_relation_precedes_opaque_digest_relation() -> None:
    payloads = _event_payloads()
    events = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offered", payloads["turn_offered"]),
        ("submit_received", payloads["submit_received"]),
        ("validation_rejected", payloads["validation_rejected"]),
        ("candidate_reset", payloads["candidate_reset"]),
        ("retry_queued", payloads["retry_queued"]),
    ]
    corrupted = _replace_row(
        _ledger_bytes(events),
        8,
        lambda row: row["payload"]["turn"]["canonical_slice"].__setitem__(
            "sha256",
            _digest("7"),
        ),
    )
    corrupted = _replace_row(
        corrupted,
        0,
        lambda row: row.__setitem__("materialization_attempts", 1),
    )
    corrupted = _replace_row(
        corrupted,
        5,
        lambda row: (
            row["payload"].__setitem__("configured_total", 1),
            row["payload"].__setitem__("remaining_before", 1),
        ),
    )

    assert _validate(corrupted)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    ("events", "row_ordinal"),
    (
        (
            [
                (
                    "task_start_requested",
                    _event_payloads()["task_start_requested"],
                )
            ],
            1,
        ),
        (
            [
                (
                    "task_start_requested",
                    _event_payloads()["task_start_requested"],
                ),
                ("task_started", _event_payloads()["task_started"]),
                (
                    "turn_offer_requested",
                    _event_payloads()["turn_offer_requested"],
                ),
            ],
            3,
        ),
    ),
)
def test_validator_binds_turn_slice_bytes_to_header_before_digest(
    events: list[tuple[str, dict[str, object]]],
    row_ordinal: int,
) -> None:
    base = _ledger_bytes(events)
    header = json.loads(base.splitlines()[0])
    other_slice = (
        "materialization_slice"
        if row_ordinal == 1
        else "task_slice"
    )

    def mutate(row: dict[str, Any]) -> None:
        turn = row["payload"]["turn"]
        byte_delta = (
            header[other_slice]["bytes"]
            - turn["canonical_slice"]["bytes"]
        )
        turn["canonical_slice"] = dict(header[other_slice])
        turn["delivered_turn"]["bytes"] += byte_delta

    corrupted = _replace_row(base, row_ordinal, mutate)

    assert _validate(corrupted)["reason"] == "payload_invalid"


def test_validator_binds_initial_and_retry_turn_requests_to_state() -> None:
    payloads = _event_payloads()
    wrong_initial = _ledger_bytes(
        [
            ("task_start_requested", payloads["task_start_requested"]),
            ("task_started", payloads["task_started"]),
            (
                "turn_offer_requested",
                {"turn": _turn("retry_materialization", 2)},
            ),
        ]
    )
    retry_turn = payloads["retry_queued"]["turn"]
    valid_retry_prefix = [
        ("task_start_requested", payloads["task_start_requested"]),
        ("task_started", payloads["task_started"]),
        ("turn_offer_requested", payloads["turn_offer_requested"]),
        ("turn_offered", payloads["turn_offered"]),
        ("submit_received", payloads["submit_received"]),
        ("validation_rejected", payloads["validation_rejected"]),
        ("candidate_reset", payloads["candidate_reset"]),
        ("retry_queued", payloads["retry_queued"]),
    ]
    valid_retry = _ledger_bytes(
        [*valid_retry_prefix, ("turn_offer_requested", {"turn": retry_turn})]
    )
    wrong_retry = _ledger_bytes(
        [
            *valid_retry_prefix,
            (
                "turn_offer_requested",
                {"turn": _turn("retry_materialization", 3)},
            ),
        ]
    )

    assert _validate(wrong_initial)["reason"] == "payload_invalid"
    assert _validate(valid_retry)["reason"] == "nonterminal_prefix"
    assert _validate(wrong_retry)["reason"] == "payload_invalid"


@pytest.mark.parametrize(
    ("events", "row_ordinal", "mutation"),
    (
        (
            [],
            0,
            lambda row: row["attempt"].__setitem__(
                "scope_sha256",
                _digest("7"),
            ),
        ),
        (
            [
                (
                    "task_start_requested",
                    _event_payloads()["task_start_requested"],
                )
            ],
            1,
            lambda row: row["payload"]["turn"]["submit_keys"].__setitem__(
                "sha256",
                _digest("7"),
            ),
        ),
        (
            [
                (
                    "task_start_requested",
                    _event_payloads()["task_start_requested"],
                ),
                ("task_started", _event_payloads()["task_started"]),
                (
                    "turn_offer_requested",
                    _event_payloads()["turn_offer_requested"],
                ),
                ("turn_offered", _event_payloads()["turn_offered"]),
                (
                    "submit_received",
                    _event_payloads()["submit_received"],
                ),
                (
                    "candidate_frozen",
                    _event_payloads()["candidate_frozen"],
                ),
            ],
            6,
            lambda row: row["payload"]["candidate_manifest"].__setitem__(
                "manifest_sha256",
                _digest("7"),
            ),
        ),
    ),
)
def test_validator_reports_recomputable_digest_mismatch(
    events: list[tuple[str, dict[str, object]]],
    row_ordinal: int,
    mutation: Any,
) -> None:
    corrupted = _replace_row(
        _ledger_bytes(events),
        row_ordinal,
        mutation,
    )

    assert _validate(corrupted)["reason"] == "digest_mismatch"


def test_validator_opaque_mismatch_precedes_recomputable_mismatch() -> None:
    payloads = _event_payloads()
    base = _ledger_bytes(
        [("task_start_requested", payloads["task_start_requested"])]
    )
    corrupted = _replace_row(
        base,
        1,
        lambda row: (
            row["payload"]["turn"]["canonical_slice"].__setitem__(
                "sha256",
                _digest("7"),
            ),
            row["payload"]["turn"]["submit_keys"].__setitem__(
                "sha256",
                _digest("8"),
            ),
        ),
    )

    assert _validate(corrupted)["reason"] == (
        "opaque_digest_equality_mismatch"
    )


def test_validator_is_bytes_only_and_exposes_no_runtime_authority() -> None:
    import inspect
    import orchestrator.workflow.provider_phased_delivery.ledger as ledger

    signature = inspect.signature(ledger.validate_ledger_bytes)

    assert tuple(signature.parameters) == ("ledger_bytes",)
    assert not {
        "publish",
        "resume",
        "retry",
        "settle",
        "reconstruct_result",
    }.intersection(
        name for name in vars(ledger) if not name.startswith("_")
    )
