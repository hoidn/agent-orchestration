from __future__ import annotations

import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow.typed_prompt_inputs import render_typed_prompt_inputs


REPO_ROOT = Path(__file__).resolve().parent.parent
VALID_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid"
TYPED_PROMPT_INPUT_FIXTURE = VALID_FIXTURES / "typed_prompt_input_phase.orc"
GENERIC_FAMILY_PROFILE_FIXTURE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "family_profiles"
    / "generic_phase_family_profile.json"
)


def _typed_prompt_inputs_module():
    return importlib.import_module("orchestrator.workflow_lisp.typed_prompt_inputs")


def _family_profiles_module():
    return importlib.import_module("orchestrator.workflow_lisp.family_profiles")


def _generic_family_profile_catalog():
    return _family_profiles_module().load_workflow_family_profile_catalog(
        (GENERIC_FAMILY_PROFILE_FIXTURE,)
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


def test_prompt_fragment_renderer_selection_recurses_only_through_admitted_lists() -> None:
    from orchestrator.workflow_lisp.definitions import PathDef, UnionDef
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.type_env import (
        ListTypeRef,
        MapTypeRef,
        OptionalTypeRef,
        PathTypeRef,
        PrimitiveTypeRef,
        UnionTypeRef,
    )

    module = _typed_prompt_inputs_module()
    span = read_sexpr_text(
        '"x"',
        source_path="typed_prompt_fragment_renderer.orc",
    ).span
    design_doc = PathTypeRef(
        name="DesignDocPath",
        definition=PathDef(
            name="DesignDocPath",
            kind="relpath",
            under="docs/design",
            must_exist=True,
            span=span,
        ),
    )
    nested = ListTypeRef(
        name="List[List[DesignDocPath]]",
        item_type_ref=ListTypeRef(
            name="List[DesignDocPath]",
            item_type_ref=design_doc,
        ),
    )
    assert module.select_prompt_fragment_renderer(
        nested,
        kind="value",
    ) == "canonical-json"
    assert module.select_prompt_fragment_renderer(
        design_doc,
        kind="path",
    ) == "posix-path-line"

    unsupported = (
        OptionalTypeRef(
            name="Optional[String]",
            item_type_ref=PrimitiveTypeRef(name="String"),
        ),
        MapTypeRef(
            name="Map[String, String]",
            key_type_ref=PrimitiveTypeRef(name="String"),
            value_type_ref=PrimitiveTypeRef(name="String"),
        ),
    )
    assert all(
        module.select_prompt_fragment_renderer(
            type_ref,
            kind="value",
        )
        is None
        for type_ref in unsupported
    )


@pytest.mark.parametrize("input_surface", ("ordinary_inputs", "prompt_value_fill"))
@pytest.mark.parametrize(
    "value",
    (
        {"variant": "PAYLOAD", "payload": {"ref": "literal-payload-key"}},
        {"variant": "EMPTY"},
    ),
)
def test_union_prompt_inputs_preserve_active_payload(
    input_surface: str,
    value: dict[str, object],
) -> None:
    """Target 2.28 renders one whole tagged value; payload `ref` stays data."""

    from orchestrator.workflow_lisp.definitions import UnionDef
    from orchestrator.workflow_lisp.reader import read_sexpr_text
    from orchestrator.workflow_lisp.type_env import (
        ListTypeRef,
        PrimitiveTypeRef,
        UnionTypeRef,
    )

    module = _typed_prompt_inputs_module()
    span = read_sexpr_text('"x"', source_path="union_prompt_input.orc").span
    outcome = UnionTypeRef(
        name="Outcome",
        definition=UnionDef(name="Outcome", variants=(), span=span),
        variant_field_types={
            "PAYLOAD": {"payload": PrimitiveTypeRef(name="Json")},
            "EMPTY": {},
        },
    )
    value_type = ListTypeRef(name="List[Outcome]", item_type_ref=outcome)

    assert module.select_prompt_fragment_renderer(
        value_type,
        kind="value",

    ) == "canonical-json"


    prompt_block, evidence = render_typed_prompt_inputs(
        [
            {
                "schema_version": "workflow_lisp_typed_prompt_input.v1",
                "binding_name": input_surface,
                "renderer": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "accepted_shape": "any_pure_value",
                },
                "value_source": {
                    "kind": "typed_binding_ref",
                    "ref": "root.steps.producer.artifacts.return",
                },
                "value_type_name": "List[Outcome]",
                "source_map_origin_key": "union-input::consumer",
                "injection_order": 0,
            }
        ],
        resolved_typed_values={input_surface: [value]},
        workflow_name="union-input::consumer",
        step_id="root.consumer",
    )

    assert json.loads(prompt_block.split("\n", 2)[1]) == [value]
    assert len(evidence) == 1


