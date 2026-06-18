"""C6 author-facing rendering-ergonomics regression surface.

Contract: docs/plans/LISP-PRIVATE-RUNTIME-VALUE-FLOW-DRAIN/design-gaps/
workflow-lisp-private-runtime-state-and-consumer-value-flow-c6-author-facing-rendering-ergonomics/
implementation_architecture.md
Target design: docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md
(Sec 7.2, 7.6, 8, 10 C6, 12, 13).

These tests assert on stable diagnostic codes, schema ids, lane/resolution sets,
and dataflow — never on prompt prose.
"""
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.rendering_ergonomics import (
    RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
    RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION,
    ALLOWED_CONSUMER_LANES,
    ALLOWED_RESOLUTIONS,
    load_rendering_ergonomics_policy,
    build_rendering_ergonomics_report,
    resolve_renderer_for_slot,
    rendering_ergonomics_author_lints,
)

REPO = Path(__file__).resolve().parents[1]
POLICY_PATH = (
    REPO
    / "workflows/examples/inputs/workflow_lisp_migrations/"
    "design_delta_parent_drain.rendering_ergonomics.json"
)


def test_schema_version_constants_are_exact():
    assert (
        RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION
        == "workflow_lisp_rendering_ergonomics_policy.v1"
    )
    assert (
        RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION
        == "workflow_lisp_rendering_ergonomics_report.v1"
    )


def test_allowed_lanes_and_resolutions_are_exact():
    assert ALLOWED_CONSUMER_LANES == frozenset(
        {
            "typed_step",
            "prompt_input",
            "observability",
            "entry_publication",
            "compatibility_bridge",
            "timed_body_materialization",
        }
    )
    assert ALLOWED_RESOLUTIONS == frozenset(
        {
            "selected",
            "not_rendered",
            "requires_override",
            "blocked",
        }
    )


def test_load_policy_accepts_checked_manifest():
    policy = load_rendering_ergonomics_policy(POLICY_PATH)
    assert policy["schema_version"] == RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION
    assert policy["target_family"] == "lisp_frontend_design_delta_parent_drain"
    assert policy["consumer_slots"], "policy must enumerate at least one consumer slot"
    architect_slot = next(
        slot
        for slot in policy["consumer_slots"]
        if slot["c0_row_id"] == "c0.design_gap_architect_prompt_draft"
    )
    assert architect_slot["request_shape"] == {
        "request_type_name": "DesignGapArchitectureRequest",
        "subject_type_name": "DesignGapArchitecturePromptSubject",
        "targets_type_name": "DesignGapArchitectureProviderTargets",
        "requires_request_record": True,
        "requires_target_split": True,
    }


def test_checked_design_delta_summary_slots_use_entry_publication_and_bridge_lanes():
    policy = load_rendering_ergonomics_policy(POLICY_PATH)
    slots_by_row = {slot["c0_row_id"]: slot for slot in policy["consumer_slots"]}

    assert (
        slots_by_row["c0.drain_materialized_drain_summary"]["consumer_lane"]
        == "entry_publication"
    )
    assert (
        slots_by_row["c0.drain_materialized_drain_summary_compiled_boundary"][
            "consumer_lane"
        ]
        == "entry_publication"
    )
    assert (
        slots_by_row["c0.work_item_summary_summary_path"]["consumer_lane"]
        == "compatibility_bridge"
    )
    assert (
        slots_by_row["c0.work_item_summary_summary_path_compiled_boundary"][
            "consumer_lane"
        ]
        == "compatibility_bridge"
    )


def test_load_policy_rejects_wrong_schema_version(tmp_path):
    bad = json.loads(POLICY_PATH.read_text())
    bad["schema_version"] = "workflow_lisp_rendering_ergonomics_policy.v0"
    target = tmp_path / "bad.json"
    target.write_text(json.dumps(bad))
    with pytest.raises(ValueError) as exc:
        load_rendering_ergonomics_policy(target)
    assert "rendering_ergonomics_policy_schema_invalid" in str(exc.value)


def test_load_policy_rejects_unknown_consumer_lane(tmp_path):
    bad = json.loads(POLICY_PATH.read_text())
    bad["consumer_slots"][0]["consumer_lane"] = "not_a_lane"
    target = tmp_path / "bad_lane.json"
    target.write_text(json.dumps(bad))
    with pytest.raises(ValueError) as exc:
        load_rendering_ergonomics_policy(target)
    assert "rendering_ergonomics_policy_schema_invalid" in str(exc.value)


