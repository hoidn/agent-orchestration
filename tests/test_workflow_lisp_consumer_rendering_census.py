from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DESIGN_DELTA_CONSUMER_RENDERING_CENSUS_PATH = (
    REPO_ROOT
    / "workflows"
    / "examples"
    / "inputs"
    / "workflow_lisp_migrations"
    / "design_delta_parent_drain.consumer_rendering_census.json"
)


def _module():
    return importlib.import_module("orchestrator.workflow_lisp.consumer_rendering_census")


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _u0_row(**overrides: object) -> dict[str, object]:
    row = {
        "row_id": "plan_phase.prompt.draft",
        "workflow_surface": "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "source_kind": "prompt_input_file",
        "symbol_or_field": "draft_prompt_path",
        "path_or_contract": "PromptInputFile",
        "plumbing_class": "prompt_rendering",
        "boundary_authority_class": "materialized_view",
        "track_owner": "C",
        "current_consumer": "provider_prompt",
        "semantic_owner": "workflow_surface",
        "source_evidence": [
            {
                "kind": "boundary_authority_report",
                "path": "boundary_authority_report.json",
            }
        ],
        "replacement_target": "Track C consumer-side rendering",
        "command_boundary": None,
        "bridge": None,
        "notes": "",
    }
    row.update(overrides)
    return row


def _u0_payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_design": "docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md",
        "coverage": {
            "workflow_surfaces": ["lisp_frontend_design_delta/plan_phase::run-plan-phase"],
            "required_source_kinds": ["prompt_input_file"],
        },
        "rows": rows or [_u0_row()],
    }


def _consumer_row(**overrides: object) -> dict[str, object]:
    row = {
        "row_id": "c0.plan_phase.prompt.draft",
        "u0_row_id": "plan_phase.prompt.draft",
        "workflow_surface": "lisp_frontend_design_delta/plan_phase::run-plan-phase",
        "source_kind": "prompt_input_file",
        "consumer_lane": "prompt_injection",
        "durability": "none",
        "renderer": {
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "accepted_shape": "any_pure_value",
        },
        "typed_value_source": {
            "kind": "sample_value_document",
            "value_document": {
                "draft_path": "artifacts/work/plan.md",
                "status": "APPROVED",
            },
        },
        "target_binding": {
            "kind": "consumer_owned_target",
            "target_labels": [
                "artifacts/work/plan_prompt_a.json",
                "artifacts/work/plan_prompt_b.json",
            ],
        },
        "track_c_decision": "KEEP_TYPED",
        "replacement_target": "typed prompt composition",
        "source_evidence": [
            {
                "kind": "u0_checked_row",
                "path": "design_delta_parent_drain.value_flow_census.json",
            },
            {
                "kind": "prompt_extern_manifest",
                "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json",
                "binding_name": "prompts.plan.draft",
            },
            {
                "kind": "provider_extern_manifest",
                "path": "workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json",
                "binding_name": "providers.plan.draft",
            }
        ],
        "command_boundary": None,
        "bridge": None,
        "notes": "",
    }
    row.update(overrides)
    return row


def _consumer_payload(*, rows: list[dict[str, object]] | None = None) -> dict[str, object]:
    return {
        "schema_version": "workflow_lisp_consumer_rendering_census.v1",
        "target_family": "lisp_frontend_design_delta_parent_drain",
        "source_design": "docs/design/workflow_lisp_private_runtime_state_and_consumer_value_flow.md",
        "source_census": {
            "path": (
                "workflows/examples/inputs/workflow_lisp_migrations/"
                "design_delta_parent_drain.value_flow_census.json"
            ),
            "schema_version": "workflow_lisp_private_runtime_value_flow_census.v1",
        },
        "coverage": {
            "consumer_lanes": ["prompt_injection"],
            "required_source_kinds": ["prompt_input_file"],
        },
        "rows": [_consumer_row()] if rows is None else rows,
    }


def _prompt_support_kwargs() -> dict[str, object]:
    return {
        "prompt_externs": {
            "prompts.plan.draft": {"input_file": "prompts/plan/draft.md"},
        },
        "prompt_externs_path": (
            "workflows/examples/inputs/workflow_lisp_migrations/"
            "design_delta_parent_drain.prompts.json"
        ),
        "provider_externs": {
            "providers.plan.draft": "codex",
        },
        "provider_externs_path": (
            "workflows/examples/inputs/workflow_lisp_migrations/"
            "design_delta_parent_drain.providers.json"
        ),
    }


