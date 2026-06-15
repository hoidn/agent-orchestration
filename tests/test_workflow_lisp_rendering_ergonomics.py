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


def test_load_policy_rejects_typed_step_with_renderer(tmp_path):
    bad = json.loads(POLICY_PATH.read_text())
    bad["consumer_slots"][0]["consumer_lane"] = "typed_step"
    bad["consumer_slots"][0]["renderer_selection"] = {"mode": "infer"}
    target = tmp_path / "bad_typed.json"
    target.write_text(json.dumps(bad))
    with pytest.raises(ValueError) as exc:
        load_rendering_ergonomics_policy(target)
    assert "rendering_ergonomics_policy_schema_invalid" in str(exc.value)
