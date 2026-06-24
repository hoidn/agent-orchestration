from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.providers.executor import ProviderExecutor


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
TYPED_PROMPT_INPUT_FIXTURE = VALID_FIXTURES / "typed_prompt_input_phase.orc"


def _typed_prompt_inputs_module():
    return importlib.import_module("orchestrator.workflow_lisp.typed_prompt_inputs")


def _compile_typed_prompt_input_bundle(tmp_path: Path):
    result = compile_stage3_module(
        TYPED_PROMPT_INPUT_FIXTURE,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )
    return next(
        bundle
        for name, bundle in result.validated_bundles.items()
        if name.endswith("run-typed-prompt-phase-demo")
    )


def _initialize_typed_prompt_input_workspace(workspace: Path) -> None:
    (workspace / "docs" / "design").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "plans").mkdir(parents=True, exist_ok=True)
    (workspace / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (workspace / "docs" / "design" / "workflow_lisp_frontend_specification.md").write_text(
        "# design\n",
        encoding="utf-8",
    )
    (workspace / "docs" / "plans" / "typed_prompt_input_plan.md").write_text(
        "# plan\n",
        encoding="utf-8",
    )


def _typed_prompt_input_bound_inputs(bundle) -> dict[str, str]:
    bound_inputs: dict[str, str] = {
        "inputs__prompt_context__design": "docs/design/workflow_lisp_frontend_specification.md",
        "inputs__prompt_context__plan": "docs/plans/typed_prompt_input_plan.md",
        "inputs__prompt_context__focus": "prefer typed values over producer-owned prompt files",
    }
    for input_name, contract in bundle.surface.inputs.items():
        definition = getattr(contract, "definition", {})
        default_value = definition.get("default") if hasattr(definition, "get") else None
        if isinstance(default_value, str):
            bound_inputs.setdefault(input_name, default_value)
        if "execution_report_target" in input_name:
            bound_inputs[input_name] = "artifacts/work/execution_report.md"
        if "progress_report_target" in input_name:
            bound_inputs[input_name] = "artifacts/work/progress_report.md"
    return bound_inputs


def _provider_step(bundle):
    return next(step for step in bundle.surface.steps if step.kind is SurfaceStepKind.PROVIDER)


def test_normalize_typed_prompt_input_entry_canonicalizes_metadata() -> None:
    module = _typed_prompt_inputs_module()
    normalized = module.normalize_typed_prompt_input_entry(
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "prompt_context",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
            "value_type_name": "PromptContext",
            "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
            "u0_row_id": "u0.fixture.prompt_context",
            "c0_row_id": "c0.fixture.prompt_context",
            "injection_order": 0,
        }
    )

    assert normalized["binding_name"] == "prompt_context"
    assert normalized["renderer"]["renderer_id"] == "canonical-json"
    assert normalized["source_map_origin_key"].startswith("typed_prompt_input_phase::")


def test_normalize_typed_prompt_input_entry_preserves_request_field_authority() -> None:
    module = _typed_prompt_inputs_module()
    normalized = module.normalize_typed_prompt_input_entry(
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "request",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {"kind": "typed_binding_ref", "binding": {"subject": {"run_state": {"ref": "inputs.ctx__run_state_path"}}}},
            "value_type_name": "SelectorRequest",
            "source_map_origin_key": "lisp_frontend_design_delta/selector::select-next-work",
            "u0_row_id": "selector.prompt.select_next_work",
            "c0_row_id": "c0.selector_prompt_select_next_work",
            "injection_order": 0,
            "request_fields": {
                "field_names": ["subject"],
                "has_subject": True,
                "has_targets": False,
                "field_authority": {
                    "subject.run_state": {
                        "authority_class": "compatibility_bridge",
                        "source_binding": "ctx.run_state_path",
                        "bridge_field_name": "run_state_path",
                    }
                },
            },
        }
    )

    assert normalized["request_fields"]["field_authority"]["subject.run_state"] == {
        "authority_class": "compatibility_bridge",
        "source_binding": "ctx.run_state_path",
        "bridge_field_name": "run_state_path",
    }


