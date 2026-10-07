"""Command-root and lexical capture witnesses for closed compilation."""

from dataclasses import replace

import pytest

from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.model import WccLet
from tests.test_workflow_lisp_command_scopes import _capture_rows, _compile, _walk, _without_scopes


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


def _assert_forwarded_workflow_reference_remains_compile_time(typed_body):
    from orchestrator.workflow_lisp.expressions import NameExpr, ProcedureCallExpr

    forwarded = [expr for expr in _walk(typed_body.expr) if isinstance(expr, ProcedureCallExpr)
        and any(isinstance(arg, NameExpr) and arg.name == 'runner' for arg in expr.args)]
    assert forwarded


def test_forwarded_workflow_reference_is_not_a_runtime_command_root(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
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
    _assert_forwarded_workflow_reference_remains_compile_time(program.entry.typed_body)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    case = next(node for node in _walk(annotated) if isinstance(node, WccCase))
    assert tuple(name for name, _ in case.arms[0].command_scope) == ('flag', 'a')
    assert _without_scopes(annotated) == _without_scopes(neutral)
    assert normalize_wcc_body_to_anf(annotated) == annotated


@pytest.mark.parametrize("wrapped", [False, True])
def test_pure_bound_capture_uses_incoming_type_before_same_name_shadow(tmp_path, monkeypatch, wrapped):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary, core
    from orchestrator.workflow_lisp.wcc.elaborate import binding_type_for_elaboration

    source = ('(let-proc (local ((n Int)) -> Int :captures (input) (+ input n)) '
        '(let* ((hook (proc-ref local)) (input "shadow") (answer (hook 1))) (record Result :i answer :s input)))')
    if wrapped:
        source = f'(if flag {source} (record Result :i 0 :s "other"))'
    program, inputs, facts = _compile(tmp_path, source, params="(input Int) (flag Bool)")
    if not wrapped:
        _assert_unwrapped_capture_type_error(program, inputs, facts)
    captures = _capture_rows(program.entry.typed_body.expr)
    assert captures
    def reject_legacy(*args, **kwargs):
        pytest.fail("closed capture reached legacy inference")
    monkeypatch.setattr(core, "_infer_inline_binding_type", reject_legacy)
    monkeypatch.setattr(core, "_resolve_lowering_expr_type", reject_legacy)
    typed = ControlFacts(**facts, closed_program=True,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    _assert_capture_binding_uses_incoming_type(program, inputs, typed, captures, binding_type_for_elaboration, summary)


def _assert_unwrapped_capture_type_error(program, inputs, facts):
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    from orchestrator.workflow_lisp.compiler_session import CompilerSession
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

    with pytest.raises(LispFrontendCompileError) as caught:
        typecheck_expression(program.entry.typed_body.expr, type_env=inputs["type_env"],
            value_env=inputs["value_env"], workflow_catalog=facts["workflow_catalog"],
            procedure_catalog=facts["procedure_catalog"], compiler_session=CompilerSession())
    assert 'pure_expr_operand_type_mismatch' in {item.code for item in caught.value.diagnostics}


def _assert_capture_binding_uses_incoming_type(program, inputs, typed, captures, binding_type_for_elaboration, summary):
    for let, index, source in captures:
        name, expr = let.bindings[index]
        shadow_type = next(item.bound_type_ref for item in _walk(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
            if isinstance(item, WccLet) and item.bound_name == "input")
        child = replace(typed, local_type_bindings={"input": shadow_type})
        assert shadow_type != source[1]
        assert binding_type_for_elaboration(expr, type_env=child.type_env, value_env=child.local_type_bindings,
            workflow_return_types=child.workflow_return_types, procedure_return_types=child.procedure_return_types,
            closed_program=True, capture_source=source) == source[1]
        assert summary._binding_control_fact(expr, name=name, facts=child, local_values={}, capture_source=source)[2] == source[1]


@pytest.mark.parametrize("source", [
    '(let-proc (local ((n Choice)) -> Int :captures (input) (match n ((A a) (+ input a.i)) ((B b) input))) '
    '(let* ((hook (proc-ref local)) (input 100) (answer (hook choice))) (record Result :i answer :s "done")))',
    '(let* ((saved (+ input 1))) (let-proc (local ((n Choice)) -> Int :captures (saved) '
    '(match n ((A a) (+ saved a.i)) ((B b) saved))) (let* ((hook (proc-ref local)) '
    '(input "input-shadow") (saved "saved-shadow") (answer (hook choice))) (record Result :i answer :s saved))))',
])
def test_retained_capture_reads_original_value_in_actual_lexical_frame(tmp_path, monkeypatch, source):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE

    program, inputs, facts = _compile(tmp_path, source, params='(input Int) (choice Choice)')
    seen = []
    original = CommandScopeContext.bind

    def bind(context, expr, **kwargs):
        child = original(context, expr, **kwargs)
        if kwargs['capture_source'] is not None:
            retained = next(row for row in reversed(context.retained_bindings) if row[1] == kwargs['capture_source'][0])
            seen.append((kwargs, child.values[kwargs['name']], retained[3]))
        return child

    monkeypatch.setattr(CommandScopeContext, 'bind', bind)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    _assert_retained_capture_values(seen)
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)
    _assert_retained_capture_aliases(seen, annotated)


def _assert_retained_capture_values(seen):
    assert seen
    assert all(value is original_value for _, value, original_value in seen)


def _assert_retained_capture_aliases(seen, annotated):
    for kwargs, value, _ in seen:
        source_identity, source_type = kwargs['capture_source']
        assert source_type.name == 'Int'
        assert getattr(value, 'value', None) not in {'input-shadow', 'saved-shadow', 100}
        aliases = [item for item in _walk(annotated) if isinstance(item, WccLet)
            and item.metadata.node_id == kwargs['metadata'].node_id]
        assert aliases
        assert aliases[0].bound_value.metadata.binding_identity == source_identity
        assert aliases[0].bound_value.metadata.type_ref == source_type


def _assert_promoted_child_shape(helper, runtime, call):
    assert runtime["key"][6] == []
    assert len(runtime["params"]) == len(call["args"]) == 1
    assert call["args"][0]["k"] == "lit"
    assert call["args"][0]["v"] is True
    assert helper["params"] == []


def _assert_inline_homonym_keeps_caller_root(helper, closed):
    assert helper["key"][6][0][0] == "x"
    assert helper["key"][7][0]["routes"] == [["command-input", "x"]]
    assert helper["params"][0][1]["name"] == "Int"
    assert helper["key"][8]["params"] == []
    assert "command_params" not in helper
    assert closed.tree["command_params"] == [["x", 0]]


def _assert_native_homonym_keeps_typed_parameter(helper, closed):
    assert helper["key"][6] == helper["key"][7] == []
    assert helper["params"][0][1]["name"] == "Bool"
    assert helper["command_params"] == helper["key"][8]["command_params"] == [["x", 0]]
    assert "command_params" not in closed.tree


def test_promoted_parent_reuses_runtime_child_shape_with_final_residual_operands(tmp_path):
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from tests.test_workflow_lisp_closed_command_transport import _compile as _compile_closed, _command

    declarations = '(defproc runtime ((flag Bool)) -> Int :effects () :lowering private-workflow (if flag 1 2))'
    declarations += '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += '(let* ((result ' + _command('flag') + ')) (runtime flag)))'
    program = _compile_closed(tmp_path, '(helper true)', declarations=declarations)
    closed = build_closed_program(program)
    helper = next(row for row in closed.tree["definitions"].values() if row["key"][2] == "helper")
    runtime = next(row for row in closed.tree["definitions"].values() if row["key"][2] == "runtime")
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    (call,) = [node for node in _ast_nodes(helper["body"]) if node.get("k") == "call"]
    _assert_promoted_child_shape(helper, runtime, call)


@pytest.mark.parametrize("mode", ["inline", "private-workflow"])
def test_inline_literal_homonym_inherits_whole_root_while_native_keeps_its_runtime_parameter(tmp_path, mode):
    from orchestrator.workflow_lisp.closed.build import build_closed_program
    from tests.test_workflow_lisp_closed_command_transport import _compile as _compile_closed, _command, _commands

    declarations = '(defproc helper ((x Bool)) -> Int :effects ((uses-command echo)) '
    declarations += ':lowering ' + mode + ' ' + _command('"${inputs.x}"') + ')'
    closed = build_closed_program(_compile_closed(tmp_path, '(helper true)', params="(x Int)", declarations=declarations))
    (helper,) = closed.tree["definitions"].values()
    (command,) = _commands(closed.tree)
    slot = command["argv_transport"][0]["parts"][0]
    assert slot["kind"] == "slot"
    assert slot["value"]["n"] == helper["params"][0][0]
    assert len(helper["key"]) == 10
    if mode == "inline":
        _assert_inline_homonym_keeps_caller_root(helper, closed)
    else:
        _assert_native_homonym_keeps_typed_parameter(helper, closed)
