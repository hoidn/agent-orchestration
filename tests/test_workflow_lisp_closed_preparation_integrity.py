"""Integrity of completed preparation before keys reuse an emitted definition."""

import pytest

from orchestrator.workflow_lisp.closed.build import Builder
from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
from tests.test_workflow_lisp_closed_command_transport import _compile, _command


@pytest.mark.parametrize("body", [
    '(invoke (bind-proc (proc-ref helper) :fixed (+ 2 3)) n)',
    '(let* ((hook (bind-proc (proc-ref helper) :fixed (+ n 1))) (n 100)) (invoke hook 2))',
    '(invoke (bind-proc (proc-ref forward) :callback (bind-proc (proc-ref helper) :fixed (+ n 1))) 2)',
])
def test_completed_capture_requests_emit_without_frontend_reentry(tmp_path, monkeypatch, body):
    from orchestrator.workflow_lisp.closed import build, command_templates
    from orchestrator.workflow_lisp.wcc import elaborate, anf
    from orchestrator.contracts.closed_program.program import ClosedProgram

    declarations = '(defproc helper ((fixed Int) (y Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += _command('"${inputs.fixed}-${inputs.y}"') + ')'
    declarations += '(defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int :effects () :lowering inline (runner y))'
    declarations += '(defproc forward ((callback ProcRef[Int -> Int]) (y Int)) -> Int :effects () :lowering inline (callback y))'
    program = _compile(tmp_path, body, params='(n Int)', declarations=declarations)
    expected = build.build_closed_program(program)
    owner = Builder(program)
    actual_prepare = owner._prepare_command_owner
    actual_instantiate = owner._instantiate_call_request
    instantiated = []

    def forbidden(*args, **kwargs):
        pytest.fail('completed capture preparation reentered the frontend')

    def instantiate(shape, call, context):
        assert shape.prepared_body is not None and shape.prepared_children is not None
        instantiated.append(shape)
        return actual_instantiate(shape, call, context)

    def prepare(callable_def, *args, **kwargs):
        result = actual_prepare(callable_def, *args, **kwargs)
        if callable_def is program.entry:
            monkeypatch.setattr(owner, '_prepare_computed_capture_requests', forbidden)
            monkeypatch.setattr(owner, '_call_capture_facts', forbidden)
            monkeypatch.setattr(command_templates, 'prepare_frontend_value', forbidden)
            monkeypatch.setattr(elaborate, '_elaborate_expr_to_body', forbidden)
            monkeypatch.setattr(build, 'elaborate_typed_workflow_body', forbidden)
            monkeypatch.setattr(build, 'normalize_wcc_body_to_anf', forbidden)
            monkeypatch.setattr(anf, 'normalize_wcc_body_to_anf', forbidden)
        return result

    monkeypatch.setattr(owner, '_prepare_command_owner', prepare)
    monkeypatch.setattr(owner, '_instantiate_call_request', instantiate)
    actual = build._build_with_builder(program, owner)
    assert instantiated
    assert any(shape.prepared_children == {} for shape in instantiated)
    assert actual.artifact() == expected.artifact()
    assert ClosedProgram.from_artifact(actual.artifact()).artifact() == actual.artifact()


@pytest.mark.parametrize('missing', ['body', 'children', 'recipe', 'capture_maps'])
def test_incomplete_capture_preparation_refuses_without_source_fallback(tmp_path, monkeypatch, missing):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed import build, command_templates

    declarations = '(defproc helper ((fixed Int) (y Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += _command('"${inputs.fixed}-${inputs.y}"') + ')'
    declarations += '(defproc invoke ((runner ProcRef[Int -> Int]) (y Int)) -> Int :effects () :lowering inline (runner y))'
    program = _compile(tmp_path, '(invoke (bind-proc (proc-ref helper) :fixed (+ n 1)) 2)',
        params='(n Int)', declarations=declarations)
    owner = Builder(program)
    actual_prepare = owner._prepare_command_owner

    def forbidden(*args, **kwargs):
        pytest.fail('incomplete preparation attempted a source fallback')

    def prepare(callable_def, source, context, **kwargs):
        body, children = actual_prepare(callable_def, source, context, **kwargs)
        if callable_def is program.entry:
            request = next(iter(children.values()))
            if missing == 'body':
                request.prepared_body = None
            elif missing == 'children':
                request.prepared_children = None
            elif missing == 'capture_maps':
                request.computed_capture_sources = None
            else:
                context.computed_capture_requests_by_alias = {
                    alias: tuple(replace(row, prepared_value=None) for row in rows)
                    for alias, rows in context.computed_capture_requests_by_alias.items()}
            monkeypatch.setattr(owner, '_command_wcc_body', forbidden)
            monkeypatch.setattr(command_templates, 'prepare_frontend_value', forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepare)
    with pytest.raises(ValueError, match='prepared body|prepared value recipe|completed capture preparation'):
        build._build_with_builder(program, owner)