def test_known_literal_union_and_metadata_skip_preserve_authored_fields() -> None:
    from orchestrator.workflow.prompt_fragment_contract import (
        validate_typed_prompt_value_source,
    )
    from orchestrator.workflow_lisp.procedure_specialization import (_flatten_inline_output_refs)

    assert _flatten_inline_output_refs(
        {"__authored": "root.steps.source.artifacts.authored"}
    ) == {"return____authored": "root.steps.source.artifacts.authored"}

    validate_typed_prompt_value_source(
        {
            "kind": "typed_union_projection",
            "descriptor": {
                "kind": "union",
                "name": "Outcome",
                "variants": [
                    {"name": "YES", "fields": []},
                    {"name": "NO", "fields": []},
                ],
            },
            "source": {
                "kind": "union",
                "discriminant": {"kind": "literal", "value": "YES"},
                "variants": {"YES": {}},
            },
        }
    )


def test_normalize_typed_prompt_input_entry_canonicalizes_metadata() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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


def test_normalize_typed_prompt_input_entry_allows_generic_source_map_without_profile_rows() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")

    normalized = module.normalize_typed_prompt_input_entry(
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "allowed_value",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "root.steps.phase-one.artifacts.allowed_value",
            },
            "value_type_name": "String",
            "source_map_origin_key": "typed_carriage::run",
            "injection_order": 0,
        }
    )

    assert normalized["binding_name"] == "allowed_value"
    assert "u0_row_id" not in normalized
    assert "c0_row_id" not in normalized


def test_normalize_typed_prompt_input_entry_rejects_partial_profile_lineage() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")

    with pytest.raises(ValueError, match="u0_row_id.*c0_row_id|c0_row_id.*u0_row_id"):
        module.normalize_typed_prompt_input_entry(
            {
                "schema_version": "workflow_lisp_typed_prompt_input.v1",
                "binding_name": "allowed_value",
                "renderer": {
                    "renderer_id": "canonical-json",
                    "renderer_version": 1,
                    "accepted_shape": "any_pure_value",
                },
                "value_source": {
                    "kind": "typed_binding_ref",
                    "ref": "root.steps.phase-one.artifacts.allowed_value",
                },
                "value_type_name": "String",
                "source_map_origin_key": "typed_carriage::run",
                "u0_row_id": "u0.partial",
                "injection_order": 0,
            }
        )


def test_normalize_typed_prompt_input_entry_preserves_request_field_authority() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
    normalized = module.normalize_typed_prompt_input_entry(
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
                        "progress_ledger": {
                            "ref": "inputs.ctx__progress_ledger_path"
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
                    "subject.progress_ledger": {
                        "authority_class": "compatibility_bridge",
                        "source_binding": "ctx.progress_ledger_path",
                        "bridge_field_name": "progress_ledger_path",
                    }
                },
            },
        }
    )

    assert normalized["request_fields"]["field_authority"]["subject.progress_ledger"] == {
        "authority_class": "compatibility_bridge",
        "source_binding": "ctx.progress_ledger_path",
        "bridge_field_name": "progress_ledger_path",
    }


def test_render_typed_prompt_inputs_serializes_runtime_evidence() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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


def test_target_2_22_fragment_trace_reuse_preserves_typed_evidence_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import typed_prompt_inputs
    from tests.test_workflow_lisp_prompt_identity_render_trace import (
        _plan,
        _render_target_2_22,
        _resolved_values,
        _typed_entries,
    )

    result = _render_target_2_22()
    monkeypatch.setattr(
        typed_prompt_inputs,
        "render_view",
        lambda *_args: pytest.fail(
            "trace-owned evidence must not call the typed renderer"
        ),
    )
    _block, evidence = typed_prompt_inputs.render_typed_prompt_inputs(
        _typed_entries(),
        resolved_typed_values={
            "payload": _resolved_values()["payload"],
            "report_path": _resolved_values()["report_path"],
        },
        workflow_name="render-trace::run",
        step_id="root.render-trace",
        fragment_render_result=result,
        compiler_prompt_attempt_binding_plan=_plan(),
    )

    assert [set(row) for row in evidence] == [
        {
            "schema_version",
            "workflow_name",
            "step_id",
            "binding_name",
            "renderer",
            "value_type_name",
            "value_digest",
            "rendered_bytes_digest",
            "evidence_key",
            "source_map_origin_key",
            "injection_order",
            "request_field_evidence",
        },
        {
            "schema_version",
            "workflow_name",
            "step_id",
            "binding_name",
            "renderer",
            "value_type_name",
            "value_digest",
            "rendered_bytes_digest",
            "evidence_key",
            "source_map_origin_key",
            "injection_order",
            "request_field_evidence",
        },
    ]
    assert all(
        row["schema_version"]
        == "workflow_lisp_typed_prompt_input_evidence.v1"
        for row in evidence
    )


