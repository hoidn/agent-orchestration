"""Selected surface control is checked against independent pre-hoist fragments."""

from dataclasses import replace

import pytest

from orchestrator.workflow_lisp.expressions import FieldAccessExpr, NameExpr
from tests.test_workflow_lisp_command_templates import SPAN, _literal


def test_runtime_fact_is_exact_and_preserves_reference_materialization():
    from orchestrator.workflow_lisp.procedure_specialization import (RUNTIME_REFERENCE)
    from orchestrator.workflow_lisp.closed.command_templates import is_direct_reference, wcc_binding_materialization
    from orchestrator.workflow_lisp.procedure_specialization import (inline_expr_field_value)

    root = NameExpr(name="root", span=SPAN, form_path=())
    field = FieldAccessExpr(base=root, fields=("leaf",), span=SPAN, form_path=())
    locals_ = {"root": {"leaf": RUNTIME_REFERENCE}}
    assert inline_expr_field_value(
        field, field_path=(), local_values=locals_, bound_record_fields=True,
        phase_target_values=None,
    ) is RUNTIME_REFERENCE
    assert is_direct_reference(RUNTIME_REFERENCE)
    assert is_direct_reference("inputs.actual")
    assert not is_direct_reference(object())
    assert not is_direct_reference(_literal("inputs.literal"))
    assert wcc_binding_materialization(
        root, expansion_owned=True, existing_ref=RUNTIME_REFERENCE, resolved_binding=None,
        run_ref_demand=False, provider_context_demand=False, request_input_demand=False,
    ) == ("alias", RUNTIME_REFERENCE)
    assert wcc_binding_materialization(
        root, expansion_owned=False, existing_ref=None, resolved_binding=RUNTIME_REFERENCE,
        run_ref_demand=False, provider_context_demand=False, request_input_demand=True,
    ) == ("alias", RUNTIME_REFERENCE)


def test_suffix_binding_resolver_preserves_unavailable_alias_and_caller():
    from orchestrator.workflow_lisp.procedure_specialization import (_resolve_inline_let_bindings)
    from orchestrator.workflow_lisp.procedure_specialization import (RUNTIME_REFERENCE)

    caller = {"available": RUNTIME_REFERENCE}
    assert _resolve_inline_let_bindings(
        (("alias", NameExpr(name="available", span=SPAN, form_path=())),), local_values=caller,
    ) == {"available": RUNTIME_REFERENCE, "alias": RUNTIME_REFERENCE}
    assert _resolve_inline_let_bindings(
        (("alias", NameExpr(name="absent", span=SPAN, form_path=())),), local_values=caller,
    ) is None
    assert caller == {"available": RUNTIME_REFERENCE}


_CONTROL_PROC = '(defproc pick ((flag Bool) (left String) (right String)) -> Pair :effects ((uses-command echo)) :lowering MODE (if flag (command-result echo :argv ("python" "probe.py" left) :returns Pair) (command-result echo :argv ("python" "probe.py" right) :returns Pair)))'
_PURE_PROC = '(defproc pick ((flag Bool) (left String) (right String)) -> Pair :effects () :lowering inline (let* ((x (if flag left right))) (record Pair :left x :right right)))'






def test_unknown_operation_requires_an_explicit_summary_rule():
    from orchestrator.workflow_lisp.closed.command_templates import expression_control_summary

    with pytest.raises(ValueError, match="no selected surface-control rule"):
        expression_control_summary(object(), result_type=None, facts=None, local_values={})


