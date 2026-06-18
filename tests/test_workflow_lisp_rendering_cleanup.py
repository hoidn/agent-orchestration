from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.rendering_cleanup")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _consumer_row(
    *,
    row_id: str,
    consumer_lane: str,
    track_c_decision: str,
    workflow_surface: str = "design_delta/example::run",
    compiled_effect_suffix: str | None = None,
) -> dict[str, object]:
    row = {
        "row_id": row_id,
        "u0_row_id": row_id.replace("c0.", "u0."),
        "workflow_surface": workflow_surface,
        "source_kind": "materialized_output",
        "consumer_lane": consumer_lane,
        "durability": "durable_timed_body"
        if consumer_lane == "timed_body_materialization"
        else "ephemeral",
        "renderer": None,
        "typed_value_source": None,
        "target_binding": None,
        "track_c_decision": track_c_decision,
        "replacement_target": "Track C replacement",
        "source_evidence": [{"kind": "u0_checked_row", "path": "value_flow.json"}],
        "command_boundary": None,
        "bridge": None,
        "notes": "",
    }
    if compiled_effect_suffix is not None:
        row["compiled_effect_match"] = {"step_id_suffix": compiled_effect_suffix}
    return row


def _consumer_payload() -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_consumer_rendering_census.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_design": "docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md",
        "source_census": {
            "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
            "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        },
        "coverage": {
            "consumer_lanes": [
                "prompt_injection",
                "human_observability",
                "entry_publication",
                "compatibility_bridge",
                "timed_body_materialization",
                "retirement_candidate",
            ],
            "required_source_kinds": ["prompt_input_file", "materialized_output"],
        },
        "rows": [
            _consumer_row(
                row_id="c0.prompt",
                consumer_lane="prompt_injection",
                track_c_decision="KEEP_TYPED",
                compiled_effect_suffix="__prompt_view",
            ),
            _consumer_row(
                row_id="c0.observability",
                consumer_lane="human_observability",
                track_c_decision="RETIRE_TO_OBSERVABILITY",
            ),
            _consumer_row(
                row_id="c0.entry",
                consumer_lane="entry_publication",
                track_c_decision="RETIRE_TO_ENTRY_PUBLICATION",
            ),
            _consumer_row(
                row_id="c0.bridge",
                consumer_lane="compatibility_bridge",
                track_c_decision="RETIRE_TO_BRIDGE_METADATA",
            ),
            _consumer_row(
                row_id="c0.blocked_bridge",
                consumer_lane="compatibility_bridge",
                track_c_decision="BLOCKED",
            ),
            _consumer_row(
                row_id="c0.timed",
                consumer_lane="timed_body_materialization",
                track_c_decision="KEEP_TIMED_PUBLICATION",
                compiled_effect_suffix="__timed_view",
            ),
        ],
    }


def _manifest_payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_rendering_cleanup.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_census": {
            "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
            "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        },
        "source_consumer_rendering_census": {
            "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json",
            "schema_version": "workflow_lisp_consumer_rendering_census.v1",
        },
        "prerequisite_reports": {
            "typed_prompt_input_report": "workflow_lisp_typed_prompt_input_report.v1",
            "observability_summary_report": "workflow_lisp_observability_summary_report.v1",
            "entry_publication_report": "workflow_lisp_entry_publication_report.v1",
            "compatibility_bridge_report": "workflow_lisp_compatibility_bridge_report.v1",
        },
        "rows": rows
        if rows is not None
        else [
            {"c0_row_id": "c0.prompt", "decision": "RETIRED_TO_PROMPT_RENDERING"},
            {"c0_row_id": "c0.observability", "decision": "RETIRED_TO_OBSERVABILITY"},
            {"c0_row_id": "c0.entry", "decision": "BLOCKED"},
            {"c0_row_id": "c0.bridge", "decision": "RETIRED_TO_BRIDGE_METADATA"},
            {"c0_row_id": "c0.blocked_bridge", "decision": "KEPT_BLOCKED_COMPATIBILITY"},
            {"c0_row_id": "c0.timed", "decision": "KEEP_TIMED_PUBLICATION"},
        ],
    }


def _typed_prompt_input_report() -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_typed_prompt_input_report.v1",
        "workflow_family": "design_delta_parent_drain",
        "status": "pass",
        "selected_rows": [{"c0_row_id": "c0.prompt"}],
    }


