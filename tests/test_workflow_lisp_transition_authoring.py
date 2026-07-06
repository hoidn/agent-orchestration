from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_LIBRARY_ROOT = REPO_ROOT / "workflows" / "library"
DESIGN_DELTA_ENTRYPOINT = (
    WORKFLOW_LIBRARY_ROOT / "lisp_frontend_design_delta" / "drain.orc"
)
DESIGN_DELTA_MIGRATION_INPUTS = (
    REPO_ROOT / "workflows" / "examples" / "inputs" / "workflow_lisp_migrations"
)
TRANSITION_AUTHORING_MANIFEST_PATH = (
    DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.transition_authoring.json"
)


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def _transition_authoring_module():
    return importlib.import_module("orchestrator.workflow_lisp.transition_authoring")


def _design_delta_provider_externs() -> dict[str, str]:
    return json.loads(
        (
            DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.providers.json"
        ).read_text(encoding="utf-8")
    )


def _design_delta_prompt_externs() -> dict[str, str]:
    return json.loads(
        (
            DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.prompts.json"
        ).read_text(encoding="utf-8")
    )


def _design_delta_command_boundaries():
    build = _build_module()
    manifest_path = (
        DESIGN_DELTA_MIGRATION_INPUTS / "design_delta_parent_drain.commands.json"
    )
    return build._parse_command_boundaries_manifest(
        json.loads(manifest_path.read_text(encoding="utf-8")),
        manifest_path=manifest_path,
    )


def _compile_design_delta_parent_drain(tmp_path: Path):
    return compile_stage3_entrypoint(
        DESIGN_DELTA_ENTRYPOINT,
        source_roots=(WORKFLOW_LIBRARY_ROOT,),
        provider_externs=_design_delta_provider_externs(),
        prompt_externs=_design_delta_prompt_externs(),
        command_boundaries=_design_delta_command_boundaries(),
        validate_shared=True,
        workspace_root=tmp_path,
    )


def _design_delta_source_map_payload(tmp_path: Path) -> dict[str, object]:
    build = _build_module()
    compile_result = _compile_design_delta_parent_drain(tmp_path)
    return build._serialize_source_map(
        compile_result,
        selected_name="lisp_frontend_design_delta/drain::drain",
    )


def _record_fields(record_def) -> dict[str, str]:
    return {field.name: field.type_name for field in record_def.fields}


def test_design_delta_parent_drain_shared_validation_clears_direct_boundary_state_path_lints(
    tmp_path: Path,
) -> None:
    compile_result = _compile_design_delta_parent_drain(tmp_path)

    assert "lisp_frontend_design_delta/drain::drain" in compile_result.validated_bundles_by_name
    assert not any(
        diagnostic.code == "workflow_boundary_type_invalid"
        for diagnostic in compile_result.diagnostics
    )


def test_design_delta_transition_contracts_use_narrowed_request_result_and_audit_types(
    tmp_path: Path,
) -> None:
    compile_result = _compile_design_delta_parent_drain(tmp_path)
    module = compile_result.compiled_results_by_name[
        "lisp_frontend_design_delta/transitions"
    ].module
    record_defs = {
        definition.name: definition
        for definition in module.definitions
        if type(definition).__name__ == "RecordDef"
    }

    drain_request = _record_fields(record_defs["DrainStatusRequest"])
    drain_result = _record_fields(record_defs["DrainStatusResult"])
    drain_audit = _record_fields(record_defs["DrainStatusAudit"])
    terminal_request = _record_fields(record_defs["TerminalWorkItemRequest"])
    terminal_result = _record_fields(record_defs["TerminalOutcomeResult"])
    terminal_audit = _record_fields(record_defs["TerminalOutcomeAudit"])
    blocked_request = _record_fields(record_defs["BlockedRecoveryOutcomeRequest"])

    assert drain_request["status"] == "DrainTerminalStatus"
    assert drain_result["status"] == "DrainTerminalStatus"
    assert drain_audit["status"] == "DrainTerminalStatus"
    assert terminal_request["reason"] == "WorkItemTerminalReason"
    assert terminal_result["reason"] == "WorkItemTerminalReason"
    assert terminal_audit["reason"] == "WorkItemTerminalReason"
    assert terminal_request["terminal_route"] == "WorkItemTerminalRoute"
    assert "summary_pointer_path" not in blocked_request
    assert "drain_status_path" not in blocked_request
    assert "progress_report_path" not in blocked_request
    assert "implementation_state_path" not in blocked_request
    assert "work_item_context_path" not in blocked_request
    assert "plan_path" not in blocked_request
    assert "target_design_review_decision" not in blocked_request
    assert "terminal_action" not in blocked_request


