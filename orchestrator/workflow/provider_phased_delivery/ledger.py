"""Physical encoding and offline validation for one provider-attempt ledger."""

from __future__ import annotations

from datetime import datetime
import json
import os
from pathlib import Path
import re
import threading
from typing import Any, Mapping

from orchestrator.providers.interactive_terminal import (
    InteractiveTerminalStartOutcome,
    NoBackendAllocationProof,
    PhasedFailedCleanupEvidence,
)
from orchestrator.workflow.prompt_dependency_evidence import (
    _attempt,
    _validate_attempt,
)
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_attempts import ProviderAttemptScope

from .diagnostics import (
    DiagnosticSource,
    DiagnosticSpan,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    diagnostic_definition,
)
from .models import (
    AdapterReceiptProjection,
    ByteDigestProjection,
    CandidateDigestManifest,
    CandidateDigestRow,
    CountDigestProjection,
    TurnProjection,
    validated_start_outcome,
)


LEDGER_SCHEMA_VERSION = "provider_prompt_phase_ledger.v1"
_U63_MAX = 2**63 - 1
_TERMINAL_EVENTS = frozenset(
    {"publication_succeeded", "terminal_failed"}
)
_TIMESTAMP_RE = re.compile(
    r"(?:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z|"
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z)"
)
_EVENT_PAYLOAD_KEYS = {
    "task_start_requested": frozenset({"turn"}),
    "task_started": frozenset({"turn", "receipt"}),
    "task_start_failed": frozenset(
        {"turn", "diagnostic", "start_failure_outcome"}
    ),
    "turn_offer_requested": frozenset({"turn"}),
    "turn_offered": frozenset({"turn", "receipt"}),
    "turn_offer_failed": frozenset({"turn", "diagnostic"}),
    "submit_received": frozenset(
        {
            "client_request_id_sha256",
            "submission_ordinal",
            "configured_total",
            "remaining_before",
        }
    ),
    "validation_rejected": frozenset(
        {"submission_ordinal", "diagnostics", "candidate_manifest"}
    ),
    "candidate_reset": frozenset(
        {"submission_ordinal", "postcondition"}
    ),
    "retry_queued": frozenset(
        {
            "rejected_submission_ordinal",
            "next_submission_ordinal",
            "turn",
        }
    ),
    "candidate_frozen": frozenset(
        {"submission_ordinal", "candidate_manifest"}
    ),
    "close_offer_requested": frozenset(
        {"submission_ordinal", "close_projection"}
    ),
    "close_offered": frozenset(
        {"submission_ordinal", "close_projection", "receipt"}
    ),
    "close_offer_failed": frozenset(
        {"submission_ordinal", "close_projection", "diagnostic"}
    ),
    "ingress_shutdown_started": frozenset({"terminal_response"}),
    "ingress_shutdown_finished": frozenset(
        {
            "terminal_response",
            "queued_requests_rejected",
            "active_requests_drained",
            "listener_closed",
            "workers_joined",
            "endpoint_zero_survivor_proven",
        }
    ),
    "ingress_shutdown_failed": frozenset(
        {
            "terminal_response",
            "queued_requests_rejected",
            "active_requests_drained",
            "listener_closed",
            "workers_joined",
            "endpoint_zero_survivor_proven",
            "diagnostic",
        }
    ),
    "join_started": frozenset(
        {"submission_ordinal", "remaining_budget_ms"}
    ),
    "join_succeeded": frozenset(
        {"submission_ordinal", "natural_shutdown_proof"}
    ),
    "join_failed": frozenset({"submission_ordinal", "diagnostic"}),
    "publication_started": frozenset({"submission_ordinal"}),
    "publication_succeeded": frozenset(
        {"submission_ordinal", "commit_status"}
    ),
    "publication_failed": frozenset(
        {"submission_ordinal", "diagnostic"}
    ),
    "cleanup_finished": frozenset(
        {
            "cleanup_status",
            "abort_calls",
            "provider_cleanup_proof",
            "cleanup_diagnostic",
            "provider_zero_survivor_proven",
        }
    ),
    "terminal_failed": frozenset(
        {
            "diagnostic",
            "cleanup_status",
            "cleanup_diagnostic",
            "endpoint_shutdown_status",
            "natural_shutdown_proof",
        }
    ),
}


def _closed(
    value: object,
    keys: frozenset[str] | set[str],
    *,
    field: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError(f"{field} payload must have exact keys")
    return value


def _u63(value: object, *, field: str, positive: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (1 if positive else 0)
        or value > _U63_MAX
    ):
        domain = "positive_u63" if positive else "u63"
        raise TypeError(f"{field} must be a non-Boolean {domain}")
    return value


def _digest(value: object, *, field: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 71
        or not value.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in value[7:])
    ):
        raise ValueError(f"{field} must be a canonical SHA-256 digest")
    return value


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _TIMESTAMP_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical UTC timestamp")
    format_string = (
        "%Y-%m-%dT%H:%M:%S.%fZ" if "." in value else "%Y-%m-%dT%H:%M:%SZ"
    )
    try:
        datetime.strptime(value, format_string)
    except ValueError as exc:
        raise ValueError(f"{field} must be a valid UTC timestamp") from exc
    return value


def _canonical_jsonl(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            dict(value),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
        + b"\n"
    )


def _byte_projection(value: object, *, field: str) -> dict[str, object]:
    if type(value) is not ByteDigestProjection:
        raise TypeError(f"{field} must be an exact ByteDigestProjection")
    checked = ByteDigestProjection(bytes=value.bytes, sha256=value.sha256)
    return {"bytes": checked.bytes, "sha256": checked.sha256}


def _count_projection(value: object, *, field: str) -> dict[str, object]:
    if type(value) is not CountDigestProjection:
        raise TypeError(f"{field} must be an exact CountDigestProjection")
    checked = CountDigestProjection(count=value.count, sha256=value.sha256)
    return {"count": checked.count, "sha256": checked.sha256}


def _turn(value: object) -> dict[str, object]:
    if type(value) is not TurnProjection:
        raise TypeError("turn must be an exact TurnProjection")
    checked = TurnProjection(
        delivery_ordinal=value.delivery_ordinal,
        phase=value.phase,
        submission_ordinal=value.submission_ordinal,
        protocol_frame=value.protocol_frame,
        canonical_slice=value.canonical_slice,
        delivered_turn=value.delivered_turn,
        submit_keys=value.submit_keys,
    )
    if checked.protocol_frame.bytes == 0:
        raise ValueError("turn.protocol_frame bytes must be nonzero")
    if (
        checked.phase != "task"
        and checked.canonical_slice.bytes == 0
    ):
        raise ValueError(
            "materialization turn.canonical_slice bytes must be nonzero"
        )
    return {
        "delivery_ordinal": checked.delivery_ordinal,
        "phase": checked.phase,
        "submission_ordinal": checked.submission_ordinal,
        "protocol_frame": _byte_projection(
            checked.protocol_frame,
            field="turn.protocol_frame",
        ),
        "canonical_slice": _byte_projection(
            checked.canonical_slice,
            field="turn.canonical_slice",
        ),
        "delivered_turn": _byte_projection(
            checked.delivered_turn,
            field="turn.delivered_turn",
        ),
        "submit_keys": _count_projection(
            checked.submit_keys,
            field="turn.submit_keys",
        ),
    }


def _receipt(
    value: object,
    *,
    expected_status: str,
) -> dict[str, object]:
    if type(value) is not AdapterReceiptProjection:
        raise TypeError("receipt must be an exact AdapterReceiptProjection")
    checked = AdapterReceiptProjection(
        status=value.status,
        handle_id_sha256=value.handle_id_sha256,
    )
    if checked.status != expected_status:
        raise ValueError("receipt status does not match its event")
    return {
        "status": checked.status,
        "handle_id_sha256": checked.handle_id_sha256,
    }


def _span(value: DiagnosticSpan) -> dict[str, int]:
    checked = DiagnosticSpan(
        start_line=value.start_line,
        start_column=value.start_column,
        end_line=value.end_line,
        end_column=value.end_column,
    )
    return {
        "start_line": checked.start_line,
        "start_column": checked.start_column,
        "end_line": checked.end_line,
        "end_column": checked.end_column,
    }


def _source(value: DiagnosticSource) -> dict[str, object]:
    checked = DiagnosticSource(
        kind=value.kind,
        owner=value.owner,
        path=value.path,
        span=value.span,
    )
    return {
        "kind": checked.kind,
        "owner": checked.owner,
        "path": checked.path,
        "span": None if checked.span is None else _span(checked.span),
    }


def _diagnostic(value: object) -> dict[str, object]:
    if type(value) is not PhasedDeliveryDiagnostic:
        raise TypeError(
            "diagnostic must be an exact PhasedDeliveryDiagnostic"
        )
    if not isinstance(value.related_sources, tuple):
        raise TypeError("diagnostic related_sources must remain a tuple")
    rejected = RejectedValue(
        type=value.rejected_value.type,
        canonical_value=value.rejected_value.canonical_value,
        summary=value.rejected_value.summary,
    )
    checked = PhasedDeliveryDiagnostic(
        code=value.code,
        reason=value.reason,
        rejected_value=rejected,
        primary_source=DiagnosticSource(
            kind=value.primary_source.kind,
            owner=value.primary_source.owner,
            path=value.primary_source.path,
            span=value.primary_source.span,
        ),
        related_sources=tuple(
            DiagnosticSource(
                kind=source.kind,
                owner=source.owner,
                path=source.path,
                span=source.span,
            )
            for source in value.related_sources
        ),
    )
    return {
        "schema_version": checked.schema_version,
        "code": checked.code,
        "reason": checked.reason,
        "rejected_value": {
            "type": rejected.type,
            "canonical_value": rejected.canonical_value,
            "summary": rejected.summary,
        },
        "primary_source": _source(checked.primary_source),
        "related_sources": [
            _source(source) for source in checked.related_sources
        ],
    }