def test_render_typed_prompt_inputs_requires_exact_binding_and_evidence_sets() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
    entries = [
        {
            "schema_version": "workflow_lisp_typed_prompt_input.v1",
            "binding_name": "allowed_value",
            "renderer": {
                "renderer_id": "canonical-json",
                "renderer_version": 1,
                "accepted_shape": "any_pure_value",
            },
            "value_source": {
                "kind": "typed_binding_ref",
                "ref": "root.steps.phase-one.artifacts.allowed_value",
            },
            "value_type_name": "String",
            "source_map_origin_key": "typed_carriage::run",
            "injection_order": 0,
        }
    ]

    with pytest.raises(ValueError, match="typed_prompt_input_binding_set_mismatch"):
        module.render_typed_prompt_inputs(
            entries,
            resolved_typed_values={
                "allowed_value": "typed-prior-value",
                "unexpected": "must-not-be-silently-ignored",
            },
            workflow_name="typed_carriage::run",
            step_id="root.phase-two",
        )

    _block, evidence = module.render_typed_prompt_inputs(
        entries,
        resolved_typed_values={"allowed_value": "typed-prior-value"},
        workflow_name="typed_carriage::run",
        step_id="root.phase-two",
    )
    with pytest.raises(ValueError, match="typed_prompt_input_evidence_set_mismatch"):
        module.validate_typed_prompt_input_composition(
            entries,
            resolved_typed_values={"allowed_value": "typed-prior-value"},
            evidence=[],
            workflow_name="typed_carriage::run",
            step_id="root.phase-two",
        )
    assert module.validate_typed_prompt_input_composition(
        entries,
        resolved_typed_values={"allowed_value": "typed-prior-value"},
        evidence=evidence,
        workflow_name="typed_carriage::run",
        step_id="root.phase-two",
    ) == evidence
    evidence_with_extra_field = [dict(evidence[0], raw_value="must-not-cross")]
    with pytest.raises(ValueError, match="typed_prompt_input_evidence_set_mismatch"):
        module.validate_typed_prompt_input_composition(
            entries,
            resolved_typed_values={"allowed_value": "typed-prior-value"},
            evidence=evidence_with_extra_field,
            workflow_name="typed_carriage::run",
            step_id="root.phase-two",
        )


def test_render_typed_prompt_inputs_rejects_duplicate_binding_or_injection_order() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
    entry = {
        "schema_version": "workflow_lisp_typed_prompt_input.v1",
        "binding_name": "allowed_value",
        "renderer": {
            "renderer_id": "canonical-json",
            "renderer_version": 1,
            "accepted_shape": "any_pure_value",
        },
        "value_source": {
            "kind": "typed_binding_ref",
            "ref": "root.steps.phase-one.artifacts.allowed_value",
        },
        "value_type_name": "String",
        "source_map_origin_key": "typed_carriage::run",
        "injection_order": 0,
    }

    with pytest.raises(ValueError, match="typed_prompt_input_binding_set_mismatch"):
        module.render_typed_prompt_inputs(
            [entry, dict(entry)],
            resolved_typed_values={"allowed_value": "typed-prior-value"},
            workflow_name="typed_carriage::run",
            step_id="root.phase-two",
        )

    second = dict(entry)
    second["binding_name"] = "allowed_path"
    second["value_source"] = {
        "kind": "typed_binding_ref",
        "ref": "root.steps.phase-one.artifacts.allowed_path",
    }
    with pytest.raises(ValueError, match="typed_prompt_input_injection_order_invalid"):
        module.render_typed_prompt_inputs(
            [entry, second],
            resolved_typed_values={
                "allowed_value": "typed-prior-value",
                "allowed_path": "task/task.md",
            },
            workflow_name="typed_carriage::run",
            step_id="root.phase-two",
        )