def test_load_consumer_rendering_census_accepts_minimal_prompt_row(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(tmp_path / "consumer_rendering_census.json", _consumer_payload())

    payload = module.load_consumer_rendering_census(
        path,
        value_flow_census=_u0_payload(),
    )

    assert payload["schema_version"] == "workflow_lisp_consumer_rendering_census.v1"
    assert payload["target_family"] == "lisp_frontend_design_delta_parent_drain"
    assert [row["row_id"] for row in payload["rows"]] == ["c0.plan_phase.prompt.draft"]
    assert payload["source_census"]["path"].endswith(
        "design_delta_parent_drain.value_flow_census.json"
    )


def test_load_consumer_rendering_census_rejects_duplicate_row_id(tmp_path: Path) -> None:
    module = _module()
    payload = _consumer_payload(
        rows=[
            _consumer_row(),
            _consumer_row(u0_row_id="selector.prompt.select_next_work"),
        ]
    )
    path = _write_json(tmp_path / "duplicate-row-id.json", payload)

    with pytest.raises(ValueError, match="duplicate row_id"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_load_consumer_rendering_census_rejects_duplicate_u0_row_id_for_one_to_one_row(
    tmp_path: Path,
) -> None:
    module = _module()
    payload = _consumer_payload(
        rows=[
            _consumer_row(),
            _consumer_row(
                row_id="c0.plan_phase.prompt.draft.duplicate",
                consumer_lane="typed_step",
            ),
        ]
    )
    path = _write_json(tmp_path / "duplicate-u0-row-id.json", payload)

    with pytest.raises(ValueError, match="duplicate u0_row_id"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_load_consumer_rendering_census_rejects_unknown_consumer_lane(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-consumer-lane.json",
        _consumer_payload(rows=[_consumer_row(consumer_lane="not_a_real_lane")]),
    )

    with pytest.raises(ValueError, match="consumer_rendering_lane_invalid"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_load_consumer_rendering_census_rejects_unknown_durability(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-durability.json",
        _consumer_payload(rows=[_consumer_row(durability="not_a_real_durability")]),
    )

    with pytest.raises(ValueError, match="consumer_rendering_census_schema_invalid"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_load_consumer_rendering_census_rejects_unknown_track_c_decision(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-track-c-decision.json",
        _consumer_payload(rows=[_consumer_row(track_c_decision="RETIRE_SOMETHING_ELSE")]),
    )

    with pytest.raises(ValueError, match="consumer_rendering_census_schema_invalid"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_reconcile_consumer_rendering_census_rejects_missing_render_only_u0_row(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(tmp_path / "missing-row.json", _consumer_payload(rows=[]))
    manifest = module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())

    with pytest.raises(ValueError, match="consumer_rendering_census_row_missing"):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=_u0_payload(),
            materialize_view_effects=[],
            command_boundary_manifest={},
            **_prompt_support_kwargs(),
        )


def test_checked_design_delta_consumer_rendering_census_does_not_route_selection_bundle_bridge_through_bootstrap_adapter(
) -> None:
    payload = json.loads(
        DESIGN_DELTA_CONSUMER_RENDERING_CENSUS_PATH.read_text(encoding="utf-8")
    )

    assert all(
        row["row_id"] != "c0.work_item_pointer_selection_bundle_path_compiled_boundary"
        for row in payload["rows"]
    )


def test_load_consumer_rendering_census_rejects_unknown_renderer_id_version(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "unknown-renderer.json",
        _consumer_payload(
            rows=[
                _consumer_row(
                    renderer={
                        "renderer_id": "unknown-renderer",
                        "renderer_version": 99,
                        "accepted_shape": "any_pure_value",
                    }
                )
            ]
        ),
    )

    with pytest.raises(ValueError, match="consumer_rendering_renderer_unknown"):
        module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())


def test_reconcile_consumer_rendering_census_rejects_renderer_shape_mismatch(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "renderer-shape-mismatch.json",
        _consumer_payload(
            rows=[
                _consumer_row(
                    renderer={
                        "renderer_id": "posix-path-line",
                        "renderer_version": 1,
                        "accepted_shape": "path_value",
                    }
                )
            ]
        ),
    )
    manifest = module.load_consumer_rendering_census(path, value_flow_census=_u0_payload())

    with pytest.raises(ValueError, match="consumer_rendering_renderer_shape_mismatch"):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=_u0_payload(),
            materialize_view_effects=[],
            command_boundary_manifest={},
            **_prompt_support_kwargs(),
        )


def test_reconcile_consumer_rendering_census_rejects_target_path_reencoded_in_typed_value(
    tmp_path: Path,
) -> None:
    module = _module()
    path = _write_json(
        tmp_path / "semantic-input-leak.json",
        _consumer_payload(
            rows=[
                _consumer_row(
                    typed_value_source={
                        "kind": "sample_value_document",
                        "value_document": {
                            "prompt_path": "artifacts/work/plan_prompt_a.json",
                            "status": "APPROVED",
                        },
                    }
                )
            ]
        ),
    )
    manifest = module.load_consumer_rendering_census(
        path,
        value_flow_census=_u0_payload(),
    )

    with pytest.raises(
        ValueError,
        match="consumer_rendering_view_used_as_semantic_input",
    ):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=_u0_payload(),
            materialize_view_effects=[],
            command_boundary_manifest={},
            **_prompt_support_kwargs(),
        )


def test_reconcile_consumer_rendering_census_rejects_unclassified_body_materialization(
    tmp_path: Path,
) -> None:
    module = _module()
    u0_payload = _u0_payload(
        rows=[
            _u0_row(
                row_id="drain.materialized.drain_summary",
                workflow_surface="lisp_frontend_design_delta/drain::drain",
                source_kind="materialized_output",
                symbol_or_field="return__drain_summary",
                plumbing_class="human_rendering",
                current_consumer="observability",
            )
        ]
    )
    payload = _consumer_payload(
        rows=[
            _consumer_row(
                u0_row_id="drain.materialized.drain_summary",
                workflow_surface="lisp_frontend_design_delta/drain::drain",
                source_kind="materialized_output",
                consumer_lane="human_observability",
                durability="durable_timed_body",
                track_c_decision="KEEP_TYPED",
            )
        ]
    )
    path = _write_json(tmp_path / "body-materialization.json", payload)
    manifest = module.load_consumer_rendering_census(path, value_flow_census=u0_payload)

    with pytest.raises(ValueError, match="consumer_rendering_body_materialization_unclassified"):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=u0_payload,
            materialize_view_effects=[],
            command_boundary_manifest={},
        )


def test_reconcile_consumer_rendering_census_accepts_timed_body_with_observability_retirement_target(
    tmp_path: Path,
) -> None:
    module = _module()
    u0_payload = _u0_payload(
        rows=[
            _u0_row(
                row_id="implementation_phase.materialized.return_checks_report",
                workflow_surface="lisp_frontend_design_delta/implementation_phase::implementation-phase",
                source_kind="materialized_output",
                symbol_or_field="return__checks-report",
                plumbing_class="human_rendering",
                current_consumer="observability",
            )
        ]
    )
    payload = _consumer_payload(
        rows=[
            _consumer_row(
                row_id="c0.implementation_phase_materialized_return_checks_report",
                u0_row_id="implementation_phase.materialized.return_checks_report",
                workflow_surface="lisp_frontend_design_delta/implementation_phase::implementation-phase",
                source_kind="materialized_output",
                consumer_lane="timed_body_materialization",
                durability="durable_timed_body",
                track_c_decision="RETIRE_TO_OBSERVABILITY",
                compiled_effect_match={
                    "step_id_suffix": "__materialize_view__blocked_implementation_checks_report",
                },
            )
        ]
    )
    path = _write_json(tmp_path / "hybrid-timed-observability.json", payload)
    manifest = module.load_consumer_rendering_census(path, value_flow_census=u0_payload)

    report = module.reconcile_consumer_rendering_census(
        manifest=manifest,
        value_flow_census=u0_payload,
        materialize_view_effects=[
            {
                "effect_id": (
                    "effect:lisp_frontend_design_delta/implementation_phase::"
                    "implementation-phase:implementation_phase."
                    "__materialize_view__blocked_implementation_checks_report:"
                    "materialize_view"
                ),
                "authority_class": "materialized_view",
                "step_id": "implementation_phase.__materialize_view__blocked_implementation_checks_report",
                "workflow_surface": "lisp_frontend_design_delta/implementation_phase::implementation-phase",
                "renderer_id": "canonical-json",
                "renderer_version": 1,
            }
        ],
        command_boundary_manifest={},
    )

    assert report["status"] == "pass"
    assert report["invalid_rows"] == []


def test_reconcile_consumer_rendering_census_rejects_same_workflow_unmatched_materialize_view_effect(
    tmp_path: Path,
) -> None:
    module = _module()
    u0_payload = _u0_payload(
        rows=[
            _u0_row(
                row_id="drain.materialized.drain_summary",
                workflow_surface="lisp_frontend_design_delta/drain::drain",
                source_kind="materialized_output",
                symbol_or_field="return__drain-summary",
                plumbing_class="human_rendering",
                current_consumer="observability",
            )
        ]
    )
    payload = _consumer_payload(
        rows=[
            _consumer_row(
                row_id="c0.drain_materialized_drain_summary",
                u0_row_id="drain.materialized.drain_summary",
                workflow_surface="lisp_frontend_design_delta/drain::drain",
                source_kind="materialized_output",
                consumer_lane="timed_body_materialization",
                durability="durable_timed_body",
                track_c_decision="KEEP_TIMED_PUBLICATION",
                typed_value_source={
                    "kind": "sample_value_document",
                    "value_document": {
                        "drain_status": "DONE",
                        "drain_status_reason": "finished",
                        "run_state_path": "state/run_state.json",
                        "summary_target": "artifacts/work/drain_summary.json",
                        "state_version": "lisp_frontend_autonomous_drain_run_state/v1",
                    },
                },
                target_binding={
                    "kind": "consumer_owned_target",
                    "target_labels": [
                        "artifacts/proof/drain_summary.render_a.json",
                        "artifacts/proof/drain_summary.render_b.json",
                    ],
                },
                compiled_effect_match={
                    "step_id_suffix": "__materialize_view__drain_summary_view",
                },
            )
        ]
    )
    path = _write_json(tmp_path / "same-workflow-unmatched-effect.json", payload)
    manifest = module.load_consumer_rendering_census(path, value_flow_census=u0_payload)

    with pytest.raises(ValueError, match="consumer_rendering_census_row_missing"):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=u0_payload,
            materialize_view_effects=[
                {
                    "effect_id": (
                        "effect:lisp_frontend_design_delta/drain::drain:"
                        "root.lisp_frontend_design_delta_drain_drain__match_terminal__done__"
                        "materialize_view__drain_summary_view:materialize_view"
                    ),
                    "workflow_surface": "lisp_frontend_design_delta/drain::drain",
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "target_path": (
                        "root.steps.lisp_frontend_design_delta/drain::drain__match_terminal__"
                        "done__status.artifacts.summary_path"
                    ),
                    "value_type": {
                        "kind": "record",
                        "name": "lisp_frontend_design_delta/types::DrainSummaryValue",
                    },
                },
                {
                    "effect_id": (
                        "effect:lisp_frontend_design_delta/drain::drain:"
                        "root.lisp_frontend_design_delta_drain_drain__match_terminal__done__"
                        "materialize_view__synthetic_extra_drain_view:materialize_view"
                    ),
                    "workflow_surface": "lisp_frontend_design_delta/drain::drain",
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "target_path": (
                        "root.steps.lisp_frontend_design_delta/drain::drain__match_terminal__"
                        "done__status.artifacts.synthetic_summary_path"
                    ),
                    "value_type": {
                        "kind": "record",
                        "name": "lisp_frontend_design_delta/types::DrainSummaryValue",
                    },
                },
            ],
            command_boundary_manifest={},
        )


