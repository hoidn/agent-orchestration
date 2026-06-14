"""Typed effect resume policy helpers for lexical checkpoints."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping


EFFECT_RESUME_POLICY_SCHEMA_VERSION = "workflow_lisp_effect_resume_policy.v1"

POLICY_KINDS = frozenset(
    {
        "recompute_or_reuse_checkpoint",
        "reuse_validated_structured_output",
        "reuse_validated_workflow_call",
        "regenerate_deterministic_view",
        "preserve_durable_view",
        "transition_idempotent_audit_required",
        "fail_closed_non_idempotent",
        "certified_resume_protocol_required",
    }
)
POLICY_DECISIONS = frozenset({"REUSABLE", "REGENERATE", "BARRIER", "INVALID"})
UNSAFE_PENDING_BEHAVIORS = frozenset(
    {
        "fail_closed",
        "audit_barrier",
        "requires_certified_resume_protocol",
    }
)
LEGACY_PROVISIONAL_POLICIES = frozenset({"shadow_record_only"})

_REQUIRED_EVIDENCE_KEYS = {
    "recompute_or_reuse_checkpoint": (),
    "reuse_validated_structured_output": ("structured_output",),
    "reuse_validated_workflow_call": ("workflow_call",),
    "regenerate_deterministic_view": ("materialized_view",),
    "preserve_durable_view": ("materialized_view",),
    "transition_idempotent_audit_required": ("transition",),
    "fail_closed_non_idempotent": (),
    "certified_resume_protocol_required": ("command_resume_protocol",),
}


@dataclass(frozen=True)
class EffectPolicyDiagnosticCodes:
    missing: str = "lexical_checkpoint_effect_policy_missing"
    schema_invalid: str = "lexical_checkpoint_effect_policy_schema_invalid"
    digest_mismatch: str = "lexical_checkpoint_effect_policy_digest_mismatch"
    policy_unknown: str = "lexical_checkpoint_effect_policy_unknown_kind"
    boundary_mismatch: str = "lexical_checkpoint_effect_policy_boundary_mismatch"
    evidence_missing: str = "lexical_checkpoint_effect_policy_evidence_missing"
    evidence_invalid: str = "lexical_checkpoint_effect_policy_evidence_stale"
    structured_output_invalid: str = "lexical_checkpoint_effect_policy_structured_output_invalid"
    command_uncertified: str = "lexical_checkpoint_effect_policy_command_uncertified"
    pending_effect_unsafe: str = "lexical_checkpoint_effect_policy_pending_effect_unsafe"
    transition_audit_missing: str = "lexical_checkpoint_effect_policy_transition_audit_missing"
    materialized_view_mismatch: str = "lexical_checkpoint_effect_policy_materialized_view_mismatch"
    used_as_semantic_authority: str = "lexical_checkpoint_effect_policy_used_as_semantic_authority"
    source_lineage_mismatch: str = "lexical_checkpoint_source_lineage_mismatch"


DIAGNOSTIC_CODES = EffectPolicyDiagnosticCodes()


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha256_text(value: object) -> str:
    return f"sha256:{hashlib.sha256(str(value).encode('utf-8')).hexdigest()}"


def _sha256_json(value: Any) -> str:
    return _sha256_text(canonical_json_dumps(value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _non_empty_string(value: Any, diagnostic: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(diagnostic)
    return value


def build_effect_resume_policy(
    *,
    policy_kind: str,
    effect_kind: str,
    boundary_kind: str,
    step_id: str,
    source_map_origin_key: str,
    evidence_requirements: Mapping[str, Any] | None = None,
    unsafe_pending_behavior: str = "fail_closed",
) -> dict[str, Any]:
    policy = {
        "schema_version": EFFECT_RESUME_POLICY_SCHEMA_VERSION,
        "policy_kind": policy_kind,
        "effect_kind": effect_kind,
        "boundary_kind": boundary_kind,
        "step_id": step_id,
        "source_map_origin_key": source_map_origin_key,
        "evidence_requirements": dict(_mapping(evidence_requirements)),
        "unsafe_pending_behavior": unsafe_pending_behavior,
    }
    policy["policy_digest"] = derive_effect_resume_policy_digest(policy)
    validate_effect_resume_policy(policy)
    return policy


def derive_effect_resume_policy_digest(policy: Mapping[str, Any]) -> str:
    normalized = {
        "schema_version": EFFECT_RESUME_POLICY_SCHEMA_VERSION,
        "policy_kind": policy.get("policy_kind"),
        "effect_kind": policy.get("effect_kind"),
        "boundary_kind": policy.get("boundary_kind"),
        "step_id": policy.get("step_id"),
        "source_map_origin_key": policy.get("source_map_origin_key"),
        "unsafe_pending_behavior": policy.get("unsafe_pending_behavior"),
        "evidence_requirements": dict(_mapping(policy.get("evidence_requirements"))),
    }
    return _sha256_json(normalized)


def validate_effect_resume_policy(
    policy: Mapping[str, Any],
    *,
    expected_origin_key: str | None = None,
) -> None:
    if policy.get("schema_version") != EFFECT_RESUME_POLICY_SCHEMA_VERSION:
        raise ValueError(DIAGNOSTIC_CODES.schema_invalid)
    policy_kind = _non_empty_string(policy.get("policy_kind"), DIAGNOSTIC_CODES.policy_unknown)
    if policy_kind not in POLICY_KINDS:
        raise ValueError(DIAGNOSTIC_CODES.policy_unknown)
    _non_empty_string(policy.get("effect_kind"), DIAGNOSTIC_CODES.evidence_invalid)
    _non_empty_string(policy.get("boundary_kind"), DIAGNOSTIC_CODES.boundary_mismatch)
    _non_empty_string(policy.get("step_id"), DIAGNOSTIC_CODES.evidence_missing)
    source_map_origin_key = _non_empty_string(
        policy.get("source_map_origin_key"),
        DIAGNOSTIC_CODES.source_lineage_mismatch,
    )
    if expected_origin_key is not None and source_map_origin_key != expected_origin_key:
        raise ValueError(DIAGNOSTIC_CODES.source_lineage_mismatch)
    unsafe_pending_behavior = _non_empty_string(
        policy.get("unsafe_pending_behavior"),
        DIAGNOSTIC_CODES.evidence_invalid,
    )
    if unsafe_pending_behavior not in UNSAFE_PENDING_BEHAVIORS:
        raise ValueError(DIAGNOSTIC_CODES.pending_effect_unsafe)
    evidence_requirements = dict(_mapping(policy.get("evidence_requirements")))
    _validate_evidence_requirements(policy_kind=policy_kind, evidence_requirements=evidence_requirements)
    expected_digest = derive_effect_resume_policy_digest(policy)
    if policy.get("policy_digest") != expected_digest:
        raise ValueError(DIAGNOSTIC_CODES.digest_mismatch)


def validate_effect_boundary_payload(effect_boundary: Mapping[str, Any], *, expected_origin_key: str) -> None:
    policy = _mapping(effect_boundary.get("policy"))
    policy_status = effect_boundary.get("policy_status")
    if policy:
        validate_effect_resume_policy(policy, expected_origin_key=expected_origin_key)
        return
    if policy_status in LEGACY_PROVISIONAL_POLICIES:
        return
    raise ValueError(DIAGNOSTIC_CODES.missing)


def is_legacy_provisional_policy(effect_boundary: Mapping[str, Any]) -> bool:
    return effect_boundary.get("policy_status") in LEGACY_PROVISIONAL_POLICIES and not _mapping(
        effect_boundary.get("policy")
    )


def derive_legacy_shadow_policy_digest(
    *,
    point_kind: str,
    step_kind: str | None,
    effect_kind: str | None,
    boundary_kind: str | None,
    loop_name: str | None,
) -> str:
    return _sha256_json(
        {
            "point_kind": point_kind,
            "policy_status": "shadow_record_only",
            "step_kind": step_kind,
            "effect_kind": effect_kind,
            "boundary_kind": boundary_kind,
            "loop_name": loop_name,
        }
    )


def _validate_evidence_requirements(
    *,
    policy_kind: str,
    evidence_requirements: Mapping[str, Any],
) -> None:
    required_keys = _REQUIRED_EVIDENCE_KEYS[policy_kind]
    for key in required_keys:
        requirement = _mapping(evidence_requirements.get(key))
        if not requirement:
            raise ValueError(_diagnostic_for_requirement_key(key, missing=True))
        _validate_requirement_shape(key=key, requirement=requirement)


def _validate_requirement_shape(*, key: str, requirement: Mapping[str, Any]) -> None:
    if key == "structured_output":
        _non_empty_string(requirement.get("bundle_path_ref"), DIAGNOSTIC_CODES.structured_output_invalid)
        _non_empty_string(requirement.get("contract_digest"), DIAGNOSTIC_CODES.structured_output_invalid)
        if not isinstance(requirement.get("payload_digest_required"), bool):
            raise ValueError(DIAGNOSTIC_CODES.structured_output_invalid)
        if not isinstance(requirement.get("declared_target_only"), bool):
            raise ValueError(DIAGNOSTIC_CODES.structured_output_invalid)
        return
    if key == "materialized_view":
        _non_empty_string(requirement.get("renderer_id"), DIAGNOSTIC_CODES.materialized_view_mismatch)
        return
    if key == "workflow_call":
        _non_empty_string(requirement.get("callee_workflow"), DIAGNOSTIC_CODES.evidence_invalid)
        _non_empty_string(requirement.get("target_dsl_version"), DIAGNOSTIC_CODES.evidence_invalid)
        _non_empty_string(requirement.get("callee_checksum"), DIAGNOSTIC_CODES.evidence_invalid)
        return
    if key == "transition":
        _non_empty_string(requirement.get("transition_identity"), DIAGNOSTIC_CODES.transition_audit_missing)
        return
    if key == "command_resume_protocol":
        _non_empty_string(requirement.get("protocol_name"), DIAGNOSTIC_CODES.command_uncertified)
        return


def _diagnostic_for_requirement_key(key: str, *, missing: bool) -> str:
    if key == "structured_output":
        return DIAGNOSTIC_CODES.structured_output_invalid if not missing else DIAGNOSTIC_CODES.evidence_missing
    if key == "materialized_view":
        return DIAGNOSTIC_CODES.materialized_view_mismatch if not missing else DIAGNOSTIC_CODES.evidence_missing
    if key == "transition":
        return DIAGNOSTIC_CODES.transition_audit_missing if not missing else DIAGNOSTIC_CODES.evidence_missing
    if key == "command_resume_protocol":
        return DIAGNOSTIC_CODES.command_uncertified
    return DIAGNOSTIC_CODES.evidence_missing if missing else DIAGNOSTIC_CODES.evidence_invalid