# --------------------------------------------------------------------------- #
# Renderer resolution (Task 3)
# --------------------------------------------------------------------------- #


def test_typed_step_resolves_not_rendered():
    slot = {
        "slot_id": "s.typed",
        "consumer_lane": "typed_step",
        "renderer_selection": {"mode": "none"},
        "value": {"type_name": "DrainResult"},
    }
    result = resolve_renderer_for_slot(slot)
    assert result["resolution"] == "not_rendered"
    assert result["selected_renderer"] is None


def test_single_candidate_resolves_selected():
    slot = {
        "slot_id": "s.prompt",
        "consumer_lane": "prompt_input",
        "renderer_selection": {
            "mode": "infer",
            "allowed_renderers": [{"renderer_id": "canonical-json", "renderer_version": 1}],
            "override_allowed": True,
        },
        "value": {"type_name": "PlanPromptContext", "authority": "typed_value"},
    }
    result = resolve_renderer_for_slot(slot)
    assert result["resolution"] == "selected"
    assert result["selected_renderer"]["renderer_id"] == "canonical-json"


def test_two_valid_candidates_resolve_requires_override_with_ambiguous_diagnostic():
    slot = {
        "slot_id": "s.ambiguous",
        "consumer_lane": "compatibility_bridge",
        "renderer_selection": {
            "mode": "infer",
            "allowed_renderers": [
                {"renderer_id": "canonical-json", "renderer_version": 1},
                {"renderer_id": "posix-path-line", "renderer_version": 1},
            ],
            "override_allowed": True,
        },
        "value": {"type_name": "PathString", "authority": "typed_value"},
    }
    result = resolve_renderer_for_slot(slot)
    assert result["resolution"] == "requires_override"
    codes = [d["code"] for d in result["diagnostics"]]
    assert "rendering_ergonomics_renderer_ambiguous" in codes
    amb = next(
        d for d in result["diagnostics"] if d["code"] == "rendering_ergonomics_renderer_ambiguous"
    )
    assert amb["slot_id"] == "s.ambiguous"
    assert {"canonical-json", "posix-path-line"} <= {
        c["renderer_id"] for c in amb["candidate_renderers"]
    }


def test_zero_candidates_resolve_requires_override_with_required_diagnostic():
    slot = {
        "slot_id": "s.none",
        "consumer_lane": "entry_publication",
        "renderer_selection": {"mode": "infer", "allowed_renderers": [], "override_allowed": True},
        "value": {"type_name": "DrainResult"},
    }
    result = resolve_renderer_for_slot(slot)
    assert result["resolution"] == "requires_override"
    assert any(
        d["code"] == "rendering_ergonomics_renderer_required" for d in result["diagnostics"]
    )


def test_unknown_override_renderer_is_rejected():
    slot = {
        "slot_id": "s.bad",
        "consumer_lane": "entry_publication",
        "renderer_selection": {
            "mode": "override",
            "local_override": {"renderer_id": "nope", "renderer_version": 9},
            "override_allowed": True,
        },
        "value": {"type_name": "DrainResult"},
    }
    result = resolve_renderer_for_slot(slot)
    assert any(
        d["code"] == "rendering_ergonomics_renderer_unknown" for d in result["diagnostics"]
    )


# --------------------------------------------------------------------------- #
# Report assembly joining C0-C5 evidence (Task 4) — real report shapes
# --------------------------------------------------------------------------- #


def _min_reports(**overrides):
    base = {
        "consumer_rendering_census_report": {"status": "pass", "rows": []},
        "typed_prompt_input_report": {"status": "pass", "selected_rows": []},
        "observability_summary_report": {"status": "pass", "selected_c0_row_ids": []},
        "entry_publication_report": {"status": "pass", "selected_c0_rows": []},
        "compatibility_bridge_report": {
            "status": "pass",
            "generated_bridges": [],
            "blocked_bridges": [],
        },
        "rendering_cleanup_report": {"status": "pass", "cleanup_decisions": []},
    }
    base.update(overrides)
    return base


def _typed_step_policy():
    return {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [
            {
                "slot_id": "s.typed",
                "consumer_lane": "typed_step",
                "c0_row_id": "c0.x",
                "renderer_selection": {"mode": "none"},
                "value": {"type_name": "DrainResult"},
            }
        ],
    }