def test_render_typed_prompt_inputs_serializes_runtime_evidence() -> None:
    module = _typed_prompt_inputs_module()
    prompt_block, evidence = module.render_typed_prompt_inputs(
        [
            module.normalize_typed_prompt_input_entry(
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                    "value_type_name": "PromptContext",
                    "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                    "u0_row_id": "u0.fixture.prompt_context",
                    "c0_row_id": "c0.fixture.prompt_context",
                    "injection_order": 0,
                }
            )
        ],
        resolved_typed_values={
            "prompt_context": {
                "design": "docs/design/workflow_lisp_frontend_specification.md",
                "plan": "docs/plans/typed_prompt_input_plan.md",
                "focus": "prefer typed values",
            }
        },
        workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
        step_id="root.run-typed-prompt-phase-demo__attempt",
    )

    assert '"focus":"prefer typed values"' in prompt_block
    assert evidence
    assert evidence[0]["schema_version"] == "workflow_lisp_typed_prompt_input_evidence.v1"
    assert evidence[0]["binding_name"] == "prompt_context"


def test_render_typed_prompt_inputs_records_hidden_bridge_leaf_evidence() -> None:
    module = _typed_prompt_inputs_module()
    prompt_block, evidence = module.render_typed_prompt_inputs(
        [
            module.normalize_typed_prompt_input_entry(
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "request",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "value_source": {
                        "kind": "typed_binding_ref",
                        "binding": {
                            "subject": {"run_state": {"ref": "inputs.ctx__run_state_path"}}
                        },
                    },
                    "value_type_name": "SelectorRequest",
                    "source_map_origin_key": "lisp_frontend_design_delta/selector::select-next-work",
                    "u0_row_id": "selector.prompt.select_next_work",
                    "c0_row_id": "c0.selector_prompt_select_next_work",
                    "injection_order": 0,
                    "request_fields": {
                        "field_names": ["subject"],
                        "has_subject": True,
                        "has_targets": False,
                        "field_authority": {
                            "subject.run_state": {
                                "authority_class": "compatibility_bridge",
                                "source_binding": "ctx.run_state_path",
                                "bridge_field_name": "run_state_path",
                            }
                        },
                    },
                }
            )
        ],
        resolved_typed_values={
            "request": {"subject": {"run_state": "state/run_state.json"}}
        },
        workflow_name="lisp_frontend_design_delta/selector::select-next-work",
        step_id="root.select-next-work__decision",
    )

    assert '"run_state":"state/run_state.json"' in prompt_block
    assert evidence[0]["request_field_evidence"] == [
        {
            "field_path": "subject.run_state",
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.run_state_path",
            "bridge_field_name": "run_state_path",
            "rendered_leaf_shape": "scalar_path",
            "rendered_leaf_digest": module.typed_prompt_input_value_digest(
                "state/run_state.json"
            ),
        }
    ]


def test_normalize_typed_prompt_input_entry_rejects_missing_lineage() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="c0_row_id|u0_row_id|source_map_origin_key"):
        module.normalize_typed_prompt_input_entry(
            {
                "schema_version": "workflow_lisp_typed_prompt_input.v1",
                "binding_name": "prompt_context",
                "renderer": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "accepted_shape": "any_pure_value",
                },
                "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                "value_type_name": "PromptContext",
                "injection_order": 0,
            }
        )


