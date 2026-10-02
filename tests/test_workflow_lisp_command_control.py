"""Selected surface control is checked against independent pre-hoist fragments."""

from pathlib import Path

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


def test_retained_capture_type_precedes_partial_surface_inference(monkeypatch):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.expressions import ProviderResultExpr
    from orchestrator.workflow_lisp.context_types import _record, contextual_type
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.lowering import core
    from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts, _binding_control_fact
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE

    scalar = PrimitiveTypeRef(name="String")
    captured = contextual_type(_record("Nested", (("leaf", scalar),)), _record("Context", (("schema", scalar),)))
    expr = ProviderResultExpr(provider=NameExpr(name="provider", span=SPAN, form_path=()), prompt=_literal("prompt"), inputs=(), capture_context="portable", returns_type_name="Nested", span=SPAN, form_path=())
    facts = ControlFacts(
        signature=None, type_env=SimpleNamespace(target_dsl_version="2.31"), local_type_bindings={},
        typed_procedures={}, workflow_catalog=None, workflows_by_name={}, procedure_type_envs={},
        workflow_name="run", retained_binding_types={"captured": captured},
    )
    def rejected_legacy_inference(*args, **kwargs):
        pytest.fail("retained type must not depend on partial surface inference")
    monkeypatch.setattr(core, "_resolve_lowering_expr_type", rejected_legacy_inference)
    assert _binding_control_fact(expr, name="captured", facts=facts, local_values={}) == (
        False, {"result": RUNTIME_REFERENCE, "context": RUNTIME_REFERENCE}, captured,
    )


@pytest.mark.parametrize("expr", [_literal(True), NameExpr(name="pure", span=SPAN, form_path=())])
def test_typed_pure_values_have_an_explicit_noncontrol_rule(expr):
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.lowering.command_control_summary import expression_control_summary

    assert not expression_control_summary(expr, result_type=PrimitiveTypeRef(name="Bool"), facts=None, local_values={})


@pytest.mark.parametrize("helper_has_retained_type", [False, True])
def test_selected_inline_helper_replaces_caller_binding_type_facts(monkeypatch, helper_has_retained_type):
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.expressions import ProcedureCallExpr
    from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary

    caller_type = PrimitiveTypeRef(name="String")
    retained_helper_types = {"shadow": PrimitiveTypeRef(name="Bool")} if helper_has_retained_type else {}
    body = _literal(True)
    procedure = SimpleNamespace(
        signature=SimpleNamespace(name="selected-helper", params=()), specialization=None,
        resolved_lowering_mode=ProcedureLoweringMode.INLINE,
        typed_body=SimpleNamespace(expr=body, type_ref=PrimitiveTypeRef(name="Bool")),
    )
    facts = summary.ControlFacts(
        signature=None, type_env=None, local_type_bindings={}, typed_procedures={},
        workflow_catalog=SimpleNamespace(signatures_by_name={}), workflows_by_name={},
        procedure_type_envs={}, workflow_name="run", retained_binding_types={"shadow": caller_type},
        procedure_binding_types={"selected-helper": retained_helper_types, "authored-helper": {"shadow": PrimitiveTypeRef(name="Int")}},
    )
    monkeypatch.setattr(summary, "select_surface_procedure_call", lambda *args, **kwargs: (procedure, ()))
    monkeypatch.setattr(summary, "procedure_type_env_for", lambda *args, **kwargs: None)
    monkeypatch.setattr(summary, "_procedure_signature_local_type_bindings", lambda *args: {})
    observed = []
    monkeypatch.setattr(summary, "_expression_control_fact", lambda *args, **kwargs: (observed.append(kwargs["facts"].retained_binding_types) or False, ("return",)))
    call = ProcedureCallExpr(callee_name="authored-helper", args=(), span=SPAN, form_path=())
    assert summary._procedure_control_fact(call, facts=facts, local_values={}) == (False, ("return",))
    assert observed == [retained_helper_types]
    assert facts.retained_binding_types == {"shadow": caller_type}