@pytest.mark.parametrize('kind', ['procedure', 'workflow'])
@pytest.mark.parametrize('missing', ['request', 'body', 'children'])
def test_emission_requires_completed_callable_request(tmp_path, monkeypatch, kind, missing):
    from orchestrator.workflow_lisp.closed import build

    declarations = ('(defproc helper ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
        + _command('"${inputs.n}"') + ')') if kind == 'procedure' else '(defworkflow helper ((n Int)) -> Int (+ n 1))'
    body = '(helper n)' if kind == 'procedure' else '(call helper :n n)'
    program = _compile(tmp_path, body, params='(n Int)', declarations=declarations)
    owner = Builder(program)
    actual_install = owner._install_prepared_requests

    def forbidden(*args, **kwargs):
        pytest.fail('incomplete callable attempted source preparation')

    def install(body, context, children):
        if missing != 'request':
            request = next(iter(children.values()))
            setattr(request, 'prepared_body' if missing == 'body' else 'prepared_children', None)
        verify = actual_install(body, context, children)
        if missing == 'request':
            context.prepared_request = None
        monkeypatch.setattr(owner, '_call_request', forbidden)
        monkeypatch.setattr(owner, '_workflow_request', forbidden)
        monkeypatch.setattr(owner, '_workflow_wcc_body', forbidden)
        monkeypatch.setattr(owner, '_command_wcc_body', forbidden)
        return verify

    monkeypatch.setattr(owner, '_install_prepared_requests', install)
    with pytest.raises(ValueError, match='prepared body|completed prepared request'):
        build._build_with_builder(program, owner)


def _program(tmp_path, prefix="prefix-"):
    declaration = '(defproc helper ((n Int)) -> Int :effects ((uses-command echo)) '
    declaration += ':lowering inline ' + _command('"' + prefix + '${inputs.n}"') + ')'
    return _compile(tmp_path, '(helper n)', params='(n Int)', declarations=declaration)


def _registrations(builder):
    return (len(builder.definitions), len(builder.run_ref_producers),
        len(builder.emitted_descriptors), len(builder.generated_result_contract_requests),
        len(builder.boundary_requests), len(builder.nominal_types), builder.opaque_ordinal)


def _forbid_emission(monkeypatch, builder):
    def fail(*args, **kwargs):
        pytest.fail("completed preparation must not translate or register a final body")

    for name in ("body", "value", "desc"):
        monkeypatch.setattr(builder, name, fail)


def _prepare_other_owner(program, shared, monkeypatch, mutate=None):
    selection_owner = Builder(program)
    _forbid_emission(monkeypatch, selection_owner)
    # Each original factory owns selection and preparation. Only completed
    # requests enter the common acceptance owner; no selected map is fabricated.
    monkeypatch.setattr(selection_owner, "_accept_prepared", shared._accept_prepared)
    if mutate is not None:
        actual = selection_owner._command_wcc_body

        def changed(callable_def, source, **kwargs):
            return mutate(actual(callable_def, source, **kwargs), callable_def, source)

        monkeypatch.setattr(selection_owner, '_command_wcc_body', changed)
    return _prepared_entry(program, builder=selection_owner)


