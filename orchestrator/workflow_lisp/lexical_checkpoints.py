"""Lexical checkpoint schema helpers and private storage-role allocation."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from orchestrator._common.canonical import (
    canonical_json_dumps,
    sha256_json as _sha256_json,
)
from orchestrator._common.status import is_run_terminal
from orchestrator.workflow.state_layout import (
    GeneratedPathAllocation,
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)
from orchestrator.workflow_lisp.lexical_checkpoint_effect_policies import (
    DIAGNOSTIC_CODES as EFFECT_POLICY_DIAGNOSTIC_CODES,
    LEGACY_PROVISIONAL_POLICIES,
    derive_legacy_shadow_policy_digest,
    validate_effect_boundary_payload,
    validate_effect_resume_policy,
)
from orchestrator.workflow_lisp.lexical_checkpoint_transition_resume import (
    build_resource_observation,
    build_transition_checkpoint_evidence,
    transition_checkpoint_evidence_from_effect_ref,
)
from orchestrator.workflow_lisp.lexical_checkpoint_restore import (
    capture_restore_payload,
    validate_restore_payload,
    validate_restore_point_metadata,
)


CHECKPOINT_RECORD_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint.v1"
CHECKPOINT_POINTS_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_points.v1"
CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_shadow_report.v1"
COMPLETED_EFFECT_REF_SCHEMA_VERSION = "workflow_lisp_completed_effect_ref.v1"

POINT_KINDS = frozenset({"effect_boundary", "loop_back_edge"})
PROVISIONAL_POLICIES = LEGACY_PROVISIONAL_POLICIES


@dataclass(frozen=True)
class CheckpointDiagnosticCodes:
    schema_invalid: str = "lexical_checkpoint_schema_invalid"
    program_identity_mismatch: str = "lexical_checkpoint_program_identity_mismatch"
    source_map_missing: str = "lexical_checkpoint_source_map_missing"
    binding_schema_mismatch: str = "lexical_checkpoint_binding_schema_mismatch"
    storage_role_invalid: str = "lexical_checkpoint_storage_role_invalid"
    source_lineage_mismatch: str = "lexical_checkpoint_source_lineage_mismatch"
    effect_policy_unknown: str = "lexical_checkpoint_effect_policy_unknown"
    completed_effect_invalid: str = "lexical_checkpoint_completed_effect_invalid"
    used_as_semantic_authority: str = "lexical_checkpoint_used_as_semantic_authority"
    record_collision: str = "lexical_checkpoint_record_collision"


DIAGNOSTIC_CODES = CheckpointDiagnosticCodes()


def _sha256_text(value: object) -> str:
    return f"sha256:{hashlib.sha256(str(value).encode('utf-8')).hexdigest()}"


def _digest(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part) for part in parts)
    return f"{prefix}:{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def derive_program_point_id(
    *,
    workflow_name: str,
    point_kind: str,
    origin_key: str,
    identity_digest: str,
) -> str:
    return _digest("pp", CHECKPOINT_POINTS_SCHEMA_VERSION, workflow_name, point_kind, origin_key, identity_digest)


def derive_checkpoint_id(
    *,
    workflow_name: str,
    program_point_id: str,
    executable_identity: str,
    lowering_schema_version: str,
    checkpoint_schema_version: str = CHECKPOINT_RECORD_SCHEMA_VERSION,
    storage_scope: str,
) -> str:
    return _digest(
        "ckpt",
        checkpoint_schema_version,
        workflow_name,
        program_point_id,
        executable_identity,
        lowering_schema_version,
        storage_scope,
    )


def derive_record_id(
    *,
    checkpoint_id: str,
    run_id: str,
    execution_index: int,
    visit_count: int,
    loop_iteration: int | None,
    call_frame_id: str | None,
) -> str:
    return _digest(
        "record",
        CHECKPOINT_RECORD_SCHEMA_VERSION,
        checkpoint_id,
        run_id,
        execution_index,
        visit_count,
        loop_iteration if loop_iteration is not None else "",
        call_frame_id or "",
    )


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _target_dsl_at_least(value: str, minimum: tuple[int, ...]) -> bool:
    try:
        return tuple(int(part) for part in value.split(".")) >= minimum
    except (AttributeError, TypeError, ValueError):
        return False


def _point_field(point: Any, name: str, default: Any = None) -> Any:
    if isinstance(point, Mapping):
        return point.get(name, default)
    return getattr(point, name, default)


def _point_details(point: Any) -> Mapping[str, Any]:
    return _mapping(_point_field(point, "details", {}))


def _point_payload(point: Any) -> dict[str, Any]:
    payload = {
        "checkpoint_id": _point_field(point, "checkpoint_id"),
        "program_point_id": _point_field(point, "program_point_id"),
        "point_kind": _point_field(point, "point_kind"),
        "workflow_name": _point_field(point, "workflow_name"),
        "step_id": _point_field(point, "step_id"),
        "node_id": _point_field(point, "node_id"),
        "presentation_key": _point_field(point, "presentation_key"),
        "origin_key": _point_field(point, "origin_key"),
    }
    payload.update(dict(_point_details(point)))
    return payload


def _checkpoint_identity_component_digest(
    point: Any,
    *,
    required: bool = False,
) -> str | None:
    """Return a validated optional executable identity component."""

    details = _point_details(point)
    payload = details if details else _mapping(point)
    step_kind = payload.get("step_kind")
    executable_identity = _mapping(payload.get("executable_identity"))
    component_digest = executable_identity.get("identity_component_digest")
    if component_digest is None:
        if required or step_kind in {"provider_peer_group", "run_ref", "trial"}:
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        return None
    if not isinstance(component_digest, str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        component_digest,
    ) is None:
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    return component_digest


def _component_checkpoint_policy_digest(
    point: Any,
    *,
    required: bool = False,
) -> str | None:
    """Validate the identity-bound policy for a component-bearing boundary."""

    details = _point_details(point)
    payload = details if details else _mapping(point)
    step_kind = payload.get("step_kind")
    supported_kinds = {"provider_peer_group", "run_ref", "trial"}
    if not required and step_kind not in supported_kinds:
        return None
    effect_boundary = _mapping(payload.get("effect_boundary"))
    policy = _mapping(effect_boundary.get("policy"))
    executable_identity = _mapping(payload.get("executable_identity"))
    if step_kind not in supported_kinds:
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    component_digest = _checkpoint_identity_component_digest(
        point,
        required=True,
    )
    expected_policy_kind = {
        "provider_peer_group": "fail_closed_non_idempotent",
        "run_ref": "reuse_validated_run_ref_result",
        "trial": "reuse_validated_trial_result",
    }[step_kind]
    if step_kind == "provider_peer_group":
        expected_evidence: Mapping[str, Any] = {}
    elif step_kind == "run_ref":
        expected_evidence = {
            "run_ref_result": {
                "step_config_digest": component_digest,
            }
        }
    else:
        trial_static_digest = component_digest
        trial_result_digest = executable_identity.get(
            "trial_result_contract_digest"
        )
        for digest in (trial_result_digest,):
            if not isinstance(digest, str) or re.fullmatch(
                r"sha256:[0-9a-f]{64}", digest
            ) is None:
                raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        expected_evidence = {
            "trial_result": {
                "trial_static_config_digest": trial_static_digest,
                "result_contract_digest": trial_result_digest,
            }
        }
    if (
        _point_field(point, "point_kind") != "effect_boundary"
        or effect_boundary.get("effect_kind") != step_kind
        or effect_boundary.get("boundary_kind") != step_kind
        or policy.get("policy_kind") != expected_policy_kind
        or policy.get("effect_kind") != step_kind
        or policy.get("boundary_kind") != step_kind
        or policy.get("step_id") != executable_identity.get("step_id")
        or policy.get("unsafe_pending_behavior") != "fail_closed"
        or dict(_mapping(policy.get("evidence_requirements")))
        != expected_evidence
    ):
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    try:
        validate_effect_resume_policy(
            policy,
            expected_origin_key=str(
                _point_field(point, "origin_key") or ""
            ),
        )
    except ValueError as exc:
        raise ValueError(
            DIAGNOSTIC_CODES.program_identity_mismatch
        ) from exc
    policy_digest = policy.get("policy_digest")
    if not isinstance(policy_digest, str) or re.fullmatch(
        r"sha256:[0-9a-f]{64}",
        policy_digest,
    ) is None:
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    return policy_digest


def _runtime_program_identity_point(
    point: Any,
    *,
    component_required: bool = False,
) -> dict[str, Any]:
    payload = {
        "checkpoint_id": _point_field(point, "checkpoint_id"),
        "program_point_id": _point_field(point, "program_point_id"),
        "point_kind": _point_field(point, "point_kind"),
        "step_id": _point_field(point, "step_id"),
    }
    component_digest = _checkpoint_identity_component_digest(
        point,
        required=component_required,
    )
    if component_digest is not None:
        payload["identity_component_digest"] = component_digest
    executable_identity = _mapping(
        (_point_details(point) or _mapping(point)).get("executable_identity")
    )
    if executable_identity.get("trial_result_contract_digest") is not None:
        payload["trial_result_contract_digest"] = executable_identity.get(
            "trial_result_contract_digest"
        )
    policy_digest = _component_checkpoint_policy_digest(
        point,
        required=component_digest is not None,
    )
    if policy_digest is not None:
        payload["effect_policy_digest"] = policy_digest
    return payload


def _require_non_empty_string(value: Any, diagnostic: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(diagnostic)
    return value


def _validate_wcc_identity(payload: Mapping[str, Any]) -> None:
    wcc_identity = _mapping(payload.get("wcc_identity"))
    runtime_identity = _mapping(payload.get("runtime_program_identity"))
    node_id_digest = _require_non_empty_string(
        wcc_identity.get("node_id_digest"), DIAGNOSTIC_CODES.program_identity_mismatch
    )
    scope_id_digest = _require_non_empty_string(
        wcc_identity.get("scope_id_digest"), DIAGNOSTIC_CODES.program_identity_mismatch
    )
    _require_non_empty_string(runtime_identity.get("wcc_node_id"), DIAGNOSTIC_CODES.program_identity_mismatch)
    _require_non_empty_string(runtime_identity.get("wcc_scope_id"), DIAGNOSTIC_CODES.program_identity_mismatch)
    _require_non_empty_string(
        runtime_identity.get("lowering_schema_version"), DIAGNOSTIC_CODES.program_identity_mismatch
    )
    if node_id_digest != _sha256_text(runtime_identity["wcc_node_id"]):
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    if scope_id_digest != _sha256_text(runtime_identity["wcc_scope_id"]):
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)


def validate_checkpoint_point_payload(point: Mapping[str, Any]) -> None:
    _require_non_empty_string(point.get("checkpoint_id"), DIAGNOSTIC_CODES.program_identity_mismatch)
    _require_non_empty_string(point.get("program_point_id"), DIAGNOSTIC_CODES.program_identity_mismatch)
    point_kind = _require_non_empty_string(point.get("point_kind"), DIAGNOSTIC_CODES.program_identity_mismatch)
    if point_kind not in POINT_KINDS:
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    component_digest = _checkpoint_identity_component_digest(point)
    _component_checkpoint_policy_digest(
        point,
        required=component_digest is not None,
    )
    _require_non_empty_string(point.get("origin_key"), DIAGNOSTIC_CODES.source_lineage_mismatch)
    _validate_wcc_identity(point)
    binding_schema = _mapping(point.get("binding_schema"))
    if not binding_schema.get("schema_digest"):
        raise ValueError(DIAGNOSTIC_CODES.binding_schema_mismatch)
    storage = _mapping(point.get("storage"))
    semantic_role = storage.get("semantic_role")
    privacy = storage.get("privacy")
    resume_scope = storage.get("resume_scope")
    if semantic_role != GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD.value:
        raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
    if privacy != GeneratedPathPrivacy.RUNTIME_SIDECAR.value:
        raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
    if point_kind == "effect_boundary" and resume_scope != GeneratedPathResumeScope.STEP_VISIT.value:
        raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
    if point_kind == "loop_back_edge" and resume_scope != GeneratedPathResumeScope.LOOP_FRAME.value:
        raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
    effect_policy = _mapping(point.get("effect_boundary"))
    loop_back_edge = _mapping(point.get("loop_back_edge"))
    if point_kind == "effect_boundary":
        try:
            validate_effect_boundary_payload(effect_policy, expected_origin_key=str(point.get("origin_key") or ""))
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
    if point_kind == "loop_back_edge" and not loop_back_edge:
        raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    restore = _mapping(point.get("restore"))
    if restore:
        validate_restore_point_metadata(restore)


def checkpoint_record_binding_schema_digest(point: Mapping[str, Any]) -> str:
    binding_schema = _mapping(point.get("binding_schema"))
    digest = binding_schema.get("schema_digest")
    if isinstance(digest, str) and digest:
        return digest
    raise ValueError(DIAGNOSTIC_CODES.binding_schema_mismatch)


def checkpoint_record_effect_policy_digest(point: Mapping[str, Any]) -> str:
    point_kind = str(point.get("point_kind") or "")
    if point_kind == "effect_boundary":
        payload = _mapping(point.get("effect_boundary"))
        policy = _mapping(payload.get("policy"))
        if policy:
            validate_effect_resume_policy(policy, expected_origin_key=str(point.get("origin_key") or ""))
            return str(policy["policy_digest"])
        if payload.get("policy_status") not in PROVISIONAL_POLICIES:
            raise ValueError(DIAGNOSTIC_CODES.effect_policy_unknown)
        return derive_legacy_shadow_policy_digest(
            point_kind=point_kind,
            step_kind=str(point.get("step_kind") or "") or None,
            effect_kind=str(payload.get("effect_kind") or "") or None,
            boundary_kind=str(payload.get("boundary_kind") or "") or None,
            loop_name=str(payload.get("loop_name") or "") or None,
        )
    payload = _mapping(point.get("loop_back_edge"))
    return derive_legacy_shadow_policy_digest(
        point_kind=point_kind,
        step_kind=str(point.get("step_kind") or "") or None,
        effect_kind=str(payload.get("effect_kind") or "") or None,
        boundary_kind=str(payload.get("boundary_kind") or "") or None,
        loop_name=str(payload.get("loop_name") or "") or None,
    )


def describe_checkpoint_record_policy(
    record: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    validity_envelope = _mapping(record.get("validity_envelope"))
    observed_digest = validity_envelope.get("effect_policy_digest")
    point_kind = str(
        (expected_point or {}).get("point_kind")
        or record.get("point_kind")
        or ""
    )
    if not isinstance(observed_digest, str) or not observed_digest:
        return {
            "record_policy_status": "invalid",
            "restore_authorized": False,
            "diagnostic": EFFECT_POLICY_DIAGNOSTIC_CODES.missing,
        }
    if expected_point is None:
        return {
            "record_policy_status": "historical_shadow_only",
            "restore_authorized": False,
            "diagnostic": None,
        }

    expected_digest = checkpoint_record_effect_policy_digest(expected_point)
    if point_kind != "effect_boundary":
        return {
            "record_policy_status": "non_effect_boundary",
            "restore_authorized": False,
            "diagnostic": None if observed_digest == expected_digest else EFFECT_POLICY_DIAGNOSTIC_CODES.digest_mismatch,
        }

    effect_boundary = _mapping(expected_point.get("effect_boundary"))
    policy = _mapping(effect_boundary.get("policy"))
    if policy:
        legacy_digest = derive_legacy_shadow_policy_digest(
            point_kind=point_kind,
            step_kind=str(expected_point.get("step_kind") or "") or None,
            effect_kind=str(effect_boundary.get("effect_kind") or "") or None,
            boundary_kind=str(effect_boundary.get("boundary_kind") or "") or None,
            loop_name=str(effect_boundary.get("loop_name") or "") or None,
        )
        if observed_digest == expected_digest:
            return {
                "record_policy_status": "policy_enforced",
                "restore_authorized": True,
                "diagnostic": None,
            }
        if observed_digest == legacy_digest and record.get("provisional_policy") in PROVISIONAL_POLICIES:
            return {
                "record_policy_status": "historical_shadow_only",
                "restore_authorized": False,
                "diagnostic": None,
            }
        return {
            "record_policy_status": "invalid",
            "restore_authorized": False,
            "diagnostic": EFFECT_POLICY_DIAGNOSTIC_CODES.digest_mismatch,
        }
    return {
        "record_policy_status": "historical_shadow_only",
        "restore_authorized": False,
        "diagnostic": None if observed_digest == expected_digest else EFFECT_POLICY_DIAGNOSTIC_CODES.digest_mismatch,
    }


def _completed_effect_refs_digest(completed_effect_refs: Sequence[Mapping[str, Any]]) -> str:
    return _sha256_json(list(completed_effect_refs))


def _runtime_step_for_point(executor: Any, point: Any) -> Any:
    node_id = _point_field(point, "node_id")
    if not isinstance(node_id, str) or not node_id:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    return executor._runtime_step_for_node_id(
        node_id,
        presentation_name=_point_field(point, "presentation_key"),
        step_id=_point_field(point, "step_id"),
    )


def _point_success_checkpoint_is_suppressed(
    executor: Any,
    point: Any,
) -> bool:
    """Ask whether this exact persisted point is a derived success."""

    suppression = getattr(
        executor,
        "_pure_replay_success_checkpoint_is_suppressed",
        None,
    )
    if not callable(suppression):
        return False
    return suppression(_runtime_step_for_point(executor, point)) is True


def _state_snapshot(executor: Any) -> Mapping[str, Any]:
    current_state = getattr(executor.state_manager, "state", None)
    if current_state is None:
        return {}
    if hasattr(current_state, "to_dict"):
        return current_state.to_dict()
    if isinstance(current_state, Mapping):
        return current_state
    return {}


def _step_state_for_runtime_step(executor: Any, runtime_step: Any) -> Mapping[str, Any]:
    state = _mapping(_state_snapshot(executor))
    step_name = runtime_step.get("name")
    steps = _mapping(state.get("steps"))
    direct = _mapping(steps.get(step_name))
    if direct.get("status") == "completed":
        return direct
    step_id = runtime_step.get("step_id")
    matches = [
        _mapping(result)
        for result in steps.values()
        if isinstance(result, Mapping) and result.get("step_id") == step_id
    ]
    if not matches:
        return direct
    matches.sort(key=lambda result: int(result.get("visit_count") or 0), reverse=True)
    return matches[0]


def _workflow_call_debug_payload(
    executor: Any,
    *,
    point: Any,
    step_state: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    call_debug = _mapping(_mapping(step_state.get("debug")).get("call"))
    if isinstance(call_debug.get("call_frame_id"), str) and call_debug.get("call_frame_id"):
        return call_debug

    workflow_call = _mapping(_mapping(point_policy.get("evidence_requirements")).get("workflow_call"))
    expected_callee = workflow_call.get("callee_workflow")
    expected_outputs_digest = _sha256_json(_mapping(step_state.get("artifacts")))
    point_name = str(_point_field(point, "presentation_key") or "")
    steps = _mapping(_mapping(_state_snapshot(executor)).get("steps"))
    candidates: list[tuple[int, int, Mapping[str, Any]]] = []

    for name, result in steps.items():
        if not isinstance(name, str):
            continue
        candidate_state = _mapping(result)
        if candidate_state.get("status") != "completed":
            continue
        candidate_debug = _mapping(_mapping(candidate_state.get("debug")).get("call"))
        candidate_frame_id = candidate_debug.get("call_frame_id")
        if not isinstance(candidate_frame_id, str) or not candidate_frame_id:
            continue
        if isinstance(expected_callee, str) and expected_callee:
            import_alias = candidate_debug.get("import_alias")
            if not isinstance(import_alias, str) or import_alias != expected_callee:
                continue
        if _sha256_json(_mapping(candidate_debug.get("workflow_outputs"))) != expected_outputs_digest:
            continue
        prefix_score = len(os.path.commonprefix((point_name, name))) if point_name else 0
        visit_count = int(candidate_state.get("visit_count") or 0)
        candidates.append((prefix_score, visit_count, candidate_debug))

    if not candidates:
        return {}
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates[0][2]


def _json_value_from_workspace(workspace: Path, relative_path: str) -> Any:
    path = (workspace / relative_path).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid) from exc
    if not path.is_file():
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid) from exc


def _json_object_from_workspace(workspace: Path, relative_path: str) -> Mapping[str, Any]:
    payload = _json_value_from_workspace(workspace, relative_path)
    if not isinstance(payload, Mapping):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    return payload


def _file_digest_from_workspace(workspace: Path, relative_path: str) -> str:
    path = (workspace / relative_path).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid) from exc
    if not path.is_file():
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _workflow_version_policy_from_workspace(workspace: Path, relative_path: str) -> str:
    path = (workspace / relative_path).resolve()
    try:
        path.relative_to(workspace.resolve())
    except ValueError as exc:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid) from exc
    if not path.is_file():
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid) from exc
    if path.suffix == ".orc":
        match = re.search(r'\(:target-dsl\s+"([^"]+)"\)', text)
        if match is None:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        return match.group(1)
    for line in text.splitlines():
        if line.strip().startswith("version:"):
            _, _, value = line.partition(":")
            version = value.strip()
            if version:
                return version
    raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)


def _provider_prompt_input_contract_digest(runtime_step: Any) -> str:
    from orchestrator.workflow.prompt_dependency_contract import (
        serialize_compiler_prompt_dependency_contract,
    )

    compiler_contract = getattr(
        runtime_step,
        "compiler_prompt_dependency_contract",
        None,
    )
    payload = {
        "provider": runtime_step.get("provider"),
        "input_file": runtime_step.get("input_file"),
        "asset_file": runtime_step.get("asset_file"),
        "prompt_consumes": runtime_step.get("prompt_consumes"),
        "depends_on": runtime_step.get("depends_on"),
        "asset_depends_on": runtime_step.get("asset_depends_on"),
        "inject_output_contract": runtime_step.get("inject_output_contract"),
        "inject_consumes": runtime_step.get("inject_consumes"),
        "consumes_injection_position": runtime_step.get("consumes_injection_position"),
    }
    if compiler_contract is not None:
        payload["compiler_prompt_dependency_contract"] = (
            serialize_compiler_prompt_dependency_contract(compiler_contract)
        )
    return _sha256_json(payload)


def _completed_effect_ref_base(point: Any, *, effect_kind: str) -> dict[str, Any]:
    return {
        "effect_ref_schema_version": COMPLETED_EFFECT_REF_SCHEMA_VERSION,
        "effect_kind": effect_kind,
        "step_id": _point_field(point, "step_id"),
        "status": "completed",
        "source_map_origin_key": _point_field(point, "origin_key"),
    }


def _policy_ref_invalid_diagnostic(expected_point: Mapping[str, Any]) -> str:
    effect_boundary = _mapping(expected_point.get("effect_boundary"))
    effect_kind = effect_boundary.get("effect_kind")
    policy = _mapping(effect_boundary.get("policy"))
    policy_kind = policy.get("policy_kind")
    if effect_kind in {"command", "provider"} or policy_kind in {
        "reuse_validated_structured_output",
        "certified_resume_protocol_required",
    }:
        return EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid
    if effect_kind == "materialize_view":
        return EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch
    if effect_kind == "resource_transition":
        return EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing
    if effect_kind == "run_ref":
        return EFFECT_POLICY_DIAGNOSTIC_CODES.run_ref_result_invalid
    if effect_kind == "trial":
        return EFFECT_POLICY_DIAGNOSTIC_CODES.trial_result_invalid
    return DIAGNOSTIC_CODES.completed_effect_invalid


def _materialized_view_durability_mode(point_policy: Mapping[str, Any]) -> str:
    return "preserve" if point_policy.get("policy_kind") == "preserve_durable_view" else "regenerate"


def _structured_output_completed_effect_ref(
    executor: Any,
    *,
    point: Any,
    runtime_step: Any,
    step_state: Mapping[str, Any],
    effect_kind: str,
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    _, resolved_output_bundle, path_error = executor._resolve_output_contract_paths(runtime_step, _state_snapshot(executor))
    if path_error is not None or not isinstance(resolved_output_bundle, Mapping):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    bundle_path = resolved_output_bundle.get("path")
    if not isinstance(bundle_path, str) or not bundle_path:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    # Root results legally serialize any JSON value at the document root, so
    # structured-output evidence must not require an object-shaped bundle.
    bundle_payload = _json_value_from_workspace(executor.workspace, bundle_path)
    structured_output = _mapping(_mapping(point_policy.get("evidence_requirements")).get("structured_output"))
    return {
        **_completed_effect_ref_base(point, effect_kind=effect_kind),
        "evidence_kind": "structured_output_bundle",
        "bundle_path": bundle_path,
        "bundle_path_ref": structured_output.get("bundle_path_ref"),
        "contract_digest": _sha256_json(
            {
                "path": bundle_path,
                "fields": resolved_output_bundle.get("fields", []),
            }
        ),
        "payload_digest": _sha256_json(bundle_payload),
        "artifact_digest": _sha256_json(_mapping(step_state.get("artifacts"))),
        **(
            {"prompt_input_contract_digest": _provider_prompt_input_contract_digest(runtime_step)}
            if effect_kind == "provider"
            else {}
        ),
    }


def _workflow_call_completed_effect_ref(
    executor: Any,
    *,
    point: Any,
    step_state: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    call_debug = _workflow_call_debug_payload(
        executor,
        point=point,
        step_state=step_state,
        point_policy=point_policy,
    )
    call_frame_id = call_debug.get("call_frame_id")
    if not isinstance(call_frame_id, str) or not call_frame_id:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    workflow_call = _mapping(_mapping(point_policy.get("evidence_requirements")).get("workflow_call"))
    callee_workflow = workflow_call.get("callee_workflow") or call_debug.get("import_alias")
    if not isinstance(callee_workflow, str) or not callee_workflow:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    workflow_file = call_debug.get("workflow_file")
    if not isinstance(workflow_file, str) or not workflow_file:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    return {
        **_completed_effect_ref_base(point, effect_kind="call"),
        "evidence_kind": "workflow_call_result",
        "call_frame_id": call_frame_id,
        "callee_workflow": callee_workflow,
        "workflow_file": workflow_file,
        "target_dsl_version": _workflow_version_policy_from_workspace(executor.workspace, workflow_file),
        "callee_checksum": _file_digest_from_workspace(executor.workspace, workflow_file),
        "input_digest": _sha256_json(_mapping(call_debug.get("bound_inputs"))),
        "terminal_result_digest": _sha256_json(_mapping(call_debug.get("workflow_outputs"))),
    }


def _materialized_view_completed_effect_ref(
    executor: Any,
    *,
    point: Any,
    step_state: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    materialize_debug = _mapping(_mapping(step_state.get("debug")).get("materialize_view"))
    required = {}
    for key in ("target_path", "evidence_path", "view_digest", "evidence_key"):
        value = materialize_debug.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        required[key] = value
    evidence_record = _json_object_from_workspace(executor.workspace, required["evidence_path"])
    renderer_id = evidence_record.get("renderer_id")
    renderer_version = evidence_record.get("renderer_version")
    value_digest = evidence_record.get("value_digest")
    if not isinstance(renderer_id, str) or not renderer_id:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if not isinstance(renderer_version, int):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if not isinstance(value_digest, str) or not value_digest:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    return {
        **_completed_effect_ref_base(point, effect_kind="materialize_view"),
        "evidence_kind": "materialized_view",
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "value_digest": value_digest,
        "durability_mode": _materialized_view_durability_mode(point_policy),
        **required,
    }


def _resource_transition_completed_effect_ref(
    executor: Any,
    *,
    point: Any,
    runtime_step: Any,
    step_state: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    from orchestrator.workflow.transition_executor import lookup_committed_transition_result

    transition_debug = _mapping(_mapping(step_state.get("debug")).get("resource_transition"))
    config = _mapping(runtime_step.get("resource_transition"))
    declaration = config.get("declaration")
    if declaration is None:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    resolved_resource, resource_error = executor._resolve_resource_transition_bindings(
        config.get("resource"),
        _state_snapshot(executor),
    )
    if resource_error is not None or not isinstance(resolved_resource, Mapping):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    normalized_resource = executor._normalize_resource_transition_paths(dict(resolved_resource))
    resource_id = transition_debug.get("resource_id")
    resource_version = transition_debug.get("version")
    if not isinstance(resource_id, str) or not resource_id:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if not isinstance(resource_version, str) or not resource_version:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    transition_policy = _mapping(_mapping(point_policy.get("evidence_requirements")).get("transition"))
    transition_identity = transition_policy.get("transition_identity")
    if not isinstance(transition_identity, str) or not transition_identity:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    resolved_request, request_error = executor._resolve_resource_transition_bindings(
        config.get("request_bindings"),
        _state_snapshot(executor),
    )
    if request_error is not None or not isinstance(resolved_request, Mapping):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    audit_path = normalized_resource.get("audit_path")
    if isinstance(audit_path, Path):
        audit_path = _relative_path(executor.state_manager, audit_path)
    if not isinstance(audit_path, str) or not audit_path:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    transition_lookup = lookup_committed_transition_result(
        declaration,
        normalized_resource,
        resolved_request,
    )
    if transition_lookup is None or transition_lookup.get("pending_replay"):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if transition_lookup.get("audit_path") != normalized_resource.get("audit_path"):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    audit_digest = transition_lookup.get("audit_digest")
    audit_row_digest = transition_lookup.get("audit_row_digest")
    request_digest = transition_lookup.get("request_digest")
    outcome_code = transition_lookup.get("outcome_code")
    version = transition_lookup.get("version")
    if not all(isinstance(value, str) and value for value in (audit_digest, audit_row_digest, request_digest, outcome_code, version)):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    audit_row_index = transition_lookup.get("audit_row_index")
    if not isinstance(audit_row_index, int):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    expected_version = config.get("expected_version")
    if isinstance(expected_version, Mapping):
        resolved_expected_version, version_error = executor._resolve_resource_transition_bindings(
            expected_version,
            _state_snapshot(executor),
        )
        if version_error is not None and resolved_expected_version is not None:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        expected_version = resolved_expected_version
    elif expected_version is not None:
        resolved_expected_version, version_error = executor._resolve_resource_transition_bindings(
            expected_version,
            _state_snapshot(executor),
        )
        if version_error is None:
            expected_version = resolved_expected_version
    evidence = build_transition_checkpoint_evidence(
        transition_identity=transition_identity,
        resource_id=resource_id,
        resource_kind=str(declaration.resource.resource_kind),
        resource_version=resource_version,
        expected_version=expected_version if isinstance(expected_version, str) else None,
        audit_path=audit_path,
        audit_digest=audit_digest,
        audit_row_index=audit_row_index,
        audit_row_digest=audit_row_digest,
        audit_outcome_code=outcome_code,
        idempotency_key=str(transition_lookup["idempotency_key"]),
        request_digest=request_digest,
        result_digest=_sha256_json(transition_lookup.get("result")),
        backend_kind=str(declaration.transition.backend.get("kind") or ""),
        source_map_origin_key=str(_point_field(point, "origin_key") or ""),
    )
    state_path = normalized_resource.get("state_path")
    bridge_path = normalized_resource.get("bridge_path")
    secondary_state_paths = normalized_resource.get("secondary_state_paths")
    return {
        **_completed_effect_ref_base(point, effect_kind="resource_transition"),
        "evidence_kind": "transition_audit",
        "evidence_schema_version": evidence["schema_version"],
        "transition_identity": evidence["transition_identity"],
        "resource_id": evidence["resource_id"],
        "resource_kind": evidence["resource_kind"],
        "resource_version": evidence["resource_version"],
        "expected_version": evidence["expected_version"],
        "audit_path": evidence["audit_path"],
        "audit_digest": evidence["audit_digest"],
        "audit_row_index": evidence["audit_row_index"],
        "audit_row_digest": evidence["audit_row_digest"],
        "audit_outcome_code": evidence["audit_outcome_code"],
        "idempotency_key": evidence["idempotency_key"],
        "request_digest": evidence["request_digest"],
        "result_digest": evidence["result_digest"],
        "backend_kind": evidence["backend_kind"],
        **(
            {"state_path": _relative_path(executor.state_manager, state_path)}
            if isinstance(state_path, Path)
            else {}
        ),
        **(
            {"bridge_path": _relative_path(executor.state_manager, bridge_path)}
            if isinstance(bridge_path, Path)
            else {}
        ),
        **(
            {
                "secondary_state_paths": [
                    _relative_path(executor.state_manager, path)
                    for path in secondary_state_paths
                    if isinstance(path, Path)
                ]
            }
            if isinstance(secondary_state_paths, list)
            else {}
        ),
    }


def _run_ref_completed_effect_ref(
    *,
    point: Any,
    runtime_step: Any,
    step_state: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Project one settled parent result without flattening runtime authority."""

    from orchestrator.workflow.executable_ir import RunRefStepConfig
    from orchestrator.workflow.run_ref.config import (
        validate_run_ref_static_config_authority,
    )
    from orchestrator.workflow.run_ref.ledger import (
        settled_result_binding_from_record,
    )

    diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.run_ref_result_invalid
    execution_config = getattr(
        getattr(runtime_step, "node", None),
        "execution_config",
        None,
    )
    if type(execution_config) is not RunRefStepConfig:
        raise ValueError(diagnostic)
    try:
        validate_run_ref_static_config_authority(execution_config.run_ref)
    except (TypeError, ValueError) as exc:
        raise ValueError(diagnostic) from exc
    requirement = _mapping(
        _mapping(point_policy.get("evidence_requirements")).get(
            "run_ref_result"
        )
    )
    static_digest = requirement.get("step_config_digest")
    if static_digest != execution_config.run_ref.digest:
        raise ValueError(diagnostic)
    settled_record = step_state.get("run_ref")
    artifacts = step_state.get("artifacts")
    if not isinstance(settled_record, Mapping) or not isinstance(
        artifacts,
        Mapping,
    ):
        raise ValueError(diagnostic)
    try:
        settled = settled_result_binding_from_record(settled_record)
    except (TypeError, ValueError) as exc:
        raise ValueError(diagnostic) from exc
    if (
        dict(settled_record) != settled.record
        or settled.step_config_digest
        != execution_config.step_config_digest
        or settled.visit.step_id != _point_field(point, "step_id")
    ):
        raise ValueError(diagnostic)
    return {
        **_completed_effect_ref_base(point, effect_kind="run_ref"),
        "evidence_kind": "run_ref_result",
        # Checkpoint identity intentionally remains the static configuration;
        # the complete executable/capsule binding stays inside settlement.
        "step_config_digest": static_digest,
        "settled_result": settled.record,
    }


