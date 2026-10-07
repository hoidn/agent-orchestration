"""Real lexical elaboration witnesses for compiler-local command scopes."""

from dataclasses import asdict, fields, is_dataclass, replace
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.lowering.command_control_summary import ControlFacts
from orchestrator.workflow_lisp.procedures import ProcedureCatalog
from orchestrator.workflow_lisp.workflows import WorkflowCatalog, ExternalToolBinding
from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
from orchestrator.workflow_lisp.wcc.anf import normalize_wcc_body_to_anf
from orchestrator.workflow_lisp.wcc.model import WCC_M4_ROUTE_SCHEMA_VERSION, WccLet


def _compile(tmp_path, body, *, params="", returns="Result", declarations="", target="2.35", schema=2):
    path = tmp_path / "entry.orc"
    path.write_text(
        f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") '
        '(defrecord Result (i Int) (s String)) '
        '(defunion Choice (A (i Int)) (B (s String))) '
        + declarations + f' (defworkflow run ({params}) -> {returns} {body}))'
    )
    commands = {"echo": ExternalToolBinding(name="echo", stable_command=("python", "probe.py"))}
    if schema == 1 or target != "2.35":
        from orchestrator.workflow_lisp.compiler import compile_stage3_module

        result = compile_stage3_module(path, entry_workflow="run", workspace_root=tmp_path,
            command_boundaries=commands, lowering_route="legacy" if schema == 1 else "wcc_m4", validate_shared=False)
        program = replace(result.typed_program, entry=result.typed_workflows[-1])
    else:
        program = compile_typed_program(path, entry_workflow="run", workspace_root=tmp_path,
            source_roots=(tmp_path,), command_boundaries=commands)
    entry = program.entry
    inputs = dict(
        owner_name=entry.definition.name, type_env=program.workflow_type_env(entry.definition.name),
        value_env=dict(entry.signature.params),
        workflow_return_types={name: item.signature.return_type_ref for name, item in program.workflows.items()},
        procedure_return_types={name: item.signature.return_type_ref for name, item in program.procedures.items()},
        resolved_procedures_by_name=program.procedures, procedure_type_envs=program.procedure_type_envs,
        route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION, closed_program=True,
    )
    from orchestrator.workflow_lisp.closed.build import Builder

    builder = Builder(program)
    facts = dict(
        signature=entry.signature, type_env=inputs["type_env"], local_type_bindings=inputs["value_env"],
        typed_procedures=program.procedures, workflows_by_name=program.workflows,
        workflow_catalog=WorkflowCatalog(signatures_by_name={name: item.signature for name, item in program.workflows.items()}, definitions_by_name={name: item.definition for name, item in program.workflows.items()}, imported_bundles_by_name={}),
        procedure_catalog=ProcedureCatalog(signatures_by_name={name: item.signature for name, item in program.procedures.items()}, definitions_by_name={name: item.definition for name, item in program.procedures.items()}, call_graph={}),
        procedure_type_envs=program.procedure_type_envs, workflow_name=entry.definition.name,
        procedure_owners=builder.procedure_owners, base_workflow_return_types=builder.workflow_return_types,
    )
    return program, inputs, facts


def _walk(node):
    yield node
    if is_dataclass(node):
        children = (getattr(node, field.name) for field in fields(node))
    elif isinstance(node, dict):
        children = node.values()
    elif isinstance(node, (tuple, list)):
        children = node
    else:
        return
    for child in children:
        yield from _walk(child)


def _capture_rows(expr):
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    return [(let, index, source) for let in _walk(expr) if isinstance(let, LetStarExpr)
        for index, source in enumerate(let.binding_capture_sources) if source is not None]


def _case_arms(body):
    from orchestrator.workflow_lisp.wcc.model import WccCase
    return [arm for case in _walk(body) if isinstance(case, WccCase) for arm in case.arms]


def _assert_variant_arm_roots(case):
    from orchestrator.workflow_lisp.wcc.model import WccNameAtom
    from orchestrator.workflow_lisp.type_env import VariantCaseTypeRef

    for arm in case.arms:
        assert tuple(name for name, _ in arm.command_scope) == ("flag", "same")
        root = arm.command_scope[1][1]
        assert isinstance(root, WccNameAtom)
        assert root.name == "same"
        assert root.metadata.binding_identity == arm.binding_identity
        assert isinstance(root.metadata.type_ref, VariantCaseTypeRef)
        assert root.metadata.type_ref.variant_name == arm.variant_name


