"""Checked C5 rendering-cleanup manifest validation and reporting."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .observability_summaries import OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID


RENDERING_CLEANUP_SCHEMA_VERSION = "workflow_lisp_rendering_cleanup.v1"
RENDERING_CLEANUP_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_rendering_cleanup_report.v1"
)
VALUE_FLOW_CENSUS_SCHEMA_VERSION = "workflow_lisp_private_runtime_value_flow_census.v1"
CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION = "workflow_lisp_consumer_rendering_census.v1"
TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION = "workflow_lisp_typed_prompt_input_report.v1"
ENTRY_PUBLICATION_REPORT_SCHEMA_VERSION = "workflow_lisp_entry_publication_report.v1"
COMPATIBILITY_BRIDGE_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_compatibility_bridge_report.v1"
)
ALLOWED_DECISIONS = frozenset(
    {
        "RETIRED_TO_PROMPT_RENDERING",
        "RETIRED_TO_OBSERVABILITY",
        "RETIRED_TO_ENTRY_PUBLICATION",
        "RETIRED_TO_BRIDGE_METADATA",
        "KEEP_TIMED_PUBLICATION",
        "KEEP_TYPED",
        "KEPT_BLOCKED_COMPATIBILITY",
        "BLOCKED",
        "NOT_C5_TARGET",
    }
)


def load_rendering_cleanup_manifest(
    path: Path,
    *,
    consumer_rendering_census: Mapping[str, Any],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: manifest must be a JSON object"
        )
    if payload.get("schema_version") != RENDERING_CLEANUP_SCHEMA_VERSION:
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: expected schema_version "
            f"{RENDERING_CLEANUP_SCHEMA_VERSION}"
        )
    if payload.get("target_family") != "lisp_frontend_design_delta_parent_drain":
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: expected Design Delta target_family"
        )
    _validate_source_reference(
        payload.get("source_census"),
        field_name="source_census",
        expected_schema=VALUE_FLOW_CENSUS_SCHEMA_VERSION,
    )
    _validate_source_reference(
        payload.get("source_consumer_rendering_census"),
        field_name="source_consumer_rendering_census",
        expected_schema=CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION,
    )
    _validate_prerequisite_reports(payload.get("prerequisite_reports"))
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: rows must be a non-empty array"
        )
    consumer_rows = {
        str(row.get("row_id", "")): row
        for row in consumer_rendering_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    seen_row_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                "rendering_cleanup_manifest_schema_invalid: "
                f"rows[{index}] must be an object"
            )
        row = dict(raw_row)
        c0_row_id = _require_string(row, "c0_row_id")
        if c0_row_id in seen_row_ids:
            raise ValueError(
                "rendering_cleanup_manifest_schema_invalid: "
                f"duplicate c0_row_id `{c0_row_id}`"
            )
        seen_row_ids.add(c0_row_id)
        if c0_row_id not in consumer_rows:
            raise ValueError(
                "rendering_cleanup_c0_row_missing: "
                f"manifest row references missing C0 row `{c0_row_id}`"
            )
        decision = _require_string(row, "decision")
        if decision not in ALLOWED_DECISIONS:
            raise ValueError(
                "rendering_cleanup_manifest_schema_invalid: "
                f"row `{c0_row_id}` uses unknown decision `{decision}`"
            )
        normalized_rows.append({"c0_row_id": c0_row_id, "decision": decision})
    missing_row_ids = sorted(set(consumer_rows) - seen_row_ids)
    if missing_row_ids:
        raise ValueError(
            "rendering_cleanup_c0_row_missing: manifest is missing decisions for "
            + ", ".join(missing_row_ids)
        )
    normalized_rows.sort(key=lambda row: str(row["c0_row_id"]))
    return {
        **payload,
        "rows": normalized_rows,
        "__manifest_path__": str(path.resolve()),
        "__manifest_sha256__": _sha256_file(path.resolve()),
    }


def build_rendering_cleanup_report(
    *,
    workflow_family: str,
    manifest: Mapping[str, Any],
    consumer_rendering_census: Mapping[str, Any],
    typed_prompt_input_report: Mapping[str, Any] | None,
    observability_summary_report: Mapping[str, Any] | None,
    entry_publication_report: Mapping[str, Any] | None,
    compatibility_bridge_report: Mapping[str, Any] | None,
    materialize_view_effects: Sequence[Mapping[str, Any]],
    workflow_boundary_projection: Mapping[str, Any] | None = None,
    source_map_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    consumer_rows = {
        str(row.get("row_id", "")): row
        for row in consumer_rendering_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    typed_prompt_report_ok = _report_status_pass(
        typed_prompt_input_report,
        schema_key="schema_version",
        expected_schema=TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION,
    )
    entry_publication_report_ok = _report_status_pass(
        entry_publication_report,
        schema_key="schema_version",
        expected_schema=ENTRY_PUBLICATION_REPORT_SCHEMA_VERSION,
    )
    compatibility_bridge_report_ok = _report_status_pass(
        compatibility_bridge_report,
        schema_key="schema_version",
        expected_schema=COMPATIBILITY_BRIDGE_REPORT_SCHEMA_VERSION,
    )
    typed_prompt_row_ids = _report_row_ids(
        typed_prompt_input_report,
        field_name="selected_rows",
        row_key="c0_row_id",
        report_ok=typed_prompt_report_ok,
    )
    entry_selected_row_ids = _report_row_ids(
        entry_publication_report,
        field_name="selected_c0_rows",
        row_key="row_id",
        report_ok=entry_publication_report_ok,
    )
    entry_lowered_row_ids = _report_row_ids(
        entry_publication_report,
        field_name="lowered_publications",
        row_key="row_id",
        report_ok=entry_publication_report_ok,
    )
    generated_bridge_row_ids = _report_row_ids(
        compatibility_bridge_report,
        field_name="generated_bridges",
        row_key="c0_row_id",
        report_ok=compatibility_bridge_report_ok,
    )
    blocked_bridge_row_ids = _report_row_ids(
        compatibility_bridge_report,
        field_name="blocked_bridges",
        row_key="c0_row_id",
        report_ok=compatibility_bridge_report_ok,
    )
    observability_row_ids = _observability_row_ids(observability_summary_report)
    observability_report_ok = _report_status_pass(
        observability_summary_report,
        schema_key="schema_id",
        expected_schema=OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
    )
    report_summaries = {
        "typed_prompt_input_report": _report_summary(
            typed_prompt_input_report,
            schema_key="schema_version",
        ),
        "observability_summary_report": _report_summary(
            observability_summary_report,
            schema_key="schema_id",
        ),
        "entry_publication_report": _report_summary(
            entry_publication_report,
            schema_key="schema_version",
        ),
        "compatibility_bridge_report": _report_summary(
            compatibility_bridge_report,
            schema_key="schema_version",
        ),
    }

    diagnostics: list[dict[str, object]] = []
    blocked_row_ids: list[str] = []
    blocked_compatibility_row_ids: list[str] = []
    surviving_body_materialization_row_ids: list[str] = []
    cleanup_decisions: list[dict[str, object]] = []
    decision_counts: Counter[str] = Counter()
    selected_rows: list[dict[str, object]] = []

    for manifest_row in manifest.get("rows", []):
        if not isinstance(manifest_row, Mapping):
            continue
        c0_row_id = str(manifest_row.get("c0_row_id", ""))
        decision = str(manifest_row.get("decision", ""))
        consumer_row = consumer_rows.get(c0_row_id)
        if consumer_row is None:
            diagnostics.append(
                {
                    "code": "rendering_cleanup_c0_row_missing",
                    "c0_row_id": c0_row_id,
                    "message": "checked C0 row is missing from consumer rendering census",
                }
            )
            continue
        decision_counts[decision] += 1
        selected_rows.append(dict(consumer_row))
        cleanup_row = _build_cleanup_row(
            consumer_row=consumer_row,
            decision=decision,
            report_summaries=report_summaries,
        )
        cleanup_decisions.append(cleanup_row)
        if decision in {"RETIRED_TO_PROMPT_RENDERING", "KEEP_TYPED"}:
            if not typed_prompt_report_ok or c0_row_id not in typed_prompt_row_ids:
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_prerequisite_missing",
                        "c0_row_id": c0_row_id,
                        "message": "typed prompt-input evidence does not cover this prompt row",
                    }
                )
            if _row_has_matching_effect(consumer_row, materialize_view_effects):
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_prompt_allocated_durable_view",
                        "c0_row_id": c0_row_id,
                        "message": "prompt row still lowers a materialize_view effect",
                    }
                )
            continue
        if decision == "RETIRED_TO_OBSERVABILITY":
            if not observability_report_ok or c0_row_id not in observability_row_ids:
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_prerequisite_missing",
                        "c0_row_id": c0_row_id,
                        "message": "observability summary evidence does not cover this row",
                    }
                )
            continue
        if decision == "BLOCKED":
            blocked_row_ids.append(c0_row_id)
            if (
                not entry_publication_report_ok
                or c0_row_id not in entry_selected_row_ids
                or c0_row_id in entry_lowered_row_ids
            ):
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_prerequisite_missing",
                        "c0_row_id": c0_row_id,
                        "message": "entry-publication evidence no longer justifies a blocked cleanup row",
                    }
                )
            continue
        if decision == "RETIRED_TO_BRIDGE_METADATA":
            if (
                not compatibility_bridge_report_ok
                or c0_row_id not in generated_bridge_row_ids
            ):
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_prerequisite_missing",
                        "c0_row_id": c0_row_id,
                        "message": "compatibility-bridge evidence does not cover this row",
                    }
                )
            continue
        if decision == "KEPT_BLOCKED_COMPATIBILITY":
            blocked_row_ids.append(c0_row_id)
            blocked_compatibility_row_ids.append(c0_row_id)
            if (
                not compatibility_bridge_report_ok
                or c0_row_id not in blocked_bridge_row_ids
            ):
                diagnostics.append(
                    {
                        "code": "rendering_cleanup_blocked_bridge_retired",
                        "c0_row_id": c0_row_id,
                        "message": "blocked compatibility bridge is no longer preserved by C4 evidence",
                    }
                )
            continue
        if decision == "KEEP_TIMED_PUBLICATION":
            surviving_body_materialization_row_ids.append(c0_row_id)
            cleanup_row["timed_publication"] = {
                "reason": (
                    "view must remain materialized before downstream consumers "
                    "observe the timed summary path"
                ),
                "materialize_view_step_ids": _matching_step_ids(
                    consumer_row,
                    materialize_view_effects,
                ),
            }
            continue

    for effect in materialize_view_effects:
        if str(effect.get("authority_class", "materialized_view")) != "materialized_view":
            continue
        matched_row_id = _matched_row_id(effect, consumer_rows)
        if matched_row_id is None:
            diagnostics.append(
                {
                    "code": "rendering_cleanup_orphan_generated_view",
                    "step_id": str(effect.get("step_id", "")),
                    "message": "generated materialize_view effect is not explained by the cleanup manifest",
                }
            )
            continue
        manifest_decision = next(
            (
                str(row.get("decision", ""))
                for row in manifest.get("rows", [])
                if isinstance(row, Mapping) and row.get("c0_row_id") == matched_row_id
            ),
            "",
        )
        if manifest_decision != "KEEP_TIMED_PUBLICATION":
            diagnostics.append(
                {
                    "code": "rendering_cleanup_body_materialization_not_timed",
                    "c0_row_id": matched_row_id,
                    "step_id": str(effect.get("step_id", "")),
                    "message": "non-timed cleanup row still lowers a body-level materialize_view effect",
                }
            )

    blocked_row_ids = sorted(dict.fromkeys(blocked_row_ids))
    blocked_compatibility_row_ids = sorted(dict.fromkeys(blocked_compatibility_row_ids))
    surviving_body_materialization_row_ids = sorted(
        dict.fromkeys(surviving_body_materialization_row_ids)
    )
    selected_rows.sort(key=lambda row: str(row.get("row_id", "")))
    cleanup_decisions.sort(key=lambda row: str(row.get("c0_row_id", "")))
    projection_workflows = _projection_workflows(workflow_boundary_projection)
    touched_workflows = {
        str(row.get("workflow_surface", ""))
        for row in consumer_rows.values()
        if isinstance(row, Mapping) and row.get("workflow_surface")
    }
    contract_isolation = {
        "workflow_signature_unchanged": all(
            workflow_name in projection_workflows for workflow_name in touched_workflows
        ),
        "typed_steps_do_not_consume_views": typed_prompt_row_ids.isdisjoint(
            generated_bridge_row_ids | blocked_bridge_row_ids | entry_lowered_row_ids
        ),
        "prompt_views_not_published": all(
            row_id not in entry_selected_row_ids and row_id not in entry_lowered_row_ids
            for row_id in typed_prompt_row_ids
        ),
        "observability_views_not_semantic_outputs": (
            True
            if not observability_report_ok
            else observability_row_ids.isdisjoint(
                entry_selected_row_ids | entry_lowered_row_ids | generated_bridge_row_ids
            )
        ),
    }
    durability_reconciliation = {
        "prompt_rows_ephemeral": all(
            not _row_has_matching_effect(consumer_rows[row_id], materialize_view_effects)
            for row_id in typed_prompt_row_ids
            if row_id in consumer_rows
        ),
        "durable_publications_state_layout_allocated": _workflows_have_allocated_materialized_views(
            workflow_names={
                str(row.get("workflow_surface", ""))
                for row_id, row in consumer_rows.items()
                if row_id in entry_lowered_row_ids
            },
            source_map_payload=source_map_payload,
            required_authority_class="public_artifact",
        ),
        "durable_bridges_state_layout_allocated": _workflows_have_allocated_materialized_views(
            workflow_names={
                str(row.get("workflow_surface", ""))
                for row_id, row in consumer_rows.items()
                if row_id in generated_bridge_row_ids
            },
            source_map_payload=source_map_payload,
            required_authority_class="compatibility_bridge",
        ),
        "body_materialize_views_timed_only": not any(
            diagnostic.get("code")
            in {
                "rendering_cleanup_body_materialization_not_timed",
                "rendering_cleanup_orphan_generated_view",
            }
            for diagnostic in diagnostics
            if isinstance(diagnostic, Mapping)
        ),
    }
    for check_name, passed in contract_isolation.items():
        if passed:
            continue
        diagnostics.append(
            {
                "code": "rendering_cleanup_contract_leak",
                "c0_row_id": check_name,
                "message": f"rendering cleanup contract check failed: {check_name}",
            }
        )
    for check_name, passed in durability_reconciliation.items():
        if passed:
            continue
        diagnostics.append(
            {
                "code": "rendering_cleanup_contract_leak",
                "c0_row_id": check_name,
                "message": f"rendering cleanup durability check failed: {check_name}",
            }
        )
    return {
        "schema_version": RENDERING_CLEANUP_REPORT_SCHEMA_VERSION,
        "status": "pass" if not diagnostics else "fail",
        "workflow_family": workflow_family,
        "target_family": workflow_family,
        "checked_manifest": {
            "path": str(manifest.get("__manifest_path__", "")),
            "sha256": (
                f"sha256:{manifest.get('__manifest_sha256__', '')}"
                if manifest.get("__manifest_sha256__")
                else ""
            ),
            "schema_version": str(manifest.get("schema_version", "")),
        },
        "source_census": _json_data(manifest.get("source_census", {})),
        "consumer_rendering_census": {
            "path": str(consumer_rendering_census.get("__manifest_path__", "")),
            "sha256": (
                f"sha256:{consumer_rendering_census.get('__manifest_sha256__', '')}"
                if consumer_rendering_census.get("__manifest_sha256__")
                else ""
            ),
            "schema_version": str(consumer_rendering_census.get("schema_version", "")),
        },
        "prerequisite_reports": report_summaries,
        "selected_rows": selected_rows,
        "cleanup_decisions": cleanup_decisions,
        "decisions": cleanup_decisions,
        "decision_counts": dict(sorted(decision_counts.items())),
        "blocked_row_ids": blocked_row_ids,
        "blocked_compatibility_row_ids": blocked_compatibility_row_ids,
        "surviving_body_materialization_row_ids": surviving_body_materialization_row_ids,
        "surviving_timed_publications": [
            dict(row)
            for row in cleanup_decisions
            if row.get("cleanup_decision") == "KEEP_TIMED_PUBLICATION"
        ],
        "retired_body_views": [
            dict(row)
            for row in cleanup_decisions
            if str(row.get("cleanup_decision", "")).startswith("RETIRED_TO_")
            and row.get("durability_before") == "durable_timed_body"
        ],
        "retired_prompt_files": [
            dict(row)
            for row in cleanup_decisions
            if row.get("cleanup_decision") == "RETIRED_TO_PROMPT_RENDERING"
        ],
        "retired_publication_plumbing": [
            dict(row)
            for row in cleanup_decisions
            if row.get("cleanup_decision") == "RETIRED_TO_ENTRY_PUBLICATION"
        ],
        "retired_bridge_plumbing": [
            dict(row)
            for row in cleanup_decisions
            if row.get("cleanup_decision") == "RETIRED_TO_BRIDGE_METADATA"
        ],
        "blocked_compatibility": [
            dict(row)
            for row in cleanup_decisions
            if row.get("cleanup_decision") == "KEPT_BLOCKED_COMPATIBILITY"
        ],
        "orphan_generated_views": [
            dict(diagnostic)
            for diagnostic in diagnostics
            if diagnostic.get("code") == "rendering_cleanup_orphan_generated_view"
        ],
        "durability_reconciliation": durability_reconciliation,
        "contract_isolation": contract_isolation,
        "diagnostics": diagnostics,
    }


def _build_cleanup_row(
    *,
    consumer_row: Mapping[str, Any],
    decision: str,
    report_summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, object]:
    c0_row_id = str(consumer_row.get("row_id", ""))
    workflow_surface = str(consumer_row.get("workflow_surface", ""))
    cleanup_row: dict[str, object] = {
        "cleanup_id": _cleanup_id(c0_row_id),
        "c0_row_id": c0_row_id,
        "u0_row_id": str(consumer_row.get("u0_row_id", "")),
        "consumer_lane": str(consumer_row.get("consumer_lane", "")),
        "workflow_surface": workflow_surface,
        "previous_track_c_decision": str(consumer_row.get("track_c_decision", "")),
        "cleanup_decision": decision,
        "durability_before": str(consumer_row.get("durability", "")),
        "durability_after": _durability_after(decision),
        "replacement_evidence": _replacement_evidence(
            c0_row_id=c0_row_id,
            decision=decision,
            report_summaries=report_summaries,
        ),
        "compiled_liveness": {
            "old_body_materialize_view_unreferenced": decision
            != "KEEP_TIMED_PUBLICATION",
            "old_public_output_unreferenced": decision != "BLOCKED",
            "old_bridge_unreferenced": decision != "KEPT_BLOCKED_COMPATIBILITY",
        },
        "source_cleanup": {
            "allowed": False,
            "expected_files": _expected_cleanup_files(workflow_surface),
        },
        "notes": str(consumer_row.get("notes", "")),
    }
    if decision == "KEPT_BLOCKED_COMPATIBILITY":
        binding_name = ""
        command_boundary = consumer_row.get("command_boundary")
        if isinstance(command_boundary, Mapping):
            binding_name = str(command_boundary.get("binding_name", ""))
        cleanup_row["blocked_by"] = {
            "adapter": binding_name or "materialize_lisp_frontend_work_item_inputs",
            "reason": "certified adapter still consumes the bridge",
        }
    return cleanup_row


def _validate_source_reference(
    raw_ref: object,
    *,
    field_name: str,
    expected_schema: str,
) -> None:
    if not isinstance(raw_ref, Mapping):
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: "
            f"{field_name} must be an object"
        )
    ref = dict(raw_ref)
    _require_string(ref, "path")
    if _require_string(ref, "schema_version") != expected_schema:
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: "
            f"{field_name}.schema_version must be `{expected_schema}`"
        )


def _validate_prerequisite_reports(raw_reports: object) -> None:
    if not isinstance(raw_reports, Mapping):
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: prerequisite_reports must be an object"
        )
    reports = dict(raw_reports)
    expected_reports = {
        "typed_prompt_input_report": TYPED_PROMPT_INPUT_REPORT_SCHEMA_VERSION,
        "observability_summary_report": OBSERVABILITY_SUMMARY_REPORT_SCHEMA_ID,
        "entry_publication_report": ENTRY_PUBLICATION_REPORT_SCHEMA_VERSION,
        "compatibility_bridge_report": COMPATIBILITY_BRIDGE_REPORT_SCHEMA_VERSION,
    }
    for field_name, expected_schema in expected_reports.items():
        if _require_string(reports, field_name) != expected_schema:
            raise ValueError(
                "rendering_cleanup_manifest_schema_invalid: "
                f"prerequisite_reports.{field_name} must be `{expected_schema}`"
            )


def _row_has_matching_effect(
    row: Mapping[str, Any],
    effects: Sequence[Mapping[str, Any]],
) -> bool:
    suffix = _compiled_effect_suffix(row)
    if suffix is None:
        return False
    workflow_surface = row.get("workflow_surface")
    return any(
        isinstance(effect.get("step_id"), str)
        and (
            workflow_surface is None
            or effect.get("workflow_surface") == workflow_surface
        )
        and str(effect.get("step_id")).endswith(suffix)
        for effect in effects
    )


def _matched_row_id(
    effect: Mapping[str, Any],
    rows_by_id: Mapping[str, Mapping[str, Any]],
) -> str | None:
    step_id = effect.get("step_id")
    if not isinstance(step_id, str):
        return None
    for row_id, row in rows_by_id.items():
        suffix = _compiled_effect_suffix(row)
        if (
            suffix is not None
            and effect.get("workflow_surface") == row.get("workflow_surface")
            and step_id.endswith(suffix)
        ):
            return row_id
    return None


def _compiled_effect_suffix(row: Mapping[str, Any]) -> str | None:
    compiled_effect = row.get("compiled_effect_match")
    if not isinstance(compiled_effect, Mapping):
        return None
    suffix = compiled_effect.get("step_id_suffix")
    return suffix if isinstance(suffix, str) and suffix else None


def _matching_step_ids(
    row: Mapping[str, Any],
    effects: Sequence[Mapping[str, Any]],
) -> list[str]:
    suffix = _compiled_effect_suffix(row)
    if suffix is None:
        return []
    workflow_surface = row.get("workflow_surface")
    matches = [
        str(effect.get("step_id", ""))
        for effect in effects
        if isinstance(effect.get("step_id"), str)
        and (
            workflow_surface is None
            or effect.get("workflow_surface") == workflow_surface
        )
        and str(effect.get("step_id")).endswith(suffix)
    ]
    return sorted(matches)


def _cleanup_id(c0_row_id: str) -> str:
    slug = "".join(character if character.isalnum() else "." for character in c0_row_id)
    slug = ".".join(part for part in slug.split(".") if part)
    return f"cleanup.{slug}" if slug else "cleanup.unknown"


def _durability_after(decision: str) -> str:
    return {
        "RETIRED_TO_PROMPT_RENDERING": "ephemeral",
        "RETIRED_TO_OBSERVABILITY": "none",
        "RETIRED_TO_ENTRY_PUBLICATION": "durable_publication",
        "RETIRED_TO_BRIDGE_METADATA": "durable_bridge",
        "KEEP_TIMED_PUBLICATION": "durable_timed_body",
        "KEEP_TYPED": "ephemeral",
        "KEPT_BLOCKED_COMPATIBILITY": "durable_bridge",
        "BLOCKED": "durable_publication",
        "NOT_C5_TARGET": "none",
    }.get(decision, "none")


def _replacement_evidence(
    *,
    c0_row_id: str,
    decision: str,
    report_summaries: Mapping[str, Mapping[str, Any]],
) -> dict[str, object]:
    report_name = {
        "RETIRED_TO_PROMPT_RENDERING": "typed_prompt_input_report",
        "KEEP_TYPED": "typed_prompt_input_report",
        "RETIRED_TO_OBSERVABILITY": "observability_summary_report",
        "RETIRED_TO_ENTRY_PUBLICATION": "entry_publication_report",
        "BLOCKED": "entry_publication_report",
        "RETIRED_TO_BRIDGE_METADATA": "compatibility_bridge_report",
        "KEPT_BLOCKED_COMPATIBILITY": "compatibility_bridge_report",
    }.get(decision)
    if report_name is None:
        return {
            "report_name": "consumer_rendering_census",
            "report_schema_version": CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION,
            "report_path": "",
            "row_id": c0_row_id,
            "status": "pass",
        }
    report_summary = report_summaries.get(report_name, {})
    return {
        "report_name": report_name,
        "report_schema_version": str(report_summary.get("schema_version", "")),
        "report_path": str(report_summary.get("path", "")),
        "row_id": c0_row_id,
        "status": str(report_summary.get("status", "")),
    }


def _expected_cleanup_files(workflow_surface: str) -> list[str]:
    workflow_name = workflow_surface.split("::", 1)[0]
    if workflow_name == "lisp_frontend_design_delta/drain":
        return ["workflows/library/lisp_frontend_design_delta/drain.orc"]
    if workflow_name == "lisp_frontend_design_delta/work_item":
        return ["workflows/library/lisp_frontend_design_delta/work_item.orc"]
    return []


def _rows(payload: Mapping[str, Any] | None, field_name: str) -> list[dict[str, Any]]:
    if not isinstance(payload, Mapping):
        return []
    rows = payload.get(field_name)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, Mapping)]


def _report_row_ids(
    payload: Mapping[str, Any] | None,
    *,
    field_name: str,
    row_key: str,
    report_ok: bool,
) -> set[str]:
    if not report_ok:
        return set()
    return {
        str(row.get(row_key, ""))
        for row in _rows(payload, field_name)
        if row.get(row_key)
    }


def _require_string(container: Mapping[str, object], field_name: str) -> str:
    value = container.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            "rendering_cleanup_manifest_schema_invalid: "
            f"`{field_name}` must be a non-empty string"
        )
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _observability_row_ids(payload: Mapping[str, Any] | None) -> set[str]:
    if not isinstance(payload, Mapping):
        return set()
    row_ids = payload.get("selected_c0_row_ids")
    if not isinstance(row_ids, list):
        return set()
    return {str(row_id) for row_id in row_ids if isinstance(row_id, str)}


def _report_status_pass(
    payload: Mapping[str, Any] | None,
    *,
    schema_key: str,
    expected_schema: str,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    return (
        payload.get(schema_key) == expected_schema
        and payload.get("status") == "pass"
    )


def _report_summary(
    payload: Mapping[str, Any] | None,
    *,
    schema_key: str,
) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {"status": "missing", "schema_version": "", "path": ""}
    return {
        "status": str(payload.get("status", "")),
        "schema_version": str(payload.get(schema_key, "")),
        "path": str(payload.get("path", "")),
    }


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


def _workflows_have_allocated_materialized_views(
    *,
    workflow_names: set[str],
    source_map_payload: Mapping[str, Any] | None,
    required_authority_class: str,
) -> bool:
    if not workflow_names:
        return True
    if not isinstance(source_map_payload, Mapping):
        return False
    workflows = source_map_payload.get("workflows")
    if not isinstance(workflows, Mapping):
        return False
    for workflow_name in workflow_names:
        workflow = workflows.get(workflow_name)
        if not isinstance(workflow, Mapping):
            return False
        allocations = workflow.get("generated_path_allocations")
        effects = workflow.get("generated_semantic_effects")
        if not isinstance(allocations, Sequence) or not isinstance(effects, Sequence):
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
        if not any(
            isinstance(effect, Mapping)
            and effect.get("effect_kind") == "materialize_view"
            and isinstance(effect.get("details"), Mapping)
            and effect["details"].get("authority_class") == required_authority_class
            and str(
                effect["details"].get(
                    "target_allocation_id",
                    effect["details"].get("allocation_id", ""),
                )
            )
            in allocation_ids
            for effect in effects
        ):
            return False
    return True


def _json_data(value: Any) -> Any:
    return json.loads(json.dumps(value))
