"""Workflow Lisp typed prompt input helpers and deterministic rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

from orchestrator.contracts.prompt_contract import (
    normalize_consume_prompt_policy,
    selected_consumed_artifacts_for_prompt,
    stringify_consumed_value,
)
from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow.view_renderer import (
    VIEW_RENDERER_SCHEMA_VERSION,
    ViewRendererError,
    render_view,
    resolve_view_renderer,
    view_bytes_digest,
    view_evidence_key,
)


TYPED_PROMPT_INPUT_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input.v1"
TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input_evidence.v1"
TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input_report.v1"
_MISSING_SAMPLE_VALUE = object()


def normalize_typed_prompt_input_entry(entry: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and normalize one lowered typed prompt-input entry."""

    normalized = dict(entry)
    if normalized.get("schema_version") != TYPED_PROMPT_INPUT_SCHEMA_VERSION:
        raise ValueError("typed_prompt_input_schema_invalid: schema_version is required")
    for field_name in (
        "binding_name",
        "value_type_name",
        "source_map_origin_key",
        "u0_row_id",
        "c0_row_id",
    ):
        _require_non_empty_string(normalized.get(field_name), field_name)
    if not isinstance(normalized.get("value_source"), Mapping):
        raise ValueError("typed_prompt_input_schema_invalid: value_source is required")
    renderer = normalized.get("renderer")
    if not isinstance(renderer, Mapping):
        raise ValueError("typed_prompt_input_schema_invalid: renderer is required")
    renderer_id = _require_non_empty_string(renderer.get("renderer_id"), "renderer.renderer_id")
    renderer_version = renderer.get("renderer_version")
    if not isinstance(renderer_version, int):
        raise ValueError("typed_prompt_input_schema_invalid: renderer.renderer_version is required")
    accepted_shape = _require_non_empty_string(
        renderer.get("accepted_shape"),
        "renderer.accepted_shape",
    )
    try:
        descriptor = resolve_view_renderer(renderer_id, renderer_version)
    except ViewRendererError as exc:
        raise ValueError(
            f"typed_prompt_input_renderer_unknown: {exc}"
        ) from exc
    if accepted_shape != descriptor.accepted_shape:
        raise ValueError(
            "typed_prompt_input_renderer_shape_mismatch: "
            f"renderer `{renderer_id}` expects `{descriptor.accepted_shape}`"
        )
    injection_order = normalized.get("injection_order")
    if not isinstance(injection_order, int) or injection_order < 0:
        raise ValueError("typed_prompt_input_schema_invalid: injection_order must be a non-negative integer")
    value_source = dict(cast_mapping(normalized["value_source"]))
    binding_source = _normalize_typed_prompt_input_binding_source(value_source)
    normalized["renderer"] = {
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "accepted_shape": accepted_shape,
    }
    normalized["binding_name"] = str(normalized["binding_name"])
    normalized["value_type_name"] = str(normalized["value_type_name"])
    normalized["source_map_origin_key"] = str(normalized["source_map_origin_key"])
    normalized["u0_row_id"] = str(normalized["u0_row_id"])
    normalized["c0_row_id"] = str(normalized["c0_row_id"])
    normalized["injection_order"] = injection_order
    normalized["value_source"] = binding_source
    return normalized


def typed_prompt_input_value_digest(value: Any) -> str:
    """Return one deterministic digest for one resolved typed prompt value."""

    if isinstance(value, str):
        payload = value.encode("utf-8")
    else:
        try:
            payload = canonical_json_for_pure_value(value).encode("utf-8")
        except Exception as exc:
            raise ValueError(
                "typed_prompt_input_value_unavailable: resolved typed prompt input is not JSON-like"
            ) from exc
    return f"sha256:{sha256(payload).hexdigest()}"


