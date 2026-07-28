"""Write-only physical encoding for one phased provider-attempt ledger."""

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
