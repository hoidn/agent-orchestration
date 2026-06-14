from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


def _module():
    return importlib.import_module(
        "orchestrator.workflow_lisp.resume_plumbing_retirement"
    )


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _row(**overrides: object) -> dict[str, object]:
    row = {
        "row_id": "drain.loop.run_state_path",
        "workflow_surface": "lisp_frontend_design_delta/drain::drain",
        "source_kind": "loop_state_field",
        "symbol_or_field": "run_state_path",
        "path_or_contract": "RunStatePath",
        "plumbing_class": "resume_only",
        "boundary_authority_class": "compatibility_bridge",
        "track_owner": "R",
        "current_consumer": "runtime_resume",
        "semantic_owner": "runtime_resume",
        "source_evidence": [
            {
                "kind": "boundary_authority_report",
                "path": "boundary_authority_report.json",
            }
        ],
        "replacement_target": "Track R private lexical checkpoints",
        "bridge": {
            "bridge_owner": "lisp_frontend_design_delta/drain",
            "consumer": "runtime_resume",
            "file_shape": "json_state_pointer",
            "retirement_condition": "remove after private checkpoint restore replaces authored run-state loop carriage",
        },
        "command_boundary": None,
        "notes": "",
    }
    row.update(overrides)
    return row


def _census(rows: list[dict[str, object]]) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_design": "docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md",
        "coverage": {
            "workflow_surfaces": sorted({str(row["workflow_surface"]) for row in rows}),
            "required_source_kinds": ["loop_state_field"],
        },
        "rows": rows,
    }


def _compiled_row(**overrides: object) -> dict[str, object]:
    row = {
        "row_id": "drain.loop.run_state_path",
        "workflow_surface": "lisp_frontend_design_delta/drain::drain",
        "symbol_or_field": "run_state_path",
        "source_kind": "loop_state_field",
        "boundary_authority_class": "compatibility_bridge",
        "observed_locations": ["loop_state_field"],
        "semantic_authority_source": "typed_runtime_resource",
    }
    row.update(overrides)
    return row


def _checkpoint_points_payload(
    *,
    workflow_name: str = "lisp_frontend_design_delta/drain::drain",
    transition_identity: str = "write-drain-status",
    include_restore: bool = True,
    include_effect_policy: bool = True,
    include_transition_evidence: bool = True,
) -> dict[str, object]:
    loop_restore = ["pure_binding", "let_continuation"]
    if include_restore:
        loop_restore.append("loop_frame")
    effect_policy: dict[str, object] | None = None
    if include_effect_policy:
        evidence_requirements: dict[str, object] = {}
        if include_transition_evidence:
            evidence_requirements["transition"] = {
                "transition_identity": transition_identity
            }
        effect_policy = {
            "boundary_kind": "resource_transition",
            "effect_kind": "resource_transition",
            "policy": {
                "schema_version": "workflow_lisp_effect_resume_policy.v1",
                "policy_kind": "transition_idempotent_audit_required",
                "unsafe_pending_behavior": "audit_barrier",
                "evidence_requirements": evidence_requirements,
            },
        }
    return {
        "schema_version": "workflow_lisp_lexical_checkpoint_points.v1",
        "checkpoint_schema_version": "workflow_lisp_lexical_checkpoint.v1",
        "workflow_name": workflow_name,
        "points": [
            {
                "checkpoint_id": "ckpt:loop",
                "point_kind": "loop_back_edge",
                "workflow_name": workflow_name,
                "restore": {
                    "eligibility": loop_restore,
                },
            },
            {
                "checkpoint_id": "ckpt:effect",
                "point_kind": "effect_boundary",
                "workflow_name": workflow_name,
                "effect_boundary": effect_policy,
                "restore": {
                    "eligibility": ["pure_binding", "let_continuation"],
                },
            },
        ],
    }


def _checkpoint_shadow_report_payload(
    *,
    workflow_name: str = "lisp_frontend_design_delta/drain::drain",
    status: str = "pass",
) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_lexical_checkpoint_shadow_report.v1",
        "workflow_name": workflow_name,
        "status": status,
        "checked_points": 2,
        "checked_records": 0,
        "diagnostics": [],
    }


