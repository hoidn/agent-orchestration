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
    InteractiveTerminalStartOutcome,
    NoBackendAllocationProof,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
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


def _diagnostic() -> PhasedDeliveryDiagnostic:
    reason = "output_validation_failed"
    definition = diagnostic_definition(reason)
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type=definition.value_type,
            canonical_value="missing_output_file",
            summary=reason,
        ),
        primary_source=DiagnosticSource(
            kind="runtime_attempt",
            owner="q2_output_contract",
            path=None,
            span=None,
        ),
        related_sources=(
            DiagnosticSource(
                kind="runtime_attempt",
                owner="runtime_step",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="candidate_set",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="phase_lifecycle",
                path=None,
                span=None,
            ),
        ),
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


def _no_allocation_start_failure() -> InteractiveTerminalStartOutcome:
    return InteractiveTerminalStartOutcome(
        status="failed",
        error_code="tmux_unavailable",
        backend_allocation="none",
        cleanup_status="not_required",
        provider_zero_survivor_proven=True,
        proof=NoBackendAllocationProof(
            disposition="no_backend_allocation",
            backend_resource_allocated=False,
            proof_complete=True,
        ),
    )


def _event_payloads() -> dict[str, dict[str, object]]:
    diagnostic = _diagnostic()
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
            "diagnostic": diagnostic,
            "start_failure_outcome": _no_allocation_start_failure(),
        },
        "turn_offer_requested": {"turn": materialization},
        "turn_offered": {
            "turn": materialization,
            "receipt": _receipt("offered"),
        },
        "turn_offer_failed": {
            "turn": materialization,
            "diagnostic": diagnostic,
        },
        "submit_received": {
            "client_request_id_sha256": _digest("4"),
            "submission_ordinal": 1,
            "configured_total": 2,
            "remaining_before": 2,
        },
        "validation_rejected": {
            "submission_ordinal": 1,
            "diagnostics": (diagnostic,),
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
            "diagnostic": diagnostic,
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
            "diagnostic": diagnostic,
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
            "diagnostic": diagnostic,
        },
        "publication_started": {"submission_ordinal": 1},
        "publication_succeeded": {
            "submission_ordinal": 1,
            "commit_status": "authoritative_state_committed",
        },
        "publication_failed": {
            "submission_ordinal": 1,
            "diagnostic": diagnostic,
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
            "diagnostic": diagnostic,
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