def _runtime_step_field(runtime_step: Any, name: str) -> Any:
    getter = getattr(runtime_step, "get", None)
    if callable(getter):
        return getter(name)
    return getattr(runtime_step, name, None)


def _trial_runtime_request_for_checkpoint(
    *,
    state_manager: Any,
    workspace: Path,
    runtime_step: Any,
    step_state: Mapping[str, Any],
    state: Mapping[str, Any],
    point: Any,
    frame_identity: Mapping[str, Any] | None = None,
) -> tuple[Any, Path]:
    """Rebuild one trial request and its derived ledger path from live authority."""

    from orchestrator.workflow.executable_ir import TrialStepConfig
    from orchestrator.workflow.provider_attempts import resolve_aggregate_run_owner
    from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
    from orchestrator.workflow.run_ref.runtime import (
        resolve_run_ref_parent_input_values_for_config,
    )
    from orchestrator.workflow.trial.config import (
        build_trial_runtime_request,
        validate_trial_static_config_authority,
    )
    from orchestrator.workflow.trial.contracts import (
        derive_trial_cell_effect_scopes,
    )

    diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.trial_result_invalid
    execution_config = getattr(
        getattr(runtime_step, "node", None),
        "execution_config",
        None,
    )
    if type(execution_config) is not TrialStepConfig:
        raise ValueError(diagnostic)
    try:
        validate_trial_static_config_authority(execution_config.trial)
    except (TypeError, ValueError) as exc:
        raise ValueError(diagnostic) from exc
    point_payload = (
        dict(point)
        if isinstance(point, Mapping)
        else _point_payload(point)
    )
    effect_boundary = _mapping(point_payload.get("effect_boundary"))
    point_policy = _mapping(effect_boundary.get("policy"))
    requirement = _mapping(
        _mapping(point_policy.get("evidence_requirements")).get(
            "trial_result"
        )
    )
    step_name = _runtime_step_field(runtime_step, "name")
    step_id = _runtime_step_field(runtime_step, "step_id")
    visit_count = step_state.get("visit_count")
    if (
        effect_boundary.get("effect_kind") != "trial"
        or point_policy.get("policy_kind") != "reuse_validated_trial_result"
        or requirement.get("trial_static_config_digest")
        != execution_config.trial.digest
        or requirement.get("result_contract_digest")
        != execution_config.trial.result_digest
        or not isinstance(step_name, str)
        or not step_name
        or not isinstance(step_id, str)
        or not step_id
        or step_id != point_payload.get("step_id")
        or step_state.get("status") != "completed"
        or step_state.get("step_id") != step_id
        or isinstance(visit_count, bool)
        or not isinstance(visit_count, int)
        or visit_count < 1
        or not isinstance(step_state.get("trial"), Mapping)
        or not isinstance(step_state.get("artifacts"), Mapping)
    ):
        raise ValueError(diagnostic)

    try:
        owner = resolve_aggregate_run_owner(state_manager)
        root_manager = owner.root_manager
        parent_workspace = Path(root_manager.workspace).resolve()
        if Path(workspace).resolve() != parent_workspace:
            raise ValueError(diagnostic)
        parent_run_root = Path(owner.aggregate_root)
        if (
            not parent_run_root.is_absolute()
            or parent_run_root.resolve(strict=False) != parent_run_root
        ):
            raise ValueError(diagnostic)
        root_state = root_manager.state
        run_ref_root_value = getattr(root_state, "run_ref_root", None)
        if not isinstance(run_ref_root_value, str) or not run_ref_root_value:
            raise ValueError(diagnostic)
        run_ref_root = Path(run_ref_root_value)
        if (
            not run_ref_root.is_absolute()
            or run_ref_root.resolve(strict=False) != run_ref_root
        ):
            raise ValueError(diagnostic)
        frame_ids = owner.resume_scope_path.call_frame_ids
        call_frame_id = frame_ids[-1] if frame_ids else None
        execution_frame_id = call_frame_id or "root"
        if frame_identity is not None and (
            frame_identity.get("visit_count") != visit_count
            or frame_identity.get("call_frame_id") != call_frame_id
        ):
            raise ValueError(diagnostic)
        resolved_inputs = {
            arm.arm_id: resolve_run_ref_parent_input_values_for_config(
                arm.run_ref,
                state,
            )
            for arm in execution_config.arms
        }
        request = build_trial_runtime_request(
            step_config=execution_config,
            visit=RunRefVisitKey(
                parent_run_id=root_manager.run_id,
                execution_frame_id=execution_frame_id,
                call_frame_id=call_frame_id,
                step_id=step_id,
                visit_count=visit_count,
            ),
            resolved_inputs_by_arm=resolved_inputs,
        )
        scopes = derive_trial_cell_effect_scopes(
            request=request,
            parent_run_root=parent_run_root,
            run_ref_root=run_ref_root,
        )
    except (OSError, TypeError, ValueError) as exc:
        if str(exc) == diagnostic:
            raise
        raise ValueError(diagnostic) from exc
    if not scopes or len({scope.trial_root for scope in scopes}) != 1:
        raise ValueError(diagnostic)
    return request, scopes[0].trial_root / "trial-events.jsonl"