def test_untyped_binding_keeps_existing_lexical_type_fact(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    from orchestrator.workflow_lisp.closed import command_templates as summary

    retained_type = object()
    facts = summary.ControlFacts(
        signature=None, type_env=None, local_type_bindings={"shadow": retained_type},
        typed_procedures={}, workflow_catalog=None, workflows_by_name={},
        procedure_type_envs={}, workflow_name="run",
    )
    body = NameExpr(name="shadow", span=SPAN, form_path=())
    expr = LetStarExpr(bindings=(("shadow", _literal("new")),), body=body, span=SPAN, form_path=())
    monkeypatch.setattr(summary, "_binding_control_fact", lambda *args, **kwargs: (False, None, None))
    monkeypatch.setattr(summary, "_direct_outputs_available", lambda *args, **kwargs: False)
    observed = []
    monkeypatch.setattr(summary, "_expression_control_fact", lambda *args, **kwargs: (observed.append(kwargs["facts"].local_type_bindings) or False, ()))
    assert not summary._let_control_fact(expr, result_type=None, facts=facts, local_values={})[0]
    assert observed == [{"shadow": retained_type}]






@pytest.mark.parametrize("expr", [_literal(True), NameExpr(name="pure", span=SPAN, form_path=())])
def test_typed_pure_values_have_an_explicit_noncontrol_rule(tmp_path, expr):
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.closed.command_templates import ControlFacts, expression_control_summary
    from tests.test_workflow_lisp_command_scopes import _compile

    _, inputs, facts = _compile(tmp_path, "(let* ((pure true)) pure)", returns="Bool")
    typed = ControlFacts(**facts, workflow_return_types=inputs["workflow_return_types"],
        procedure_return_types=inputs["procedure_return_types"])
    assert not expression_control_summary(expr, result_type=PrimitiveTypeRef(name="Bool"), facts=typed, local_values={})



@pytest.mark.parametrize("caller_value", ['"caller"', '42'])
def test_selected_inline_helper_uses_its_real_lexical_types(tmp_path, monkeypatch, caller_value):
    from tests.test_workflow_lisp_command_scopes import _compile
    from orchestrator.workflow_lisp.closed import command_templates as summary
    from orchestrator.workflow_lisp.expressions import LiteralExpr

    program, inputs, facts = _compile(tmp_path,
        f'(let* ((shadow {caller_value}) (hook (bind-proc (proc-ref helper) :fixed true))) (hook 1))',
        declarations='(defproc helper ((fixed Bool) (n Int)) -> Result :effects ((uses-command echo)) :lowering inline '
        '(let* ((shadow true) (r (command-result echo :argv ("python" "probe.py" fixed n) :returns Result))) r))')
    typed = summary.ControlFacts(**facts,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    observed = []
    original = summary._closed_binding_type

    def lookup(expr, **kwargs):
        result = original(expr, **kwargs)
        if isinstance(expr, LiteralExpr) and expr.value is True:
            observed.append((result, kwargs["facts"].local_type_bindings))
        return result


    monkeypatch.setattr(summary, "_closed_binding_type", lookup)
    assert not summary.expression_control_summary(program.entry.typed_body.expr,
        result_type=program.entry.typed_body.type_ref, facts=typed, local_values={})
    assert observed
    assert observed[-1][0].name == "Bool"
    assert "shadow" not in observed[-1][1]
    assert set(observed[-1][1]) == {"fixed", "n"}


def _compile_imported_helper_snapshot(tmp_path, reference, provider):
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program

    leaf_path = tmp_path / "leaf.orc"
    (tmp_path / "prompt.md").write_text("Return the requested Leaf record.")
    leaf_body = '(provider-result providers.execute :prompt prompts.execute :inputs () :returns Leaf)' if provider else '(record Leaf :n 7)'
    leaf_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule leaf) (export get) (defrecord Leaf (n Int)) '
        f'(defworkflow get () -> Leaf {leaf_body}))')
    leaf = compile_stage3_entrypoint(leaf_path, source_roots=(tmp_path,), workspace_root=tmp_path,
        provider_externs={"providers.execute": "selected-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
         validate_shared=True).entry_result.typed_program
    leaf = replace(leaf, entry=leaf.workflows["leaf::get"])
    owner_path = tmp_path / "owner.orc"
    owner_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule owner) (export get) (defrecord Leaf (n Int)) (defrecord Result (i Int) (s String)) '
        '(defproc helper () -> Result :effects ((calls-workflow dep)) :lowering inline '
        '(let* ((r (call dep)) (shadow true)) (record Result :i r.n :s "owner"))) '
        '(defworkflow get () -> Result (helper)))')
    if reference:
        owner_path.write_text(owner_path.read_text().replace("(let* ((r (call dep))", "(let* ((ref (workflow-ref dep)) (r (call dep))"))
        snapshot = compile_typed_program(owner_path, entry_workflow="get", source_roots=(tmp_path,),
            workspace_root=tmp_path, command_boundaries={}, imported_programs={"dep": leaf})
    else:
        owner = compile_stage3_entrypoint(owner_path, source_roots=(tmp_path,), workspace_root=tmp_path,
            imported_programs={"dep": leaf},  validate_shared=True)
        snapshot = owner.entry_result.typed_program
    assert snapshot.producer_lowering_schema == 2
    snapshot = replace(snapshot, entry=snapshot.workflows["owner::get"],
        producer_lowering_schema=2 if reference else 1)
    leaf_path.unlink()
    owner_path.unlink()
    return leaf, snapshot