def test_render_typed_prompt_inputs_rejects_unknown_renderer() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_renderer_unknown"):
        module.render_typed_prompt_inputs(
            [
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "unknown-renderer",
                        "renderer_version": 99,
                        "accepted_shape": "any_pure_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                    "value_type_name": "PromptContext",
                    "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                    "u0_row_id": "u0.fixture.prompt_context",
                    "c0_row_id": "c0.fixture.prompt_context",
                    "injection_order": 0,
                }
            ],
            resolved_typed_values={"prompt_context": {"focus": "prefer typed values"}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_render_typed_prompt_inputs_rejects_shape_mismatch() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_renderer_shape_mismatch"):
        module.render_typed_prompt_inputs(
            [
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "posix-path-line",
                        "renderer_version": 1,
                        "accepted_shape": "path_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                    "value_type_name": "PromptContext",
                    "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                    "u0_row_id": "u0.fixture.prompt_context",
                    "c0_row_id": "c0.fixture.prompt_context",
                    "injection_order": 0,
                }
            ],
            resolved_typed_values={"prompt_context": {"focus": "prefer typed values"}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_render_typed_prompt_inputs_rejects_non_json_like_value() -> None:
    module = _typed_prompt_inputs_module()
    with pytest.raises(ValueError, match="typed_prompt_input_value_unavailable|typed_prompt_input_renderer_shape_mismatch"):
        module.render_typed_prompt_inputs(
            [
                {
                    "schema_version": "workflow_lisp_typed_prompt_input.v1",
                    "binding_name": "prompt_context",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "value_source": {"kind": "typed_binding_ref", "ref": "inputs.prompt_context"},
                    "value_type_name": "PromptContext",
                    "source_map_origin_key": "typed_prompt_input_phase::run-typed-prompt-phase-demo",
                    "u0_row_id": "u0.fixture.prompt_context",
                    "c0_row_id": "c0.fixture.prompt_context",
                    "injection_order": 0,
                }
            ],
            resolved_typed_values={"prompt_context": {"bad": {1, 2, 3}}},
            workflow_name="typed_prompt_input_phase::run-typed-prompt-phase-demo",
            step_id="root.run-typed-prompt-phase-demo__attempt",
        )


def test_build_typed_prompt_input_report_indexes_imported_private_surfaces() -> None:
    module = _typed_prompt_inputs_module()
    imported_bundle = SimpleNamespace(
        surface=SimpleNamespace(
            name="%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1",
            steps=(
                SimpleNamespace(
                    kind=SurfaceStepKind.PROVIDER,
                    step_id="root.review-plan__result",
                    typed_prompt_inputs=(
                        {
                            "schema_version": "workflow_lisp_typed_prompt_input.v1",
                            "binding_name": "request",
                            "renderer": {
                                "renderer_id": "canonical-json",
                                "renderer_version": 1,
                                "accepted_shape": "any_pure_value",
                            },
                            "value_source": {
                                "kind": "typed_binding_ref",
                                "binding": {"ref": "inputs.request"},
                            },
                            "value_type_name": "PlanReviewRequest",
                            "source_map_origin_key": "%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1",
                            "u0_row_id": "plan_phase.prompt.review",
                            "c0_row_id": "c0.plan_phase_prompt_review",
                            "injection_order": 0,
                        },
                    ),
                ),
            ),
        ),
        imports={},
    )
    top_level_bundle = SimpleNamespace(
        surface=SimpleNamespace(name="lisp_frontend_design_delta/plan_phase::run-plan-phase", steps=()),
        imports={imported_bundle.surface.name: imported_bundle},
    )

    report = module.build_typed_prompt_input_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest={
            "rows": [
                {
                    "row_id": "c0.plan_phase_prompt_review",
                    "u0_row_id": "plan_phase.prompt.review",
                    "workflow_surface": "%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "KEEP_TYPED",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                }
            ]
        },
        checked_manifest_path="checked.json",
        checked_manifest_sha256="sha256:test",
        validated_bundles_by_name={
            top_level_bundle.surface.name: top_level_bundle,
        },
    )

    assert report["status"] == "pass"
    assert report["missing_rows"] == []
    assert report["selected_rows"] == [
        {
            "workflow_surface": "%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1",
            "provider_step_id": "root.review-plan__result",
            "c0_row_id": "c0.plan_phase_prompt_review",
            "u0_row_id": "plan_phase.prompt.review",
            "binding_names": ["request"],
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "source_map_origin_keys": [
                "%plan_phase.lisp_frontend_design_delta/plan_phase::review-plan.v1"
            ],
        }
    ]


def test_build_typed_prompt_input_report_records_hidden_bridge_field_expectation() -> None:
    module = _typed_prompt_inputs_module()
    selector_bundle = SimpleNamespace(
        surface=SimpleNamespace(
            name="lisp_frontend_design_delta/selector::select-next-work",
            steps=(
                SimpleNamespace(
                    kind=SurfaceStepKind.PROVIDER,
                    step_id="root.select-next-work__decision",
                    typed_prompt_inputs=(
                        {
                            "schema_version": "workflow_lisp_typed_prompt_input.v1",
                            "binding_name": "request",
                            "renderer": {
                                "renderer_id": "canonical-json",
                                "renderer_version": 1,
                                "accepted_shape": "any_pure_value",
                            },
                            "value_source": {
                                "kind": "typed_binding_ref",
                                "binding": {
                                    "subject": {
                                        "run_state": {
                                            "ref": "inputs.ctx__run_state_path"
                                        }
                                    }
                                },
                            },
                            "value_type_name": "SelectorRequest",
                            "source_map_origin_key": "lisp_frontend_design_delta/selector::select-next-work",
                            "u0_row_id": "selector.prompt.select_next_work",
                            "c0_row_id": "c0.selector_prompt_select_next_work",
                            "injection_order": 0,
                            "request_fields": {
                                "field_names": ["subject"],
                                "has_subject": True,
                                "has_targets": False,
                                "field_authority": {
                                    "subject.run_state": {
                                        "authority_class": "compatibility_bridge",
                                        "source_binding": "ctx.run_state_path",
                                        "bridge_field_name": "run_state_path",
                                    }
                                },
                            },
                        },
                    ),
                ),
            ),
        ),
        imports={},
    )

    report = module.build_typed_prompt_input_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest={
            "rows": [
                {
                    "row_id": "c0.selector_prompt_select_next_work",
                    "u0_row_id": "selector.prompt.select_next_work",
                    "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "KEEP_TYPED",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "request_field_expectations": [
                        {
                            "field_path": "subject.run_state",
                            "authority_class": "compatibility_bridge",
                            "source_binding": "ctx.run_state_path",
                            "bridge_field_name": "run_state_path",
                        }
                    ],
                }
            ]
        },
        checked_manifest_path="checked.json",
        checked_manifest_sha256="sha256:test",
        validated_bundles_by_name={selector_bundle.surface.name: selector_bundle},
    )

    selector_row = report["selected_rows"][0]
    assert selector_row["request_fields"]["field_authority"]["subject.run_state"] == {
        "authority_class": "compatibility_bridge",
        "source_binding": "ctx.run_state_path",
        "bridge_field_name": "run_state_path",
    }