def test_render_typed_prompt_inputs_records_hidden_bridge_leaf_evidence() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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
                            "subject": {
                                "progress_ledger": {
                                    "ref": "inputs.ctx__progress_ledger_path"
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
                            "subject.progress_ledger": {
                                "authority_class": "compatibility_bridge",
                                "source_binding": "ctx.progress_ledger_path",
                                "bridge_field_name": "progress_ledger_path",
                            }
                        },
                    },
                }
            )
        ],
        resolved_typed_values={
            "request": {"subject": {"progress_ledger": "state/progress_ledger.json"}}
        },
        workflow_name="lisp_frontend_design_delta/selector::select-next-work",
        step_id="root.select-next-work__decision",
    )

    assert '"progress_ledger":"state/progress_ledger.json"' in prompt_block
    assert evidence[0]["request_field_evidence"] == [
        {
            "field_path": "subject.progress_ledger",
            "authority_class": "compatibility_bridge",
            "source_binding": "ctx.progress_ledger_path",
            "bridge_field_name": "progress_ledger_path",
            "rendered_leaf_shape": "scalar_path",
            "rendered_leaf_digest": module.typed_prompt_input_value_digest(
                "state/progress_ledger.json"
            ),
        }
    ]


def test_normalize_typed_prompt_input_entry_rejects_missing_lineage() -> None:
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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
    module = importlib.import_module("orchestrator.workflow.typed_prompt_inputs")
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
                                        "progress_ledger": {
                                            "ref": "inputs.ctx__progress_ledger_path"
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
                                    "subject.progress_ledger": {
                                        "authority_class": "compatibility_bridge",
                                        "source_binding": "ctx.progress_ledger_path",
                                        "bridge_field_name": "progress_ledger_path",
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
                            "field_path": "subject.progress_ledger",
                            "authority_class": "compatibility_bridge",
                            "source_binding": "ctx.progress_ledger_path",
                            "bridge_field_name": "progress_ledger_path",
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
    assert selector_row["request_fields"]["field_authority"]["subject.progress_ledger"] == {
        "authority_class": "compatibility_bridge",
        "source_binding": "ctx.progress_ledger_path",
        "bridge_field_name": "progress_ledger_path",
    }


@pytest.mark.parametrize(
    ("field_authority", "expected_code"),
    [
        (
            {
                "subject.progress_ledger": {
                    "authority_class": "compatibility_bridge",
                    "bridge_field_name": "progress_ledger_path",
                }
            },
            "typed_prompt_input_hidden_bridge_source_unmapped",
        ),
        (
            {
                "subject.progress_ledger": {
                    "authority_class": "runtime_derived",
                    "source_binding": "ctx.progress_ledger_path",
                    "bridge_field_name": "progress_ledger_path",
                }
            },
            "typed_prompt_input_hidden_bridge_authority_mismatch",
        ),
        (
            {
                "subject.progress_ledger": {
                    "authority_class": "compatibility_bridge",
                    "source_binding": "ctx.progress_ledger_path",
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
                                        "progress_ledger": {
                                            "ref": "inputs.ctx__progress_ledger_path"
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
                            "field_path": "subject.progress_ledger",
                            "authority_class": "compatibility_bridge",
                            "source_binding": "ctx.progress_ledger_path",
                            "bridge_field_name": "progress_ledger_path",
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


def test_runtime_rejects_missing_composer_evidence_before_provider_preparation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _initialize_typed_prompt_input_workspace(tmp_path)
    state_manager = StateManager(
        workspace=tmp_path,
        run_id="typed-prompt-input-missing-composer-evidence",
    )
    calls = {"preparations": 0, "executions": 0}


    def _prepare(*_args, **_kwargs):
        calls["preparations"] += 1
        return pytest.fail("provider preparation must not be reached")

    def _execute(*_args, **_kwargs):
        calls["executions"] += 1
        return pytest.fail("provider execution must not be reached")


    assert calls == {"preparations": 0, "executions": 0}


def test_typed_prompt_input_fixture_rows_resolve_via_family_profile_catalog() -> None:
    catalog = _generic_family_profile_catalog()

    prompt_context_row = catalog.typed_prompt_input_row(
        "typed_prompt_input_phase::run-typed-prompt-phase-demo",
        "providers.execute",
    )
    assert prompt_context_row["c0_row_id"] == "c0.fixture.prompt_context"
    assert prompt_context_row["u0_row_id"] == "u0.fixture.prompt_context"

    request_row = catalog.typed_prompt_input_row(
        "typed_prompt_input_local_request_record::run-local-request-record-demo",
        "providers.execute",
    )
    assert request_row["preserve_request_record"] is True
    assert request_row["request_fields"]["field_names"] == ["subject", "targets"]