def test_same_key_changed_template_fails_at_preparation_completion_before_emission(tmp_path, monkeypatch):
    first_program = _program(tmp_path / "first")
    _, children, builder = _prepared_entry(first_program)
    (first,) = children.values()
    second_program = _program(tmp_path / "second", "different-")
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    with pytest.raises(ValueError, match="contradictory prepared"):
        _, again, _ = _prepare_other_owner(second_program, builder, monkeypatch)
        (second,) = again.values()
        assert second.key == first.key
        assert second.prepared_body.bound_value.operation_payload["argv_transport"] != first.prepared_body.bound_value.operation_payload["argv_transport"]
    assert _registrations(builder) == registrations
    assert first.canonical not in builder.definitions


def _map_body(body, transform):
    from dataclasses import replace
    from orchestrator.workflow_lisp.wcc.model import WccLet, WccHalt, WccListMap

    if isinstance(body, WccLet):
        return replace(body, body=_map_body(body.body, transform))
    assert isinstance(body, WccHalt) and isinstance(body.result, WccListMap)
    return replace(body, result=replace(body.result, body=transform(body.result.body)))


def _copied_capture_bindings(expr, name):
    from dataclasses import replace

    return tuple((binding, replace(value, name=name) if index < len(expr.binding_capture_sources)
        and expr.binding_capture_sources[index] is not None else value)
        for index, (binding, value) in enumerate(expr.bindings))


def _assert_normalized_capture_source(request, helper):
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    from orchestrator.workflow_lisp.wcc.model import WccBlock
    from tests.test_workflow_lisp_command_scopes import _walk

    assert any(isinstance(node, WccBlock) for node in _walk(request.prepared_body))
    assert any(isinstance(node, LetStarExpr) and any(row is not None for row in node.binding_capture_sources)
        for node in _walk(helper.typed_body))


@pytest.mark.parametrize('mode', ['relocated', 'copied-unused', 'retarget'])
def test_real_retained_frontend_capture_row_cannot_retarget_same_typed_input(tmp_path, monkeypatch, mode):
    from dataclasses import replace
    from orchestrator.workflow_lisp.expressions import LetStarExpr
    from orchestrator.workflow_lisp.wcc import elaborate

    declarations = '(defunion Choice (A (i Int)) (B))'
    declarations += '(defworkflow helper ((input Int) (other Int) (choice Choice)) -> Int '
    declarations += '(let* ((out (command-result echo :argv ("python" "probe.py") :returns Int))) '
    declarations += '(let-proc (local ((n Int)) -> Int :captures (input) (+ input n)) '
    declarations += '(let* ((hook (proc-ref local)) (input 100) (answer (hook 1))) answer))))'
    entry = '(call helper :input input :other other :choice choice)'
    first = _compile(tmp_path / 'first', entry, params='(input Int) (other Int) (choice Choice)', declarations=declarations)
    _, children, builder = _prepared_entry(first)
    (request,) = children.values()
    _assert_normalized_capture_source(request, first.workflows['cp/transport::helper'])
    second = _compile(tmp_path / 'second', entry, params='(input Int) (other Int) (choice Choice)', declarations=declarations)
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)

    helper = second.workflows['cp/transport::helper']
    assert dict(helper.signature.params)['input'] == dict(helper.signature.params)['other']
    retained = helper.typed_body.binding_environment['other' if mode == 'retarget' else 'input']
    actual = elaborate._elaborate_expr_to_body
    seen = []

    def mutate(expr, **kwargs):
        if isinstance(expr, LetStarExpr) and any(row is not None for row in expr.binding_capture_sources):
            seen.append(expr.binding_capture_sources)
            rows = tuple(None if row is None else (retained, row[1]) for row in expr.binding_capture_sources)
            bindings = _copied_capture_bindings(expr, 'other') if mode == 'copied-unused' else expr.bindings
            expr = replace(expr, binding_capture_sources=rows, bindings=bindings)
        return actual(expr, **kwargs)

    monkeypatch.setattr(elaborate, '_elaborate_expr_to_body', mutate)
    if mode == 'retarget':
        with pytest.raises(ValueError, match='contradictory prepared'):
            _prepare_other_owner(second, builder, monkeypatch)
    else:
        _prepare_other_owner(second, builder, monkeypatch)
    assert seen and all(row[0].name == "input" for rows in seen for row in rows if row is not None)
    assert _registrations(builder) == registrations


