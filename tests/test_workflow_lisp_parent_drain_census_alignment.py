from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.consumer_rendering_census import (
    extract_materialize_view_effects,
)


def _support_module():
    return importlib.import_module("tests.test_workflow_lisp_build_artifacts")


def _alignment_module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.parent_drain_census_alignment"
    )


def _compiled_materialize_view_effects(
    tmp_path: Path,
    *,
    workflow_surfaces: set[str] | None = None,
) -> list[dict[str, Any]]:
    support = _support_module()
    build = support._build_module()
    request = support._design_delta_parent_drain_request(tmp_path)
    compile_command_manifest = json.loads(
        request.command_boundaries_path.read_text(encoding="utf-8")
    )
    command_boundaries = build._parse_command_boundaries_manifest(
        compile_command_manifest,
        manifest_path=request.command_boundaries_path,
    )
    compile_result = compile_stage3_entrypoint(
        request.source_path,
        source_roots=request.source_roots,
        provider_externs=json.loads(
            request.provider_externs_path.read_text(encoding="utf-8")
        ),
        prompt_externs=json.loads(
            request.prompt_externs_path.read_text(encoding="utf-8")
        ),
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    effects = list(
        build._collect_materialize_view_effects(
            compile_result.validated_bundles_by_name
        )
    )
    if workflow_surfaces is None:
        return effects
    return [
        effect
        for effect in effects
        if str(effect.get("workflow_surface", "")) in workflow_surfaces
    ]


def _build_alignment_report(
    tmp_path: Path,
    *,
    checked_boundary_authority_registry: dict[str, object] | None = None,
    compiled_boundary_registry: dict[str, object] | None = None,
    value_flow_census_payload: dict[str, object] | None = None,
    consumer_rendering_census_payload: dict[str, object] | None = None,
    compatibility_bridges_payload: dict[str, object] | None = None,
    checked_command_boundary_manifest: dict[str, object] | None = None,
    resume_plumbing_manifest_payload: dict[str, object] | None = None,
    materialize_view_effects: list[dict[str, Any]] | None = None,
) -> dict[str, object]:
    support = _support_module()
    build = support._build_module()
    request = support._design_delta_parent_drain_request(tmp_path)

    compile_command_manifest = json.loads(
        request.command_boundaries_path.read_text(encoding="utf-8")
    )
    command_boundaries = build._parse_command_boundaries_manifest(
        compile_command_manifest,
        manifest_path=request.command_boundaries_path,
    )
    compile_result = compile_stage3_entrypoint(
        request.source_path,
        source_roots=request.source_roots,
        provider_externs=json.loads(
            request.provider_externs_path.read_text(encoding="utf-8")
        ),
        prompt_externs=json.loads(
            request.prompt_externs_path.read_text(encoding="utf-8")
        ),
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    source_map_payload = build._serialize_source_map(
        compile_result,
        selected_name=request.entry_workflow,
    )
    filtered_effects = _compiled_materialize_view_effects(
        tmp_path / "compiled-effects",
        workflow_surfaces={
            str(row.get("workflow_surface", ""))
            for row in (
                consumer_rendering_census_payload
                if consumer_rendering_census_payload is not None
                else support._load_design_delta_consumer_rendering_census()["rows"]
            )
            if isinstance(row, dict)
        },
    )
    compiled_effects = (
        materialize_view_effects
        if materialize_view_effects is not None
        else filtered_effects
    )

    if compiled_boundary_registry is None:
        compiled_boundary_registry = support._aligned_design_delta_boundary_authority_registry(
            tmp_path / "compiled-boundaries"
        )
    if checked_boundary_authority_registry is None:
        checked_boundary_authority_registry = copy.deepcopy(compiled_boundary_registry)
    if value_flow_census_payload is None:
        value_flow_census_payload = copy.deepcopy(
            support._aligned_design_delta_value_flow_census()
        )
    if consumer_rendering_census_payload is None:
        consumer_rendering_census_payload = copy.deepcopy(
            support._load_design_delta_consumer_rendering_census()
        )
    if compatibility_bridges_payload is None:
        compatibility_bridges_payload = copy.deepcopy(
            support._load_design_delta_compatibility_bridges()
        )
    if checked_command_boundary_manifest is None:
        checked_command_boundary_manifest = copy.deepcopy(compile_command_manifest)
    if resume_plumbing_manifest_payload is None:
        resume_plumbing_manifest_payload = copy.deepcopy(
            support._load_design_delta_resume_plumbing_retirement_manifest(
                support.DESIGN_DELTA_RESUME_PLUMBING_RETIREMENT_PATH
            )
        )

    builder = getattr(
        _alignment_module(),
        "build_parent_drain_census_alignment_report",
    )
    return builder(
        workflow_family="design_delta_parent_drain",
        checked_boundary_authority_registry=checked_boundary_authority_registry,
        checked_value_flow_census=value_flow_census_payload,
        checked_consumer_rendering_census=consumer_rendering_census_payload,
        checked_compatibility_bridge_manifest=compatibility_bridges_payload,
        checked_command_boundary_manifest=checked_command_boundary_manifest,
        checked_resume_plumbing_manifest=resume_plumbing_manifest_payload,
        compiled_boundary_rows=compiled_boundary_registry["rows"],
        source_map_payload=source_map_payload,
        materialize_view_effects=compiled_effects,
        prompt_externs=json.loads(
            request.prompt_externs_path.read_text(encoding="utf-8")
        ),
        provider_externs=json.loads(
            request.provider_externs_path.read_text(encoding="utf-8")
        ),
    )


def test_parent_drain_census_alignment_accepts_aligned_temporary_payloads(
    tmp_path: Path,
) -> None:
    report = _build_alignment_report(tmp_path)

    assert report["schema_version"] == (
        "workflow_lisp_design_delta_parent_drain_checked_census_alignment_report.v1"
    )
    assert report["status"] == "pass"
    assert report["missing_rows"] == []
    assert report["stale_rows"] == []
    assert report["invalid_rows"] == []
    assert report["extra_compiled_rows"] == []
    assert report["dangling_bridge_rows"] == []
    assert report["command_boundary_violations"] == []


def test_checked_consumer_rendering_census_keeps_checks_report_pair_timed_while_tracking_observability_retirement():
    consumer_rendering_census = (
        _support_module()._load_design_delta_consumer_rendering_census()
    )
    rows_by_id = {
        row["row_id"]: row
        for row in consumer_rendering_census["rows"]
        if row["row_id"]
        in {
            "c0.implementation_phase_materialized_return_checks_report",
            "c0.implementation_phase_materialized_return_checks_report_compiled_boundary",
        }
    }

    primary_row = rows_by_id[
        "c0.implementation_phase_materialized_return_checks_report"
    ]
    mirror_row = rows_by_id[
        "c0.implementation_phase_materialized_return_checks_report_compiled_boundary"
    ]

    assert primary_row["consumer_lane"] == "timed_body_materialization"
    assert primary_row["durability"] == "durable_timed_body"
    assert primary_row["track_c_decision"] == "RETIRE_TO_OBSERVABILITY"
    assert mirror_row["consumer_lane"] == "timed_body_materialization"
    assert mirror_row["durability"] == "durable_timed_body"
    assert mirror_row["track_c_decision"] == "RETIRE_TO_OBSERVABILITY"


def test_parent_drain_census_alignment_rejects_stale_checked_u0_row(
    tmp_path: Path,
) -> None:
    value_flow_census_payload = copy.deepcopy(
        _support_module()._load_design_delta_value_flow_census()
    )
    stale_row = copy.deepcopy(
        next(
            row
            for row in value_flow_census_payload["rows"]
            if row["row_id"] == "implementation_phase.input.baseline_design"
        )
    )
    stale_row["row_id"] = "stale.fake.boundary"
    stale_row["symbol_or_field"] = "fake_boundary_path"
    stale_row["path_or_contract"] = "fake_boundary_path"
    value_flow_census_payload["rows"].append(stale_row)

    report = _build_alignment_report(
        tmp_path,
        value_flow_census_payload=value_flow_census_payload,
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_stale_checked_row"}
    assert any(row["row_id"] == "stale.fake.boundary" for row in report["stale_rows"])


def test_parent_drain_census_alignment_rejects_carried_context_misclassification(
    tmp_path: Path,
) -> None:
    value_flow_census_payload = copy.deepcopy(
        _support_module()._load_design_delta_value_flow_census()
    )
    target_row = next(
        row
        for row in value_flow_census_payload["rows"]
        if row["row_id"] == "implementation_phase.generated.phase_ctx_run_artifact_root"
    )
    target_row["boundary_authority_class"] = "compatibility_bridge"

    report = _build_alignment_report(
        tmp_path,
        value_flow_census_payload=value_flow_census_payload,
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_carried_context_misclassified"}
    assert any(
        row["row_id"] == "implementation_phase.generated.phase_ctx_run_artifact_root"
        for row in report["carried_context_rows"]
    )


def test_parent_drain_census_alignment_rejects_hidden_bridge_misclassification(
    tmp_path: Path,
) -> None:
    value_flow_census_payload = copy.deepcopy(
        _support_module()._load_design_delta_value_flow_census()
    )
    target_row = next(
        row
        for row in value_flow_census_payload["rows"]
        if row["row_id"] == "work_item.loop.run_state_path"
    )
    target_row["boundary_authority_class"] = "runtime_derived"

    report = _build_alignment_report(
        tmp_path,
        value_flow_census_payload=value_flow_census_payload,
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_hidden_bridge_misclassified"}
    assert any(
        row["row_id"] == "work_item.loop.run_state_path"
        for row in report["hidden_bridge_rows"]
    )


def test_parent_drain_census_alignment_rejects_dangling_bridge_lineage(
    tmp_path: Path,
) -> None:
    compatibility_bridges_payload = copy.deepcopy(
        _support_module()._load_design_delta_compatibility_bridges()
    )
    compatibility_bridges_payload["bridges"][0]["u0_row_id"] = "u0.missing.bridge_row"

    report = _build_alignment_report(
        tmp_path,
        compatibility_bridges_payload=compatibility_bridges_payload,
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_dangling_bridge_lineage"}
    assert any(
        row["bridge_id"] == compatibility_bridges_payload["bridges"][0]["bridge_id"]
        for row in report["dangling_bridge_rows"]
    )


def test_parent_drain_census_alignment_rejects_missing_command_or_materialize_view_evidence(
    tmp_path: Path,
) -> None:
    report = _build_alignment_report(
        tmp_path,
        checked_command_boundary_manifest={},
        materialize_view_effects=[],
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {
        "parent_drain_census_command_boundary_missing",
        "parent_drain_census_materialize_view_unmatched",
    }
    assert report["command_boundary_violations"]
    assert report["invalid_rows"]


def test_parent_drain_census_alignment_rejects_materialize_view_match_from_other_workflow(
    tmp_path: Path,
) -> None:
    consumer_rendering_census_payload = copy.deepcopy(
        _support_module()._load_design_delta_consumer_rendering_census()
    )
    target_row = next(
        row
        for row in consumer_rendering_census_payload["rows"]
        if row["row_id"] == "c0.work_item_materialized_work_item_context_view"
    )
    target_workflow_surface = str(target_row["workflow_surface"])
    target_step_id_suffix = str(target_row["compiled_effect_match"]["step_id_suffix"])
    compiled_effects = _compiled_materialize_view_effects(
        tmp_path / "compiled-effects"
    )
    filtered_effects = [
        effect
        for effect in compiled_effects
        if not (
            str(effect.get("workflow_surface", "")) == target_workflow_surface
            and str(effect.get("step_id", "")).endswith(target_step_id_suffix)
        )
    ]

    report = _build_alignment_report(
        tmp_path,
        consumer_rendering_census_payload=consumer_rendering_census_payload,
        materialize_view_effects=filtered_effects,
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_materialize_view_unmatched"}
    assert any(
        row["row_id"] == "c0.work_item_materialized_work_item_context_view"
        for row in report["invalid_rows"]
    )


def test_parent_drain_census_alignment_rejects_unchecked_materialize_view_workflow_surface(
    tmp_path: Path,
) -> None:
    compiled_effects = _compiled_materialize_view_effects(tmp_path / "compiled-effects")
    synthetic_effect = copy.deepcopy(compiled_effects[0])
    synthetic_effect["workflow_surface"] = (
        "lisp_frontend_design_delta/drain::synthetic-unchecked-surface"
    )
    synthetic_effect["effect_id"] = (
        "effect:lisp_frontend_design_delta/drain::synthetic-unchecked-surface:"
        "materialize_view"
    )
    synthetic_effect["step_id"] = (
        "root.lisp_frontend_design_delta_drain__materialize_view__"
        "synthetic_unchecked_surface"
    )

    report = _build_alignment_report(
        tmp_path,
        materialize_view_effects=[*compiled_effects, synthetic_effect],
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } >= {"parent_drain_census_materialize_view_unmatched"}
    assert any(
        row["row_id"] == synthetic_effect["effect_id"] for row in report["invalid_rows"]
    )


def test_checked_design_delta_parent_drain_alignment_report_matches_current_manifests(
    tmp_path: Path,
) -> None:
    support = _support_module()
    report = _build_alignment_report(
        tmp_path,
        checked_boundary_authority_registry=copy.deepcopy(
            support._load_design_delta_boundary_authority_registry()
        ),
        value_flow_census_payload=copy.deepcopy(
            support._load_design_delta_value_flow_census()
        ),
        consumer_rendering_census_payload=copy.deepcopy(
            support._load_design_delta_consumer_rendering_census()
        ),
        compatibility_bridges_payload=copy.deepcopy(
            support._load_design_delta_compatibility_bridges()
        ),
        resume_plumbing_manifest_payload=copy.deepcopy(
            support._load_design_delta_resume_plumbing_retirement_manifest(
                support.DESIGN_DELTA_RESUME_PLUMBING_RETIREMENT_PATH
            )
        ),
        materialize_view_effects=_compiled_materialize_view_effects(
            tmp_path / "checked-current-evidence"
        ),
    )

    assert report["status"] == "pass"
    assert report["missing_rows"] == []
    assert report["stale_rows"] == []
    assert report["invalid_rows"] == []