def test_select_resume_plumbing_retirement_candidates_from_checked_census() -> None:
    module = _module()
    census = _census(
        [
            _row(),
            _row(
                row_id="work_item.generated.phase_ctx_run_state_root",
                source_kind="generated_path",
                symbol_or_field="phase-ctx__run__state-root",
                path_or_contract="phase-ctx__run__state-root",
                boundary_authority_class="runtime_derived",
            ),
            _row(
                row_id="drain.output.return_run_state",
                source_kind="public_output",
                symbol_or_field="return__run-state",
                path_or_contract="return__run-state",
                plumbing_class="entry_publication",
                boundary_authority_class="public_artifact",
                track_owner="C",
                current_consumer="downstream_workflow",
                semantic_owner="workflow_surface",
                bridge=None,
                replacement_target="Track C entry publication policy",
            ),
        ]
    )

    candidates = module.select_resume_plumbing_retirement_candidates(census)

    assert [row["row_id"] for row in candidates] == [
        "drain.loop.run_state_path",
        "work_item.generated.phase_ctx_run_state_root",
    ]


def test_load_resume_plumbing_retirement_manifest_accepts_checked_compatibility_decision(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "resume_plumbing_retirement.json",
        {
            "schema_version": "workflow_lisp_resume_plumbing_retirement.v1",
            "target_family": "lisp_frontend_design_delta_parent_drain",
            "source_census": {
                "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
                "fingerprint": "sha256:census",
            },
            "decisions": [
                {
                    "row_id": "transitions.resource.drain_run_state",
                    "decision": "KEPT_COMPATIBILITY",
                    "remaining_consumer": "runtime_transition_bridge",
                    "retirement_condition": "remove after runtime-native resource backing no longer requires the bridge field",
                    "parity_constraint": "Track C public output and parity baseline still carry run_state",
                }
            ],
        },
    )

    manifest = module.load_resume_plumbing_retirement_manifest(path)

    assert manifest["schema_version"] == "workflow_lisp_resume_plumbing_retirement.v1"
    assert manifest["decisions"][0]["decision"] == "KEPT_COMPATIBILITY"


def test_load_resume_plumbing_retirement_manifest_rejects_missing_compatibility_metadata(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "resume_plumbing_retirement.json",
        {
            "schema_version": "workflow_lisp_resume_plumbing_retirement.v1",
            "target_family": "lisp_frontend_design_delta_parent_drain",
            "source_census": {
                "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json",
                "fingerprint": "sha256:census",
            },
            "decisions": [
                {
                    "row_id": "transitions.resource.drain_run_state",
                    "decision": "KEPT_COMPATIBILITY",
                }
            ],
        },
    )

    with pytest.raises(ValueError, match="resume_plumbing_retirement_compatibility_unjustified"):
        module.load_resume_plumbing_retirement_manifest(path)


def test_resume_plumbing_retirement_report_serialization_is_deterministic() -> None:
    module = _module()
    report = module.build_resume_plumbing_retirement_report(
        workflow_family="design_delta_parent_drain",
        census=_census([_row()]),
        census_fingerprint="sha256:census",
        compiled_rows=[],
        manifest=None,
        manifest_fingerprint=None,
        checkpoint_points_payload=_checkpoint_points_payload(),
        checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
    )

    first = module.serialize_resume_plumbing_retirement_report(report)
    second = module.serialize_resume_plumbing_retirement_report(report)

    assert first == second
    payload = json.loads(first)
    assert payload["source_census"]["fingerprint"] == "sha256:census"
    assert payload["manifest"] is None