def _assert_variant_root_hygiene(annotated):
    from orchestrator.workflow_lisp.wcc.model import WccCase
    from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed

    arm = next(item for item in _walk(annotated) if isinstance(item, WccCase)).arms[0]
    assert _free_names(arm) == {"flag"}
    renamed = _renamed(arm, {"same": "outside", "flag": "outer_flag"})
    assert renamed.binding_name == "same"
    assert tuple(name for name, _ in renamed.command_scope) == ("flag", "same")
    assert tuple(value.name for _, value in renamed.command_scope) == ("outer_flag", "same")
    _assert_captured_variant_binder_renaming(annotated, arm)


def _assert_captured_variant_binder_renaming(annotated, arm):
    from orchestrator.workflow_lisp.wcc.model import WccCase
    from orchestrator.workflow_lisp.wcc.use_site_scope import rename_capturing_binders

    moved, _ = rename_capturing_binders(annotated, live=frozenset({"same"}))
    moved_arm = next(item for item in _walk(moved) if isinstance(item, WccCase)).arms[0]
    assert moved_arm.binding_name != "same"
    assert moved_arm.command_scope[1][0] == "same"
    assert moved_arm.command_scope[1][1].name == moved_arm.binding_name
    assert moved_arm.command_scope[1][1].metadata.binding_identity == arm.binding_identity


def _assert_recorded_elaborations_are_neutral(recorded):
    assert len(recorded) == 2
    assert recorded[0][1] == recorded[1][1]
    for body, saved in recorded:
        assert _without_scopes(body) == saved
        assert all(arm.command_scope is None for arm in _case_arms(body))


def _assert_distinct_scope_outputs(outputs):
    from orchestrator.workflow_lisp.wcc.model import WccCase

    first_arms = [next(item for item in _walk(body) if isinstance(item, WccCase)).arms[0] for body in outputs]
    assert first_arms[0].command_scope is None
    assert first_arms[1].command_scope is not None
    assert _without_scopes(outputs[0]) == _without_scopes(outputs[1])
    assert all(normalize_wcc_body_to_anf(body) == body for body in outputs)