@pytest.mark.parametrize('mode', ['match-alpha', 'let-label'])
def test_prepared_map_body_binders_preserve_scope_and_consumed_labels(tmp_path, monkeypatch, mode):
    from dataclasses import replace
    from orchestrator.workflow_lisp.wcc.hygiene import _renamed
    from orchestrator.workflow_lisp.wcc.model import WccCase, WccLet

    stable = '(command-result echo :argv ("python" "probe.py") :returns Int)'
    inner = '(match item ((A a) a.n) ((B b) b.n))' if mode == 'match-alpha' else '(let* ((n 1)) (+ n 1))'
    declarations = '(defunion Choice (A (n Int)) (B (n Int)))'
    declarations += '(defproc helper ((values List[Choice])) -> List[Int] :effects ((uses-command echo)) :lowering inline '
    declarations += '(let* ((out ' + stable + ')) (list/map ((item values)) ' + inner + ')))'
    first = _compile(tmp_path / 'first', '(helper values)', params='(values List[Choice])', declarations=declarations, returns='List[Int]')
    _, _, builder = _prepared_entry(first)
    second = _compile(tmp_path / 'second', '(helper values)', params='(values List[Choice])', declarations=declarations, returns='List[Int]')

    def transform(expr):
        if mode == 'match-alpha':
            assert isinstance(expr, WccCase)
            arms = tuple(replace(arm, binding_name=arm.binding_name + '_alpha',
                body=_renamed(arm.body, {arm.binding_name: arm.binding_name + '_alpha'})) for arm in expr.arms)
            return replace(expr, arms=arms)
        assert isinstance(expr, WccLet) and expr.metadata.binding_label == 'n'
        return replace(expr, metadata=replace(expr.metadata, binding_label='changed'))

    def mutate(body, call, source):
        return _map_body(body, transform) if call.definition.name.endswith('helper') else body

    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    if mode == 'let-label':
        with pytest.raises(ValueError, match='contradictory prepared'):
            _prepare_other_owner(second, builder, monkeypatch, mutate)
    else:
        _prepare_other_owner(second, builder, monkeypatch, mutate)
    assert _registrations(builder) == registrations
    assert builder.definitions == {}


def test_provenance_only_distinct_owner_preparation_preserves_key_and_registration(tmp_path, monkeypatch):
    _, children, builder = _prepared_entry(_program(tmp_path / "first"))
    (first,) = children.values()
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    _, children, _ = _prepare_other_owner(_program(tmp_path / "relocated"), builder, monkeypatch)
    (second,) = children.values()
    assert second.key == first.key
    assert _registrations(builder) == registrations
    assert len(builder.prepared_by_key) == 1


def test_identical_completed_input_memo_hit_does_not_elaborate_or_compare_again(tmp_path, monkeypatch):
    program = _program(tmp_path)
    _, children, builder = _prepared_entry(program)
    (first,) = children.values()
    actual = builder._command_wcc_body
    _forbid_emission(monkeypatch, builder)

    def guard(callable_def, *args, **kwargs):
        if callable_def.definition.name == first.procedure.definition.name:
            pytest.fail("completed input memo hit elaborated its child again")
        return actual(callable_def, *args, **kwargs)

    def forbid_comparison(*args, **kwargs):
        pytest.fail("completed input memo hit compared its child again")

    monkeypatch.setattr(builder, "_command_wcc_body", guard)
    monkeypatch.setattr(
        "orchestrator.workflow_lisp.closed.preparation_check.assert_same_prepared_body",
        forbid_comparison,
    )
    _, children, _ = _prepared_entry(program, builder=builder)
    (second,) = children.values()
    assert first.prepared_body is not None and second.prepared_body is first.prepared_body
    assert second.prepared_children is first.prepared_children


def _shadow_program(tmp_path):
    body = '(let* ((n (+ n 1)) (out ' + _command('"stable"') + ')) n)'
    declaration = '(defproc helper ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline ' + body + ')'
    return _compile(tmp_path, '(helper n)', params='(n Int)', declarations=declaration)


