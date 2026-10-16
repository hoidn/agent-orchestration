from __future__ import annotations

from dataclasses import fields, is_dataclass

import pytest
from pathlib import Path

from orchestrator.workflow_lisp.expression_traversal import iter_child_exprs
from orchestrator.workflow_lisp.expressions import NameExpr, ProviderResultExpr, elaborate_expression
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.syntax import SyntaxNode
from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
from orchestrator.workflow_lisp.typecheck import typecheck_expression
from orchestrator.workflow_lisp.workflows import build_extern_environment
from orchestrator.workflow_lisp.definitions import (
    RecordDef,
    RecordField,
    UnionDef,
    UnionVariant,
    WorkflowLispModule,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.result_guidance import ResultGuidance
from orchestrator.workflow_lisp.wcc.elaborate import (
    _prebind_effect_argument_matches,
    elaborate_typed_workflow_body,
)
from orchestrator.workflow_lisp.wcc.model import WccIdentityFactory, WccNameAtom, WccPerform
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint


def _expression_syntax(source: str) -> SyntaxNode:
    module = read_sexpr_text(source, source_path="provider_context_values_test.orc")
    assert len(module.items) == 1
    datum = module.items[0]
    return SyntaxNode(
        datum=datum,
        span=datum.span,
        module_path="provider_context_values_test.orc",
        form_path=("workflow-lisp", "provider-context-values-test"),
    )


def test_provider_result_elaborates_portable_context_operand_and_capture() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context seed :capture-context :portable :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.35",
    )

    assert isinstance(expr, ProviderResultExpr)
    assert expr.capture_context == "portable"
    assert expr.context_expr == NameExpr(
        name="seed",
        span=expr.context_expr.span,
        form_path=expr.context_expr.form_path,
        expansion_stack=expr.context_expr.expansion_stack,
    )
    assert expr.context_expr in iter_child_exprs(expr)


def test_capture_context_wraps_the_expression_result_but_not_the_model_return() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context seed :capture-context :portable :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.35",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "seed": type_env.resolve_type(
                "Context", span=expr.span, form_path=expr.form_path
            )
        },
        extern_environment=build_extern_environment(
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.execute": "tests/prompt.md"},
        ),
    )

    assert typed.type_ref.name == "Contextual[Int]"
    assert typed.expr.returns_type_name == "Int"


def test_context_input_without_capture_keeps_the_model_result_type() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context seed :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.35",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )

    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={
            "seed": type_env.resolve_type(
                "Context", span=expr.span, form_path=expr.form_path
            )
        },
        extern_environment=build_extern_environment(
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.execute": "tests/prompt.md"},
        ),
    )

    assert typed.type_ref.name == "Int"




def test_capture_context_rejects_session_artifact_publication() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                "(provider-result providers.execute :prompt prompts.execute :inputs () "
                ":capture-context :portable :session-artifact session :returns Int)"
            ),
            bound_names=frozenset({"providers.execute", "prompts.execute", "session"}),
            target_dsl_version="2.35",
        )

    assert excinfo.value.diagnostics[0].code == "provider_context_session_artifact_invalid"


def test_capture_context_rejects_provider_peer_groups() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(with-live-provider-peers "
            "((left (provider-result providers.execute :prompt prompts.execute :inputs () "
            ":capture-context :portable :returns Int)) "
            "(right (provider-result providers.execute :prompt prompts.execute :inputs () :returns Int))) "
            "left)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute"}),
        target_dsl_version="2.35",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typecheck_expression(
            expr,
            type_env=type_env,
            value_env={},
            extern_environment=build_extern_environment(
                provider_externs={"providers.execute": "test-provider"},
                prompt_externs={"prompts.execute": "tests/prompt.md"},
            ),
        )

    assert excinfo.value.diagnostics[0].code == "provider_context_peer_group_invalid"


def test_wcc_prebinds_a_computed_provider_context_operand() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context (let* ((chosen seed)) chosen) :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.35",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )
    context_type = type_env.resolve_type("Context", span=expr.span, form_path=expr.form_path)

    rewritten, bindings = _prebind_effect_argument_matches(
        expr,
        scope=WccIdentityFactory(owner_name="test", lexical_owner_chain=("workflow",)),
        type_env=type_env,
        value_env={"seed": context_type},
        workflow_return_types={},
        procedure_return_types={},
    )

    assert isinstance(rewritten.context_expr, NameExpr)
    assert len(bindings) == 1
    assert bindings[0][2] == expr.context_expr