def test_load_consumer_rendering_census_rejects_bridge_row_without_bridge_metadata(
    tmp_path: Path,
) -> None:
    module = _module()
    u0_payload = _u0_payload(
        rows=[
            _u0_row(
                row_id="work_item.pointer.selection_bundle_path",
                workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                source_kind="pointer_path",
                symbol_or_field="selection_bundle_path",
                path_or_contract="SelectionBundlePath",
                plumbing_class="compatibility_bridge",
                boundary_authority_class="compatibility_bridge",
                current_consumer="materialize_lisp_frontend_work_item_inputs",
                bridge={
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "consumer": "materialize_lisp_frontend_work_item_inputs",
                    "file_shape": "pointer_file",
                    "retirement_condition": "remove when typed bootstrap replaces pointer transport",
                },
            )
        ]
    )
    payload = _consumer_payload(
        rows=[
            _consumer_row(
                u0_row_id="work_item.pointer.selection_bundle_path",
                workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                source_kind="pointer_path",
                consumer_lane="compatibility_bridge",
                durability="durable_bridge",
                track_c_decision="RETIRE_TO_BRIDGE_METADATA",
                bridge=None,
            )
        ]
    )
    path = _write_json(tmp_path / "missing-bridge-metadata.json", payload)

    with pytest.raises(ValueError, match="consumer_rendering_bridge_metadata_missing"):
        module.load_consumer_rendering_census(path, value_flow_census=u0_payload)


