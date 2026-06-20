"""Cross-report checked census alignment for the Design Delta parent drain."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from .lexical_checkpoints import canonical_json_dumps


PARENT_DRAIN_CENSUS_ALIGNMENT_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_design_delta_parent_drain_checked_census_alignment_report.v1"
)

_CARRIED_CONTEXT_ALLOWED_CLASSES = frozenset({"runtime_derived", "generated_internal"})
_BOUNDARY_EVIDENCE_KINDS = frozenset(
    {"boundary_authority_report", "boundary_authority_registry", "compiled_boundary_projection"}
)
_MATERIALIZE_VIEW_CONSUMER_LANES = frozenset(
    {"timed_body_materialization", "retirement_candidate"}
)


def build_parent_drain_census_alignment_report(
    *,
    workflow_family: str,
    checked_boundary_authority_registry: Mapping[str, Any] | None,
    checked_value_flow_census: Mapping[str, Any],
    checked_consumer_rendering_census: Mapping[str, Any],
    checked_compatibility_bridge_manifest: Mapping[str, Any] | None,
    checked_command_boundary_manifest: Mapping[str, Any],
    checked_resume_plumbing_manifest: Mapping[str, Any] | None,
    compiled_boundary_rows: Sequence[Mapping[str, Any]] | None = None,
    boundary_authority_report: Mapping[str, Any] | None = None,
    source_map_payload: Mapping[str, Any] | None = None,
    materialize_view_effects: Sequence[Mapping[str, Any]] = (),
    prompt_externs: Mapping[str, Any] | None = None,
    provider_externs: Mapping[str, Any] | None = None,
    value_flow_census_report: Mapping[str, Any] | None = None,
    consumer_rendering_census_report: Mapping[str, Any] | None = None,
    compatibility_bridge_report: Mapping[str, Any] | None = None,
    resume_plumbing_retirement_report: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    del prompt_externs
    del provider_externs
    del value_flow_census_report
    del consumer_rendering_census_report
    del compatibility_bridge_report
    del resume_plumbing_retirement_report

    normalized_compiled_boundary_rows = _normalize_compiled_boundary_rows(
        compiled_boundary_rows=compiled_boundary_rows,
        boundary_authority_report=boundary_authority_report,
    )
    compiled_boundary_by_key = {
        (row["workflow_surface"], row["symbol_or_field"]): row
        for row in normalized_compiled_boundary_rows
    }
    checked_boundary_rows = _normalize_checked_boundary_rows(
        checked_boundary_authority_registry
    )
    checked_boundary_by_key = {
        (row["workflow_surface"], row["symbol_or_field"]): row
        for row in checked_boundary_rows
    }

    checked_value_rows = [
        dict(row)
        for row in checked_value_flow_census.get("rows", [])
        if isinstance(row, Mapping)
    ]
    checked_value_by_id = {
        str(row.get("row_id", "")): row
        for row in checked_value_rows
        if _non_empty_string(row.get("row_id"))
    }
    checked_consumer_rows = [
        dict(row)
        for row in checked_consumer_rendering_census.get("rows", [])
        if isinstance(row, Mapping)
    ]
    checked_materialize_rows = [
        row
        for row in checked_consumer_rows
        if str(row.get("source_kind", "")) == "materialized_output"
        and str(row.get("consumer_lane", "")) in _MATERIALIZE_VIEW_CONSUMER_LANES
    ]
    scoped_materialize_view_effects = [
        effect
        for effect in materialize_view_effects
        if _non_empty_string(effect.get("workflow_surface"))
        and str(effect.get("authority_class", "materialized_view"))
        == "materialized_view"
        and "__publish__" not in str(effect.get("step_id", ""))
    ]
    checked_consumer_by_id = {
        str(row.get("row_id", "")): row
        for row in checked_consumer_rows
        if _non_empty_string(row.get("row_id"))
    }

    stale_rows: list[dict[str, Any]] = []
    missing_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    extra_compiled_rows: list[dict[str, Any]] = []
    dangling_bridge_rows: list[dict[str, Any]] = []
    command_boundary_violations: list[dict[str, Any]] = []
    carried_context_rows: list[dict[str, Any]] = []
    hidden_bridge_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    covered_compiled_keys: set[tuple[str, str]] = set()
    for row in checked_value_rows:
        boundary_key = _checked_value_boundary_key(row)
        if boundary_key is None:
            continue
        compiled_row = compiled_boundary_by_key.get(boundary_key)
        if compiled_row is None:
            stale = _row_summary(row, code="parent_drain_census_stale_checked_row")
            stale_rows.append(stale)
            diagnostics.append(stale)
            continue
        covered_compiled_keys.add(boundary_key)
        if str(row.get("boundary_authority_class", "")) != str(
            compiled_row.get("boundary_authority_class", "")
        ):
            invalid = _row_summary(
                row,
                code="parent_drain_census_boundary_authority_mismatch",
                expected=compiled_row.get("boundary_authority_class"),
                actual=row.get("boundary_authority_class"),
            )
            invalid_rows.append(invalid)
            diagnostics.append(invalid)

    for compiled_key, compiled_row in sorted(compiled_boundary_by_key.items()):
        if _ignore_boundary_alignment_row(compiled_row):
            continue
        if compiled_key not in checked_boundary_by_key:
            missing = _compiled_row_summary(
                compiled_row,
                code="parent_drain_census_missing_checked_row",
            )
            missing_rows.append(missing)
            diagnostics.append(missing)
        if compiled_key not in covered_compiled_keys:
            extra = _compiled_row_summary(
                compiled_row,
                code="parent_drain_census_missing_checked_row",
            )
            extra_compiled_rows.append(extra)
            diagnostics.append(extra)

    for checked_row in checked_boundary_rows:
        if _ignore_boundary_alignment_row(checked_row):
            continue
        boundary_key = (checked_row["workflow_surface"], checked_row["symbol_or_field"])
        compiled_row = compiled_boundary_by_key.get(boundary_key)
        if compiled_row is None:
            stale = _boundary_row_summary(
                checked_row,
                code="parent_drain_census_stale_checked_row",
            )
            stale_rows.append(stale)
            diagnostics.append(stale)
            continue
        if str(checked_row.get("boundary_authority_class", "")) != str(
            compiled_row.get("boundary_authority_class", "")
        ):
            invalid = _boundary_row_summary(
                checked_row,
                code="parent_drain_census_boundary_authority_mismatch",
                expected=compiled_row.get("boundary_authority_class"),
                actual=checked_row.get("boundary_authority_class"),
            )
            invalid_rows.append(invalid)
            diagnostics.append(invalid)

    for consumer_row in checked_consumer_rows:
        u0_row_id = str(consumer_row.get("u0_row_id", ""))
        if not u0_row_id:
            continue
        if u0_row_id not in checked_value_by_id:
            stale = {
                "code": "parent_drain_census_stale_checked_row",
                "row_id": str(consumer_row.get("row_id", "")),
                "u0_row_id": u0_row_id,
                "workflow_surface": str(consumer_row.get("workflow_surface", "")),
            }
            stale_rows.append(stale)
            diagnostics.append(stale)

    for row in checked_value_rows:
        if _is_carried_context_row(row) and str(
            row.get("boundary_authority_class", "")
        ) not in _CARRIED_CONTEXT_ALLOWED_CLASSES:
            carried = _row_summary(
                row,
                code="parent_drain_census_carried_context_misclassified",
            )
            carried_context_rows.append(carried)
            invalid_rows.append(carried)
            diagnostics.append(carried)
        if _is_hidden_bridge_row(row) and str(
            row.get("boundary_authority_class", "")
        ) != "compatibility_bridge":
            hidden = _row_summary(
                row,
                code="parent_drain_census_hidden_bridge_misclassified",
            )
            hidden_bridge_rows.append(hidden)
            invalid_rows.append(hidden)
            diagnostics.append(hidden)

    bridges = (
        checked_compatibility_bridge_manifest.get("bridges", [])
        if isinstance(checked_compatibility_bridge_manifest, Mapping)
        else []
    )
    for bridge in bridges:
        if not isinstance(bridge, Mapping):
            continue
        bridge_id = str(bridge.get("bridge_id", ""))
        c0_row_id = str(bridge.get("c0_row_id", ""))
        u0_row_id = str(bridge.get("u0_row_id", ""))
        checked_c0_row = checked_consumer_by_id.get(c0_row_id)
        checked_u0_row = checked_value_by_id.get(u0_row_id)
        if checked_c0_row is None or checked_u0_row is None:
            dangling = {
                "code": "parent_drain_census_dangling_bridge_lineage",
                "bridge_id": bridge_id,
                "c0_row_id": c0_row_id,
                "u0_row_id": u0_row_id,
            }
            dangling_bridge_rows.append(dangling)
            diagnostics.append(dangling)
            continue
        if str(checked_c0_row.get("u0_row_id", "")) != u0_row_id:
            dangling = {
                "code": "parent_drain_census_dangling_bridge_lineage",
                "bridge_id": bridge_id,
                "c0_row_id": c0_row_id,
                "u0_row_id": u0_row_id,
            }
            dangling_bridge_rows.append(dangling)
            diagnostics.append(dangling)

    decisions = (
        checked_resume_plumbing_manifest.get("decisions", [])
        if isinstance(checked_resume_plumbing_manifest, Mapping)
        else []
    )
    for decision in decisions:
        if not isinstance(decision, Mapping):
            continue
        row_id = str(decision.get("row_id", ""))
        if row_id and row_id not in checked_value_by_id and row_id not in {
            "transitions.resource.drain_run_state"
        }:
            stale = {
                "code": "parent_drain_census_stale_checked_row",
                "row_id": row_id,
                "reason": "resume decision references missing checked U0 row",
            }
            stale_rows.append(stale)
            diagnostics.append(stale)

    compiled_command_rows = _source_map_command_boundary_rows(source_map_payload)
    for row in compiled_command_rows:
        binding_name = str(row.get("command_name", ""))
        if binding_name and binding_name not in checked_command_boundary_manifest:
            violation = {
                "code": "parent_drain_census_command_boundary_missing",
                "binding_name": binding_name,
                "workflow_surface": str(row.get("workflow_surface", "")),
                "step_id": str(row.get("step_id", "")),
            }
            command_boundary_violations.append(violation)
            diagnostics.append(violation)

    for row in checked_materialize_rows:
        compiled_match = row.get("compiled_effect_match")
        if not isinstance(compiled_match, Mapping):
            continue
        matched = any(
            _materialize_view_effect_matches_row(effect, row)
            for effect in scoped_materialize_view_effects
        )
        if not matched:
            invalid = {
                "code": "parent_drain_census_materialize_view_unmatched",
                "row_id": str(row.get("row_id", "")),
                "workflow_surface": str(row.get("workflow_surface", "")),
            }
            invalid_rows.append(invalid)
            diagnostics.append(invalid)

    for effect in scoped_materialize_view_effects:
        matched = any(
            _materialize_view_effect_matches_row(effect, row)
            for row in checked_materialize_rows
        )
        if not matched:
            invalid = {
                "code": "parent_drain_census_materialize_view_unmatched",
                "row_id": str(effect.get("effect_id", "")),
                "workflow_surface": str(effect.get("workflow_surface", "")),
            }
            invalid_rows.append(invalid)
            diagnostics.append(invalid)

    deduped_diagnostics = _dedupe_diagnostics(diagnostics)
    summary = {
        "checked_value_flow_rows": len(checked_value_rows),
        "checked_consumer_rows": len(checked_consumer_rows),
        "checked_boundary_rows": len(checked_boundary_rows),
        "compiled_boundary_rows": len(normalized_compiled_boundary_rows),
        "compiled_command_boundary_rows": len(compiled_command_rows),
        "compiled_materialize_view_effects": len(scoped_materialize_view_effects),
        "missing_rows": len(missing_rows),
        "stale_rows": len(stale_rows),
        "invalid_rows": len(invalid_rows),
        "extra_compiled_rows": len(extra_compiled_rows),
        "dangling_bridge_rows": len(dangling_bridge_rows),
        "command_boundary_violations": len(command_boundary_violations),
        "carried_context_rows": len(carried_context_rows),
        "hidden_bridge_rows": len(hidden_bridge_rows),
    }
    return {
        "schema_version": PARENT_DRAIN_CENSUS_ALIGNMENT_REPORT_SCHEMA_VERSION,
        "workflow_family": workflow_family,
        "status": "pass" if not deduped_diagnostics else "fail",
        "summary": summary,
        "missing_rows": _sort_rows(missing_rows),
        "stale_rows": _sort_rows(stale_rows),
        "invalid_rows": _sort_rows(invalid_rows),
        "extra_compiled_rows": _sort_rows(extra_compiled_rows),
        "dangling_bridge_rows": _sort_rows(dangling_bridge_rows),
        "command_boundary_violations": _sort_rows(command_boundary_violations),
        "carried_context_rows": _sort_rows(carried_context_rows),
        "hidden_bridge_rows": _sort_rows(hidden_bridge_rows),
        "diagnostics": deduped_diagnostics,
        "provenance": {
            "checked_boundary_authority_registry": _manifest_ref(
                checked_boundary_authority_registry,
                path_fields=("__registry_path__", "path"),
            ),
            "checked_value_flow_census": _manifest_ref(
                checked_value_flow_census,
                path_fields=("__census_path__", "path"),
            ),
            "checked_consumer_rendering_census": _manifest_ref(
                checked_consumer_rendering_census,
                path_fields=("__manifest_path__", "path"),
            ),
            "checked_compatibility_bridge_manifest": _manifest_ref(
                checked_compatibility_bridge_manifest,
                path_fields=("__manifest_path__", "path"),
            ),
            "checked_resume_plumbing_manifest": _manifest_ref(
                checked_resume_plumbing_manifest,
                path_fields=("__manifest_path__", "path"),
            ),
            "source_map": _manifest_ref(source_map_payload, path_fields=("report_path",)),
        },
    }


def serialize_parent_drain_census_alignment_report(report: Mapping[str, Any]) -> str:
    return canonical_json_dumps(report)


def _normalize_compiled_boundary_rows(
    *,
    compiled_boundary_rows: Sequence[Mapping[str, Any]] | None,
    boundary_authority_report: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if compiled_boundary_rows:
        rows: list[dict[str, Any]] = []
        for raw_row in compiled_boundary_rows:
            if not isinstance(raw_row, Mapping):
                continue
            workflow_surface = str(
                raw_row.get("workflow_surface", raw_row.get("workflow_name", ""))
            )
            symbol_or_field = str(
                raw_row.get("symbol_or_field", raw_row.get("field_name", ""))
            )
            boundary_authority_class = str(
                raw_row.get("boundary_authority_class", raw_row.get("authority_class", ""))
            )
            if not workflow_surface or not symbol_or_field or not boundary_authority_class:
                continue
            rows.append(
                {
                    "row_id": str(
                        raw_row.get(
                            "row_id",
                            f"compiled_boundary::{workflow_surface}::{symbol_or_field}",
                        )
                    ),
                    "workflow_surface": workflow_surface,
                    "symbol_or_field": symbol_or_field,
                    "boundary_authority_class": boundary_authority_class,
                }
            )
        return _sort_rows(rows)

    rows = []
    for workflow in (boundary_authority_report or {}).get("workflows", []):
        if not isinstance(workflow, Mapping):
            continue
        workflow_surface = str(workflow.get("workflow_name", ""))
        if not workflow_surface:
            continue
        for bucket in (
            "public_authored",
            "compatibility_bridge",
            "runtime_derived",
            "generated_internal",
            "materialized_view",
            "public_artifact",
        ):
            values = workflow.get(bucket, [])
            if not isinstance(values, list):
                continue
            for symbol_or_field in values:
                if not _non_empty_string(symbol_or_field):
                    continue
                rows.append(
                    {
                        "row_id": f"compiled_boundary::{workflow_surface}::{symbol_or_field}",
                        "workflow_surface": workflow_surface,
                        "symbol_or_field": str(symbol_or_field),
                        "boundary_authority_class": bucket,
                    }
                )
    return _sort_rows(rows)


def _normalize_checked_boundary_rows(
    payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = []
    if not isinstance(payload, Mapping):
        return rows
    for raw_row in payload.get("rows", []):
        if not isinstance(raw_row, Mapping):
            continue
        workflow_surface = str(raw_row.get("workflow_name", ""))
        symbol_or_field = str(raw_row.get("field_name", ""))
        boundary_authority_class = str(raw_row.get("authority_class", ""))
        if not workflow_surface or not symbol_or_field or not boundary_authority_class:
            continue
        rows.append(
            {
                "row_id": f"boundary_registry::{workflow_surface}::{symbol_or_field}",
                "workflow_surface": workflow_surface,
                "symbol_or_field": symbol_or_field,
                "boundary_authority_class": boundary_authority_class,
            }
        )
    return _sort_rows(rows)


def _checked_value_boundary_key(
    row: Mapping[str, Any],
) -> tuple[str, str] | None:
    if not any(
        isinstance(evidence, Mapping)
        and str(evidence.get("kind", "")) in _BOUNDARY_EVIDENCE_KINDS
        for evidence in row.get("source_evidence", [])
        if isinstance(row.get("source_evidence"), list)
    ):
        return None
    workflow_surface = str(row.get("workflow_surface", ""))
    symbol_or_field = str(row.get("symbol_or_field", ""))
    if not workflow_surface or not symbol_or_field:
        return None
    if symbol_or_field.startswith("__write_root__"):
        return None
    return (workflow_surface, symbol_or_field)


def _source_map_command_boundary_rows(
    source_map_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    workflows = (source_map_payload or {}).get("workflows", {})
    if not isinstance(workflows, Mapping):
        return []
    rows = []
    for workflow_surface, workflow in workflows.items():
        if not isinstance(workflow, Mapping):
            continue
        for boundary in workflow.get("command_boundaries", []):
            if not isinstance(boundary, Mapping):
                continue
            rows.append(
                {
                    "workflow_surface": str(workflow_surface),
                    "command_name": str(boundary.get("command_name", "")),
                    "step_id": str(boundary.get("step_id", "")),
                }
            )
    return _sort_rows(rows)


def _materialize_view_effect_matches_row(
    effect: Mapping[str, Any],
    row: Mapping[str, Any],
) -> bool:
    compiled_match = row.get("compiled_effect_match")
    if not isinstance(compiled_match, Mapping):
        return False
    workflow_surface = str(row.get("workflow_surface", ""))
    effect_workflow_surface = str(effect.get("workflow_surface", ""))
    step_id_suffix = str(compiled_match.get("step_id_suffix", ""))
    step_id = str(effect.get("step_id", ""))
    return bool(
        workflow_surface
        and effect_workflow_surface == workflow_surface
        and step_id_suffix
        and step_id.endswith(step_id_suffix)
    )


def _ignore_boundary_alignment_row(row: Mapping[str, Any]) -> bool:
    return str(row.get("symbol_or_field", "")).startswith("__write_root__")


def _is_carried_context_row(row: Mapping[str, Any]) -> bool:
    row_id = str(row.get("row_id", ""))
    symbol = str(row.get("symbol_or_field", ""))
    return "phase_ctx" in row_id or symbol.startswith("phase-ctx__")


def _is_hidden_bridge_row(row: Mapping[str, Any]) -> bool:
    return (
        str(row.get("symbol_or_field", "")) == "run_state_path"
        and str(row.get("current_consumer", "")) == "runtime_resume"
    )


def _row_summary(
    row: Mapping[str, Any],
    *,
    code: str,
    expected: object | None = None,
    actual: object | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "row_id": str(row.get("row_id", "")),
        "workflow_surface": str(row.get("workflow_surface", "")),
        "symbol_or_field": str(row.get("symbol_or_field", "")),
    }
    if expected is not None:
        payload["expected"] = expected
    if actual is not None:
        payload["actual"] = actual
    return payload


def _compiled_row_summary(
    row: Mapping[str, Any],
    *,
    code: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "row_id": str(row.get("row_id", "")),
        "workflow_surface": str(row.get("workflow_surface", "")),
        "symbol_or_field": str(row.get("symbol_or_field", "")),
    }


def _boundary_row_summary(
    row: Mapping[str, Any],
    *,
    code: str,
    expected: object | None = None,
    actual: object | None = None,
) -> dict[str, Any]:
    payload = {
        "code": code,
        "row_id": str(row.get("row_id", "")),
        "workflow_surface": str(row.get("workflow_surface", "")),
        "symbol_or_field": str(row.get("symbol_or_field", "")),
    }
    if expected is not None:
        payload["expected"] = expected
    if actual is not None:
        payload["actual"] = actual
    return payload


def _manifest_ref(
    payload: Mapping[str, Any] | None,
    *,
    path_fields: tuple[str, ...],
) -> dict[str, Any] | None:
    if not isinstance(payload, Mapping):
        return None
    path = ""
    for field in path_fields:
        value = payload.get(field)
        if _non_empty_string(value):
            path = str(value)
            break
    if not path:
        return None
    return {"path": path}


def _dedupe_diagnostics(
    diagnostics: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        code = str(diagnostic.get("code", ""))
        identifier = str(
            diagnostic.get("row_id", diagnostic.get("bridge_id", diagnostic.get("binding_name", "")))
        )
        key = (code, identifier)
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(diagnostic))
    return _sort_rows(result)


def _sort_rows(rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        (dict(row) for row in rows),
        key=lambda row: (
            str(row.get("workflow_surface", "")),
            str(row.get("row_id", row.get("bridge_id", row.get("binding_name", "")))),
            str(row.get("code", "")),
        ),
    )


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value)