def _validated_terminal_trial_rows(
    *,
    ledger_path: Path,
    request: Any,
    workspace: Path,
    step_name: str,
    step_state: Mapping[str, Any],
    state: Mapping[str, Any],
) -> tuple[Any, Any]:
    """Reuse the settled rows only after proving the ledger is already terminal."""

    from orchestrator.workflow.trial.ledger import load_trial_event_ledger
    from orchestrator.workflow.trial.settlement import (
        commit_trial_parent_settlement,
        prepare_trial_parent_settlement,
    )

    diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.trial_result_invalid
    try:
        ledger = load_trial_event_ledger(ledger_path)
        prepared_rows = tuple(
            row for row in ledger.rows if row.kind == "trial_prepared"
        )
        committed_rows = tuple(
            row for row in ledger.rows if row.kind == "trial_parent_committed"
        )
        if (
            len(prepared_rows) != 1
            or len(committed_rows) != 1
            or ledger.rows[-1].row_digest != committed_rows[0].row_digest
        ):
            raise ValueError(diagnostic)
        prepared = prepare_trial_parent_settlement(
            ledger_path,
            request=request,
            parent_workspace=Path(workspace).resolve(),
            result_envelope=step_state["trial"],
        )
        # The commit edge binds the moment this trial cleared current_step.
        # A later step may now be current, but this same trial may not be.
        settlement_state = dict(state)
        current_step = settlement_state.get("current_step")
        if current_step is not None:
            later_step_id = _mapping(current_step).get("step_id")
            if (
                not isinstance(current_step, Mapping)
                or not isinstance(later_step_id, str)
                or not later_step_id
                or later_step_id == request.visit.step_id
            ):
                raise ValueError(diagnostic)
        settlement_state.pop("current_step", None)
        committed = commit_trial_parent_settlement(
            ledger_path,
            request=request,
            prepared=prepared,
            step_name=step_name,
            expected_artifacts=step_state["artifacts"],
            read_parent_state=lambda: settlement_state,
        )
        if (
            prepared.row.row_digest != prepared_rows[0].row_digest
            or committed.row_digest != committed_rows[0].row_digest
        ):
            raise ValueError(diagnostic)
    except (OSError, TypeError, ValueError) as exc:
        if str(exc) == diagnostic:
            raise
        raise ValueError(diagnostic) from exc
    return prepared, committed