def test_reconcile_consumer_rendering_census_rejects_command_boundary_row_without_view_metadata(
    tmp_path: Path,
) -> None:
    module = _module()
    u0_payload = _u0_payload(
        rows=[
            _u0_row(
                row_id="work_item.command.selection_bundle_path",
                workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                source_kind="command_adapter_input",
                symbol_or_field="selection_bundle_path",
                path_or_contract="SelectionBundlePath",
                plumbing_class="compatibility_bridge",
                boundary_authority_class="compatibility_bridge",
                current_consumer="materialize_lisp_frontend_work_item_inputs",
                command_boundary={
                    "binding_name": "materialize_lisp_frontend_work_item_inputs",
                },
                bridge={
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "consumer": "materialize_lisp_frontend_work_item_inputs",
                    "file_shape": "command_input_file",
                    "retirement_condition": "remove when typed bootstrap replaces path transport",
                },
            )
        ]
    )
    payload = _consumer_payload(
        rows=[
            _consumer_row(
                u0_row_id="work_item.command.selection_bundle_path",
                workflow_surface="lisp_frontend_design_delta/work_item::run-work-item",
                source_kind="command_adapter_input",
                consumer_lane="compatibility_bridge",
                durability="durable_bridge",
                track_c_decision="RETIRE_TO_BRIDGE_METADATA",
                command_boundary={
                    "binding_name": "materialize_lisp_frontend_work_item_inputs",
                },
                bridge={
                    "bridge_owner": "lisp_frontend_design_delta/work_item",
                    "consumer": "materialize_lisp_frontend_work_item_inputs",
                    "file_shape": "command_input_file",
                    "retirement_condition": "remove when typed bootstrap replaces path transport",
                },
            )
        ]
    )
    path = _write_json(tmp_path / "missing-command-boundary-view-metadata.json", payload)
    manifest = module.load_consumer_rendering_census(path, value_flow_census=u0_payload)

    with pytest.raises(
        ValueError,
        match="consumer_rendering_command_boundary_missing",
    ):
        module.reconcile_consumer_rendering_census(
            manifest=manifest,
            value_flow_census=u0_payload,
            materialize_view_effects=[],
            boundary_authority_report={
                "workflows": [
                    {
                        "workflow_name": "lisp_frontend_design_delta/work_item::run-work-item",
                    }
                ]
            },
            command_boundary_manifest={
                "materialize_lisp_frontend_work_item_inputs": {
                    "evidence_refs": ["design_delta_work_item_inputs_ok"],
                }
            },
        )


def test_checked_in_design_delta_consumer_rendering_census_drops_work_item_command_bridge_row() -> None:
    payload = json.loads(
        DESIGN_DELTA_CONSUMER_RENDERING_CENSUS_PATH.read_text(encoding="utf-8")
    )

    assert {
        row["row_id"]
        for row in payload["rows"]
    }.isdisjoint({"c0.work_item_command_selection_bundle_path"})
