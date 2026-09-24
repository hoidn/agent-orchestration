from __future__ import annotations

from dataclasses import fields, is_dataclass
from types import SimpleNamespace

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
from orchestrator.workflow_lisp.wcc.defunctionalize import _frontend_expr_from_wcc_loop_binding_value
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
        target_dsl_version="2.31",
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
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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


@pytest.mark.parametrize("clause", (":context seed", ":capture-context :portable"))
def test_provider_context_clauses_reject_old_targets(clause: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                "(provider-result providers.execute :prompt prompts.execute :inputs () "
                f"{clause} :returns Int)"
            ),
            bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
            target_dsl_version="2.30",
        )

    assert excinfo.value.diagnostics[0].code == "provider_context_target_dsl_unsupported"


def test_capture_context_rejects_session_artifact_publication() -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        elaborate_expression(
            _expression_syntax(
                "(provider-result providers.execute :prompt prompts.execute :inputs () "
                ":capture-context :portable :session-artifact session :returns Int)"
            ),
            bound_names=frozenset({"providers.execute", "prompts.execute", "session"}),
            target_dsl_version="2.31",
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
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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


def test_lowering_provider_context_map_keeps_the_model_descriptor_unwrapped() -> None:
    from orchestrator.workflow_lisp.lowering.effects import (
        LowerableProviderResult,
        _lower_provider_context_config,
    )

    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context seed :capture-context :portable :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=expr.span,
        )
    )
    lowerable = LowerableProviderResult(
        provider_name="providers.execute",
        prompt_name="prompts.execute",
        inputs=(),
        span=expr.span,
        form_path=expr.form_path,
        context_expr=expr.context_expr,
        capture_context=expr.capture_context,
        returns_type_name=expr.returns_type_name,
    )

    config = _lower_provider_context_config(
        lowerable,
        result_type=type_env.resolve_type("Contextual[Int]", span=expr.span, form_path=expr.form_path),
        context=SimpleNamespace(type_env=type_env, source_read_trace=None),
        local_values={"seed": "inputs.seed"},
    )

    assert config["input"] == {"ref": "inputs.seed"}
    assert config["capture"] == "portable"
    assert config["result_descriptor"] == {
        "kind": "primitive",
        "name": "Int",
    }


def test_captured_context_uses_its_two_runtime_artifacts_as_whole_output_refs() -> None:
    from orchestrator.workflow_lisp.lowering.effects import (
        _provider_context_capture_output_refs,
    )

    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=_expression_syntax("seed").span,
        )
    )

    assert _provider_context_capture_output_refs(
        "example__result",
        type_env.resolve_type("Contextual[Int]", span=_expression_syntax("seed").span, form_path=("test",)),
        capture_context=True,
    ) == {
        "return__result": "root.steps.example__result.artifacts.result",
        "return__context": "root.steps.example__result.artifacts.context",
    }


def test_capture_contract_keeps_a_structured_model_value_at_the_root() -> None:
    from orchestrator.workflow_lisp.contracts import (
        derive_prompt_guided_structured_result_contract,
    )

    span = _expression_syntax("seed").span
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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
            target_dsl_version="2.31",
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