def _trial_completed_effect_ref(
    executor: Any,
    *,
    point: Any,
    runtime_step: Any,
    step_state: Mapping[str, Any],
) -> Mapping[str, Any]:
    state = _state_snapshot(executor)
    workspace = Path(
        getattr(
            executor,
            "workspace",
            getattr(executor.state_manager, "workspace", Path.cwd()),
        )
    )
    request, ledger_path = _trial_runtime_request_for_checkpoint(
        state_manager=executor.state_manager,
        workspace=workspace,
        runtime_step=runtime_step,
        step_state=step_state,
        state=state,
        point=point,
    )
    prepared, committed = _validated_terminal_trial_rows(
        ledger_path=ledger_path,
        request=request,
        workspace=workspace,
        step_name=str(_runtime_step_field(runtime_step, "name")),
        step_state=step_state,
        state=state,
    )
    return {
        **_completed_effect_ref_base(point, effect_kind="trial"),
        "evidence_kind": "trial_result",
        "trial_static_config_digest": request.static_config_digest,
        "trial_step_config_digest": request.trial_step_config_digest,
        "trial_request_digest": request.digest,
        "trial_visit_digest": _sha256_json(request.visit.record),
        "result_contract_digest": request.result_contract_digest,
        "result_envelope_digest": _sha256_json(step_state["trial"]),
        "trial_prepared_row_digest": prepared.row.row_digest,
        "trial_parent_committed_row_digest": committed.row_digest,
        "parent_state_settlement_digest": committed.payload[
            "parent_state_settlement_digest"
        ],
    }


def collect_completed_effect_refs(
    executor: Any,
    *,
    point: Any,
    committed_step_state: Mapping[str, Any] | None = None,
) -> list[Mapping[str, Any]]:
    effect_boundary = _mapping(_point_details(point).get("effect_boundary"))
    effect_kind = effect_boundary.get("effect_kind")
    if not isinstance(effect_kind, str) or not effect_kind:
        return []
    if effect_kind == "pure_projection":
        return []
    runtime_step = _runtime_step_for_point(executor, point)
    step_state = (
        _mapping(committed_step_state)
        if committed_step_state is not None
        else _step_state_for_runtime_step(executor, runtime_step)
    )
    if step_state.get("status") != "completed":
        return []
    point_policy = _mapping(effect_boundary.get("policy"))
    if effect_kind in {"command", "provider"}:
        return [
            _structured_output_completed_effect_ref(
                executor,
                point=point,
                runtime_step=runtime_step,
                step_state=step_state,
                effect_kind=effect_kind,
                point_policy=point_policy,
            )
        ]
    if effect_kind == "call":
        try:
            return [
                _workflow_call_completed_effect_ref(
                    executor,
                    point=point,
                    step_state=step_state,
                    point_policy=point_policy,
                )
            ]
        except ValueError as exc:
            if str(exc) == DIAGNOSTIC_CODES.completed_effect_invalid:
                return []
            raise
    if effect_kind == "materialize_view":
        return [
            _materialized_view_completed_effect_ref(
                executor,
                point=point,
                step_state=step_state,
                point_policy=point_policy,
            )
        ]
    if effect_kind == "resource_transition":
        return [
            _resource_transition_completed_effect_ref(
                executor,
                point=point,
                runtime_step=runtime_step,
                step_state=step_state,
                point_policy=point_policy,
            )
        ]
    if effect_kind == "run_ref":
        return [
            _run_ref_completed_effect_ref(
                point=point,
                runtime_step=runtime_step,
                step_state=step_state,
                point_policy=point_policy,
            )
        ]
    if effect_kind == "trial":
        return [
            _trial_completed_effect_ref(
                executor,
                point=point,
                runtime_step=runtime_step,
                step_state=step_state,
            )
        ]
    return []


_RUN_REF_COMPLETED_EFFECT_REF_KEYS = frozenset(
    {
        "effect_ref_schema_version",
        "effect_kind",
        "step_id",
        "status",
        "source_map_origin_key",
        "evidence_kind",
        "step_config_digest",
        "settled_result",
    }
)

_TRIAL_COMPLETED_EFFECT_REF_KEYS = frozenset(
    {
        "effect_ref_schema_version",
        "effect_kind",
        "step_id",
        "status",
        "source_map_origin_key",
        "evidence_kind",
        "trial_static_config_digest",
        "trial_step_config_digest",
        "trial_request_digest",
        "trial_visit_digest",
        "result_contract_digest",
        "result_envelope_digest",
        "trial_prepared_row_digest",
        "trial_parent_committed_row_digest",
        "parent_state_settlement_digest",
    }
)


def _validate_run_ref_completed_effect_ref(
    ref: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> None:
    from orchestrator.workflow.run_ref.ledger import (
        settled_result_binding_from_record,
    )

    diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.run_ref_result_invalid
    if set(ref) != _RUN_REF_COMPLETED_EFFECT_REF_KEYS:
        raise ValueError(diagnostic)
    if (
        ref.get("effect_ref_schema_version")
        != COMPLETED_EFFECT_REF_SCHEMA_VERSION
        or ref.get("effect_kind") != "run_ref"
        or ref.get("step_id") != expected_point.get("step_id")
        or ref.get("status") != "completed"
        or ref.get("source_map_origin_key")
        != expected_point.get("origin_key")
        or ref.get("evidence_kind") != "run_ref_result"
    ):
        raise ValueError(diagnostic)
    requirement = _mapping(
        _mapping(point_policy.get("evidence_requirements")).get(
            "run_ref_result"
        )
    )
    static_digest = ref.get("step_config_digest")
    if (
        not isinstance(static_digest, str)
        or re.fullmatch(r"sha256:[0-9a-f]{64}", static_digest) is None
        or static_digest != requirement.get("step_config_digest")
    ):
        raise ValueError(diagnostic)
    settled_record = ref.get("settled_result")
    if not isinstance(settled_record, Mapping):
        raise ValueError(diagnostic)
    try:
        settled = settled_result_binding_from_record(settled_record)
    except (TypeError, ValueError) as exc:
        raise ValueError(diagnostic) from exc
    if (
        dict(settled_record) != settled.record
        or settled.visit.step_id != ref.get("step_id")
    ):
        raise ValueError(diagnostic)


def _validate_trial_completed_effect_ref(
    ref: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any],
    point_policy: Mapping[str, Any],
) -> None:
    diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.trial_result_invalid
    if set(ref) != _TRIAL_COMPLETED_EFFECT_REF_KEYS:
        raise ValueError(diagnostic)
    if (
        ref.get("effect_ref_schema_version")
        != COMPLETED_EFFECT_REF_SCHEMA_VERSION
        or ref.get("effect_kind") != "trial"
        or ref.get("step_id") != expected_point.get("step_id")
        or ref.get("status") != "completed"
        or ref.get("source_map_origin_key")
        != expected_point.get("origin_key")
        or ref.get("evidence_kind") != "trial_result"
    ):
        raise ValueError(diagnostic)
    for field in (
        "trial_static_config_digest",
        "trial_step_config_digest",
        "trial_request_digest",
        "trial_visit_digest",
        "result_contract_digest",
        "result_envelope_digest",
        "trial_prepared_row_digest",
        "trial_parent_committed_row_digest",
        "parent_state_settlement_digest",
    ):
        value = ref.get(field)
        if (
            not isinstance(value, str)
            or re.fullmatch(r"sha256:[0-9a-f]{64}", value) is None
        ):
            raise ValueError(diagnostic)
    requirement = _mapping(
        _mapping(point_policy.get("evidence_requirements")).get(
            "trial_result"
        )
    )
    if (
        ref.get("trial_static_config_digest")
        != requirement.get("trial_static_config_digest")
        or ref.get("result_contract_digest")
        != requirement.get("result_contract_digest")
    ):
        raise ValueError(diagnostic)


