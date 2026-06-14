from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def _module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.lexical_checkpoint_default_resume"
    )


def _runtime_plan(
    *,
    workflow_name: str = "lisp_frontend_design_delta/drain::drain",
    points: tuple[object, ...] = (),
) -> object:
    return SimpleNamespace(
        workflow_name=workflow_name,
        lexical_checkpoint_points=points,
        observability=SimpleNamespace(has_compiled_frontend_lineage=True),
    )


def _point(
    *,
    checkpoint_id: str = "ckpt:loop",
    node_id: str = "root.loop",
    point_kind: str = "loop_back_edge",
    details: dict[str, object] | None = None,
) -> object:
    return SimpleNamespace(
        checkpoint_id=checkpoint_id,
        node_id=node_id,
        point_kind=point_kind,
        workflow_name="lisp_frontend_design_delta/drain::drain",
        details=details or {},
        origin_key="source:loop",
    )


def _checkpoint_points_payload(
    *,
    workflow_name: str = "lisp_frontend_design_delta/drain::drain",
    include_restore: bool = True,
    include_effect_policy: bool = True,
    include_transition_evidence: bool = True,
) -> dict[str, object]:
    restore_payload: dict[str, object] = {}
    if include_restore:
        restore_payload = {
            "restore": {
                "eligibility": ["pure_binding", "let_continuation", "loop_frame"],
            }
        }
    effect_boundary: dict[str, object] = {}
    if include_effect_policy:
        policy: dict[str, object] = {
            "schema_version": "workflow_lisp_effect_resume_policy.v1",
            "policy_kind": "transition_idempotent_audit_required",
            "unsafe_pending_behavior": "audit_barrier",
            "evidence_requirements": {},
        }
        if include_transition_evidence:
            policy["evidence_requirements"] = {
                "transition": {"transition_identity": "write-drain-status"}
            }
        effect_boundary = {
            "effect_boundary": {
                "boundary_kind": "resource_transition",
                "effect_kind": "resource_transition",
                "policy": policy,
            }
        }
    return {
        "schema_version": "workflow_lisp_lexical_checkpoint_points.v1",
        "checkpoint_schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "workflow_name": workflow_name,
        "points": [
            {
                "checkpoint_id": "ckpt:loop",
                "workflow_name": workflow_name,
                "point_kind": "loop_back_edge",
                "executable_identity": {"node_id": "root.loop"},
                **restore_payload,
            },
            {
                "checkpoint_id": "ckpt:effect",
                "workflow_name": workflow_name,
                "point_kind": "effect_boundary",
                "executable_identity": {"node_id": "root.transition"},
                "restore": {"eligibility": ["pure_binding"]},
                **effect_boundary,
            },
        ],
    }


def _retirement_report_payload(
    *,
    workflow_family: str = "design_delta_parent_drain",
    decisions: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_resume_plumbing_retirement_report.v1",
        "workflow_family": workflow_family,
        "status": "pass",
        "decisions": decisions
        or [
            {
                "row_id": "work_item.loop.run_state_path",
                "decision": "KEPT_COMPATIBILITY",
                "track_owner": "R",
                "current_consumer": "runtime_transition_bridge",
                "observed_locations": ["call_signature"],
            },
            {
                "row_id": "drain.output.return_run_state",
                "decision": "NOT_R5_TARGET",
                "track_owner": "C",
                "current_consumer": "downstream_workflow",
                "observed_locations": ["public_boundary"],
            },
        ],
    }