def _retarget_terminal_identity(body, identity):
    from dataclasses import replace
    from orchestrator.workflow_lisp.wcc.model import WccHalt, WccLet, WccNameAtom

    if isinstance(body, WccLet):
        return replace(body, body=_retarget_terminal_identity(body.body, identity))
    assert isinstance(body, WccHalt) and isinstance(body.result, WccNameAtom)
    assert body.result.metadata.binding_identity != identity
    return replace(body, result=replace(body.result,
        metadata=replace(body.result.metadata, binding_identity=identity)))


def test_same_spelling_old_input_and_shadow_binder_are_distinct_at_acceptance(tmp_path, monkeypatch):
    _, _, builder = _prepared_entry(_shadow_program(tmp_path / 'first'))
    second = _shadow_program(tmp_path / 'second')
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)

    def change(body, callable_def, source):
        if source is second and callable_def.definition.name.endswith('helper'):
            identity = callable_def.typed_body.binding_environment['n']
            return _retarget_terminal_identity(body, identity)
        return body

    with pytest.raises(ValueError, match='contradictory prepared'):
        _prepare_other_owner(second, builder, monkeypatch, change)
    assert _registrations(builder) == registrations


def test_nested_closed_bool_key_is_not_an_int_key(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.preparation_check import _same

    declaration = '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline '
    declaration += _command('"${inputs.flag}"') + ')'
    _, children, _ = _prepared_entry(_compile(tmp_path, '(helper true)', declarations=declaration))
    (request,) = children.values()
    key = deepcopy(request.key)
    assert key[6][0][2]['v'] is True
    key[6][0][2]['v'] = 1
    with pytest.raises(ValueError, match='contradictory prepared'):
        _same(request.key, key, 'key')


def _recipe_program(tmp_path, increment):
    declarations = '(defproc leaf ((fixed Int) (n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += _command('fixed n') + ')'
    declarations += '(defproc invoke ((runner ProcRef[Int -> Int]) (n Int)) -> Int :effects () :lowering inline (runner n))'
    declarations += '(defproc helper ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += f'(invoke (bind-proc (proc-ref leaf) :fixed (+ n {increment})) n))'
    return _compile(tmp_path, '(helper n)', params='(n Int)', declarations=declarations)


def test_same_key_changed_local_computed_creation_recipe_fails_before_emission(tmp_path, monkeypatch):
    _, children, builder = _prepared_entry(_recipe_program(tmp_path / 'first', 1))
    (first,) = children.values()
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    with pytest.raises(ValueError, match='contradictory prepared'):
        _, children, _ = _prepare_other_owner(_recipe_program(tmp_path / 'second', 2), builder, monkeypatch)
        (second,) = children.values()
        assert first.key == second.key
    assert _registrations(builder) == registrations


@pytest.mark.parametrize('depth', [2, 5])
def test_diamond_preparation_and_emission_share_each_completed_input_once(tmp_path, monkeypatch, depth):
    from collections import Counter
    from orchestrator.workflow_lisp.closed.build import _build_with_builder
    from orchestrator.contracts.closed_program.program import ClosedProgram

    declarations = '(defproc level0 ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += _command('"${inputs.n}"') + ')'
    for level in range(1, depth + 1):
        declarations += f'(defproc level{level} ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline '
        declarations += f'(let* ((a (level{level - 1} n)) (b (level{level - 1} n))) (+ a b)))'
    program = _compile(tmp_path, f'(level{depth} n)', params='(n Int)', declarations=declarations)
    builder, prepared, emitted = Builder(program), Counter(), Counter()
    actual_prepare, actual_emit = builder._command_wcc_body, builder._build_procedure

    def prepare(callable_def, *args, **kwargs):
        prepared[callable_def.definition.name] += 1
        return actual_prepare(callable_def, *args, **kwargs)

    def emit(procedure, source, key, canonical, **kwargs):
        emitted[canonical] += 1
        return actual_emit(procedure, source, key, canonical, **kwargs)

    monkeypatch.setattr(builder, '_command_wcc_body', prepare)
    monkeypatch.setattr(builder, '_build_procedure', emit)
    closed = _build_with_builder(program, builder)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert restored.tree == closed.tree
    assert set(emitted.values()) == {1} and len(emitted) == depth + 1
    assert {name: count for name, count in prepared.items() if 'level' in name} == {
        f'cp/transport::level{level}': 1 for level in range(depth + 1)}
    assert len(builder.completed_preparations) == len(builder.prepared_by_key) == depth + 1