def _validate_completed_effect_refs(
    record: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any],
) -> None:
    completed_effect_refs = record.get("completed_effect_refs")
    if not isinstance(completed_effect_refs, list):
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    effect_boundary = _mapping(expected_point.get("effect_boundary"))
    if not _mapping(effect_boundary.get("policy")):
        if not completed_effect_refs:
            return
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    effect_kind = effect_boundary.get("effect_kind")
    if effect_kind == "pure_projection":
        if completed_effect_refs:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        return

    validity_envelope = _mapping(record.get("validity_envelope"))
    observed_digest = validity_envelope.get("completed_effect_refs_digest")
    if not completed_effect_refs:
        if observed_digest is None:
            return
        if observed_digest != _completed_effect_refs_digest(()):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        return

    if not isinstance(observed_digest, str) or not observed_digest:
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    if observed_digest != _completed_effect_refs_digest(tuple(_mapping(ref) for ref in completed_effect_refs)):
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    if len(completed_effect_refs) != 1:
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    ref = _mapping(completed_effect_refs[0])
    point_policy = _mapping(effect_boundary.get("policy"))
    if effect_kind == "run_ref":
        _validate_run_ref_completed_effect_ref(
            ref,
            expected_point=expected_point,
            point_policy=point_policy,
        )
        return
    if effect_kind == "trial":
        _validate_trial_completed_effect_ref(
            ref,
            expected_point=expected_point,
            point_policy=point_policy,
        )
        return
    for key in ("effect_ref_schema_version", "effect_kind", "step_id", "status", "source_map_origin_key"):
        value = ref.get(key)
        if key == "effect_ref_schema_version":
            if value != COMPLETED_EFFECT_REF_SCHEMA_VERSION:
                raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if ref.get("step_id") != expected_point.get("step_id"):
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    if ref.get("effect_kind") != effect_kind:
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    if ref.get("status") != "completed":
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))
    if ref.get("source_map_origin_key") != expected_point.get("origin_key"):
        raise ValueError(_policy_ref_invalid_diagnostic(expected_point))

    if effect_kind in {"command", "provider"}:
        for key in ("bundle_path", "bundle_path_ref", "contract_digest", "payload_digest", "artifact_digest"):
            value = ref.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if effect_kind == "provider":
            prompt_input_contract_digest = ref.get("prompt_input_contract_digest")
            if not isinstance(prompt_input_contract_digest, str) or not prompt_input_contract_digest:
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if ref.get("evidence_kind") != "structured_output_bundle":
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        return
    if effect_kind == "call":
        for key in (
            "call_frame_id",
            "callee_workflow",
            "workflow_file",
            "target_dsl_version",
            "callee_checksum",
            "input_digest",
            "terminal_result_digest",
        ):
            value = ref.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("evidence_kind") != "workflow_call_result":
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        return
    if effect_kind == "materialize_view":
        for key in ("target_path", "evidence_path", "view_digest", "evidence_key", "renderer_id", "value_digest", "durability_mode"):
            value = ref.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if not isinstance(ref.get("renderer_version"), int):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("evidence_kind") != "materialized_view":
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        return
    if effect_kind == "resource_transition":
        for key in ("transition_identity", "resource_id", "resource_version", "audit_path", "audit_digest", "idempotency_key"):
            value = ref.get(key)
            if not isinstance(value, str) or not value:
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing)
        evidence = transition_checkpoint_evidence_from_effect_ref(ref)
        if evidence is not None:
            for key in ("resource_kind", "audit_outcome_code", "request_digest", "result_digest", "backend_kind"):
                value = evidence.get(key)
                if not isinstance(value, str) or not value:
                    raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing)
        if ref.get("evidence_kind") != "transition_audit":
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing)
        return


