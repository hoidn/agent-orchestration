"""Selected surface control is checked against independent pre-hoist fragments."""

from pathlib import Path
from dataclasses import replace

import pytest

from orchestrator.workflow_lisp.expressions import FieldAccessExpr, NameExpr
from tests.test_workflow_lisp_command_templates import SPAN, _literal


def test_runtime_fact_is_exact_and_preserves_reference_materialization():
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import (
        RUNTIME_REFERENCE, is_direct_reference, wcc_binding_materialization,
    )
    from orchestrator.workflow_lisp.lowering.values import inline_expr_field_value

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
    from orchestrator.workflow_lisp.lowering.values import _resolve_inline_let_bindings
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE

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


@pytest.mark.parametrize("proc,body,expected,step_count", [
    ("", "(record Pair :left left :right right)", False, 0),
    ("", '(record Pair :left left :right "literal")', False, 1),
    ("", "(let* ((x (if flag left right))) (record Pair :left x :right right))", False, 1),
    (_CONTROL_PROC.replace("MODE", "inline"), "(pick flag left right)", True, 1),
    (_CONTROL_PROC.replace("MODE", "private-workflow"), "(pick flag left right)", False, 1),
    (_PURE_PROC, "(pick flag left right)", False, 1),
    ("", '(let* ((r (command-result echo :argv ("python" "probe.py") :returns Pair)) (unused (match choice ((A a) (record Pair :left left :right right)) ((B b) (record Pair :left right :right left))))) r)', False, 1),
])
def test_branch_summary_matches_real_pre_hoist_fragment(tmp_path, monkeypatch, proc, body, expected, step_count):
    from copy import deepcopy
    from orchestrator.workflow_lisp.compiler import compile_stage3_module
    from orchestrator.workflow_lisp.lowering import core
    from orchestrator.workflow_lisp.lowering.command_control_summary import (
        branch_control_summary, control_facts_for_context,
    )
    from orchestrator.workflow_lisp.lowering.composition_graph import (
        CompositionScope, build_fragment, fragment_requires_helper_boundary,
    )
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    source = tmp_path / "entry.orc"
    source.write_text(
        '(workflow-lisp (:language "0.1") (:target-dsl "2.32") '
        '(defrecord Pair (left String) (right String)) (defunion Choice (A) (B)) '
        + proc + ' (defworkflow run ((choice Choice) (flag Bool) (left String) (right String)) -> Pair '
        '(match choice ((A a) ' + body + ') ((B b) (record Pair :left left :right right)))))'
    )
    original = core._lower_conditional_branch_expr
    observations = {}

    def branch(expr, **kwargs):
        selected = branch_control_summary(
            expr, result_type=kwargs["result_type"], facts=control_facts_for_context(kwargs["context"]),
            local_values=kwargs["local_values"],
        )
        steps, terminal = original(expr, **kwargs)
        if kwargs["context"].workflow_name == "run" and kwargs["step_name"].endswith(("__a", "__b")):
            fragment = build_fragment(
                emitted_steps=deepcopy(steps),
                scope=CompositionScope(kwargs["step_name"], None, "match_case", None),
                output_refs=terminal.output_refs, hidden_inputs=terminal.hidden_inputs,
            )
            observations[kwargs["step_name"].rsplit("__", 1)[-1]] = (
                selected, fragment_requires_helper_boundary(fragment), len(steps),
            )
        return steps, terminal

    monkeypatch.setattr(core, "_lower_conditional_branch_expr", branch)
    compile_stage3_module(
        source, entry_workflow="run", workspace_root=tmp_path,
        lowering_route="legacy", validate_shared=False,
        command_boundaries={"echo": ExternalToolBinding(name="echo", stable_command=("python", "probe.py"))},
    )
    assert observations == {"a": (expected, expected, step_count), "b": (False, False, 0)}


