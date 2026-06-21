"""Checked C0 consumer-rendering census validation and reconciliation."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from orchestrator.workflow.view_renderer import (
    ViewRendererError,
    render_view,
    resolve_view_renderer,
    view_bytes_digest,
)

from .lexical_checkpoints import canonical_json_dumps
from .value_flow_census import (
    DESIGN_DELTA_PARENT_DRAIN_FAMILY,
    RENDER_ONLY_PLUMBING_CLASSES,
    SOURCE_KINDS,
)


CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION = "workflow_lisp_consumer_rendering_census.v1"
CONSUMER_RENDERING_CENSUS_REPORT_SCHEMA_VERSION = (
    "workflow_lisp_consumer_rendering_census_report.v1"
)
CONSUMER_LANES = frozenset(
    {
        "typed_step",
        "prompt_injection",
        "human_observability",
        "entry_publication",
        "compatibility_bridge",
        "timed_body_materialization",
        "retirement_candidate",
    }
)
DURABILITY_CLASSES = frozenset(
    {
        "none",
        "ephemeral",
        "durable_publication",
        "durable_bridge",
        "durable_timed_body",
    }
)
TRACK_C_DECISIONS = frozenset(
    {
        "KEEP_TYPED",
        "KEEP_TIMED_PUBLICATION",
        "RETIRE_TO_PROMPT_RENDERING",
        "RETIRE_TO_OBSERVABILITY",
        "RETIRE_TO_ENTRY_PUBLICATION",
        "RETIRE_TO_BRIDGE_METADATA",
        "BLOCKED",
    }
)
RENDER_REQUIRED_SOURCE_KINDS = frozenset(
    {
        "prompt_input_file",
        "materialized_output",
        "summary_report_target",
        "public_output",
        "bridge_file",
        "pointer_path",
        "command_adapter_input",
    }
)
RENDER_OPTIONAL_SOURCE_KINDS = frozenset({"public_input", "record_field"})
BRIDGE_SOURCE_KINDS = frozenset({"bridge_file", "pointer_path", "command_adapter_input"})
BODY_MATERIALIZATION_SOURCE_KINDS = frozenset({"materialized_output"})
RETIREMENT_DECISIONS = frozenset(
    {
        "RETIRE_TO_PROMPT_RENDERING",
        "RETIRE_TO_OBSERVABILITY",
        "RETIRE_TO_ENTRY_PUBLICATION",
        "RETIRE_TO_BRIDGE_METADATA",
        "BLOCKED",
    }
)


def load_consumer_rendering_census(
    path: Path,
    *,
    value_flow_census: Mapping[str, Any],
) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("consumer rendering census must be a JSON object")
    if payload.get("schema_version") != CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION:
        raise ValueError(
            f"expected schema_version {CONSUMER_RENDERING_CENSUS_SCHEMA_VERSION}"
        )
    if payload.get("target_family") != DESIGN_DELTA_PARENT_DRAIN_FAMILY:
        raise ValueError(
            f"expected target_family {DESIGN_DELTA_PARENT_DRAIN_FAMILY}"
        )
    if not _non_empty_string(payload.get("source_design")):
        raise ValueError("source_design is required")
    source_census = _normalize_source_census(payload.get("source_census"))
    _validate_source_census_reference(
        source_census,
        value_flow_census=value_flow_census,
    )

    coverage = _require_mapping(payload, "coverage")
    consumer_lanes = _require_string_list(coverage, "consumer_lanes")
    required_source_kinds = _require_string_list(coverage, "required_source_kinds")
    if unknown_lanes := sorted(
        lane for lane in consumer_lanes if lane not in CONSUMER_LANES
    ):
        raise ValueError(
            "consumer_rendering_census_schema_invalid: coverage.consumer_lanes "
            "contains unknown lane values: " + ", ".join(unknown_lanes)
        )
    if unknown_source_kinds := sorted(
        kind for kind in required_source_kinds if kind not in SOURCE_KINDS
    ):
        raise ValueError(
            "consumer_rendering_census_schema_invalid: coverage.required_source_kinds "
            "contains unknown source_kind values: " + ", ".join(unknown_source_kinds)
        )

    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows must be an array")

    u0_rows = {
        str(row.get("row_id")): row
        for row in value_flow_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    seen_row_ids: set[str] = set()
    seen_u0_row_ids: set[str] = set()
    normalized_rows: list[dict[str, Any]] = []
    for index, raw_row in enumerate(rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(f"rows[{index}] must be an object")
        row = dict(raw_row)
        row_id = _require_string(row, "row_id")
        if row_id in seen_row_ids:
            raise ValueError(f"duplicate row_id `{row_id}`")
        seen_row_ids.add(row_id)
        u0_row_id = _require_string(row, "u0_row_id")
        if u0_row_id in seen_u0_row_ids:
            raise ValueError(f"duplicate u0_row_id `{u0_row_id}`")
        seen_u0_row_ids.add(u0_row_id)

        workflow_surface = _require_string(row, "workflow_surface")
        source_kind = _require_string(row, "source_kind")
        if source_kind not in SOURCE_KINDS:
            raise ValueError(
                "consumer_rendering_census_schema_invalid: "
                f"row `{row_id}` uses unknown source_kind `{source_kind}`"
            )
        consumer_lane = _require_string(row, "consumer_lane")
        if consumer_lane not in CONSUMER_LANES:
            raise ValueError(
                "consumer_rendering_lane_invalid: "
                f"row `{row_id}` uses unknown consumer_lane `{consumer_lane}`"
            )
        durability = _require_string(row, "durability")
        if durability not in DURABILITY_CLASSES:
            raise ValueError(
                "consumer_rendering_census_schema_invalid: "
                f"row `{row_id}` uses unknown durability `{durability}`"
            )
        track_c_decision = _require_string(row, "track_c_decision")
        if track_c_decision not in TRACK_C_DECISIONS:
            raise ValueError(
                "consumer_rendering_census_schema_invalid: "
                f"row `{row_id}` uses unknown track_c_decision `{track_c_decision}`"
            )
        row_renderer = _normalize_renderer(row_id, row.get("renderer"))
        compiled_effect_match = _normalize_compiled_effect_match(
            row_id,
            row.get("compiled_effect_match"),
        )
        _require_mapping_or_none(row, "typed_value_source")
        _require_mapping_or_none(row, "target_binding")
        source_evidence = row.get("source_evidence")
        if not isinstance(source_evidence, list) or not source_evidence:
            raise ValueError(
                "consumer_rendering_census_schema_invalid: "
                f"row `{row_id}` must declare source_evidence"
            )
        for evidence in source_evidence:
            if not isinstance(evidence, Mapping):
                raise ValueError(
                    "consumer_rendering_census_schema_invalid: "
                    f"row `{row_id}` has non-object source_evidence"
                )
            if not _non_empty_string(evidence.get("kind")) or not _non_empty_string(
                evidence.get("path")
            ):
                raise ValueError(
                    "consumer_rendering_census_schema_invalid: "
                    f"row `{row_id}` has incomplete source_evidence entries"
                )

        bridge = _require_mapping_or_none(row, "bridge")
        command_boundary = _require_mapping_or_none(row, "command_boundary")
        if source_kind in BRIDGE_SOURCE_KINDS or consumer_lane == "compatibility_bridge":
            if not isinstance(bridge, Mapping):
                raise ValueError(
                    "consumer_rendering_bridge_metadata_missing: "
                    f"row `{row_id}` requires checked bridge metadata"
                )
            for field_name in (
                "bridge_owner",
                "consumer",
                "file_shape",
                "retirement_condition",
            ):
                if not _non_empty_string(bridge.get(field_name)):
                    raise ValueError(
                        "consumer_rendering_bridge_metadata_missing: "
                        f"row `{row_id}` bridge metadata is missing `{field_name}`"
                    )
        if source_kind == "command_adapter_input" and isinstance(command_boundary, Mapping):
            if not _non_empty_string(command_boundary.get("binding_name")):
                raise ValueError(
                    "consumer_rendering_command_boundary_missing: "
                    f"row `{row_id}` requires command_boundary.binding_name"
                )

        if row_renderer is not None:
            descriptor = resolve_view_renderer(
                str(row_renderer["renderer_id"]),
                int(row_renderer["renderer_version"]),
            )
            if row_renderer.get("accepted_shape") != descriptor.accepted_shape:
                raise ValueError(
                    "consumer_rendering_renderer_shape_mismatch: "
                    f"row `{row_id}` declares accepted_shape "
                    f"`{row_renderer.get('accepted_shape')}` but renderer expects "
                    f"`{descriptor.accepted_shape}`"
                )
        if u0_row_id in u0_rows:
            u0_row = u0_rows[u0_row_id]
            if workflow_surface != u0_row.get("workflow_surface") or source_kind != u0_row.get(
                "source_kind"
            ):
                raise ValueError(
                    "consumer_rendering_census_source_census_mismatch: "
                    f"row `{row_id}` no longer matches U0 row `{u0_row_id}`"
                )
        row["compiled_effect_match"] = compiled_effect_match
        normalized_rows.append(row)

    normalized_payload = dict(payload)
    normalized_payload["source_census"] = source_census
    normalized_payload["rows"] = normalized_rows
    normalized_payload["__manifest_path__"] = str(path.resolve())
    normalized_payload["__manifest_sha256__"] = _sha256_file(path.resolve())
    return normalized_payload


def extract_materialize_view_effects(
    semantic_ir_payload: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    if not isinstance(semantic_ir_payload, Mapping):
        return []
    effects = semantic_ir_payload.get("effects")
    if not isinstance(effects, Mapping):
        return []
    extracted: list[dict[str, Any]] = []
    for effect_id, effect in effects.items():
        if not isinstance(effect, Mapping):
            continue
        if effect.get("effect_kind") != "materialize_view":
            continue
        details = effect.get("details")
        if not isinstance(details, Mapping):
            continue
        extracted.append(
            {
                "effect_id": str(effect_id),
                "workflow_surface": str(effect.get("workflow_name", "")),
                "renderer_id": str(details.get("renderer_id", "")),
                "renderer_version": details.get("renderer_version"),
                "step_id": _effect_step_id(
                    effect_id=str(effect_id),
                    workflow_surface=str(effect.get("workflow_name", "")),
                ),
                "target_path": details.get("target_path"),
                "target_allocation_id": details.get("target_allocation_id")
                or details.get("allocation_id"),
                "authority_class": str(
                    details.get("authority_class", "materialized_view")
                ),
                "value_type": _json_data(details.get("value_type")),
            }
        )
    return extracted


def reconcile_consumer_rendering_census(
    *,
    manifest: Mapping[str, Any],
    value_flow_census: Mapping[str, Any],
    materialize_view_effects: Iterable[Mapping[str, Any]],
    command_boundary_manifest: Mapping[str, Any],
    boundary_authority_report: Mapping[str, Any] | None = None,
    boundary_authority_report_path: str | None = None,
    prompt_externs: Mapping[str, Any] | None = None,
    prompt_externs_path: str | None = None,
    provider_externs: Mapping[str, Any] | None = None,
    provider_externs_path: str | None = None,
    command_boundaries_path: str | None = None,
    view_dual_run_vectors: Mapping[str, Any] | None = None,
    view_dual_run_vectors_path: str | None = None,
    view_dual_run_report: Mapping[str, Any] | None = None,
    view_dual_run_report_path: str | None = None,
) -> dict[str, Any]:
    report = build_consumer_rendering_census_report(
        manifest=manifest,
        value_flow_census=value_flow_census,
        materialize_view_effects=materialize_view_effects,
        command_boundary_manifest=command_boundary_manifest,
        boundary_authority_report=boundary_authority_report,
        boundary_authority_report_path=boundary_authority_report_path,
        prompt_externs=prompt_externs,
        prompt_externs_path=prompt_externs_path,
        provider_externs=provider_externs,
        provider_externs_path=provider_externs_path,
        command_boundaries_path=command_boundaries_path,
        view_dual_run_vectors=view_dual_run_vectors,
        view_dual_run_vectors_path=view_dual_run_vectors_path,
        view_dual_run_report=view_dual_run_report,
        view_dual_run_report_path=view_dual_run_report_path,
    )
    if report["status"] != "pass":
        first = report["diagnostics"][0] if report["diagnostics"] else {}
        code = (
            str(first.get("code"))
            if isinstance(first, Mapping) and first.get("code")
            else "consumer_rendering_census_invalid"
        )
        row_id = (
            str(first.get("row_id"))
            if isinstance(first, Mapping) and first.get("row_id")
            else "unknown_row"
        )
        raise ValueError(f"{code}: {row_id}")
    return report


def build_consumer_rendering_census_report(
    *,
    manifest: Mapping[str, Any],
    value_flow_census: Mapping[str, Any],
    materialize_view_effects: Iterable[Mapping[str, Any]],
    command_boundary_manifest: Mapping[str, Any],
    boundary_authority_report: Mapping[str, Any] | None = None,
    boundary_authority_report_path: str | None = None,
    prompt_externs: Mapping[str, Any] | None = None,
    prompt_externs_path: str | None = None,
    provider_externs: Mapping[str, Any] | None = None,
    provider_externs_path: str | None = None,
    command_boundaries_path: str | None = None,
    view_dual_run_vectors: Mapping[str, Any] | None = None,
    view_dual_run_vectors_path: str | None = None,
    view_dual_run_report: Mapping[str, Any] | None = None,
    view_dual_run_report_path: str | None = None,
) -> dict[str, Any]:
    manifest_rows = [
        dict(row)
        for row in manifest.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("u0_row_id"), str)
    ]
    manifest_rows_by_u0 = {
        str(row["u0_row_id"]): row for row in manifest_rows
    }
    u0_rows = {
        str(row.get("row_id")): row
        for row in value_flow_census.get("rows", [])
        if isinstance(row, Mapping) and isinstance(row.get("row_id"), str)
    }
    required_rows = [
        row
        for row in u0_rows.values()
        if _u0_row_requires_c0(row)
    ]
    missing_rows: list[dict[str, Any]] = []
    stale_rows: list[dict[str, Any]] = []
    invalid_rows: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []

    for u0_row in required_rows:
        row_id = str(u0_row["row_id"])
        manifest_row = manifest_rows_by_u0.get(row_id)
        if manifest_row is None:
            missing_rows.append(
                {
                    "row_id": row_id,
                    "workflow_surface": str(u0_row.get("workflow_surface", "")),
                    "reason": "required U0 rendering row is missing from the checked C0 manifest",
                }
            )
            diagnostics.append(
                _diagnostic(
                    "consumer_rendering_census_row_missing",
                    row_id=row_id,
                    message="required U0 rendering row is missing from the checked C0 manifest",
                )
            )
            continue
        if (
            manifest_row.get("workflow_surface") != u0_row.get("workflow_surface")
            or manifest_row.get("source_kind") != u0_row.get("source_kind")
        ):
            stale_rows.append(
                {
                    "row_id": row_id,
                    "workflow_surface": str(u0_row.get("workflow_surface", "")),
                    "reason": "checked C0 row no longer matches the owning U0 row",
                }
            )
            diagnostics.append(
                _diagnostic(
                    "consumer_rendering_census_row_stale",
                    row_id=row_id,
                    message="checked C0 row no longer matches the owning U0 row",
                )
            )

    materialize_effects = list(materialize_view_effects)
    body_materialization_rows_by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(
        list
    )
    boundary_workflows = {
        str(row.get("workflow_name", "")): row
        for row in (boundary_authority_report or {}).get("workflows", [])
        if isinstance(row, Mapping) and isinstance(row.get("workflow_name"), str)
    }
    for manifest_row in manifest_rows:
        if (
            str(manifest_row.get("source_kind", ""))
            in BODY_MATERIALIZATION_SOURCE_KINDS
        ):
            body_materialization_rows_by_workflow[
                str(manifest_row.get("workflow_surface", ""))
            ].append(manifest_row)

    seam_proof_by_renderer: dict[tuple[str, int], dict[str, Any]] = {}
    effect_rows_by_u0: dict[str, dict[str, Any]] = {}
    for effect in materialize_effects:
        if not isinstance(effect, Mapping):
            continue
        if str(effect.get("authority_class", "materialized_view")) != "materialized_view":
            continue
        effect_id = str(effect.get("effect_id", ""))
        workflow_surface = str(effect.get("workflow_surface", ""))
        renderer_id = str(effect.get("renderer_id", ""))
        renderer_version = effect.get("renderer_version")
        candidate_rows = []
        for manifest_row in body_materialization_rows_by_workflow.get(
            workflow_surface, []
        ):
            row_renderer = manifest_row.get("renderer")
            if isinstance(row_renderer, Mapping):
                if str(row_renderer.get("renderer_id", "")) != renderer_id:
                    continue
                if row_renderer.get("renderer_version") != renderer_version:
                    continue
            candidate_rows.append(manifest_row)
        candidate_rows = _match_compiled_effect_rows(effect, candidate_rows)

        if not candidate_rows:
            if _is_bridge_fulfillment_effect(effect):
                continue
            missing_rows.append(
                {
                    "row_id": effect_id,
                    "workflow_surface": workflow_surface,
                    "reason": "compiler-generated materialize_view effect has no checked C0 body-materialization row",
                }
            )
            diagnostics.append(
                _diagnostic(
                    "consumer_rendering_census_row_missing",
                    row_id=effect_id,
                    message=(
                        "compiler-generated materialize_view effect has no checked "
                        "C0 body-materialization row"
                    ),
                )
            )
            continue

        if len(candidate_rows) > 1:
            stale_rows.append(
                {
                    "row_id": effect_id,
                    "workflow_surface": workflow_surface,
                    "reason": "compiler-generated materialize_view effect matches multiple checked C0 body-materialization rows",
                }
            )
            diagnostics.append(
                _diagnostic(
                    "consumer_rendering_census_row_stale",
                    row_id=effect_id,
                    message=(
                        "compiler-generated materialize_view effect matches multiple "
                        "checked C0 body-materialization rows"
                    ),
                )
            )
            continue

        matched_row = candidate_rows[0]
        u0_row_id = str(matched_row.get("u0_row_id", ""))
        effect_row = effect_rows_by_u0.setdefault(
            u0_row_id,
            {
                "u0_row_id": u0_row_id,
                "workflow_surface": workflow_surface,
                "renderer_id": renderer_id,
                "effect_ids": [],
            },
        )
        effect_row["effect_ids"].append(effect_id)

    for manifest_row in manifest_rows:
        u0_row_id = str(manifest_row.get("u0_row_id", ""))
        u0_row = u0_rows.get(u0_row_id)
        if u0_row is None:
            stale_rows.append(
                {
                    "row_id": u0_row_id,
                    "workflow_surface": str(manifest_row.get("workflow_surface", "")),
                    "reason": "referenced U0 row is missing from the checked source census",
                }
            )
            diagnostics.append(
                _diagnostic(
                    "consumer_rendering_census_row_stale",
                    row_id=u0_row_id,
                    message="referenced U0 row is missing from the checked source census",
                )
            )
            continue

        workflow_surface = str(manifest_row.get("workflow_surface", ""))
        source_kind = str(manifest_row.get("source_kind", ""))
        consumer_lane = str(manifest_row.get("consumer_lane", ""))
        track_c_decision = str(manifest_row.get("track_c_decision", ""))
        durability = str(manifest_row.get("durability", ""))
        row_renderer = manifest_row.get("renderer")
        source_evidence = [
            evidence
            for evidence in manifest_row.get("source_evidence", [])
            if isinstance(evidence, Mapping)
        ]

        if source_kind in BODY_MATERIALIZATION_SOURCE_KINDS:
            body_ok = (
                consumer_lane == "timed_body_materialization"
                and track_c_decision
                in {"KEEP_TIMED_PUBLICATION", "RETIRE_TO_OBSERVABILITY"}
                and durability == "durable_timed_body"
            ) or (
                consumer_lane == "retirement_candidate"
                and track_c_decision in RETIREMENT_DECISIONS
            )
            if not body_ok:
                invalid_rows.append(
                    {
                        "row_id": u0_row_id,
                        "reason": "body-level materialization is neither a timed publication nor a retirement candidate",
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        "consumer_rendering_body_materialization_unclassified",
                        row_id=u0_row_id,
                        message="body-level materialization is neither a timed publication nor a retirement candidate",
                    )
                )

        if consumer_lane == "prompt_injection":
            prompt_evidence = _find_source_evidence(
                source_evidence, kind="prompt_extern_manifest"
            )
            provider_evidence = _find_source_evidence(
                source_evidence, kind="provider_extern_manifest"
            )
            if (
                not prompt_evidence
                or not provider_evidence
                or not prompt_externs
                or not provider_externs
                or not _evidence_path_matches(prompt_evidence, prompt_externs_path)
                or not _evidence_path_matches(provider_evidence, provider_externs_path)
                or not _evidence_binding_present(prompt_evidence, prompt_externs)
                or not _evidence_binding_present(provider_evidence, provider_externs)
            ):
                invalid_rows.append(
                    {
                        "row_id": u0_row_id,
                        "reason": "prompt-rendering row is missing checked prompt/provider extern evidence",
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        "consumer_rendering_census_schema_invalid",
                        row_id=u0_row_id,
                        message="prompt-rendering row is missing checked prompt/provider extern evidence",
                    )
                )

        if consumer_lane == "entry_publication":
            if not boundary_workflows or workflow_surface not in boundary_workflows:
                stale_rows.append(
                    {
                        "row_id": u0_row_id,
                        "workflow_surface": workflow_surface,
                        "reason": "boundary-authority evidence does not cover the workflow surface",
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        "consumer_rendering_census_row_stale",
                        row_id=u0_row_id,
                        message="boundary-authority evidence does not cover the workflow surface",
                    )
                )

        if source_kind == "command_adapter_input":
            if not isinstance(manifest_row.get("command_boundary"), Mapping):
                invalid_rows.append(
                    {
                        "row_id": u0_row_id,
                        "reason": "command-boundary metadata is missing",
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        "consumer_rendering_command_boundary_missing",
                        row_id=u0_row_id,
                        message="command-boundary metadata is missing",
                    )
                )
            else:
                boundary = dict(manifest_row["command_boundary"])
                binding_name = str(boundary.get("binding_name", ""))
                manifest_binding = command_boundary_manifest.get(binding_name)
                if not binding_name or not isinstance(manifest_binding, Mapping):
                    invalid_rows.append(
                        {
                            "row_id": u0_row_id,
                            "reason": "command-boundary binding is missing from the checked command manifest",
                        }
                    )
                    diagnostics.append(
                        _diagnostic(
                            "consumer_rendering_command_boundary_missing",
                            row_id=u0_row_id,
                            message="command-boundary binding is missing from the checked command manifest",
                        )
                    )
                else:
                    if not _non_empty_string_list(boundary.get("evidence_refs")):
                        invalid_rows.append(
                            {
                                "row_id": u0_row_id,
                                "reason": "command-boundary row is missing evidence_refs",
                            }
                        )
                        diagnostics.append(
                            _diagnostic(
                                "consumer_rendering_command_boundary_missing",
                                row_id=u0_row_id,
                                message="command-boundary row is missing evidence_refs",
                            )
                        )
                    if not (
                        _non_empty_string(boundary.get("replacement_surface"))
                        or _non_empty_string(boundary.get("retirement_label"))
                        or _non_empty_string(boundary.get("retirement_status"))
                        or isinstance(boundary.get("view_binding"), Mapping)
                    ):
                        invalid_rows.append(
                            {
                                "row_id": u0_row_id,
                                "reason": "command-boundary row is missing view-retirement metadata",
                            }
                        )
                        diagnostics.append(
                            _diagnostic(
                                "consumer_rendering_command_boundary_missing",
                                row_id=u0_row_id,
                                message="command-boundary row is missing view-retirement metadata",
                            )
                        )

        dual_run_vectors_evidence = _find_source_evidence(
            source_evidence, kind="view_dual_run_vectors"
        )
        dual_run_report_evidence = _find_source_evidence(
            source_evidence, kind="view_dual_run_report"
        )
        if dual_run_vectors_evidence or dual_run_report_evidence:
            dual_run_error = _validate_dual_run_evidence(
                row_id=u0_row_id,
                vectors_evidence=dual_run_vectors_evidence,
                vectors_payload=view_dual_run_vectors,
                vectors_path=view_dual_run_vectors_path,
                report_evidence=dual_run_report_evidence,
                report_payload=view_dual_run_report,
                report_path=view_dual_run_report_path,
            )
            if dual_run_error is not None:
                invalid_rows.append(
                    {
                        "row_id": u0_row_id,
                        "reason": dual_run_error,
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        "consumer_rendering_census_schema_invalid",
                        row_id=u0_row_id,
                        message=dual_run_error,
                    )
                )

        if isinstance(row_renderer, Mapping):
            try:
                seam_proof = _build_renderer_seam_proof(manifest_row)
            except ValueError as exc:
                message = str(exc)
                code = message.split(":", 1)[0]
                invalid_rows.append(
                    {
                        "row_id": u0_row_id,
                        "reason": message,
                    }
                )
                diagnostics.append(
                    _diagnostic(
                        code,
                        row_id=u0_row_id,
                        message=message,
                    )
                )
            else:
                key = (
                    str(seam_proof["renderer_id"]),
                    int(seam_proof["renderer_version"]),
                )
                seam_proof_by_renderer.setdefault(key, seam_proof)

    workflow_rows = []
    for workflow_surface in sorted(
        {str(row.get("workflow_surface", "")) for row in manifest_rows}
    ):
        rows = [
            {
                "row_id": str(row.get("row_id", "")),
                "u0_row_id": str(row.get("u0_row_id", "")),
                "source_kind": str(row.get("source_kind", "")),
                "consumer_lane": str(row.get("consumer_lane", "")),
                "durability": str(row.get("durability", "")),
                "track_c_decision": str(row.get("track_c_decision", "")),
            }
            for row in manifest_rows
            if str(row.get("workflow_surface", "")) == workflow_surface
        ]
        workflow_rows.append(
            {
                "workflow_surface": workflow_surface,
                "rows": rows,
            }
        )
    effect_rows = [
        {
            **row,
            "effect_ids": sorted(str(effect_id) for effect_id in row["effect_ids"]),
        }
        for row in sorted(
            effect_rows_by_u0.values(),
            key=lambda row: str(row.get("u0_row_id", "")),
        )
    ]

    status = "pass"
    if missing_rows or stale_rows or invalid_rows or diagnostics:
        status = "fail"
    manifest_provenance = {
        "path": str(manifest.get("__manifest_path__", "")),
        "sha256": f"sha256:{manifest.get('__manifest_sha256__', '')}",
        "schema_version": str(manifest.get("schema_version", "")),
    }
    source_census_provenance = {
        "path": str(
            manifest.get("source_census", {}).get(
                "path", value_flow_census.get("__census_path__", "")
            )
        ),
        "schema_version": str(
            manifest.get("source_census", {}).get(
                "schema_version", value_flow_census.get("schema_version", "")
            )
        ),
        "sha256": f"sha256:{value_flow_census.get('__census_sha256__', '')}",
    }
    compiled_evidence = {
        "boundary_authority_report": {
            "path": str(
                boundary_authority_report_path
                or _report_path(boundary_authority_report)
            ),
            "workflow_count": len(boundary_workflows),
        },
        "prompt_externs": {
            "path": str(prompt_externs_path or ""),
            "binding_count": len(prompt_externs or {}),
        },
        "provider_externs": {
            "path": str(provider_externs_path or ""),
            "binding_count": len(provider_externs or {}),
        },
        "command_boundary_manifest": {
            "path": str(command_boundaries_path or ""),
            "binding_count": len(command_boundary_manifest),
        },
        "view_dual_run_vectors": {
            "path": str(view_dual_run_vectors_path or ""),
            "workflow_family": str((view_dual_run_vectors or {}).get("workflow_family", "")),
            "adapter_name": str((view_dual_run_vectors or {}).get("adapter_name", "")),
            "vector_count": len((view_dual_run_vectors or {}).get("vectors", []))
            if isinstance((view_dual_run_vectors or {}).get("vectors"), list)
            else 0,
        },
        "view_dual_run_report": {
            "path": str(view_dual_run_report_path or ""),
            "workflow_family": str((view_dual_run_report or {}).get("workflow_family", "")),
            "artifact_id": str((view_dual_run_report or {}).get("artifact_id", "")),
            "status": str(
                (view_dual_run_report or {}).get(
                    "overall_status",
                    (view_dual_run_report or {}).get("status", ""),
                )
            ),
        },
    }
    return {
        "schema_version": CONSUMER_RENDERING_CENSUS_REPORT_SCHEMA_VERSION,
        "workflow_family": "design_delta_parent_drain",
        "target_family": DESIGN_DELTA_PARENT_DRAIN_FAMILY,
        "manifest_provenance": manifest_provenance,
        "source_census_provenance": source_census_provenance,
        "checked_manifest": manifest_provenance,
        "source_census": source_census_provenance,
        "compiled_evidence": compiled_evidence,
        "required_source_kinds": list(
            manifest.get("coverage", {}).get("required_source_kinds", [])
        ),
        "declared_consumer_lanes": list(
            manifest.get("coverage", {}).get("consumer_lanes", [])
        ),
        "rows": [
            {
                "row_id": str(row.get("row_id", "")),
                "u0_row_id": str(row.get("u0_row_id", "")),
                "workflow_surface": str(row.get("workflow_surface", "")),
                "source_kind": str(row.get("source_kind", "")),
                "consumer_lane": str(row.get("consumer_lane", "")),
                "durability": str(row.get("durability", "")),
                "track_c_decision": str(row.get("track_c_decision", "")),
            }
            for row in manifest_rows
        ],
        "workflow_rows": workflow_rows,
        "materialize_view_effect_rows": effect_rows,
        "renderer_seam_proofs": list(seam_proof_by_renderer.values()),
        "missing_rows": missing_rows,
        "stale_rows": stale_rows,
        "invalid_rows": invalid_rows,
        "diagnostics": diagnostics,
        "status": status,
    }


def _build_renderer_seam_proof(row: Mapping[str, Any]) -> dict[str, Any]:
    row_id = str(row.get("u0_row_id", row.get("row_id", "")))
    renderer = _require_mapping(row, "renderer")
    renderer_id = _require_string(renderer, "renderer_id")
    renderer_version = _require_int(renderer, "renderer_version")
    accepted_shape = _require_string(renderer, "accepted_shape")
    descriptor = resolve_view_renderer(renderer_id, renderer_version)
    if accepted_shape != descriptor.accepted_shape:
        raise ValueError(
            "consumer_rendering_renderer_shape_mismatch: "
            f"row `{row_id}` accepted_shape does not match renderer registry"
        )
    typed_value_source = _require_mapping(row, "typed_value_source")
    value_document = typed_value_source.get("value_document")
    target_binding = _require_mapping(row, "target_binding")
    target_labels = target_binding.get("target_labels")
    if not isinstance(target_labels, list) or len(target_labels) < 2:
        raise ValueError(
            "consumer_rendering_target_dependent: "
            f"row `{row_id}` must prove renderer output across at least two target allocations"
        )
    try:
        rendered = render_view(renderer_id, renderer_version, value_document)
    except ViewRendererError as exc:
        if exc.code == "view_renderer_unknown":
            raise ValueError(
                f"consumer_rendering_renderer_unknown: row `{row_id}`"
            ) from exc
        raise ValueError(
            f"consumer_rendering_renderer_shape_mismatch: row `{row_id}`"
        ) from exc
    leaked_target = _find_embedded_target_label(value_document, target_labels)
    compatibility_reason = row.get("compatibility_reason")
    if leaked_target is not None and not _non_empty_string(compatibility_reason):
        raise ValueError(
            "consumer_rendering_view_used_as_semantic_input: "
            f"row `{row_id}` re-encodes rendered target label `{leaked_target}` in the typed value document"
        )
    target_digests = {
        str(target_label): view_bytes_digest(rendered)
        for target_label in target_labels
        if isinstance(target_label, str) and target_label
    }
    if len(set(target_digests.values())) != 1:
        raise ValueError(
            "consumer_rendering_target_dependent: "
            f"row `{row_id}` rendered bytes drift across target allocations"
        )
    return {
        "u0_row_id": row_id,
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "accepted_shape": accepted_shape,
        "value_document_digest": _typed_value_digest(value_document),
        "rendered_bytes_digest": next(iter(target_digests.values())),
        "target_labels": list(target_digests),
    }


def _u0_row_requires_c0(row: Mapping[str, Any]) -> bool:
    plumbing_class = row.get("plumbing_class")
    source_kind = row.get("source_kind")
    if plumbing_class in RENDER_ONLY_PLUMBING_CLASSES:
        return True
    if source_kind in {"bridge_file", "pointer_path"}:
        return True
    return (
        source_kind == "command_adapter_input"
        and row.get("plumbing_class") == "compatibility_bridge"
    )


def _typed_value_digest(value: Any) -> str:
    return f"sha256:{hashlib.sha256(canonical_json_dumps(value).encode('utf-8')).hexdigest()}"


def _normalize_compiled_effect_match(
    row_id: str,
    value: object,
) -> dict[str, str] | None:
    if value is None:
        return None
    match = _require_mapping({"compiled_effect_match": value}, "compiled_effect_match")
    step_id_suffix = _require_string(match, "step_id_suffix")
    return {
        "step_id_suffix": step_id_suffix,
    }


def _effect_step_id(*, effect_id: str, workflow_surface: str) -> str | None:
    if not effect_id or not workflow_surface:
        return None
    prefix = f"effect:{workflow_surface}:"
    suffix = ":materialize_view"
    if not effect_id.startswith(prefix) or not effect_id.endswith(suffix):
        return None
    step_id = effect_id[len(prefix) : -len(suffix)]
    return step_id or None


def _match_compiled_effect_rows(
    effect: Mapping[str, Any],
    candidate_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    if not candidate_rows:
        return []
    rows_with_match = [
        row
        for row in candidate_rows
        if isinstance(row.get("compiled_effect_match"), Mapping)
    ]
    if not rows_with_match:
        return candidate_rows
    step_id = effect.get("step_id")
    if not isinstance(step_id, str) or not step_id:
        return []
    matched_rows = []
    for row in rows_with_match:
        compiled_effect_match = row.get("compiled_effect_match")
        if not isinstance(compiled_effect_match, Mapping):
            continue
        step_id_suffix = compiled_effect_match.get("step_id_suffix")
        if isinstance(step_id_suffix, str) and step_id.endswith(step_id_suffix):
            matched_rows.append(row)
    return matched_rows


def _is_bridge_fulfillment_effect(effect: Mapping[str, Any]) -> bool:
    step_id = str(effect.get("step_id", ""))
    target_path = str(effect.get("target_path", ""))
    value_type = effect.get("value_type")
    value_type_name = (
        str(value_type.get("name", ""))
        if isinstance(value_type, Mapping)
        else ""
    )
    return bool(
        step_id.endswith("__materialize_view__selected_item_summary")
        and target_path.endswith("artifacts.return__item_summary_target_path")
        and value_type_name
        == "lisp_frontend_design_delta/types::WorkItemSummaryValue"
    )


def _normalize_source_census(value: object) -> dict[str, str]:
    if isinstance(value, Mapping):
        path = _require_string(value, "path")
        schema_version = _require_string(value, "schema_version")
        return {
            "path": path,
            "schema_version": schema_version,
        }
    if _non_empty_string(value):
        return {
            "path": str(value),
            "schema_version": "",
        }
    raise ValueError("source_census is required")


def _validate_source_census_reference(
    source_census: Mapping[str, str],
    *,
    value_flow_census: Mapping[str, Any],
) -> None:
    actual_path = value_flow_census.get("__census_path__")
    if _non_empty_string(actual_path) and not _paths_match(
        str(source_census.get("path", "")),
        str(actual_path),
    ):
        raise ValueError(
            "consumer_rendering_census_source_census_mismatch: "
            "manifest source_census.path does not match the checked U0 census path"
        )
    actual_schema = value_flow_census.get("schema_version")
    declared_schema = str(source_census.get("schema_version", ""))
    if _non_empty_string(actual_schema) and declared_schema and declared_schema != str(actual_schema):
        raise ValueError(
            "consumer_rendering_census_source_census_mismatch: "
            "manifest source_census.schema_version does not match the checked U0 census schema"
        )


def _find_source_evidence(
    source_evidence: Iterable[Mapping[str, Any]],
    *,
    kind: str,
) -> Mapping[str, Any] | None:
    for evidence in source_evidence:
        if str(evidence.get("kind", "")) == kind:
            return evidence
    return None


def _evidence_path_matches(
    evidence: Mapping[str, Any] | None,
    expected_path: str | None,
) -> bool:
    if evidence is None:
        return False
    if not _non_empty_string(expected_path):
        return False
    return _paths_match(str(evidence.get("path", "")), str(expected_path))


def _evidence_binding_present(
    evidence: Mapping[str, Any] | None,
    bindings: Mapping[str, Any] | None,
) -> bool:
    if evidence is None:
        return False
    binding_name = evidence.get("binding_name")
    if not _non_empty_string(binding_name):
        return False
    return isinstance(bindings, Mapping) and str(binding_name) in bindings


def _validate_dual_run_evidence(
    *,
    row_id: str,
    vectors_evidence: Mapping[str, Any] | None,
    vectors_payload: Mapping[str, Any] | None,
    vectors_path: str | None,
    report_evidence: Mapping[str, Any] | None,
    report_payload: Mapping[str, Any] | None,
    report_path: str | None,
) -> str | None:
    if vectors_evidence is not None:
        if not _evidence_path_matches(vectors_evidence, vectors_path):
            return (
                f"row `{row_id}` references view dual-run vectors that do not match the checked vectors path"
            )
        if not isinstance(vectors_payload, Mapping):
            return f"row `{row_id}` requires checked view dual-run vectors evidence"
        if str(vectors_payload.get("workflow_family", "")) != "design_delta_parent_drain":
            return f"row `{row_id}` references view dual-run vectors for the wrong workflow family"
        adapter_name = vectors_evidence.get("adapter_name")
        if _non_empty_string(adapter_name) and str(vectors_payload.get("adapter_name", "")) != str(adapter_name):
            return f"row `{row_id}` references view dual-run vectors for the wrong adapter"
    if report_evidence is not None:
        if not _evidence_path_matches(report_evidence, report_path):
            return f"row `{row_id}` references a view dual-run report path that does not match the checked report"
        if not isinstance(report_payload, Mapping):
            return f"row `{row_id}` requires a checked view dual-run report"
        if str(report_payload.get("workflow_family", "")) != "design_delta_parent_drain":
            return f"row `{row_id}` references a view dual-run report for the wrong workflow family"
        if str(report_payload.get("artifact_id", "")) != str(report_evidence.get("artifact_id", "")):
            return f"row `{row_id}` references a view dual-run report with the wrong artifact id"
        if str(report_payload.get("overall_status", "")) != "pass":
            return f"row `{row_id}` requires a passing checked view dual-run report"
    return None


def _report_path(payload: Mapping[str, Any] | None) -> str:
    if not isinstance(payload, Mapping):
        return ""
    report_path = payload.get("report_path")
    if _non_empty_string(report_path):
        return str(report_path)
    return ""


def _paths_match(left: str, right: str) -> bool:
    if left == right:
        return True
    left_posix = Path(left).as_posix()
    right_posix = Path(right).as_posix()
    return left_posix.endswith(right_posix) or right_posix.endswith(left_posix)


def _find_embedded_target_label(
    value: Any,
    target_labels: Iterable[object],
) -> str | None:
    labels = {str(label) for label in target_labels if _non_empty_string(label)}
    if not labels:
        return None
    for item in _iter_string_leaves(value):
        if item in labels:
            return item
    return None


def _iter_string_leaves(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for item in value.values():
            yield from _iter_string_leaves(item)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            yield from _iter_string_leaves(item)


def _normalize_renderer(row_id: str, value: object) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(
            "consumer_rendering_census_schema_invalid: "
            f"row `{row_id}` renderer must be an object"
        )
    renderer_id = _require_string(value, "renderer_id")
    renderer_version = _require_int(value, "renderer_version")
    accepted_shape = _require_string(value, "accepted_shape")
    try:
        resolve_view_renderer(renderer_id, renderer_version)
    except ViewRendererError as exc:
        raise ValueError(
            f"consumer_rendering_renderer_unknown: row `{row_id}`"
        ) from exc
    return {
        "renderer_id": renderer_id,
        "renderer_version": renderer_version,
        "accepted_shape": accepted_shape,
    }


def _diagnostic(code: str, *, row_id: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "row_id": row_id,
        "message": message,
    }


def _json_data(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _json_data(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_data(item) for item in value]
    return value


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _non_empty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _non_empty_string_list(value: object) -> bool:
    return isinstance(value, list) and all(_non_empty_string(item) for item in value)


def _require_mapping(payload: Mapping[str, Any], field_name: str) -> dict[str, Any]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return dict(value)


def _require_mapping_or_none(
    payload: Mapping[str, Any],
    field_name: str,
) -> dict[str, Any] | None:
    value = payload.get(field_name)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object when present")
    return dict(value)


def _require_string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if not _non_empty_string(value):
        raise ValueError(f"{field_name} is required")
    return str(value)


def _require_int(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _require_string_list(payload: Mapping[str, Any], field_name: str) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, list) or not all(_non_empty_string(item) for item in value):
        raise ValueError(f"{field_name} must be a non-empty string array")
    return [str(item) for item in value]
