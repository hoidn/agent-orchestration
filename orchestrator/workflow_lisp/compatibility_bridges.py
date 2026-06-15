"""Checked C4 compatibility-bridge manifest validation and reporting."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from orchestrator.workflow.view_renderer import resolve_view_renderer


COMPATIBILITY_BRIDGE_METADATA_SCHEMA_VERSION = (
    "workflow_lisp_compatibility_bridge_metadata.v1"
)
COMPATIBILITY_BRIDGE_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_compatibility_bridge_report.v1"
)


def select_compatibility_bridge_rows(
    census_payload: object,
) -> list[dict[str, object]]:
    if not isinstance(census_payload, Mapping):
        return []
    rows = census_payload.get("rows")
    if not isinstance(rows, Sequence):
        return []
    selected: list[dict[str, object]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if row.get("consumer_lane") == "compatibility_bridge" or row.get(
            "track_c_decision"
        ) == "RETIRE_TO_BRIDGE_METADATA":
            selected.append(dict(row))
    return selected


def load_compatibility_bridge_manifest(
    path: Path,
    *,
    value_flow_census: Mapping[str, Any],
    consumer_rendering_census: Mapping[str, Any],
    command_boundary_manifest: Mapping[str, Any],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: manifest must be a JSON object"
        )
    if payload.get("schema_version") != COMPATIBILITY_BRIDGE_METADATA_SCHEMA_VERSION:
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: expected schema_version "
            f"{COMPATIBILITY_BRIDGE_METADATA_SCHEMA_VERSION}"
        )
    if payload.get("target_family") != "lisp_frontend_design_delta_parent_drain":
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: expected Design Delta target_family"
        )
    _validate_source_reference(
        payload.get("source_census"),
        expected_schema="workflow_lisp_private_runtime_value_flow_census.v1",
        field_name="source_census",
    )
    _validate_source_reference(
        payload.get("source_consumer_rendering_census"),
        expected_schema="workflow_lisp_consumer_rendering_census.v1",
        field_name="source_consumer_rendering_census",
    )
    raw_rows = payload.get("bridges")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: bridges must be a non-empty array"
        )

    selected_rows = {
        str(row.get("row_id", "")): row
        for row in select_compatibility_bridge_rows(consumer_rendering_census)
        if isinstance(row.get("row_id"), str)
    }
    u0_rows = {
        str(row.get("row_id", "")): row
        for row in value_flow_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    seen_bridge_ids: set[str] = set()
    seen_c0_row_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"bridges[{index}] must be an object"
            )
        row = dict(raw_row)
        bridge_id = _require_string(row, "bridge_id")
        if bridge_id in seen_bridge_ids:
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"duplicate bridge_id `{bridge_id}`"
            )
        seen_bridge_ids.add(bridge_id)
        c0_row_id = _require_string(row, "c0_row_id")
        if c0_row_id in seen_c0_row_ids:
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"duplicate c0_row_id `{c0_row_id}`"
            )
        seen_c0_row_ids.add(c0_row_id)
        selected_row = selected_rows.get(c0_row_id)
        if selected_row is None:
            raise ValueError(
                "compatibility_bridge_c0_row_missing: "
                f"manifest row `{bridge_id}` references missing C0 row `{c0_row_id}`"
            )
        u0_row_id = _require_string(row, "u0_row_id")
        if selected_row.get("u0_row_id") != u0_row_id:
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"manifest row `{bridge_id}` no longer matches C0/U0 lineage"
            )
        if u0_row_id not in u0_rows:
            raise ValueError(
                "compatibility_bridge_c0_row_missing: "
                f"manifest row `{bridge_id}` references missing U0 row `{u0_row_id}`"
            )
        workflow_surface = _require_string(row, "workflow_surface")
        if workflow_surface != selected_row.get("workflow_surface"):
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"manifest row `{bridge_id}` workflow_surface drifted from checked C0 row"
            )
        bridge_owner = _require_string(row, "bridge_owner")
        consumer = _require_string(row, "consumer")
        file_shape = _require_string(row, "file_shape")
        bridge_metadata = selected_row.get("bridge")
        if isinstance(bridge_metadata, Mapping):
            if bridge_owner != bridge_metadata.get("bridge_owner"):
                raise ValueError(
                    "compatibility_bridge_metadata_schema_invalid: "
                    f"manifest row `{bridge_id}` bridge_owner drifted from checked C0 row"
                )
            if consumer != bridge_metadata.get("consumer"):
                raise ValueError(
                    "compatibility_bridge_metadata_schema_invalid: "
                    f"manifest row `{bridge_id}` consumer drifted from checked C0 row"
                )
            if file_shape != bridge_metadata.get("file_shape"):
                raise ValueError(
                    "compatibility_bridge_metadata_schema_invalid: "
                    f"manifest row `{bridge_id}` file_shape drifted from checked C0 row"
                )
        typed_value_source = _require_mapping(row, "typed_value_source")
        _validate_typed_value_source(
            bridge_id=bridge_id,
            typed_value_source=typed_value_source,
        )
        renderer = _require_mapping(row, "renderer")
        renderer_id = _require_string(renderer, "renderer_id")
        renderer_version = _require_int(renderer, "renderer_version")
        accepted_shape = _require_string(renderer, "accepted_shape")
        descriptor = resolve_view_renderer(renderer_id, renderer_version)
        if descriptor.accepted_shape != accepted_shape:
            raise ValueError(
                "compatibility_bridge_renderer_shape_mismatch: "
                f"manifest row `{bridge_id}` declares `{accepted_shape}` but renderer "
                f"expects `{descriptor.accepted_shape}`"
            )
        target = _require_mapping(row, "target")
        if _require_string(target, "authority_class") != "compatibility_bridge":
            raise ValueError(
                "compatibility_bridge_metadata_schema_invalid: "
                f"manifest row `{bridge_id}` must declare authority_class "
                "`compatibility_bridge`"
            )
        _require_string(target, "kind")
        _require_string(target, "durability")
        retirement = _require_mapping(row, "retirement")
        _require_string(retirement, "allowed_when")
        _require_string(retirement, "replacement_target")
        command_boundary = _require_mapping_or_none(row, "command_boundary")
        if (
            selected_row.get("source_kind") == "command_adapter_input"
            or selected_row.get("track_c_decision") == "BLOCKED"
        ):
            if not isinstance(command_boundary, Mapping):
                raise ValueError(
                    "compatibility_bridge_required_metadata_missing: "
                    f"manifest row `{bridge_id}` must declare command_boundary metadata"
                )
        if isinstance(command_boundary, Mapping):
            binding_name = _require_string(command_boundary, "binding_name")
            if (
                isinstance(selected_row.get("command_boundary"), Mapping)
                and binding_name
                != selected_row["command_boundary"].get("binding_name")
            ):
                raise ValueError(
                    "compatibility_bridge_metadata_schema_invalid: "
                    f"manifest row `{bridge_id}` command boundary drifted from checked C0 row"
                )
            manifest_binding = command_boundary_manifest.get(binding_name)
            if not isinstance(manifest_binding, Mapping) or manifest_binding.get(
                "kind"
            ) != "certified_adapter":
                raise ValueError(
                    "compatibility_bridge_command_boundary_uncertified: "
                    f"manifest row `{bridge_id}` references uncertified binding `{binding_name}`"
                )
        normalized_rows.append(row)

    missing_c0_row_ids = sorted(set(selected_rows) - seen_c0_row_ids)
    if missing_c0_row_ids:
        raise ValueError(
            "compatibility_bridge_required_metadata_missing: "
            "selected C0 compatibility rows missing checked bridge metadata: "
            + ", ".join(missing_c0_row_ids)
        )

    normalized_rows.sort(key=lambda row: str(row["bridge_id"]))
    return {
        **payload,
        "bridges": normalized_rows,
        "__manifest_path__": str(path.resolve()),
        "__manifest_sha256__": _sha256_file(path.resolve()),
    }


def build_compatibility_bridge_report(
    *,
    workflow_family: str,
    manifest: Mapping[str, Any],
    consumer_rendering_census: Mapping[str, Any],
    command_boundary_manifest: Mapping[str, Any],
    workflow_boundary_projection: Mapping[str, Any] | None = None,
    source_map_payload: Mapping[str, Any] | None = None,
    materialize_view_effects: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    selected_rows_by_id = {
        str(row.get("row_id", "")): row
        for row in select_compatibility_bridge_rows(consumer_rendering_census)
        if isinstance(row.get("row_id"), str)
    }
    projection_workflows = _projection_workflows(workflow_boundary_projection)
    source_map_workflows = _source_map_workflows(source_map_payload)
    report_selected_rows: list[dict[str, object]] = []
    generated_bridges: list[dict[str, object]] = []
    blocked_bridges: list[dict[str, object]] = []
    diagnostics: list[dict[str, object]] = []
    orphan_bridge_files: list[dict[str, object]] = []
    bridge_workflows: set[str] = set()
    all_row_ids: set[str] = set()
    manifest_row_ids: set[str] = set()

    for raw_row in manifest.get("bridges", []):
        if not isinstance(raw_row, Mapping):
            continue
        row = dict(raw_row)
        c0_row_id = str(row.get("c0_row_id", ""))
        manifest_row_ids.add(c0_row_id)
        selected_row = selected_rows_by_id.get(c0_row_id)
        if selected_row is None:
            orphan_bridge_files.append(
                {
                    "bridge_id": str(row.get("bridge_id", "")),
                    "c0_row_id": c0_row_id,
                }
            )
            diagnostics.append(
                {
                    "code": "compatibility_bridge_orphan_file",
                    "bridge_id": str(row.get("bridge_id", "")),
                    "c0_row_id": c0_row_id,
                    "message": "manifest row is no longer backed by a selected C0 compatibility row",
                }
            )
            continue
        report_selected_rows.append(dict(selected_row))
        all_row_ids.add(c0_row_id)
        workflow_surface = str(row.get("workflow_surface", ""))
        if workflow_surface:
            bridge_workflows.add(workflow_surface)
        report_row = {
            "bridge_id": str(row.get("bridge_id", "")),
            "c0_row_id": c0_row_id,
            "u0_row_id": str(row.get("u0_row_id", "")),
            "workflow_surface": workflow_surface,
            "bridge_owner": str(row.get("bridge_owner", "")),
            "consumer": str(row.get("consumer", "")),
            "file_shape": str(row.get("file_shape", "")),
            "renderer": _json_data(row.get("renderer", {})),
            "typed_value_source": _json_data(row.get("typed_value_source", {})),
            "target": _json_data(row.get("target", {})),
            "retirement": _json_data(row.get("retirement", {})),
        }
        command_boundary = row.get("command_boundary")
        if (
            isinstance(command_boundary, Mapping)
            or selected_row.get("track_c_decision") == "BLOCKED"
        ):
            binding_name = (
                str(command_boundary.get("binding_name", ""))
                if isinstance(command_boundary, Mapping)
                else ""
            )
            if binding_name:
                binding = command_boundary_manifest.get(binding_name)
                report_row["command_boundary"] = {
                    "binding_name": binding_name,
                    "kind": binding.get("kind") if isinstance(binding, Mapping) else None,
                }
            blocked_bridges.append(report_row)
        else:
            generated_bridges.append(report_row)

    report_selected_rows = [
        dict(row)
        for _, row in sorted(selected_rows_by_id.items(), key=lambda item: item[0])
    ]
    missing_selected_rows = sorted(set(selected_rows_by_id) - manifest_row_ids)
    for c0_row_id in missing_selected_rows:
        diagnostics.append(
            {
                "code": "compatibility_bridge_required_metadata_missing",
                "c0_row_id": c0_row_id,
                "message": "selected C0 compatibility row is missing checked bridge metadata",
            }
        )

    report_selected_rows.sort(key=lambda row: str(row.get("row_id", "")))
    generated_bridges.sort(key=lambda row: str(row.get("bridge_id", "")))
    blocked_bridges.sort(key=lambda row: str(row.get("bridge_id", "")))
    orphan_bridge_files.sort(key=lambda row: str(row.get("bridge_id", "")))
    contract_isolation = {
        "workflow_signature_unchanged": all(
            workflow_name in projection_workflows for workflow_name in bridge_workflows
        ),
        "call_contract_unchanged": all(
            str(row["command_boundary"].get("kind", "")) == "certified_adapter"
            for row in blocked_bridges
            if isinstance(row.get("command_boundary"), Mapping)
        ),
        "boundary_projection_public_inputs_unchanged": all(
            not _projection_workflow_mentions_bridge_public_inputs(
                projection_workflows.get(workflow_name)
            )
            for workflow_name in bridge_workflows
        ),
        "typed_steps_do_not_consume_bridge_views": all(
            _workflow_has_bridge_allocation_evidence(
                workflow_name=str(row.get("workflow_surface", "")),
                source_map_workflows=source_map_workflows,
                materialize_view_effects=materialize_view_effects,
            )
            for row in generated_bridges
            if isinstance(row, Mapping)
        ),
    }
    for check_name, passed in contract_isolation.items():
        if passed:
            continue
        diagnostics.append(
            {
                "code": "compatibility_bridge_contract_leak",
                "c0_row_id": ",".join(sorted(all_row_ids)) if all_row_ids else "",
                "message": f"compatibility bridge contract check failed: {check_name}",
            }
        )
    return {
        "schema_version": COMPATIBILITY_BRIDGE_REPORT_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "fail",
        "workflow_family": workflow_family,
        "checked_manifest": {
            "path": str(manifest.get("__manifest_path__", "")),
            "sha256": (
                f"sha256:{manifest.get('__manifest_sha256__', '')}"
                if manifest.get("__manifest_sha256__")
                else ""
            ),
            "schema_version": str(manifest.get("schema_version", "")),
        },
        "selected_c0_rows": report_selected_rows,
        "generated_bridges": generated_bridges,
        "retired_bridges": [],
        "blocked_bridges": blocked_bridges,
        "orphan_bridge_files": orphan_bridge_files,
        "contract_isolation": contract_isolation,
        "diagnostics": diagnostics,
    }


def _validate_source_reference(
    raw_ref: object,
    *,
    expected_schema: str,
    field_name: str,
) -> None:
    if not isinstance(raw_ref, Mapping):
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"{field_name} must be an object"
        )
    ref = dict(raw_ref)
    _require_string(ref, "path")
    if _require_string(ref, "schema_version") != expected_schema:
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"{field_name}.schema_version must be `{expected_schema}`"
        )


def _require_mapping(container: Mapping[str, object], field_name: str) -> dict[str, Any]:
    value = container.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"`{field_name}` must be an object"
        )
    return dict(value)


def _require_mapping_or_none(
    container: Mapping[str, object],
    field_name: str,
) -> dict[str, Any] | None:
    value = container.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"`{field_name}` must be an object when present"
        )
    return dict(value)


def _require_string(container: Mapping[str, object], field_name: str) -> str:
    value = container.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"`{field_name}` must be a non-empty string"
        )
    return value


def _require_int(container: Mapping[str, object], field_name: str) -> int:
    value = container.get(field_name)
    if not isinstance(value, int):
        raise ValueError(
            "compatibility_bridge_metadata_schema_invalid: "
            f"`{field_name}` must be an integer"
        )
    return value


def _validate_typed_value_source(
    *,
    bridge_id: str,
    typed_value_source: Mapping[str, object],
) -> None:
    kind = _require_string(typed_value_source, "kind")
    has_locator = False
    ref = typed_value_source.get("ref")
    if isinstance(ref, str) and ref.strip():
        has_locator = True
    value_document = typed_value_source.get("value_document")
    if value_document is not None:
        has_locator = True
    source_ref = typed_value_source.get("source_ref")
    if isinstance(source_ref, str) and source_ref.strip():
        has_locator = True
    typed_source = typed_value_source.get("typed_source")
    if isinstance(typed_source, Mapping) and typed_source:
        has_locator = True
    field_path = typed_value_source.get("field_path")
    if (
        isinstance(field_path, Sequence)
        and not isinstance(field_path, (str, bytes))
        and any(isinstance(part, str) and part.strip() for part in field_path)
    ):
        has_locator = True
    if not has_locator:
        raise ValueError(
            "compatibility_bridge_typed_source_missing: "
            f"manifest row `{bridge_id}` typed_value_source `{kind}` must declare "
            "a ref or typed source locator"
        )


def _json_data(value: object) -> object:
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_data(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _projection_workflows(
    payload: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    workflows = payload.get("workflows")
    if not isinstance(workflows, Sequence):
        return {}
    return {
        str(workflow.get("workflow_name")): workflow
        for workflow in workflows
        if isinstance(workflow, Mapping) and isinstance(workflow.get("workflow_name"), str)
    }


def _source_map_workflows(
    payload: Mapping[str, Any] | None,
) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    workflows = payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return {}
    return {
        str(workflow_name): workflow
        for workflow_name, workflow in workflows.items()
        if isinstance(workflow_name, str) and isinstance(workflow, Mapping)
    }


def _projection_workflow_mentions_bridge_public_inputs(
    workflow: Mapping[str, Any] | None,
) -> bool:
    if not isinstance(workflow, Mapping):
        return True
    boundary = workflow.get("boundary")
    if not isinstance(boundary, Mapping):
        return True
    public_inputs = boundary.get("public_input_names")
    if not isinstance(public_inputs, Sequence):
        return True
    return any(
        isinstance(name, str) and ("bridge" in name or "selection_bundle" in name)
        for name in public_inputs
    )


def _workflow_has_bridge_allocation_evidence(
    *,
    workflow_name: str,
    source_map_workflows: Mapping[str, Mapping[str, Any]],
    materialize_view_effects: Sequence[Mapping[str, Any]],
) -> bool:
    workflow = source_map_workflows.get(workflow_name)
    if not isinstance(workflow, Mapping):
        return False
    generated_effects = workflow.get("generated_semantic_effects")
    allocations = workflow.get("generated_path_allocations")
    if not isinstance(generated_effects, Sequence) or not isinstance(allocations, Sequence):
        return False
    allocation_ids = {
        str(allocation.get("allocation_id", ""))
        for allocation in allocations
        if isinstance(allocation, Mapping)
        and allocation.get("semantic_role") == "materialized_value_view"
        and isinstance(allocation.get("allocation_id"), str)
        and allocation.get("allocation_id")
    }
    if not allocation_ids:
        return False
    if any(
        isinstance(effect, Mapping)
        and effect.get("effect_kind") == "materialize_view"
        and isinstance(effect.get("details"), Mapping)
        and effect["details"].get("authority_class") == "compatibility_bridge"
        and str(
            effect["details"].get(
                "target_allocation_id",
                effect["details"].get("allocation_id", ""),
            )
        )
        in allocation_ids
        for effect in generated_effects
    ):
        return True
    return False