@pytest.mark.parametrize(
    ("field_authority", "expected_code"),
    [
        (
            {
                "subject.run_state": {
                    "authority_class": "compatibility_bridge",
                    "bridge_field_name": "run_state_path",
                }
            },
            "typed_prompt_input_hidden_bridge_source_unmapped",
        ),
        (
            {
                "subject.run_state": {
                    "authority_class": "runtime_derived",
                    "source_binding": "ctx.run_state_path",
                    "bridge_field_name": "run_state_path",
                }
            },
            "typed_prompt_input_hidden_bridge_authority_mismatch",
        ),
        (
            {
                "subject.run_state": {
                    "authority_class": "compatibility_bridge",
                    "source_binding": "ctx.run_state_path",
                    "bridge_field_name": "wrong_field_name",
                }
            },
            "typed_prompt_input_hidden_bridge_bridge_field_mismatch",
        ),
    ],
)
def test_build_typed_prompt_input_report_fails_closed_on_hidden_bridge_field_drift(
    field_authority: dict[str, dict[str, str]],
    expected_code: str,
) -> None:
    module = _typed_prompt_inputs_module()
    selector_bundle = SimpleNamespace(
        surface=SimpleNamespace(
            name="lisp_frontend_design_delta/selector::select-next-work",
            steps=(
                SimpleNamespace(
                    kind=SurfaceStepKind.PROVIDER,
                    step_id="root.select-next-work__decision",
                    typed_prompt_inputs=(
                        {
                            "schema_version": "workflow_lisp_typed_prompt_input.v1",
                            "binding_name": "request",
                            "renderer": {
                                "renderer_id": "canonical-json",
                                "renderer_version": 1,
                                "accepted_shape": "any_pure_value",
                            },
                            "value_source": {
                                "kind": "typed_binding_ref",
                                "binding": {
                                    "subject": {
                                        "run_state": {
                                            "ref": "inputs.ctx__run_state_path"
                                        }
                                    }
                                },
                            },
                            "value_type_name": "SelectorRequest",
                            "source_map_origin_key": "lisp_frontend_design_delta/selector::select-next-work",
                            "u0_row_id": "selector.prompt.select_next_work",
                            "c0_row_id": "c0.selector_prompt_select_next_work",
                            "injection_order": 0,
                            "request_fields": {
                                "field_names": ["subject"],
                                "has_subject": True,
                                "has_targets": False,
                                "field_authority": field_authority,
                            },
                        },
                    ),
                ),
            ),
        ),
        imports={},
    )

    report = module.build_typed_prompt_input_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest={
            "rows": [
                {
                    "row_id": "c0.selector_prompt_select_next_work",
                    "u0_row_id": "selector.prompt.select_next_work",
                    "workflow_surface": "lisp_frontend_design_delta/selector::select-next-work",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "KEEP_TYPED",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                    "request_field_expectations": [
                        {
                            "field_path": "subject.run_state",
                            "authority_class": "compatibility_bridge",
                            "source_binding": "ctx.run_state_path",
                            "bridge_field_name": "run_state_path",
                        }
                    ],
                }
            ]
        },
        checked_manifest_path="checked.json",
        checked_manifest_sha256="sha256:test",
        validated_bundles_by_name={selector_bundle.surface.name: selector_bundle},
    )

    assert report["status"] == "fail"
    assert any(row["code"] == expected_code for row in report["invalid_rows"])