def _observability_summary_report() -> dict[str, object]:
    return {
        "schema_id": "workflow_lisp_observability_summary_report.v1",
        "workflow_family": "design_delta_parent_drain",
        "status": "pass",
        "selected_c0_row_ids": ["c0.observability"],
        "diagnostics": {"errors": [], "warnings": []},
    }


def _entry_publication_report() -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_entry_publication_report.v1",
        "workflow_family": "lisp_frontend_design_delta_parent_drain",
        "status": "pass",
        "selected_c0_rows": [{"row_id": "c0.entry"}],
        "lowered_publications": [],
        "compatibility_reasons": [{"row_id": "c0.entry"}],
    }


def _compatibility_bridge_report() -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_compatibility_bridge_report.v1",
        "workflow_family": "design_delta_parent_drain",
        "status": "pass",
        "generated_bridges": [{"c0_row_id": "c0.bridge"}],
        "blocked_bridges": [{"c0_row_id": "c0.blocked_bridge"}],
    }


def _workflow_boundary_projection() -> dict[str, object]:
    return {
        "workflows": [
            {
                "workflow_name": "design_delta/example::run",
                "boundary": {
                    "public_input_names": [],
                },
            }
        ]
    }


def _source_map_payload() -> dict[str, object]:
    return {
        "workflows": {
            "design_delta/example::run": {
                "generated_semantic_effects": [
                    {
                        "effect_kind": "materialize_view",
                        "details": {
                            "authority_class": "compatibility_bridge",
                            "allocation_id": "bridge-allocation",
                        },
                    }
                ],
                "generated_path_allocations": [
                    {
                        "allocation_id": "bridge-allocation",
                        "semantic_role": "materialized_value_view",
                    }
                ],
            }
        }
    }


def test_load_rendering_cleanup_manifest_accepts_allowed_decisions(
    tmp_path: Path,
) -> None:
    module = _module()
    manifest_path = _write_json(tmp_path / "rendering_cleanup.json", _manifest_payload())

    payload = module.load_rendering_cleanup_manifest(
        manifest_path,
        consumer_rendering_census=_consumer_payload(),
    )

    assert payload["schema_version"] == "workflow_lisp_rendering_cleanup.v1"
    assert payload["target_family"] == "lisp_frontend_design_delta_parent_drain"
    assert {row["decision"] for row in payload["rows"]} == {
        "RETIRED_TO_PROMPT_RENDERING",
        "RETIRED_TO_OBSERVABILITY",
        "BLOCKED",
        "RETIRED_TO_BRIDGE_METADATA",
        "KEPT_BLOCKED_COMPATIBILITY",
        "KEEP_TIMED_PUBLICATION",
    }


def test_checked_design_delta_rendering_cleanup_retires_summary_body_materialization() -> None:
    manifest_path = (
        Path(__file__).resolve().parent.parent
        / "workflows"
        / "examples"
        / "inputs"
        / "workflow_lisp_migrations"
        / "design_delta_parent_drain.rendering_cleanup.json"
    )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    decisions = {row["c0_row_id"]: row["decision"] for row in payload["rows"]}

    assert decisions["c0.drain_materialized_drain_summary"] == (
        "RETIRED_TO_ENTRY_PUBLICATION"
    )
    assert decisions["c0.drain_materialized_drain_summary_compiled_boundary"] == (
        "RETIRED_TO_ENTRY_PUBLICATION"
    )
    assert decisions["c0.work_item_summary_summary_path"] == (
        "RETIRED_TO_BRIDGE_METADATA"
    )
    assert decisions["c0.work_item_summary_summary_path_compiled_boundary"] == (
        "RETIRED_TO_BRIDGE_METADATA"
    )