def test_design_delta_transition_declarations_tighten_preconditions_and_idempotency(
    tmp_path: Path,
) -> None:
    compile_result = _compile_design_delta_parent_drain(tmp_path)
    module = compile_result.compiled_results_by_name[
        "lisp_frontend_design_delta/transitions"
    ].module
    transitions = {transition.name: transition for transition in module.transitions}

    terminal = transitions["record-terminal-work-item"]
    blocked = transitions["record-blocked-recovery-outcome"]

    assert {"work_item_id", "terminal_route"}.issubset(terminal.idempotency_fields)
    assert {"work_item_id", "recovery_route"}.issubset(blocked.idempotency_fields)

    blocked_preconditions = repr(blocked.preconditions)
    assert "fields=('recovery_route',)" in blocked_preconditions
    assert "TERMINAL_BLOCKED" in blocked_preconditions
    assert "fields=('reason',)" in blocked_preconditions
    assert "not_blocked" in blocked_preconditions


def test_transition_authoring_report_passes_for_checked_design_delta_family(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=_design_delta_source_map_payload(tmp_path),
    )

    assert report["schema_version"] == "workflow_lisp_transition_authoring_report.v1"
    assert report["workflow_family"] == "design_delta_parent_drain"
    assert report["status"] == "pass"
    assert {row["module_name"] for row in report["compiled_origins"]} == {
        "lisp_frontend_design_delta/transitions",
        "lisp_frontend_design_delta/work_item",
    }
    assert all(
        row["classification"] == "low_level_library"
        for row in report["compiled_origins"]
    )
    drain_terminal_rows = [
        row
        for row in report["compiled_origins"]
        if row["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
    ]
    assert drain_terminal_rows == [
        {
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "module_name": "lisp_frontend_design_delta/transitions",
            "path": str(
                REPO_ROOT
                / "workflows"
                / "library"
                / "lisp_frontend_design_delta"
                / "transitions.orc"
            ),
            "line": 351,
            "step_kind": "resource_transition",
            "step_id": "lisp_frontend_design_delta_drain_drain__recorded_summary__lisp_frontend_design_delta_transitions_record_drain_terminal_outcome_stdlib_1__transition_result",
            "classification": "low_level_library",
            "matched_row_id": "low_level.record_drain_terminal_outcome",
        }
    ]
    finalize_rows = [
        row
        for row in report["compiled_origins"]
        if "std_resource_finalize_selected_item_proc_" in row["step_id"]
    ]
    assert finalize_rows
    assert {row["workflow_name"] for row in finalize_rows} == {
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation",
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation",
    }
    assert all(
        row["matched_row_id"] == "low_level.imported_finalize_selected_item"
        and row["module_name"] == "lisp_frontend_design_delta/work_item"
        and row["path"]
        == str(
            REPO_ROOT
            / "orchestrator"
            / "workflow_lisp"
            / "stdlib_modules"
            / "std"
            / "resource.orc"
        )
        for row in finalize_rows
    )
    assert any(
        row["module_name"] == "lisp_frontend_design_delta/transitions"
        and row["matched_row_id"] == "low_level.record_design_gap_progress"
        for row in report["compiled_origins"]
    )
    assert report["ordinary_body_violations"] == []
    assert report["extra_origins"] == []
    assert report["stale_allowed_origins"] == []
    assert report["invalid_allowed_origins"] == []
    assert report["source_shape_violations"] == []


def test_transition_authoring_manifest_rejects_high_level_allowed_origin_rows(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = json.loads(TRANSITION_AUTHORING_MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["allowed_origins"] = [
        {
            "row_id": "high_level.drain.inline_transition",
            "classification": "low_level_library",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
            "module_name": "lisp_frontend_design_delta/drain",
            "step_kind": "resource_transition",
            "step_id_contains": "synthetic_direct_transition",
        }
    ]
    manifest_path = tmp_path / "high_level_allowed_origin.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="high-level modules may not appear"):
        transition_authoring.load_transition_authoring_manifest(manifest_path)


def test_transition_authoring_report_flags_high_level_raw_transition_origin(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    source_map_payload = _design_delta_source_map_payload(tmp_path)
    mutated_payload = copy.deepcopy(source_map_payload)
    workflows = mutated_payload["workflows"]
    assert isinstance(workflows, dict)
    synthetic = copy.deepcopy(
        workflows[
            "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
        ]
    )
    assert isinstance(synthetic, dict)
    synthetic["workflow_name"] = (
        "lisp_frontend_design_delta/drain::synthetic-direct-transition"
    )
    synthetic["workflow_origin"]["module_name"] = "lisp_frontend_design_delta/drain"
    synthetic["workflow_origin"]["path"] = str(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    )
    synthetic["workflow_origin"]["line"] = 999
    synthetic["workflow_origin"]["end_line"] = 1005
    step_id = "lisp_frontend_design_delta_transitions_emit_drain_status_transition_audit"
    synthetic["step_ids"][step_id]["path"] = str(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "drain.orc"
    )
    synthetic["step_ids"][step_id]["line"] = 999
    synthetic["step_ids"][step_id]["end_line"] = 1005
    workflows[
        "lisp_frontend_design_delta/drain::synthetic-direct-transition"
    ] = synthetic

    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=mutated_payload,
    )

    assert report["status"] == "fail"
    assert any(
        row["module_name"] == "lisp_frontend_design_delta/drain"
        and row["classification"] == "ordinary_body_violation"
        for row in report["compiled_origins"]
    )


def test_transition_authoring_report_uses_explicit_extra_origin_bucket_for_unmatched_low_level_sites(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    source_map_payload = _design_delta_source_map_payload(tmp_path)
    mutated_payload = copy.deepcopy(source_map_payload)
    workflows = mutated_payload["workflows"]
    assert isinstance(workflows, dict)
    synthetic = copy.deepcopy(
        workflows[
            "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit"
        ]
    )
    assert isinstance(synthetic, dict)
    synthetic["workflow_name"] = (
        "lisp_frontend_design_delta/transitions::synthetic-unchecked-transition"
    )
    synthetic["workflow_origin"]["line"] = 1001
    synthetic["workflow_origin"]["end_line"] = 1007
    synthetic["core_nodes"][0]["statement_id"] = (
        "root.lisp_frontend_design_delta_transitions_synthetic_unchecked_transition"
    )
    synthetic["core_nodes"][0]["step_id"] = (
        "lisp_frontend_design_delta_transitions_synthetic_unchecked_transition"
    )
    synthetic["core_nodes"][0]["origin_key"] = (
        "lisp_frontend_design_delta/transitions::synthetic-unchecked-transition::"
        "step_id::lisp_frontend_design_delta_transitions_synthetic_unchecked_transition"
    )
    workflows[
        "lisp_frontend_design_delta/transitions::synthetic-unchecked-transition"
    ] = synthetic

    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=mutated_payload,
    )

    assert report["status"] == "fail"
    assert report["ordinary_body_violations"] == []
    assert report["extra_origins"] == [
        {
            "workflow_name": "lisp_frontend_design_delta/transitions::synthetic-unchecked-transition",
            "module_name": "lisp_frontend_design_delta/transitions",
            "step_kind": "resource_transition",
            "step_id": "lisp_frontend_design_delta_transitions_synthetic_unchecked_transition",
            "classification": "low_level_library",
        }
    ]


def test_transition_authoring_report_rejects_stale_allowed_origin_rows(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    manifest["allowed_origins"][0]["step_id_contains"] = "missing_transition_site"

    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=_design_delta_source_map_payload(tmp_path),
    )

    assert report["status"] == "fail"
    assert report["stale_allowed_origins"] == [
        {
            "row_id": "low_level.emit_drain_status_transition_audit",
            "workflow_name": "lisp_frontend_design_delta/transitions::emit-drain-status-transition-audit",
            "module_name": "lisp_frontend_design_delta/transitions",
            "step_kind": "resource_transition",
            "step_id_contains": "missing_transition_site",
            "classification": "low_level_library",
        }
    ]


def test_transition_authoring_report_rejects_source_shape_assertion_failures(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    manifest["source_shape_assertions"] = [
        {
            "module_name": "lisp_frontend_design_delta/transitions",
            "forbidden_substrings": ["record-drain-terminal-outcome"],
        }
    ]

    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=_design_delta_source_map_payload(tmp_path),
    )

    assert report["status"] == "fail"
    assert report["source_shape_violations"] == [
        {
            "module_name": "lisp_frontend_design_delta/transitions",
            "substring": "record-drain-terminal-outcome",
            "path": str(REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "transitions.orc"),
            "reason": "forbidden low-level transition authoring text is still present",
        }
    ]


def test_transition_authoring_report_records_selected_item_summary_carrier_path_without_render_authority() -> None:
    manifest = json.loads(TRANSITION_AUTHORING_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["selected_item_summary_path_assertions"] == [
        {
            "row_id": "selected_item.summary_path",
            "workflow_surface": "lisp_frontend_design_delta/work_item::run-selected-item-stdlib",
            "compiled_boundary_row_id": "compiled_boundary::lisp_frontend_design_delta/work_item::run-selected-item-stdlib::return__summary-path",
            "fulfilled_source_ref": "root.steps.lisp_frontend_design_delta/work_item::run-selected-item-stdlib__resolved__call_lisp_frontend_design_delta/bootstrap::project-work-item-inputs.artifacts.return__item_summary_target_path",
            "authority_class": "compatibility_bridge",
            "rejected_source_kinds": [
                "phase_report_path",
                "pointer_file",
            ],
        }
    ]


def test_transition_authoring_report_rejects_selected_item_summary_path_sourced_from_phase_report() -> None:
    manifest = json.loads(TRANSITION_AUTHORING_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert (
        manifest["selected_item_summary_path_assertions"][0]["rejected_source_kinds"]
        == ["phase_report_path", "pointer_file"]
    )


def test_transition_authoring_report_rejects_selected_item_summary_path_sourced_from_pointer_file() -> None:
    manifest = json.loads(TRANSITION_AUTHORING_MANIFEST_PATH.read_text(encoding="utf-8"))
    assert (
        manifest["selected_item_summary_path_assertions"][0]["fulfilled_source_ref"]
        == "root.steps.lisp_frontend_design_delta/work_item::run-selected-item-stdlib__resolved__call_lisp_frontend_design_delta/bootstrap::project-work-item-inputs.artifacts.return__item_summary_target_path"
    )


def test_transition_authoring_report_records_imported_finalize_selected_item_transition_origins(
    tmp_path: Path,
) -> None:
    transition_authoring = _transition_authoring_module()
    manifest = transition_authoring.load_transition_authoring_manifest(
        TRANSITION_AUTHORING_MANIFEST_PATH
    )
    report = transition_authoring.build_transition_authoring_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest=manifest,
        source_map_payload=_design_delta_source_map_payload(tmp_path),
    )

    finalize_rows = [
        row
        for row in report["compiled_origins"]
        if "std_resource_finalize_selected_item_proc_" in row["step_id"]
    ]

    assert finalize_rows
    assert {row["workflow_name"] for row in finalize_rows} == {
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-blocked-implementation",
        "lisp_frontend_design_delta/work_item::finalize-selected-item-from-completed-implementation",
    }
    assert all(
        row["module_name"] == "lisp_frontend_design_delta/work_item"
        and row["step_kind"] == "resource_transition"
        and row["classification"] == "low_level_library"
        and row["path"]
        == str(
            REPO_ROOT
            / "orchestrator"
            / "workflow_lisp"
            / "stdlib_modules"
            / "std"
            / "resource.orc"
        )
        for row in finalize_rows
    )