def _compile_imported_snapshot_caller(tmp_path, snapshot):
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program

    caller_path = tmp_path / "caller.orc"
    caller_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule caller) (export run) (defrecord Result (i Int) (s String)) (defworkflow run ((shadow String)) -> String '
        '(let* ((r (call dep))) shadow)))')
    return compile_typed_program(caller_path, entry_workflow="run", workspace_root=tmp_path,
        source_roots=(tmp_path,), command_boundaries={}, imported_programs={"dep": snapshot})


def _imported_snapshot_control_facts(caller, builder, summary):
    from orchestrator.workflow_lisp.workflows import WorkflowCatalog
    from orchestrator.workflow_lisp.procedures import ProcedureCatalog

    entry = caller.entry
    facts = summary.ControlFacts(signature=entry.signature, type_env=caller.workflow_type_env(entry.definition.name),
        local_type_bindings=dict(entry.signature.params), typed_procedures=caller.procedures,
        workflow_catalog=WorkflowCatalog(signatures_by_name={**{name: item.signature for name, item in caller.workflows.items()},
                **caller.module_workflow_signatures[caller.entry_module]},
            definitions_by_name={name: item.definition for name, item in caller.workflows.items()}, imported_bundles_by_name={}),
        workflows_by_name=caller.workflows, procedure_type_envs=caller.procedure_type_envs,
        workflow_name=entry.definition.name,
        procedure_catalog=ProcedureCatalog(signatures_by_name={name: item.signature for name, item in caller.procedures.items()},
            definitions_by_name={name: item.definition for name, item in caller.procedures.items()}, call_graph={}),
        workflow_return_types=builder._workflow_return_types_for(caller, entry.definition.name),
        procedure_return_types=builder.procedure_return_types, procedure_owners=builder.procedure_owners,
        base_workflow_return_types=builder.workflow_return_types)
    return facts


def _assert_imported_snapshot_alias_facts(leaf, snapshot, facts, reference, provider, monkeypatch):
    from orchestrator.workflow_lisp.closed import command_templates as summary
    from orchestrator.workflow_lisp.expressions import CallExpr

    observed = []
    original = summary._closed_binding_type
    references = []
    original_binding = summary._binding_control_fact
    def binding(expr, **kwargs):
        result = original_binding(expr, **kwargs)
        if isinstance(expr, summary.ex.WorkflowRefLiteralExpr):
            references.append((expr, result))
        return result
    monkeypatch.setattr(summary, "_binding_control_fact", binding)

    def lookup(expr, **kwargs):
        result = original(expr, **kwargs)
        if isinstance(expr, CallExpr):
            observed.append((result, kwargs["facts"].workflow_return_types))
        return result

    monkeypatch.setattr(summary, "_closed_binding_type", lookup)
    assert not summary.expression_control_summary(snapshot.entry.typed_body.expr,
        result_type=snapshot.entry.typed_body.type_ref, facts=facts, local_values={})
    own_alias = _assert_imported_snapshot_type_alias(snapshot, facts, observed)
    _assert_imported_reference_alias(references, own_alias, leaf, reference, provider)


def _assert_imported_snapshot_type_alias(snapshot, facts, observed):
    assert observed
    own_alias = snapshot.module_workflow_signatures["owner"]["dep"].return_type_ref
    caller_alias = facts.workflow_return_types["dep"]
    assert own_alias != caller_alias
    assert observed[0][0] == own_alias
    assert observed[0][1]["dep"] == own_alias
    return own_alias