def render_typed_prompt_inputs(
    entries: Sequence[Mapping[str, Any]],
    *,
    resolved_typed_values: Mapping[str, Any],
    workflow_name: str,
    step_id: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Render typed prompt-input blocks and structured runtime evidence."""

    normalized_entries = sorted(
        (normalize_typed_prompt_input_entry(entry) for entry in entries),
        key=lambda item: (item["injection_order"], item["binding_name"]),
    )
    rendered_blocks: list[str] = []
    evidence_payloads: list[dict[str, Any]] = []
    for entry in normalized_entries:
        binding_name = entry["binding_name"]
        if binding_name not in resolved_typed_values:
            raise ValueError(
                f"typed_prompt_input_value_unavailable: missing resolved typed value for `{binding_name}`"
            )
        resolved_value = resolved_typed_values[binding_name]
        value_digest = typed_prompt_input_value_digest(resolved_value)
        renderer = entry["renderer"]
        try:
            rendered_bytes = render_view(
                str(renderer["renderer_id"]),
                int(renderer["renderer_version"]),
                resolved_value,
            )
        except ViewRendererError as exc:
            code = (
                "typed_prompt_input_renderer_shape_mismatch"
                if exc.code == "view_value_shape_invalid"
                else "typed_prompt_input_renderer_unknown"
            )
            raise ValueError(f"{code}: {exc}") from exc
        rendered_text = rendered_bytes.decode("utf-8").rstrip("\n")
        rendered_blocks.append(
            "\n".join(
                (
                    f"## Typed Prompt Input: {binding_name}",
                    rendered_text,
                )
            )
        )
        evidence_payloads.append(
            {
                "schema_version": TYPED_PROMPT_INPUT_EVIDENCE_SCHEMA_VERSION,
                "workflow_name": workflow_name,
                "step_id": step_id,
                "binding_name": binding_name,
                "renderer": dict(renderer),
                "value_type_name": entry["value_type_name"],
                "value_digest": value_digest,
                "rendered_bytes_digest": view_bytes_digest(rendered_bytes),
                "evidence_key": view_evidence_key(
                    str(renderer["renderer_id"]),
                    int(renderer["renderer_version"]),
                    VIEW_RENDERER_SCHEMA_VERSION,
                    value_digest,
                ),
                "source_map_origin_key": entry["source_map_origin_key"],
                "u0_row_id": entry["u0_row_id"],
                "c0_row_id": entry["c0_row_id"],
                "injection_order": entry["injection_order"],
                "request_field_evidence": _request_field_evidence_rows(
                    entry=entry,
                    resolved_value=resolved_value,
                ),
            }
        )
    return "\n\n".join(rendered_blocks), evidence_payloads


def build_typed_prompt_input_report(
    *,
    workflow_family: str,
    checked_manifest: Mapping[str, Any],
    checked_manifest_path: str,
    checked_manifest_sha256: str,
    validated_bundles_by_name: Mapping[str, Any],
) -> dict[str, Any]:
    """Reconcile checked prompt-injection rows with compiled typed prompt inputs."""

    selected_manifest_rows = _selected_typed_prompt_input_rows(checked_manifest)
    selected_consume_prompt_rows = _selected_consumed_artifact_prompt_rows(checked_manifest)
    bundle_index = _bundle_index_by_surface_name(validated_bundles_by_name)
    selected_rows: list[dict[str, Any]] = []
    consumed_artifact_prompt_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    stale_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    for row in selected_manifest_rows:
        workflow_surface = row.get("workflow_surface")
        if not isinstance(workflow_surface, str) or not workflow_surface:
            missing_rows.append(
                {
                    "code": "typed_prompt_input_row_missing",
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "reason": "workflow_surface missing from checked row",
                }
            )
            continue
        bundle = bundle_index.get(workflow_surface)
        if bundle is None:
            missing_rows.append(
                {
                    "code": "typed_prompt_input_row_missing",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "reason": "compiled workflow surface is missing",
                }
            )
            continue

        compiled_effect_suffix = _compiled_effect_suffix(row)
        if compiled_effect_suffix and any(
            getattr(step, "kind", None) is SurfaceStepKind.MATERIALIZE_ARTIFACTS
            and isinstance(getattr(step, "step_id", None), str)
            and step.step_id.endswith(compiled_effect_suffix)
            for step in bundle.surface.steps
        ):
            stale_rows.append(
                {
                    "code": "typed_prompt_input_materialization_still_required",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "step_id_suffix": compiled_effect_suffix,
                }
            )
            continue

        matching_entries: list[dict[str, Any]] = []
        provider_step_id: str | None = None
        for step in _iter_surface_steps(bundle.surface.steps):
            if getattr(step, "kind", None) is not SurfaceStepKind.PROVIDER:
                continue
            raw_entries = getattr(step, "typed_prompt_inputs", ()) or ()
            normalized_entries: list[dict[str, Any]] = []
            for entry in raw_entries:
                if not isinstance(entry, Mapping):
                    continue
                try:
                    normalized_entries.append(normalize_typed_prompt_input_entry(entry))
                except ValueError:
                    continue
            row_entries = [
                entry
                for entry in normalized_entries
                if entry["c0_row_id"] == row.get("row_id")
                and entry["u0_row_id"] == row.get("u0_row_id")
            ]
            if row_entries:
                provider_step_id = getattr(step, "step_id", None)
                matching_entries.extend(row_entries)

        if not matching_entries:
            missing_rows.append(
                {
                    "code": "typed_prompt_input_row_missing",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "reason": "compiled provider step typed_prompt_inputs missing",
                }
            )
            continue

        renderer = row.get("renderer")
        renderer_id = renderer.get("renderer_id") if isinstance(renderer, Mapping) else None
        renderer_version = renderer.get("renderer_version") if isinstance(renderer, Mapping) else None
        accepted_shape = renderer.get("accepted_shape") if isinstance(renderer, Mapping) else None
        mismatched = [
            entry
            for entry in matching_entries
            if entry["renderer"]["renderer_id"] != renderer_id
            or entry["renderer"]["renderer_version"] != renderer_version
            or entry["renderer"]["accepted_shape"] != accepted_shape
            or not entry.get("source_map_origin_key")
        ]
        if mismatched:
            invalid_rows.append(
                {
                    "code": "typed_prompt_input_source_map_missing"
                    if any(not entry.get("source_map_origin_key") for entry in mismatched)
                    else "typed_prompt_input_renderer_shape_mismatch",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                }
            )
            continue

        compiled_request_fields = _compiled_request_fields(matching_entries)
        hidden_bridge_diagnostics = _validate_hidden_bridge_request_fields(
            row=row,
            compiled_request_fields=compiled_request_fields,
            workflow_surface=workflow_surface,
        )
        if hidden_bridge_diagnostics:
            invalid_rows.extend(hidden_bridge_diagnostics)
            continue

        selected_row = {
            "workflow_surface": workflow_surface,
            "provider_step_id": provider_step_id,
            "c0_row_id": row.get("row_id"),
            "u0_row_id": row.get("u0_row_id"),
            "binding_names": [entry["binding_name"] for entry in matching_entries],
            "renderer": dict(matching_entries[0]["renderer"]),
            "source_map_origin_keys": sorted(
                {entry["source_map_origin_key"] for entry in matching_entries}
            ),
        }
        if compiled_request_fields:
            selected_row["request_fields"] = compiled_request_fields
        selected_rows.append(selected_row)

    for row in selected_consume_prompt_rows:
        workflow_surface = row.get("workflow_surface")
        artifact_name = row.get("artifact_name")
        if not isinstance(workflow_surface, str) or not workflow_surface:
            continue
        if not isinstance(artifact_name, str) or not artifact_name:
            continue
        bundle = bundle_index.get(workflow_surface)
        if bundle is None:
            continue

        matched_step: Any | None = None
        matched_policy: Any | None = None
        matched_consumes: Sequence[Any] = ()
        for step in _iter_surface_steps(bundle.surface.steps):
            if getattr(step, "kind", None) is not SurfaceStepKind.PROVIDER:
                continue
            consumes = _surface_step_consumes(step)
            for consume in consumes:
                if not isinstance(consume, Mapping):
                    continue
                policy = normalize_consume_prompt_policy(consume)
                if policy.artifact_name != artifact_name:
                    continue
                matched_step = step
                matched_policy = policy
                matched_consumes = consumes
                break
            else:
                continue
            break

        if matched_step is None or matched_policy is None:
            missing_rows.append(
                {
                    "code": "typed_prompt_input_row_missing",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "reason": "compiled provider step consumes row missing",
                }
            )
            continue

        sample_value = _consume_prompt_sample_value(row)
        prompt_filter_omission = _consume_prompt_filter_omission_reason(
            matched_step,
            matched_consumes,
            artifact_name=artifact_name,
        )
        omission_reason: str | None = prompt_filter_omission
        rendered_policy = "omitted"
        rendered_bytes_count: int | None = None
        rendered_value_digest: str | None = None
        rendered_value_reference: str | None = None
        if omission_reason is None:
            if matched_policy.mode == "none":
                omission_reason = "mode_none"
            elif sample_value is _MISSING_SAMPLE_VALUE:
                omission_reason = "sample_value_missing"
            else:
                rendered_value = stringify_consumed_value(sample_value)
                if rendered_value is None:
                    omission_reason = "render_value_unavailable"
                else:
                    rendered_policy = (
                        "rendered_reference"
                        if matched_policy.mode == "reference"
                        else "rendered_content"
                    )
                    rendered_bytes_count = len(rendered_value.encode("utf-8"))
                    rendered_value_digest = typed_prompt_input_value_digest(sample_value)
                    if matched_policy.mode == "reference" and isinstance(sample_value, str):
                        rendered_value_reference = sample_value

        evidence_row: dict[str, Any] = {
            "workflow_surface": workflow_surface,
            "provider_step_id": getattr(matched_step, "step_id", None),
            "c0_row_id": row.get("row_id"),
            "u0_row_id": row.get("u0_row_id"),
            "artifact_name": artifact_name,
            "mode": matched_policy.mode,
            "label": matched_policy.label,
            "role": matched_policy.role,
            "value_kind": _consume_prompt_value_kind(
                bundle,
                artifact_name=artifact_name,
                sample_value=sample_value,
            ),
            "rendered_policy": rendered_policy,
            "rendered_bytes_count": rendered_bytes_count,
            "rendered_value_digest": rendered_value_digest,
            "omission_reason": omission_reason,
        }
        if rendered_value_reference is not None:
            evidence_row["rendered_value_reference"] = rendered_value_reference
        consumed_artifact_prompt_rows.append(evidence_row)

    return {
        "schema_version": TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "checked_manifest": {
            "path": checked_manifest_path,
            "sha256": checked_manifest_sha256,
        },
        "selected_rows": selected_rows,
        "consumed_artifact_prompt_rows": consumed_artifact_prompt_rows,
        "missing_rows": missing_rows,
        "stale_rows": stale_rows,
        "invalid_rows": invalid_rows,
        "status": "pass" if not (missing_rows or stale_rows or invalid_rows) else "fail",
    }


def cast_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return value


def _request_field_evidence_rows(
    *,
    entry: Mapping[str, Any],
    resolved_value: Any,
) -> list[dict[str, Any]]:
    request_fields = entry.get("request_fields")
    if not isinstance(request_fields, Mapping):
        return []
    field_authority = request_fields.get("field_authority")
    if not isinstance(field_authority, Mapping):
        return []
    evidence_rows: list[dict[str, Any]] = []
    for field_path in sorted(
        str(path) for path in field_authority if isinstance(path, str) and path
    ):
        metadata = field_authority.get(field_path)
        if not isinstance(metadata, Mapping):
            continue
        leaf_value = _resolve_request_field_value(resolved_value, field_path)
        evidence_row = {
            "field_path": field_path,
            "authority_class": str(metadata.get("authority_class", "")),
            "source_binding": str(metadata.get("source_binding", "")),
            "bridge_field_name": str(metadata.get("bridge_field_name", "")),
            "rendered_leaf_shape": _rendered_leaf_shape(
                leaf_value,
                field_path=field_path,
            ),
            "rendered_leaf_digest": typed_prompt_input_value_digest(leaf_value),
        }
        checked_row_id = metadata.get("checked_row_id")
        if isinstance(checked_row_id, str) and checked_row_id:
            evidence_row["checked_row_id"] = checked_row_id
        evidence_rows.append(evidence_row)
    return evidence_rows


def _resolve_request_field_value(value: Any, field_path: str) -> Any:
    current = value
    for segment in field_path.split("."):
        if not isinstance(current, Mapping) or segment not in current:
            raise ValueError(
                "typed_prompt_input_hidden_bridge_field_missing: "
                f"missing rendered request field `{field_path}`"
            )
        current = current[segment]
    return current


def _rendered_leaf_shape(value: Any, *, field_path: str) -> str:
    if isinstance(value, str):
        return "scalar_path"
    if isinstance(value, Mapping) and isinstance(value.get("ref"), str):
        return "ref_object"
    raise ValueError(
        "typed_prompt_input_hidden_bridge_leaf_shape_invalid: "
        f"rendered request field `{field_path}` is not path-like"
    )


def _compiled_request_fields(entries: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not entries:
        return {}
    request_fields = entries[0].get("request_fields")
    return dict(request_fields) if isinstance(request_fields, Mapping) else {}


def _validate_hidden_bridge_request_fields(
    *,
    row: Mapping[str, Any],
    compiled_request_fields: Mapping[str, Any],
    workflow_surface: str,
) -> list[dict[str, Any]]:
    expectations = row.get("request_field_expectations")
    if not isinstance(expectations, Sequence) or isinstance(expectations, (str, bytes)):
        return []
    field_authority = (
        dict(compiled_request_fields.get("field_authority", {}))
        if isinstance(compiled_request_fields.get("field_authority"), Mapping)
        else {}
    )
    diagnostics: list[dict[str, Any]] = []
    for expectation in expectations:
        if not isinstance(expectation, Mapping):
            continue
        field_path = expectation.get("field_path")
        if not isinstance(field_path, str) or not field_path:
            continue
        compiled = field_authority.get(field_path)
        if not isinstance(compiled, Mapping):
            diagnostics.append(
                {
                    "code": "typed_prompt_input_hidden_bridge_field_missing",
                    "workflow_surface": workflow_surface,
                    "c0_row_id": row.get("row_id"),
                    "u0_row_id": row.get("u0_row_id"),
                    "field_path": field_path,
                }
            )
            continue
        expected_authority = expectation.get("authority_class")
        if isinstance(expected_authority, str) and expected_authority:
            observed_authority = compiled.get("authority_class")
            if observed_authority != expected_authority:
                diagnostics.append(
                    {
                        "code": "typed_prompt_input_hidden_bridge_authority_mismatch",
                        "workflow_surface": workflow_surface,
                        "c0_row_id": row.get("row_id"),
                        "u0_row_id": row.get("u0_row_id"),
                        "field_path": field_path,
                        "expected_authority_class": expected_authority,
                        "observed_authority_class": observed_authority,
                    }
                )
                continue
        expected_source = expectation.get("source_binding")
        if isinstance(expected_source, str) and expected_source:
            observed_source = compiled.get("source_binding")
            if observed_source != expected_source:
                diagnostics.append(
                    {
                        "code": "typed_prompt_input_hidden_bridge_source_unmapped",
                        "workflow_surface": workflow_surface,
                        "c0_row_id": row.get("row_id"),
                        "u0_row_id": row.get("u0_row_id"),
                        "field_path": field_path,
                        "expected_source_binding": expected_source,
                        "observed_source_binding": observed_source,
                    }
                )
                continue
        expected_bridge_field = expectation.get("bridge_field_name")
        if isinstance(expected_bridge_field, str) and expected_bridge_field:
            observed_bridge_field = compiled.get("bridge_field_name")
            if observed_bridge_field != expected_bridge_field:
                diagnostics.append(
                    {
                        "code": "typed_prompt_input_hidden_bridge_bridge_field_mismatch",
                        "workflow_surface": workflow_surface,
                        "c0_row_id": row.get("row_id"),
                        "u0_row_id": row.get("u0_row_id"),
                        "field_path": field_path,
                        "expected_bridge_field_name": expected_bridge_field,
                        "observed_bridge_field_name": observed_bridge_field,
                    }
                )
    return diagnostics


def _surface_step_consumes(step: Any) -> Sequence[Any]:
    consumes = getattr(step, "consumes", None)
    if isinstance(consumes, Sequence) and not isinstance(consumes, (str, bytes)):
        return consumes
    common = getattr(step, "common", None)
    common_consumes = getattr(common, "consumes", None)
    if isinstance(common_consumes, Sequence) and not isinstance(common_consumes, (str, bytes)):
        return common_consumes
    return ()


def _surface_step_provider_session(step: Any) -> Mapping[str, Any] | None:
    provider_session = getattr(step, "provider_session", None)
    if isinstance(provider_session, Mapping):
        return provider_session
    common = getattr(step, "common", None)
    provider_session = getattr(common, "provider_session", None)
    if isinstance(provider_session, Mapping):
        return provider_session
    return None


def _consume_prompt_sample_value(row: Mapping[str, Any]) -> Any:
    sample_source = row.get("typed_value_source")
    if isinstance(sample_source, Mapping):
        for field_name in ("value_document", "sample_value", "value"):
            if field_name in sample_source:
                return sample_source.get(field_name)
    if "sample_value" in row:
        return row.get("sample_value")
    return _MISSING_SAMPLE_VALUE


def _consume_prompt_filter_omission_reason(
    step: Any,
    consumes: Sequence[Any],
    *,
    artifact_name: str,
) -> str | None:
    if getattr(step, "inject_consumes", True) is False:
        return "inject_consumes_disabled"

    prompt_consumes = getattr(step, "prompt_consumes", None)
    if prompt_consumes is not None:
        if not isinstance(prompt_consumes, Sequence) or isinstance(prompt_consumes, (str, bytes)):
            return "prompt_consumes_filtered"
        allowed_names = {
            name for name in prompt_consumes if isinstance(name, str) and name.strip()
        }
        if not allowed_names or artifact_name not in allowed_names:
            return "prompt_consumes_filtered"

    provider_session = _surface_step_provider_session(step)
    if isinstance(provider_session, Mapping) and provider_session.get("mode") == "resume":
        session_id_from = provider_session.get("session_id_from")
        if isinstance(session_id_from, str) and session_id_from == artifact_name:
            return "reserved_session_excluded"

    step_mapping: dict[str, Any] = {
        "consumes": list(consumes),
    }
    if prompt_consumes is not None:
        step_mapping["prompt_consumes"] = list(prompt_consumes)
    if provider_session is not None:
        step_mapping["provider_session"] = dict(provider_session)
    selected = {
        policy.artifact_name
        for policy, _ in selected_consumed_artifacts_for_prompt(
            step_mapping,
            {
                normalize_consume_prompt_policy(consume).artifact_name: ""
                for consume in consumes
                if isinstance(consume, Mapping)
                and normalize_consume_prompt_policy(consume).artifact_name
            },
        )
    }
    if artifact_name not in selected:
        return "not_selected"
    return None


def _consume_prompt_value_kind(
    bundle: Any,
    *,
    artifact_name: str,
    sample_value: Any,
) -> str | None:
    surface = getattr(bundle, "surface", None)
    artifacts = getattr(surface, "artifacts", None)
    contract = artifacts.get(artifact_name) if isinstance(artifacts, Mapping) else None
    for candidate in (
        getattr(contract, "kind", None),
        contract.get("kind") if isinstance(contract, Mapping) else None,
        getattr(contract, "value_type", None),
        (
            contract.definition.get("type")
            if hasattr(getattr(contract, "definition", None), "get")
            else None
        ),
        (
            contract.get("definition", {}).get("type")
            if isinstance(contract, Mapping)
            and isinstance(contract.get("definition"), Mapping)
            else None
        ),
    ):
        if isinstance(candidate, str) and candidate:
            return candidate

    if sample_value is _MISSING_SAMPLE_VALUE:
        return None
    if isinstance(sample_value, bool):
        return "bool"
    if isinstance(sample_value, int):
        return "int"
    if isinstance(sample_value, float):
        return "float"
    if isinstance(sample_value, str):
        return "string"
    if isinstance(sample_value, Mapping):
        return "map"
    if isinstance(sample_value, Sequence) and not isinstance(sample_value, (str, bytes)):
        return "list"
    return type(sample_value).__name__


def _normalize_typed_prompt_input_binding_source(value_source: Mapping[str, Any]) -> dict[str, Any]:
    kind = value_source.get("kind")
    binding: Any
    if "binding" in value_source:
        binding = value_source["binding"]
    elif isinstance(value_source.get("binding_ref"), str):
        binding = {"ref": value_source["binding_ref"]}
    elif isinstance(value_source.get("ref"), str):
        binding = {"ref": value_source["ref"]}
    else:
        raise ValueError("typed_prompt_input_schema_invalid: value_source binding is required")
    return {
        "kind": str(kind) if isinstance(kind, str) and kind else "typed_binding_ref",
        "binding": binding,
    }


def _require_non_empty_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"typed_prompt_input_schema_invalid: {field_name} is required")
    return value


def _selected_typed_prompt_input_rows(
    checked_manifest: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = checked_manifest.get("rows")
    if not isinstance(rows, Sequence):
        return []
    return [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("consumer_lane") == "prompt_injection"
        and row.get("track_c_decision") == "KEEP_TYPED"
    ]


def _selected_consumed_artifact_prompt_rows(
    checked_manifest: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    rows = checked_manifest.get("rows")
    if not isinstance(rows, Sequence):
        return []
    return [
        row
        for row in rows
        if isinstance(row, Mapping)
        and row.get("consumer_lane") == "prompt_injection"
        and row.get("track_c_decision") == "RETIRED_TO_PROMPT_RENDERING"
        and isinstance(row.get("artifact_name"), str)
        and row.get("artifact_name")
    ]


def _compiled_effect_suffix(row: Mapping[str, Any]) -> str | None:
    compiled_effect_match = row.get("compiled_effect_match")
    if not isinstance(compiled_effect_match, Mapping):
        return None
    suffix = compiled_effect_match.get("step_id_suffix")
    return suffix if isinstance(suffix, str) and suffix else None


def _bundle_index_by_surface_name(
    validated_bundles_by_name: Mapping[str, Any],
) -> dict[str, Any]:
    indexed: dict[str, Any] = {}
    visited_bundle_ids: set[int] = set()

    def visit(bundle: Any) -> None:
        bundle_id = id(bundle)
        if bundle_id in visited_bundle_ids:
            return
        visited_bundle_ids.add(bundle_id)

        surface = getattr(bundle, "surface", None)
        surface_name = getattr(surface, "name", None)
        if isinstance(surface_name, str) and surface_name:
            indexed.setdefault(surface_name, bundle)

        imports = getattr(bundle, "imports", None)
        if not isinstance(imports, Mapping):
            return
        for imported_bundle in imports.values():
            visit(imported_bundle)

    for bundle in validated_bundles_by_name.values():
        visit(bundle)
    return indexed


def _iter_surface_steps(steps: Sequence[Any]) -> Sequence[Any]:
    flat_steps: list[Any] = []

    def visit(step: Any) -> None:
        flat_steps.append(step)

        repeat_until = getattr(step, "repeat_until", None)
        if repeat_until is not None:
            for child in getattr(repeat_until, "steps", ()) or ():
                visit(child)

        then_branch = getattr(step, "then_branch", None)
        if then_branch is not None:
            for child in getattr(then_branch, "steps", ()) or ():
                visit(child)

        else_branch = getattr(step, "else_branch", None)
        if else_branch is not None:
            for child in getattr(else_branch, "steps", ()) or ():
                visit(child)

        for child in getattr(step, "for_each_steps", ()) or ():
            visit(child)

        match_cases = getattr(step, "match_cases", None)
        if isinstance(match_cases, Mapping):
            for case in match_cases.values():
                for child in getattr(case, "steps", ()) or ():
                    visit(child)

    for step in steps:
        visit(step)
    return flat_steps