def _decision(**overrides: object) -> object:
    payload = {
        "kind": "RESTORED",
        "checkpoint_id": "ckpt:loop",
        "record_id": "record:loop",
        "source_map_origin_key": "source:loop",
        "diagnostics": (),
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def test_default_resume_serialization_is_deterministic() -> None:
    module = _module()
    policy = module.build_default_resume_policy(
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=2,
        is_workflow_lisp=True,
        runtime_plan=_runtime_plan(points=(_point(),)),
    )
    report = module.build_default_resume_report(
        workflow_family="design_delta_parent_drain",
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=2,
        checkpoint_points_payload=_checkpoint_points_payload(),
        checkpoint_shadow_report_payload={
            "schema_version": "workflow_lisp_lexical_checkpoint_shadow_report.v1",
            "status": "pass",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
        },
        resume_plumbing_retirement_report_payload=_retirement_report_payload(),
    )
    decision = module.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=_runtime_plan(points=(_point(),)),
        restart_node_id="root.loop",
        restore_selector=lambda **_: _decision(),
        is_workflow_lisp=True,
    )

    first = (
        module.serialize_default_resume_payload(policy),
        module.serialize_default_resume_payload(report),
        module.serialize_default_resume_payload(decision),
    )
    second = (
        module.serialize_default_resume_payload(policy),
        module.serialize_default_resume_payload(report),
        module.serialize_default_resume_payload(decision),
    )

    assert first == second
    assert json.loads(first[0])["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert json.loads(first[1])["schema_version"] == "workflow_lisp_checkpoint_default_resume_report.v1"
    assert json.loads(first[2])["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"


def test_runtime_default_resume_report_uses_report_schema() -> None:
    module = _module()

    report = module.build_runtime_default_resume_report(
        workflow_name="lisp_frontend_design_delta/drain::drain",
        decision=module.determine_runtime_default_resume_decision(
            state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
            runtime_plan=_runtime_plan(points=(_point(),)),
            restart_node_id="root.loop",
            restore_selector=lambda **_: _decision(),
            is_workflow_lisp=True,
        ),
    )

    assert report["schema_version"] == "workflow_lisp_checkpoint_default_resume_report.v1"
    assert report["checked_workflows"][0]["workflow_name"] == "lisp_frontend_design_delta/drain::drain"
    assert report["default_modes"][0]["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert report["status"] == "pass"


@pytest.mark.parametrize(
    ("lowering_schema_version", "is_workflow_lisp", "historical_compatibility", "expected_mode"),
    [
        (2, True, False, "LEXICAL_CHECKPOINT_DEFAULT"),
        (1, True, False, "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"),
        (2, True, True, "HISTORICAL_STEP_GRANULAR_COMPATIBILITY"),
        (None, False, False, "INELIGIBLE_STEP_GRANULAR"),
    ],
)
def test_build_default_resume_policy_classifies_route_modes(
    lowering_schema_version: int | None,
    is_workflow_lisp: bool,
    historical_compatibility: bool,
    expected_mode: str,
) -> None:
    module = _module()

    policy = module.build_default_resume_policy(
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=lowering_schema_version,
        is_workflow_lisp=is_workflow_lisp,
        historical_compatibility=historical_compatibility,
        runtime_plan=_runtime_plan(points=(_point(),) if lowering_schema_version == 2 else ()),
    )

    assert policy["default_mode"] == expected_mode


def test_runtime_default_resume_fails_closed_without_checkpoint_points() -> None:
    module = _module()

    decision = module.determine_runtime_default_resume_decision(
        state={"context": {"workflow_lisp": {"lowering_schema_version": 2}}},
        runtime_plan=_runtime_plan(points=()),
        restart_node_id="root.loop",
        restore_selector=lambda **_: _decision(),
        is_workflow_lisp=True,
    )

    assert decision["mode"] == "FAIL_CLOSED"
    assert "lexical_default_resume_checkpoint_points_missing" in decision["diagnostics"]


@pytest.mark.parametrize(
    ("points_payload", "retirement_payload", "expected_code"),
    [
        (
            _checkpoint_points_payload(include_restore=False),
            _retirement_report_payload(),
            "lexical_default_resume_restore_metadata_missing",
        ),
        (
            _checkpoint_points_payload(include_effect_policy=False),
            _retirement_report_payload(),
            "lexical_default_resume_effect_policy_missing",
        ),
        (
            _checkpoint_points_payload(include_transition_evidence=False),
            _retirement_report_payload(),
            "lexical_default_resume_transition_evidence_missing",
        ),
        (
            _checkpoint_points_payload(),
            None,
            "lexical_default_resume_retirement_evidence_missing",
        ),
    ],
)
def test_build_default_resume_report_fails_closed_without_required_evidence(
    points_payload: dict[str, object],
    retirement_payload: dict[str, object] | None,
    expected_code: str,
) -> None:
    module = _module()

    report = module.build_default_resume_report(
        workflow_family="design_delta_parent_drain",
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=2,
        checkpoint_points_payload=points_payload,
        checkpoint_shadow_report_payload={
            "schema_version": "workflow_lisp_lexical_checkpoint_shadow_report.v1",
            "status": "pass",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
        },
        resume_plumbing_retirement_report_payload=retirement_payload,
    )

    assert report["status"] == "fail"
    assert report["diagnostics"][0]["code"] == expected_code


def test_build_default_resume_report_populates_checked_workflow_and_mode_sections() -> None:
    module = _module()

    report = module.build_default_resume_report(
        workflow_family="design_delta_parent_drain",
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=2,
        checkpoint_points_payload=_checkpoint_points_payload(),
        checkpoint_shadow_report_payload={
            "schema_version": "workflow_lisp_lexical_checkpoint_shadow_report.v1",
            "status": "pass",
            "workflow_name": "lisp_frontend_design_delta/drain::drain",
        },
        resume_plumbing_retirement_report_payload=_retirement_report_payload(),
    )

    assert report["checked_workflows"][0]["route"]["default_mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert report["default_modes"][0]["mode"] == "LEXICAL_CHECKPOINT_DEFAULT"
    assert report["historical_compatibility"] == []
    assert report["fail_closed"] == []


def test_validate_default_resume_cleanup_candidate_blocks_still_consumed_and_wrong_track_rows() -> None:
    module = _module()

    blocked = module.validate_default_resume_cleanup_candidate(
        {
            "row_id": "work_item.loop.run_state_path",
            "track_owner": "R",
            "current_consumer": "runtime_transition_bridge",
            "decision": "KEPT_COMPATIBILITY",
        }
    )
    wrong_track = module.validate_default_resume_cleanup_candidate(
        {
            "row_id": "drain.output.return_run_state",
            "track_owner": "C",
            "current_consumer": "downstream_workflow",
            "decision": "NOT_R5_TARGET",
        }
    )

    assert blocked["cleanup_action"] in {"BLOCKED", "KEEP_HISTORICAL_ONLY"}
    assert blocked["diagnostics"][0]["code"] == "lexical_default_resume_cleanup_consumer_exists"
    assert wrong_track["cleanup_action"] == "BLOCKED"
    assert wrong_track["diagnostics"][0]["code"] == "lexical_default_resume_cleanup_wrong_track"


@pytest.mark.parametrize(
    ("row", "expected_action"),
    [
        (
            {
                "row_id": "drain.publish.run_state_path",
                "track_owner": "R",
                "plumbing_class": "resume_only",
                "boundary_authority_class": "public_artifact",
                "semantic_owner": "workflow_surface",
                "decision": "RETIRED",
            },
            "KEEP_HISTORICAL_ONLY",
        ),
        (
            {
                "row_id": "transitions.resource.drain_run_state",
                "track_owner": "R",
                "plumbing_class": "resume_only",
                "boundary_authority_class": "compatibility_bridge",
                "semantic_owner": "domain_resource",
                "decision": "HIDDEN_PRIVATE",
            },
            "BLOCKED",
        ),
    ],
)
def test_validate_default_resume_cleanup_candidate_protects_public_artifact_and_domain_resource_rows(
    row: dict[str, object],
    expected_action: str,
) -> None:
    module = _module()

    candidate = module.validate_default_resume_cleanup_candidate(row)

    assert candidate["cleanup_action"] == expected_action


@pytest.mark.parametrize("authority_source", ["checkpoint_record", "checkpoint_path", "report_path"])
def test_validate_default_resume_cleanup_candidate_rejects_checkpoint_or_report_authority(
    authority_source: str,
) -> None:
    module = _module()

    with pytest.raises(
        ValueError,
        match="lexical_default_resume_checkpoint_used_as_authority",
    ):
        module.validate_default_resume_cleanup_candidate(
            {
                "row_id": "work_item.loop.run_state_path",
                "track_owner": "R",
                "current_consumer": "runtime_resume",
                "decision": "RETIRED",
                "authority_source": authority_source,
            }
        )