def _no_allocation_proof(value: NoBackendAllocationProof) -> dict[str, object]:
    checked = NoBackendAllocationProof(
        disposition=value.disposition,
        backend_resource_allocated=value.backend_resource_allocated,
        proof_complete=value.proof_complete,
    )
    return {
        "disposition": checked.disposition,
        "backend_resource_allocated": checked.backend_resource_allocated,
        "proof_complete": checked.proof_complete,
    }


def _failed_cleanup_proof(
    value: PhasedFailedCleanupEvidence,
) -> dict[str, object]:
    checked = PhasedFailedCleanupEvidence(
        disposition=value.disposition,
        pane_absent=value.pane_absent,
        server_absent=value.server_absent,
        cleanup_complete=value.cleanup_complete,
        error_code=value.error_code,
    )
    return {
        "disposition": checked.disposition,
        "pane_absent": checked.pane_absent,
        "server_absent": checked.server_absent,
        "cleanup_complete": checked.cleanup_complete,
        "error_code": checked.error_code,
    }


def _provider_cleanup_proof(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if type(value) is NoBackendAllocationProof:
        return _no_allocation_proof(value)
    if type(value) is PhasedFailedCleanupEvidence:
        return _failed_cleanup_proof(value)
    raise TypeError("provider_cleanup_proof has an invalid proof type")


def _start_failure(value: object) -> dict[str, object]:
    if type(value) is not InteractiveTerminalStartOutcome:
        raise TypeError(
            "start_failure_outcome must be an exact start outcome"
        )
    checked = validated_start_outcome(value)
    if checked.status != "failed":
        raise ValueError("start_failure_outcome must be failed")
    assert checked.error_code is not None
    assert checked.backend_allocation is not None
    assert checked.cleanup_status is not None
    assert checked.provider_zero_survivor_proven is not None
    assert checked.proof is not None
    return {
        "status": "failed",
        "error_code": checked.error_code,
        "backend_allocation": checked.backend_allocation,
        "cleanup_status": checked.cleanup_status,
        "provider_zero_survivor_proven": (
            checked.provider_zero_survivor_proven
        ),
        "proof": _provider_cleanup_proof(checked.proof),
    }


def _candidate_manifest(value: object) -> dict[str, object]:
    if type(value) is not CandidateDigestManifest:
        raise TypeError(
            "candidate_manifest must be an embedded exact manifest"
        )
    if (
        not isinstance(value.rows, tuple)
        or any(type(row) is not CandidateDigestRow for row in value.rows)
    ):
        raise TypeError("candidate_manifest rows must remain an exact tuple")
    rows = tuple(
        CandidateDigestRow(
            contract_ordinal=row.contract_ordinal,
            role=row.role,
            logical_name=row.logical_name,
            workspace_relative_path=row.workspace_relative_path,
            presence=row.presence,
            byte_length=row.byte_length,
            sha256=row.sha256,
        )
        for row in value.rows
    )
    checked = CandidateDigestManifest(
        submission_ordinal=value.submission_ordinal,
        disposition=value.disposition,
        rows=rows,
        manifest_sha256=value.manifest_sha256,
    )
    return {
        "schema_version": checked.schema_version,
        "submission_ordinal": checked.submission_ordinal,
        "disposition": checked.disposition,
        "rows": [row.to_dict() for row in checked.rows],
        "manifest_sha256": checked.manifest_sha256,
    }


def _positive_submission(value: object, *, field: str) -> int:
    return _u63(value, field=field, positive=True)


def _close_projection(value: object) -> dict[str, object]:
    node = _closed(
        value,
        {"close_text", "submit_keys"},
        field="close_projection",
    )
    return {
        "close_text": _byte_projection(
            node["close_text"],
            field="close_projection.close_text",
        ),
        "submit_keys": _count_projection(
            node["submit_keys"],
            field="close_projection.submit_keys",
        ),
    }


def _terminal_response(value: object) -> dict[str, str]:
    node = _closed(
        value,
        {"status", "code", "reason"},
        field="terminal_response",
    )
    expected = {
        "status": "failed",
        "code": "provider_phased_submit_protocol_invalid",
        "reason": "submit_lifecycle_invalid",
    }
    if dict(node) != expected:
        raise ValueError("terminal_response payload is invalid")
    return expected


def _natural_shutdown_proof(
    value: object,
) -> dict[str, object] | None:
    if value is None:
        return None
    node = _closed(
        value,
        {
            "disposition",
            "return_code",
            "pane_absent",
            "server_absent",
            "proof_complete",
        },
        field="natural_shutdown_proof",
    )
    expected = {
        "disposition": "natural_exit",
        "return_code": 0,
        "pane_absent": True,
        "server_absent": True,
        "proof_complete": True,
    }
    if (
        dict(node) != expected
        or isinstance(node["return_code"], bool)
        or node["pane_absent"] is not True
        or node["server_absent"] is not True
        or node["proof_complete"] is not True
    ):
        raise ValueError("natural_shutdown_proof payload is invalid")
    return expected


def _project_payload(
    event: str,
    value: object,
) -> dict[str, object]:
    keys = _EVENT_PAYLOAD_KEYS.get(event)
    if keys is None:
        raise ValueError("event is unknown")
    node = _closed(value, keys, field=event)

    if event.startswith("task_"):
        turn = _turn(node["turn"])
        projected: dict[str, object] = {"turn": turn}
        if turn["phase"] != "task":
            raise ValueError("task event turn phase is invalid")
        if event == "task_started":
            projected["receipt"] = _receipt(
                node["receipt"],
                expected_status="started",
            )
        elif event == "task_start_failed":
            projected["diagnostic"] = _diagnostic(node["diagnostic"])
            projected["start_failure_outcome"] = _start_failure(
                node["start_failure_outcome"]
            )
        return projected

    if event in {
        "turn_offer_requested",
        "turn_offered",
        "turn_offer_failed",
    }:
        turn = _turn(node["turn"])
        projected = {"turn": turn}
        if turn["phase"] == "task":
            raise ValueError("turn offer requires materialization")
        if event == "turn_offered":
            projected["receipt"] = _receipt(
                node["receipt"],
                expected_status="offered",
            )
        elif event == "turn_offer_failed":
            projected["diagnostic"] = _diagnostic(node["diagnostic"])
        return projected

    if event == "submit_received":
        submission = _positive_submission(
            node["submission_ordinal"],
            field="submission_ordinal",
        )
        configured = _positive_submission(
            node["configured_total"],
            field="configured_total",
        )
        remaining = _u63(
            node["remaining_before"],
            field="remaining_before",
        )
        if (
            configured not in {1, 2, 3}
            or submission > configured
            or remaining != configured - submission + 1
        ):
            raise ValueError("submit_received ordinal/count payload is invalid")
        return {
            "client_request_id_sha256": _digest(
                node["client_request_id_sha256"],
                field="client_request_id_sha256",
            ),
            "submission_ordinal": submission,
            "configured_total": configured,
            "remaining_before": remaining,
        }

    if event in {"validation_rejected", "candidate_frozen"}:
        submission = _positive_submission(
            node["submission_ordinal"],
            field="submission_ordinal",
        )
        manifest = _candidate_manifest(node["candidate_manifest"])
        expected_disposition = (
            "rejected" if event == "validation_rejected" else "frozen"
        )
        if (
            manifest["submission_ordinal"] != submission
            or manifest["disposition"] != expected_disposition
        ):
            raise ValueError("candidate_manifest contradicts its event")
        projected: dict[str, object] = {
            "submission_ordinal": submission,
        }
        if event == "validation_rejected":
            diagnostics = node["diagnostics"]
            if (
                not isinstance(diagnostics, tuple)
                or not diagnostics
                or any(
                    type(item) is not PhasedDeliveryDiagnostic
                    for item in diagnostics
                )
            ):
                raise TypeError(
                    "diagnostics must be a non-empty exact tuple"
                )
            projected["diagnostics"] = [
                _diagnostic(item) for item in diagnostics
            ]
        projected["candidate_manifest"] = manifest
        return projected

    if event == "candidate_reset":
        submission = _positive_submission(
            node["submission_ordinal"],
            field="submission_ordinal",
        )
        if node["postcondition"] != "all_bound_paths_absent":
            raise ValueError("candidate_reset postcondition is invalid")
        return {
            "submission_ordinal": submission,
            "postcondition": node["postcondition"],
        }

    if event == "retry_queued":
        rejected = _positive_submission(
            node["rejected_submission_ordinal"],
            field="rejected_submission_ordinal",
        )
        following = _positive_submission(
            node["next_submission_ordinal"],
            field="next_submission_ordinal",
        )
        turn = _turn(node["turn"])
        if (
            following != rejected + 1
            or following > 3
            or turn["phase"] != "retry_materialization"
            or turn["submission_ordinal"] != following
        ):
            raise ValueError("retry_queued ordinal payload is invalid")
        return {
            "rejected_submission_ordinal": rejected,
            "next_submission_ordinal": following,
            "turn": turn,
        }

    if event in {
        "close_offer_requested",
        "close_offered",
        "close_offer_failed",
    }:
        projected = {
            "submission_ordinal": _positive_submission(
                node["submission_ordinal"],
                field="submission_ordinal",
            ),
            "close_projection": _close_projection(
                node["close_projection"]
            ),
        }
        if event == "close_offered":
            projected["receipt"] = _receipt(
                node["receipt"],
                expected_status="close_offered",
            )
        elif event == "close_offer_failed":
            projected["diagnostic"] = _diagnostic(node["diagnostic"])
        return projected

    if event.startswith("ingress_shutdown_"):
        projected = {
            "terminal_response": _terminal_response(
                node["terminal_response"]
            )
        }
        if event != "ingress_shutdown_started":
            for field in (
                "queued_requests_rejected",
                "active_requests_drained",
                "workers_joined",
            ):
                projected[field] = _u63(node[field], field=field)
            if type(node["listener_closed"]) is not bool:
                raise TypeError("listener_closed must be Boolean")
            projected["listener_closed"] = node["listener_closed"]
            expected_proof = event == "ingress_shutdown_finished"
            if node["endpoint_zero_survivor_proven"] is not expected_proof:
                raise ValueError(
                    "endpoint_zero_survivor_proven contradicts event"
                )
            if expected_proof and node["listener_closed"] is not True:
                raise ValueError(
                    "finished ingress requires a closed listener"
                )
            projected["endpoint_zero_survivor_proven"] = expected_proof
            if event == "ingress_shutdown_failed":
                projected["diagnostic"] = _diagnostic(
                    node["diagnostic"]
                )
        return projected

    if event in {
        "join_started",
        "join_succeeded",
        "join_failed",
        "publication_started",
        "publication_succeeded",
        "publication_failed",
    }:
        projected = {
            "submission_ordinal": _positive_submission(
                node["submission_ordinal"],
                field="submission_ordinal",
            )
        }
        if event == "join_started":
            projected["remaining_budget_ms"] = _u63(
                node["remaining_budget_ms"],
                field="remaining_budget_ms",
            )
        elif event == "join_succeeded":
            proof = _natural_shutdown_proof(
                node["natural_shutdown_proof"]
            )
            if proof is None:
                raise ValueError("join_succeeded requires natural proof")
            projected["natural_shutdown_proof"] = proof
        elif event in {"join_failed", "publication_failed"}:
            projected["diagnostic"] = _diagnostic(node["diagnostic"])
        elif event == "publication_succeeded":
            if node["commit_status"] != "authoritative_state_committed":
                raise ValueError("publication commit_status is invalid")
            projected["commit_status"] = node["commit_status"]
        return projected

    if event == "cleanup_finished":
        status = node["cleanup_status"]
        if status not in {"not_required", "complete", "incomplete"}:
            raise ValueError("cleanup_finished status is invalid")
        abort_calls = _u63(node["abort_calls"], field="abort_calls")
        if abort_calls not in {0, 1}:
            raise ValueError("abort_calls must be zero or one")
        proof = node["provider_cleanup_proof"]
        cleanup_diagnostic = node["cleanup_diagnostic"]
        survivor = node["provider_zero_survivor_proven"]
        if type(survivor) is not bool:
            raise TypeError("provider_zero_survivor_proven must be Boolean")
        if status == "not_required":
            if (
                type(proof) is not NoBackendAllocationProof
                or cleanup_diagnostic is not None
                or abort_calls != 0
                or survivor is not True
            ):
                raise ValueError("not_required cleanup union is invalid")
        elif status == "complete":
            if (
                type(proof) is not PhasedFailedCleanupEvidence
                or proof.cleanup_complete is not True
                or cleanup_diagnostic is not None
                or survivor is not True
            ):
                raise ValueError("complete cleanup union is invalid")
        elif (
            cleanup_diagnostic is None
            or type(cleanup_diagnostic) is not PhasedDeliveryDiagnostic
            or survivor is not False
            or (
                proof is not None
                and (
                    type(proof) is not PhasedFailedCleanupEvidence
                    or proof.cleanup_complete is not False
                )
            )
        ):
            raise ValueError("incomplete cleanup union is invalid")
        return {
            "cleanup_status": status,
            "abort_calls": abort_calls,
            "provider_cleanup_proof": _provider_cleanup_proof(proof),
            "cleanup_diagnostic": (
                None
                if cleanup_diagnostic is None
                else _diagnostic(cleanup_diagnostic)
            ),
            "provider_zero_survivor_proven": survivor,
        }

    if event == "terminal_failed":
        status = node["cleanup_status"]
        if status not in {
            "not_required",
            "complete",
            "incomplete",
            "not_permitted",
        }:
            raise ValueError("terminal_failed cleanup_status is invalid")
        cleanup_diagnostic = node["cleanup_diagnostic"]
        if status == "incomplete":
            if type(cleanup_diagnostic) is not PhasedDeliveryDiagnostic:
                raise ValueError(
                    "incomplete terminal cleanup requires diagnostic"
                )
        elif cleanup_diagnostic is not None:
            raise ValueError(
                "terminal cleanup diagnostic nullability is invalid"
            )
        endpoint_status = node["endpoint_shutdown_status"]
        if endpoint_status not in {
            "not_allocated",
            "complete",
            "incomplete",
        }:
            raise ValueError("endpoint_shutdown_status is invalid")
        natural = _natural_shutdown_proof(
            node["natural_shutdown_proof"]
        )
        if (natural is not None) != (status == "not_permitted"):
            raise ValueError(
                "terminal natural-proof cleanup union is invalid"
            )
        if (
            status == "not_required"
            and endpoint_status != "not_allocated"
        ) or (
            status == "not_permitted"
            and endpoint_status != "complete"
        ):
            raise ValueError(
                "terminal cleanup and endpoint statuses are inconsistent"
            )
        return {
            "diagnostic": _diagnostic(node["diagnostic"]),
            "cleanup_status": status,
            "cleanup_diagnostic": (
                None
                if cleanup_diagnostic is None
                else _diagnostic(cleanup_diagnostic)
            ),
            "endpoint_shutdown_status": endpoint_status,
            "natural_shutdown_proof": natural,
        }

    raise RuntimeError("unhandled provider phase ledger event")


def ledger_relative_path(
    scope: ProviderAttemptScope,
    ordinal: int,
) -> Path:
    """Derive the unique sidecar path from the existing attempt identity."""

    if type(scope) is not ProviderAttemptScope:
        raise TypeError("scope must be an exact ProviderAttemptScope")
    ordinal = _u63(ordinal, field="ordinal", positive=True)
    attempt = _attempt(scope, ordinal)
    return Path(
        "workflow_lisp",
        "prompt_dependencies",
        attempt["step_key"],
        attempt["visit_key"],
        f"attempt-{ordinal:06d}-provider-prompt-phases.jsonl",
    )


def encode_header(
    *,
    scope: ProviderAttemptScope,
    ordinal: int,
    cut: CanonicalPromptCut,
    materialization_attempts: int,
    created_at: str,
) -> bytes:
    """Encode the exact sequence-zero ledger header."""

    if type(scope) is not ProviderAttemptScope:
        raise TypeError("scope must be an exact ProviderAttemptScope")
    ordinal = _u63(ordinal, field="ordinal", positive=True)
    if type(cut) is not CanonicalPromptCut:
        raise TypeError("cut must be an exact CanonicalPromptCut")
    checked_cut = CanonicalPromptCut(
        task_slice=cut.task_slice,
        materialization_slice=cut.materialization_slice,
        canonical_composed=cut.canonical_composed,
        projection=cut.projection,
    )
    if checked_cut.projection.materialization_slice.bytes == 0:
        raise ValueError("materialization_slice bytes must be nonzero")
    attempts = _u63(
        materialization_attempts,
        field="materialization_attempts",
        positive=True,
    )
    if attempts not in {1, 2, 3}:
        raise ValueError("materialization_attempts must be in 1..3")
    projection = checked_cut.projection
    return _canonical_jsonl(
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "record_kind": "header",
            "seq": 0,
            "attempt": _attempt(scope, ordinal),
            "target_dsl": "2.23",
            "delivery": "phased",
            "materialization_attempts": attempts,
            "prompt_attempt_identity_version": (
                "workflow_prompt_attempt_identity.v2"
            ),
            "protocol_schema_version": (
                "provider_phased_protocol_frame.v1"
            ),
            "canonical_composed": _byte_projection(
                projection.canonical_composed,
                field="canonical_composed",
            ),
            "task_slice": _byte_projection(
                projection.task_slice,
                field="task_slice",
            ),
            "materialization_slice": _byte_projection(
                projection.materialization_slice,
                field="materialization_slice",
            ),
            "created_at": _timestamp(created_at, field="created_at"),
        }
    )


