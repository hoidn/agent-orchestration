"""Private transition-resume evidence helpers for lexical checkpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


TRANSITION_CHECKPOINT_EVIDENCE_SCHEMA_VERSION = "workflow_lisp_transition_checkpoint_evidence.v1"
RESOURCE_OBSERVATION_SCHEMA_VERSION = "workflow_lisp_resource_observation.v1"

COMMITTED_RESULT_REUSED = "COMMITTED_RESULT_REUSED"
RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
AUDIT_STALE = "AUDIT_STALE"
IDEMPOTENCY_MISMATCH = "IDEMPOTENCY_MISMATCH"
NOT_TRANSITION_AWARE = "NOT_TRANSITION_AWARE"


@dataclass(frozen=True)
class TransitionResumeDiagnosticCodes:
    evidence_missing: str = "lexical_checkpoint_transition_evidence_missing"
    evidence_schema_invalid: str = "lexical_checkpoint_transition_evidence_schema_invalid"
    audit_row_missing: str = "lexical_checkpoint_transition_audit_row_missing"
    audit_digest_mismatch: str = "lexical_checkpoint_transition_audit_digest_mismatch"
    audit_row_digest_mismatch: str = "lexical_checkpoint_transition_audit_row_digest_mismatch"
    idempotency_mismatch: str = "lexical_checkpoint_transition_idempotency_mismatch"
    request_digest_mismatch: str = "lexical_checkpoint_transition_request_digest_mismatch"
    result_digest_mismatch: str = "lexical_checkpoint_transition_result_digest_mismatch"
    resource_version_conflict: str = "lexical_checkpoint_transition_resource_version_conflict"
    resource_observation_invalid: str = "lexical_checkpoint_transition_resource_observation_invalid"
    pending_replay_unresolved: str = "lexical_checkpoint_transition_pending_replay_unresolved"
    used_as_semantic_authority: str = "lexical_checkpoint_transition_used_as_semantic_authority"


DIAGNOSTIC_CODES = TransitionResumeDiagnosticCodes()


@dataclass(frozen=True)
class TransitionResumeEvaluation:
    decision: str
    diagnostics: tuple[str, ...]
    transition_identity: str | None = None
    resource_id: str | None = None
    resource_version: str | None = None
    audit_row_index: int | None = None
    audit_row_digest: str | None = None
    result: Mapping[str, Any] | None = None
    version: str | None = None


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def sha256_json(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_dumps(value).encode('utf-8')).hexdigest()}"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _require_non_empty_string(value: Any, diagnostic: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(diagnostic)
    return value


def validate_transition_checkpoint_evidence(evidence: Mapping[str, Any]) -> None:
    if evidence.get("schema_version") != TRANSITION_CHECKPOINT_EVIDENCE_SCHEMA_VERSION:
        raise ValueError(DIAGNOSTIC_CODES.evidence_schema_invalid)
    for key in (
        "transition_identity",
        "resource_id",
        "resource_kind",
        "resource_version",
        "audit_path",
        "audit_digest",
        "audit_row_digest",
        "audit_outcome_code",
        "idempotency_key",
        "request_digest",
        "result_digest",
        "backend_kind",
        "source_map_origin_key",
    ):
        _require_non_empty_string(evidence.get(key), DIAGNOSTIC_CODES.evidence_schema_invalid)
    if not isinstance(evidence.get("audit_row_index"), int) or evidence["audit_row_index"] < 0:
        raise ValueError(DIAGNOSTIC_CODES.evidence_schema_invalid)


def build_transition_checkpoint_evidence(
    *,
    transition_identity: str,
    resource_id: str,
    resource_kind: str,
    resource_version: str,
    expected_version: str | None,
    audit_path: str,
    audit_digest: str,
    audit_row_index: int,
    audit_row_digest: str,
    audit_outcome_code: str,
    idempotency_key: str,
    request_digest: str,
    result_digest: str,
    backend_kind: str,
    source_map_origin_key: str,
) -> dict[str, Any]:
    evidence = {
        "schema_version": TRANSITION_CHECKPOINT_EVIDENCE_SCHEMA_VERSION,
        "transition_identity": transition_identity,
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "resource_version": resource_version,
        "expected_version": expected_version,
        "audit_path": audit_path,
        "audit_digest": audit_digest,
        "audit_row_index": audit_row_index,
        "audit_row_digest": audit_row_digest,
        "audit_outcome_code": audit_outcome_code,
        "idempotency_key": idempotency_key,
        "request_digest": request_digest,
        "result_digest": result_digest,
        "backend_kind": backend_kind,
        "source_map_origin_key": source_map_origin_key,
    }
    validate_transition_checkpoint_evidence(evidence)
    return evidence


def validate_resource_observation(observation: Mapping[str, Any]) -> None:
    if observation.get("schema_version") != RESOURCE_OBSERVATION_SCHEMA_VERSION:
        raise ValueError(DIAGNOSTIC_CODES.resource_observation_invalid)
    for key in (
        "resource_id",
        "resource_kind",
        "observed_version",
        "transition_identity",
        "checkpoint_id",
        "program_point_id",
        "source_step_id",
        "source_map_origin_key",
        "audit_path",
        "audit_digest",
    ):
        _require_non_empty_string(observation.get(key), DIAGNOSTIC_CODES.resource_observation_invalid)


def build_resource_observation(
    *,
    resource_id: str,
    resource_kind: str,
    observed_version: str,
    transition_identity: str,
    checkpoint_id: str,
    program_point_id: str,
    source_step_id: str,
    source_map_origin_key: str,
    audit_path: str,
    audit_digest: str,
) -> dict[str, Any]:
    observation = {
        "schema_version": RESOURCE_OBSERVATION_SCHEMA_VERSION,
        "resource_id": resource_id,
        "resource_kind": resource_kind,
        "observed_version": observed_version,
        "transition_identity": transition_identity,
        "checkpoint_id": checkpoint_id,
        "program_point_id": program_point_id,
        "source_step_id": source_step_id,
        "source_map_origin_key": source_map_origin_key,
        "audit_path": audit_path,
        "audit_digest": audit_digest,
    }
    validate_resource_observation(observation)
    return observation


def transition_checkpoint_evidence_from_effect_ref(effect_ref: Mapping[str, Any]) -> Mapping[str, Any] | None:
    effect_ref_map = _mapping(effect_ref)
    evidence = {
        "schema_version": effect_ref_map.get("evidence_schema_version"),
        "transition_identity": effect_ref_map.get("transition_identity"),
        "resource_id": effect_ref_map.get("resource_id"),
        "resource_kind": effect_ref_map.get("resource_kind"),
        "resource_version": effect_ref_map.get("resource_version"),
        "expected_version": effect_ref_map.get("expected_version"),
        "audit_path": effect_ref_map.get("audit_path"),
        "audit_digest": effect_ref_map.get("audit_digest"),
        "audit_row_index": effect_ref_map.get("audit_row_index"),
        "audit_row_digest": effect_ref_map.get("audit_row_digest"),
        "audit_outcome_code": effect_ref_map.get("audit_outcome_code"),
        "idempotency_key": effect_ref_map.get("idempotency_key"),
        "request_digest": effect_ref_map.get("request_digest"),
        "result_digest": effect_ref_map.get("result_digest"),
        "backend_kind": effect_ref_map.get("backend_kind"),
        "source_map_origin_key": effect_ref_map.get("source_map_origin_key"),
    }
    if evidence["schema_version"] is None:
        return None
    validate_transition_checkpoint_evidence(evidence)
    return evidence


def evaluate_transition_resume(
    effect_ref: Mapping[str, Any],
    *,
    workspace: Path,
    authoritative_resource: Mapping[str, Any] | None = None,
    resource_observations: tuple[Mapping[str, Any], ...] = (),
) -> TransitionResumeEvaluation:
    from orchestrator.workflow.transition_executor import (
        load_transition_resource_state_for_kind,
        lookup_transition_audit_record,
        read_transition_audit_rows,
        read_pending_transition_replay,
        transition_audit_file_digest,
        transition_audit_row_digest,
    )

    evidence = transition_checkpoint_evidence_from_effect_ref(effect_ref)
    if evidence is None:
        return TransitionResumeEvaluation(
            decision=NOT_TRANSITION_AWARE,
            diagnostics=(DIAGNOSTIC_CODES.evidence_missing,),
        )

    for observation in resource_observations:
        try:
            validate_resource_observation(observation)
        except ValueError as exc:
            return TransitionResumeEvaluation(
                decision=AUDIT_STALE,
                diagnostics=(str(exc),),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=evidence["resource_version"],
            )

    authoritative = _mapping(authoritative_resource)
    if not authoritative:
        return TransitionResumeEvaluation(
            decision=NOT_TRANSITION_AWARE,
            diagnostics=(DIAGNOSTIC_CODES.evidence_missing,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    authoritative_audit_path = authoritative.get("audit_path")
    if not isinstance(authoritative_audit_path, Path):
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.used_as_semantic_authority,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    checkpoint_paths = {
        "audit_path": (workspace / evidence["audit_path"]).resolve(),
    }
    for field_name in ("state_path", "bridge_path"):
        path_value = effect_ref.get(field_name)
        if isinstance(path_value, str) and path_value:
            checkpoint_paths[field_name] = (workspace / path_value).resolve()
    secondary_state_paths = effect_ref.get("secondary_state_paths")
    if isinstance(secondary_state_paths, list):
        checkpoint_paths["secondary_state_paths"] = tuple(
            (workspace / str(path)).resolve()
            for path in secondary_state_paths
        )
    authoritative_paths = {
        "audit_path": authoritative_audit_path.resolve(),
    }
    for field_name in ("state_path", "bridge_path"):
        path_value = authoritative.get(field_name)
        if isinstance(path_value, Path):
            authoritative_paths[field_name] = path_value.resolve()
    authoritative_secondary_paths = authoritative.get("secondary_state_paths")
    if isinstance(authoritative_secondary_paths, list):
        authoritative_paths["secondary_state_paths"] = tuple(
            path.resolve()
            for path in authoritative_secondary_paths
            if isinstance(path, Path)
        )
    if checkpoint_paths != authoritative_paths:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.used_as_semantic_authority,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    audit_path = authoritative_paths["audit_path"]
    resource: dict[str, Any] = {
        "resource_kind": evidence["resource_kind"],
        "resource_id": evidence["resource_id"],
        "audit_path": audit_path,
    }
    for field_name in ("state_path", "bridge_path"):
        if field_name in authoritative_paths:
            resource[field_name] = authoritative_paths[field_name]
    if "secondary_state_paths" in authoritative_paths:
        resource["secondary_state_paths"] = list(authoritative_paths["secondary_state_paths"])

    current_audit_digest = transition_audit_file_digest(audit_path)
    if current_audit_digest != evidence["audit_digest"]:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.audit_digest_mismatch,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )

    rows = read_transition_audit_rows(audit_path)
    audit_row_index = evidence["audit_row_index"]
    if audit_row_index >= len(rows):
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.audit_row_missing,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    row = rows[audit_row_index]
    if transition_audit_row_digest(row) != evidence["audit_row_digest"]:
        if row.get("idempotency_key") != evidence["idempotency_key"]:
            return TransitionResumeEvaluation(
                decision=IDEMPOTENCY_MISMATCH,
                diagnostics=(DIAGNOSTIC_CODES.idempotency_mismatch,),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=evidence["resource_version"],
            )
        if row.get("request_digest") != evidence["request_digest"]:
            return TransitionResumeEvaluation(
                decision=AUDIT_STALE,
                diagnostics=(DIAGNOSTIC_CODES.request_digest_mismatch,),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=evidence["resource_version"],
            )
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.audit_row_digest_mismatch,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if row.get("outcome_code") not in {"committed", "replayed"}:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.audit_row_missing,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if row.get("request_digest") != evidence["request_digest"]:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.request_digest_mismatch,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if row.get("idempotency_key") != evidence["idempotency_key"]:
        return TransitionResumeEvaluation(
            decision=IDEMPOTENCY_MISMATCH,
            diagnostics=(DIAGNOSTIC_CODES.idempotency_mismatch,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if sha256_json(row.get("result")) != evidence["result_digest"]:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.result_digest_mismatch,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    lookup = lookup_transition_audit_record(
        resource,
        transition_name=evidence["transition_identity"],
        resource_kind=evidence["resource_kind"],
        resource_id=evidence["resource_id"],
        idempotency_key=evidence["idempotency_key"],
        request_digest=evidence["request_digest"],
    )
    pending_row = read_pending_transition_replay(audit_path)
    if lookup is None:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.audit_row_missing,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if lookup.get("pending_replay") or pending_row is not None:
        return TransitionResumeEvaluation(
            decision=AUDIT_STALE,
            diagnostics=(DIAGNOSTIC_CODES.pending_replay_unresolved,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    try:
        current_state = load_transition_resource_state_for_kind(evidence["resource_kind"], resource)
    except Exception:
        return TransitionResumeEvaluation(
            decision=RESOURCE_CONFLICT,
            diagnostics=(DIAGNOSTIC_CODES.resource_version_conflict,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=evidence["resource_version"],
        )
    if current_state.version != evidence["resource_version"]:
        return TransitionResumeEvaluation(
            decision=RESOURCE_CONFLICT,
            diagnostics=(DIAGNOSTIC_CODES.resource_version_conflict,),
            transition_identity=evidence["transition_identity"],
            resource_id=evidence["resource_id"],
            resource_version=current_state.version,
        )
    for observation in resource_observations:
        if observation.get("resource_id") != evidence["resource_id"]:
            return TransitionResumeEvaluation(
                decision=AUDIT_STALE,
                diagnostics=(DIAGNOSTIC_CODES.resource_observation_invalid,),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=current_state.version,
            )
        if observation.get("observed_version") != current_state.version:
            return TransitionResumeEvaluation(
                decision=RESOURCE_CONFLICT,
                diagnostics=(DIAGNOSTIC_CODES.resource_version_conflict,),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=current_state.version,
            )
        if observation.get("audit_digest") != current_audit_digest:
            return TransitionResumeEvaluation(
                decision=AUDIT_STALE,
                diagnostics=(DIAGNOSTIC_CODES.resource_observation_invalid,),
                transition_identity=evidence["transition_identity"],
                resource_id=evidence["resource_id"],
                resource_version=current_state.version,
            )
    return TransitionResumeEvaluation(
        decision=COMMITTED_RESULT_REUSED,
        diagnostics=(),
        transition_identity=evidence["transition_identity"],
        resource_id=evidence["resource_id"],
        resource_version=current_state.version,
        audit_row_index=evidence["audit_row_index"],
        audit_row_digest=evidence["audit_row_digest"],
        result=row.get("result") if isinstance(row.get("result"), Mapping) else None,
        version=str(row.get("version")) if row.get("version") is not None else None,
    )