def test_report_passes_when_every_selected_row_has_slot_and_lane():
    policy = _typed_step_policy()
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.x", "consumer_lane": "none"}],
        }
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["schema_version"] == RENDERING_ERGONOMICS_REPORT_SCHEMA_VERSION
    assert report["status"] == "pass"
    assert set(report["contract_isolation"]) == {
        "typed_steps_do_not_consume_views",
        "provider_inputs_use_typed_prompt_lane",
        "entry_publications_use_publish_policy",
        "bridges_use_metadata",
        "body_materialize_views_timed_or_compatibility_only",
    }


def test_report_fails_when_selected_row_has_no_slot():
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.orphan", "consumer_lane": "prompt_injection"}],
        }
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_consumer_slot_missing" for d in report["diagnostics"]
    )


def test_report_fails_on_missing_prerequisite():
    policy = _typed_step_policy()
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.x", "consumer_lane": "none"}],
        }
    )
    del reports["compatibility_bridge_report"]
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_prerequisite_missing" for d in report["diagnostics"]
    )


def test_report_fails_on_body_render_not_timed():
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [
            {
                "slot_id": "s.timed",
                "consumer_lane": "timed_body_materialization",
                "expected_track_c_lane": "C5",
                "c0_row_id": "c0.body",
                "renderer_selection": {
                    "mode": "infer",
                    "allowed_renderers": [{"renderer_id": "canonical-json", "renderer_version": 1}],
                },
                "value": {"type_name": "Summary"},
            }
        ],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.body", "consumer_lane": "timed_body_materialization"}],
        }
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_body_render_not_timed" for d in report["diagnostics"]
    )
    assert report["body_render_lints"]


# --------------------------------------------------------------------------- #
# Provider :inputs typed value -> C1 lane (Task 7)
# --------------------------------------------------------------------------- #


def _prompt_slot(c0_row_id="c0.plan_phase_prompt_draft"):
    return {
        "slot_id": "provider.plan.draft.inputs.plan_context",
        "consumer_lane": "prompt_input",
        "expected_track_c_lane": "C1",
        "c0_row_id": c0_row_id,
        "source_form": {"kind": "provider_input"},
        "renderer_selection": {
            "mode": "infer",
            "allowed_renderers": [{"renderer_id": "canonical-json", "renderer_version": 1}],
            "override_allowed": True,
        },
        "value": {"type_name": "PlanPromptContext", "authority": "typed_value"},
    }


def test_provider_inputs_typed_value_selects_c1_lane_without_prompt_file():
    slot = _prompt_slot()
    resolution = resolve_renderer_for_slot(slot)
    assert resolution["resolution"] == "selected"
    assert resolution["selected_lane"] == "C1_TYPED_PROMPT_INPUT"

    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [{"c0_row_id": slot["c0_row_id"]}],
        },
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "pass"
    assert not any(
        d["code"] == "rendering_ergonomics_prompt_file_still_required"
        for d in report["diagnostics"]
    )


def test_provider_inputs_still_requiring_prompt_file_fails():
    slot = _prompt_slot()
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [
                {
                    "c0_row_id": slot["c0_row_id"],
                    "prompt_input_file": "artifacts/work/plan_context.prompt.txt",
                }
            ],
        },
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_prompt_file_still_required"
        for d in report["diagnostics"]
    )


def test_provider_input_shapes_emit_owned_request_record_observations():
    slot = _prompt_slot("c0.plan_phase_prompt_review")
    slot["workflow_surface"] = "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    slot["u0_row_id"] = "plan_phase.prompt.review"
    slot["source_form"]["provider_call_locator"] = "providers.plan.review"
    slot["request_shape"] = {
        "request_type_name": "PlanReviewRequest",
        "subject_type_name": "PlanReviewPromptSubject",
        "targets_type_name": "PlanReviewProviderTargets",
        "requires_request_record": True,
        "requires_target_split": True,
    }
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [
                {
                    "workflow_surface": slot["workflow_surface"],
                    "provider_step_id": "root.plan.review",
                    "c0_row_id": slot["c0_row_id"],
                    "u0_row_id": slot["u0_row_id"],
                    "binding_names": ["request"],
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "source_map_origin_keys": [slot["workflow_surface"]],
                }
            ],
        },
    )

    report = build_rendering_ergonomics_report(
        policy=policy,
        prerequisite_reports=reports,
        provider_input_observations=[
            {
                "workflow_surface": slot["workflow_surface"],
                "provider_call_locator": "providers.plan.review",
                "provider_step_id": "root.plan.review",
                "c0_row_id": slot["c0_row_id"],
                "binding_names": ["request"],
                "binding_count": 1,
                "value_type_name": "PlanReviewRequest",
                "request_fields": {
                    "subject_type_name": "PlanReviewPromptSubject",
                    "targets_type_name": "PlanReviewProviderTargets",
                },
            }
        ],
    )

    assert report["status"] == "pass"
    provider_shapes = {row["c0_row_id"]: row for row in report["provider_input_shapes"]}
    assert provider_shapes[slot["c0_row_id"]]["request_type_name"] == "PlanReviewRequest"
    assert not report["diagnostics"]


