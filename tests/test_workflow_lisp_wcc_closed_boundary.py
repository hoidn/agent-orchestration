"""Prepared executable edges close before any final translation or registration."""

from dataclasses import replace

import pytest

from orchestrator.workflow_lisp.closed import build
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.wcc import model as w
from tests.test_workflow_lisp_closed_command_transport import _compile, _command
from tests.test_workflow_lisp_closed_preparation_integrity import _registrations
from tests.workflow_lisp_closed_program_helpers import install


def _provider(tmp_path, *, dependency=False):
    from orchestrator.workflow_lisp.workflows import PromptExtern
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/boundary) (export run)
      (defpath Document :kind relpath :under "docs" :must-exist true)
      (defprompt ask (:fills (message :text) (score :value Int)) -> Int "{message} {score}")
      (defworkflow run ((message String) (score Int) (doc Document)) -> Int
        (provider-result provider :prompt (ask :message message :score score)
          :model "gpt-6-sol" :effort "low" :timeout-sec 3 :delivery :composed)))'''
    if dependency:
        source = source.replace(':prompt (ask :message message :score score)',
            ':prompt prompt :inputs (doc) :returns Int :prompt-dependencies (:required (doc) :position append)')
    path = install(tmp_path, source)
    return compile_typed_program(path, entry_workflow='run', source_roots=(tmp_path,),
        workspace_root=tmp_path, provider_externs={'provider': 'codex'}, command_boundaries={},
        prompt_externs={'prompt': PromptExtern(name='prompt', input_file='inputs/prompt.md')})


def _corrupt_operand(body, position, bad):
    if position == 'list':
        assert isinstance(body, w.WccHalt) and isinstance(body.result, w.WccList)
        return replace(body, result=replace(body.result, items=(bad,)))
    if position == 'case-command-scope':
        assert isinstance(body, w.WccCase)
        return replace(body, arms=(replace(body.arms[0], command_scope=(('root', bad),)), *body.arms[1:]))
    assert isinstance(body, w.WccLet) and isinstance(body.bound_value, w.WccPerform)
    perform = body.bound_value
    payload = dict(perform.operation_payload)
    if position == 'prompt':
        application = payload['prompt_application']
        payload['prompt_application'] = {**application,
            'fills': ({**application['fills'][0], 'value': bad}, *application['fills'][1:])}
    elif position == 'dependency':
        dependency = payload['prompt_dependencies']
        payload['prompt_dependencies'] = replace(dependency,
            rows=(replace(dependency.rows[0], value=bad),))
    elif position == 'policy':
        payload['model'] = bad
    elif position == 'command-input':
        payload['adapter_inputs'] = (('input', bad),)
    elif position == 'transport-slot':
        plan = payload['argv_transport'][0]
        payload['argv_transport'] = [{**plan, 'parts': [{**plan['parts'][0], 'value': bad}]}]
    return replace(body, bound_value=replace(perform, operation_payload=payload))


@pytest.mark.parametrize('position', ['list', 'capture', 'computed-capture', 'closed-argument',
    'prompt', 'dependency', 'policy', 'command-input', 'transport-slot', 'case-command-scope'])
@pytest.mark.parametrize('kind', ['raw', 'opaque'])
def test_raw_or_opaque_operand_refuses_before_final_emission(tmp_path, monkeypatch, position, kind):
    if position in {'prompt', 'dependency', 'policy'}:
        program = _provider(tmp_path, dependency=position == 'dependency')
    elif position in {'capture', 'computed-capture', 'closed-argument'}:
        declaration = '(defproc helper ((fixed Int) (n Int)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('n') + ')'
        declaration += '(defproc invoke ((hook ProcRef[Int -> Int])) -> Int :effects () :lowering inline (hook 1))'
        operand = '(+ 2 3)' if position == 'closed-argument' else '(+ n 1)'
        program = _compile(tmp_path, '(invoke (bind-proc (proc-ref helper) :fixed ' + operand + '))',
            params='(n Int)', declarations=declaration)
    elif position == 'case-command-scope':
        program = _compile(tmp_path, '(match choice ((A a) ' + _command('a.i') + ') ((B b) 0))',
            params='(choice Choice)', declarations='(defunion Choice (A (i Int)) (B))')
    else:
        program = _compile(tmp_path, '(list n)' if position == 'list' else _command('"${inputs.n}"'),
            params='(n Int)', returns='List[Int]' if position == 'list' else 'Int')
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner
    registered = []

    def forbidden(*args, **kwargs):
        pytest.fail('an unclosed operand reached final emission')

    def prepared(callable_def, source, context, **kwargs):
        body, children = prepare(callable_def, source, context, **kwargs)
        if callable_def is program.entry:
            metadata = body.metadata
            bad = program.entry.typed_body.expr
            if kind == 'opaque':
                bad = w.WccOpaqueFrontendValue(metadata=metadata, expr=bad)
            if position == 'capture':
                request = next(iter(children.values()))
                request.captures[0] = replace(request.captures[0], value=bad)
            elif position == 'closed-argument':
                request = next(iter(children.values()))
                request.prepared_closed_values = (bad,)
            elif position == 'computed-capture':
                context.computed_capture_requests_by_alias = {
                    alias: tuple(replace(row, prepared_value=bad) for row in rows)
                    for alias, rows in context.computed_capture_requests_by_alias.items()}
            else:
                body = _corrupt_operand(body, position, bad)
            registered.append(_registrations(owner))
            for name in ('body', 'value', 'desc'):
                monkeypatch.setattr(owner, name, forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    with pytest.raises(ValueError, match='closed|executable|operand|prepared'):
        build._build_with_builder(program, owner)
    assert _registrations(owner) == registered[0]


@pytest.mark.parametrize('mutation', ['unknown-node', 'missing-operand', 'unknown-effect',
    'unknown-field', 'unknown-transport-kind', 'unknown-fill-field'])
def test_malformed_preparation_refuses_before_final_emission(tmp_path, monkeypatch, mutation):
    program = _provider(tmp_path) if mutation == 'unknown-fill-field' else _compile(
        tmp_path, _command('"${inputs.n}"'), params='(n Int)')
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner

    def forbidden(*args, **kwargs):
        pytest.fail('malformed preparation reached final emission')

    def prepared(callable_def, source, context, **kwargs):
        body, children = prepare(callable_def, source, context, **kwargs)
        if callable_def is program.entry:
            perform = body.bound_value
            payload = dict(perform.operation_payload)
            if mutation in {'unknown-node', 'missing-operand'}:
                perform = replace(perform, positional_args=(object() if mutation == 'unknown-node' else None,))
            elif mutation == 'unknown-effect':
                perform = replace(perform, perform_kind='unowned-effect')
            elif mutation == 'unknown-field':
                payload['unexpected'] = program.entry.typed_body.expr
            elif mutation == 'unknown-transport-kind':
                payload['argv_transport'] = [{'kind': 'unowned-plan'}]
            else:
                application = payload['prompt_application']
                payload['prompt_application'] = {**application, 'fills': tuple(
                    {**row, 'unexpected': True} for row in application['fills'])}
            body = replace(body, bound_value=replace(perform, operation_payload=payload))
            for name in ('body', 'value', 'desc'):
                monkeypatch.setattr(owner, name, forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    with pytest.raises(ValueError, match='closed|executable|operand|payload|unknown|unexpected'):
        build._build_with_builder(program, owner)


@pytest.mark.parametrize('mutation', ['unknown-kind', 'unknown-field', 'missing-child', 'nested-raw'])
def test_malformed_capture_wire_refuses_before_final_emission(tmp_path, monkeypatch, mutation):
    declarations = '(defproc helper ((fixed Int) (n Int)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('n') + ')'
    declarations += '(defproc invoke ((hook ProcRef[Int -> Int])) -> Int :effects () :lowering inline (hook 1))'
    program = _compile(tmp_path, '(invoke (bind-proc (proc-ref helper) :fixed (+ n 1)))',
        params='(n Int)', declarations=declarations)
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner
    registered = []

    def forbidden(*args, **kwargs):
        pytest.fail('an unclosed capture wire reached final emission')

    def prepared(callable_def, *args, **kwargs):
        body, children = prepare(callable_def, *args, **kwargs)
        if callable_def is program.entry:
            wire = {'k': 'name', 'n': 'n'}
            if mutation == 'unknown-kind':
                wire['k'] = 'unowned-executable'
            elif mutation == 'unknown-field':
                wire['unexpected'] = {'k': 'name', 'n': 'n'}
            elif mutation == 'missing-child':
                wire = {'k': 'field', 'path': ['n']}
            else:
                wire = {'k': 'field', 'base': program.entry.typed_body.expr, 'path': ['n']}
            request = next(iter(children.values()))
            request.captures[0] = replace(request.captures[0], value=wire)
            registered.append(_registrations(owner))
            for name in ('body', 'value', 'desc'):
                monkeypatch.setattr(owner, name, forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    with pytest.raises(ValueError, match='closed|capture|operand|prepared'):
        build._build_with_builder(program, owner)
    assert _registrations(owner) == registered[0]


@pytest.mark.parametrize('mutation', ['entry', 'nested', 'extra'])
def test_incomplete_child_inventory_refuses_before_final_emission(tmp_path, monkeypatch, mutation):
    declarations = '(defproc helper ((fixed Int) (n Int)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('n') + ')'
    declarations += '(defproc invoke ((hook ProcRef[Int -> Int])) -> Int :effects () :lowering inline (hook 1))'
    program = _compile(tmp_path, '(invoke (bind-proc (proc-ref helper) :fixed (+ n 1)))',
        params='(n Int)', declarations=declarations)
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner

    def forbidden(*args, **kwargs):
        pytest.fail('an incomplete request graph reached final emission')

    def prepared(callable_def, *args, **kwargs):
        body, children = prepare(callable_def, *args, **kwargs)
        if callable_def is program.entry:
            request = next(iter(children.values()))
            if mutation == 'entry':
                children = {}
            elif mutation == 'nested':
                assert request.prepared_children
                request.prepared_children = {}
            else:
                children = {**children, ('unowned-child', 0): request}
            for name in ('body', 'value', 'desc'):
                monkeypatch.setattr(owner, name, forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    with pytest.raises(ValueError, match='prepared child table'):
        build._build_with_builder(program, owner)


def test_instantiated_context_values_and_json_default_data_are_closed():
    from orchestrator.workflow_lisp.closed.context import run_context_value, phase_context_value
    from orchestrator.workflow_lisp.closed.preparation_check import _closed_capture_value

    string = {'kind': 'primitive', 'name': 'String'}
    run_type = {'kind': 'record', 'name': 'RunCtx', 'fields': [
        {'name': name, 'type': string} for name in ('run-id', 'state-root', 'artifact-root')]}
    phase_type = {'kind': 'record', 'name': 'PhaseCtx', 'fields': [
        {'name': 'run', 'type': run_type}, *[
            {'name': name, 'type': string} for name in ('phase-name', 'state-root', 'artifact-root')]]}
    run = run_context_value(run_type)
    _closed_capture_value(run)
    _closed_capture_value(phase_context_value(run, 'review', phase_type))
    _closed_capture_value(phase_context_value({'k': 'field', 'base': {'k': 'name', 'n': 'item'},
        'path': ['run']}, 'review', phase_type))
    _closed_capture_value({'k': 'lit', 'v': {'k': 'json-data', 'items': [None, 1]},
        'type': {'kind': 'primitive', 'name': 'Value'}})


@pytest.mark.parametrize('workflow', [False, True])
def test_prepared_inline_effect_map_and_workflow_emit_without_source_reentry(tmp_path, monkeypatch, workflow):
    from orchestrator.workflow_lisp.wcc import analysis, elaborate, historical
    from orchestrator.contracts.closed_program.program import ClosedProgram

    declarations = '(defproc worker ((n Int)) -> Int :effects ((uses-command echo)) :lowering inline ' + _command('n') + ')'
    declarations += '(defworkflow child ((items List[Int])) -> List[Int] (list/map-effect ((item items)) :max 3 (worker item)))'
    expression = '(call child :items items)' if workflow else '(list/map-effect ((item items)) :max 3 (worker item))'
    program = _compile(tmp_path, expression, params='(items List[Int])',
        declarations=declarations, returns='List[Int]')
    expected = build.build_closed_program(program)
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner
    instantiate = owner._instantiate_call_request
    calls = []

    def forbidden(*args, **kwargs):
        pytest.fail('completed map/workflow preparation reentered source analysis')

    def prepared(callable_def, *args, **kwargs):
        result = prepare(callable_def, *args, **kwargs)
        if callable_def is program.entry:
            monkeypatch.setattr(analysis, '_normalized_inline_procedure_wcc_body', forbidden)
            monkeypatch.setattr(elaborate, '_elaborate_expr_to_body', forbidden)
            monkeypatch.setattr(historical, '_frontend_expr_from_wcc_value', forbidden)
            monkeypatch.setattr(historical, 'substitute_opaque_expression', forbidden)
            monkeypatch.setattr(build, 'elaborate_typed_workflow_body', forbidden)
            monkeypatch.setattr(build, 'normalize_wcc_body_to_anf', forbidden)
            monkeypatch.setattr(owner, '_selected_callable_gap', forbidden)
            monkeypatch.setattr(owner, '_prepare_computed_capture_requests', forbidden)
        return result

    def instantiation(*args, **kwargs):
        calls.append(args[0])
        return instantiate(*args, **kwargs)

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    monkeypatch.setattr(owner, '_instantiate_call_request', instantiation)
    actual = build._build_with_builder(program, owner)
    assert calls
    assert actual.artifact() == expected.artifact()
    assert ClosedProgram.from_artifact(actual.artifact()).artifact() == actual.artifact()


def test_imported_pure_if_has_structured_prepared_values(tmp_path):
    from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
    from tests.test_workflow_lisp_closed_command_transport import _walk_wcc
    from tests.workflow_lisp_closed_program_helpers import BOUNDARIES

    path = install(tmp_path, {
        'entry.orc': '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule entry) (import older :only (choose)) (export run)
          (defworkflow run ((n Int)) -> Int (choose n)))''',
        'older.orc': '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule older) (export choose)
          (defproc choose ((n Int)) -> Int :effects ((uses-command fetch)) :lowering inline
            (command-result fetch :argv ("python" "probe.py" (if (> n 0) (+ n 1) (+ n 2))) :returns Int)))''',
    }, entry_path='entry.orc')
    program = compile_typed_program(path, entry_workflow='run', source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=BOUNDARIES)
    _, children, _ = _prepared_entry(program)
    request = next(iter(children.values()))
    nodes = list(_walk_wcc(request.prepared_body))
    assert not any(isinstance(node, w.WccOpaqueFrontendValue) for node in nodes)
    assert any(isinstance(node, w.WccSelect) for node in nodes)


@pytest.mark.parametrize('dependency', [False, True])
def test_prepared_prompt_payload_emits_without_source_reentry(tmp_path, monkeypatch, dependency):
    from orchestrator.contracts.closed_program.program import ClosedProgram
    from orchestrator.workflow_lisp.closed import command_templates
    from orchestrator.workflow_lisp.wcc import elaborate, historical

    program = _provider(tmp_path, dependency=dependency)
    expected = build.build_closed_program(program)
    owner = build.Builder(program)
    prepare = owner._prepare_command_owner
    visited = []

    def forbidden(*args, **kwargs):
        pytest.fail('completed prompt payload reentered frontend preparation')

    def prepared(callable_def, *args, **kwargs):
        body, children = prepare(callable_def, *args, **kwargs)
        if callable_def is program.entry:
            perform = body.bound_value
            visited.extend(w.perform_payload_values(perform.perform_kind, perform.operation_payload))
            for module, name in ((command_templates, 'prepare_frontend_value'),
                    (elaborate, '_elaborate_expr_to_body'), (build, 'normalize_wcc_body_to_anf'),
                    (historical, '_frontend_expr_from_wcc_value')):
                monkeypatch.setattr(module, name, forbidden)
        return body, children

    monkeypatch.setattr(owner, '_prepare_command_owner', prepared)
    actual = build._build_with_builder(program, owner)
    assert len(visited) == (5 if dependency else 6)
    assert actual.artifact() == expected.artifact()
    assert ClosedProgram.from_artifact(actual.artifact()).artifact() == actual.artifact()


def test_direct_value_translator_has_no_frontend_or_anf_dependencies():
    import ast
    import inspect
    from orchestrator.workflow_lisp.closed import values

    module = ast.parse(inspect.getsource(values))
    imports = [node.module or '' for node in ast.walk(module) if isinstance(node, ast.ImportFrom)]
    assert not any(name.endswith(('expressions', 'wcc.elaborate', 'wcc.anf', 'effects')) for name in imports)