def test_original_schema_difference_with_same_projected_body_is_accepted(tmp_path, monkeypatch):
    from dataclasses import replace
    from pathlib import Path
    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    _, children, builder = _prepared_entry(_program(tmp_path / 'schema2'))
    (first,) = children.values()
    second = _program(tmp_path / 'schema1')
    path = Path(second.entry.definition.span.start.path)
    result = compile_stage3_module(path, entry_workflow=second.entry.definition.name,
        workspace_root=tmp_path / 'schema1', command_boundaries={'echo': second.command_boundaries['echo']},
         validate_shared=False)
    assert result.typed_program.producer_lowering_schema == 2
    original = replace(result.typed_program, entry=result.typed_workflows[-1],
        producer_lowering_schema=1)
    assert builder.typed.producer_lowering_schema == 2
    assert original.producer_lowering_schema == 1
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    _, children, _ = _prepare_other_owner(original, builder, monkeypatch)
    (request,) = children.values()
    assert request.key == first.key and request.command_interface == first.command_interface
    assert _registrations(builder) == registrations


def test_irrelevant_inline_actuals_reuse_shape_and_keep_their_final_operands(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed.build import _build_with_builder
    from tests.test_workflow_lisp_closed_command_transport import _ast_nodes

    declaration = '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline '
    declaration += '(command-result echo :argv ("python" "probe.py") :returns Int))'
    program = _compile(tmp_path, '(let* ((first (helper true))) (helper false))', declarations=declaration)
    builder = Builder(program)
    actual, preparations = builder._command_wcc_body, []

    def prepare(callable_def, *args, **kwargs):
        if callable_def.definition.name.endswith('helper'):
            preparations.append(callable_def)
        return actual(callable_def, *args, **kwargs)

    monkeypatch.setattr(builder, '_command_wcc_body', prepare)
    _, children, _ = _prepared_entry(program, builder=builder)
    assert len(preparations) == 1
    left, right = children.values()
    assert left.prepared_body is not None and right.prepared_body is left.prepared_body
    assert right.prepared_children is left.prepared_children
    assert not left.command_fact_demand and not right.command_fact_demand
    assert builder.definitions == {}
    closed = _build_with_builder(program, builder)
    calls = [node for node in _ast_nodes(closed.tree['body']) if node.get('k') == 'call']
    assert [call['args'][0]['v'] for call in calls] == [True, False]
    assert calls[0]['callee'] == calls[1]['callee']
    assert len(preparations) == len(closed.tree['definitions']) == 1


@pytest.mark.parametrize('control', ['join', 'loop'])
def test_relocated_control_parameter_identity_keeps_its_binding_owner(tmp_path, monkeypatch, control):
    stable = '(command-result echo :argv ("python" "probe.py") :returns Int)'
    tail = _command('state')
    if control == 'join':
        body = f'(let* ((state (if flag {stable} n))) {tail})'
    else:
        body = f'(loop/recur :max 1 :state n :on-exhausted 0 (fn (state) (let* ((out {tail})) (done out))))'
    declaration = '(defproc helper ((n Int) (flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline ' + body + ')'
    first = _compile(tmp_path / 'first', '(helper n flag)', params='(n Int) (flag Bool)', declarations=declaration)
    _, children, builder = _prepared_entry(first)
    (original,) = children.values()
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    second = _compile(tmp_path / 'second', '(helper n flag)', params='(n Int) (flag Bool)', declarations=declaration)
    _, children, _ = _prepare_other_owner(second, builder, monkeypatch)
    (relocated,) = children.values()
    assert relocated.key == original.key
    assert _registrations(builder) == registrations


def test_reelaborated_literal_roots_keep_their_current_capture_partition(tmp_path, monkeypatch):
    from dataclasses import replace
    from orchestrator.workflow_lisp.compiler import compile_stage3_module
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    from orchestrator.workflow_lisp.wcc.model import WccNameAtom, WccLiteralAtom
    from tests.test_workflow_lisp_command_scopes import _compile as compile_scoped

    declarations = '(defproc child ((a Int) (b Int)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += '(command-result echo :argv ("python" "probe.py" "${inputs.a}" "${inputs.b}") :returns Int))'
    declarations += '(defproc parent ((a Int) (b Int) (choice Choice) (gate Bool)) -> Int '
    declarations += ':effects ((uses-command echo)) :lowering inline '
    declarations += '(let* ((result (match choice ((A av) (if gate (child a b) 0)) ((B bv) 0)))) result))'
    program, _, _ = compile_scoped(tmp_path, '(let* ((alias 7)) (parent alias alias choice gate))',
        params='(choice Choice) (gate Bool)', returns='Int', declarations=declarations)
    result = compile_stage3_module(tmp_path / 'entry.orc', entry_workflow='run', workspace_root=tmp_path,
        command_boundaries={'echo': ExternalToolBinding(name='echo', stable_command=('python', 'probe.py'), closure=('probe.py',))},
         validate_shared=False)
    program = replace(result.typed_program, entry=result.typed_workflows[-1])
    builder, seen = Builder(program), []
    actual = builder._call_request

    def observe(procedure, source, call, context, **kwargs):
        request = actual(procedure, source, call, context, **kwargs)
        if procedure.definition.name.endswith('::child'):
            memo = builder.completed_preparations
            builder.completed_preparations = {}
            try:
                fresh = actual(procedure, source, call, context, **kwargs)
            finally:
                builder.completed_preparations = memo
            assert all(isinstance(arg, (WccNameAtom, WccLiteralAtom)) for arg in call.args)
            partition = tuple(arg.name if isinstance(arg, WccNameAtom) else arg.value
                for arg in call.args)
            seen.append((partition, request, fresh))
        return request

    monkeypatch.setattr(builder, '_call_request', observe)
    _forbid_emission(monkeypatch, builder)
    _prepared_entry(program, builder=builder)
    assert [partition for partition, _, _ in seen] == [("a", "b"), (7, 7)]
    for _, cached, fresh in seen:
        assert [row.routes for row in cached.captures] == [row.routes for row in fresh.captures]
        assert cached.key == fresh.key