def test_provider_input_shapes_fail_when_nested_subject_or_targets_types_drift():
    slot = _prompt_slot("c0.plan_phase_prompt_review")
    slot["workflow_surface"] = "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    slot["u0_row_id"] = "plan_phase.prompt.review"
    slot["source_form"]["provider_call_locator"] = "providers.plan.review"
    slot["request_shape"] = {
        "request_type_name": "PlanReviewRequest",
        "subject_type_name": "PlanReviewPromptSubject",
        "targets_type_name": "PlanReviewProviderTargets",
        "requires_request_record": True,
        "requires_target_split": True,
    }
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [
                {
                    "workflow_surface": slot["workflow_surface"],
                    "provider_step_id": "root.plan.review",
                    "c0_row_id": slot["c0_row_id"],
                    "u0_row_id": slot["u0_row_id"],
                    "binding_names": ["request"],
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "source_map_origin_keys": [slot["workflow_surface"]],
                }
            ],
        },
    )

    report = build_rendering_ergonomics_report(
        policy=policy,
        prerequisite_reports=reports,
        provider_input_observations=[
            {
                "workflow_surface": slot["workflow_surface"],
                "provider_call_locator": "providers.plan.review",
                "provider_step_id": "root.plan.review",
                "c0_row_id": slot["c0_row_id"],
                "binding_names": ["request"],
                "binding_count": 1,
                "value_type_name": "PlanReviewRequest",
                "request_fields": {
                    "field_names": ["subject", "targets"],
                    "subject_type_name": "WrongSubjectType",
                    "targets_type_name": "WrongTargetsType",
                    "semantic_field_count": 4,
                    "write_target_field_count": 2,
                },
            }
        ],
    )

    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_provider_request_record_missing"
        and d.get("expected_subject_type") == "PlanReviewPromptSubject"
        and d.get("observed_subject_type") == "WrongSubjectType"
        for d in report["diagnostics"]
    )
    assert any(
        d["code"] == "rendering_ergonomics_provider_write_target_unclassified"
        and d.get("expected_targets_type") == "PlanReviewProviderTargets"
        and d.get("observed_targets_type") == "WrongTargetsType"
        for d in report["diagnostics"]
    )


def test_provider_input_shapes_fail_when_request_record_is_flattened():
    slot = _prompt_slot("c0.plan_phase_prompt_review")
    slot["workflow_surface"] = "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    slot["u0_row_id"] = "plan_phase.prompt.review"
    slot["source_form"]["provider_call_locator"] = "providers.plan.review"
    slot["request_shape"] = {
        "request_type_name": "PlanReviewRequest",
        "subject_type_name": "PlanReviewPromptSubject",
        "targets_type_name": "PlanReviewProviderTargets",
        "requires_request_record": True,
        "requires_target_split": True,
    }
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [
                {
                    "workflow_surface": slot["workflow_surface"],
                    "provider_step_id": "root.plan.review",
                    "c0_row_id": slot["c0_row_id"],
                    "u0_row_id": slot["u0_row_id"],
                    "binding_names": ["subject", "targets"],
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "source_map_origin_keys": [slot["workflow_surface"]],
                }
            ],
        },
    )

    report = build_rendering_ergonomics_report(
        policy=policy,
        prerequisite_reports=reports,
        provider_input_observations=[
            {
                "workflow_surface": slot["workflow_surface"],
                "provider_call_locator": "providers.plan.review",
                "provider_step_id": "root.plan.review",
                "c0_row_id": slot["c0_row_id"],
                "binding_names": ["subject", "targets"],
                "binding_count": 2,
                "value_type_name": "PlanReviewRequest",
            }
        ],
    )

    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_provider_flat_input_list_nontrivial"
        for d in report["diagnostics"]
    )


