"""Restore payload helpers for private lexical checkpoint sidecars."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence


RESTORE_PAYLOAD_SCHEMA_VERSION = "workflow_lisp_lexical_restore_payload.v1"
RESTORE_DECISION_RESTORED = "RESTORED"
RESTORE_DECISION_NOT_RESTORABLE = "NOT_RESTORABLE"
RESTORE_DECISION_INVALID = "INVALID"
RESTORE_ELIGIBILITY_CLASSES = frozenset(
    {"pure_binding", "let_continuation", "match_branch", "loop_frame"}
)
RESTORE_TRANSPORTS = frozenset({"inline_json", "private_artifact_ref"})


@dataclass(frozen=True)
class RestoreDiagnosticCodes:
    payload_schema_invalid: str = "lexical_restore_payload_schema_invalid"
    program_identity_mismatch: str = "lexical_restore_program_identity_mismatch"
    semantic_digest_mismatch: str = "lexical_restore_semantic_digest_mismatch"
    source_lineage_mismatch: str = "lexical_restore_source_lineage_mismatch"
    binding_schema_mismatch: str = "lexical_restore_binding_schema_mismatch"
    value_digest_mismatch: str = "lexical_restore_value_digest_mismatch"
    proof_mismatch: str = "lexical_restore_proof_mismatch"
    loop_frame_mismatch: str = "lexical_restore_loop_frame_mismatch"
    pending_effect_unsafe: str = "lexical_restore_pending_effect_unsafe"
    resource_observation_mismatch: str = "lexical_restore_resource_observation_mismatch"
    used_as_semantic_authority: str = "lexical_restore_used_as_semantic_authority"


DIAGNOSTIC_CODES = RestoreDiagnosticCodes()


@dataclass(frozen=True)
class RestoreDecision:
    kind: str
    checkpoint_id: str | None = None
    record_id: str | None = None
    source_map_origin_key: str | None = None
    restore_payload: Mapping[str, Any] | None = None
    diagnostics: tuple[str, ...] = ()

    @property
    def restored_bindings(self) -> int:
        payload = self.restore_payload or {}
        bindings = payload.get("bindings") if isinstance(payload, Mapping) else None
        return len(bindings) if isinstance(bindings, list) else 0

    @property
    def restored_loop_frames(self) -> int:
        payload = self.restore_payload or {}
        return 1 if isinstance(payload, Mapping) and isinstance(payload.get("loop_frame"), Mapping) else 0


def canonical_json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def _sha256_text(value: object) -> str:
    return f"sha256:{hashlib.sha256(str(value).encode('utf-8')).hexdigest()}"


def _sha256_json(value: Any) -> str:
    return _sha256_text(canonical_json_dumps(value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else ()


def _non_empty_string(value: Any, diagnostic: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(diagnostic)
    return value


def _binding_schema_digest(binding: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "binding_name": binding.get("binding_name"),
            "binding_kind": binding.get("binding_kind"),
            "type_ref": binding.get("type_ref"),
        }
    )


def _binding_value_digest(binding: Mapping[str, Any]) -> str:
    return _sha256_json(resolve_binding_restore_value(binding))


def _private_artifact_bundle_record(
    binding: Mapping[str, Any],
    *,
    state_manager: Any | None,
) -> Mapping[str, Any]:
    if state_manager is None:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    workspace = getattr(state_manager, "workspace", None)
    if workspace is None:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    workspace_path = Path(workspace).resolve()
    artifact_ref = _mapping(binding.get("private_artifact_ref"))
    artifact_path = _non_empty_string(
        artifact_ref.get("path"),
        DIAGNOSTIC_CODES.used_as_semantic_authority,
    )
    if artifact_ref.get("bundle_kind") != "pure_projection_result":
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    expected_schema = artifact_ref.get("pure_expr_schema_version")
    if not isinstance(expected_schema, int):
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    expected_payload_digest = artifact_ref.get("payload_digest")
    if not isinstance(expected_payload_digest, str) or not expected_payload_digest:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    bundle_path = (workspace_path / artifact_path).resolve()
    try:
        bundle_path.relative_to(workspace_path)
    except ValueError as exc:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority) from exc
    try:
        bundle_record = state_manager.read_runtime_sidecar_json(bundle_path)
    except Exception as exc:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority) from exc
    if not isinstance(bundle_record, Mapping):
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    if bundle_record.get("pure_expr_schema_version") != expected_schema:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    if bundle_record.get("payload_digest") != expected_payload_digest:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    if "result" not in bundle_record:
        raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
    return bundle_record


def resolve_binding_restore_value(
    binding: Mapping[str, Any],
    *,
    state_manager: Any | None = None,
) -> Any:
    transport = binding.get("transport")
    if transport == "inline_json":
        return binding.get("value")
    if transport == "private_artifact_ref":
        return _private_artifact_bundle_record(binding, state_manager=state_manager).get("result")
    raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)


def _proof_variant_name(proof: Mapping[str, Any]) -> str | None:
    variant = proof.get("variant")
    if isinstance(variant, str) and variant:
        return variant
    variant_name = proof.get("variant_name")
    if isinstance(variant_name, str) and variant_name:
        return variant_name
    return None


def _proof_discriminant_digest(proof: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "proof_id": proof.get("proof_id"),
            "subject_binding": proof.get("subject_binding"),
            "union_type": proof.get("union_type"),
            "variant": _proof_variant_name(proof),
            "proof_source": proof.get("proof_source"),
            "source_map_origin_key": proof.get("source_map_origin_key"),
        }
    )


def _binding_descriptor_digest(descriptor: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "binding_name": descriptor.get("binding_name"),
            "binding_kind": descriptor.get("binding_kind"),
            "type_ref": descriptor.get("type_ref"),
            "source_step_id": descriptor.get("source_step_id"),
            "source_map_origin_key": descriptor.get("source_map_origin_key"),
            "value_document": descriptor.get("value_document"),
        }
    )


def _proof_descriptor_digest(descriptor: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "proof_id": descriptor.get("proof_id"),
            "subject_binding": descriptor.get("subject_binding"),
            "union_type": descriptor.get("union_type"),
            "proof_source": descriptor.get("proof_source"),
            "source_map_origin_key": descriptor.get("source_map_origin_key"),
        }
    )


def _loop_frame_digest(loop_frame: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "loop_id": loop_frame.get("loop_id"),
            "iteration": loop_frame.get("iteration"),
            "next_iteration": loop_frame.get("next_iteration"),
            "state_binding": loop_frame.get("state_binding"),
            "type_ref": loop_frame.get("type_ref"),
            "state_value": loop_frame.get("state_value"),
        }
    )


def _loop_frame_descriptor_digest(descriptor: Mapping[str, Any]) -> str:
    return _sha256_json(
        {
            "loop_name": descriptor.get("loop_name"),
            "loop_site_id": descriptor.get("loop_site_id"),
            "state_binding_name": descriptor.get("state_binding_name"),
            "state_type_ref": descriptor.get("state_type_ref"),
            "source_map_origin_key": descriptor.get("source_map_origin_key"),
        }
    )


def build_restore_metadata(
    *,
    binding_descriptors: Sequence[Mapping[str, Any]] = (),
    proof_descriptors: Sequence[Mapping[str, Any]] = (),
    loop_frame_descriptor: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    normalized_binding_descriptors = [dict(descriptor) for descriptor in binding_descriptors if isinstance(descriptor, Mapping)]
    normalized_proof_descriptors = [dict(descriptor) for descriptor in proof_descriptors if isinstance(descriptor, Mapping)]
    normalized_loop_descriptor = dict(loop_frame_descriptor) if isinstance(loop_frame_descriptor, Mapping) else None
    eligibility: list[str] = []
    if normalized_binding_descriptors:
        eligibility.extend(["pure_binding", "let_continuation"])
    if normalized_proof_descriptors:
        eligibility.append("match_branch")
    if normalized_loop_descriptor is not None:
        eligibility.append("loop_frame")
    return {
        "eligibility": list(dict.fromkeys(eligibility)),
        "binding_descriptors": normalized_binding_descriptors,
        "binding_descriptor_digests": [
            _binding_descriptor_digest(descriptor)
            for descriptor in normalized_binding_descriptors
        ],
        "proof_descriptors": normalized_proof_descriptors,
        "proof_descriptor_digests": [
            _proof_descriptor_digest(descriptor)
            for descriptor in normalized_proof_descriptors
        ],
        "loop_frame_descriptor": normalized_loop_descriptor,
        "loop_frame_descriptor_digest": (
            _loop_frame_descriptor_digest(normalized_loop_descriptor)
            if normalized_loop_descriptor is not None
            else None
        ),
    }


def public_restore_metadata(restore: Mapping[str, Any]) -> Mapping[str, Any]:
    restore_map = _mapping(restore)
    if not restore_map:
        return {}
    return {
        "eligibility": list(_sequence(restore_map.get("eligibility"))),
        "binding_descriptor_digests": list(_sequence(restore_map.get("binding_descriptor_digests"))),
        "proof_descriptor_digests": list(_sequence(restore_map.get("proof_descriptor_digests"))),
        "loop_frame_descriptor_digest": restore_map.get("loop_frame_descriptor_digest"),
    }


def validate_restore_point_metadata(restore: Mapping[str, Any]) -> None:
    eligibility = restore.get("eligibility")
    if not isinstance(eligibility, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    if not set(eligibility) <= RESTORE_ELIGIBILITY_CLASSES:
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    binding_descriptors = restore.get("binding_descriptors")
    if not isinstance(binding_descriptors, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    for descriptor in binding_descriptors:
        descriptor_map = _mapping(descriptor)
        _non_empty_string(descriptor_map.get("binding_name"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("binding_kind"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("type_ref"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("source_map_origin_key"), DIAGNOSTIC_CODES.payload_schema_invalid)
        if "value_document" not in descriptor_map or not _value_document_is_valid(descriptor_map.get("value_document")):
            raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
        source_step_name = descriptor_map.get("source_step_name")
        source_step_id = descriptor_map.get("source_step_id")
        if source_step_name is None and source_step_id is None:
            pass
        else:
            _non_empty_string(source_step_name, DIAGNOSTIC_CODES.payload_schema_invalid)
            _non_empty_string(source_step_id, DIAGNOSTIC_CODES.payload_schema_invalid)
    binding_digests = restore.get("binding_descriptor_digests")
    proof_digests = restore.get("proof_descriptor_digests")
    loop_digest = restore.get("loop_frame_descriptor_digest")
    if (
        not isinstance(binding_digests, list)
        or binding_digests != [_binding_descriptor_digest(_mapping(descriptor)) for descriptor in binding_descriptors]
    ):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    proof_descriptors = restore.get("proof_descriptors")
    if not isinstance(proof_descriptors, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    for descriptor in proof_descriptors:
        descriptor_map = _mapping(descriptor)
        _non_empty_string(descriptor_map.get("proof_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("subject_binding"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("union_type"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("proof_source"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("source_step_name"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("source_step_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(descriptor_map.get("source_map_origin_key"), DIAGNOSTIC_CODES.payload_schema_invalid)
    if (
        not isinstance(proof_digests, list)
        or proof_digests != [_proof_descriptor_digest(_mapping(descriptor)) for descriptor in proof_descriptors]
    ):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    loop_descriptor = restore.get("loop_frame_descriptor")
    if loop_descriptor is not None:
        loop_map = _mapping(loop_descriptor)
        _non_empty_string(loop_map.get("loop_name"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(loop_map.get("loop_site_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(loop_map.get("state_binding_name"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(loop_map.get("state_type_ref"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(loop_map.get("source_map_origin_key"), DIAGNOSTIC_CODES.payload_schema_invalid)
        if loop_digest != _loop_frame_descriptor_digest(loop_map):
            raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    elif loop_digest is not None:
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)


def _binding_name_from_match_step(step_name: str) -> str | None:
    match = re.search(r"__([^:]+?)__match_", step_name)
    if match is None:
        return None
    return match.group(1)


def _value_document_is_valid(value: Any) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if isinstance(value, Mapping):
        if set(value) == {"ref"}:
            return isinstance(value.get("ref"), str) and bool(value.get("ref"))
        return all(_value_document_is_valid(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_value_document_is_valid(item) for item in value)
    return False


def _match_subject_from_match_step(step_name: str) -> str | None:
    _, marker, suffix = step_name.rpartition("__match_")
    if marker != "__match_" or not suffix:
        return None
    return suffix


def capture_restore_payload(
    *,
    executor: Any,
    point: Any,
    execution_index: int,
    loop_iteration: int | None,
) -> Mapping[str, Any] | None:
    restore = _mapping(getattr(point, "details", {}).get("restore"))
    if not restore:
        return None

    run_state = executor.state_manager.state.to_dict() if executor.state_manager.state is not None else {}
    steps = run_state.get("steps", {})
    if not isinstance(steps, dict):
        steps = {}

    bindings: list[dict[str, Any]] = []
    proofs: list[dict[str, Any]] = []
    seen_proofs: set[str] = set()
    binding_descriptors = [
        _mapping(descriptor)
        for descriptor in _sequence(restore.get("binding_descriptors"))
        if isinstance(descriptor, Mapping)
    ]
    proof_descriptors = [
        _mapping(descriptor)
        for descriptor in _sequence(restore.get("proof_descriptors"))
        if isinstance(descriptor, Mapping)
    ]

    for descriptor in binding_descriptors:
        step_name = descriptor.get("source_step_name")
        value_document = descriptor.get("value_document")
        value = None
        if value_document is not None and hasattr(executor, "_resolve_pure_projection_bindings"):
            value, error = executor._resolve_pure_projection_bindings(value_document, run_state)
            if error is not None:
                continue
        elif isinstance(step_name, str) and step_name:
            result = _mapping(steps.get(step_name))
            if result.get("status") != "completed":
                continue
            artifacts = _mapping(result.get("artifacts"))
            if "return" not in artifacts:
                continue
            value = artifacts.get("return")
        else:
            continue
        binding_payload = {
            "binding_name": descriptor.get("binding_name"),
            "binding_kind": descriptor.get("binding_kind"),
            "type_ref": descriptor.get("type_ref"),
            "schema_digest": "",
            "value_digest": "",
            "transport": "inline_json",
            "value": value,
            "source_map_origin_key": descriptor.get("source_map_origin_key"),
        }
        if isinstance(step_name, str) and step_name:
            binding_payload["source_step_name"] = step_name
        source_step_id = descriptor.get("source_step_id")
        if isinstance(source_step_id, str) and source_step_id:
            binding_payload["source_step_id"] = source_step_id
        binding_payload["schema_digest"] = _binding_schema_digest(binding_payload)
        binding_payload["value_digest"] = _binding_value_digest(binding_payload)
        bindings.append(binding_payload)

    for descriptor in proof_descriptors:
        step_name = descriptor.get("source_step_name")
        proof_id = descriptor.get("proof_id")
        if not isinstance(step_name, str) or not step_name or not isinstance(proof_id, str) or not proof_id:
            continue
        if proof_id in seen_proofs:
            continue
        result = _mapping(steps.get(step_name))
        if result.get("status") != "completed":
            continue
        structured_match = _mapping(_mapping(result.get("debug")).get("structured_match"))
        selected_case = structured_match.get("selected_case")
        if not isinstance(selected_case, str) or not selected_case:
            continue
        proof_payload = {
            "proof_id": proof_id,
            "proof_kind": "match_branch",
            "subject_binding": descriptor.get("subject_binding"),
            "union_type": descriptor.get("union_type"),
            "variant": selected_case,
            "variant_name": selected_case,
            "proof_source": descriptor.get("proof_source"),
            "source_map_origin_key": descriptor.get("source_map_origin_key"),
            "discriminant_digest": "",
        }
        proof_payload["discriminant_digest"] = _proof_discriminant_digest(proof_payload)
        proofs.append(proof_payload)
        seen_proofs.add(proof_id)

    loop_frame = None
    if getattr(point, "point_kind", None) == "loop_back_edge":
        loop_name = getattr(point, "presentation_key", "")
        progress = _mapping(_mapping(run_state.get("repeat_until")).get(loop_name))
        frame_result = _mapping(steps.get(loop_name))
        artifacts = _mapping(frame_result.get("artifacts"))
        if progress or artifacts:
            iteration = loop_iteration if isinstance(loop_iteration, int) else progress.get("condition_evaluated_for_iteration")
            if not isinstance(iteration, int):
                iteration = 0
            state_value = {
                str(key[len("state__"):]): value
                for key, value in artifacts.items()
                if isinstance(key, str) and key.startswith("state__")
            }
            loop_descriptor = _mapping(restore.get("loop_frame_descriptor"))
            loop_frame = {
                "loop_id": loop_name,
                "loop_name": loop_name,
                "loop_site_id": loop_descriptor.get("loop_site_id"),
                "iteration": iteration,
                "current_iteration": iteration,
                "next_iteration": iteration + 1,
                "frame_state_digest": "",
                "state_binding": "state",
                "state_binding_name": loop_descriptor.get("state_binding_name", "state"),
                "type_ref": loop_descriptor.get("state_type_ref", "loop_frame"),
                "state_type_ref": loop_descriptor.get("state_type_ref", "loop_frame"),
                "frame_digest": "",
                "state_value": state_value,
                "proofs": [],
                "proofs_carried": [],
            }
            loop_frame["frame_digest"] = _loop_frame_digest(loop_frame)
            loop_frame["frame_state_digest"] = loop_frame["frame_digest"]

    payload = {
        "schema_version": RESTORE_PAYLOAD_SCHEMA_VERSION,
        "eligibility": list(restore.get("eligibility", ())),
        "restorable": bool(bindings or proofs or loop_frame),
        "resume_after": {
            "program_point_id": getattr(point, "program_point_id", ""),
            "step_id": getattr(point, "step_id", ""),
            "execution_index": execution_index,
            "continuation_kind": getattr(point, "point_kind", ""),
        },
        "bindings": bindings,
        "active_variant_proofs": proofs,
        "loop_frame": loop_frame,
        "completed_effect_barrier": None,
        "resource_observations": [],
    }
    if not payload["restorable"]:
        return None
    validate_restore_payload(payload)
    return payload


def validate_restore_payload(
    payload: Mapping[str, Any],
    *,
    expected_origin_key: str | None = None,
    state_manager: Any | None = None,
) -> None:
    if payload.get("schema_version") != RESTORE_PAYLOAD_SCHEMA_VERSION:
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    eligibility = payload.get("eligibility")
    if not isinstance(eligibility, list) or not eligibility or not set(eligibility) <= RESTORE_ELIGIBILITY_CLASSES:
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    resume_after = _mapping(payload.get("resume_after"))
    _non_empty_string(resume_after.get("program_point_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
    _non_empty_string(resume_after.get("step_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
    if not isinstance(resume_after.get("execution_index"), int):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    _non_empty_string(resume_after.get("continuation_kind"), DIAGNOSTIC_CODES.payload_schema_invalid)

    bindings = payload.get("bindings")
    if not isinstance(bindings, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    for binding in bindings:
        binding_map = _mapping(binding)
        _non_empty_string(binding_map.get("binding_name"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(binding_map.get("binding_kind"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(binding_map.get("type_ref"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(binding_map.get("source_map_origin_key"), DIAGNOSTIC_CODES.payload_schema_invalid)
        transport = _non_empty_string(binding_map.get("transport"), DIAGNOSTIC_CODES.payload_schema_invalid)
        if transport not in RESTORE_TRANSPORTS:
            raise ValueError(DIAGNOSTIC_CODES.used_as_semantic_authority)
        if binding_map.get("schema_digest") != _binding_schema_digest(binding_map):
            raise ValueError(DIAGNOSTIC_CODES.binding_schema_mismatch)
        if binding_map.get("value_digest") != _sha256_json(
            resolve_binding_restore_value(binding_map, state_manager=state_manager)
        ):
            raise ValueError(DIAGNOSTIC_CODES.value_digest_mismatch)

    proofs = payload.get("active_variant_proofs")
    if not isinstance(proofs, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    for proof in proofs:
        proof_map = _mapping(proof)
        _non_empty_string(proof_map.get("proof_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(proof_map.get("subject_binding"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(proof_map.get("union_type"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(_proof_variant_name(proof_map), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(proof_map.get("proof_source"), DIAGNOSTIC_CODES.payload_schema_invalid)
        _non_empty_string(proof_map.get("source_map_origin_key"), DIAGNOSTIC_CODES.payload_schema_invalid)
        if proof_map.get("discriminant_digest") != _proof_discriminant_digest(proof_map):
            raise ValueError(DIAGNOSTIC_CODES.proof_mismatch)

    loop_frame = payload.get("loop_frame")
    if loop_frame is not None:
        loop_map = _mapping(loop_frame)
        _non_empty_string(loop_map.get("loop_id"), DIAGNOSTIC_CODES.payload_schema_invalid)
        if not isinstance(loop_map.get("iteration"), int) or not isinstance(loop_map.get("next_iteration"), int):
            raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
        if not isinstance(loop_map.get("current_iteration"), int):
            raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
        if not isinstance(loop_map.get("state_value"), Mapping):
            raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
        if loop_map.get("frame_digest") != _loop_frame_digest(loop_map):
            raise ValueError(DIAGNOSTIC_CODES.loop_frame_mismatch)

    resource_observations = payload.get("resource_observations")
    if not isinstance(resource_observations, list):
        raise ValueError(DIAGNOSTIC_CODES.payload_schema_invalid)
    if resource_observations:
        raise ValueError(DIAGNOSTIC_CODES.resource_observation_mismatch)


def _workflow_path_from_state(state_manager: Any, state: Mapping[str, Any]) -> Path | None:
    workflow_file = state.get("workflow_file")
    if not isinstance(workflow_file, str) or not workflow_file:
        return None
    candidate = (state_manager.workspace / workflow_file).resolve()
    return candidate if candidate.exists() else None


def _loop_frame_matches_repeat_until_progress(
    loop_frame: Mapping[str, Any],
    state: Mapping[str, Any],
) -> bool:
    loop_id = loop_frame.get("loop_id")
    iteration = loop_frame.get("iteration")
    next_iteration = loop_frame.get("next_iteration")
    if not isinstance(loop_id, str) or not loop_id:
        return False
    if not isinstance(iteration, int) or not isinstance(next_iteration, int):
        return False

    repeat_until = _mapping(state.get("repeat_until"))
    progress = _mapping(repeat_until.get(loop_id))
    if not progress:
        return False

    condition_evaluated = progress.get("condition_evaluated_for_iteration")
    if condition_evaluated is not None and condition_evaluated != iteration:
        return False

    current_iteration = progress.get("current_iteration")
    if current_iteration is not None and current_iteration not in {iteration, next_iteration}:
        return False

    completed_iterations = {
        value
        for value in progress.get("completed_iterations", ())
        if isinstance(value, int)
    }
    exhausted = progress.get("exhausted")
    if exhausted is True and iteration not in completed_iterations:
        return False

    steps = _mapping(state.get("steps"))
    persisted_loop_step = _mapping(steps.get(loop_id))
    persisted_artifacts = _mapping(persisted_loop_step.get("artifacts"))
    if persisted_artifacts:
        persisted_state = {
            key[len("state__"):]: value
            for key, value in persisted_artifacts.items()
            if isinstance(key, str) and key.startswith("state__")
        }
        if persisted_state and persisted_state != loop_frame.get("state_value"):
            return False
    return True


def _match_join_node_by_binding_name(
    executable_workflow: Any,
    binding_name: str,
) -> Any | None:
    suffix = f"__{binding_name}__match_decision"
    nodes = getattr(executable_workflow, "nodes", {})
    for node in nodes.values() if isinstance(nodes, Mapping) else ():
        statement_name = getattr(node, "statement_name", None)
        case_outputs = getattr(node, "case_outputs", None)
        if (
            isinstance(statement_name, str)
            and statement_name.endswith(suffix)
            and isinstance(case_outputs, Mapping)
            and case_outputs
        ):
            return node
    return None


def _node_result_artifact(
    *,
    executable_workflow: Any,
    state: Mapping[str, Any],
    node_id: str,
    output_name: str,
) -> Any:
    if not isinstance(node_id, str) or not node_id:
        return None
    nodes = getattr(executable_workflow, "nodes", {})
    node = nodes.get(node_id) if isinstance(nodes, Mapping) else None
    presentation_name = getattr(node, "presentation_name", None)
    if not isinstance(presentation_name, str) or not presentation_name:
        return None
    steps = _mapping(state.get("steps"))
    step_result = _mapping(steps.get(presentation_name))
    artifacts = _mapping(step_result.get("artifacts"))
    return artifacts.get(output_name)


def _selector_variant_for_match_join(
    *,
    executable_workflow: Any,
    state: Mapping[str, Any],
    node: Any,
) -> str | None:
    selector_address = getattr(node, "selector_address", None)
    selector_node_id = getattr(selector_address, "node_id", None)
    selector_output_name = getattr(selector_address, "output_name", None)
    if not isinstance(selector_node_id, str) or not isinstance(selector_output_name, str):
        return None
    selected_variant = _node_result_artifact(
        executable_workflow=executable_workflow,
        state=state,
        node_id=selector_node_id,
        output_name=selector_output_name,
    )
    return selected_variant if isinstance(selected_variant, str) and selected_variant else None


def _binding_contract_matches_type_ref(contract: Any, type_ref: Any) -> bool:
    if not isinstance(type_ref, str) or not type_ref:
        return False
    contract_kind = getattr(contract, "kind", None)
    if contract_kind == "scalar":
        expected = {
            "string": "String",
            "integer": "Int",
            "boolean": "Bool",
        }.get(getattr(contract, "value_type", None))
        if expected is None:
            return True
        return type_ref == expected
    if contract_kind == "relpath":
        return type_ref not in {"String", "Int", "Bool"}
    return True


def _type_ref_for_contract(contract: Any, fallback: Any) -> str:
    contract_kind = getattr(contract, "kind", None)
    if contract_kind == "scalar":
        mapped = {
            "string": "String",
            "integer": "Int",
            "boolean": "Bool",
        }.get(getattr(contract, "value_type", None))
        if isinstance(mapped, str):
            return mapped
    definition = getattr(contract, "definition", None)
    if isinstance(definition, Mapping):
        for key in ("name", "type"):
            value = definition.get(key)
            if isinstance(value, str) and value:
                return value
    if isinstance(fallback, str) and fallback:
        return fallback
    return type(fallback).__name__


def _binding_matches_current_contract(
    *,
    binding: Mapping[str, Any],
    executable_workflow: Any,
    state: Mapping[str, Any],
) -> bool:
    binding_name = binding.get("binding_name")
    if not isinstance(binding_name, str) or not binding_name:
        return False
    node = _match_join_node_by_binding_name(executable_workflow, binding_name)
    if node is None:
        return True
    selected_variant = _selector_variant_for_match_join(
        executable_workflow=executable_workflow,
        state=state,
        node=node,
    )
    case_outputs = getattr(node, "case_outputs", {})
    if not isinstance(selected_variant, str) or selected_variant not in case_outputs:
        return False
    contract = _mapping(case_outputs[selected_variant]).get("return")
    if contract is None or not _binding_contract_matches_type_ref(contract, binding.get("type_ref")):
        return False
    source_address = getattr(contract, "source_address", None)
    source_node_id = getattr(source_address, "node_id", None)
    source_output_name = getattr(source_address, "output_name", None)
    if not isinstance(source_node_id, str) or not isinstance(source_output_name, str):
        return False
    current_value = _node_result_artifact(
        executable_workflow=executable_workflow,
        state=state,
        node_id=source_node_id,
        output_name=source_output_name,
    )
    if binding.get("transport") == "inline_json":
        return current_value is not None and binding.get("value_digest") == _sha256_json(current_value)
    return True


def _binding_contract_for_name(
    *,
    executable_workflow: Any,
    state: Mapping[str, Any],
    binding_name: str,
) -> Any | None:
    node = _match_join_node_by_binding_name(executable_workflow, binding_name)
    if node is None:
        return None
    selected_variant = _selector_variant_for_match_join(
        executable_workflow=executable_workflow,
        state=state,
        node=node,
    )
    case_outputs = getattr(node, "case_outputs", {})
    if not isinstance(selected_variant, str) or selected_variant not in case_outputs:
        return None
    return _mapping(case_outputs[selected_variant]).get("return")


def _binding_descriptor_diagnostic(
    *,
    binding: Mapping[str, Any],
    restore_metadata: Mapping[str, Any],
) -> str | None:
    descriptors = [
        _mapping(descriptor)
        for descriptor in _sequence(restore_metadata.get("binding_descriptors"))
        if isinstance(descriptor, Mapping)
    ]
    binding_name = binding.get("binding_name")
    if not isinstance(binding_name, str) or not binding_name:
        return DIAGNOSTIC_CODES.binding_schema_mismatch
    descriptor = next(
        (candidate for candidate in descriptors if candidate.get("binding_name") == binding_name),
        None,
    )
    if descriptor is None:
        return DIAGNOSTIC_CODES.binding_schema_mismatch
    if binding.get("source_map_origin_key") != descriptor.get("source_map_origin_key"):
        return DIAGNOSTIC_CODES.source_lineage_mismatch
    if binding.get("binding_kind") != descriptor.get("binding_kind"):
        return DIAGNOSTIC_CODES.binding_schema_mismatch
    if binding.get("type_ref") != descriptor.get("type_ref"):
        return DIAGNOSTIC_CODES.binding_schema_mismatch
    return None


def _proof_descriptor_diagnostic(
    *,
    proof: Mapping[str, Any],
    restore_metadata: Mapping[str, Any],
) -> str | None:
    descriptors = [
        _mapping(descriptor)
        for descriptor in _sequence(restore_metadata.get("proof_descriptors"))
        if isinstance(descriptor, Mapping)
    ]
    proof_id = proof.get("proof_id")
    if not isinstance(proof_id, str) or not proof_id:
        return DIAGNOSTIC_CODES.proof_mismatch
    descriptor = next(
        (candidate for candidate in descriptors if candidate.get("proof_id") == proof_id),
        None,
    )
    if descriptor is None:
        return DIAGNOSTIC_CODES.proof_mismatch
    if proof.get("source_map_origin_key") != descriptor.get("source_map_origin_key"):
        return DIAGNOSTIC_CODES.source_lineage_mismatch
    if proof.get("proof_source") != descriptor.get("proof_source"):
        return DIAGNOSTIC_CODES.proof_mismatch
    if proof.get("subject_binding") != descriptor.get("subject_binding"):
        return DIAGNOSTIC_CODES.proof_mismatch
    if proof.get("union_type") != descriptor.get("union_type"):
        return DIAGNOSTIC_CODES.proof_mismatch
    return None


def _match_join_node_for_proof_source(
    *,
    executable_workflow: Any,
    proof: Mapping[str, Any],
) -> Any | None:
    proof_source = proof.get("proof_source")
    if not isinstance(proof_source, str) or not proof_source:
        return None
    nodes = getattr(executable_workflow, "nodes", {})
    for node in nodes.values() if isinstance(nodes, Mapping) else ():
        node_step_id = getattr(node, "step_id", None)
        if (
            getattr(node, "case_outputs", None)
            and isinstance(node_step_id, str)
            and (
                node_step_id == proof_source
                or node_step_id.endswith(f".{proof_source}")
                or node_step_id.endswith(proof_source)
            )
        ):
            return node
    return None


def _proof_matches_current_selector_variant(
    *,
    proof: Mapping[str, Any],
    executable_workflow: Any,
    state: Mapping[str, Any],
) -> bool:
    expected_variant = _proof_variant_name(proof)
    if not isinstance(expected_variant, str) or not expected_variant:
        return False
    node = _match_join_node_for_proof_source(executable_workflow=executable_workflow, proof=proof)
    if node is None:
        return False
    current_variant = _selector_variant_for_match_join(
        executable_workflow=executable_workflow,
        state=state,
        node=node,
    )
    return current_variant == expected_variant


def select_restore_candidate(
    *,
    state_manager: Any,
    runtime_plan: Any,
    state: Mapping[str, Any],
    checkpoint_id: str | None = None,
    restart_node_id: str | None = None,
    executable_workflow: Any | None = None,
) -> RestoreDecision:
    from orchestrator.workflow_lisp import lexical_checkpoints as checkpoints

    expected_program_identity = checkpoints.checkpoint_runtime_program_identity(
        state_manager=state_manager,
        runtime_plan=runtime_plan,
        workflow_path=_workflow_path_from_state(state_manager, state),
    )
    all_points = tuple(getattr(runtime_plan, "lexical_checkpoint_points", ()))

    def _select_for_points(points: Sequence[Any], *, selected_checkpoint_id: str | None = None) -> RestoreDecision:
        if not points:
            return RestoreDecision(kind=RESTORE_DECISION_NOT_RESTORABLE, checkpoint_id=selected_checkpoint_id)

        invalid_diagnostics: list[str] = []
        saw_non_restorable = False

        for point in points:
            index_path = checkpoints.resolve_checkpoint_index_path(
                state_manager=state_manager,
                workflow_name=point.workflow_name,
                checkpoint_id=point.checkpoint_id,
            )
            try:
                index_payload = state_manager.read_runtime_sidecar_json(index_path)
            except Exception:
                continue
            records = index_payload.get("records") if isinstance(index_payload, Mapping) else None
            if not isinstance(records, list):
                continue
            for entry in reversed(records):
                entry_map = _mapping(entry)
                record_path_value = entry_map.get("record_path")
                if not isinstance(record_path_value, str) or not record_path_value:
                    continue
                try:
                    record = state_manager.read_runtime_sidecar_json(state_manager.workspace / record_path_value)
                except Exception:
                    continue
                if not isinstance(record, Mapping):
                    continue

                record_id = record.get("record_id") if isinstance(record.get("record_id"), str) else None
                origin_key = point.origin_key if isinstance(getattr(point, "origin_key", None), str) else None
                program_identity = _mapping(record.get("program_identity"))
                if program_identity.get("semantic_ir_digest") != expected_program_identity.get("semantic_ir_digest"):
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.semantic_digest_mismatch,),
                    )
                if any(
                    program_identity.get(field) != expected_program_identity.get(field)
                    for field in ("workflow_name", "lowering_schema_version", "source_module_digest", "executable_ir_digest")
                ):
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.program_identity_mismatch,),
                    )
                if record.get("origin_key") != point.origin_key:
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.source_lineage_mismatch,),
                    )
                if record.get("binding_schema_digest") != checkpoints.checkpoint_record_binding_schema_digest(
                    checkpoints._point_payload(point)
                ):
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.binding_schema_mismatch,),
                    )
                if _mapping(record.get("pending_effect_policy")).get("policy_status") != "shadow_record_only":
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.pending_effect_unsafe,),
                    )
                restore_payload = record.get("restore_payload")
                if restore_payload is None:
                    saw_non_restorable = True
                    continue
                try:
                    validate_restore_payload(
                        _mapping(restore_payload),
                        expected_origin_key=point.origin_key,
                        state_manager=state_manager,
                    )
                except ValueError as exc:
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(str(exc),),
                    )
                restore_metadata = _mapping(getattr(point, "details", {}).get("restore"))
                bindings = _sequence(_mapping(restore_payload).get("bindings"))
                binding_diagnostic = next(
                    (
                        diagnostic
                        for binding in bindings
                        for diagnostic in (
                            _binding_descriptor_diagnostic(
                                binding=_mapping(binding),
                                restore_metadata=restore_metadata,
                            ),
                        )
                        if diagnostic is not None
                    ),
                    None,
                )
                if binding_diagnostic is not None:
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(binding_diagnostic,),
                    )
                proofs = _sequence(_mapping(restore_payload).get("active_variant_proofs"))
                proof_diagnostic = next(
                    (
                        diagnostic
                        for proof in proofs
                        for diagnostic in (
                            _proof_descriptor_diagnostic(
                                proof=_mapping(proof),
                                restore_metadata=restore_metadata,
                            ),
                        )
                        if diagnostic is not None
                    ),
                    None,
                )
                if proof_diagnostic is not None:
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(proof_diagnostic,),
                    )
                if executable_workflow is not None:
                    if any(
                        not _binding_matches_current_contract(
                            binding=_mapping(binding),
                            executable_workflow=executable_workflow,
                            state=state,
                        )
                        for binding in bindings
                    ):
                        return RestoreDecision(
                            kind=RESTORE_DECISION_INVALID,
                            checkpoint_id=point.checkpoint_id,
                            record_id=record_id,
                            source_map_origin_key=origin_key,
                            diagnostics=(DIAGNOSTIC_CODES.binding_schema_mismatch,),
                        )
                    if any(
                        not _proof_matches_current_selector_variant(
                            proof=_mapping(proof),
                            executable_workflow=executable_workflow,
                            state=state,
                        )
                        for proof in proofs
                    ):
                        return RestoreDecision(
                            kind=RESTORE_DECISION_INVALID,
                            checkpoint_id=point.checkpoint_id,
                            record_id=record_id,
                            source_map_origin_key=origin_key,
                            diagnostics=(DIAGNOSTIC_CODES.proof_mismatch,),
                        )
                loop_frame = _mapping(_mapping(restore_payload).get("loop_frame"))
                if loop_frame and not _loop_frame_matches_repeat_until_progress(loop_frame, state):
                    return RestoreDecision(
                        kind=RESTORE_DECISION_INVALID,
                        checkpoint_id=point.checkpoint_id,
                        record_id=record_id,
                        source_map_origin_key=origin_key,
                        diagnostics=(DIAGNOSTIC_CODES.loop_frame_mismatch,),
                    )
                return RestoreDecision(
                    kind=RESTORE_DECISION_RESTORED,
                    checkpoint_id=point.checkpoint_id,
                    record_id=record_id,
                    source_map_origin_key=origin_key,
                    restore_payload=_mapping(restore_payload),
                    diagnostics=(),
                )

        if invalid_diagnostics:
            return RestoreDecision(
                kind=RESTORE_DECISION_INVALID,
                checkpoint_id=selected_checkpoint_id,
                source_map_origin_key=None,
                diagnostics=tuple(invalid_diagnostics),
            )
        if saw_non_restorable:
            return RestoreDecision(kind=RESTORE_DECISION_NOT_RESTORABLE, checkpoint_id=selected_checkpoint_id)
        return RestoreDecision(kind=RESTORE_DECISION_NOT_RESTORABLE, checkpoint_id=selected_checkpoint_id)

    if checkpoint_id is not None:
        selected_points = tuple(point for point in all_points if getattr(point, "checkpoint_id", None) == checkpoint_id)
        return _select_for_points(selected_points, selected_checkpoint_id=checkpoint_id)

    selected_points = all_points
    if restart_node_id is not None:
        selected_points = tuple(
            point
            for point in all_points
            if getattr(point, "node_id", None) == restart_node_id
            or getattr(point, "step_id", None) == restart_node_id
        )
    primary = _select_for_points(selected_points)
    if primary.kind != RESTORE_DECISION_RESTORED:
        return primary

    primary_payload = dict(_mapping(primary.restore_payload))
    if isinstance(primary_payload.get("loop_frame"), Mapping):
        return primary

    repeat_until = state.get("repeat_until")
    if not isinstance(repeat_until, Mapping) or not repeat_until:
        return primary

    loop_points = tuple(
        point
        for point in all_points
        if getattr(point, "point_kind", None) == "loop_back_edge"
        and getattr(point, "presentation_key", None) in repeat_until
    )
    companion = _select_for_points(loop_points)
    if companion.kind == RESTORE_DECISION_INVALID:
        return companion
    companion_payload = _mapping(companion.restore_payload)
    if companion.kind != RESTORE_DECISION_RESTORED or not isinstance(companion_payload.get("loop_frame"), Mapping):
        return primary

    merged_payload = dict(primary_payload)
    merged_payload["eligibility"] = list(
        dict.fromkeys(
            list(primary_payload.get("eligibility", ()))
            + list(companion_payload.get("eligibility", ()))
        )
    )
    merged_payload["loop_frame"] = companion_payload.get("loop_frame")
    return RestoreDecision(
        kind=RESTORE_DECISION_RESTORED,
        checkpoint_id=primary.checkpoint_id,
        record_id=primary.record_id,
        source_map_origin_key=primary.source_map_origin_key,
        restore_payload=merged_payload,
        diagnostics=(),
    )