def test_resume_plumbing_retirement_report_rejects_wrong_track_rows() -> None:
    module = _module()

    with pytest.raises(ValueError, match="resume_plumbing_retirement_wrong_track"):
        module.build_resume_plumbing_retirement_report(
            workflow_family="design_delta_parent_drain",
            census=_census(
                [
                    _row(
                        row_id="drain.output.return_run_state",
                        source_kind="public_output",
                        symbol_or_field="return__run-state",
                        path_or_contract="return__run-state",
                        plumbing_class="entry_publication",
                        boundary_authority_class="public_artifact",
                        track_owner="C",
                        current_consumer="downstream_workflow",
                        semantic_owner="workflow_surface",
                        bridge=None,
                        replacement_target="Track C entry publication policy",
                    )
                ]
            ),
            census_fingerprint="sha256:census",
            compiled_rows=[],
            manifest={
                "schema_version": "workflow_lisp_resume_plumbing_retirement.v1",
                "target_family": "lisp_frontend_design_delta_parent_drain",
                "source_census": {
                    "path": "checked.json",
                    "fingerprint": "sha256:census",
                },
                "decisions": [
                    {
                        "row_id": "drain.output.return_run_state",
                        "decision": "KEPT_COMPATIBILITY",
                        "remaining_consumer": "downstream_workflow",
                        "retirement_condition": "not in R5 scope",
                        "parity_constraint": "Track C owns terminal publication",
                    }
                ],
            },
            manifest_fingerprint="sha256:manifest",
            checkpoint_points_payload=_checkpoint_points_payload(),
            checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
        )


def test_resume_plumbing_retirement_report_rejects_checkpoint_or_report_authority() -> None:
    module = _module()

    with pytest.raises(
        ValueError,
        match="resume_plumbing_retirement_checkpoint_used_as_authority",
    ):
        module.build_resume_plumbing_retirement_report(
            workflow_family="design_delta_parent_drain",
            census=_census([_row()]),
            census_fingerprint="sha256:census",
            compiled_rows=[
                _compiled_row(
                    semantic_authority_source="checkpoint_record",
                    observed_locations=["replacement_authority"],
                )
            ],
            manifest=None,
            manifest_fingerprint=None,
            checkpoint_points_payload=_checkpoint_points_payload(),
            checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
        )


@pytest.mark.parametrize(
    ("points_payload", "shadow_report_payload", "expected_code"),
    [
        (
            _checkpoint_points_payload(include_restore=False),
            _checkpoint_shadow_report_payload(),
            "resume_plumbing_retirement_restore_evidence_missing",
        ),
        (
            _checkpoint_points_payload(include_effect_policy=False),
            _checkpoint_shadow_report_payload(),
            "resume_plumbing_retirement_effect_policy_missing",
        ),
        (
            _checkpoint_points_payload(include_transition_evidence=False),
            _checkpoint_shadow_report_payload(),
            "resume_plumbing_retirement_transition_evidence_missing",
        ),
        (
            _checkpoint_points_payload(),
            _checkpoint_shadow_report_payload(status="fail"),
            "resume_plumbing_retirement_restore_evidence_missing",
        ),
    ],
)
def test_resume_plumbing_retirement_report_fails_closed_without_required_checkpoint_evidence(
    points_payload: dict[str, object],
    shadow_report_payload: dict[str, object],
    expected_code: str,
) -> None:
    module = _module()

    report = module.build_resume_plumbing_retirement_report(
        workflow_family="design_delta_parent_drain",
        census=_census([_row()]),
        census_fingerprint="sha256:census",
        compiled_rows=[],
        manifest=None,
        manifest_fingerprint=None,
        checkpoint_points_payload=points_payload,
        checkpoint_shadow_report_payload=shadow_report_payload,
    )

    assert report["status"] == "fail"
    assert report["diagnostics"][0]["code"] == expected_code


def test_resume_plumbing_retirement_report_requires_row_specific_checkpoint_workflow_evidence() -> None:
    module = _module()

    report = module.build_resume_plumbing_retirement_report(
        workflow_family="design_delta_parent_drain",
        census=_census(
            [
                _row(
                    row_id="work_item.loop.run_state_path",
                    workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                )
            ]
        ),
        census_fingerprint="sha256:census",
        compiled_rows=[],
        manifest=None,
        manifest_fingerprint=None,
        checkpoint_points_payload=_checkpoint_points_payload(),
        checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
    )

    assert report["status"] == "fail"
    assert report["diagnostics"][0]["code"] == "resume_plumbing_retirement_restore_evidence_missing"


