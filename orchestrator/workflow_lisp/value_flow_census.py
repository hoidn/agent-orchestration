"""Checked U0 value-flow census validation and Design Delta reconciliation."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any


VALUE_FLOW_CENSUS_SCHEMA_VERSION = "workflow_lisp_private_runtime_value_flow_census.v1"
VALUE_FLOW_CENSUS_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_private_runtime_value_flow_census_report.v1"
)
DESIGN_DELTA_PARENT_DRAIN_FAMILY = "lisp_frontend_design_delta_parent_drain"

SOURCE_KINDS = frozenset(
    {
        "public_input",
        "public_output",
        "loop_state_field",
        "record_field",
        "materialized_output",
        "prompt_input_file",
        "summary_report_target",
        "pointer_path",
        "provider_target",
        "command_adapter_input",
        "bridge_file",
        "generated_path",
    }
)
PLUMBING_CLASSES = frozenset(
    {
        "resume_only",
        "domain_resource",
        "prompt_rendering",
        "human_rendering",
        "entry_publication",
        "compatibility_bridge",
        "timed_publication",
        "genuine_external_io",
        "public_authored",
        "generated_internal",
    }
)
BOUNDARY_AUTHORITY_CLASSES = frozenset(
    {
        "public_authored",
        "compatibility_bridge",
        "runtime_derived",
        "generated_internal",
        "materialized_view",
        "public_artifact",
    }
)
RENDER_ONLY_PLUMBING_CLASSES = frozenset(
    {"prompt_rendering", "human_rendering", "entry_publication"}
)
SEMANTIC_AUTHORITY_CLASSES = frozenset({"public_authored", "public_artifact"})
BOUNDARY_EVIDENCE_KINDS = frozenset(
    {
        "boundary_authority_report",
        "compiled_boundary_projection",
        "boundary_authority_registry",
    }
)
BOUNDARY_AUTHORITY_BUCKETS = {
    "public_authored": "public_authored",
    "compatibility_bridge": "compatibility_bridge",
    "runtime_derived": "runtime_derived",
    "generated_internal": "generated_internal",
    "materialized_view": "materialized_view",
    "public_artifact": "public_artifact",
}


def select_resume_plumbing_retirement_candidates(
    census: Mapping[str, Any] | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows = census.get("rows", []) if isinstance(census, Mapping) else census
    return [
        dict(row)
        for row in rows
        if isinstance(row, Mapping)
        and resume_plumbing_retirement_target_status(row) != "NOT_R5_TARGET"
    ]


def resume_plumbing_retirement_target_status(row: Mapping[str, Any]) -> str:
    if row.get("plumbing_class") != "resume_only":
        return "NOT_R5_TARGET"
    if row.get("current_consumer") != "runtime_resume":
        return "NOT_R5_TARGET"
    boundary_authority_class = row.get("boundary_authority_class")
    source_kind = row.get("source_kind")
    if boundary_authority_class in {"runtime_derived", "generated_internal"}:
        return "HIDDEN_PRIVATE"
    if source_kind == "generated_path":
        return "HIDDEN_PRIVATE"
    return "RETIRED"


def validate_resume_plumbing_retirement_decision(
    row: Mapping[str, Any],
    *,
    decision: str,
) -> None:
    if decision not in {
        "RETIRED",
        "HIDDEN_PRIVATE",
        "KEPT_COMPATIBILITY",
        "BLOCKED",
        "NOT_R5_TARGET",
    }:
        raise ValueError(
            f"resume_plumbing_retirement_schema_invalid: unknown decision `{decision}`"
        )
    automatic_status = resume_plumbing_retirement_target_status(row)
    if automatic_status == "NOT_R5_TARGET" and decision != "NOT_R5_TARGET":
        raise ValueError(
            "resume_plumbing_retirement_wrong_track: "
            f"row `{row.get('row_id', '')}` is outside R5 automatic candidate scope"
        )
    if decision in {"KEPT_COMPATIBILITY", "BLOCKED"}:
        bridge = row.get("bridge")
        if not isinstance(bridge, Mapping):
            raise ValueError(
                "resume_plumbing_retirement_compatibility_unjustified: "
                f"row `{row.get('row_id', '')}` requires checked bridge metadata"
            )
        for field_name in (
            "bridge_owner",
            "consumer",
            "file_shape",
            "retirement_condition",
        ):
            if not _non_empty_string(bridge.get(field_name)):
                raise ValueError(
                    "resume_plumbing_retirement_compatibility_unjustified: "
                    f"row `{row.get('row_id', '')}` bridge metadata is missing `{field_name}`"
                )


def normalize_resume_plumbing_retirement_compiled_rows(
    candidate_rows: Iterable[Mapping[str, Any]],
    *,
    boundary_authority_report: Mapping[str, Any],
    source_text_by_surface: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    boundary_rows = _index_boundary_authority_report(boundary_authority_report)
    normalized: dict[str, dict[str, Any]] = {}
    types_source = source_text_by_surface.get("lisp_frontend_design_delta/types", "")
    drain_source = source_text_by_surface.get(
        "lisp_frontend_design_delta/drain::drain", ""
    )
    work_item_source = source_text_by_surface.get(
        "lisp_frontend_design_delta/work_item::run-work-item", ""
    )

    for candidate in candidate_rows:
        row_id = str(candidate.get("row_id", ""))
        normalized_row = {
            "row_id": row_id,
            "workflow_surface": str(candidate.get("workflow_surface", "")),
            "symbol_or_field": str(candidate.get("symbol_or_field", "")),
            "source_kind": str(candidate.get("source_kind", "")),
            "boundary_authority_class": None,
            "observed_locations": [],
            "semantic_authority_source": "typed_runtime_resource",
        }
        if row_id == "drain.loop.run_state_path":
            boundary_row = boundary_rows.get(
                ("lisp_frontend_design_delta/drain::drain", "run_state_path")
            )
            if boundary_row is not None:
                normalized_row["boundary_authority_class"] = boundary_row[
                    "boundary_authority_class"
                ]
                if boundary_row["boundary_authority_class"] == "public_authored":
                    normalized_row["observed_locations"].append("public_boundary")
            drain_state_block = _source_block(
                types_source,
                "(defrecord DrainState",
                "(defunion DrainLoopTerminal",
            )
            if "(run-state RunStatePath)" in drain_state_block:
                normalized_row["observed_locations"].append("loop_state_field")
            if "state.run-state" in drain_source:
                normalized_row["observed_locations"].append("call_signature")
        elif row_id == "work_item.loop.run_state_path":
            boundary_row = boundary_rows.get(
                ("lisp_frontend_design_delta/work_item::run-work-item", "run_state_path")
            )
            if boundary_row is not None:
                normalized_row["boundary_authority_class"] = boundary_row[
                    "boundary_authority_class"
                ]
                if boundary_row["boundary_authority_class"] == "public_authored":
                    normalized_row["observed_locations"].append("public_boundary")
            if (
                "(run_state_path RunStatePath)" in types_source
                and ":run_state_path" in work_item_source
            ):
                normalized_row["observed_locations"].append("call_signature")
        else:
            boundary_row = boundary_rows.get(
                (
                    str(candidate.get("workflow_surface", "")),
                    str(candidate.get("symbol_or_field", "")),
                )
            )
            if boundary_row is not None:
                normalized_row["boundary_authority_class"] = boundary_row[
                    "boundary_authority_class"
                ]
                normalized_row["observed_locations"].append("boundary_report")

        if normalized_row["observed_locations"] or normalized_row["boundary_authority_class"] is not None:
            normalized_row["observed_locations"] = sorted(
                set(normalized_row["observed_locations"])
            )
            normalized[row_id] = normalized_row

    return normalized


def summarize_resume_plumbing_retirement_stale_rows(
    candidate_rows: Iterable[Mapping[str, Any]],
    *,
    compiled_rows: Mapping[str, Mapping[str, Any]] | Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if isinstance(compiled_rows, Mapping):
        compiled_row_ids = {str(row_id) for row_id in compiled_rows}
    else:
        compiled_row_ids = {
            str(row.get("row_id", ""))
            for row in compiled_rows
            if isinstance(row, Mapping)
        }
    stale_rows: list[dict[str, Any]] = []
    for row in candidate_rows:
        row_id = str(row.get("row_id", ""))
        if row_id in compiled_row_ids:
            continue
        stale_rows.append(
            {
                "row_id": row_id,
                "workflow_surface": str(row.get("workflow_surface", "")),
                "symbol_or_field": str(row.get("symbol_or_field", "")),
                "reason": "compiled evidence missing for checked resume-only row",
            }
        )
    return stale_rows


def load_value_flow_census(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("value-flow census must be a JSON object")
    if payload.get("schema_version") != VALUE_FLOW_CENSUS_SCHEMA_VERSION:
        raise ValueError(
            f"expected schema_version {VALUE_FLOW_CENSUS_SCHEMA_VERSION}"
        )
    if payload.get("target_family") != DESIGN_DELTA_PARENT_DRAIN_FAMILY:
        raise ValueError(
            f"expected target_family {DESIGN_DELTA_PARENT_DRAIN_FAMILY}"
        )
    if not _non_empty_string(payload.get("source_design")):
        raise ValueError("source_design is required")
    coverage = _require_mapping(payload, "coverage")
    workflow_surfaces = _require_non_empty_string_list(coverage, "workflow_surfaces")
    required_source_kinds = _require_non_empty_string_list(
        coverage, "required_source_kinds"
    )
    absent_source_kinds = _optional_mapping(coverage, "absent_source_kinds") or {}
    if unknown_source_kinds := sorted(
        kind for kind in required_source_kinds if kind not in SOURCE_KINDS
    ):
        raise ValueError(
            "coverage.required_source_kinds contains unknown source_kind values: "
            + ", ".join(unknown_source_kinds)
        )
    rows = payload.get("rows")
    if not isinstance(rows, list) or not rows:
        raise ValueError("rows must be a non-empty array")
    seen_row_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    covered_source_kinds: set[str] = set()
    covered_workflow_surfaces: set[str] = set()
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"rows[{index}] must be an object")
        row = dict(raw_row)
        row_id = _require_string(row, "row_id")
        if row_id in seen_row_ids:
            raise ValueError(f"duplicate row_id `{row_id}`")
        seen_row_ids.add(row_id)
        source_kind = _require_string(row, "source_kind")
        if source_kind not in SOURCE_KINDS:
            raise ValueError(f"unknown source_kind `{source_kind}` for row `{row_id}`")
        plumbing_class = _require_string(row, "plumbing_class")
        if plumbing_class not in PLUMBING_CLASSES:
            raise ValueError(
                f"unknown plumbing_class `{plumbing_class}` for row `{row_id}`"
            )
        boundary_authority_class = _require_string(row, "boundary_authority_class")
        if boundary_authority_class not in BOUNDARY_AUTHORITY_CLASSES:
            raise ValueError(
                "unknown boundary_authority_class "
                f"`{boundary_authority_class}` for row `{row_id}`"
            )
        workflow_surface = _require_string(row, "workflow_surface")
        if workflow_surface not in workflow_surfaces:
            raise ValueError(
                f"row `{row_id}` references workflow_surface `{workflow_surface}` outside coverage.workflow_surfaces"
            )
        _require_string(row, "symbol_or_field")
        _require_string(row, "path_or_contract")
        _require_string(row, "track_owner")
        _require_string(row, "semantic_owner")
        source_evidence = row.get("source_evidence")
        if not isinstance(source_evidence, list) or not source_evidence:
            raise ValueError(f"row `{row_id}` must declare source_evidence")
        for evidence in source_evidence:
            if not isinstance(evidence, Mapping):
                raise ValueError(f"row `{row_id}` has non-object source_evidence")
            if not _non_empty_string(evidence.get("kind")) or not _non_empty_string(
                evidence.get("path")
            ):
                raise ValueError(
                    f"row `{row_id}` source_evidence entries require kind and path"
                )
        current_consumer = _string_or_none(row.get("current_consumer"))
        if plumbing_class in RENDER_ONLY_PLUMBING_CLASSES and not current_consumer:
            raise ValueError(
                f"row `{row_id}` requires current_consumer for render-only plumbing"
            )
        if plumbing_class == "compatibility_bridge":
            bridge = _require_mapping(row, "bridge")
            _validate_bridge_metadata(bridge, row_id=row_id)
        else:
            if row.get("bridge") not in (None, {}):
                bridge = _require_mapping(row, "bridge")
                _validate_bridge_metadata(bridge, row_id=row_id)
        if plumbing_class == "domain_resource" and not any(
            str(evidence.get("kind", "")).startswith("resource_")
            or str(evidence.get("kind", "")).startswith("transition_")
            for evidence in source_evidence
        ):
            raise ValueError(f"row `{row_id}` needs resource/transition evidence")
        command_boundary = row.get("command_boundary")
        if (
            plumbing_class == "genuine_external_io"
            or source_kind == "command_adapter_input"
        ):
            if not isinstance(command_boundary, Mapping):
                raise ValueError(f"row `{row_id}` requires command-boundary evidence")
            _validate_command_boundary_metadata(command_boundary, row_id=row_id)
        elif command_boundary is not None:
            if not isinstance(command_boundary, Mapping):
                raise ValueError(
                    f"row `{row_id}` command_boundary must be an object when present"
                )
            _validate_command_boundary_metadata(command_boundary, row_id=row_id)
        if (
            source_kind == "pointer_path"
            and boundary_authority_class in SEMANTIC_AUTHORITY_CLASSES
        ):
            raise ValueError(
                f"row `{row_id}` pointer_path cannot be classified as semantic authority"
            )
        if (
            plumbing_class == "resume_only"
            and boundary_authority_class == "public_authored"
        ):
            raise ValueError(
                f"row `{row_id}` resume_only plumbing cannot be public_authored"
            )
        if source_kind == "generated_path" and plumbing_class == "public_authored":
            raise ValueError(
                f"row `{row_id}` leaves generated path-like plumbing unclassified"
            )
        covered_source_kinds.add(source_kind)
        covered_workflow_surfaces.add(workflow_surface)
        normalized_rows.append(row)
    for required_kind in required_source_kinds:
        if required_kind in covered_source_kinds:
            continue
        absent_entry = absent_source_kinds.get(required_kind)
        if not isinstance(absent_entry, Mapping):
            raise ValueError(
                f"required source_kind `{required_kind}` is not represented by rows or checked absence evidence"
            )
        if not _non_empty_string(absent_entry.get("reason")):
            raise ValueError(
                f"coverage.absent_source_kinds.{required_kind} requires a reason"
            )
        absent_evidence = absent_entry.get("source_evidence")
        if not isinstance(absent_evidence, list) or not absent_evidence:
            raise ValueError(
                f"coverage.absent_source_kinds.{required_kind} requires source_evidence"
            )
    for workflow_surface in workflow_surfaces:
        if workflow_surface not in covered_workflow_surfaces:
            raise ValueError(
                "coverage.workflow_surfaces contains "
                f"`{workflow_surface}` with no checked rows"
            )
    return {
        "schema_version": VALUE_FLOW_CENSUS_SCHEMA_VERSION,
        "target_family": DESIGN_DELTA_PARENT_DRAIN_FAMILY,
        "source_design": str(payload["source_design"]),
        "coverage": {
            "workflow_surfaces": workflow_surfaces,
            "required_source_kinds": required_source_kinds,
            **(
                {"absent_source_kinds": absent_source_kinds}
                if absent_source_kinds
                else {}
            ),
        },
        "rows": normalized_rows,
    }


def reconcile_value_flow_census(
    *,
    census: Mapping[str, Any],
    checked_census_path: Path,
    checked_census_sha256: str,
    boundary_authority_report: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
    prompt_externs: Mapping[str, str | Mapping[str, str]],
    provider_externs: Mapping[str, str],
    command_boundary_manifest: Mapping[str, object],
    boundary_authority_registry: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    declared_workflow_surfaces = list(census["coverage"]["workflow_surfaces"])
    compiled_boundary_rows = _collect_boundary_compiled_rows(
        boundary_authority_report=boundary_authority_report,
        boundary_authority_registry=boundary_authority_registry,
    )
    compiled_boundary_by_key = {
        _boundary_key(row["workflow_surface"], row["symbol_or_field"]): row
        for row in compiled_boundary_rows
    }
    checked_rows = [dict(row) for row in census["rows"]]
    covered_boundary_keys: set[tuple[str, str]] = set()
    stale_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []

    for checked_row in checked_rows:
        if _row_has_boundary_evidence(checked_row):
            boundary_key = _checked_boundary_key(checked_row)
            compiled_boundary_row = compiled_boundary_by_key.get(boundary_key)
            if compiled_boundary_row is None:
                stale_rows.append(_checked_row_summary(checked_row))
            else:
                covered_boundary_keys.add(boundary_key)
                if (
                    checked_row["boundary_authority_class"]
                    != compiled_boundary_row["boundary_authority_class"]
                ):
                    invalid_rows.append(
                        {
                            "row_id": checked_row["row_id"],
                            "reason": "boundary_authority_class does not match compiled evidence",
                            "expected": compiled_boundary_row["boundary_authority_class"],
                            "actual": checked_row["boundary_authority_class"],
                        }
                    )
        _validate_manifest_backed_row(
            checked_row=checked_row,
            source_map_payload=source_map_payload,
            prompt_externs=prompt_externs,
            provider_externs=provider_externs,
            command_boundary_manifest=command_boundary_manifest,
            stale_rows=stale_rows,
            invalid_rows=invalid_rows,
        )

    missing_rows = [
        _compiled_row_summary(row)
        for key, row in compiled_boundary_by_key.items()
        if key not in covered_boundary_keys
    ]
    extra_compiled_rows = [
        {
            "row_id": f"workflow_surface::{workflow_surface}",
            "workflow_surface": workflow_surface,
            "reason": (
                "compiled workflow surface has path-like evidence but is not declared "
                "in coverage.workflow_surfaces"
            ),
        }
        for workflow_surface in sorted(
            _compiled_workflow_surfaces_with_path_like_evidence(
                boundary_authority_report=boundary_authority_report,
                source_map_payload=source_map_payload,
            )
            - set(declared_workflow_surfaces)
        )
    ]
    status = "pass"
    if missing_rows or stale_rows or invalid_rows or extra_compiled_rows:
        status = "fail"
    workflow_rows = []
    for workflow_surface in declared_workflow_surfaces:
        rows = [
            {
                "row_id": row["row_id"],
                "source_kind": row["source_kind"],
                "symbol_or_field": row["symbol_or_field"],
                "plumbing_class": row["plumbing_class"],
                "boundary_authority_class": row["boundary_authority_class"],
            }
            for row in checked_rows
            if row["workflow_surface"] == workflow_surface
        ]
        workflow_rows.append(
            {
                "workflow_surface": workflow_surface,
                "rows": rows,
            }
        )
    return {
        "schema_version": VALUE_FLOW_CENSUS_REPORT_SCHEMA_VERSION,
        "workflow_family": "design_delta_parent_drain",
        "checked_census_path": str(checked_census_path),
        "checked_census_fingerprint": f"sha256:{checked_census_sha256}",
        "required_source_kinds": list(census["coverage"]["required_source_kinds"]),
        "declared_workflow_surfaces": declared_workflow_surfaces,
        "rows": [dict(row) for row in checked_rows],
        "workflow_rows": workflow_rows,
        "missing_rows": missing_rows,
        "stale_rows": stale_rows,
        "invalid_rows": invalid_rows,
        "extra_compiled_rows": extra_compiled_rows,
        "compiled_evidence": {
            "boundary_authority_report": "boundary_authority_report.json",
            "boundary_authority_registry": boundary_authority_registry is not None,
            "source_map": "source_map.json",
            "prompt_extern_manifest": True,
            "provider_extern_manifest": True,
            "command_boundary_manifest": True,
        },
        "status": status,
    }


def _collect_boundary_compiled_rows(
    *,
    boundary_authority_report: Mapping[str, Any],
    boundary_authority_registry: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if boundary_authority_registry is not None:
        rows = boundary_authority_registry.get("rows")
        if isinstance(rows, list):
            return [
                _boundary_registry_row_summary(row)
                for row in rows
                if isinstance(row, Mapping)
                and bool(row.get("path_like"))
                and _non_empty_string(row.get("workflow_name"))
                and _non_empty_string(row.get("field_name"))
                and _non_empty_string(row.get("authority_class"))
            ]

    compiled_rows: list[dict[str, Any]] = []
    seen_keys: set[tuple[str, str]] = set()
    for workflow_row in boundary_authority_report.get("workflows", []):
        if not isinstance(workflow_row, Mapping):
            continue
        workflow_surface = workflow_row.get("workflow_name")
        if not _non_empty_string(workflow_surface):
            continue
        for bucket_name, authority_class in BOUNDARY_AUTHORITY_BUCKETS.items():
            bucket = workflow_row.get(bucket_name)
            if not isinstance(bucket, list):
                continue
            for field_name in bucket:
                if not _non_empty_string(field_name):
                    continue
                boundary_key = _boundary_key(str(workflow_surface), str(field_name))
                if boundary_key in seen_keys:
                    continue
                seen_keys.add(boundary_key)
                compiled_rows.append(
                    {
                        "row_id": (
                            "compiled_boundary::"
                            f"{workflow_surface}::{field_name}"
                        ),
                        "workflow_surface": str(workflow_surface),
                        "source_kind": _infer_source_kind(
                            field_name=str(field_name),
                            authority_class=authority_class,
                        ),
                        "symbol_or_field": str(field_name),
                        "boundary_authority_class": authority_class,
                    }
                )
    return compiled_rows


def _boundary_registry_row_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    workflow_surface = str(row["workflow_name"])
    field_name = str(row["field_name"])
    authority_class = str(row["authority_class"])
    surface_kind = str(row.get("surface_kind", ""))
    return {
        "row_id": f"compiled_boundary::{workflow_surface}::{field_name}",
        "workflow_surface": workflow_surface,
        "source_kind": _infer_source_kind(
            field_name=field_name,
            authority_class=authority_class,
            surface_kind=surface_kind,
        ),
        "symbol_or_field": field_name,
        "boundary_authority_class": authority_class,
    }


def _validate_manifest_backed_row(
    *,
    checked_row: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
    prompt_externs: Mapping[str, str | Mapping[str, str]],
    provider_externs: Mapping[str, str],
    command_boundary_manifest: Mapping[str, object],
    stale_rows: list[dict[str, Any]],
    invalid_rows: list[dict[str, Any]],
) -> None:
    evidence_list = checked_row.get("source_evidence")
    if not isinstance(evidence_list, list):
        return
    evidence_kinds = {
        str(evidence.get("kind"))
        for evidence in evidence_list
        if isinstance(evidence, Mapping)
    }
    workflow_surface = str(checked_row["workflow_surface"])

    if "prompt_extern_manifest" in evidence_kinds:
        prompt_binding = str(checked_row["symbol_or_field"])
        if prompt_binding not in prompt_externs:
            stale_rows.append(_checked_row_summary(checked_row))
    if "provider_extern_manifest" in evidence_kinds:
        provider_binding = str(checked_row["symbol_or_field"])
        provider_name = provider_externs.get(provider_binding)
        if provider_name is None:
            stale_rows.append(_checked_row_summary(checked_row))
        elif str(provider_name) != str(checked_row["path_or_contract"]):
            invalid_rows.append(
                {
                    "row_id": checked_row["row_id"],
                    "reason": "provider target does not match provider extern manifest",
                    "expected": provider_name,
                    "actual": checked_row["path_or_contract"],
                }
            )
    if "command_boundary_manifest" not in evidence_kinds and "source_map" not in evidence_kinds:
        return
    command_boundary = checked_row.get("command_boundary")
    if not isinstance(command_boundary, Mapping):
        stale_rows.append(_checked_row_summary(checked_row))
        return
    command_name = _string_or_none(command_boundary.get("command_name"))
    if not command_name:
        stale_rows.append(_checked_row_summary(checked_row))
        return
    manifest_entry = command_boundary_manifest.get(command_name)
    if not isinstance(manifest_entry, Mapping):
        stale_rows.append(_checked_row_summary(checked_row))
        return
    input_signature_ref = _string_or_none(command_boundary.get("input_signature_ref"))
    if input_signature_ref is not None:
        signature = manifest_entry.get("input_signature")
        if not isinstance(signature, list) or not any(
            isinstance(entry, Mapping) and entry.get("name") == input_signature_ref
            for entry in signature
        ):
            stale_rows.append(_checked_row_summary(checked_row))
            return
    source_map_workflows = source_map_payload.get("workflows")
    if not isinstance(source_map_workflows, Mapping):
        return
    workflow_payload = source_map_workflows.get(workflow_surface)
    if not isinstance(workflow_payload, Mapping):
        stale_rows.append(_checked_row_summary(checked_row))
        return
    command_boundaries = workflow_payload.get("command_boundaries")
    if not isinstance(command_boundaries, list) or not any(
        isinstance(boundary, Mapping)
        and boundary.get("command_name") == command_name
        for boundary in command_boundaries
    ):
        stale_rows.append(_checked_row_summary(checked_row))


def _validate_bridge_metadata(bridge: Mapping[str, Any], *, row_id: str) -> None:
    for field_name in (
        "bridge_owner",
        "consumer",
        "file_shape",
        "retirement_condition",
    ):
        if not _non_empty_string(bridge.get(field_name)):
            raise ValueError(f"row `{row_id}` requires bridge metadata `{field_name}`")


def _validate_command_boundary_metadata(
    command_boundary: Mapping[str, Any], *, row_id: str
) -> None:
    for field_name in (
        "manifest_path",
        "command_name",
        "behavior_class",
        "stable_command",
        "boundary_role",
    ):
        value = command_boundary.get(field_name)
        if field_name == "stable_command":
            if not isinstance(value, list) or not value or not all(
                isinstance(item, str) and item for item in value
            ):
                raise ValueError(
                    f"row `{row_id}` requires command-boundary evidence `{field_name}`"
                )
            continue
        if not _non_empty_string(value):
            raise ValueError(
                f"row `{row_id}` requires command-boundary evidence `{field_name}`"
            )


def _compiled_workflow_surfaces_with_path_like_evidence(
    *,
    boundary_authority_report: Mapping[str, Any],
    source_map_payload: Mapping[str, Any],
) -> set[str]:
    workflow_surfaces: set[str] = set()
    for workflow_row in boundary_authority_report.get("workflows", []):
        if not isinstance(workflow_row, Mapping):
            continue
        workflow_surface = workflow_row.get("workflow_name")
        if not isinstance(workflow_surface, str) or not workflow_surface:
            continue
        if any(
            isinstance(workflow_row.get(bucket_name), list) and workflow_row.get(bucket_name)
            for bucket_name in BOUNDARY_AUTHORITY_BUCKETS
        ):
            workflow_surfaces.add(workflow_surface)
    source_map_workflows = source_map_payload.get("workflows")
    if isinstance(source_map_workflows, Mapping):
        for workflow_surface, workflow_payload in source_map_workflows.items():
            if not isinstance(workflow_surface, str) or not isinstance(
                workflow_payload, Mapping
            ):
                continue
            command_boundaries = workflow_payload.get("command_boundaries")
            if isinstance(command_boundaries, list) and command_boundaries:
                workflow_surfaces.add(workflow_surface)
    return workflow_surfaces


def _checked_boundary_key(row: Mapping[str, Any]) -> tuple[str, str]:
    for evidence in row.get("source_evidence", []):
        if not isinstance(evidence, Mapping):
            continue
        if evidence.get("kind") not in BOUNDARY_EVIDENCE_KINDS:
            continue
        workflow_surface = _string_or_none(evidence.get("workflow_name")) or str(
            row["workflow_surface"]
        )
        field_name = _string_or_none(evidence.get("field_name")) or str(
            row["symbol_or_field"]
        )
        return _boundary_key(workflow_surface, field_name)
    return _boundary_key(str(row["workflow_surface"]), str(row["symbol_or_field"]))


def _row_has_boundary_evidence(row: Mapping[str, Any]) -> bool:
    for evidence in row.get("source_evidence", []):
        if isinstance(evidence, Mapping) and evidence.get("kind") in BOUNDARY_EVIDENCE_KINDS:
            return True
    return False


def _boundary_key(workflow_surface: str, field_name: str) -> tuple[str, str]:
    return (workflow_surface, field_name)


def _infer_source_kind(
    *,
    field_name: str,
    authority_class: str,
    surface_kind: str | None = None,
) -> str:
    if surface_kind == "managed_write_root":
        return "generated_path"
    if surface_kind == "runtime_context_input":
        return "generated_path"
    if surface_kind == "generated_internal_input":
        return "generated_path"
    if surface_kind == "flattened_output":
        if authority_class == "materialized_view":
            return "materialized_output"
        return "public_output"
    if surface_kind == "compatibility_bridge_input":
        if field_name == "run_state_path":
            return "loop_state_field"
        if field_name == "selection_bundle_path":
            return "pointer_path"
        return "bridge_file"
    if surface_kind == "public_input":
        if "__" in field_name:
            return "record_field"
        return "public_input"
    if field_name.startswith("__write_root__"):
        return "generated_path"
    if field_name.endswith("state-root") or field_name.endswith("artifact-root"):
        return "generated_path"
    if field_name == "run_state_path":
        return "loop_state_field"
    if field_name == "selection_bundle_path":
        return "pointer_path"
    if field_name.startswith("return__"):
        if authority_class == "materialized_view":
            return "materialized_output"
        return "public_output"
    if "__" in field_name and authority_class == "public_authored":
        return "record_field"
    if authority_class in {"runtime_derived", "generated_internal"}:
        return "generated_path"
    if authority_class == "compatibility_bridge":
        return "bridge_file"
    return "public_input"


def _compiled_row_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "workflow_surface": row["workflow_surface"],
        "source_kind": row["source_kind"],
        "symbol_or_field": row["symbol_or_field"],
    }


def _checked_row_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "row_id": row["row_id"],
        "workflow_surface": row["workflow_surface"],
        "source_kind": row["source_kind"],
        "symbol_or_field": row["symbol_or_field"],
    }


def _index_boundary_authority_report(
    boundary_authority_report: Mapping[str, Any],
) -> dict[tuple[str, str], dict[str, Any]]:
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    workflows = boundary_authority_report.get("workflows")
    if not isinstance(workflows, list):
        return indexed
    for workflow_row in workflows:
        if not isinstance(workflow_row, Mapping):
            continue
        workflow_name = workflow_row.get("workflow_name")
        if not _non_empty_string(workflow_name):
            continue
        for bucket_name in BOUNDARY_AUTHORITY_BUCKETS:
            bucket_rows = workflow_row.get(bucket_name)
            if not isinstance(bucket_rows, list):
                continue
            for bucket_row in bucket_rows:
                if not _non_empty_string(bucket_row):
                    continue
                field_name = str(bucket_row)
                indexed[(str(workflow_name), str(field_name))] = {
                    "workflow_surface": str(workflow_name),
                    "field_name": str(field_name),
                    "boundary_authority_class": bucket_name,
                }
    return indexed


def _source_block(source: str, start_marker: str, end_marker: str) -> str:
    start_index = source.find(start_marker)
    if start_index < 0:
        return ""
    end_index = source.find(end_marker, start_index)
    if end_index < 0:
        return source[start_index:]
    return source[start_index:end_index]


def _require_mapping(mapping: Mapping[str, Any], field_name: str) -> Mapping[str, Any]:
    value = mapping.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _optional_mapping(
    mapping: Mapping[str, Any], field_name: str
) -> Mapping[str, Any] | None:
    value = mapping.get(field_name)
    return value if isinstance(value, Mapping) else None


def _require_string(mapping: Mapping[str, Any], field_name: str) -> str:
    value = mapping.get(field_name)
    if not _non_empty_string(value):
        raise ValueError(f"{field_name} must be a non-empty string")
    return str(value)


def _require_non_empty_string_list(
    mapping: Mapping[str, Any], field_name: str
) -> list[str]:
    value = mapping.get(field_name)
    if not isinstance(value, list) or not value or not all(
        _non_empty_string(item) for item in value
    ):
        raise ValueError(f"{field_name} must be a non-empty array of strings")
    return [str(item) for item in value]


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)


def _string_or_none(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value else None
