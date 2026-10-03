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


@pytest.mark.parametrize("reference,provider", [(False, False), (True, False), (True, True)])
def test_imported_helper_reads_its_original_snapshot_alias_view(tmp_path, monkeypatch, reference, provider):
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.closed.build import Builder
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary
    from orchestrator.workflow_lisp.workflows import WorkflowCatalog
    from orchestrator.workflow_lisp.procedures import ProcedureCatalog
    from orchestrator.workflow_lisp.expressions import CallExpr

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
    caller_path = tmp_path / "caller.orc"
    caller_path.write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.35") '
        '(defmodule caller) (export run) (defrecord Result (i Int) (s String)) (defworkflow run ((shadow String)) -> String '
        '(let* ((r (call dep))) shadow)))')
    caller = compile_typed_program(caller_path, entry_workflow="run", workspace_root=tmp_path,
        source_roots=(tmp_path,), command_boundaries={}, imported_programs={"dep": snapshot})
    builder = Builder(caller)
    assert builder.procedure_owners["owner::helper"][1] is snapshot
    assert snapshot.producer_lowering_schema == (2 if reference else 1) and caller.producer_lowering_schema == 2
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
    assert observed
    own_alias = snapshot.module_workflow_signatures["owner"]["dep"].return_type_ref
    caller_alias = facts.workflow_return_types["dep"]
    assert own_alias != caller_alias
    assert observed[0][0] == own_alias
    assert observed[0][1]["dep"] == own_alias
    if reference:
        assert references
        assert references[0][0].target_name == "dep"
        assert references[0][1][1].return_type_ref == own_alias
        assert references[0][1][2].return_type_ref == own_alias
        assert references[0][1][1].extern_rebinding_plan.is_empty
        assert references[0][1][1].authority_source.workflow_name == "dep"
        if provider:
            assert leaf.typed_program.externs["providers.execute"].provider_id == "selected-provider"


