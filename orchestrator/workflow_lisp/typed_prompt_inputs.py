"""Workflow Lisp typed prompt input helpers and deterministic rendering."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from hashlib import sha256
from typing import Any

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
    selected_rows: list[dict[str, Any]] = []
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
        bundle = validated_bundles_by_name.get(workflow_surface)
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
        for step in bundle.surface.steps:
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

        selected_rows.append(
            {
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
        )

    return {
        "schema_version": TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "checked_manifest": {
            "path": checked_manifest_path,
            "sha256": checked_manifest_sha256,
        },
        "selected_rows": selected_rows,
        "missing_rows": missing_rows,
        "stale_rows": stale_rows,
        "invalid_rows": invalid_rows,
        "status": "pass" if not (missing_rows or stale_rows or invalid_rows) else "fail",
    }


def cast_mapping(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return value


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


def _compiled_effect_suffix(row: Mapping[str, Any]) -> str | None:
    compiled_effect_match = row.get("compiled_effect_match")
    if not isinstance(compiled_effect_match, Mapping):
        return None
    suffix = compiled_effect_match.get("step_id_suffix")
    return suffix if isinstance(suffix, str) and suffix else None