def test_closed_type_lookup_uses_real_sibling_environments(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.lowering import core, command_control_summary as summary

    program, inputs, facts = _compile(
        tmp_path, '(let* ((a (let* ((x 1)) x)) (b (let* ((x "hello")) x))) (record Result :i a :s b))',
    )
    body = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    siblings = [item for item in _walk(body) if isinstance(item, WccLet) and item.metadata.binding_identity is not None and item.metadata.binding_identity.name == "x"]
    assert len(siblings) == 2
    assert siblings[0].metadata.binding_identity == siblings[1].metadata.binding_identity
    assert siblings[0].bound_type_ref != siblings[1].bound_type_ref
    def reject_legacy(*args, **kwargs):
        pytest.fail("closed lexical type lookup reached the partial legacy adapter")
    monkeypatch.setattr(core, "_infer_inline_binding_type", reject_legacy)
    closed = ControlFacts(**facts, closed_program=True,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    for (_, outer), expected in zip(program.entry.typed_body.expr.bindings, siblings, strict=True):
        name, expr = outer.bindings[0]
        actual = summary._binding_control_fact(expr, name=name, facts=closed, local_values={})
        assert actual[2] == expected.bound_type_ref


def _without_scopes(node):
    if is_dataclass(node):
        return (type(node), tuple((field.name, _without_scopes(getattr(node, field.name)))
            for field in fields(node) if field.name != "command_scope"))
    if isinstance(node, dict):
        return tuple((key, _without_scopes(value)) for key, value in node.items())
    if isinstance(node, (tuple, list)):
        return tuple(_without_scopes(value) for value in node)
    return node


def test_surface_arm_certificate_keeps_variant_roots_and_neutral_body(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.wcc.model import WccCase

    program, inputs, facts = _compile(
        tmp_path,
        '(match choice ((A same) (if flag (command-result echo :argv ("python" "probe.py" same.i) :returns Result) (record Result :i 1 :s "a"))) '
        '((B same) (if flag (command-result echo :argv ("python" "probe.py" same.s) :returns Result) (record Result :i 2 :s "b"))))',
        params="(choice Choice) (flag Bool)", target="2.32", schema=1,
    )
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    before = _without_scopes(neutral)
    annotated = elaborate_command_scopes(
        program.entry.typed_body, **inputs, incoming_command_facts=ControlFacts(**facts),
        producer_lowering_schema=program.producer_lowering_schema,
    )
    case = next(item for item in _walk(annotated) if isinstance(item, WccCase))
    _assert_variant_arm_roots(case)
    assert case.arms[0].binding_identity == case.arms[1].binding_identity
    assert _without_scopes(annotated) == before
    assert _without_scopes(neutral) == before
    assert normalize_wcc_body_to_anf(annotated) == annotated


@pytest.mark.parametrize("body,expected", [
    ('(if true (command-result echo :argv ("python" "probe.py" "${inputs.absent}") :returns Result) (record Result :i 1 :s "a"))', ()),
    ('(record Result :i 1 :s "a")', None),
])
def test_empty_reset_is_distinct_from_inheritance_and_placeholders(tmp_path, monkeypatch, body, expected):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.wcc.model import WccCase

    entered = []
    original = CommandScopeContext.arm
    def observe(context, expr, **kwargs):
        result = original(context, expr, **kwargs)
        entered.append(result)
        return result
    monkeypatch.setattr(CommandScopeContext, "arm", observe)
    program, inputs, facts = _compile(tmp_path,
        f'(match choice ((A a) {body}) ((B b) (record Result :i 2 :s "b")))',
        params="(choice Choice)", target="2.32", schema=1)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    case = next(item for item in _walk(annotated) if isinstance(item, WccCase))
    assert case.arms[0].command_scope == expected
    assert case.arms[1].command_scope is None
    if expected == ():
        reset = entered[0][1]
        assert reset.values == reset.operands == reset.control.local_type_bindings == {}
        assert reset.retained_bindings == ()
        assert reset.control.iteration_scope is None
        assert reset.control.workflow_name.startswith("%composition.")
    assert "choice" in entered[1][1].values


def test_bridge_value_match_resets_but_guarded_tail_and_wcc_case_inherit(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.wcc.model import WccCase

    match = '(match choice ((A a) (if flag (command-result echo :argv ("python" "probe.py") :returns Int) 1)) ((B b) 2))'
    loop = '(loop/recur :max 2 :state (loop-state (i Int 0)) :on-exhausted 0 (fn (state) BODY))'
    for index, body in enumerate((match, loop.replace("BODY", f'(let* ((r {match})) (done 0))'), loop.replace("BODY", f'(match choice ((A a) (if flag (done 1) (done 2))) ((B b) (done 3)))'))):
        folder = tmp_path / str(index)
        folder.mkdir()
        program, inputs, facts = _compile(folder, body, params="(choice Choice) (flag Bool)", returns="Int")
        neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
        annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
            incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
        case = next(item for item in _walk(annotated) if isinstance(item, WccCase))
        assert (case.arms[0].command_scope is not None) == (index == 1)
        assert _without_scopes(annotated) == _without_scopes(neutral)
        assert normalize_wcc_body_to_anf(annotated) == annotated


@pytest.mark.parametrize('effectful_second', [False, True])
def test_real_effect_argument_joins_and_anf_temporaries_link_without_source_ids(tmp_path, monkeypatch, effectful_second):
    from orchestrator.workflow_lisp.closed.command_templates import (
        elaborate_command_scopes, continuation_binding_demands, CommandScopeContext,
    )
    from orchestrator.workflow_lisp.wcc.model import WccJoin

    match = '(match choice ((A a) (if flag (command-result echo :argv ("python" "probe.py") :returns Int) 1)) ((B b) 2))'
    second = '(if flag (command-result echo :argv ("python" "probe.py") :returns Bool) false)' if effectful_second else '(if flag true false)'
    body = f'(command-result echo :argv ("python" "probe.py" {match} {second} (if flag true false)) :returns Int)'
    program, inputs, facts = _compile(tmp_path, body, params="(choice Choice) (flag Bool)", returns="Int")
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    linked = set()
    original = CommandScopeContext.binding_demands

    def demand(context, metadata, variants):
        linked.add(metadata.node_id)
        return original(context, metadata, variants)

    monkeypatch.setattr(CommandScopeContext, "binding_demands", demand)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    joins = [item for item in _walk(neutral) if isinstance(item, WccJoin) and item.metadata.binding_identity is None]
    assert joins
    assert {item.metadata.node_id for item in joins} <= linked
    assert any(isinstance(item, WccLet) and "anf" in item.bound_name for item in _walk(neutral))
    assert _without_scopes(annotated) == _without_scopes(neutral)
    assert continuation_binding_demands(annotated) == continuation_binding_demands(neutral)


def test_variant_frames_keep_real_continuation_demands_separate(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE
    from orchestrator.workflow_lisp.expressions import LiteralExpr

    program, inputs, facts = _compile(tmp_path,
        '(match choice ((A same) (let* ((x (if true "chosen" "other")) (reply (request-input x))) '
        '(command-result echo :argv ("python" "probe.py" x) :returns Int))) '
        '((B same) (let* ((x (if true true false))) (command-result echo :argv ("python" "probe.py" x) :returns Int))))',
        params="(choice Choice)", returns="Int")
    observed = []
    original = CommandScopeContext.bind

    def bind(context, expr, **kwargs):
        child = original(context, expr, **kwargs)
        if kwargs["name"] == "x":
            observed.append((kwargs["variants"], kwargs["metadata"],
                context.binding_demands(kwargs["metadata"], kwargs["variants"]), child.values["x"]))
        return child

    monkeypatch.setattr(CommandScopeContext, "bind", bind)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert len(observed) == 2
    assert observed[0][1].scope_id == observed[1][1].scope_id
    assert observed[0][1].binding_identity == observed[1][1].binding_identity
    assert observed[0][2] == (False, False, True)
    assert observed[1][2] == (False, False, False)
    assert isinstance(observed[0][3], LiteralExpr) and observed[0][3].value == "chosen"
    assert observed[1][3] is RUNTIME_REFERENCE
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(program.entry.typed_body, **inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)




def test_suffix_shortcut_does_not_classify_unreached_binding(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.lowering import command_control_summary as summary
    from orchestrator.workflow_lisp.lowering.command_transport_decisions import RUNTIME_REFERENCE

    body = '(let* ((r (command-result echo :argv ("python" "probe.py") :returns Result)) '
    body += '(unused (match choice ((A a) (record Result :i 1 :s "a")) ((B b) (record Result :i 2 :s "b"))))) r)'
    program, inputs, facts = _compile(tmp_path, body, params="(choice Choice)")
    typed = ControlFacts(**facts, closed_program=True,
        workflow_return_types=inputs["workflow_return_types"], procedure_return_types=inputs["procedure_return_types"])
    reached = []
    original = summary._binding_control_fact

    def binding(expr, **kwargs):
        reached.append(kwargs["name"])
        return original(expr, **kwargs)

    monkeypatch.setattr(summary, "_binding_control_fact", binding)
    assert not summary.branch_control_summary(program.entry.typed_body.expr,
        result_type=program.entry.typed_body.type_ref, facts=typed, local_values={})
    assert reached == ["r"]
    reached.clear()
    # Losing one actual projected leaf removes the suffix shortcut.
    original_value = summary._materialized_binding_value
    monkeypatch.setattr(summary, "_materialized_binding_value", lambda *args, **kwargs: {"i": RUNTIME_REFERENCE})
    assert summary.branch_control_summary(program.entry.typed_body.expr,
        result_type=program.entry.typed_body.type_ref, facts=typed, local_values={})
    assert reached == ["r", "unused"]


def test_hygiene_scopes_variant_roots_and_preserves_source_formal(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes

    program, inputs, facts = _compile(tmp_path,
        '(match choice ((A same) (if flag (command-result echo :argv ("python" "probe.py" same.i) :returns Result) '
        '(record Result :i 1 :s "a"))) ((B same) (record Result :i 2 :s "b")))',
        params="(choice Choice) (flag Bool)", target="2.32", schema=1)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    _assert_variant_root_hygiene(annotated)


def test_selected_helper_initial_facts_preserve_erased_workflow_reference(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, CommandScopeContext
    from orchestrator.workflow_lisp.lowering.values import _procedure_signature_local_type_bindings
    from orchestrator.workflow_lisp.workflow_refs import ResolvedWorkflowRef

    program, inputs, facts = _compile(tmp_path, '(pick (workflow-ref leaf) choice flag)',
        params='(choice Choice) (flag Bool)', declarations='''
        (defworkflow leaf ((n Int)) -> Result (record Result :i n :s "leaf"))
        (defproc pick ((runner WorkflowRef[Int -> Result]) (choice Choice) (flag Bool)) -> Result
          :effects ((calls-workflow runner)) :lowering inline
          (match choice ((A same) (if flag (call runner :n same.i) (record Result :i 1 :s "a")))
            ((B same) (record Result :i 2 :s "b"))))''')
    selected = next(item for item in program.procedures.values()
        if item.specialization is not None and item.specialization.workflow_ref_bindings)
    compile_time = dict(selected.specialization.workflow_ref_bindings)
    helper_inputs = {**inputs, 'owner_name': selected.definition.name,
        'type_env': program.procedure_type_envs[selected.definition.name],
        'value_env': _procedure_signature_local_type_bindings(selected),
        'compile_time_bindings': compile_time}
    seen = []
    original = CommandScopeContext.arm

    def arm(context, expr, **kwargs):
        seen.append(context)
        return original(context, expr, **kwargs)

    monkeypatch.setattr(CommandScopeContext, 'arm', arm)
    annotated = elaborate_command_scopes(selected.typed_body, **helper_inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    assert seen
    for context in seen:
        assert isinstance(context.values['runner'], ResolvedWorkflowRef)
        assert context.values['runner'] == compile_time['runner']
        assert 'runner' not in context.operands
    neutral = normalize_wcc_body_to_anf(elaborate_typed_workflow_body(selected.typed_body, **helper_inputs))
    assert _without_scopes(annotated) == _without_scopes(neutral)


def test_distinct_caller_values_leave_neutral_elaboration_untouched(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes, runtime_binding_value
    from orchestrator.workflow_lisp.wcc import elaborate
    from orchestrator.workflow_lisp.wcc.model import WccCase
    from orchestrator.workflow_lisp.lowering.values import _resolve_inline_expr_value

    program, inputs, facts = _compile(tmp_path,
        '(match choice ((A same) (let* ((x incoming) (unused (match choice '
        '((A a) (record Result :i 1 :s "a")) ((B b) (record Result :i 2 :s "b"))))) x)) '
        '((B same) incoming))', params='(choice Choice) (incoming Result)', target='2.32', schema=1,
        declarations='(defworkflow constant () -> Result (record Result :i 7 :s "constant"))')
    typed = ControlFacts(**facts)
    runtime = runtime_binding_value(inputs['value_env']['incoming'], facts=typed,
        span=program.entry.typed_body.expr.span, form_path=program.entry.typed_body.expr.form_path)
    constant = next(item for item in program.workflows.values() if item.definition.name.endswith('constant'))
    static = _resolve_inline_expr_value(constant.typed_body.expr, local_values={})
    recorded = []
    original = elaborate.elaborate_typed_workflow_body

    def observe(*args, **kwargs):
        body = original(*args, **kwargs)
        if kwargs.get('command_scope_context') is None:
            recorded.append((body, _without_scopes(body)))
        return body

    monkeypatch.setattr(elaborate, 'elaborate_typed_workflow_body', observe)
    outputs = [elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=typed, producer_lowering_schema=program.producer_lowering_schema,
        local_values={'incoming': value}) for value in (runtime, static)]
    _assert_recorded_elaborations_are_neutral(recorded)
    _assert_distinct_scope_outputs(outputs)


def test_absent_command_scope_preserves_legacy_wcc_json(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import elaborate_command_scopes
    from orchestrator.workflow_lisp.wcc.model import WccCase
    from orchestrator.workflow_lisp.build_manifest_io import _json_data

    program, inputs, facts = _compile(tmp_path,
        '(match choice ((A a) (if flag (record Result :i 1 :s "a") (record Result :i 2 :s "b"))) '
        '((B b) (record Result :i 3 :s "c")))', params='(choice Choice) (flag Bool)', target='2.32', schema=1)
    annotated = elaborate_command_scopes(program.entry.typed_body, **inputs,
        incoming_command_facts=ControlFacts(**facts), producer_lowering_schema=program.producer_lowering_schema)
    case = next(item for item in _walk(annotated) if isinstance(item, WccCase))
    assert case.arms[0].command_scope is not None
    encoded = _json_data(case.arms[1])
    assert 'command_scope' not in encoded
    reset = _json_data(replace(case.arms[1], command_scope=()))
    assert reset['command_scope'] == []