def validate_completed_effect_refs_against_authoritative_state(
    record: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any],
    state: Mapping[str, Any],
    state_manager: Any,
    workspace: Path,
    executable_workflow: Any,
    runtime_plan: Any,
    loaded_workflow: Any | None = None,
) -> None:
    from orchestrator.workflow.executable_ir import RunRefStepConfig
    from orchestrator.workflow.runtime_step import RuntimeStep

    _validate_completed_effect_refs(record, expected_point=expected_point)
    completed_effect_refs = record.get("completed_effect_refs")
    if not isinstance(completed_effect_refs, list) or not completed_effect_refs:
        return
    ref = _mapping(completed_effect_refs[0])
    effect_boundary = _mapping(expected_point.get("effect_boundary"))
    effect_kind = effect_boundary.get("effect_kind")
    point_policy = _mapping(effect_boundary.get("policy"))
    node_id = expected_point.get("node_id")
    nodes = getattr(executable_workflow, "nodes", {})
    node = nodes.get(node_id) if isinstance(nodes, Mapping) else None
    if node is None:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    runtime_step = RuntimeStep(
        node=node,
        name=str(expected_point.get("presentation_key") or ""),
        step_id=str(expected_point.get("step_id") or ""),
        target_dsl_version=getattr(executable_workflow, "version", None),
    )
    qualified_checkpoints = tuple(
        checkpoint
        for checkpoint in getattr(runtime_plan, "resume_checkpoints", ())
        if (
            getattr(checkpoint, "node_id", None) == node_id
            and getattr(checkpoint, "runtime_step_id_mode", None)
            == "qualified_iteration"
        )
    )
    if len(qualified_checkpoints) > 1:
        raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
    if qualified_checkpoints:
        checkpoint = qualified_checkpoints[0]
        frame_identity = _mapping(record.get("frame_identity"))
        iteration = frame_identity.get("loop_iteration")
        observed_runtime_step_id = frame_identity.get("runtime_step_id")
        owner_node_id = getattr(
            checkpoint,
            "iteration_owner_node_id",
            None,
        )
        suffix = getattr(
            checkpoint,
            "iteration_step_id_suffix",
            None,
        )
        if (
            isinstance(iteration, bool)
            or not isinstance(iteration, int)
            or iteration < 0
            or not isinstance(observed_runtime_step_id, str)
            or not observed_runtime_step_id
            or not isinstance(owner_node_id, str)
            or not owner_node_id
            or not isinstance(suffix, str)
            or not suffix
        ):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        expected_runtime_step_id = (
            f"{owner_node_id}#{iteration}.{suffix}"
        )
        if observed_runtime_step_id != expected_runtime_step_id:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        candidates = tuple(
            _mapping(candidate)
            for candidate in _mapping(state.get("steps")).values()
            if (
                isinstance(candidate, Mapping)
                and candidate.get("step_id")
                == expected_runtime_step_id
            )
        )
        if len(candidates) != 1:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        step_state = candidates[0]
    else:
        if "runtime_step_id" in _mapping(record.get("frame_identity")):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        step_state = _mapping(
            _mapping(state.get("steps")).get(runtime_step.name)
        )

    if effect_kind == "run_ref":
        from orchestrator.workflow.provider_attempts import (
            resolve_aggregate_run_owner,
        )
        from orchestrator.workflow.run_ref.config import BundleProgram
        from orchestrator.workflow.run_ref.ledger import (
            settled_result_binding_from_record,
        )
        from orchestrator.workflow.run_ref.runtime import (
            RunRefRuntimeRequest,
            validate_completed_run_ref_authority,
        )

        diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.run_ref_result_invalid
        try:
            execution_config = getattr(node, "execution_config", None)
            if type(execution_config) is not RunRefStepConfig:
                raise ValueError(diagnostic)
            requirement = _mapping(
                _mapping(point_policy.get("evidence_requirements")).get(
                    "run_ref_result"
                )
            )
            if (
                ref.get("step_config_digest")
                != execution_config.run_ref.digest
                or ref.get("step_config_digest")
                != requirement.get("step_config_digest")
            ):
                raise ValueError(diagnostic)
            settled_record = ref.get("settled_result")
            persisted_settled = step_state.get("run_ref")
            artifacts = step_state.get("artifacts")
            if (
                step_state.get("status") != "completed"
                or not isinstance(settled_record, Mapping)
                or not isinstance(persisted_settled, Mapping)
                or dict(persisted_settled) != dict(settled_record)
                or not isinstance(artifacts, Mapping)
            ):
                raise ValueError(diagnostic)
            settled = settled_result_binding_from_record(settled_record)
            if (
                dict(settled_record) != settled.record
                or settled.step_config_digest
                != execution_config.step_config_digest
            ):
                raise ValueError(diagnostic)

            owner = resolve_aggregate_run_owner(state_manager)
            root_manager = owner.root_manager
            if Path(workspace).resolve() != Path(root_manager.workspace).resolve():
                raise ValueError(diagnostic)
            root_state = root_manager.state
            run_ref_root_value = getattr(root_state, "run_ref_root", None)
            if not isinstance(run_ref_root_value, str) or not run_ref_root_value:
                raise ValueError(diagnostic)
            frame_ids = owner.resume_scope_path.call_frame_ids
            call_frame_id = frame_ids[-1] if frame_ids else None
            execution_frame_id = call_frame_id or "root"
            frame_identity = _mapping(record.get("frame_identity"))
            visit_count = frame_identity.get("visit_count")
            if (
                isinstance(visit_count, bool)
                or not isinstance(visit_count, int)
                or visit_count <= 0
                or frame_identity.get("call_frame_id") != call_frame_id
                or settled.visit.parent_run_id != root_manager.run_id
                or settled.visit.execution_frame_id != execution_frame_id
                or settled.visit.call_frame_id != call_frame_id
                or settled.visit.step_id != step_state.get("step_id")
                or settled.visit.step_id != expected_point.get("step_id")
                or settled.visit.visit_count != visit_count
                or step_state.get("visit_count") != visit_count
            ):
                raise ValueError(diagnostic)

            capsule_dir = None
            if isinstance(execution_config.run_ref.program, BundleProgram):
                provenance = getattr(loaded_workflow, "provenance", None)
                persisted_surface = getattr(
                    provenance,
                    "frontend_persisted_surface_path",
                    None,
                )
                if not isinstance(persisted_surface, Path):
                    raise ValueError(diagnostic)
                persisted_surface = (
                    persisted_surface
                    if persisted_surface.is_absolute()
                    else Path(root_manager.workspace) / persisted_surface
                ).resolve(strict=False)
                capsule_dir = (
                    persisted_surface.parent / "run_ref_bundle_capsule.v1"
                ).resolve(strict=False)

            request = RunRefRuntimeRequest(
                step_config=execution_config,
                visit=settled.visit,
                parent_state=state,
                parent_workspace=Path(root_manager.workspace).resolve(),
                parent_run_root=owner.aggregate_root.resolve(),
                run_ref_root=Path(run_ref_root_value),
                capsule_dir=capsule_dir,
            )
            validate_completed_run_ref_authority(
                request,
                settled_result=settled.record,
                artifacts=artifacts,
                reconcile_pending=False,
            )
        except (OSError, TypeError, ValueError) as exc:
            if str(exc) == diagnostic:
                raise
            raise ValueError(diagnostic) from exc
        return

    if effect_kind == "trial":
        diagnostic = EFFECT_POLICY_DIAGNOSTIC_CODES.trial_result_invalid
        try:
            request, ledger_path = _trial_runtime_request_for_checkpoint(
                state_manager=state_manager,
                workspace=Path(workspace),
                runtime_step=runtime_step,
                step_state=step_state,
                state=state,
                point=expected_point,
                frame_identity=_mapping(record.get("frame_identity")),
            )
            prepared, committed = _validated_terminal_trial_rows(
                ledger_path=ledger_path,
                request=request,
                workspace=Path(workspace),
                step_name=str(_runtime_step_field(runtime_step, "name")),
                step_state=step_state,
                state=state,
            )
            expected = {
                "trial_static_config_digest": request.static_config_digest,
                "trial_step_config_digest": request.trial_step_config_digest,
                "trial_request_digest": request.digest,
                "trial_visit_digest": _sha256_json(request.visit.record),
                "result_contract_digest": request.result_contract_digest,
                "result_envelope_digest": _sha256_json(step_state["trial"]),
                "trial_prepared_row_digest": prepared.row.row_digest,
                "trial_parent_committed_row_digest": committed.row_digest,
                "parent_state_settlement_digest": committed.payload[
                    "parent_state_settlement_digest"
                ],
            }
            if any(ref.get(name) != value for name, value in expected.items()):
                raise ValueError(diagnostic)
        except (OSError, TypeError, ValueError) as exc:
            if str(exc) == diagnostic:
                raise
            raise ValueError(diagnostic) from exc
        return

    if effect_kind in {"command", "provider"}:
        if step_state.get("status") != "completed":
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        step_artifacts = step_state.get("artifacts")
        if not isinstance(step_artifacts, Mapping) or ref.get("artifact_digest") != _sha256_json(
            step_artifacts
        ):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        output_bundle = _mapping(runtime_step.get("output_bundle"))
        fields = output_bundle.get("fields")
        if not isinstance(fields, list):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        bundle_path = ref.get("bundle_path")
        if not isinstance(bundle_path, str) or not bundle_path:
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        payload = _json_value_from_workspace(workspace, bundle_path)
        structured_output = _mapping(_mapping(point_policy.get("evidence_requirements")).get("structured_output"))
        if ref.get("bundle_path_ref") != structured_output.get("bundle_path_ref"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if structured_output.get("declared_target_only"):
            declared_path = output_bundle.get("path")
            if isinstance(declared_path, str) and "${" not in declared_path and bundle_path != declared_path:
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if ref.get("contract_digest") != _sha256_json({"path": bundle_path, "fields": fields}):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if ref.get("payload_digest") != _sha256_json(payload):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        if effect_kind == "provider":
            if ref.get("prompt_input_contract_digest") != _provider_prompt_input_contract_digest(runtime_step):
                raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.structured_output_invalid)
        return

    if effect_kind == "call":
        if step_state.get("status") != "completed":
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        workflow_call = _mapping(_mapping(point_policy.get("evidence_requirements")).get("workflow_call"))
        validation_executor = type(
            "CheckpointValidationExecutor",
            (),
            {"state_manager": type("CheckpointValidationStateManager", (), {"state": state})()},
        )()
        call_debug = _workflow_call_debug_payload(
            validation_executor,
            point=expected_point,
            step_state=step_state,
            point_policy=point_policy,
        )
        if ref.get("call_frame_id") != call_debug.get("call_frame_id"):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("callee_workflow") != (workflow_call.get("callee_workflow") or call_debug.get("import_alias")):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        workflow_file = call_debug.get("workflow_file")
        if not isinstance(workflow_file, str) or not workflow_file:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("workflow_file") != workflow_file:
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("target_dsl_version") != _workflow_version_policy_from_workspace(workspace, workflow_file):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("callee_checksum") != _file_digest_from_workspace(workspace, workflow_file):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("input_digest") != _sha256_json(_mapping(call_debug.get("bound_inputs"))):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        if ref.get("terminal_result_digest") != _sha256_json(_mapping(call_debug.get("workflow_outputs"))):
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        return

    if effect_kind == "materialize_view":
        if step_state.get("status") != "completed":
            raise ValueError(DIAGNOSTIC_CODES.completed_effect_invalid)
        evidence_record = _json_object_from_workspace(workspace, str(ref.get("evidence_path")))
        if ref.get("renderer_id") != evidence_record.get("renderer_id"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("renderer_version") != evidence_record.get("renderer_version"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("value_digest") != evidence_record.get("value_digest"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("view_digest") != evidence_record.get("view_digest"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("evidence_key") != evidence_record.get("evidence_key"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("target_path") != evidence_record.get("target_path"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("view_digest") != _file_digest_from_workspace(workspace, str(ref.get("target_path"))):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        if ref.get("durability_mode") != _materialized_view_durability_mode(point_policy):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.materialized_view_mismatch)
        return

    if effect_kind == "resource_transition":
        transition = _mapping(_mapping(point_policy.get("evidence_requirements")).get("transition"))
        if ref.get("transition_identity") != transition.get("transition_identity"):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing)
        if ref.get("audit_digest") != _file_digest_from_workspace(workspace, str(ref.get("audit_path"))):
            raise ValueError(EFFECT_POLICY_DIAGNOSTIC_CODES.transition_audit_missing)
        if transition_checkpoint_evidence_from_effect_ref(ref) is not None:
            return
        return


def validate_checkpoint_record(
    record: Mapping[str, Any],
    *,
    expected_point: Mapping[str, Any] | None = None,
    expected_program_identity: Mapping[str, Any] | None = None,
) -> None:
    if record.get("schema_version") != CHECKPOINT_RECORD_SCHEMA_VERSION:
        raise ValueError(DIAGNOSTIC_CODES.schema_invalid)
    validity_envelope = _mapping(record.get("validity_envelope"))
    binding_schema_digest = record.get("binding_schema_digest") or validity_envelope.get("binding_schema_digest")
    storage_allocation_id = record.get("storage_allocation_id") or validity_envelope.get("storage_allocation_id")
    origin_key = record.get("origin_key") or validity_envelope.get("source_map_origin_key")
    if not binding_schema_digest:
        raise ValueError(DIAGNOSTIC_CODES.binding_schema_mismatch)
    if not storage_allocation_id:
        raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
    if not origin_key:
        raise ValueError(DIAGNOSTIC_CODES.source_lineage_mismatch)
    provisional_policy = record.get("provisional_policy")
    if provisional_policy is not None and provisional_policy not in PROVISIONAL_POLICIES:
        raise ValueError(DIAGNOSTIC_CODES.effect_policy_unknown)
    if expected_program_identity is not None:
        if canonical_json_dumps(_mapping(record.get("program_identity"))) != canonical_json_dumps(expected_program_identity):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
    if expected_point is not None:
        validate_checkpoint_point_payload(expected_point)
        if record.get("checkpoint_id") != expected_point.get("checkpoint_id"):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        if record.get("program_point_id") != expected_point.get("program_point_id"):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        if record.get("point_kind") != expected_point.get("point_kind"):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        if binding_schema_digest != checkpoint_record_binding_schema_digest(expected_point):
            raise ValueError(DIAGNOSTIC_CODES.binding_schema_mismatch)
        if storage_allocation_id != _mapping(expected_point.get("storage")).get("allocation_id"):
            raise ValueError(DIAGNOSTIC_CODES.storage_role_invalid)
        if origin_key != expected_point.get("origin_key"):
            raise ValueError(DIAGNOSTIC_CODES.source_lineage_mismatch)
        policy_summary = describe_checkpoint_record_policy(record, expected_point=expected_point)
        if policy_summary.get("diagnostic") is not None:
            raise ValueError(str(policy_summary["diagnostic"]))
        if policy_summary.get("record_policy_status") == "policy_enforced":
            _validate_completed_effect_refs(record, expected_point=expected_point)
    restore_payload = record.get("restore_payload")
    if restore_payload is not None:
        validate_restore_payload(_mapping(restore_payload), expected_origin_key=str(origin_key))


def validate_checkpoint_index_update(
    *,
    checkpoint_id: str,
    existing_records: Sequence[Mapping[str, Any]],
    candidate_record: Mapping[str, Any],
) -> None:
    candidate_record_id = candidate_record.get("record_id")
    candidate_frame_identity = candidate_record.get("frame_identity")
    for existing in existing_records:
        if existing.get("record_id") != candidate_record_id:
            continue
        if existing.get("frame_identity") != candidate_frame_identity:
            raise ValueError(
                f"{DIAGNOSTIC_CODES.record_collision}:{checkpoint_id}:{candidate_record_id}"
                )


def _checkpoint_role(value: str) -> GeneratedPathSemanticRole:
    if value == GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD.value:
        return GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD
    if value == GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_INDEX.value:
        return GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_INDEX
    raise ValueError(f"unsupported checkpoint semantic role: {value}")


def allocate_checkpoint_storage(
    *,
    workflow_name: str,
    checkpoint_id: str,
    semantic_role: str,
    storage_scope: str | None = None,
) -> GeneratedPathAllocation:
    role = _checkpoint_role(semantic_role)
    if role == GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD:
        relative_path = (
            f".orchestrate/runs/${{runtime.run_id}}/workflow_lisp/checkpoints/records/{checkpoint_id}"
        )
        resume_scope = (
            GeneratedPathResumeScope(storage_scope)
            if isinstance(storage_scope, str) and storage_scope
            else GeneratedPathResumeScope.STEP_VISIT
        )
    else:
        relative_path = (
            f".orchestrate/runs/${{runtime.run_id}}/workflow_lisp/checkpoints/index/{checkpoint_id}.json"
        )
        resume_scope = GeneratedPathResumeScope.RUN
    allocation = StateLayout.allocate(
        GeneratedPathAllocationRequest(
            owner="workflow_lisp.lexical_checkpoints",
            workflow_name=workflow_name,
            semantic_role=role,
            privacy=GeneratedPathPrivacy.RUNTIME_SIDECAR,
            resume_scope=resume_scope,
            stable_identity=checkpoint_id,
            projection_hints={"path_template": relative_path},
        )
    )
    return allocation


def _runtime_plan_points_by_step_id(runtime_plan: Any) -> dict[str, Any]:
    points_by_step_id: dict[str, Any] = {}
    for point in getattr(runtime_plan, "lexical_checkpoint_points", ()):
        step_id = _point_field(point, "step_id")
        if isinstance(step_id, str) and step_id:
            if step_id in points_by_step_id:
                raise ValueError(
                    f"duplicate lexical checkpoint step id: {step_id}"
                )
            points_by_step_id[step_id] = point
    return points_by_step_id


def _program_identity(executor: Any, point: Any) -> Mapping[str, Any]:
    provenance = getattr(getattr(executor, "loaded_bundle", None), "provenance", None)
    workflow_path = getattr(provenance, "workflow_path", None)
    return checkpoint_runtime_program_identity(
        state_manager=executor.state_manager,
        runtime_plan=executor.runtime_plan,
        workflow_path=workflow_path if isinstance(workflow_path, Path) else None,
        executable_ir=getattr(executor, "executable_ir", None),
    )


def _q3_provider_configurations(
    executable_ir: Any,
) -> tuple[dict[str, Any], ...]:
    if executable_ir is None:
        return ()
    from orchestrator.workflow.executable_ir import ProviderStepConfig
    from orchestrator.workflow.prompt_fragment_contract import (
        PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION,
        PROMPT_ATTEMPT_IDENTITY_VERSION,
        serialize_compiler_prompt_attempt_binding_plan,
        validate_compiler_prompt_attempt_pair,
    )
    from orchestrator.workflow.provider_phased_delivery.models import (
        partition_provider_call_policy,
    )

    target_dsl_version = getattr(executable_ir, "version", None)
    nodes = _mapping(getattr(executable_ir, "nodes", {}))
    configurations: list[dict[str, Any]] = []
    for node_id in sorted(nodes):
        node = nodes[node_id]
        config = getattr(node, "execution_config", None)
        if not isinstance(config, ProviderStepConfig):
            continue
        validate_compiler_prompt_attempt_pair(
            config.prompt_attempt_identity_version,
            config.compiler_prompt_attempt_binding_plan,
            fragment_contract=config.compiler_prompt_fragment_contract,
            dependency_contract=config.compiler_prompt_dependency_contract,
            typed_prompt_inputs=config.typed_prompt_inputs,
            target_dsl_version=(
                target_dsl_version
                if isinstance(target_dsl_version, str)
                else None
            ),
        )
        try:
            provider_policy, runtime_policy = partition_provider_call_policy(
                config.provider_call_policy or {}
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "provider_phased_delivery_carriage_mismatch"
            ) from exc
        if runtime_policy is None:
            if (
                config.prompt_attempt_identity_version
                == PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION
            ):
                raise ValueError(
                    "provider_phased_delivery_carriage_mismatch"
                )
            persisted_policy = None
        else:
            if (
                not isinstance(target_dsl_version, str)
                or not _target_dsl_at_least(target_dsl_version, (2, 23))
            ):
                raise ValueError(
                    "provider_phased_delivery_carriage_mismatch"
                )
            if (
                runtime_policy.delivery == "phased"
                and config.prompt_attempt_identity_version
                != PHASED_PROMPT_ATTEMPT_IDENTITY_VERSION
            ):
                raise ValueError(
                    "provider_phased_delivery_carriage_mismatch"
                )
            if (
                runtime_policy.delivery == "composed"
                and config.prompt_attempt_identity_version
                not in {None, PROMPT_ATTEMPT_IDENTITY_VERSION}
            ):
                raise ValueError(
                    "provider_phased_delivery_carriage_mismatch"
                )
            persisted_policy = {}
            if provider_policy.model is not None:
                persisted_policy["model"] = provider_policy.model
            if provider_policy.effort is not None:
                persisted_policy["effort"] = provider_policy.effort
            persisted_policy["delivery"] = runtime_policy.delivery
            if runtime_policy.materialization_attempts is not None:
                persisted_policy["materialization_attempts"] = (
                    runtime_policy.materialization_attempts
                )
        if (
            config.prompt_attempt_identity_version is None
            and persisted_policy is None
        ):
            continue
        if (
            config.prompt_attempt_identity_version is not None
            and config.compiler_prompt_attempt_binding_plan is None
        ):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        configuration = {
            "node_id": _require_non_empty_string(
                getattr(node, "node_id", None),
                DIAGNOSTIC_CODES.program_identity_mismatch,
            ),
            "step_id": _require_non_empty_string(
                getattr(node, "step_id", None),
                DIAGNOSTIC_CODES.program_identity_mismatch,
            ),
        }
        if config.prompt_attempt_identity_version is not None:
            configuration["prompt_attempt_identity_version"] = (
                config.prompt_attempt_identity_version
            )
            configuration["compiler_prompt_attempt_binding_plan"] = (
                serialize_compiler_prompt_attempt_binding_plan(
                    config.compiler_prompt_attempt_binding_plan
                )
            )
        if persisted_policy is not None:
            configuration["provider_call_policy"] = persisted_policy
        configurations.append(configuration)
    return tuple(configurations)


def checkpoint_runtime_program_identity(
    *,
    state_manager: Any,
    runtime_plan: Any,
    workflow_path: Path | None = None,
    executable_ir: Any = None,
) -> Mapping[str, Any]:
    workflow_name = str(getattr(runtime_plan, "workflow_name", "") or "")
    source_module_digest = (
        state_manager.calculate_checksum(workflow_path)
        if isinstance(workflow_path, Path) and workflow_path.exists()
        else _digest("source", workflow_name)
    )
    runtime_points = tuple(
        getattr(runtime_plan, "lexical_checkpoint_points", ())
    )
    required_component_nodes: dict[
        str,
        tuple[str, str, str | None, str | None],
    ] = {}
    for node in _mapping(getattr(runtime_plan, "nodes", {})).values():
        node_kind = _point_field(node, "kind")
        is_peer = (
            node_kind == "provider_peer_group"
            or _point_field(node, "provider_peer_group") is not None
        )
        is_run_ref = (
            node_kind == "run_ref"
            or _point_field(node, "run_ref_config_digest") is not None
        )
        is_trial = (
            node_kind == "trial"
            or _point_field(node, "trial_config_digest") is not None
            or _point_field(node, "trial_result_contract_digest") is not None
        )
        matched_kinds = sum((is_peer, is_run_ref, is_trial))
        if matched_kinds == 0:
            continue
        if matched_kinds != 1:
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        step_id = _point_field(node, "step_id")
        node_id = _point_field(node, "node_id")
        if (
            not isinstance(step_id, str)
            or not step_id
            or not isinstance(node_id, str)
            or not node_id
            or step_id in required_component_nodes
        ):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        component_kind = (
            "provider_peer_group"
            if is_peer
            else "run_ref"
            if is_run_ref
            else "trial"
        )
        expected_component_digest = None
        expected_result_contract_digest = None
        if is_run_ref:
            expected_component_digest = _point_field(
                node,
                "run_ref_config_digest",
            )
            if not isinstance(expected_component_digest, str) or re.fullmatch(
                r"sha256:[0-9a-f]{64}",
                expected_component_digest,
            ) is None:
                raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        elif is_trial:
            expected_component_digest = _point_field(
                node,
                "trial_config_digest",
            )
            expected_result_contract_digest = _point_field(
                node,
                "trial_result_contract_digest",
            )
            for digest in (
                expected_component_digest,
                expected_result_contract_digest,
            ):
                if not isinstance(digest, str) or re.fullmatch(
                    r"sha256:[0-9a-f]{64}",
                    digest,
                ) is None:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    )
        required_component_nodes[step_id] = (
            node_id,
            component_kind,
            expected_component_digest,
            expected_result_contract_digest,
        )
    observed_required_points: dict[str, list[Any]] = {
        step_id: [] for step_id in required_component_nodes
    }
    for point in runtime_points:
        step_id = _point_field(point, "step_id")
        if step_id in observed_required_points:
            observed_required_points[step_id].append(point)
    for step_id, points in observed_required_points.items():
        (
            expected_node_id,
            component_kind,
            expected_component_digest,
            expected_result_contract_digest,
        ) = (
            required_component_nodes[step_id]
        )
        if (
            len(points) != 1
            or _point_field(points[0], "node_id")
            != expected_node_id
        ):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        observed_component_digest = _checkpoint_identity_component_digest(
            points[0],
            required=True,
        )
        if (
            expected_component_digest is not None
            and observed_component_digest != expected_component_digest
        ):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        observed_identity = _mapping(
            (_point_details(points[0]) or _mapping(points[0])).get(
                "executable_identity"
            )
        )
        if (
            expected_result_contract_digest is not None
            and observed_identity.get("trial_result_contract_digest")
            != expected_result_contract_digest
        ):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        if expected_component_digest is not None and executable_ir is not None:
            executable_nodes = _mapping(
                getattr(executable_ir, "nodes", {})
            )
            executable_node = executable_nodes.get(expected_node_id)
            execution_config = getattr(
                executable_node,
                "execution_config",
                None,
            )
            if component_kind == "run_ref":
                from orchestrator.workflow.executable_ir import RunRefStepConfig
                from orchestrator.workflow.run_ref.config import (
                    validate_run_ref_static_config_authority,
                )

                if type(execution_config) is not RunRefStepConfig:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    )
                try:
                    validate_run_ref_static_config_authority(
                        execution_config.run_ref
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    ) from exc
                if execution_config.run_ref.digest != expected_component_digest:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    )
            elif component_kind == "trial":
                from orchestrator.workflow.executable_ir import TrialStepConfig
                from orchestrator.workflow.trial.config import (
                    validate_trial_static_config_authority,
                )

                if type(execution_config) is not TrialStepConfig:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    )
                try:
                    validate_trial_static_config_authority(
                        execution_config.trial
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    ) from exc
                if (
                    execution_config.trial.digest
                    != expected_component_digest
                    or execution_config.trial.result_digest
                    != expected_result_contract_digest
                ):
                    raise ValueError(
                        DIAGNOSTIC_CODES.program_identity_mismatch
                    )
    lexical_points = [
        _runtime_program_identity_point(
            point,
            component_required=(
                _point_field(point, "step_id")
                in required_component_nodes
            ),
        )
        for point in runtime_points
    ]
    provider_configurations = _q3_provider_configurations(executable_ir)
    executable_projection = {
        "ordered_node_ids": list(
            getattr(runtime_plan, "ordered_node_ids", ())
        ),
        "lexical_checkpoint_points": lexical_points,
    }
    semantic_projection = {
        "workflow_name": workflow_name,
        "resume_checkpoints": [
            {
                "checkpoint_kind": checkpoint.checkpoint_kind,
                "node_id": checkpoint.node_id,
                "step_id": checkpoint.step_id,
            }
            for checkpoint in getattr(runtime_plan, "resume_checkpoints", ())
        ],
        "lexical_checkpoint_points": lexical_points,
    }
    if provider_configurations:
        serialized_configurations = [
            dict(configuration)
            for configuration in provider_configurations
        ]
        executable_projection["provider_configurations"] = (
            serialized_configurations
        )
        semantic_projection["provider_configurations"] = (
            serialized_configurations
        )
    executable_ir_digest = _sha256_json(executable_projection)
    semantic_ir_digest = _sha256_json(semantic_projection)
    lowering_schema_version = "wcc_m4"
    lexical_checkpoint_points = getattr(runtime_plan, "lexical_checkpoint_points", ())
    if lexical_checkpoint_points:
        first_point = lexical_checkpoint_points[0]
        lowering_schema_version = str(
            _mapping(_point_details(first_point).get("runtime_program_identity")).get("lowering_schema_version", "wcc_m4")
        )
    identity = {
        "workflow_name": workflow_name,
        "lowering_schema_version": lowering_schema_version,
        "source_module_digest": source_module_digest,
        "executable_ir_digest": executable_ir_digest,
        "semantic_ir_digest": semantic_ir_digest,
        "checkpoint_schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
    }
    if provider_configurations:
        identity["provider_configurations"] = [
            dict(configuration)
            for configuration in provider_configurations
        ]
    return identity