def test_provider_input_shapes_fail_when_targets_split_is_missing():
    slot = _prompt_slot("c0.plan_phase_prompt_review")
    slot["workflow_surface"] = "lisp_frontend_design_delta/plan_phase::run-plan-phase"
    slot["u0_row_id"] = "plan_phase.prompt.review"
    slot["source_form"]["provider_call_locator"] = "providers.plan.review"
    slot["request_shape"] = {
        "request_type_name": "PlanReviewRequest",
        "subject_type_name": "PlanReviewPromptSubject",
        "targets_type_name": "PlanReviewProviderTargets",
        "requires_request_record": True,
        "requires_target_split": True,
    }
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [slot],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": slot["c0_row_id"], "consumer_lane": "prompt_injection"}],
        },
        typed_prompt_input_report={
            "status": "pass",
            "selected_rows": [
                {
                    "workflow_surface": slot["workflow_surface"],
                    "provider_step_id": "root.plan.review",
                    "c0_row_id": slot["c0_row_id"],
                    "u0_row_id": slot["u0_row_id"],
                    "binding_names": ["request"],
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "source_map_origin_keys": [slot["workflow_surface"]],
                }
            ],
        },
    )

    report = build_rendering_ergonomics_report(
        policy=policy,
        prerequisite_reports=reports,
        provider_input_observations=[
            {
                "workflow_surface": slot["workflow_surface"],
                "provider_call_locator": "providers.plan.review",
                "provider_step_id": "root.plan.review",
                "c0_row_id": slot["c0_row_id"],
                "binding_names": ["request"],
                "binding_count": 1,
                "value_type_name": "PlanReviewRequest",
                "request_fields": {
                    "field_names": ["subject"],
                    "subject_type_name": "PlanReviewPromptSubject",
                    "semantic_field_count": 4,
                    "write_target_field_count": 0,
                },
            }
        ],
    )

    assert report["status"] == "fail"
    assert any(
        d["code"] == "rendering_ergonomics_provider_write_target_unclassified"
        for d in report["diagnostics"]
    )


# --------------------------------------------------------------------------- #
# Author-facing lints (Task 5)
# --------------------------------------------------------------------------- #


def test_command_glue_rendering_is_linted():
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [
            {
                "slot_id": "s.glue",
                "consumer_lane": "entry_publication",
                "expected_track_c_lane": "C3",
                "c0_row_id": "c0.glue",
                "rendering_implementation": "inline_python",
                "renderer_selection": {
                    "mode": "infer",
                    "allowed_renderers": [{"renderer_id": "canonical-json", "renderer_version": 1}],
                },
                "value": {"type_name": "Bundle"},
            }
        ],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.glue", "consumer_lane": "entry_publication"}],
        },
        entry_publication_report={"status": "pass", "selected_c0_rows": ["c0.glue"]},
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    assert report["status"] == "fail"
    lints = rendering_ergonomics_author_lints(report)
    assert any(d["code"] == "rendering_ergonomics_command_glue_forbidden" for d in lints)


def test_body_render_not_timed_names_replacement_lane_via_author_lints():
    policy = {
        "schema_version": RENDERING_ERGONOMICS_POLICY_SCHEMA_VERSION,
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "consumer_slots": [
            {
                "slot_id": "s.body",
                "consumer_lane": "timed_body_materialization",
                "expected_track_c_lane": "C5",
                "c0_row_id": "c0.body",
                "renderer_selection": {
                    "mode": "infer",
                    "allowed_renderers": [{"renderer_id": "canonical-json", "renderer_version": 1}],
                },
                "value": {"type_name": "Summary"},
            }
        ],
    }
    reports = _min_reports(
        consumer_rendering_census_report={
            "status": "pass",
            "rows": [{"row_id": "c0.body", "consumer_lane": "timed_body_materialization"}],
        }
    )
    report = build_rendering_ergonomics_report(policy=policy, prerequisite_reports=reports)
    lints = rendering_ergonomics_author_lints(report)
    body = next(
        d for d in lints if d["code"] == "rendering_ergonomics_body_render_not_timed"
    )
    assert body["replacement_lane"]


def test_load_policy_rejects_typed_step_with_renderer(tmp_path):
    bad = json.loads(POLICY_PATH.read_text())
    bad["consumer_slots"][0]["consumer_lane"] = "typed_step"
    bad["consumer_slots"][0]["renderer_selection"] = {"mode": "infer"}
    target = tmp_path / "bad_typed.json"
    target.write_text(json.dumps(bad))
    with pytest.raises(ValueError) as exc:
        load_rendering_ergonomics_policy(target)
    assert "rendering_ergonomics_policy_schema_invalid" in str(exc.value)