def test_capture_source_schema_validates_nested_field_guidance_at_231(
    tmp_path: Path,
) -> None:
    source = tmp_path / "guided_capture.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule guided_capture)
  (export capture)
  (defunion Decision
    (APPROVE (confidence Float :description \"Confidence in approval.\"))
    (REVISE (reason String :format-hint \"Short explanation.\")))
  (defrecord Answer
    (decision Decision :description \"Final decision.\"))
  (defworkflow capture () -> Contextual[Answer]
    (provider-result providers.capture :prompt prompts.capture :inputs ()
      :capture-context :portable :returns Answer)))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.capture": "capture-provider"},
        prompt_externs={"prompts.capture": "prompts/capture.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    decision = workflow.authored_mapping["steps"][0]["output_bundle"]["fields"][0]["fields"][0]
    assert decision["description"] == "Final decision."
    assert decision["variants"]["APPROVE"]["fields"][0]["description"] == (
        "Confidence in approval."
    )


def test_capture_context_compiles_to_raw_ref_and_binds_through_the_surface(
    tmp_path: Path,
) -> None:
    source = tmp_path / "capture_context.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule capture_context)
  (export capture)
  (defworkflow capture () -> Contextual[Int]
    (provider-result providers.execute :prompt prompts.execute :inputs ()
      :capture-context :portable :returns Int)))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    step = workflow.authored_mapping["steps"][0]
    assert step["provider_context"]["capture"] == "portable"
    assert step["output_bundle"]["fields"] == [
        {
            "name": "__result__",
            "json_pointer": "",
            "type": "integer",
            "source_map_subject": step["output_bundle"]["fields"][0]["source_map_subject"],
        }
    ]
    terminal = workflow.authored_mapping["steps"][1]
    assert terminal["pure_projection"]["binding_refs"] == {
        f"root.steps.{step['name']}.artifacts.result": {
            "ref": f"root.steps.{step['name']}.artifacts.result"
        },
        f"root.steps.{step['name']}.artifacts.context": {
            "ref": f"root.steps.{step['name']}.artifacts.context"
        },
    }
    assert all(
        ".artifacts.context__" not in value["from"]["ref"]
        for value in workflow.authored_mapping["outputs"].values()
    )


@pytest.mark.parametrize("capture", (False, True))
def test_imported_prompt_keeps_its_defining_module_result_type(
    tmp_path: Path,
    capture: bool,
) -> None:
    (tmp_path / "review_prompt.orc").write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.31")
  (defmodule review_prompt)
  (export review)
  (defrecord Decision (approved Bool))
  (defprompt review (:fills (subject :text)) -> Decision "Review {subject}."))
''',
        encoding="utf-8",
    )
    source = tmp_path / "consumer.orc"
    source.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.31")
  (defmodule consumer)
  (import review_prompt :only (review))
  (export run)
  (defworkflow run () -> Bool
    (let* ((decision (provider-result providers.review
                      :prompt (review :subject "design")
                      {":capture-context :portable" if capture else ""})))
      decision.{"result." if capture else ""}approved)))
''',
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.review": "review-provider"},
        prompt_externs={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    (workflow,) = result.entry_result.lowered_workflows
    step = next(row for row in workflow.authored_mapping["steps"] if "provider" in row)
    if capture:
        assert step["provider_context"]["result_descriptor"]["name"] == "Decision"
        assert step["output_bundle"]["fields"][0]["json_pointer"] == ""
    else:
        assert "provider_context" not in step
        assert step["output_bundle"]["fields"][0]["name"] == "approved"


def test_captured_context_field_binds_the_next_provider_call(
    tmp_path: Path,
) -> None:
    source = tmp_path / "capture_then_bind.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule capture_then_bind)
  (export chain)
  (defworkflow chain () -> Int
    (let* ((first (provider-result providers.first :prompt prompts.first :inputs ()
                    :capture-context :portable :returns Int))
           (second (provider-result providers.second :prompt prompts.second :inputs ()
                     :context first.context :returns Int)))
      second)))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={
            "providers.first": "first-provider",
            "providers.second": "second-provider",
        },
        prompt_externs={
            "prompts.first": "prompts/first.md",
            "prompts.second": "prompts/second.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    first, second = workflow.authored_mapping["steps"][:2]
    assert second["provider_context"] == {
        "input": {"ref": f"root.steps.{first['name']}.artifacts.context"}
    }


def test_uncaptured_contextual_result_consumes_its_flattened_context_projection(
    tmp_path: Path,
) -> None:
    source = tmp_path / "uncaptured_contextual.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule uncaptured_contextual)
  (export chain)
  (defworkflow chain () -> Int
    (let* ((first (provider-result providers.first :prompt prompts.first :inputs ()
                    :returns Contextual[Int]))
           (second (provider-result providers.second :prompt prompts.second :inputs ()
                     :context first.context :returns Int)))
      second)))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={
            "providers.first": "first-provider",
            "providers.second": "second-provider",
        },
        prompt_externs={
            "prompts.first": "prompts/first.md",
            "prompts.second": "prompts/second.md",
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    first, projection, second = workflow.authored_mapping["steps"]
    assert first["output_bundle"]["fields"] != [
        {"name": "__result__", "json_pointer": ""}
    ]
    assert projection["pure_projection"]
    assert second["provider_context"]["input"]["ref"] != (
        f"root.steps.{first['name']}.artifacts.context"
    )


def test_context_parameter_is_materialized_from_flattened_boundary_fields(
    tmp_path: Path,
) -> None:
    source = tmp_path / "context_parameter.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule context_parameter)
  (export ask)
  (defworkflow ask ((seed Context)) -> Int
    (provider-result providers.ask :prompt prompts.ask :inputs ()
      :context seed :returns Int)))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.ask": "ask-provider"},
        prompt_externs={"prompts.ask": "prompts/ask.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    projection, provider = workflow.authored_mapping["steps"][:2]
    assert projection["output_bundle"]["fields"][0]["name"] == "__result__"
    assert projection["pure_projection"]["binding_refs"] == {
        "inputs.seed__schema": {"ref": "inputs.seed__schema"},
        "inputs.seed__events": {"ref": "inputs.seed__events"},
        "inputs.seed__coverage": {"ref": "inputs.seed__coverage"},
        "inputs.seed__lineage": {"ref": "inputs.seed__lineage"},
    }
    assert provider["provider_context"] == {
        "input": {"ref": f"root.steps.{projection['name']}.artifacts.__result__"}
    }


def test_pre_231_keeps_nested_transportable_workflow_inputs_refused(
    tmp_path: Path,
) -> None:
    source = tmp_path / "old_nested_input.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.30\")
  (defmodule old_nested_input)
  (defunion Choice
    (ONE (value Int))
    (TWO (label String)))
  (defrecord Packet (choices List[Choice]))
  (defworkflow unchanged ((packet Packet)) -> Int 1))
""",
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            source,
            source_roots=(tmp_path,),
            validate_shared=False,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "workflow_boundary_type_invalid"
    assert "packet.choices.item" in excinfo.value.diagnostics[0].message


def test_computed_context_is_materialized_before_the_provider_boundary(
    tmp_path: Path,
) -> None:
    source = tmp_path / "computed_context.orc"
    source.write_text(
        """(workflow-lisp
  (:language \"0.1\")
  (:target-dsl \"2.31\")
  (defmodule computed_context)
  (export ask)
  (defworkflow ask () -> Int
    (let* ((first (provider-result providers.seed :prompt prompts.seed :inputs ()
                    :capture-context :portable :returns Int)))
      (provider-result providers.ask :prompt prompts.ask :inputs ()
        :context (record-update first.context :schema \"revised\")
        :returns Int))))
""",
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        source,
        source_roots=(tmp_path,),
        provider_externs={"providers.seed": "seed-provider", "providers.ask": "ask-provider"},
        prompt_externs={"prompts.seed": "prompts/seed.md", "prompts.ask": "prompts/ask.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    (workflow,) = result.entry_result.lowered_workflows
    _first, projection, provider = workflow.authored_mapping["steps"][:3]
    assert "pure_projection" in projection
    assert projection["output_bundle"]["fields"][0]["name"] == "__result__"
    assert projection["output_bundle"]["fields"][0]["json_pointer"] == ""
    assert provider["provider_context"] == {
        "input": {"ref": f"root.steps.{projection['name']}.artifacts.__result__"}
    }


def test_wcc_provider_payload_reconstructs_context_selection_and_operand() -> None:
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
            module_name=None,
            imports=(),
            exports=(),
            definitions=(),
            span=_expression_syntax("seed").span,
        )
    )
    span = _expression_syntax("seed").span
    metadata = WccIdentityFactory(
        owner_name="test",
        lexical_owner_chain=("workflow",),
    ).value_metadata(
        role="perform",
        type_ref=type_env.resolve_type("Contextual[Int]", span=span, form_path=("test",)),
        source_span=span,
        form_path=("test",),
    )
    perform = WccPerform(
        metadata=metadata,
        perform_kind="provider_result",
        target_name="providers.execute",
        prompt_name="prompts.execute",
        positional_args=(),
        keyword_args=(),
        returns_type_name="Int",
        operation_payload={
            "context_expr": WccNameAtom(
                metadata=metadata,
                name="seed",
            ),
            "capture_context": "portable",
        },
    )

    reconstructed = _frontend_expr_from_wcc_loop_binding_value(perform)

    assert reconstructed.capture_context == "portable"
    assert isinstance(reconstructed.context_expr, NameExpr)
    assert reconstructed.context_expr.name == "seed"


def test_wcc_payload_keeps_a_prebound_computed_context_and_capture_selection() -> None:
    expr = elaborate_expression(
        _expression_syntax(
            "(provider-result providers.execute :prompt prompts.execute :inputs () "
            ":context (let* ((chosen seed)) chosen) :capture-context :portable :returns Int)"
        ),
        bound_names=frozenset({"providers.execute", "prompts.execute", "seed"}),
        target_dsl_version="2.31",
    )
    type_env = FrontendTypeEnvironment.from_module(
        WorkflowLispModule(
            language_version="0.1",
            target_dsl_version="2.31",
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