def test_closed_workflow_ref_aliases_remain_compile_time_values(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile, _walk
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary, core
    from orchestrator.workflow_lisp.wcc.model import WccLet
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.type_env import WorkflowRefTypeRef
    from orchestrator.workflow_lisp.workflow_refs import ResolvedWorkflowRef

    program, inputs, facts = _compile(tmp_path,
        '(let* ((original (workflow-ref leaf)) (alias original)) (record Result :i 1 :s "done"))',
        declarations='(defworkflow leaf () -> Result (record Result :i 7 :s "leaf"))')
    typed = summary.ControlFacts(**facts, closed_program=True,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    def reject_legacy(*args, **kwargs):
        pytest.fail("closed compile-time workflow alias reached legacy inference")
    monkeypatch.setattr(core, "_resolve_lowering_expr_type", reject_legacy)
    expr = program.entry.typed_body.expr
    _, value, type_ref = summary._binding_control_fact(expr.bindings[0][1],
        name="original", facts=typed, local_values={})
    assert isinstance(value, ResolvedWorkflowRef)
    assert isinstance(type_ref, WorkflowRefTypeRef)
    assert summary._binding_control_fact(expr.bindings[1][1], name="alias", facts=typed,
        local_values={"original": value}) == (False, value, type_ref)
    assert not summary.expression_control_summary(expr, result_type=program.entry.typed_body.type_ref,
        facts=typed, local_values={})
    assert all(item.bound_name not in {"original", "alias"} for item in _walk(
        elaborate_typed_workflow_body(program.entry.typed_body, **inputs)) if isinstance(item, WccLet))


def test_command_scope_capture_retains_real_loop_state_frame(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile, _without_scopes, _walk
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf

    program, inputs, facts = _compile(tmp_path,
        '(loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted 0 (fn (state) '
        '(let-proc (local ((n Choice)) -> Int :captures (state) '
        '(match n ((A a) (+ state.i a.i)) ((B b) state.i))) '
        '(let* ((hook (proc-ref local)) (state "shadow") (answer (hook choice))) (done answer)))))',
        params='(choice Choice)', returns='Int')
    captured = []
    original = CommandScopeContext.bind
    def observe(context, expr, **kwargs):
        child = original(context, expr, **kwargs)
        if kwargs['capture_source'] is not None:
            captured.append((kwargs, child.values[kwargs['name']]))
        return child
    monkeypatch.setattr(CommandScopeContext, 'bind', observe)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert captured
    assert captured[0][0]['capture_source'][0].name == 'state'
    assert isinstance(captured[0][1], dict) and 'i' in captured[0][1]
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


@pytest.mark.parametrize('body,code', [
    ('(let* ((input "shadow") (answer (+ input 1))) (record Result :i answer :s input))', 'pure_expr_operand_type_mismatch'),
    ('(let* ((hook (bind-proc (proc-ref helper) :fixed "bad"))) (record Result :i (hook 1) :s "done"))', 'proc_ref_binding_type_invalid'),
])
def test_closed_capture_changes_preserve_unrelated_type_errors(tmp_path, body, code):
    from tests.test_workflow_lisp_command_scopes import _compile
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, body, params='(input Int)',
            declarations='(defproc helper ((fixed Int) (n Int)) -> Int :effects () :lowering inline (+ fixed n))')
    assert code in {item.code for item in caught.value.diagnostics}


def test_command_scope_call_types_use_same_prepared_condition_owner(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc import elaborate

    program, inputs, facts = _compile(tmp_path,
        '(if (let* ((b (helper))) b) (record Result :i 1 :s "yes") (record Result :i 2 :s "no"))',
        declarations='(defproc helper () -> Bool :effects ((uses-command echo)) :lowering inline '
        '(command-result echo :argv ("python" "probe.py") :returns Bool))')
    observed = []
    original = elaborate._elaboration_procedure_return_types
    def observe(body, edges, returns, **kwargs):
        assert kwargs['closed_program'] is True
        result = original(body, edges, returns, **kwargs)
        observed.append((_without_scopes(body.expr), dict(edges), result))
        return result
    monkeypatch.setattr(elaborate, '_elaboration_procedure_return_types', observe)
    elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert len(observed) == 3
    assert observed[0] == observed[1] == observed[2]


def test_loop_exhaustion_command_facts_keep_enclosing_owner(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts

    program, inputs, facts = _compile(tmp_path,
        '(loop/recur :max 1 :state (loop-state (i Int 0)) :on-exhausted '
        '(match choice ((A a) (if flag 1 0)) '
        '((B b) 0)) (fn (state) (done 1)))', params='(choice Choice) (flag Bool)', returns='Int')
    observed = []
    original = CommandScopeContext.arm
    def observe(context, expr, **kwargs):
        observed.append(context)
        return original(context, expr, **kwargs)
    monkeypatch.setattr(CommandScopeContext, 'arm', observe)
    elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert observed
    assert all(context.owner == 'wcc' and context.control.iteration_scope is None for context in observed)
    assert all(any(row[1] == program.entry.typed_body.expr.binding_identity for row in context.retained_bindings)
        for context in observed)


def test_proof_branch_command_facts_consume_actual_narrowed_environment(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
    from orchestrator.workflow_lisp.type_env import VariantCaseTypeRef, UnionTypeRef

    body = '(let* ((choice (variant ImplementationState COMPLETED :execution_report report))) (if (= choice.variant COMPLETED) (let* ((x choice.execution_report)) '
    body += '(command-result echo :argv ("python" "probe.py" x) :returns Result)) (record Result :i 0 :s "no")))'
    program, inputs, facts = _compile(tmp_path, body,
        params='(report WorkReport)', target='2.26', schema=2, declarations='''
        (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)
        (defunion ImplementationState (COMPLETED (execution_report WorkReport))
          (BLOCKED (progress_report WorkReport)))''')
    seen = []
    original = CommandScopeContext.bind
    def observe(context, expr, **kwargs):
        if kwargs['name'] == 'x': seen.append(context)
        return original(context, expr, **kwargs)
    monkeypatch.setattr(CommandScopeContext, 'bind', observe)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert seen
    context = seen[0]
    narrowed = context.control.local_type_bindings['choice']
    assert isinstance(narrowed, VariantCaseTypeRef) and narrowed.variant_name == 'COMPLETED'
    operand = context.operands['choice']
    assert operand.metadata.type_ref == narrowed
    rows = [row for row in context.retained_bindings if row[1] == operand.metadata.binding_identity]
    assert isinstance(rows[-2][2], UnionTypeRef) and rows[-1][2] == narrowed
    assert rows[-2][0] == rows[-1][0] and rows[-2][3] is rows[-1][3]
    assert context.owner == 'wcc'
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


@pytest.mark.parametrize('alias', [False, True])
@pytest.mark.parametrize('reset_before', [False, True])
def test_erased_local_proc_refs_remain_available_to_command_facts(tmp_path, monkeypatch, alias, reset_before):
    from tests.test_workflow_lisp_command_scopes import _compile, _walk, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
    from orchestrator.workflow_lisp.wcc.model import WccCase, WccLet
    from orchestrator.workflow_lisp.procedure_refs import ResolvedProcRefValue
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary

    bindings = '((hook (proc-ref helper)) (alias hook))' if alias else '((hook (proc-ref helper)))'
    callee = 'alias' if alias else 'hook'
    arm = f'({callee} flag)'
    if reset_before:
        arm = f'(if flag (match other ((A item) {arm}) ((B item) (record Result :i 0 :s "inner"))) (record Result :i 0 :s "no"))'
    program, inputs, facts = _compile(tmp_path, '(loop/recur :max 1 :state (loop-state (i Int 0)) '
        f':on-exhausted (record Result :i 0 :s "stop") (fn (state) (let* {bindings[:-1]} '
        f'(answer (match choice ((A a) {arm}) ((B b) (record Result :i 0 :s b.s))))) '
        '(done answer))))', params='(choice Choice) (other Choice) (flag Bool)',
        declarations='(defproc helper ((flag Bool)) -> Result :effects ((uses-command echo)) :lowering inline '
        '(if flag (command-result echo :argv ("python" "probe.py") :returns Result) (record Result :i 0 :s "no")))')
    seen = []
    original = summary._procedure_control_fact
    def observe(expr, **kwargs):
        seen.append(kwargs['local_values'].get(callee))
        return original(expr, **kwargs)
    monkeypatch.setattr(summary, '_procedure_control_fact', observe)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    case = next(node for node in _walk(annotated) if isinstance(node, WccCase))
    assert seen and all(isinstance(value, ResolvedProcRefValue) for value in seen)
    if reset_before:
        assert tuple(name for name, _ in case.arms[0].command_scope) == ('other', 'flag')
    else:
        assert case.arms[0].command_scope is None  # The actual loop owner selects the private helper override.
    _assert_erased_proc_ref_binders(annotated)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


def _assert_erased_proc_ref_binders(body):
    from tests.test_workflow_lisp_command_scopes import _walk
    from orchestrator.workflow_lisp.wcc.model import WccLet
    assert not any(isinstance(node, WccLet) and node.bound_name in {'hook', 'alias'} for node in _walk(body))


def test_runtime_shadow_removes_erased_reference_before_command_reset(tmp_path, monkeypatch):
    from tests.test_workflow_lisp_command_scopes import _compile, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf

    source = '(loop/recur :max 1 :state (loop-state (i Int 0)) :on-exhausted (record Result :i 0 :s "stop") '
    source += '(fn (state) (let* ((hook (proc-ref helper))) (let* ((hook "shadow") '
    source += '(answer (match choice ((A a) (if flag (helper flag) (record Result :i 0 :s "no"))) '
    source += '((B b) (record Result :i 0 :s "b"))))) (done answer)))))'
    program, inputs, facts = _compile(tmp_path, source, params='(choice Choice) (flag Bool)',
        declarations='(defproc helper ((flag Bool)) -> Result :effects ((uses-command echo)) :lowering inline '
        '(if flag (command-result echo :argv ("python" "probe.py") :returns Result) (record Result :i 0 :s "no")))')
    resets = []
    original = CommandScopeContext.arm
    def observe(context, expr, **kwargs):
        roots, child = original(context, expr, **kwargs)
        if roots is not None: resets.append(child)
        return roots, child
    monkeypatch.setattr(CommandScopeContext, 'arm', observe)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert resets
    assert all('hook' not in child.values and 'hook' not in child.operands for child in resets)
    assert all('hook' not in child.control.local_type_bindings for child in resets)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


@pytest.mark.parametrize('nested', ['loop', 'match'])
def test_nested_command_owners_preserve_names_removed_by_reset(tmp_path, monkeypatch, nested):
    from tests.test_workflow_lisp_command_scopes import _compile, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf

    result = '(record Result :i x :s "done")'
    if nested == 'loop':
        inner = '(loop/recur :max 1 :state (record State :i 0) :on-exhausted (record Result :i 0 :s "stop") '
        inner += f'(fn (state) (let* ((x 1)) (done {result}))))'
    else:
        inner = '(let* ((inner (command-result echo :argv ("python" "probe.py") :returns Choice))) (match inner '
        inner += f'((A item) (let* ((x 1)) {result})) ((B item) (record Result :i 0 :s "b"))))'
    source = f'(match choice ((A a) (if true {inner} (record Result :i 0 :s "no"))) '
    source += '((B b) (record Result :i 0 :s "b")))'
    program, inputs, facts = _compile(tmp_path, source, params='(choice Choice) (unused Int)',
        schema=1, target='2.32', declarations='(defrecord State (i Int))')
    seen = []
    original = CommandScopeContext.bind
    def observe(context, expr, **kwargs):
        if kwargs['name'] == 'x': seen.append(context)
        return original(context, expr, **kwargs)
    monkeypatch.setattr(CommandScopeContext, 'bind', observe)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert seen
    assert all('unused' not in context.control.local_type_bindings for context in seen)
    assert all('unused' not in context.values and 'unused' not in context.operands for context in seen)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


def test_forwarded_workflow_reference_is_not_a_runtime_command_root(tmp_path):
    from tests.test_workflow_lisp_command_scopes import _compile, _walk, _without_scopes
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.expressions import NameExpr, ProcedureCallExpr
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
    from orchestrator.workflow_lisp.wcc.model import WccCase

    program, inputs, facts = _compile(tmp_path,
        '(loop/recur :max 1 :state (loop-state (i Int 0)) '
        ':on-exhausted (record Result :i 0 :s "stop") (fn (state) '
        '(let* ((runner (workflow-ref leaf)) '
        '(answer (match choice ((A a) (if flag (invoke runner a.i) '
        '(record Result :i 0 :s "no"))) ((B b) (record Result :i 0 :s b.s))))) (done answer))))',
        params='(choice Choice) (flag Bool)', declarations='''
        (defworkflow leaf ((n Int)) -> Result (record Result :i n :s "leaf"))
        (defproc invoke ((runner WorkflowRef[Int -> Result]) (n Int)) -> Result
          :effects ((calls-workflow runner)) :lowering inline (call runner :n n))''')
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    forwarded = [expr for expr in _walk(program.entry.typed_body.expr) if isinstance(expr, ProcedureCallExpr)
        and any(isinstance(arg, NameExpr) and arg.name == 'runner' for arg in expr.args)]
    assert forwarded
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    case = next(node for node in _walk(annotated) if isinstance(node, WccCase))
    assert tuple(name for name, _ in case.arms[0].command_scope) == ('flag', 'a')
    assert _without_scopes(annotated) == _without_scopes(neutral)
    assert normalize_wcc_body_to_anf(annotated) == annotated