def test_build_typed_prompt_input_report_records_consume_prompt_mode_evidence_without_body_content() -> None:
    module = _typed_prompt_inputs_module()
    execution_log_body = "execute evidence\nsecond line\n"
    private_notes_body = "private notes\n"
    consume_bundle = SimpleNamespace(
        surface=SimpleNamespace(
            name="consume_prompt_demo::review",
            artifacts={
                "baseline_design": SimpleNamespace(kind="relpath", definition={"type": "relpath"}),
                "execution_log": SimpleNamespace(kind="string", definition={"type": "string"}),
                "private_notes": SimpleNamespace(kind="string", definition={"type": "string"}),
                "filtered_attachment": SimpleNamespace(kind="string", definition={"type": "string"}),
            },
            steps=(
                SimpleNamespace(
                    kind=SurfaceStepKind.PROVIDER,
                    step_id="root.review",
                    prompt_consumes=(
                        "baseline_design",
                        "execution_log",
                        "private_notes",
                    ),
                    typed_prompt_inputs=(),
                    consumes=(
                        {
                            "artifact": "baseline_design",
                            "prompt": {
                                "mode": "reference",
                                "label": "Baseline design",
                                "role": "compatibility_baseline",
                            },
                        },
                        {
                            "artifact": "execution_log",
                            "prompt": {"mode": "content"},
                        },
                        {
                            "artifact": "private_notes",
                            "prompt": {"mode": "none", "role": "internal_only"},
                        },
                        {
                            "artifact": "filtered_attachment",
                            "prompt": {"mode": "content"},
                        },
                    ),
                ),
            ),
        ),
        imports={},
    )

    report = module.build_typed_prompt_input_report(
        workflow_family="consume_prompt_demo",
        checked_manifest={
            "rows": [
                {
                    "row_id": "c0.consume_prompt.baseline_design",
                    "u0_row_id": "u0.consume_prompt.baseline_design",
                    "workflow_surface": "consume_prompt_demo::review",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "RETIRED_TO_PROMPT_RENDERING",
                    "artifact_name": "baseline_design",
                    "typed_value_source": {
                        "kind": "sample_value_document",
                        "value_document": "docs/design/workflow_lisp_frontend_specification.md",
                    },
                },
                {
                    "row_id": "c0.consume_prompt.execution_log",
                    "u0_row_id": "u0.consume_prompt.execution_log",
                    "workflow_surface": "consume_prompt_demo::review",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "RETIRED_TO_PROMPT_RENDERING",
                    "artifact_name": "execution_log",
                    "typed_value_source": {
                        "kind": "sample_value_document",
                        "value_document": execution_log_body,
                    },
                },
                {
                    "row_id": "c0.consume_prompt.private_notes",
                    "u0_row_id": "u0.consume_prompt.private_notes",
                    "workflow_surface": "consume_prompt_demo::review",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "RETIRED_TO_PROMPT_RENDERING",
                    "artifact_name": "private_notes",
                    "typed_value_source": {
                        "kind": "sample_value_document",
                        "value_document": private_notes_body,
                    },
                },
                {
                    "row_id": "c0.consume_prompt.filtered_attachment",
                    "u0_row_id": "u0.consume_prompt.filtered_attachment",
                    "workflow_surface": "consume_prompt_demo::review",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "RETIRED_TO_PROMPT_RENDERING",
                    "artifact_name": "filtered_attachment",
                    "typed_value_source": {
                        "kind": "sample_value_document",
                        "value_document": "filtered body\n",
                    },
                }
            ]
        },
        checked_manifest_path="checked.json",
        checked_manifest_sha256="sha256:test",
        validated_bundles_by_name={
            consume_bundle.surface.name: consume_bundle,
        },
    )

    rows_by_artifact = {
        row["artifact_name"]: row for row in report["consumed_artifact_prompt_rows"]
    }
    assert set(rows_by_artifact) == {
        "baseline_design",
        "execution_log",
        "private_notes",
        "filtered_attachment",
    }

    baseline_design = rows_by_artifact["baseline_design"]
    assert baseline_design == {
        "workflow_surface": "consume_prompt_demo::review",
        "provider_step_id": "root.review",
        "c0_row_id": "c0.consume_prompt.baseline_design",
        "u0_row_id": "u0.consume_prompt.baseline_design",
        "artifact_name": "baseline_design",
        "mode": "reference",
        "label": "Baseline design",
        "role": "compatibility_baseline",
        "value_kind": "relpath",
        "rendered_policy": "rendered_reference",
        "rendered_bytes_count": len(
            "docs/design/workflow_lisp_frontend_specification.md".encode("utf-8")
        ),
        "rendered_value_digest": module.typed_prompt_input_value_digest(
            "docs/design/workflow_lisp_frontend_specification.md"
        ),
        "rendered_value_reference": "docs/design/workflow_lisp_frontend_specification.md",
        "omission_reason": None,
    }

    execution_log = rows_by_artifact["execution_log"]
    assert execution_log == {
        "workflow_surface": "consume_prompt_demo::review",
        "provider_step_id": "root.review",
        "c0_row_id": "c0.consume_prompt.execution_log",
        "u0_row_id": "u0.consume_prompt.execution_log",
        "artifact_name": "execution_log",
        "mode": "content",
        "label": None,
        "role": None,
        "value_kind": "string",
        "rendered_policy": "rendered_content",
        "rendered_bytes_count": len(execution_log_body.encode("utf-8")),
        "rendered_value_digest": module.typed_prompt_input_value_digest(execution_log_body),
        "omission_reason": None,
    }

    private_notes = rows_by_artifact["private_notes"]
    assert private_notes == {
        "workflow_surface": "consume_prompt_demo::review",
        "provider_step_id": "root.review",
        "c0_row_id": "c0.consume_prompt.private_notes",
        "u0_row_id": "u0.consume_prompt.private_notes",
        "artifact_name": "private_notes",
        "mode": "none",
        "label": None,
        "role": "internal_only",
        "value_kind": "string",
        "rendered_policy": "omitted",
        "rendered_bytes_count": None,
        "rendered_value_digest": None,
        "omission_reason": "mode_none",
    }

    filtered_attachment = rows_by_artifact["filtered_attachment"]
    assert filtered_attachment == {
        "workflow_surface": "consume_prompt_demo::review",
        "provider_step_id": "root.review",
        "c0_row_id": "c0.consume_prompt.filtered_attachment",
        "u0_row_id": "u0.consume_prompt.filtered_attachment",
        "artifact_name": "filtered_attachment",
        "mode": "content",
        "label": None,
        "role": None,
        "value_kind": "string",
        "rendered_policy": "omitted",
        "rendered_bytes_count": None,
        "rendered_value_digest": None,
        "omission_reason": "prompt_consumes_filtered",
    }

    serialized_rows = json.dumps(report["consumed_artifact_prompt_rows"])
    assert execution_log_body not in serialized_rows
    assert private_notes_body not in serialized_rows