def _binding_schema_digest(point: Any) -> str:
    return checkpoint_record_binding_schema_digest(_point_payload(point))


def _effect_policy_digest(point: Any) -> str:
    return checkpoint_record_effect_policy_digest(_point_payload(point))


def resolve_checkpoint_record_family_path(
    *,
    state_manager: Any,
    workflow_name: str,
    checkpoint_id: str,
    storage_scope: str | None = None,
) -> Path:
    allocation = allocate_checkpoint_storage(
        workflow_name=workflow_name,
        checkpoint_id=checkpoint_id,
        semantic_role=GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD.value,
        storage_scope=storage_scope,
    )
    rendered = allocation.concrete_path_template.replace("${runtime.run_id}", state_manager.run_id)
    return state_manager.workspace / rendered


def resolve_checkpoint_record_path(
    *,
    state_manager: Any,
    workflow_name: str,
    checkpoint_id: str,
    record_id: str,
    storage_scope: str | None = None,
) -> Path:
    return resolve_checkpoint_record_family_path(
        state_manager=state_manager,
        workflow_name=workflow_name,
        checkpoint_id=checkpoint_id,
        storage_scope=storage_scope,
    ) / f"{record_id}.json"


def resolve_checkpoint_index_path(
    *,
    state_manager: Any,
    workflow_name: str,
    checkpoint_id: str,
) -> Path:
    allocation = allocate_checkpoint_storage(
        workflow_name=workflow_name,
        checkpoint_id=checkpoint_id,
        semantic_role=GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_INDEX.value,
    )
    rendered = allocation.concrete_path_template.replace("${runtime.run_id}", state_manager.run_id)
    return state_manager.workspace / rendered


def resolve_runtime_shadow_report_path(*, state_manager: Any) -> Path:
    return state_manager.workflow_lisp_checkpoint_shadow_report_path()


def _relative_path(state_manager: Any, path: Path) -> str:
    try:
        return path.relative_to(state_manager.workspace).as_posix()
    except ValueError:
        return path.as_posix()


def _load_json_object(state_manager: Any, path: Path) -> dict[str, Any] | None:
    payload = state_manager.read_runtime_sidecar_json(path)
    if payload is None:
        return None
    if not isinstance(payload, dict):
        raise ValueError(f"checkpoint sidecar must decode to an object: {path}")
    return payload


def _initialize_shadow_report(
    *,
    workflow_name: str,
    point_count: int,
) -> dict[str, Any]:
    return {
        "schema_version": CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION,
        "workflow_name": workflow_name,
        "status": "pass",
        "checked_points": point_count,
        "checked_records": 0,
        "missing_points": [],
        "invalid_records": [],
        "stale_records": [],
        "diagnostics": [],
    }


