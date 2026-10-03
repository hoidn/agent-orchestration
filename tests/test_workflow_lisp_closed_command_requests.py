"""Closed command request identities, residual interfaces and sharing."""

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from tests.test_workflow_lisp_closed_command_transport import _compile, _command, _commands


def _prepared_entry(program, *, builder=None):
    from orchestrator.workflow_lisp.closed.build import Builder

    builder = Builder(program) if builder is None else builder
    entry = program.entry
    types = program.workflow_type_env(entry.definition.name)
    context = builder.definition_context(canonical=entry.definition.name,
        owner=entry.definition.name, source_program=program, type_env=types,
        node=entry.typed_body, params=entry.definition.params, callable_def=entry)
    body, children = builder._prepare_command_owner(entry, program, context,
        type_env=types, value_env=dict(entry.signature.params))
    return body, children, builder


def test_workflow_context_capture_shape_exists_before_complete_key(tmp_path):
    from unittest.mock import patch
    from tests import test_workflow_lisp_closed_program_context as context_tests

    programs = []
    actual_build = context_tests.build_closed_program

    def observe(program):
        programs.append(program)
        return actual_build(program)

    with patch.object(context_tests, "build_closed_program", observe):
        context_tests.test_compiled_import_keeps_its_native_body_and_explicit_context_route(tmp_path)
    (program,) = programs
    _, children, builder = _prepared_entry(program)
    (request,) = children.values()
    assert len(request.key[7]) == len(request.captures) == 1
    assert request.captures[0].routes[0][0] == "context"
    assert request.captures[0].value is None
    assert request.captures[0].run_ref_producers == ()
    assert request.key[7][0]["type"]["name"] == "consumer::PhaseCtx"
    (native,) = request.prepared_children.values()
    assert native.key[8]["params"][0]["name"] == "producer::PhaseCtx"
    assert builder.definitions == {}


def test_stable_command_descendant_does_not_promote_irrelevant_inline_literal(tmp_path):
    stable = '(command-result echo :argv ("python" "probe.py") :returns Int)'
    declaration = '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) '
    declaration += ':lowering inline ' + stable + ')'
    _, children, _ = _prepared_entry(_compile(tmp_path, '(helper true)', declarations=declaration))
    (request,) = children.values()
    assert request.command_fact_demand is False
    assert request.key[6] == []
    assert len(request.procedure.signature.params) == len(request.argument_indices) == 1
    assert request.arguments is None


def test_stable_command_child_still_makes_its_actual_case_arm_command_bearing(tmp_path):
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface

    stable = '(command-result echo :argv ("python" "probe.py") :returns Int)'
    declarations = '(defunion Choice (A) (B))'
    declarations += '(defproc helper () -> Int :effects ((uses-command echo)) :lowering inline ' + stable + ')'
    match = '(match choice ((A a) (if flag (helper) 1)) ((B b) 0))'
    program = _compile(tmp_path, '(loop/recur :max 1 :state 0 :on-exhausted 0 '
        '(fn (state) (let* ((result ' + match + ')) (done result))))',
        params='(choice Choice) (flag Bool)', declarations=declarations)
    body, children, builder = _prepared_entry(program)
    interfaces = {selector: child.command_interface for selector, child in children.items()}
    bearings = {selector: child.command_bearing for selector, child in children.items()}
    interface = command_interface(body, native_rows=None, command_capture_rows=[],
        child_interfaces=interfaces, child_bearings=bearings,
        call_declaration_identity=lambda call: builder._command_declaration_identity(
            call, program, program.entry.definition.name))
    assert [row for row in interface['decisions'] if row[0] == 'arm'] == [
        ['arm', 0, 'A', 'reset']]