def encode_event(
    *,
    seq: int,
    event: str,
    attempt: Mapping[str, Any],
    observed_at: str,
    payload: Mapping[str, Any],
) -> bytes:
    """Encode one individually closed event row without history inference."""

    seq = _u63(seq, field="seq", positive=True)
    if not isinstance(event, str) or event not in _EVENT_PAYLOAD_KEYS:
        raise ValueError("event is unknown")
    if not isinstance(attempt, Mapping):
        raise TypeError("attempt must be a mapping")
    _u63(attempt.get("ordinal"), field="attempt.ordinal", positive=True)
    _validate_attempt(attempt)
    projected_payload = _project_payload(event, payload)
    return _canonical_jsonl(
        {
            "schema_version": LEDGER_SCHEMA_VERSION,
            "record_kind": "event",
            "seq": seq,
            "event": event,
            "attempt": dict(attempt),
            "observed_at": _timestamp(
                observed_at,
                field="observed_at",
            ),
            "payload": projected_payload,
        }
    )


_VALIDATION_SCHEMA_VERSION = "provider_prompt_phase_ledger_validation.v1"
_HEADER_KEYS = frozenset(
    {
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
)
_EVENT_KEYS = frozenset(
    {
        "schema_version",
        "record_kind",
        "seq",
        "event",
        "attempt",
        "observed_at",
        "payload",
    }
)
_EMPTY_SUBMIT_KEYS_SHA256 = (
    "sha256:"
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
_START_TIMEOUT_ERROR = "start_timeout"
_START_CLEANUP_INCOMPLETE_ERROR = (
    "interactive_terminal_start_cleanup_incomplete"
)
_EVENT_DIAGNOSTIC_REASONS = {
    "task_start_failed": frozenset(
        {
            "adapter_start_failed",
            "deadline_exhausted_before_start",
            "deadline_exhausted_during_start",
        }
    ),
    "close_offer_failed": frozenset(
        {
            "close_offer_failed",
            "deadline_exhausted_before_close_offer",
            "deadline_exhausted_during_close_offer",
        }
    ),
    "ingress_shutdown_failed": frozenset(
        {
            "ingress_shutdown_failed",
            "deadline_exhausted_before_ingress_shutdown",
            "deadline_exhausted_during_ingress_shutdown",
        }
    ),
    "join_failed": frozenset(
        {
            "natural_join_failed",
            "deadline_exhausted_before_join",
            "deadline_exhausted_during_join",
        }
    ),
    "publication_failed": frozenset(
        {
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
        }
    ),
}
_INITIAL_OFFER_DIAGNOSTIC_REASONS = frozenset(
    {
        "initial_offer_failed",
        "deadline_exhausted_before_initial_offer",
        "deadline_exhausted_during_initial_offer",
    }
)
_RETRY_OFFER_DIAGNOSTIC_REASONS = frozenset(
    {
        "retry_offer_failed",
        "deadline_exhausted_before_retry_offer",
        "deadline_exhausted_during_retry_offer",
    }
)
_VALIDATION_DIAGNOSTIC_SEQUENCES = frozenset(
    {
        ("output_validation_failed",),
        ("structured_result_validation_failed",),
        (
            "output_validation_failed",
            "structured_result_validation_failed",
        ),
    }
)


class _DuplicateJsonKey(ValueError):
    pass


class _OversizedJsonInteger:
    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text


def _object_without_duplicate_keys(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON constant: {value}")


def _parse_json_integer(value: str) -> int | _OversizedJsonInteger:
    digits = value[1:] if value.startswith("-") else value
    if len(digits) <= 19:
        return int(value)
    return _OversizedJsonInteger(value)


def _canonical_decoded_json(value: object) -> str:
    if type(value) is _OversizedJsonInteger:
        return value.text
    if isinstance(value, Mapping):
        return (
            "{"
            + ",".join(
                json.dumps(
                    key,
                    ensure_ascii=True,
                    allow_nan=False,
                )
                + ":"
                + _canonical_decoded_json(value[key])
                for key in sorted(value)
            )
            + "}"
        )
    if isinstance(value, list):
        return (
            "["
            + ",".join(_canonical_decoded_json(item) for item in value)
            + "]"
        )
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _canonical_decoded_jsonl(value: object) -> bytes:
    return (_canonical_decoded_json(value) + "\n").encode("ascii")


def _validation_result(
    *,
    status: str,
    reason: str,
    row_count: int,
    last_contiguous_seq: int | None,
    terminal_event: str | None,
) -> dict[str, object]:
    return {
        "schema_version": _VALIDATION_SCHEMA_VERSION,
        "status": status,
        "reason": reason,
        "row_count": row_count,
        "last_contiguous_seq": last_contiguous_seq,
        "terminal_event": terminal_event,
    }


def _decoded_byte_projection(
    value: object,
    *,
    field: str,
) -> ByteDigestProjection:
    node = _closed(value, {"bytes", "sha256"}, field=field)
    return ByteDigestProjection(
        bytes=_u63(node["bytes"], field=f"{field}.bytes"),
        sha256=_digest(node["sha256"], field=f"{field}.sha256"),
    )


def _decoded_count_projection(
    value: object,
    *,
    field: str,
) -> CountDigestProjection:
    node = _closed(value, {"count", "sha256"}, field=field)
    return CountDigestProjection(
        count=_u63(node["count"], field=f"{field}.count"),
        sha256=_digest(node["sha256"], field=f"{field}.sha256"),
    )


def _decoded_turn(
    value: object,
    *,
    normalize_task_seal: bool,
) -> tuple[TurnProjection, str | None]:
    node = _closed(
        value,
        {
            "delivery_ordinal",
            "phase",
            "submission_ordinal",
            "protocol_frame",
            "canonical_slice",
            "delivered_turn",
            "submit_keys",
        },
        field="turn",
    )
    submit_keys = _decoded_count_projection(
        node["submit_keys"],
        field="turn.submit_keys",
    )
    recorded_task_seal: str | None = None
    if node["phase"] == "task" and normalize_task_seal:
        recorded_task_seal = submit_keys.sha256
        submit_keys = CountDigestProjection(
            count=submit_keys.count,
            sha256=_EMPTY_SUBMIT_KEYS_SHA256,
        )
    return (
        TurnProjection(
            delivery_ordinal=_u63(
                node["delivery_ordinal"],
                field="turn.delivery_ordinal",
            ),
            phase=node["phase"],
            submission_ordinal=node["submission_ordinal"],
            protocol_frame=_decoded_byte_projection(
                node["protocol_frame"],
                field="turn.protocol_frame",
            ),
            canonical_slice=_decoded_byte_projection(
                node["canonical_slice"],
                field="turn.canonical_slice",
            ),
            delivered_turn=_decoded_byte_projection(
                node["delivered_turn"],
                field="turn.delivered_turn",
            ),
            submit_keys=submit_keys,
        ),
        recorded_task_seal,
    )


def _decoded_receipt(value: object) -> AdapterReceiptProjection:
    node = _closed(
        value,
        {"status", "handle_id_sha256"},
        field="receipt",
    )
    return AdapterReceiptProjection(
        status=node["status"],
        handle_id_sha256=_digest(
            node["handle_id_sha256"],
            field="receipt.handle_id_sha256",
        ),
    )


def _decoded_span(value: object) -> DiagnosticSpan:
    node = _closed(
        value,
        {"start_line", "start_column", "end_line", "end_column"},
        field="diagnostic.span",
    )
    return DiagnosticSpan(
        start_line=node["start_line"],
        start_column=node["start_column"],
        end_line=node["end_line"],
        end_column=node["end_column"],
    )


def _decoded_source(value: object) -> DiagnosticSource:
    node = _closed(
        value,
        {"kind", "owner", "path", "span"},
        field="diagnostic.source",
    )
    return DiagnosticSource(
        kind=node["kind"],
        owner=node["owner"],
        path=node["path"],
        span=None if node["span"] is None else _decoded_span(node["span"]),
    )


def _decoded_diagnostic(value: object) -> PhasedDeliveryDiagnostic:
    node = _closed(
        value,
        {
            "schema_version",
            "code",
            "reason",
            "rejected_value",
            "primary_source",
            "related_sources",
        },
        field="diagnostic",
    )
    if node["schema_version"] != "provider_phased_delivery_diagnostic.v1":
        raise ValueError("diagnostic schema is invalid")
    rejected = _closed(
        node["rejected_value"],
        {"type", "canonical_value", "summary"},
        field="diagnostic.rejected_value",
    )
    related = node["related_sources"]
    if not isinstance(related, list):
        raise TypeError("diagnostic.related_sources must be an array")
    return PhasedDeliveryDiagnostic(
        code=node["code"],
        reason=node["reason"],
        rejected_value=RejectedValue(
            type=rejected["type"],
            canonical_value=rejected["canonical_value"],
            summary=rejected["summary"],
        ),
        primary_source=_decoded_source(node["primary_source"]),
        related_sources=tuple(_decoded_source(item) for item in related),
    )


def _decoded_cleanup_proof(
    value: object,
) -> NoBackendAllocationProof | PhasedFailedCleanupEvidence | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise TypeError("cleanup proof must be an object or null")
    if set(value) == {
        "disposition",
        "backend_resource_allocated",
        "proof_complete",
    }:
        return NoBackendAllocationProof(
            disposition=value["disposition"],
            backend_resource_allocated=value[
                "backend_resource_allocated"
            ],
            proof_complete=value["proof_complete"],
        )
    if set(value) == {
        "disposition",
        "pane_absent",
        "server_absent",
        "cleanup_complete",
        "error_code",
    }:
        return PhasedFailedCleanupEvidence(
            disposition=value["disposition"],
            pane_absent=value["pane_absent"],
            server_absent=value["server_absent"],
            cleanup_complete=value["cleanup_complete"],
            error_code=value["error_code"],
        )
    raise ValueError("cleanup proof shape is invalid")


def _decoded_start_failure(
    value: object,
) -> InteractiveTerminalStartOutcome:
    node = _closed(
        value,
        {
            "status",
            "error_code",
            "backend_allocation",
            "cleanup_status",
            "provider_zero_survivor_proven",
            "proof",
        },
        field="start_failure_outcome",
    )
    return InteractiveTerminalStartOutcome(
        status=node["status"],
        error_code=node["error_code"],
        backend_allocation=node["backend_allocation"],
        cleanup_status=node["cleanup_status"],
        provider_zero_survivor_proven=node[
            "provider_zero_survivor_proven"
        ],
        proof=_decoded_cleanup_proof(node["proof"]),
    )


def _decoded_manifest(
    value: object,
) -> tuple[CandidateDigestManifest, str]:
    node = _closed(
        value,
        {
            "schema_version",
            "submission_ordinal",
            "disposition",
            "rows",
            "manifest_sha256",
        },
        field="candidate_manifest",
    )
    if (
        node["schema_version"]
        != "provider_phased_candidate_digest_manifest.v1"
        or not isinstance(node["rows"], list)
    ):
        raise ValueError("candidate manifest shape is invalid")
    rows: list[CandidateDigestRow] = []
    for raw_row in node["rows"]:
        row = _closed(
            raw_row,
            {
                "contract_ordinal",
                "role",
                "logical_name",
                "workspace_relative_path",
                "presence",
                "byte_length",
                "sha256",
            },
            field="candidate_manifest.row",
        )
        rows.append(
            CandidateDigestRow(
                contract_ordinal=row["contract_ordinal"],
                role=row["role"],
                logical_name=row["logical_name"],
                workspace_relative_path=row["workspace_relative_path"],
                presence=row["presence"],
                byte_length=row["byte_length"],
                sha256=row["sha256"],
            )
        )
    recorded = _digest(
        node["manifest_sha256"],
        field="candidate_manifest.manifest_sha256",
    )
    expected = CandidateDigestManifest.create(
        submission_ordinal=node["submission_ordinal"],
        disposition=node["disposition"],
        rows=tuple(rows),
    )
    return expected, recorded


def _decoded_close_projection(value: object) -> dict[str, object]:
    node = _closed(
        value,
        {"close_text", "submit_keys"},
        field="close_projection",
    )
    return {
        "close_text": _decoded_byte_projection(
            node["close_text"],
            field="close_projection.close_text",
        ),
        "submit_keys": _decoded_count_projection(
            node["submit_keys"],
            field="close_projection.submit_keys",
        ),
    }


def _validate_event_diagnostic_semantics(
    event: str,
    payload: Mapping[str, Any],
) -> None:
    if event == "validation_rejected":
        diagnostics = payload["diagnostics"]
        if not isinstance(diagnostics, list):
            raise TypeError("validation diagnostics must be an array")
        reasons = tuple(item["reason"] for item in diagnostics)
        if reasons not in _VALIDATION_DIAGNOSTIC_SEQUENCES:
            raise ValueError(
                "validation diagnostics do not follow the closed sequence"
            )
        return
    if event == "turn_offer_failed":
        turn = payload["turn"]
        diagnostic = payload["diagnostic"]
        allowed = (
            _INITIAL_OFFER_DIAGNOSTIC_REASONS
            if turn["phase"] == "initial_materialization"
            else _RETRY_OFFER_DIAGNOSTIC_REASONS
        )
        if diagnostic["reason"] not in allowed:
            raise ValueError(
                "turn-offer diagnostic contradicts the turn phase"
            )
        return
    if event == "task_start_failed":
        diagnostic_reason = payload["diagnostic"]["reason"]
        outcome = payload["start_failure_outcome"]
        error_code = outcome["error_code"]
        backend_allocation = outcome["backend_allocation"]
        cleanup_status = outcome["cleanup_status"]

        if cleanup_status == "incomplete":
            proof = outcome["proof"]
            if (
                backend_allocation != "possible_or_allocated"
                or error_code != _START_CLEANUP_INCOMPLETE_ERROR
                or proof["error_code"]
                != _START_CLEANUP_INCOMPLETE_ERROR
                or diagnostic_reason
                not in {
                    "adapter_start_failed",
                    "deadline_exhausted_during_start",
                }
            ):
                raise ValueError(
                    "incomplete start cleanup contradicts the start result"
                )
            return

        if diagnostic_reason == "deadline_exhausted_before_start":
            valid = (
                error_code == _START_TIMEOUT_ERROR
                and backend_allocation == "none"
                and cleanup_status == "not_required"
            )
        elif diagnostic_reason == "deadline_exhausted_during_start":
            valid = (
                error_code == _START_TIMEOUT_ERROR
                and backend_allocation == "possible_or_allocated"
                and cleanup_status == "completed"
            )
        elif diagnostic_reason == "adapter_start_failed":
            valid = (
                error_code
                not in {
                    _START_TIMEOUT_ERROR,
                    _START_CLEANUP_INCOMPLETE_ERROR,
                }
            )
        else:
            valid = False
        if not valid:
            raise ValueError(
                "start diagnostic contradicts the adapter outcome"
            )
        return
    allowed = _EVENT_DIAGNOSTIC_REASONS.get(event)
    if allowed is not None and payload["diagnostic"]["reason"] not in allowed:
        raise ValueError("event diagnostic reason is invalid")


def _decoded_payload(
    event: str,
    value: object,
) -> tuple[dict[str, object], list[tuple[str, str]]]:
    keys = _EVENT_PAYLOAD_KEYS[event]
    node = _closed(value, keys, field=event)
    typed: dict[str, object] = dict(node)
    recomputable: list[tuple[str, str]] = []

    if "turn" in node:
        turn, task_seal = _decoded_turn(
            node["turn"],
            normalize_task_seal=True,
        )
        typed["turn"] = turn
        if task_seal is not None:
            recomputable.append((task_seal, _EMPTY_SUBMIT_KEYS_SHA256))
    if "receipt" in node:
        typed["receipt"] = _decoded_receipt(node["receipt"])
    if "diagnostic" in node:
        typed["diagnostic"] = _decoded_diagnostic(node["diagnostic"])
    if "diagnostics" in node:
        diagnostics = node["diagnostics"]
        if not isinstance(diagnostics, list):
            raise TypeError("diagnostics must be an array")
        decoded_diagnostics = tuple(
            _decoded_diagnostic(item) for item in diagnostics
        )
        precedences = tuple(
            diagnostic_definition(item.reason).precedence
            for item in decoded_diagnostics
        )
        if precedences != tuple(sorted(precedences)):
            raise ValueError("diagnostics are not in fixed precedence order")
        typed["diagnostics"] = decoded_diagnostics
    if "start_failure_outcome" in node:
        typed["start_failure_outcome"] = _decoded_start_failure(
            node["start_failure_outcome"]
        )
    if "candidate_manifest" in node:
        manifest, recorded = _decoded_manifest(node["candidate_manifest"])
        typed["candidate_manifest"] = manifest
        recomputable.append((recorded, manifest.manifest_sha256))
    if "close_projection" in node:
        typed["close_projection"] = _decoded_close_projection(
            node["close_projection"]
        )
    if "provider_cleanup_proof" in node:
        typed["provider_cleanup_proof"] = _decoded_cleanup_proof(
            node["provider_cleanup_proof"]
        )
    if node.get("cleanup_diagnostic") is not None:
        typed["cleanup_diagnostic"] = _decoded_diagnostic(
            node["cleanup_diagnostic"]
        )

    projected = _project_payload(event, typed)
    normalized = dict(node)
    if "turn" in projected and recomputable:
        normalized["turn"] = projected["turn"]
    if "candidate_manifest" in projected:
        normalized["candidate_manifest"] = projected["candidate_manifest"]
    if projected != normalized:
        raise ValueError("payload projection is not canonical")
    _validate_event_diagnostic_semantics(event, projected)
    return projected, recomputable


def _validated_header(
    row: Mapping[str, Any],
) -> tuple[dict[str, Any], list[tuple[str, str]]]:
    if (
        row["schema_version"] != LEDGER_SCHEMA_VERSION
        or row["record_kind"] != "header"
        or row["target_dsl"] != "2.23"
        or row["delivery"] != "phased"
        or row["prompt_attempt_identity_version"]
        != "workflow_prompt_attempt_identity.v2"
        or row["protocol_schema_version"]
        != "provider_phased_protocol_frame.v1"
    ):
        raise ValueError("header literal is invalid")
    attempts = _u63(
        row["materialization_attempts"],
        field="materialization_attempts",
        positive=True,
    )
    if attempts not in {1, 2, 3}:
        raise ValueError("materialization_attempts is invalid")
    _timestamp(row["created_at"], field="created_at")
    composed = _decoded_byte_projection(
        row["canonical_composed"],
        field="canonical_composed",
    )
    task = _decoded_byte_projection(row["task_slice"], field="task_slice")
    materialization = _decoded_byte_projection(
        row["materialization_slice"],
        field="materialization_slice",
    )
    if (
        materialization.bytes == 0
        or composed.bytes != task.bytes + materialization.bytes
    ):
        raise ValueError("header byte projections are invalid")

    attempt_node = row["attempt"]
    if not isinstance(attempt_node, Mapping):
        raise TypeError("attempt must be an object")
    attempt = _closed(
        attempt_node,
        {"scope", "scope_sha256", "step_key", "visit_key", "ordinal"},
        field="attempt",
    )
    ordinal = _u63(
        attempt["ordinal"],
        field="attempt.ordinal",
        positive=True,
    )
    _digest(attempt["scope_sha256"], field="attempt.scope_sha256")
    scope = ProviderAttemptScope.from_dict(attempt["scope"])
    expected_attempt = _attempt(scope, ordinal)
    normalized_attempt = dict(expected_attempt)
    normalized_attempt["scope_sha256"] = attempt["scope_sha256"]
    if dict(attempt) != normalized_attempt:
        raise ValueError("attempt metadata contradicts scope")
    expected_scope_sha = expected_attempt["scope_sha256"]
    return (
        {
            "attempt": dict(attempt),
            "materialization_attempts": attempts,
            "task_slice": {
                "bytes": task.bytes,
                "sha256": task.sha256,
            },
            "materialization_slice": {
                "bytes": materialization.bytes,
                "sha256": materialization.sha256,
            },
        },
        [(attempt["scope_sha256"], expected_scope_sha)],
    )


class _LedgerGrammar:
    def __init__(self, header: Mapping[str, Any]) -> None:
        self.phase = "header"
        self.header = header
        self.cleanup: Mapping[str, Any] | None = None
        self.start_failure: Mapping[str, Any] | None = None
        self.ingress = "not_allocated"
        self.provider_live = False
        self.ingress_mode: str | None = None
        self.accepted_submit_receipt_flushed = False
        self.current_submit: int | None = None
        self.pending_turn: Mapping[str, Any] | None = None
        self.pending_close: Mapping[str, Any] | None = None
        self.handle_digest: str | None = None
        self.natural_proof: Mapping[str, Any] | None = None
        self.request_ids: set[str] = set()
        self.turn_digests: dict[
            tuple[int, str, int | None], Mapping[str, Any]
        ] = {}
        self.close_digests: Mapping[str, Any] | None = None
        self.manifest_binding: tuple[tuple[object, ...], ...] | None = None
        self.primary_failure_diagnostic: Mapping[str, Any] | None = None

    @staticmethod
    def _turn_key(turn: Mapping[str, Any]) -> tuple[int, str, int | None]:
        return (
            turn["delivery_ordinal"],
            turn["phase"],
            turn["submission_ordinal"],
        )

    @staticmethod
    def _opaque_turn_fields(turn: Mapping[str, Any]) -> tuple[str, ...]:
        return (
            turn["protocol_frame"]["sha256"],
            turn["canonical_slice"]["sha256"],
            turn["delivered_turn"]["sha256"],
            turn["submit_keys"]["sha256"],
        )

    def _opaque_turn_reason(
        self,
        expected: Mapping[str, Any],
        actual: Mapping[str, Any],
    ) -> str | None:
        scalar_fields = (
            "delivery_ordinal",
            "phase",
            "submission_ordinal",
        )
        if any(actual[field] != expected[field] for field in scalar_fields):
            raise ValueError("turn scalar mismatch")
        for field in (
            "protocol_frame",
            "canonical_slice",
            "delivered_turn",
            "submit_keys",
        ):
            scalar = "count" if field == "submit_keys" else "bytes"
            if actual[field][scalar] != expected[field][scalar]:
                raise ValueError("turn projection scalar mismatch")
        actual_values = self._opaque_turn_fields(actual)
        expected_values = self._opaque_turn_fields(expected)
        if actual_values == expected_values:
            return None
        for field_index, (actual_digest, expected_digest) in enumerate(
            zip(actual_values, expected_values, strict=True)
        ):
            if actual_digest == expected_digest:
                continue
            same_field_values = {
                self._opaque_turn_fields(turn)[field_index]
                for turn in self.turn_digests.values()
            }
            if actual_digest in same_field_values:
                return "opaque_digest_order_mismatch"
            return "opaque_digest_equality_mismatch"
        return None

    def _check_turn_header_binding(
        self,
        turn: Mapping[str, Any],
    ) -> str | None:
        expected_projection = (
            self.header["task_slice"]
            if turn["phase"] == "task"
            else self.header["materialization_slice"]
        )
        if (
            turn["canonical_slice"]["bytes"]
            != expected_projection["bytes"]
        ):
            raise ValueError("turn canonical-slice byte binding is invalid")
        expected = expected_projection["sha256"]
        actual = turn["canonical_slice"]["sha256"]
        if actual == expected:
            return None
        other = (
            self.header["materialization_slice"]["sha256"]
            if turn["phase"] == "task"
            else self.header["task_slice"]["sha256"]
        )
        if actual == other:
            return "opaque_digest_order_mismatch"
        return "opaque_digest_equality_mismatch"

    def _check_receipt(self, receipt: Mapping[str, Any]) -> str | None:
        digest = receipt["handle_id_sha256"]
        if self.handle_digest is None:
            self.handle_digest = digest
            return None
        if digest != self.handle_digest:
            return "opaque_digest_equality_mismatch"
        return None

    def _manifest_shape(
        self,
        manifest: Mapping[str, Any],
    ) -> tuple[tuple[object, ...], ...]:
        return tuple(
            (
                row["contract_ordinal"],
                row["role"],
                row["logical_name"],
                row["workspace_relative_path"],
            )
            for row in manifest["rows"]
        )

    def _check_payload_relations(
        self,
        event: str,
        payload: Mapping[str, Any],
    ) -> str | None:
        turn = payload.get("turn")
        if isinstance(turn, Mapping):
            binding_reason = self._check_turn_header_binding(turn)
            if binding_reason is not None:
                return binding_reason
        if event in {"task_started", "turn_offered", "close_offered"}:
            receipt = payload["receipt"]
            assert isinstance(receipt, Mapping)
            receipt_reason = self._check_receipt(receipt)
            if receipt_reason is not None:
                return receipt_reason
        if event in {"task_started", "task_start_failed", "turn_offered", "turn_offer_failed"}:
            if self.pending_turn is None or not isinstance(turn, Mapping):
                raise ValueError("turn outcome has no request")
            reason = self._opaque_turn_reason(self.pending_turn, turn)
            if reason is not None:
                return reason
        if event in {"task_start_requested", "turn_offer_requested"}:
            assert isinstance(turn, Mapping)
            key = self._turn_key(turn)
            prior = self.turn_digests.get(key)
            if prior is not None:
                reason = self._opaque_turn_reason(prior, turn)
                if reason is not None:
                    return reason
            self.pending_turn = turn
            self.turn_digests[key] = turn
        if event == "retry_queued":
            assert isinstance(turn, Mapping)
            self.pending_turn = turn
            self.turn_digests[self._turn_key(turn)] = turn
        if event == "submit_received":
            if (
                payload["configured_total"]
                != self.header["materialization_attempts"]
                or payload["submission_ordinal"]
                != (1 if self.current_submit is None else self.current_submit + 1)
                or payload["client_request_id_sha256"] in self.request_ids
            ):
                raise ValueError("submit scalar relation is invalid")
            self.request_ids.add(payload["client_request_id_sha256"])
            self.current_submit = payload["submission_ordinal"]
        if event in {
            "validation_rejected",
            "candidate_reset",
            "candidate_frozen",
            "close_offer_requested",
            "close_offered",
            "close_offer_failed",
            "join_started",
            "join_succeeded",
            "join_failed",
            "publication_started",
            "publication_succeeded",
            "publication_failed",
        }:
            if payload["submission_ordinal"] != self.current_submit:
                raise ValueError("submission ordinal relation is invalid")
        if event in {"validation_rejected", "candidate_frozen"}:
            manifest = payload["candidate_manifest"]
            assert isinstance(manifest, Mapping)
            shape = self._manifest_shape(manifest)
            if self.manifest_binding is None:
                self.manifest_binding = shape
            elif shape != self.manifest_binding:
                raise ValueError("candidate manifest binding changed")
        if event == "retry_queued":
            if self.current_submit is None:
                raise ValueError("retry has no rejected submission")
            if (
                payload["rejected_submission_ordinal"] != self.current_submit
                or payload["next_submission_ordinal"]
                != self.current_submit + 1
                or payload["next_submission_ordinal"]
                > self.header["materialization_attempts"]
            ):
                raise ValueError("retry ordinal relation is invalid")
        if event in {"close_offer_requested", "close_offered", "close_offer_failed"}:
            close = payload["close_projection"]
            assert isinstance(close, Mapping)
            if event == "close_offer_requested":
                self.pending_close = close
            elif self.pending_close is None:
                raise ValueError("close outcome has no request")
            else:
                for field in ("close_text", "submit_keys"):
                    scalar = "count" if field == "submit_keys" else "bytes"
                    if close[field][scalar] != self.pending_close[field][scalar]:
                        raise ValueError("close scalar mismatch")
                    if (
                        close[field]["sha256"]
                        != self.pending_close[field]["sha256"]
                    ):
                        return "opaque_digest_equality_mismatch"
        return None

    def _check_cross_event_scalars(
        self,
        event: str,
        payload: Mapping[str, Any],
    ) -> bool:
        turn = payload.get("turn")
        if isinstance(turn, Mapping):
            expected_slice = (
                self.header["task_slice"]
                if turn["phase"] == "task"
                else self.header["materialization_slice"]
            )
            if (
                turn["canonical_slice"]["bytes"]
                != expected_slice["bytes"]
            ):
                return False
        if event == "turn_offer_requested" and isinstance(turn, Mapping):
            if self.phase == "task_started":
                if (
                    turn["phase"] != "initial_materialization"
                    or turn["submission_ordinal"] != 1
                    or turn["delivery_ordinal"] != 1
                ):
                    return False
            elif self.phase == "retry":
                if self.pending_turn is None:
                    return False
                for field in (
                    "delivery_ordinal",
                    "phase",
                    "submission_ordinal",
                ):
                    if turn[field] != self.pending_turn[field]:
                        return False
                for field in (
                    "protocol_frame",
                    "canonical_slice",
                    "delivered_turn",
                    "submit_keys",
                ):
                    scalar = "count" if field == "submit_keys" else "bytes"
                    if (
                        turn[field][scalar]
                        != self.pending_turn[field][scalar]
                    ):
                        return False
        if (
            event
            in {
                "task_started",
                "task_start_failed",
                "turn_offered",
                "turn_offer_failed",
            }
            and self.pending_turn is not None
            and isinstance(turn, Mapping)
        ):
            for field in (
                "delivery_ordinal",
                "phase",
                "submission_ordinal",
            ):
                if turn[field] != self.pending_turn[field]:
                    return False
            for field in (
                "protocol_frame",
                "canonical_slice",
                "delivered_turn",
                "submit_keys",
            ):
                scalar = "count" if field == "submit_keys" else "bytes"
                if (
                    turn[field][scalar]
                    != self.pending_turn[field][scalar]
                ):
                    return False
        if event == "submit_received":
            expected_submission = (
                1 if self.current_submit is None else self.current_submit + 1
            )
            if (
                payload["configured_total"]
                != self.header["materialization_attempts"]
                or payload["submission_ordinal"] != expected_submission
                or payload["client_request_id_sha256"] in self.request_ids
            ):
                return False
        if (
            event
            in {
                "validation_rejected",
                "candidate_reset",
                "candidate_frozen",
                "close_offer_requested",
                "close_offered",
                "close_offer_failed",
                "join_started",
                "join_succeeded",
                "join_failed",
                "publication_started",
                "publication_succeeded",
                "publication_failed",
            }
            and self.current_submit is not None
            and payload["submission_ordinal"] != self.current_submit
        ):
            return False
        if event == "retry_queued":
            if (
                payload["next_submission_ordinal"]
                > self.header["materialization_attempts"]
            ):
                return False
            if self.current_submit is not None and (
                payload["rejected_submission_ordinal"]
                != self.current_submit
                or payload["next_submission_ordinal"]
                != self.current_submit + 1
            ):
                return False
        if (
            event in {"close_offered", "close_offer_failed"}
            and self.pending_close is not None
        ):
            close = payload["close_projection"]
            assert isinstance(close, Mapping)
            for field in ("close_text", "submit_keys"):
                scalar = "count" if field == "submit_keys" else "bytes"
                if (
                    close[field][scalar]
                    != self.pending_close[field][scalar]
                ):
                    return False
        if event in {"validation_rejected", "candidate_frozen"}:
            manifest = payload["candidate_manifest"]
            assert isinstance(manifest, Mapping)
            if (
                self.manifest_binding is not None
                and self._manifest_shape(manifest) != self.manifest_binding
            ):
                return False
        if (
            event
            in {"ingress_shutdown_finished", "ingress_shutdown_failed"}
            # The floor holds whenever a close outcome proves the accepted
            # submit receipt flushed, including terminalization after a failed
            # close offer. Earlier terminalization may truthfully report zero.
            and (
                self.ingress_mode == "normal"
                or self.accepted_submit_receipt_flushed
            )
            and self.current_submit is not None
            and payload["active_requests_drained"] < 1
        ):
            return False
        return True

    def _event_order(self, event: str, payload: Mapping[str, Any]) -> bool:
        allowed: dict[str, set[str]] = {
            "header": {"task_start_requested", "cleanup_finished"},
            "task_requested": {
                "task_started",
                "task_start_failed",
                "cleanup_finished",
            },
            "task_failed": {"cleanup_finished"},
            "task_started": {"turn_offer_requested", "cleanup_finished"},
            "turn_requested": {
                "turn_offered",
                "turn_offer_failed",
                "cleanup_finished",
            },
            "turn_failed": {"cleanup_finished"},
            "turn_offered": {"submit_received", "cleanup_finished"},
            "submitted": {
                "validation_rejected",
                "candidate_frozen",
                "cleanup_finished",
            },
            "rejected": {"candidate_reset", "cleanup_finished"},
            "reset": {"retry_queued", "cleanup_finished"},
            "retry": {"turn_offer_requested", "cleanup_finished"},
            "frozen": {"close_offer_requested", "cleanup_finished"},
            "close_requested": {
                "close_offered",
                "close_offer_failed",
                "cleanup_finished",
            },
            "close_failed": {"cleanup_finished"},
            "close_offered": {"ingress_shutdown_started", "cleanup_finished"},
            "ingress_started_normal": {
                "ingress_shutdown_finished",
                "cleanup_finished",
            },
            "ingress_finished_normal": {"join_started", "cleanup_finished"},
            "join_started": {
                "join_succeeded",
                "join_failed",
                "cleanup_finished",
                "terminal_failed",
            },
            "join_failed": {"cleanup_finished"},
            "join_succeeded": {
                "publication_started",
                "terminal_failed",
            },
            "publication_started": {
                "publication_succeeded",
                "publication_failed",
                "terminal_failed",
            },
            "publication_failed": {"terminal_failed"},
            "cleanup_not_allocated": {"terminal_failed"},
            "cleanup_unresolved": {
                "ingress_shutdown_started",
                "terminal_failed",
            },
            "cleanup_not_started": {"ingress_shutdown_started"},
            "cleanup_started": {
                "ingress_shutdown_finished",
                "ingress_shutdown_failed",
            },
            "cleanup_complete": {"terminal_failed"},
            "cleanup_incomplete": {"terminal_failed"},
            "ingress_started_terminal": {
                "ingress_shutdown_finished",
                "ingress_shutdown_failed",
            },
            "ingress_finished_terminal": {"terminal_failed"},
            "ingress_failed_terminal": {"terminal_failed"},
            "terminal": set(),
        }
        return event in allowed[self.phase]

    def accept(
        self,
        event: str,
        payload: Mapping[str, Any],
    ) -> str | None:
        if not self._check_cross_event_scalars(event, payload):
            return "payload_invalid"
        if not self._event_order(event, payload):
            return "event_order_invalid"
        try:
            opaque_reason = self._check_payload_relations(event, payload)
        except (TypeError, ValueError):
            return "payload_invalid"
        if opaque_reason is not None:
            return opaque_reason

        if event == "task_start_requested":
            self.phase = "task_requested"
        elif event == "task_started":
            self.phase = "task_started"
            self.provider_live = True
            self.ingress = "unresolved"
        elif event == "task_start_failed":
            self.phase = "task_failed"
            self.start_failure = payload["start_failure_outcome"]
            self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "turn_offer_requested":
            self.phase = "turn_requested"
            if self.ingress == "unresolved":
                self.ingress = "not_started"
        elif event == "turn_offered":
            self.phase = "turn_offered"
        elif event == "turn_offer_failed":
            self.phase = "turn_failed"
            self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "submit_received":
            self.phase = "submitted"
        elif event == "validation_rejected":
            self.phase = "rejected"
        elif event == "candidate_reset":
            self.phase = "reset"
        elif event == "retry_queued":
            self.phase = "retry"
        elif event == "candidate_frozen":
            self.phase = "frozen"
        elif event == "close_offer_requested":
            self.phase = "close_requested"
        elif event == "close_offered":
            self.accepted_submit_receipt_flushed = True
            self.phase = "close_offered"
        elif event == "close_offer_failed":
            self.accepted_submit_receipt_flushed = True
            self.phase = "close_failed"
            self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "ingress_shutdown_started":
            if self.cleanup is None:
                self.ingress_mode = "normal"
                self.phase = "ingress_started_normal"
            else:
                self.ingress_mode = "terminal"
                self.phase = "ingress_started_terminal"
            self.ingress = "started"
        elif event == "ingress_shutdown_finished":
            self.ingress = "complete"
            self.phase = (
                "ingress_finished_normal"
                if self.cleanup is None
                else "ingress_finished_terminal"
            )
        elif event == "ingress_shutdown_failed":
            self.ingress = "incomplete"
            self.phase = "ingress_failed_terminal"
            if self.primary_failure_diagnostic is None:
                self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "join_started":
            self.phase = "join_started"
        elif event == "join_succeeded":
            self.natural_proof = payload["natural_shutdown_proof"]
            self.phase = "join_succeeded"
        elif event == "join_failed":
            self.phase = "join_failed"
            self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "publication_started":
            self.phase = "publication_started"
        elif event == "publication_failed":
            self.phase = "publication_failed"
            self.primary_failure_diagnostic = payload["diagnostic"]
        elif event == "cleanup_finished":
            if self.cleanup is not None:
                return "event_order_invalid"
            if not self._validate_cleanup(payload):
                return "payload_invalid"
            self.cleanup = payload
            self.phase = {
                "not_allocated": "cleanup_not_allocated",
                "unresolved": "cleanup_unresolved",
                "not_started": "cleanup_not_started",
                "started": "cleanup_started",
                "complete": "cleanup_complete",
                "incomplete": "cleanup_incomplete",
            }[self.ingress]
        elif event == "terminal_failed":
            if not self._validate_terminal(payload):
                return "payload_invalid"
            self.phase = "terminal"
        elif event == "publication_succeeded":
            self.phase = "terminal"
        return None

    def _validate_cleanup(self, payload: Mapping[str, Any]) -> bool:
        if self.start_failure is not None:
            expected_status = self.start_failure["cleanup_status"]
            if expected_status == "completed":
                expected_status = "complete"
            valid = (
                payload["cleanup_status"] == expected_status
                and payload["abort_calls"] == 0
                and payload["provider_cleanup_proof"]
                == self.start_failure["proof"]
                and payload["provider_zero_survivor_proven"]
                == self.start_failure["provider_zero_survivor_proven"]
            )
            if (
                valid
                and expected_status == "incomplete"
                and payload["cleanup_diagnostic"]["reason"]
                != "adapter_start_cleanup_incomplete"
            ):
                return False
            return valid
        status = payload["cleanup_status"]
        abort_calls = payload["abort_calls"]
        proof = payload["provider_cleanup_proof"]
        diagnostic = payload["cleanup_diagnostic"]
        if not self.provider_live:
            return (
                status == "not_required"
                and abort_calls == 0
                and isinstance(proof, Mapping)
                and proof.get("disposition") == "no_backend_allocation"
                and diagnostic is None
                and payload["provider_zero_survivor_proven"] is True
            )
        if status == "complete":
            return abort_calls == 1
        if status != "incomplete" or not isinstance(diagnostic, Mapping):
            return False
        reason = diagnostic["reason"]
        if proof is None:
            return (
                abort_calls == 0
                and reason == "deadline_exhausted_before_adapter_cleanup"
            ) or (
                abort_calls == 1
                and reason
                in {
                    "deadline_exhausted_during_adapter_cleanup",
                    "adapter_cleanup_failed",
                }
            )
        if not isinstance(proof, Mapping) or abort_calls != 1:
            return False
        expected_reason = (
            "adapter_cleanup_failed"
            if proof["error_code"] is not None
            else "provider_zero_survivor_unproven"
        )
        return reason == expected_reason

    def _validate_terminal(self, payload: Mapping[str, Any]) -> bool:
        if (
            self.primary_failure_diagnostic is not None
            and payload["diagnostic"] != self.primary_failure_diagnostic
        ):
            return False
        if self.natural_proof is not None or self.phase == "join_started":
            natural = payload["natural_shutdown_proof"]
            return (
                payload["cleanup_status"] == "not_permitted"
                and payload["cleanup_diagnostic"] is None
                and payload["endpoint_shutdown_status"] == "complete"
                and natural is not None
                and (
                    self.natural_proof is None
                    or natural == self.natural_proof
                )
            )
        if self.cleanup is None:
            return False
        expected_endpoint = {
            "not_allocated": "not_allocated",
            "unresolved": "not_allocated",
            "complete": "complete",
            "incomplete": "incomplete",
        }.get(self.ingress)
        return (
            expected_endpoint is not None
            and payload["cleanup_status"]
            == self.cleanup["cleanup_status"]
            and payload["cleanup_diagnostic"]
            == self.cleanup["cleanup_diagnostic"]
            and payload["endpoint_shutdown_status"] == expected_endpoint
            and payload["natural_shutdown_proof"] is None
        )


def validate_ledger_bytes(ledger_bytes: bytes) -> dict[str, object]:
    """Validate one ledger from supplied bytes without reading runtime state."""

    if type(ledger_bytes) is not bytes:
        raise TypeError("ledger_bytes must be exact bytes")
    complete_lines: list[bytes]
    truncated = bool(ledger_bytes) and not ledger_bytes.endswith(b"\n")
    parts = ledger_bytes.split(b"\n")
    complete_lines = [
        part + b"\n"
        for part in (parts[:-1] if truncated else parts[:-1])
    ]
    decoded: list[object] = []
    last_contiguous: int | None = None
    terminal_event: str | None = None
    header_state: dict[str, Any] | None = None
    grammar: _LedgerGrammar | None = None

    for row_index, line in enumerate(complete_lines):
        try:
            text = line[:-1].decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return _validation_result(
                status="malformed",
                reason="invalid_utf8",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        try:
            row = json.loads(
                text,
                object_pairs_hook=_object_without_duplicate_keys,
                parse_constant=_reject_json_constant,
                parse_int=_parse_json_integer,
            )
        except (json.JSONDecodeError, RecursionError, TypeError, ValueError):
            return _validation_result(
                status="malformed",
                reason="invalid_json",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        decoded.append(row)
        try:
            canonical = _canonical_decoded_jsonl(row)
        except (RecursionError, TypeError, ValueError, UnicodeEncodeError):
            canonical = None
        if canonical != line:
            return _validation_result(
                status="malformed",
                reason="noncanonical_json",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        if row_index == 0:
            if (
                not isinstance(row, Mapping)
                or row.get("record_kind") != "header"
            ):
                reason = "missing_header"
            elif set(row) != _HEADER_KEYS:
                reason = "unknown_key"
            else:
                reason = None
            if reason is not None:
                return _validation_result(
                    status="malformed",
                    reason=reason,
                    row_count=len(decoded),
                    last_contiguous_seq=None,
                    terminal_event=None,
                )
            if type(row["seq"]) is not int or row["seq"] != 0:
                return _validation_result(
                    status="malformed",
                    reason="sequence_invalid",
                    row_count=len(decoded),
                    last_contiguous_seq=None,
                    terminal_event=None,
                )
            try:
                header_state, header_seals = _validated_header(row)
            except (TypeError, ValueError, KeyError):
                return _validation_result(
                    status="malformed",
                    reason="payload_invalid",
                    row_count=len(decoded),
                    last_contiguous_seq=None,
                    terminal_event=None,
                )
            last_contiguous = 0
            grammar = _LedgerGrammar(header_state)
            if any(actual != expected for actual, expected in header_seals):
                return _validation_result(
                    status="malformed",
                    reason="digest_mismatch",
                    row_count=len(decoded),
                    last_contiguous_seq=last_contiguous,
                    terminal_event=None,
                )
            continue

        assert header_state is not None
        assert grammar is not None
        if not isinstance(row, Mapping) or set(row) != _EVENT_KEYS:
            reason = "unknown_key"
        elif (
            not isinstance(row.get("event"), str)
            or row["event"] not in _EVENT_PAYLOAD_KEYS
        ):
            reason = "unknown_event"
        else:
            reason = None
        if reason is not None:
            return _validation_result(
                status="malformed",
                reason=reason,
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        seq = row["seq"]
        if (
            isinstance(seq, bool)
            or not isinstance(seq, int)
            or seq < 1
            or seq > _U63_MAX
            or last_contiguous is None
            or seq != last_contiguous + 1
        ):
            return _validation_result(
                status="malformed",
                reason="sequence_invalid",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        if row["attempt"] != header_state["attempt"]:
            return _validation_result(
                status="malformed",
                reason="attempt_mismatch",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        try:
            if (
                row["schema_version"] != LEDGER_SCHEMA_VERSION
                or row["record_kind"] != "event"
            ):
                raise ValueError("event literal is invalid")
            _timestamp(row["observed_at"], field="observed_at")
            payload, seals = _decoded_payload(
                row["event"],
                row["payload"],
            )
        except (TypeError, ValueError, KeyError):
            return _validation_result(
                status="malformed",
                reason="payload_invalid",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        grammar_reason = grammar.accept(row["event"], payload)
        if grammar_reason is not None:
            return _validation_result(
                status="malformed",
                reason=grammar_reason,
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        if any(actual != expected for actual, expected in seals):
            return _validation_result(
                status="malformed",
                reason="digest_mismatch",
                row_count=len(decoded),
                last_contiguous_seq=last_contiguous,
                terminal_event=terminal_event,
            )
        last_contiguous = seq
        if row["event"] in _TERMINAL_EVENTS:
            terminal_event = row["event"]

    if truncated:
        return _validation_result(
            status="truncated",
            reason="truncated_final_row",
            row_count=len(decoded),
            last_contiguous_seq=last_contiguous,
            terminal_event=terminal_event,
        )
    if not decoded:
        return _validation_result(
            status="malformed",
            reason="missing_header",
            row_count=0,
            last_contiguous_seq=None,
            terminal_event=None,
        )
    if terminal_event is None:
        return _validation_result(
            status="valid_prefix",
            reason="nonterminal_prefix",
            row_count=len(decoded),
            last_contiguous_seq=last_contiguous,
            terminal_event=None,
        )
    return _validation_result(
        status="complete",
        reason="complete",
        row_count=len(decoded),
        last_contiguous_seq=last_contiguous,
        terminal_event=terminal_event,
    )


def _write_all(descriptor: int, payload: bytes) -> None:
    offset = 0
    while offset < len(payload):
        written = os.write(descriptor, payload[offset:])
        if (
            isinstance(written, bool)
            or not isinstance(written, int)
            or written <= 0
        ):
            raise OSError("phase ledger write made no progress")
        offset += written


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path,
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_CLOEXEC", 0),
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _ensure_durable_directory_chain(
    run_root: Path,
    relative_parent: Path,
) -> Path:
    if not run_root.is_dir():
        raise ValueError("run_root must be an existing directory")
    _fsync_directory(run_root)
    current = run_root
    for component in relative_parent.parts:
        child = current / component
        created = False
        try:
            os.mkdir(child, 0o700)
            created = True
        except FileExistsError:
            if not child.is_dir():
                raise ValueError(
                    "phase ledger directory component is not a directory"
                )
        _fsync_directory(child)
        if created:
            _fsync_directory(current)
        current = child
    return current


class ProviderPromptPhaseLedgerWriter:
    """Single-use writer with only local sequence and terminal closure."""

    _path: Path
    _descriptor: int
    _attempt: dict[str, Any]
    _seq: int
    _terminal: bool
    _poisoned: bool
    _closed: bool
    _lock: threading.Lock

    def __init__(self) -> None:
        raise TypeError(
            "ProviderPromptPhaseLedgerWriter is factory-only; use create"
        )

    @classmethod
    def _from_created_file(
        cls,
        *,
        path: Path,
        descriptor: int,
        attempt: dict[str, Any],
    ) -> ProviderPromptPhaseLedgerWriter:
        writer = object.__new__(cls)
        writer._path = path
        writer._descriptor = descriptor
        writer._attempt = attempt
        writer._seq = 0
        writer._terminal = False
        writer._poisoned = False
        writer._closed = False
        writer._lock = threading.Lock()
        return writer

    @classmethod
    def create(
        cls,
        run_root: str | Path,
        *,
        scope: ProviderAttemptScope,
        ordinal: int,
        cut: CanonicalPromptCut,
        materialization_attempts: int,
        created_at: str,
    ) -> ProviderPromptPhaseLedgerWriter:
        relative = ledger_relative_path(scope, ordinal)
        root = Path(run_root)
        destination_parent = _ensure_durable_directory_chain(
            root,
            relative.parent,
        )
        destination = destination_parent / relative.name
        header = encode_header(
            scope=scope,
            ordinal=ordinal,
            cut=cut,
            materialization_attempts=materialization_attempts,
            created_at=created_at,
        )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                destination,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_APPEND
                | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
            _write_all(descriptor, header)
            os.fsync(descriptor)
            _fsync_directory(destination.parent)
            return cls._from_created_file(
                path=destination,
                descriptor=descriptor,
                attempt=_attempt(scope, ordinal),
            )
        except BaseException as primary_error:
            if descriptor is not None:
                try:
                    os.close(descriptor)
                except BaseException as cleanup_error:
                    primary_error.add_note(
                        "phase ledger descriptor cleanup also failed: "
                        f"{type(cleanup_error).__name__}: {cleanup_error}"
                    )
            raise

    @property
    def path(self) -> Path:
        return self._path

    def append(
        self,
        event: str,
        payload: Mapping[str, Any],
        *,
        observed_at: str,
    ) -> None:
        with self._lock:
            self._append_locked(
                event,
                payload,
                observed_at=observed_at,
            )

    def _append_locked(
        self,
        event: str,
        payload: Mapping[str, Any],
        *,
        observed_at: str,
    ) -> None:
        if self._poisoned:
            raise RuntimeError("phase ledger writer is poisoned")
        if self._closed:
            raise RuntimeError("phase ledger writer is closed")
        if self._terminal:
            raise RuntimeError("phase ledger already recorded a terminal event")
        if self._seq == _U63_MAX:
            raise RuntimeError("phase ledger sequence is exhausted")
        next_seq = self._seq + 1
        encoded = encode_event(
            seq=next_seq,
            event=event,
            attempt=self._attempt,
            observed_at=observed_at,
            payload=payload,
        )
        try:
            _write_all(self._descriptor, encoded)
            os.fsync(self._descriptor)
        except BaseException as exc:
            self._poisoned = True
            raise RuntimeError(
                "phase ledger append durability is uncertain; writer poisoned"
            ) from exc
        self._seq = next_seq
        self._terminal = event in _TERMINAL_EVENTS

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            descriptor = self._descriptor
            self._descriptor = -1
            self._closed = True
            os.close(descriptor)