def _write_failed_shadow_report(
    *,
    state_manager: Any,
    workflow_name: str,
    point_count: int,
    diagnostic: str,
) -> None:
    report_path = resolve_runtime_shadow_report_path(state_manager=state_manager)
    report = _load_json_object(state_manager, report_path) or _initialize_shadow_report(
        workflow_name=workflow_name,
        point_count=point_count,
    )
    report["status"] = "fail"
    diagnostics = report.setdefault("diagnostics", [])
    if isinstance(diagnostics, list):
        diagnostics.append(diagnostic)
    invalid_records = report.setdefault("invalid_records", [])
    if isinstance(invalid_records, list):
        invalid_records.append(diagnostic)
    state_manager.write_runtime_sidecar_json(report_path, report)


def emit_runtime_shadow_record(
    *,
    executor: Any,
    step_id: str,
    execution_index: int,
    visit_count: int,
    loop_iteration: int | None = None,
    call_frame_id: str | None = None,
    runtime_step_id: str | None = None,
    committed_step_state: Mapping[str, Any] | None = None,
) -> Mapping[str, Any] | None:
    runtime_plan = getattr(executor, "runtime_plan", None)
    if runtime_plan is None:
        return None
    point = _runtime_plan_points_by_step_id(runtime_plan).get(step_id)
    if point is None:
        return None

    workflow_name = str(_point_field(point, "workflow_name") or runtime_plan.workflow_name or "")
    point_count = len(getattr(runtime_plan, "lexical_checkpoint_points", ()))
    try:
        if not isinstance(call_frame_id, str) or not call_frame_id:
            candidate_frame_id = getattr(executor.state_manager, "frame_id", None)
            if isinstance(candidate_frame_id, str) and candidate_frame_id:
                call_frame_id = candidate_frame_id
        point_payload = _point_payload(point)
        validate_checkpoint_point_payload(point_payload)
        if workflow_name != getattr(runtime_plan, "workflow_name", ""):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
        if _point_success_checkpoint_is_suppressed(executor, point):
            return None

        checkpoint_id = str(point_payload.get("checkpoint_id") or "")
        program_point_id = str(point_payload.get("program_point_id") or "")
        point_kind = str(point_payload.get("point_kind") or "")
        storage_scope = _mapping(point_payload.get("storage")).get("resume_scope")

        record_allocation = allocate_checkpoint_storage(
            workflow_name=workflow_name,
            checkpoint_id=checkpoint_id,
            semantic_role=GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_RECORD.value,
            storage_scope=storage_scope,
        )
        index_allocation = allocate_checkpoint_storage(
            workflow_name=workflow_name,
            checkpoint_id=checkpoint_id,
            semantic_role=GeneratedPathSemanticRole.LEXICAL_CHECKPOINT_INDEX.value,
        )
        record_id = derive_record_id(
            checkpoint_id=checkpoint_id,
            run_id=executor.state_manager.run_id,
            execution_index=execution_index,
            visit_count=visit_count,
            loop_iteration=loop_iteration,
            call_frame_id=call_frame_id,
        )
        record_path = resolve_checkpoint_record_path(
            state_manager=executor.state_manager,
            workflow_name=workflow_name,
            checkpoint_id=checkpoint_id,
            record_id=record_id,
            storage_scope=storage_scope,
        )
        index_path = resolve_checkpoint_index_path(
            state_manager=executor.state_manager,
            workflow_name=workflow_name,
            checkpoint_id=checkpoint_id,
        )

        frame_identity = {
            "execution_index": execution_index,
            "visit_count": visit_count,
            "loop_iteration": loop_iteration,
            "call_frame_id": call_frame_id,
        }
        if runtime_step_id is not None:
            if not runtime_step_id:
                raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)
            frame_identity["runtime_step_id"] = runtime_step_id
        record = {
            "schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
            "checkpoint_id": checkpoint_id,
            "program_point_id": program_point_id,
            "point_kind": point_kind,
            "record_id": record_id,
            "run_id": executor.state_manager.run_id,
            "frame_identity": frame_identity,
            "program_identity": _program_identity(executor, point),
            "validity_envelope": {
                "binding_schema_digest": _binding_schema_digest(point),
                "effect_policy_digest": _effect_policy_digest(point),
                "completed_effect_refs_digest": None,
                "source_map_origin_key": _point_field(point, "origin_key"),
                "storage_allocation_id": record_allocation.allocation_id,
            },
            "binding_schema_digest": _binding_schema_digest(point),
            "storage_allocation_id": record_allocation.allocation_id,
            "origin_key": point_payload.get("origin_key"),
            "provisional_policy": "shadow_record_only",
            "typed_binding_refs": [],
            "active_variant_proofs": [],
            "loop_frame_state": (
                {"iteration": loop_iteration}
                if loop_iteration is not None
                and runtime_step_id is None
                else None
            ),
            "pending_effect_policy": {
                "effect_kind": _point_details(point).get("step_kind", point_kind),
                "policy_status": "shadow_record_only",
            },
            "completed_effect_refs": [],
            "resource_version_observations": [],
            "shadow_validation": {
                "status": "pass",
                "diagnostics": [],
            },
        }
        completed_effect_refs = collect_completed_effect_refs(
            executor,
            point=point,
            committed_step_state=committed_step_state,
        )
        record["completed_effect_refs"] = [dict(ref) for ref in completed_effect_refs]
        restore_payload = capture_restore_payload(
            executor=executor,
            point=point,
            execution_index=execution_index,
            loop_iteration=loop_iteration,
            completed_effect_refs=completed_effect_refs,
        )
        if restore_payload is not None:
            record["restore_payload"] = dict(restore_payload)
        if (
            restore_payload is not None
            and isinstance(record.get("restore_payload"), Mapping)
            and len(completed_effect_refs) == 1
            and _mapping(completed_effect_refs[0]).get("effect_kind") == "resource_transition"
        ):
            transition_ref = _mapping(completed_effect_refs[0])
            restore_payload_record = dict(_mapping(record["restore_payload"]))
            bindings = _sequence(restore_payload_record.get("bindings"))
            if any(
                _mapping(binding).get("source_step_id") == point_payload.get("step_id")
                for binding in bindings
            ):
                observation = build_resource_observation(
                    resource_id=str(transition_ref.get("resource_id") or ""),
                    resource_kind=str(transition_ref.get("resource_kind") or ""),
                    observed_version=str(transition_ref.get("resource_version") or ""),
                    transition_identity=str(transition_ref.get("transition_identity") or ""),
                    checkpoint_id=checkpoint_id,
                    program_point_id=program_point_id,
                    source_step_id=str(point_payload.get("step_id") or ""),
                    source_map_origin_key=str(point_payload.get("origin_key") or ""),
                    audit_path=str(transition_ref.get("audit_path") or ""),
                    audit_digest=str(transition_ref.get("audit_digest") or ""),
                )
                restore_payload_record["resource_observations"] = [observation]
                record["restore_payload"] = restore_payload_record
        record["validity_envelope"]["completed_effect_refs_digest"] = _completed_effect_refs_digest(
            tuple(_mapping(ref) for ref in completed_effect_refs)
        )
        validate_checkpoint_record(
            record,
            expected_point=point_payload,
            expected_program_identity=_program_identity(executor, point),
        )

        existing_record = _load_json_object(executor.state_manager, record_path)
        if existing_record is not None and canonical_json_dumps(existing_record) != canonical_json_dumps(record):
            raise ValueError(f"{DIAGNOSTIC_CODES.record_collision}:{checkpoint_id}:{record_id}")

        index_payload = _load_json_object(executor.state_manager, index_path) or {
            "workflow_name": workflow_name,
            "checkpoint_id": checkpoint_id,
            "program_point_id": program_point_id,
            "storage_allocation_id": index_allocation.allocation_id,
            "records": [],
        }
        existing_records = index_payload.get("records", [])
        if not isinstance(existing_records, list):
            raise ValueError("lexical checkpoint index records must be a list")
        validate_checkpoint_index_update(
            checkpoint_id=checkpoint_id,
            existing_records=tuple(existing_records),
            candidate_record={
                "record_id": record_id,
                "frame_identity": frame_identity,
            },
        )

        appended = not any(
            isinstance(existing, Mapping)
            and existing.get("record_id") == record_id
            and existing.get("frame_identity") == frame_identity
            for existing in existing_records
        )
        if appended:
            existing_records.append(
                {
                    "record_id": record_id,
                    "program_point_id": program_point_id,
                    "point_kind": point_kind,
                    "frame_identity": frame_identity,
                    "record_path": _relative_path(executor.state_manager, record_path),
                }
            )

        if existing_record is None:
            executor.state_manager.write_runtime_sidecar_json(record_path, record)
        if appended:
            executor.state_manager.write_runtime_sidecar_json(index_path, index_payload)

        report_path = resolve_runtime_shadow_report_path(state_manager=executor.state_manager)
        report = _load_json_object(executor.state_manager, report_path) or _initialize_shadow_report(
            workflow_name=workflow_name,
            point_count=point_count,
        )
        report["checked_points"] = point_count
        if appended:
            report["checked_records"] = int(report.get("checked_records", 0)) + 1
        executor.state_manager.write_runtime_sidecar_json(report_path, report)
        return record
    except Exception as exc:
        _write_failed_shadow_report(
            state_manager=executor.state_manager,
            workflow_name=workflow_name or getattr(runtime_plan, "workflow_name", ""),
            point_count=point_count,
            diagnostic=str(exc),
        )
        raise


def assert_runtime_shadow_emission(
    *,
    executor: Any,
    state_manager: Any,
    inputs: Mapping[str, Any],
    expected_record_kinds: set[str],
) -> None:
    loaded_bundle = getattr(executor, "loaded_bundle", None)
    provenance = getattr(loaded_bundle, "provenance", None)
    workflow_path = getattr(provenance, "workflow_path", None)
    if not isinstance(workflow_path, Path):
        raise AssertionError("loaded bundle provenance must expose workflow_path")
    if state_manager.state is None:
        state_manager.initialize(str(workflow_path), bound_inputs=dict(inputs))

    final_state = executor.execute(on_error="stop")
    final_status = final_state.get("status")
    if not is_run_terminal(final_status, raise_on_unhashable=True):
        raise AssertionError(f"unexpected workflow terminal status: {final_status}")

    observed_kinds: set[str] = set()
    observed_records: list[Mapping[str, Any]] = []
    for point in getattr(executor.runtime_plan, "lexical_checkpoint_points", ()):
        index_path = resolve_checkpoint_index_path(
            state_manager=state_manager,
            workflow_name=str(_point_field(point, "workflow_name")),
            checkpoint_id=str(_point_field(point, "checkpoint_id")),
        )
        index_payload = _load_json_object(state_manager, index_path)
        if index_payload is None:
            continue
        records = index_payload.get("records", [])
        if not isinstance(records, list):
            raise AssertionError(f"checkpoint index must store a list of records: {index_path}")
        for entry in records:
            if not isinstance(entry, Mapping):
                raise AssertionError(f"checkpoint index entry must be an object: {index_path}")
            record_path = state_manager.workspace / str(entry["record_path"])
            record = _load_json_object(state_manager, record_path)
            if record is None:
                raise AssertionError(f"checkpoint record missing: {record_path}")
            validate_checkpoint_record(
                record,
                expected_point=_point_payload(point),
                expected_program_identity=_program_identity(executor, point),
            )
            observed_records.append(record)
            observed_kinds.add(str(entry.get("point_kind") or _point_field(point, "point_kind")))

    if not expected_record_kinds.issubset(observed_kinds):
        raise AssertionError(
            f"missing checkpoint record kinds: expected {sorted(expected_record_kinds)}, got {sorted(observed_kinds)}"
        )

    if not any(
        isinstance(record.get("frame_identity"), Mapping)
        and isinstance(record["frame_identity"].get("call_frame_id"), str)
        and record["frame_identity"].get("call_frame_id")
        for record in observed_records
    ):
        raise AssertionError("expected at least one call-frame-qualified checkpoint record")

    report_path = resolve_runtime_shadow_report_path(state_manager=state_manager)
    report = _load_json_object(state_manager, report_path)
    if report is None:
        raise AssertionError("runtime shadow report was not written")
    if report.get("status") != "pass":
        raise AssertionError(f"runtime shadow report failed: {report}")
    if int(report.get("checked_records", 0)) < len(observed_records):
        raise AssertionError("runtime shadow report under-counted emitted records")