@pytest.mark.parametrize("fixture_kind", ["produce", "resume", "finalize"])
def test_generated_control_and_phase_wrapper_match_real_fragment(tmp_path, monkeypatch, fixture_kind):
    from orchestrator.workflow_lisp import expressions as ex
    from orchestrator.workflow_lisp.lowering import control_dispatch
    from orchestrator.workflow_lisp.lowering.command_control_summary import (
        expression_control_summary, control_facts_for_context,
    )
    from orchestrator.workflow_lisp.lowering.composition_graph import (
        CompositionScope, build_fragment, fragment_requires_helper_boundary,
    )
    from tests import test_workflow_lisp_phase_stdlib as phase
    from tests import test_workflow_lisp_resource_stdlib as resource

    intrinsic_types = (ex.ProduceOneOfExpr, ex.ResumeOrStartExpr, ex.FinalizeSelectedItemExpr)
    observed_types = (*intrinsic_types, ex.WithPhaseExpr, ex.RunProviderPhaseExpr, ex.ResourceTransitionExpr)
    original = control_dispatch._control_lower_expression_impl
    rows = []

    def dispatch(typed, *, context, local_values):
        interested = isinstance(typed.expr, observed_types)
        if interested:
            selected = expression_control_summary(
                typed.expr, result_type=typed.type_ref, facts=control_facts_for_context(context), local_values=local_values,
            )
        if isinstance(typed.expr, ex.WithPhaseExpr):
            _assert_selected_phase_shortcuts(typed.expr, context=context, local_values=local_values)
        steps, terminal = original(typed, context=context, local_values=local_values)
        if interested:
            fragment = build_fragment(
                emitted_steps=steps, scope=CompositionScope("probe", None, "workflow", None),
                output_refs=terminal.output_refs, hidden_inputs=terminal.hidden_inputs,
            )
            oracle = fragment_requires_helper_boundary(fragment)
            assert selected == oracle
            rows.append((type(typed.expr), selected))
        return steps, terminal

    monkeypatch.setattr(control_dispatch, "_control_lower_expression_impl", dispatch)
    if fixture_kind == "produce":
        phase._compile(phase.VALID_RUN_PROVIDER_FIXTURE, tmp_path=tmp_path)
        expected_type = ex.ProduceOneOfExpr
    elif fixture_kind == "resume":
        phase._compile(phase.VALID_RESUME_FIXTURE, tmp_path=tmp_path)
        expected_type = ex.ResumeOrStartExpr
    else:
        from orchestrator.workflow_lisp.compiler import compile_stage3_module

        compile_stage3_module(
            resource.VALID_FINALIZE_FIXTURE, workspace_root=tmp_path,
            command_boundaries=resource._command_boundary_environment().bindings_by_name,
            validate_shared=False, lowering_route="legacy",
        )
        expected_type = ex.FinalizeSelectedItemExpr
    assert (expected_type, True) in rows
    if fixture_kind == "produce":
        assert (ex.RunProviderPhaseExpr, False) in rows
        assert any(kind is ex.WithPhaseExpr for kind, _ in rows)


def test_unknown_operation_requires_an_explicit_summary_rule():
    from orchestrator.workflow_lisp.lowering.command_control_summary import expression_control_summary

    with pytest.raises(ValueError, match="no selected surface-control rule"):
        expression_control_summary(object(), result_type=None, facts=None, local_values={})