def _control_parameter_use(node, name, identity):
    from dataclasses import fields, is_dataclass, replace
    from orchestrator.workflow_lisp.wcc.model import WccNameAtom

    if isinstance(node, WccNameAtom) and node.name == name:
        return replace(node, metadata=replace(node.metadata, binding_identity=identity))
    if isinstance(node, tuple):
        return tuple(_control_parameter_use(child, name, identity) for child in node)
    if isinstance(node, dict):
        return {key: _control_parameter_use(child, name, identity) for key, child in node.items()}
    if is_dataclass(node):
        return replace(node, **{field.name: _control_parameter_use(getattr(node, field.name), name, identity)
            for field in fields(node) if field.name != 'metadata'})
    return node


@pytest.mark.parametrize('control', ['join', 'loop'])
@pytest.mark.parametrize('retarget', [False, True])
def test_compiled_control_parameter_metadata_identity_uses_its_own_namespace(tmp_path, monkeypatch, control, retarget):
    """Structural WCC gate: ordinary source uses currently omit this metadata."""
    from dataclasses import replace
    from orchestrator.workflow_lisp.wcc.model import WccJoin, WccRecJoin, WccNameAtom
    from tests.test_workflow_lisp_command_scopes import _walk

    stable = '(command-result echo :argv ("python" "probe.py") :returns Int)'
    tail = _command('state')
    if control == 'join':
        body = f'(let* ((state (if flag {stable} n))) {tail})'
        node_type, scope_field = WccJoin, 'continuation'
    else:
        body = f'(loop/recur :max 1 :state n :on-exhausted 0 (fn (state) (let* ((out {tail})) (done out))))'
        node_type, scope_field = WccRecJoin, 'body'
    declaration = '(defproc helper ((n Int) (flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline ' + body + ')'

    def annotate(body, callable_def, source, *, outer=False):
        if not callable_def.definition.name.endswith('helper'):
            return body
        assert isinstance(body, node_type) and len(body.params) == 1
        assert body.metadata.binding_identity is not None
        external = callable_def.typed_body.binding_environment['n']
        assert external != body.metadata.binding_identity
        assert dict(callable_def.signature.params)['n'] == body.params[0].type_ref
        identity = external if outer else body.metadata.binding_identity
        scoped = _control_parameter_use(getattr(body, scope_field), body.params[0].name, identity)
        assert any(isinstance(node, WccNameAtom) and node.metadata.binding_identity == identity
            for node in _walk(scoped))
        return replace(body, **{scope_field: scoped})

    first = _compile(tmp_path / 'first', '(helper n flag)', params='(n Int) (flag Bool)', declarations=declaration)
    builder = Builder(first)
    actual = builder._command_wcc_body
    monkeypatch.setattr(builder, '_command_wcc_body', lambda call, source, **kwargs:
        annotate(actual(call, source, **kwargs), call, source))
    _prepared_entry(first, builder=builder)
    registrations = _registrations(builder)
    _forbid_emission(monkeypatch, builder)
    second = _compile(tmp_path / 'second', '(helper n flag)', params='(n Int) (flag Bool)', declarations=declaration)
    change = lambda body, call, source: annotate(body, call, source, outer=retarget)
    if retarget:
        with pytest.raises(ValueError, match='contradictory prepared'):
            _prepare_other_owner(second, builder, monkeypatch, change)
    else:
        _prepare_other_owner(second, builder, monkeypatch, change)
    assert _registrations(builder) == registrations