def test_resume_plumbing_retirement_report_accepts_matching_checkpoint_workflow_evidence() -> None:
    module = _module()

    report = module.build_resume_plumbing_retirement_report(
        workflow_family="design_delta_parent_drain",
        census=_census(
            [
                _row(
                    row_id="work_item.loop.run_state_path",
                    workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                )
            ]
        ),
        census_fingerprint="sha256:census",
        compiled_rows=[],
        manifest=None,
        manifest_fingerprint=None,
        checkpoint_points_payload=_checkpoint_points_payload(
            workflow_name="lisp_frontend_design_delta/work_item::run-work-item",
            transition_identity="record-terminal-work-item",
            include_restore=False,
        ),
        checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(
            workflow_name="lisp_frontend_design_delta/work_item::run-work-item"
        ),
    )

    assert report["status"] == "pass"
    assert report["diagnostics"] == []


def test_resume_plumbing_retirement_report_requires_checked_compatibility_for_drain_run_state_bridge() -> None:
    module = _module()

    with pytest.raises(
        ValueError,
        match="resume_plumbing_retirement_compatibility_unjustified",
    ):
        module.build_resume_plumbing_retirement_report(
            workflow_family="design_delta_parent_drain",
            census=_census([_row()]),
            census_fingerprint="sha256:census",
            compiled_rows=[
                {
                    "row_id": "transitions.resource.drain_run_state",
                    "workflow_surface": "lisp_frontend_design_delta/transitions",
                    "symbol_or_field": "drain-run-state",
                    "source_kind": "bridge_file",
                    "boundary_authority_class": "compatibility_bridge",
                    "observed_locations": ["resource_bridge_backing"],
                    "semantic_authority_source": "typed_runtime_resource",
                }
            ],
            manifest=None,
            manifest_fingerprint=None,
            checkpoint_points_payload=_checkpoint_points_payload(),
            checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
        )


def test_r6_default_resume_cleanup_candidates_consume_checked_r5_report() -> None:
    default_resume = importlib.import_module(
        "orchestrator.workflow_lisp.lexical_checkpoint_default_resume"
    )

    report = default_resume.build_default_resume_report(
        workflow_family="design_delta_parent_drain",
        workflow_name="lisp_frontend_design_delta/drain::drain",
        lowering_schema_version=2,
        checkpoint_points_payload=_checkpoint_points_payload(),
        checkpoint_shadow_report_payload=_checkpoint_shadow_report_payload(),
        resume_plumbing_retirement_report_payload={
            "schema_version": "workflow_lisp_resume_plumbing_retirement_report.v1",
            "workflow_family": "design_delta_parent_drain",
            "status": "pass",
            "decisions": [
                {
                    "row_id": "work_item.loop.run_state_path",
                    "decision": "KEPT_COMPATIBILITY",
                    "track_owner": "R",
                    "current_consumer": "runtime_transition_bridge",
                    "observed_locations": ["call_signature"],
                },
                {
                    "row_id": "transitions.resource.drain_run_state",
                    "decision": "KEPT_COMPATIBILITY",
                    "track_owner": "R",
                    "current_consumer": "runtime_transition_bridge",
                    "observed_locations": ["resource_bridge_backing"],
                },
            ],
        },
    )

    cleanup = {row["row_id"]: row for row in report["cleanup_candidates"]}
    assert cleanup["work_item.loop.run_state_path"]["r5_decision"] == "KEPT_COMPATIBILITY"
    assert cleanup["work_item.loop.run_state_path"]["cleanup_action"] in {
        "BLOCKED",
        "KEEP_HISTORICAL_ONLY",
    }
    assert cleanup["transitions.resource.drain_run_state"]["r5_decision"] == "KEPT_COMPATIBILITY"