def test_case_subject_command_does_not_count_pure_arms_in_interface_inventory(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed.command_interfaces import command_interface
    from orchestrator.workflow_lisp.wcc.model import WccCase
    from tests.test_workflow_lisp_closed_command_transport import _planned, _walk_wcc

    program = _compile(tmp_path, '(match choice ((A a) 0) ((B b) 0))',
        params='(choice Choice)', declarations='(defunion Choice (A) (B))')
    body, _ = _planned(program)
    (case,) = [node for node in _walk_wcc(body) if isinstance(node, WccCase)]
    _, (command,) = _planned(_compile(tmp_path / 'command',
        '(command-result echo :argv ("python" "probe.py") :returns Int)'))
    # A structural relation gate: an Int command is not an admitted union subject.
    # Both nodes come from real owners; only the traversal relevance is exercised.
    subject_only = replace(case, subject=command,
        arms=tuple(replace(arm, command_scope=()) for arm in case.arms))
    interface = command_interface(subject_only, native_rows=None, command_capture_rows=[],
        child_interfaces={}, call_declaration_identity=lambda call: None)
    assert interface['decisions'] == []


def test_closed_loop_binds_its_demanded_index_only_in_its_body(tmp_path):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    from orchestrator.workflow_lisp.closed.program import ClosedProgram

    body = '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
    body += '(let* ((result ' + _command('"${loop.index}"') + ')) (done result))))'
    closed = build_closed_program(_compile(tmp_path, body))
    (loop,) = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'loop']
    (command,) = _commands(closed.tree)
    assert command['argv_transport'][0]['parts'][0]['value']['n'] == loop['index']
    assert loop['index'] not in {loop['param'], loop['name']}
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def test_checked_loop_relation_counts_owner_before_nested_budget_operand(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.command_check import checked_command_interfaces
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    from orchestrator.workflow_lisp.closed.names import key_type_descriptor

    source = '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
    source += '(let* ((result ' + _command('"${loop.index}"') + ')) (done result))))'
    tree = deepcopy(build_closed_program(_compile(tmp_path, source)).tree)
    (outer,) = [node for node in _ast_nodes(tree['body']) if node['k'] == 'loop']
    # A relation gate over actual closed nodes; effectful budgets are not admitted source.
    outer['budget'] = {'k': 'block', 'body': deepcopy(outer)}
    interface = checked_command_interfaces(tree,
        project_type=lambda descriptor: key_type_descriptor(descriptor, run_ref_signatures={}),
        fail=lambda *args: pytest.fail(str(args)))[tree['entry']]
    choices = [row[3][1][0][1] for row in interface['decisions'] if row[0] == 'arg']
    assert choices == [['loop', 1], ['loop', 0]]


def test_actual_selected_arm_emits_ordered_roots_and_resets_loop_index(tmp_path):
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    match = '(match choice ((A a) (if flag '
    match += _command('"${inputs.a__i}" a.i "${loop.index}"') + ' 1)) ((B b) 2))'
    source = '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
    source += '(let* ((result ' + match + ')) (done result))))'
    closed = build_closed_program(_compile(tmp_path, source,
        params='(choice Choice) (flag Bool)',
        declarations='(defunion Choice (A (i Int)) (B (i Int)))'))
    (case,) = [node for node in _ast_nodes(closed.tree['body']) if node['k'] == 'case']
    first, second = case['arms']
    assert [name for name, _ in first['command_scope']] == ['flag', 'a']
    assert first['command_scope'][1][1]['n'] == first['bind']
    assert 'command_scope' not in second
    parts = _commands(closed.tree)[0]['argv_transport']
    assert parts[0]['parts'][0]['value']['n'] == first['bind']
    assert parts[2]['parts'][0]['kind'] == 'missing'
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree


def _field_certificate_tree(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    match = '(match choice ((A a) (if flag '
    match += _command('"${inputs.r__i}" r.i') + ' 1)) ((B b) 2))'
    source = '(loop/recur :max 1 :state 0 :on-exhausted 0 (fn (state) '
    source += '(let* ((result ' + match + ')) (done result))))'
    tree = deepcopy(build_closed_program(_compile(tmp_path, source,
        params='(choice Choice) (r Pair) (flag Bool) (payload Value)',
        declarations='(defrecord Pair (i Int)) (defunion Choice (A) (B))')).tree)
    (case,) = [node for node in _ast_nodes(tree['body']) if node['k'] == 'case']
    arm = case['arms'][0]
    command = _commands(tree)[0]
    field = deepcopy(command['argv'][1])
    # The certificate grammar admits pure field roots; all descriptors/operands are actual.
    arm['command_scope'] = [['n', field]]
    slot = command['argv_transport'][0]['parts'][0]
    slot['name'], slot['value'] = ['input', 'n', 'n'], deepcopy(field)
    return tree, arm, field


@pytest.mark.parametrize('move_provenance', [False, True])
def test_checked_field_certificate_preserves_origin_without_provenance_authority(tmp_path, move_provenance):
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, program_digest
    from orchestrator.workflow_lisp.closed.sites import assign_sites

    tree, _, field = _field_certificate_tree(tmp_path)
    if move_provenance:
        field['base']['@'] = {'span': 'relocated.orc:1:1', 'form': ['diagnostic']}
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    assert ClosedProgram.from_artifact(altered.artifact()).tree == tree


def test_checked_field_certificate_cannot_follow_rebinding_of_its_base(tmp_path):
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.workflow_lisp.closed.sites import assign_sites

    tree, arm, field = _field_certificate_tree(tmp_path)
    wire = field['base']['n']
    descriptor = dict(tree['params'])[wire]
    value = {'k': 'record', 'type': descriptor,
        'fields': [['i', {'k': 'lit', 'v': 7, 'type': descriptor['fields'][0]['type']}]]}
    arm['body'] = {'k': 'let', 'name': wire, 'value': value, 'body': arm['body']}
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    with pytest.raises(ClosedProgramInvalid, match='command_transport'):
        ClosedProgram.from_artifact(altered.artifact())


@pytest.mark.parametrize('root_kind', ['block', 'data'])
def test_checked_root_origin_handles_local_binders_and_literal_data(tmp_path, root_kind):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.workflow_lisp.closed.sites import assign_sites

    tree, arm, field = _field_certificate_tree(tmp_path)
    root = {'k': 'block', 'body': {'k': 'let', 'name': '%inside', 'value': field,
        'body': {'k': 'halt', 'value': {'k': 'name', 'n': '%inside'}}}}
    if root_kind == 'data':
        root = {'k': 'lit', 'type': dict(tree['params'])['payload'],
            'v': {'k': 'name', 'n': 'data-only', '@': 'literal-data'}}
    arm['command_scope'] = [['n', root]]
    slot = _commands(tree)[0]['argv_transport'][0]['parts'][0]
    slot['value'] = deepcopy(root)
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    assert ClosedProgram.from_artifact(altered.artifact()).tree == tree
    if root_kind == 'data':
        slot['value']['v']['@'] = 'changed-literal-data'
        altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
        with pytest.raises(ClosedProgramInvalid, match='command_transport'):
            ClosedProgram.from_artifact(altered.artifact())


@pytest.mark.parametrize("control", ["join", "loop"])
def test_pure_root_control_target_homonym_preserves_external_value_origin(tmp_path, control):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes, assign_sites

    tree, arm, field = _field_certificate_tree(tmp_path / 'command')
    source = '(loop/recur :max 1 :state 0 :on-exhausted r.i (fn (state) (done r.i)))'
    if control == "join":
        source = '(let* ((result (match choice ((A a) r.i) ((B b) r.i)))) result)'
    pure = build_closed_program(_compile(tmp_path / 'pure', source,
        params='(choice Choice) (r Pair)',
        declarations='(defrecord Pair (i Int)) (defunion Choice (A) (B))'))
    (body,) = [deepcopy(node) for node in _ast_nodes(pure.tree['body']) if node['k'] == control]
    previous, body['name'] = body['name'], field['base']['n']
    for node in _ast_nodes(body):
        if node.get('join') == previous:
            node['join'] = body['name']
    root = {'k': 'block', 'body': body}
    arm['command_scope'] = [['n', root]]
    _commands(tree)[0]['argv_transport'][0]['parts'][0]['value'] = deepcopy(root)
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    valid = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    assert ClosedProgram.from_artifact(valid.artifact()).tree == tree
    wire = field['base']['n']
    descriptor = dict(tree['params'])[wire]
    replacement = {'k': 'record', 'type': descriptor,
        'fields': [['i', {'k': 'lit', 'v': 7, 'type': descriptor['fields'][0]['type']}]]}
    arm['body'] = {'k': 'let', 'name': wire, 'value': replacement, 'body': arm['body']}
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    with pytest.raises(ClosedProgramInvalid, match='command_transport'):
        ClosedProgram.from_artifact(altered.artifact())


def test_actual_private_workflow_command_child_is_prepared_before_its_key(tmp_path):
    declarations = '(defworkflow child ((n Int)) -> Int ' + _command('"${inputs.n}"') + ')'
    program = _compile(tmp_path, '(call child :n n)', params='(n Int)', declarations=declarations)
    closed = build_closed_program(program)
    (child,) = closed.tree['definitions'].values()
    (command,) = _commands(closed.tree)
    assert child['command_params'] == child['key'][8]['command_params'] == [['n', 0]]
    assert len(child['key']) == 10
    assert command['argv_transport'][0]['parts'][0]['value']['n'] == child['params'][0][0]


def test_source_free_checker_rederives_command_decisions_after_consistent_renaming(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes, assign_sites

    declaration = '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) '
    declaration += ':lowering inline ' + _command('flag') + ')'
    closed = build_closed_program(_compile(tmp_path, '(helper true)', declarations=declaration))
    tree = deepcopy(closed.tree)
    (old_name, definition), = tree['definitions'].items()
    definition['key'][9]['command_decisions'][0][1] = 3
    new_name = canonical_callee_name_from_key(definition['key'])
    tree['definitions'] = {new_name: definition}
    for node in _ast_nodes(tree['body']):
        if node.get('k') == 'call' and node['callee'] == old_name:
            node['callee'] = new_name
    sites = assign_sites(tree)
    tree['sites'] = [list(row) for row in sites]
    altered = ClosedProgram(tree=tree, sites=sites, digest=program_digest(tree))
    with pytest.raises(ClosedProgramInvalid, match='command_decisions'):
        ClosedProgram.from_artifact(altered.artifact())


@pytest.mark.parametrize('shadow', ['literal', 'computed'])
def test_native_root_certificate_cannot_follow_a_same_typed_rebinding(tmp_path, shadow):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid, program_digest
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes, assign_sites

    source = '(let* ((computed (+ n 1))) ' + _command('"${inputs.n}"') + ')'
    closed = build_closed_program(_compile(tmp_path, source, params='(n Int)'))
    tree = deepcopy(closed.tree)
    wire, descriptor = tree['params'][0]
    value = {'k': 'lit', 'v': 7, 'type': descriptor}
    if shadow == 'computed':
        value = deepcopy(next(node for node in _ast_nodes(tree['body']) if node['k'] == 'op'))
    tree['body'] = {'k': 'let', 'name': wire, 'value': value, 'body': tree['body']}
    tree['sites'] = [list(row) for row in assign_sites(tree)]
    altered = ClosedProgram(tree=tree, sites=tuple(map(tuple, tree['sites'])), digest=program_digest(tree))
    with pytest.raises(ClosedProgramInvalid, match='command_transport'):
        ClosedProgram.from_artifact(altered.artifact())


def test_native_root_alias_frozen_before_rebinding_remains_available(tmp_path):
    from copy import deepcopy
    from orchestrator.workflow_lisp.closed.program import ClosedProgram, program_digest
    from orchestrator.workflow_lisp.closed.sites import assign_sites

    closed = build_closed_program(_compile(tmp_path, _command('"${inputs.n}"'), params='(n Int)'))
    tree = deepcopy(closed.tree)
    wire, descriptor = tree['params'][0]
    alias = '%preserved-root'
    _commands(tree)[0]['argv_transport'][0]['parts'][0]['value'] = {'k': 'name', 'n': alias}
    shadow = {'k': 'let', 'name': wire, 'value': {'k': 'lit', 'v': 7, 'type': descriptor}, 'body': tree['body']}
    tree['body'] = {'k': 'let', 'name': alias, 'value': {'k': 'name', 'n': wire}, 'body': shadow}
    tree['sites'] = [list(row) for row in assign_sites(tree)]
    altered = ClosedProgram(tree=tree, sites=tuple(map(tuple, tree['sites'])), digest=program_digest(tree))
    assert ClosedProgram.from_artifact(altered.artifact()).tree == tree


def test_provider_relations_visit_actual_fills_before_policy_operands(tmp_path):
    from orchestrator.workflow_lisp.closed.check import _Checker
    from orchestrator.workflow_lisp.closed.command_check import _effect_children
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes, _effect_value_children
    from tests.workflow_lisp_closed_program_helpers import install

    source = '(workflow-lisp (:language "0.1") (:target-dsl "TARGET") '
    source += '(defmodule cp/order) (export run) '
    source += '(defprompt render (:fills (text :text)) -> Int "{text}") '
    source += '(defworkflow run ((text String) (model String)) -> Int '
    source += '(provider-result providers.ask :prompt (render :text text) :model model)))'
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow='cp/order::run',
        source_roots=(tmp_path,), workspace_root=tmp_path,
        command_boundaries={}, provider_externs={'providers.ask': 'reviewer'})
    closed = build_closed_program(typed)
    (provider,) = [node for node in _ast_nodes(closed.tree['body'])
        if node.get('class') == 'provider']
    expected = [provider['prompt']['fills'][0]['value'], *provider['policy'].values()]
    assert _effect_value_children(provider) == expected
    assert _Checker(closed.tree)._effect_children(provider) == expected
    assert _effect_children(provider) == expected


def _assert_native_literal_arguments(closed, type_name, keys):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    assert len(keys) == 1
    assert keys[0][6] == []
    assert keys[0][8]["params"] == [{"kind": "primitive", "name": type_name}]
    calls = [node for node in _ast_nodes(closed.tree["body"]) if node["k"] == "call"]
    expected = {"Bool": [True, False], "String": ["first", "second"]}
    assert [call["args"][0]["v"] for call in calls] == expected[type_name]
    (command,) = _commands(closed.tree)
    assert command["argv_transport"] == [{"kind": "value"}]
    (helper,) = closed.tree["definitions"].values()
    assert command["argv"][0]["n"] == helper["params"][0][0]


@pytest.mark.parametrize("type_name,arguments", [("Bool", ("true", "false")),
    ("String", ('"first"', '"second"'))])
@pytest.mark.parametrize("mode", ["inline", "private-workflow"])
def test_inline_literal_actuals_use_existing_tagged_value_key_rows(tmp_path, type_name, arguments, mode):
    declaration = '(defproc helper ((argument ' + type_name + ')) -> Int '
    declaration += ':effects ((uses-command echo)) :lowering ' + mode + ' ' + _command('argument') + ')'
    program = _compile(tmp_path,
        '(let* ((first (helper ' + arguments[0] + '))) (helper ' + arguments[1] + '))',
        declarations=declaration)
    closed = build_closed_program(program)
    keys = [row["key"] for row in closed.tree["definitions"].values() if row["key"][2] == "helper"]
    if mode == "private-workflow":
        _assert_native_literal_arguments(closed, type_name, keys)
        return
    assert len(keys) == 2
    assert all(any(row[0] == "argument" for row in key[6]) for key in keys)
    assert keys[0][:6] == keys[1][:6]
    assert keys[0][6] != keys[1][6]
    assert all(key[8]["params"] == [] for key in keys)
    assert all(row["params"] == [] for row in closed.tree["definitions"].values())
    assert {command["argv_transport"][0]["parts"][0]["text"]
        for command in _commands(closed.tree)} == ({"True", "False"} if type_name == "Bool" else {"first", "second"})


def test_promoted_parent_reuses_runtime_child_shape_with_final_residual_operands(tmp_path):
    declarations = '(defproc runtime ((flag Bool)) -> Int :effects () :lowering private-workflow (if flag 1 2))'
    declarations += '(defproc helper ((flag Bool)) -> Int :effects ((uses-command echo)) :lowering inline '
    declarations += '(let* ((result ' + _command('flag') + ')) (runtime flag)))'
    program = _compile(tmp_path, '(helper true)', declarations=declarations)
    closed = build_closed_program(program)
    helper = next(row for row in closed.tree["definitions"].values() if row["key"][2] == "helper")
    runtime = next(row for row in closed.tree["definitions"].values() if row["key"][2] == "runtime")
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    (call,) = [node for node in _ast_nodes(helper["body"]) if node.get("k") == "call"]
    assert runtime["key"][6] == []
    assert len(runtime["params"]) == len(call["args"]) == 1
    assert call["args"][0]["k"] == "lit"
    assert call["args"][0]["v"] is True
    assert helper["params"] == []


@pytest.mark.parametrize("mode", ["inline", "private-workflow"])
def test_inline_literal_homonym_inherits_whole_root_while_native_keeps_its_runtime_parameter(tmp_path, mode):
    declarations = '(defproc helper ((x Bool)) -> Int :effects ((uses-command echo)) '
    declarations += ':lowering ' + mode + ' ' + _command('"${inputs.x}"') + ')'
    closed = build_closed_program(_compile(tmp_path, '(helper true)', params="(x Int)", declarations=declarations))
    (helper,) = closed.tree["definitions"].values()
    (command,) = _commands(closed.tree)
    slot = command["argv_transport"][0]["parts"][0]
    assert slot["kind"] == "slot"
    assert slot["value"]["n"] == helper["params"][0][0]
    assert len(helper["key"]) == 10
    if mode == "inline":
        assert helper["key"][6][0][0] == "x"
        assert helper["key"][7][0]["routes"] == [["command-input", "x"]]
        assert helper["params"][0][1]["name"] == "Int"
        assert helper["key"][8]["params"] == []
        assert "command_params" not in helper
        assert closed.tree["command_params"] == [["x", 0]]
    else:
        assert helper["key"][6] == helper["key"][7] == []
        assert helper["params"][0][1]["name"] == "Bool"
        assert helper["command_params"] == helper["key"][8]["command_params"] == [["x", 0]]
        assert "command_params" not in closed.tree


@pytest.mark.parametrize("depth", [2, 5])
def test_workflow_diamond_prepares_each_owner_once_and_retains_each_edge(tmp_path, monkeypatch, depth):
    from collections import Counter
    from orchestrator.workflow_lisp.closed.build import Builder
    from orchestrator.workflow_lisp.closed.program import ClosedProgram
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    declarations = '(defworkflow level0 ((input Int)) -> Int ' + _command('"${inputs.input}"') + ')'
    for level in range(1, depth + 1):
        child = 'level' + str(level - 1)
        declarations += '(defworkflow level' + str(level) + ' ((input Int)) -> Int '
        declarations += '(let* ((a (call ' + child + ' :input input)) '
        declarations += '(b (call ' + child + ' :input a))) (+ a b)))'
    prepared = Counter()
    original = Builder._prepare_command_workflow

    def observe(builder, workflow, source_program, captures):
        prepared[workflow.definition.name] += 1
        return original(builder, workflow, source_program, captures)

    monkeypatch.setattr(Builder, '_prepare_command_workflow', observe)
    program = _compile(tmp_path, '(call level' + str(depth) + ' :input input)',
        params='(input Int)', declarations=declarations)
    closed = build_closed_program(program)
    assert prepared == Counter({'cp/transport::level' + str(level): 1 for level in range(depth + 1)})
    assert len(closed.tree['definitions']) == depth + 1
    for row in closed.tree['definitions'].values():
        children = [decision for decision in row['key'][9]['command_decisions'] if decision[0] == 'call']
        calls = [node for node in _ast_nodes(row['body']) if node['k'] == 'call']
        assert len(children) == len(calls)
        assert len(children) == (0 if row['key'][2] == 'level0' else 2)
    assert ClosedProgram.from_artifact(closed.artifact()).tree == closed.tree
