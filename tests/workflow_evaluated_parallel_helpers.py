"""Checked artifacts and ordinary memo rows for parallel replay witnesses."""

from contextlib import contextmanager

from orchestrator.workflow.evaluated import effect_inputs
from orchestrator.workflow.evaluated.machine import site_nodes
from orchestrator.workflow.evaluated.memo import reduce_memo
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_command_lifecycle import _publish
from tests.workflow_lisp_closed_program_helpers import build, BOUNDARIES

import json
import hashlib


COMMAND = '(command-result fetch :argv ("python" "probe.py" repo) :returns Int)'


def mapped(body=COMMAND, *, source='(list "a" "b" "c" "d")', label='repo'):
    return (f'(list/map-effect (({label} {source})) :max 4 :parallel 2 '
            f':workspace (string/concat {label} "/work") {body})')


def worker(body, *, result='Int'):
    return f'(defworkflow worker ((repo String)) -> {result} {body})'


@contextmanager
def replay_case(root, body=None, *, declarations='', result='List[Int]', boundaries=BOUNDARIES):
    root.mkdir(parents=True, exist_ok=True)
    (root / 'probe.py').write_text('# immutable implementation\n')
    text = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.37")
        (defmodule parallel) (export run) {declarations}
        (defworkflow run () -> {result} {body or mapped()}))'''
    program = build(root, text, boundaries=boundaries)
    with _publish(root, program) as authority:
        yield authority


def effect(authority, index, *, site=0, indices=None):
    identity, node = list(site_nodes(authority.program).items())[site]
    for ordinal in indices or [index]:
        identity = identity.replace('[*]', f'[{ordinal}]', 1)
    return identity, node


def site_index(authority, *, boundary=None, kind=None):
    for index, node in enumerate(site_nodes(authority.program).values()):
        if boundary is not None and node.get('boundary') == boundary:
            return index
        if kind is not None and node['class'] == kind:
            return index
    raise AssertionError('fixture has no requested effect site')


def command_rows(authority, index, *, site=0, value=None, operand=None, attempt=1, indices=None):
    identity, node = effect(authority, index, site=site, indices=indices)
    operands = ()
    if node['argv']:
        operands = (coerce_evaluated_value(operand or 'abcd'[index], {'kind': 'primitive', 'name': 'String'}),)
    digest = hashlib.sha256(identity.encode()).hexdigest()
    result_path = f'effects/{digest}/attempt-{attempt}/result.json'
    _resolved, parts, implementation = effect_inputs._resolve_effect_input(
        authority, node, operands, identity, authority.run_root.parents[2], None,
        None, None, None, result_path, owner=authority.program.tree['entry'],
        check_command_destinations=False,
    )
    common = dict(identity=identity, attempt=attempt, input_parts=parts,
                  input_digest=canonical_sha256(parts), implementation_files=implementation,
                  result_path=result_path, time=1.0)
    result = index if value is None else value
    start = dict(record='started', **common)
    commit = dict(record='committed', **common, value=result,
                  result_digest=canonical_sha256(result), depends_on=[], effect_class='command')
    return start, commit


def write_rows(authority, rows):
    raw = b''.join(json.dumps(row, separators=(',', ':')).encode() + b'\n' for row in rows)
    authority.run_files.write_atomic('memo.jsonl', raw)
    from orchestrator.workflow.evaluated.machine import site_classes
    return reduce_memo(raw, site_classes(authority.program))


def completed_rows(authority, order=(2, 0, 3, 1)):
    rows = []
    for index in order:
        rows.extend(command_rows(authority, index))
    rows.append(dict(record='terminal', outcome='completed', value=[0, 1, 2, 3]))
    return rows


RUN_REF = '''(run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
    :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
    :policy (:environment :deterministic-effect-free :setup ()))'''


def descriptor_value(descriptor):
    kind = descriptor['kind']
    if kind == 'record':
        return {field['name']: descriptor_value(field['type']) for field in descriptor['fields']}
    if kind == 'list':
        return []
    if kind == 'optional':
        return None
    return {'Int': 0, 'String': '', 'Bool': False, 'Float': 0.0,
            'RunId': 'child-run', 'Value': {}}[descriptor['name']]


def coordinator_rows(authority, index=0, *, site=0):
    from tests.test_workflow_evaluated_memo import _started, _committed, _run_ref_proof
    identity, node = effect(authority, index, site=site)
    value = descriptor_value(node['result'])
    value['value'] = index
    return [_started(identity), _committed(identity, effect_class='run_ref', value=value,
        proof=_run_ref_proof(identity, authority.run_root))]
