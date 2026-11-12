from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("input_surface", ("ordinary_inputs",))
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