def _assert_imported_reference_alias(references, own_alias, leaf, reference, provider):
    if reference:
        assert references
        assert references[0][0].target_name == "dep"
        assert references[0][1][1].return_type_ref == own_alias
        assert references[0][1][2].return_type_ref == own_alias
        assert references[0][1][1].extern_rebinding_plan.is_empty
        assert references[0][1][1].authority_source.workflow_name == "dep"
        if provider:
            assert leaf.externs["providers.execute"].provider_id == "selected-provider"


@pytest.mark.parametrize("reference,provider", [(False, False), (True, False), (True, True)])
def test_imported_helper_reads_its_original_snapshot_alias_view(tmp_path, monkeypatch, reference, provider):
    from orchestrator.workflow_lisp.closed.build import Builder
    from orchestrator.workflow_lisp.closed import command_templates as summary

    leaf, snapshot = _compile_imported_helper_snapshot(tmp_path, reference, provider)
    caller = _compile_imported_snapshot_caller(tmp_path, snapshot)
    builder = Builder(caller)
    assert builder.procedure_owners["owner::helper"][1] is snapshot
    assert snapshot.producer_lowering_schema == (2 if reference else 1) and caller.producer_lowering_schema == 2
    facts = _imported_snapshot_control_facts(caller, builder, summary)
    _assert_imported_snapshot_alias_facts(leaf, snapshot, facts, reference, provider, monkeypatch)


def _command_preparation_call_shapes(call_kind, command):
    if call_kind == "procedure":
        declaration = '(defproc helper ((flag Bool)) -> Int '
        declaration += ':effects ((uses-command echo)) :lowering inline ' + command('flag') + ')'
        first, second = '(helper alias)', '(helper materialized)'
    else:
        declaration = '(defworkflow helper ((flag Bool)) -> Int ' + command('flag') + ')'
        first, second = '(call helper :flag alias)', '(call helper :flag materialized)'
    return declaration, first, second


def _assert_prepared_command_call_order(calls):
    from orchestrator.workflow_lisp.wcc.model import WccCall

    assert [(node.args if isinstance(node, WccCall) else tuple(value for _, value in node.keyword_args))[0].name
        for node in calls] == ["alias", "materialized"]


@pytest.mark.parametrize("call_kind", ("procedure", "workflow"))
def test_call_preparation_consumes_real_alias_facts_after_operand_normalization(tmp_path, call_kind):
    from orchestrator.workflow_lisp.closed.build import Builder
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.model import WccCall, WccPerform
    from tests.test_workflow_lisp_closed_command_transport import (
        _command, _compile, _declaration_resolver, _scope_inputs, _walk_wcc,
        _without_authorized_annotations,
    )

    declaration, first, second = _command_preparation_call_shapes(call_kind, _command)
    program = _compile(tmp_path,
        '(let* ((alias true) (first ' + first + ') '
        '(materialized (if true true false))) ' + second + ')', declarations=declaration)
    builder = Builder(program)
    inputs, facts = _scope_inputs(program, builder)
    observed = []

    def prepare(selector, expr, call, context, actual_values):
        operands = call.args if isinstance(call, WccCall) else tuple(value for _, value in call.keyword_args)
        observed.append((getattr(actual_values[0], "value", None), operands[0].name, selector))

    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=facts, producer_lowering_schema=program.producer_lowering_schema,
        include_command_plans=True, source_program=program,
        command_bindings=builder._command_bindings(program, program.entry_module)[0],
        call_preparator=prepare, call_declaration_identity=_declaration_resolver(program, builder))
    assert len(observed) == 2
    did = ["cp/transport", call_kind, "helper"]
    assert observed == [(None, "materialized", (did, 1)), (True, "alias", (did, 0))]
    calls = [node for node in _walk_wcc(annotated)
        if isinstance(node, WccCall)
        or isinstance(node, WccPerform) and node.perform_kind == "workflow_call"]
    _assert_prepared_command_call_order(calls)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(
        program.entry.typed_body, **inputs))
    assert _without_authorized_annotations(annotated) == _without_authorized_annotations(neutral)
    assert not builder.definitions and not builder.run_ref_producers
    assert not builder.emitted_descriptors and not builder.generated_result_contract_requests
    assert not builder.boundary_requests