@pytest.mark.parametrize('mutation', ['name', 'producer', 'phantom-producer', 'signature', 'field-value'])
def test_reused_carrier_record_keeps_its_local_nominal_and_run_ref_owner(tmp_path, monkeypatch, mutation):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed import preparation_check as check
    from orchestrator.workflow_lisp.closed.names import CanonicalNameError
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    from orchestrator.workflow_lisp.type_env import UnionTypeRef
    from tests.test_workflow_lisp_closed_program_effects import _CARRIER_RUN_REF_SOURCE
    from tests.workflow_lisp_closed_program_helpers import build

    actual = getattr(check._Comparison, 'WccRecordAtom', check._Comparison.record)
    seen = []

    def retarget(self, left, right, frame, path):
        if left.type_name != right.type_name and not seen:
            seen.append((left, right))
            if mutation == 'name':
                left = replace(left, type_name='forged-carrier-name')
            elif mutation == 'producer':
                left = replace(left, resolved_type=right.resolved_type)
            elif mutation == 'phantom-producer':
                # Keep the local carrier spelling while replacing its concrete producer.
                foreign = replace(right.resolved_type, name=left.resolved_type.name)
                left = replace(left, type_name=foreign.name, resolved_type=foreign)
            elif mutation == 'signature':
                carrier = left.resolved_type
                payload = carrier.field_types['payload']
                assert isinstance(payload, UnionTypeRef) and len(payload.type_args) == 1
                result = payload.type_args[0]
                origin, inputs = result.run_ref_origin
                changed = replace(result, run_ref_origin=(origin, (('forged-input', inputs[0][1]),)))
                phantom = replace(payload, type_args=(changed,))
                forged = replace(carrier, field_types={**carrier.field_types, 'payload': phantom})
                left = replace(left, resolved_type=forged)
            else:
                name, value = left.fields[0]
                left = replace(left, fields=((name, replace(value, name='missing-source')), *left.fields[1:]))
        return actual(self, left, right, frame, path)

    monkeypatch.setattr(check._Comparison, 'WccRecordAtom', retarget, raising=False)
    expected = ('canonical identity is missing owner facts'
        if mutation in {'phantom-producer', 'signature'} else 'contradictory prepared')
    with pytest.raises(LispFrontendCompileError, match=expected) as exc:
        build(tmp_path, _CARRIER_RUN_REF_SOURCE, boundaries={}, providers={}, prompts={})
    diagnostic = exc.value.diagnostics[0]
    assert diagnostic.code == 'compiler_defect'
    assert isinstance(diagnostic.cause, CanonicalNameError if mutation in {'phantom-producer', 'signature'} else ValueError)
    assert len(seen) == 1
