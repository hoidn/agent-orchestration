"""Adversarial mutations of publicly compiled parallel programs."""
from copy import deepcopy
import json

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram, ClosedProgramInvalid
from orchestrator.contracts.closed_program.sites import _ast_nodes
from tests.test_workflow_lisp_parallel_map_closed import checked, MAP, COMMAND, source


def refuse(tree):
    with pytest.raises(ClosedProgramInvalid) as error:
        ClosedProgram.from_artifact(json.dumps(tree))
    return error.value.rule


@pytest.mark.parametrize('field,value', [
    ('max', 0), ('max', -1), ('max', True), ('max', 1.5),
    ('parallel', 0), ('parallel', -1), ('parallel', True), ('parallel', '2'),
    ('binder', None), ('binder', ''), ('binder', 'bad/name'),
    ('item_type', {'kind': 'primitive', 'name': 'Int'}),
    ('result', {'kind': 'primitive', 'name': 'String'}),
    ('body', None), ('label', 3), ('index', 'repo'),
])
def test_refuse_malformed_parallel_control(tmp_path, field, value):
    program = checked(tmp_path, source(MAP))
    tree = deepcopy(program.tree)
    tree['body'][field] = value
    assert refuse(tree)


@pytest.mark.parametrize('field', ['source', 'workspace', 'body', 'item_type', 'result', 'binder', 'parallel', 'max', 'label'])
def test_refuse_missing_parallel_edges(tmp_path, field):
    tree = deepcopy(checked(tmp_path, source(MAP)).tree)
    del tree['body'][field]
    assert refuse(tree) == 'node_shape'


@pytest.mark.parametrize('field', ['source', 'workspace'])
@pytest.mark.parametrize('wrapper', ['block', 'select', 'nested-block', 'effectful-call'])
def test_refuse_hidden_effects_in_parallel_pure_regions(tmp_path, field, wrapper):
    declarations = f'(defworkflow worker ((repo String)) -> Box {COMMAND})'
    mapped = MAP.replace(COMMAND, '(call worker :repo repo)') if wrapper == 'effectful-call' else MAP
    program = checked(tmp_path, source(mapped, declarations=declarations))
    tree = deepcopy(program.tree)
    node = tree['body']
    effect_body = deepcopy(node['body'])
    hidden = {'k': 'block', 'body': effect_body}
    if wrapper == 'nested-block':
        hidden = {'k': 'block', 'body': {'k': 'halt', 'value': hidden}}
    if wrapper == 'select':
        hidden = {'k': 'select', 'cond': {'k': 'lit', 'v': True, 'type': {'kind': 'primitive', 'name': 'Bool'}},
            'then': {'prefix': [], 'value': hidden}, 'else': {'prefix': [], 'value': deepcopy(node[field])}}
    node[field] = hidden
    assert refuse(tree) == 'effect_in_value'


@pytest.mark.parametrize('target', ['2.35', '2.36'])
def test_old_target_artifact_refuses_parallel_node(tmp_path, target):
    tree = deepcopy(checked(tmp_path, source(MAP)).tree)
    tree['target'] = target
    assert refuse(tree) == 'target'


def test_refuse_forged_parallel_site_and_annotation_in_pure_workspace(tmp_path):
    program = checked(tmp_path, source(MAP))
    tree = deepcopy(program.tree)
    command = next(n for n in _ast_nodes(tree['body']) if n['k'] == 'perform')
    command['site'] = 'loop:repo[*] / #1'
    tree['sites'] = [[tree['entry'], command['site']]]
    assert refuse(tree) == 'sites'
    tree = deepcopy(program.tree)
    tree['body']['workspace']['body']['value']['site'] = 'forged'
    assert refuse(tree) == 'node_shape'


def test_refuse_forged_call_frame_under_parallel_map(tmp_path):
    declaration = f'(defworkflow worker ((repo String)) -> Box {COMMAND})'
    tree = deepcopy(checked(tmp_path, source(MAP.replace(COMMAND, '(call worker :repo repo)'), declarations=declaration)).tree)
    call = next(n for n in _ast_nodes(tree['body']) if n['k'] == 'call')
    call['frame'] = call['frame'].replace('par-map:repo[*]', 'par-map:other[*]')
    assert refuse(tree) == 'frame_mismatch'