def test_untyped_binding_keeps_existing_lexical_type_fact(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary
    from orchestrator.workflow_lisp.lowering.context import _context_with_local_type_binding

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
    legacy = SimpleNamespace(local_type_bindings={"shadow": retained_type})
    assert _context_with_local_type_binding(legacy, binding_name="shadow", binding_type=None) is legacy
    assert observed == [legacy.local_type_bindings]


def test_materialized_capture_preserves_whole_roots_without_nested_leaf_facts():
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.context_types import _record, contextual_type
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.lowering.command_control_summary import _materialized_binding_value
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE
    from orchestrator.workflow_lisp.lowering.effects import _provider_context_capture_output_refs
    from orchestrator.workflow_lisp.lowering.control_dispatch import _binding_local_value_from_terminal
    from orchestrator.workflow_lisp.lowering.values import inline_expr_field_value

    scalar = PrimitiveTypeRef(name="String")
    nested = _record("Nested", (("leaf", scalar),))
    captured = contextual_type(nested, _record("Context", (("schema", scalar),)))
    outputs = _provider_context_capture_output_refs("provider", captured, capture_context=True)
    assert outputs == {
        "return__result": "root.steps.provider.artifacts.result",
        "return__context": "root.steps.provider.artifacts.context",
    }
    context = SimpleNamespace(type_env=SimpleNamespace(target_dsl_version="2.31"))
    actual = _binding_local_value_from_terminal(
        object(), binding_type=captured,
        binding_terminal=SimpleNamespace(output_refs=outputs, returned_union_type_name=None), context=context,
    )
    predicted = _materialized_binding_value(captured, output_names=tuple(outputs), facts=context)
    assert predicted == {"result": RUNTIME_REFERENCE, "context": RUNTIME_REFERENCE}
    root = NameExpr(name="captured", span=SPAN, form_path=())
    projected = FieldAccessExpr(base=root, fields=("result", "leaf"), span=SPAN, form_path=())
    for value in (actual, predicted):
        assert inline_expr_field_value(
            projected, field_path=(), local_values={"captured": value},
            bound_record_fields=True, phase_target_values=None,
        ) is None


def _assert_selected_phase_shortcuts(expr, *, context, local_values):
    from orchestrator.workflow_lisp import expressions as ex
    from orchestrator.workflow_lisp.lowering import core
    from orchestrator.workflow_lisp.lowering.context import _copy_context_with_phase_scope
    from orchestrator.workflow_lisp.lowering.phase_scope import _resolve_active_phase_scope
    from orchestrator.workflow_lisp.lowering.command_control_summary import (
        _with_phase_facts, _suffix_outputs_available, control_facts_for_context,
    )

    active = _resolve_active_phase_scope(expr, local_values=local_values)
    facts = _with_phase_facts(expr, facts=control_facts_for_context(context), local_values=local_values)
    assert facts.phase_scope.scope == active.scope
    assert set(facts.phase_target_values) == set(active.target_refs)
    target = ex.PhaseTargetExpr(target_name=next(iter(active.target_refs)), span=expr.span, form_path=expr.form_path)
    actual_context = _copy_context_with_phase_scope(context, phase_scope=active)
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef

    result_type = PrimitiveTypeRef(name="String")
    suffix = (("unused", _literal(True)),)
    let = ex.LetStarExpr(bindings=suffix, body=target, span=expr.span, form_path=expr.form_path)
    assert core._inline_output_refs_for_expr(target, type_ref=result_type, context=actual_context, local_values=local_values) is not None
    assert core._inline_output_refs_for_expr(let, type_ref=result_type, context=actual_context, local_values=local_values) is None
    assert not _suffix_outputs_available(let, suffix, result_type=result_type, facts=facts, local_values=local_values)
    assert _suffix_outputs_available(let, (), result_type=result_type, facts=facts, local_values=local_values)


@pytest.mark.parametrize("expr", [_literal(True), NameExpr(name="pure", span=SPAN, form_path=())])
def test_typed_pure_values_have_an_explicit_noncontrol_rule(expr):
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.lowering.command_control_summary import expression_control_summary

    assert not expression_control_summary(expr, result_type=PrimitiveTypeRef(name="Bool"), facts=None, local_values={})



@pytest.mark.parametrize("caller_value", ['"caller"', '42'])
def test_selected_inline_helper_uses_its_real_lexical_types(tmp_path, monkeypatch, caller_value):
    from tests.test_workflow_lisp_command_scopes import _compile
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary, core
    from orchestrator.workflow_lisp.expressions import LiteralExpr

    program, inputs, facts = _compile(tmp_path,
        f'(let* ((shadow {caller_value}) (hook (bind-proc (proc-ref helper) :fixed true))) (hook 1))',
        declarations='(defproc helper ((fixed Bool) (n Int)) -> Result :effects ((uses-command echo)) :lowering inline '
        '(let* ((shadow true) (r (command-result echo :argv ("python" "probe.py" fixed n) :returns Result))) r))')
    typed = summary.ControlFacts(**facts, closed_program=True,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    observed = []
    original = summary._closed_binding_type

    def lookup(expr, **kwargs):
        result = original(expr, **kwargs)
        if isinstance(expr, LiteralExpr) and expr.value is True:
            observed.append((result, kwargs["facts"].local_type_bindings))
        return result

    def reject_legacy(*args, **kwargs):
        pytest.fail("closed selected helper reached legacy type inference")

    monkeypatch.setattr(core, "_infer_inline_binding_type", reject_legacy)
    monkeypatch.setattr(core, "_resolve_lowering_expr_type", reject_legacy)
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
    leaf_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.32") '
        '(defmodule leaf) (export get) (defrecord Leaf (n Int)) '
        f'(defworkflow get () -> Leaf {leaf_body}))')
    leaf = compile_stage3_entrypoint(leaf_path, source_roots=(tmp_path,), workspace_root=tmp_path,
        provider_externs={"providers.execute": "selected-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
        lowering_route="legacy", validate_shared=True).validated_bundles_by_name["leaf::get"]
    owner_path = tmp_path / "owner.orc"
    owner_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.32") '
        '(defmodule owner) (export get) (defrecord Leaf (n Int)) (defrecord Result (i Int) (s String)) '
        '(defproc helper () -> Result :effects ((calls-workflow dep)) :lowering inline '
        '(let* ((r (call dep)) (shadow true)) (record Result :i r.n :s "owner"))) '
        '(defworkflow get () -> Result (helper)))')
    if reference:
        owner_path.write_text(owner_path.read_text().replace("(let* ((r (call dep))", "(let* ((ref (workflow-ref dep)) (r (call dep))"))
        owner_path.write_text(owner_path.read_text().replace('"2.32"', '"2.35"'))
        snapshot = compile_typed_program(owner_path, entry_workflow="get", source_roots=(tmp_path,),
            workspace_root=tmp_path, command_boundaries={}, imported_programs={"dep": leaf.typed_program})
    else:
        owner = compile_stage3_entrypoint(owner_path, source_roots=(tmp_path,), workspace_root=tmp_path,
            imported_workflow_bundles={"dep": leaf}, lowering_route="legacy", validate_shared=True)
        snapshot = owner.validated_bundles_by_name["owner::get"].typed_program
    snapshot = replace(snapshot, entry=snapshot.workflows["owner::get"])
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
        workflow_name=entry.definition.name, closed_program=True,
        procedure_catalog=ProcedureCatalog(signatures_by_name={name: item.signature for name, item in caller.procedures.items()},
            definitions_by_name={name: item.definition for name, item in caller.procedures.items()}, call_graph={}),
        workflow_return_types=builder._workflow_return_types_for(caller, entry.definition.name),
        procedure_return_types=builder.procedure_return_types, procedure_owners=builder.procedure_owners,
        base_workflow_return_types=builder.workflow_return_types)
    return facts


def _assert_imported_snapshot_alias_facts(leaf, snapshot, facts, reference, provider, monkeypatch):
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary
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
            assert leaf.typed_program.externs["providers.execute"].provider_id == "selected-provider"


@pytest.mark.parametrize("reference,provider", [(False, False), (True, False), (True, True)])
def test_imported_helper_reads_its_original_snapshot_alias_view(tmp_path, monkeypatch, reference, provider):
    from orchestrator.workflow_lisp.closed.build import Builder
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary

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