def test_load_rendering_cleanup_manifest_requires_source_and_prerequisite_reports(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _manifest_payload()
    payload.pop("source_census")
    payload.pop("prerequisite_reports")
    manifest_path = _write_json(tmp_path / "rendering_cleanup.json", payload)

    with pytest.raises(ValueError, match="rendering_cleanup_manifest_schema_invalid"):
        module.load_rendering_cleanup_manifest(
            manifest_path,
            consumer_rendering_census=_consumer_payload(),
        )


def test_build_rendering_cleanup_report_joins_prior_lane_evidence() -> None:
    module = _module()
    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=_manifest_payload(),
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=_typed_prompt_input_report(),
        observability_summary_report=_observability_summary_report(),
        entry_publication_report=_entry_publication_report(),
        compatibility_bridge_report=_compatibility_bridge_report(),
        materialize_view_effects=[
            {"step_id": "root.__timed_view", "workflow_surface": "design_delta/example::run"}
        ],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload=_source_map_payload(),
    )

    assert report["schema_version"] == "workflow_lisp_rendering_cleanup_report.v1"
    assert report["status"] == "pass"
    assert report["decision_counts"]["BLOCKED"] == 1
    assert report["decision_counts"]["KEPT_BLOCKED_COMPATIBILITY"] == 1
    assert report["decision_counts"]["KEEP_TIMED_PUBLICATION"] == 1
    assert report["blocked_row_ids"] == ["c0.blocked_bridge", "c0.entry"]
    assert report["surviving_body_materialization_row_ids"] == ["c0.timed"]
    assert report["source_census"]["schema_version"] == "workflow_lisp_private_runtime_value_flow_census.v1"
    assert (
        report["prerequisite_reports"]["observability_summary_report"]["schema_version"]
        == "workflow_lisp_observability_summary_report.v1"
    )
    cleanup_rows = {
        row["c0_row_id"]: row for row in report["cleanup_decisions"]
    }
    observability_row = cleanup_rows["c0.observability"]
    assert observability_row["cleanup_id"]
    assert observability_row["u0_row_id"] == "u0.observability"
    assert observability_row["previous_track_c_decision"] == "RETIRE_TO_OBSERVABILITY"
    assert observability_row["cleanup_decision"] == "RETIRED_TO_OBSERVABILITY"
    assert observability_row["durability_before"] == "ephemeral"
    assert observability_row["durability_after"] == "none"
    assert observability_row["replacement_evidence"]["row_id"] == "c0.observability"
    assert observability_row["compiled_liveness"]["old_body_materialize_view_unreferenced"] is True
    assert observability_row["source_cleanup"] == {"allowed": False, "expected_files": []}
    blocked_bridge_row = cleanup_rows["c0.blocked_bridge"]
    assert blocked_bridge_row["blocked_by"] == {
        "adapter": "materialize_lisp_frontend_work_item_inputs",
        "reason": "certified adapter still consumes the bridge",
    }
    timed_row = cleanup_rows["c0.timed"]
    assert timed_row["timed_publication"]["materialize_view_step_ids"] == [
        "root.__timed_view"
    ]


def test_build_rendering_cleanup_report_rejects_prompt_row_with_durable_generated_view() -> None:
    module = _module()
    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=_manifest_payload(),
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=_typed_prompt_input_report(),
        observability_summary_report=_observability_summary_report(),
        entry_publication_report=_entry_publication_report(),
        compatibility_bridge_report=_compatibility_bridge_report(),
        materialize_view_effects=[
            {"step_id": "root.__prompt_view", "workflow_surface": "design_delta/example::run"}
        ],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload=_source_map_payload(),
    )

    assert report["status"] == "fail"
    assert report["diagnostics"][0]["code"] == "rendering_cleanup_prompt_allocated_durable_view"


def test_build_rendering_cleanup_report_requires_c1_evidence_for_keep_typed_prompt_rows() -> None:
    module = _module()
    manifest = _manifest_payload(
        rows=[
            {"c0_row_id": "c0.prompt", "decision": "KEEP_TYPED"},
            {"c0_row_id": "c0.observability", "decision": "RETIRED_TO_OBSERVABILITY"},
            {"c0_row_id": "c0.entry", "decision": "BLOCKED"},
            {"c0_row_id": "c0.bridge", "decision": "RETIRED_TO_BRIDGE_METADATA"},
            {"c0_row_id": "c0.blocked_bridge", "decision": "KEPT_BLOCKED_COMPATIBILITY"},
            {"c0_row_id": "c0.timed", "decision": "KEEP_TIMED_PUBLICATION"},
        ]
    )
    typed_prompt_input_report = _typed_prompt_input_report()
    typed_prompt_input_report["selected_rows"] = []

    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=manifest,
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=typed_prompt_input_report,
        observability_summary_report=_observability_summary_report(),
        entry_publication_report=_entry_publication_report(),
        compatibility_bridge_report=_compatibility_bridge_report(),
        materialize_view_effects=[
            {"step_id": "root.__timed_view", "workflow_surface": "design_delta/example::run"}
        ],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload=_source_map_payload(),
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]
        if diagnostic.get("c0_row_id") == "c0.prompt"
    } == {"rendering_cleanup_prerequisite_missing"}