def test_capture_contract_keeps_a_structured_model_value_at_the_root() -> None:
    from orchestrator.workflow_lisp.contracts import (
        derive_prompt_guided_structured_result_contract,
    )

    span = _expression_syntax("seed").span
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(
                RecordDef(
                    name="Answer",
                    fields=(RecordField(name="data", type_name="String", span=span),),
                    span=span,
                ),
            ),
            span=span,
        )
    )

    contract = derive_prompt_guided_structured_result_contract(
        type_env.resolve_type("Answer", span=span, form_path=("test",)),
        workflow_name="capture",
        step_id="capture__result",
        type_env=type_env,
        span=span,
        whole_value=True,
    )

    assert contract.contract_kind == "output_bundle"
    field = contract.payload["fields"][0]
    assert {key: value for key, value in field.items() if key != "source_map_subject"} == {
        "name": "__result__",
        "json_pointer": "",
        "type": "record",
        "record_name": "Answer",
        "fields": [{"name": "data", "type": "string"}],
    }
    assert field["source_map_subject"] == {
        "subject_kind": "output_bundle_field",
        "subject_name": "capture__result::root-result::__result__",
        "workflow_name": "capture",
    }
    assert len(contract.field_origins) == 1
    assert contract.field_origins[0].subject_ref.subject_name == (
        "capture__result::root-result::__result__"
    )
    assert contract.field_origins[0].span == span


def test_capture_root_schema_keeps_nested_record_and_variant_field_guidance() -> None:
    from orchestrator.workflow_lisp.contracts import (
        derive_prompt_guided_structured_result_contract,
    )

    span = _expression_syntax("seed").span
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(
                UnionDef(
                    name="Decision",
                    variants=(
                        UnionVariant(
                            name="APPROVE",
                            fields=(
                                RecordField(
                                    name="confidence",
                                    type_name="Float",
                                    span=span,
                                    guidance=ResultGuidance(
                                        description="Confidence in approval."
                                    ),
                                ),
                            ),
                            span=span,
                        ),
                        UnionVariant(
                            name="REVISE",
                            fields=(
                                RecordField(
                                    name="reason",
                                    type_name="String",
                                    span=span,
                                    guidance=ResultGuidance(
                                        format_hint="Short explanation."
                                    ),
                                ),
                            ),
                            span=span,
                        ),
                    ),
                    span=span,
                ),
                RecordDef(
                    name="Answer",
                    fields=(
                        RecordField(
                            name="decision",
                            type_name="Decision",
                            span=span,
                            guidance=ResultGuidance(description="Final decision."),
                        ),
                    ),
                    span=span,
                ),
            ),
            span=span,
        )
    )

    contract = derive_prompt_guided_structured_result_contract(
        type_env.resolve_type("Answer", span=span, form_path=("test",)),
        workflow_name="capture",
        step_id="capture__result",
        type_env=type_env,
        span=span,
        whole_value=True,
    )

    decision = contract.payload["fields"][0]["fields"][0]
    assert decision["description"] == "Final decision."
    assert decision["variants"]["APPROVE"]["fields"][0]["description"] == (
        "Confidence in approval."
    )
    assert decision["variants"]["REVISE"]["fields"][0]["format_hint"] == (
        "Short explanation."
    )




















def test_wcc_payload_keeps_a_prebound_computed_context_and_capture_selection() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context (let* ((chosen seed)) chosen) :capture-context :portable :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.35",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.35",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )
    context_type = type_env.resolve_type("Context", span=expr.span, form_path=expr.form_path)
    typed = typecheck_expression(
        expr,
        type_env=type_env,
        value_env={"seed": context_type},
        extern_environment=build_extern_environment(
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.execute": "tests/prompt.md"},
        ),
    )
    wcc = elaborate_typed_workflow_body(
        typed,
        owner_name="test",
        type_env=type_env,
        value_env={"seed": context_type},
    )

    def find_performs(value):
        if isinstance(value, WccPerform):
            return [value]
        if is_dataclass(value):
            return [perform for field in fields(value) for perform in find_performs(getattr(value, field.name))]
        if isinstance(value, tuple | list):
            return [perform for item in value for perform in find_performs(item)]
        if isinstance(value, dict):
            return [perform for item in value.values() for perform in find_performs(item)]
        return []

    (perform,) = find_performs(wcc)
    assert perform.metadata.type_ref.name == "Contextual[Int]"
    assert perform.returns_type_name == "Int"
    assert perform.operation_payload["capture_context"] == "portable"
    assert isinstance(perform.operation_payload["context_expr"], WccNameAtom)

def test_current_target_accepts_nested_transportable_workflow_inputs(
    tmp_path: Path,
) -> None:
    source = tmp_path / "current_nested_input.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.35\")
  (defmodule current_nested_input)
  (defunion Choice
    (ONE (value Int))
    (TWO (label String)))
  (defrecord Packet (choices List[Choice]))
  (defworkflow unchanged ((packet Packet)) -> Int 1))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        validate_shared=False,
        workspace_root=tmp_path,
    )
    [workflow] = result.entry_result.typed_workflows
    packet = dict(workflow.signature.params)["packet"]
    choice = packet.field_types["choices"].item_type_ref
    assert choice.name == "Choice"
    assert set(choice.variant_field_types) == {"ONE", "TWO"}
    assert workflow.typed_body.expr.value == 1
