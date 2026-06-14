"""Lexical checkpoint schema helpers and private storage-role allocation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from orchestrator.workflow.state_layout import (
    GeneratedPathAllocation,
    GeneratedPathAllocationRequest,
    GeneratedPathPrivacy,
    GeneratedPathResumeScope,
    GeneratedPathSemanticRole,
    StateLayout,
)
from orchestrator.workflow_lisp.lexical_checkpoint_restore import (
    capture_restore_payload,
    validate_restore_payload,
    validate_restore_point_metadata,
)


CHECKPOINT_RECORD_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint.v1"
CHECKPOINT_POINTS_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_points.v1"
CHECKPOINT_SHADOW_REPORT_SCHEMA_VERSION = "workflow_lisp_lexical_checkpoint_shadow_report.v1"

POINT_KINDS = frozenset({"effect_boundary", "loop_back_edge"})
PROVISIONAL_POLICIES = frozenset({"shadow_record_only"})


@dataclass(frozen=True)
class CheckpointDiagnosticCodes:
    schema_invalid: str = "lexical_checkpoint_schema_invalid"
    program_identity_mismatch: str = "lexical_checkpoint_program_identity_mismatch"
    source_map_missing: str = "lexical_checkpoint_source_map_missing"
    binding_schema_mismatch: str = "lexical_checkpoint_binding_schema_mismatch"
    storage_role_invalid: str = "lexical_checkpoint_storage_role_invalid"
    source_lineage_mismatch: str = "lexical_checkpoint_source_lineage_mismatch"
    effect_policy_unknown: str = "lexical_checkpoint_effect_policy_unknown"
    used_as_semantic_authority: str = "lexical_checkpoint_used_as_semantic_authority"
    record_collision: str = "lexical_checkpoint_record_collision"


DIAGNOSTIC_CODES = CheckpointDiagnosticCodes()


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha256_text(value: object) -> str:
    return f"sha256:{hashlib.sha256(str(value).encode('utf-8')).hexdigest()}"


def _sha256_json(value: Any) -> str:
    return _sha256_text(canonical_json_dumps(value))


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
        if effect_policy.get("policy_status") not in PROVISIONAL_POLICIES:
            raise ValueError(DIAGNOSTIC_CODES.effect_policy_unknown)
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
    payload = _mapping(point.get("effect_boundary")) if point.get("point_kind") == "effect_boundary" else _mapping(
        point.get("loop_back_edge")
    )
    policy_status = payload.get("policy_status", "shadow_record_only")
    if policy_status not in PROVISIONAL_POLICIES:
        raise ValueError(DIAGNOSTIC_CODES.effect_policy_unknown)
    return _sha256_json(
        {
            "point_kind": point.get("point_kind"),
            "policy_status": policy_status,
            "step_kind": point.get("step_kind"),
            "effect_kind": payload.get("effect_kind"),
            "boundary_kind": payload.get("boundary_kind"),
            "loop_name": payload.get("loop_name"),
        }
    )


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
    if record.get("provisional_policy") not in PROVISIONAL_POLICIES:
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
        effect_policy_digest = validity_envelope.get("effect_policy_digest")
        if effect_policy_digest != checkpoint_record_effect_policy_digest(expected_point):
            raise ValueError(DIAGNOSTIC_CODES.effect_policy_unknown)
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
            points_by_step_id[step_id] = point
    return points_by_step_id


def _program_identity(executor: Any, point: Any) -> Mapping[str, Any]:
    provenance = getattr(getattr(executor, "loaded_bundle", None), "provenance", None)
    workflow_path = getattr(provenance, "workflow_path", None)
    return checkpoint_runtime_program_identity(
        state_manager=executor.state_manager,
        runtime_plan=executor.runtime_plan,
        workflow_path=workflow_path if isinstance(workflow_path, Path) else None,
    )


def checkpoint_runtime_program_identity(
    *,
    state_manager: Any,
    runtime_plan: Any,
    workflow_path: Path | None = None,
) -> Mapping[str, Any]:
    workflow_name = str(getattr(runtime_plan, "workflow_name", "") or "")
    source_module_digest = (
        state_manager.calculate_checksum(workflow_path)
        if isinstance(workflow_path, Path) and workflow_path.exists()
        else _digest("source", workflow_name)
    )
    lexical_points = [
        {
            "checkpoint_id": _point_field(point, "checkpoint_id"),
            "program_point_id": _point_field(point, "program_point_id"),
            "point_kind": _point_field(point, "point_kind"),
            "step_id": _point_field(point, "step_id"),
        }
        for point in getattr(runtime_plan, "lexical_checkpoint_points", ())
    ]
    executable_ir_digest = _sha256_json(
        {
            "ordered_node_ids": list(getattr(runtime_plan, "ordered_node_ids", ())),
            "lexical_checkpoint_points": lexical_points,
        }
    )
    semantic_ir_digest = _sha256_json(
        {
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
    )
    lowering_schema_version = "wcc_m4"
    lexical_checkpoint_points = getattr(runtime_plan, "lexical_checkpoint_points", ())
    if lexical_checkpoint_points:
        first_point = lexical_checkpoint_points[0]
        lowering_schema_version = str(
            _mapping(_point_details(first_point).get("runtime_program_identity")).get("lowering_schema_version", "wcc_m4")
        )
    return {
        "workflow_name": workflow_name,
        "lowering_schema_version": lowering_schema_version,
        "source_module_digest": source_module_digest,
        "executable_ir_digest": executable_ir_digest,
        "semantic_ir_digest": semantic_ir_digest,
        "checkpoint_schema_version": CHECKPOINT_RECORD_SCHEMA_VERSION,
    }


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
        point_payload = _point_payload(point)
        validate_checkpoint_point_payload(point_payload)
        if workflow_name != getattr(runtime_plan, "workflow_name", ""):
            raise ValueError(DIAGNOSTIC_CODES.program_identity_mismatch)

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
                "source_map_origin_key": _point_field(point, "origin_key"),
                "storage_allocation_id": record_allocation.allocation_id,
            },
            "binding_schema_digest": _binding_schema_digest(point),
            "storage_allocation_id": record_allocation.allocation_id,
            "origin_key": point_payload.get("origin_key"),
            "provisional_policy": "shadow_record_only",
            "typed_binding_refs": [],
            "active_variant_proofs": [],
            "loop_frame_state": None if loop_iteration is None else {"iteration": loop_iteration},
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
        restore_payload = capture_restore_payload(
            executor=executor,
            point=point,
            execution_index=execution_index,
            loop_iteration=loop_iteration,
        )
        if restore_payload is not None:
            record["restore_payload"] = dict(restore_payload)
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
    if final_state.get("status") not in {"completed", "failed"}:
        raise AssertionError(f"unexpected workflow terminal status: {final_state.get('status')}")

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