def test_build_typed_prompt_input_report_keeps_design_delta_consume_prompt_rows_empty_until_authored_consumes_exist() -> None:
    module = _typed_prompt_inputs_module()
    report = module.build_typed_prompt_input_report(
        workflow_family="design_delta_parent_drain",
        checked_manifest={
            "rows": [
                {
                    "row_id": "c0.plan_phase_prompt_draft",
                    "u0_row_id": "plan_phase.prompt.draft",
                    "workflow_surface": "lisp_frontend_design_delta/plan_phase::run-plan-phase",
                    "consumer_lane": "prompt_injection",
                    "track_c_decision": "KEEP_TYPED",
                    "renderer": {
                        "renderer_id": "canonical-json",
                        "renderer_version": 1,
                        "accepted_shape": "any_pure_value",
                    },
                }
            ]
        },
        checked_manifest_path="checked.json",
        checked_manifest_sha256="sha256:test",
        validated_bundles_by_name={},
    )

    assert report["consumed_artifact_prompt_rows"] == []


def test_runtime_smoke_renders_typed_prompt_inputs_without_prompt_materialization(
    tmp_path: Path,
) -> None:
    _initialize_typed_prompt_input_workspace(tmp_path)
    bundle = _compile_typed_prompt_input_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="typed-prompt-input-runtime")
    state_manager.initialize(
        TYPED_PROMPT_INPUT_FIXTURE.as_posix(),
        bound_inputs=_typed_prompt_input_bound_inputs(bundle),
    )
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)
    captured: dict[str, object] = {"prompt": "", "output_bundle_path": ""}

    def _prepare_invocation(_self, *args, **kwargs):
        captured["prompt"] = kwargs.get("prompt_content", "")
        env = dict(kwargs.get("env") or {})
        captured["output_bundle_path"] = env.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "")
        return SimpleNamespace(input_mode="stdin", prompt=captured["prompt"], env=env), None

    def _execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / "artifacts" / "work" / "execution_report.md").write_text(
            "# execution report\n",
            encoding="utf-8",
        )
        bundle_path.write_text(
            json.dumps(
                {
                    "variant": "COMPLETED",
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute(on_error="stop")

    provider_step = _provider_step(bundle)
    assert state["steps"][provider_step.name]["exit_code"] == 0
    assert getattr(provider_step, "typed_prompt_inputs")
    assert not any(
        step.kind is SurfaceStepKind.MATERIALIZE_ARTIFACTS and "prompt_inputs" in step.step_id
        for step in bundle.surface.steps
    )
    evidence_root = (
        tmp_path
        / ".orchestrate"
        / "runs"
        / "typed-prompt-input-runtime"
        / "workflow_lisp"
        / "typed_prompt_inputs"
    )
    assert evidence_root.exists()
    assert "prefer typed values over producer-owned prompt files" in str(captured["prompt"])


def test_typed_prompt_input_evidence_does_not_replace_provider_output_authority(
    tmp_path: Path,
) -> None:
    _initialize_typed_prompt_input_workspace(tmp_path)
    bundle = _compile_typed_prompt_input_bundle(tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="typed-prompt-input-authority")
    state_manager.initialize(
        TYPED_PROMPT_INPUT_FIXTURE.as_posix(),
        bound_inputs=_typed_prompt_input_bound_inputs(bundle),
    )
    executor = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0)

    def _prepare_invocation(_self, *args, **kwargs):
        return SimpleNamespace(input_mode="stdin", prompt=kwargs.get("prompt_content", ""), env=dict(kwargs.get("env") or {})), None

    def _execute(_self, invocation, **_kwargs):
        wrong_bundle = tmp_path / "artifacts" / "work" / "wrong-path.json"
        wrong_bundle.parent.mkdir(parents=True, exist_ok=True)
        wrong_bundle.write_text(
            json.dumps(
                {
                    "variant": "COMPLETED",
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        evidence_root = (
            tmp_path
            / ".orchestrate"
            / "runs"
            / "typed-prompt-input-authority"
            / "workflow_lisp"
            / "typed_prompt_inputs"
        )
        evidence_root.mkdir(parents=True, exist_ok=True)
        (evidence_root / "attempt.json").write_text(
            json.dumps({"schema_version": "workflow_lisp_typed_prompt_input_evidence.v1"}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = executor.execute(on_error="stop")

    provider_step = _provider_step(bundle)
    assert getattr(provider_step, "typed_prompt_inputs")
    assert state["steps"][provider_step.name]["status"] == "failed"
    assert "evidence" not in json.dumps(state["steps"][provider_step.name])