@pytest.mark.parametrize(
    ("report_override", "expected_row_id"),
    [
        (
            {
                "typed_prompt_input_report": {
                    "schema_version": "wrong.schema",
                    "status": "fail",
                }
            },
            "c0.prompt",
        ),
        (
            {
                "entry_publication_report": {
                    "schema_version": "wrong.schema",
                    "status": "fail",
                }
            },
            "c0.entry",
        ),
        (
            {
                "compatibility_bridge_report": {
                    "schema_version": "wrong.schema",
                    "status": "fail",
                }
            },
            "c0.bridge",
        ),
    ],
)
def test_build_rendering_cleanup_report_fails_closed_on_non_passing_prerequisite_reports(
    report_override: dict[str, dict[str, object]],
    expected_row_id: str,
) -> None:
    module = _module()
    typed_prompt_input_report = _typed_prompt_input_report()
    entry_publication_report = _entry_publication_report()
    compatibility_bridge_report = _compatibility_bridge_report()

    if "typed_prompt_input_report" in report_override:
        typed_prompt_input_report.update(report_override["typed_prompt_input_report"])
    if "entry_publication_report" in report_override:
        entry_publication_report.update(report_override["entry_publication_report"])
    if "compatibility_bridge_report" in report_override:
        compatibility_bridge_report.update(
            report_override["compatibility_bridge_report"]
        )

    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=_manifest_payload(),
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=typed_prompt_input_report,
        observability_summary_report=_observability_summary_report(),
        entry_publication_report=entry_publication_report,
        compatibility_bridge_report=compatibility_bridge_report,
        materialize_view_effects=[
            {"step_id": "root.__timed_view", "workflow_surface": "design_delta/example::run"}
        ],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload=_source_map_payload(),
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"]
        for diagnostic in report["diagnostics"]
        if diagnostic.get("c0_row_id") == expected_row_id
    } == {"rendering_cleanup_prerequisite_missing"}


def test_build_rendering_cleanup_report_requires_observability_summary_evidence() -> None:
    module = _module()
    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=_manifest_payload(),
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=_typed_prompt_input_report(),
        observability_summary_report=None,
        entry_publication_report=_entry_publication_report(),
        compatibility_bridge_report=_compatibility_bridge_report(),
        materialize_view_effects=[],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload=_source_map_payload(),
    )

    assert report["status"] == "fail"
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } == {"rendering_cleanup_prerequisite_missing"}


def test_build_rendering_cleanup_report_requires_compiled_bridge_effect_evidence() -> None:
    module = _module()
    report = module.build_rendering_cleanup_report(
        workflow_family="design_delta_parent_drain",
        manifest=_manifest_payload(),
        consumer_rendering_census=_consumer_payload(),
        typed_prompt_input_report=_typed_prompt_input_report(),
        observability_summary_report=_observability_summary_report(),
        entry_publication_report=_entry_publication_report(),
        compatibility_bridge_report=_compatibility_bridge_report(),
        materialize_view_effects=[
            {"step_id": "root.__timed_view", "workflow_surface": "design_delta/example::run"}
        ],
        workflow_boundary_projection=_workflow_boundary_projection(),
        source_map_payload={
            "workflows": {
                "design_delta/example::run": {
                    "generated_semantic_effects": [],
                    "generated_path_allocations": [
                        {
                            "allocation_id": "bridge-allocation",
                            "privacy": "compatibility_view",
                            "semantic_role": "compatibility_pointer_view",
                        }
                    ],
                }
            }
        },
    )

    assert report["status"] == "fail"
    assert report["durability_reconciliation"]["durable_bridges_state_layout_allocated"] is False
    assert {
        diagnostic["code"] for diagnostic in report["diagnostics"]
    } == {"rendering_cleanup_contract_leak"}
