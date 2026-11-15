from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow_lisp.closed.names import canonical_callee_name_from_key
from orchestrator.workflow_lisp.closed.program import ClosedProgram, ClosedProgramInvalid
from tests.test_workflow_lisp_closed_program_check import INT, _halt, _tree
from tests.test_workflow_lisp_closed_program_elaboration import _GENERIC_PHASE_TARGET_SOURCE
from tests.workflow_lisp_closed_program_helpers import build


def _source(helper: bool = False) -> str:
    source = _GENERIC_PHASE_TARGET_SOURCE
    if helper:
        source = source.replace(
            '(defworkflow run',
            '''(defworkflow target ((ctx PhaseCtx)) -> WorkReportTarget
    (with-phase ctx implementation (phase-target execution-report)))
  (defworkflow run''',
        )
        source = source.rsplit('(with-phase ctx implementation (phase-target execution-report))', 1)
        source = '(call target :ctx ctx)'.join(source)
    # Carry a public context explicitly; a PhaseCtx entry parameter is hidden.
    source = source.replace(
        '(defworkflow run ((ctx PhaseCtx))',
        '(defrecord Request (ctx PhaseCtx))\n  (defworkflow run ((request Request))',
    )
    return source.replace('(call target :ctx ctx)', '(call target :ctx request.ctx)') if helper else source.replace(
        '(with-phase ctx implementation', '(with-phase request.ctx implementation',
    )


def _context(base: str = 'artifacts/work') -> dict:
    return {
        'run': {'run-id': 'run', 'state-root': 'state/run', 'artifact-root': 'artifacts/run'},
        'phase-name': 'implementation', 'state-root': 'state/run', 'artifact-root': base,
    }


@pytest.mark.parametrize('helper', [False, True], ids=['entry', 'workflow-call'])
def test_generic_phase_target_build_readback_and_runtime(tmp_path: Path, helper: bool) -> None:
    program = build(tmp_path, _source(helper), boundaries={}, providers={}, prompts={})
    restored = ClosedProgram.from_artifact(program.artifact())
    assert restored.digest == program.digest
    result = evaluate_closed_program(restored, {'request': {'ctx': _context()}})
    assert result.json_value() == 'artifacts/work/implementation/execution-report.md'
    assert result.descriptor == restored.tree['result']
    assert result.descriptor['under'] == 'artifacts/work'


@pytest.mark.parametrize(('base', 'error_code'), [
    ('artifacts', 'path_join_under_escape'),
    ('artifacts/work-extra', 'path_join_under_escape'),
    ('/artifacts/work', 'pure_expr_operand_type_mismatch'),
    ('artifacts/work/../work', 'pure_expr_operand_type_mismatch'),
])
def test_generic_phase_target_refuses_invalid_runtime_base(tmp_path: Path, base: str, error_code: str) -> None:
    program = ClosedProgram.from_artifact(build(
        tmp_path, _source(), boundaries={}, providers={}, prompts={},
    ).artifact())
    dispatched = []
    with pytest.raises((EvaluatedValueError, PureExprEvaluationError)) as excinfo:
        evaluate_closed_program(program, {'request': {'ctx': _context(base)}}, effect_handler=lambda *args: dispatched.append(args))
    assert excinfo.value.code == error_code
    assert dispatched == []


def test_original_hidden_phase_context_source_builds_and_reads_back(tmp_path: Path) -> None:
    program = build(tmp_path, _GENERIC_PHASE_TARGET_SOURCE, boundaries={}, providers={}, prompts={})
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


ROOT = {'kind': 'path', 'name': 'sample::Root', 'under': 'artifacts', 'must_exist_target': False}
TARGET = {'kind': 'path', 'name': 'sample::Target', 'under': 'artifacts/work', 'must_exist_target': False}
STRING = {'kind': 'primitive', 'name': 'String'}


def _path_join(base_type: dict, child: str = 'implementation/execution-report.md') -> dict:
    return {
        'k': 'path_join',
        'base': {'k': 'lit', 'v': 'artifacts/work', 'type': deepcopy(base_type)},
        'child': {'k': 'lit', 'v': child, 'type': deepcopy(STRING)},
        'type': deepcopy(TARGET),
    }


def _artifact(base_type: dict, *, key: bool = False) -> str:
    value = _path_join(base_type)
    if key:
        definition_key = ['sample', 'procedure', 'bound', [], [], [],
                          [['path', deepcopy(TARGET), value]], [], {'params': [], 'result': deepcopy(INT)}]
        name = canonical_callee_name_from_key(definition_key)
        tree = _tree()
        tree['definitions'] = {name: {'key': definition_key, 'params': [], 'result': deepcopy(INT), 'body': _halt()}}
    else:
        tree = _tree(_halt(value), result=TARGET)
    tree['types'] = {d['name']: deepcopy(d) for d in [base_type, TARGET] if d['kind'] == 'path'}
    return json.dumps(tree)


@pytest.mark.parametrize('key', [False, True], ids=['body', 'definition-key-closed-value'])
@pytest.mark.parametrize('under', ['artifacts', 'artifacts/work'], ids=['narrowing', 'same-root'])
def test_path_join_artifact_admits_declared_root_narrowing(key: bool, under: str) -> None:
    # Independent checked artifacts exercise the ClosedValue key guard directly.
    program = ClosedProgram.from_artifact(_artifact({**ROOT, 'under': under}, key=key))
    assert program.digest


@pytest.mark.parametrize('key', [False, True], ids=['body', 'definition-key-closed-value'])
@pytest.mark.parametrize('under', ['state', 'artifacts/review', 'artifacts/work-extra', 'artifacts/work/subdir'])
def test_path_join_artifact_refuses_disjoint_or_broader_result_root(key: bool, under: str) -> None:
    base = {**ROOT, 'under': under}
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(_artifact(base, key=key))
    assert excinfo.value.rule == ('definition_key' if key else 'path_root')


@pytest.mark.parametrize(('child', 'rule'), [
    ({'k': 'lit', 'v': 7, 'type': INT}, 'type_mismatch'),
    ({'k': 'lit', 'v': '', 'type': STRING}, 'path_child'),
    ({'k': 'lit', 'v': 'phase\\report.md', 'type': STRING}, 'path_child'),
])
def test_path_join_artifact_preserves_literal_string_child_validation(child: dict, rule: str) -> None:
    tree = json.loads(_artifact(ROOT))
    tree['body']['value']['child'] = child
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(json.dumps(tree))
    assert excinfo.value.rule == rule


@pytest.mark.parametrize('key', [False, True], ids=['body', 'definition-key-closed-value'])
def test_path_join_artifact_refuses_non_path_base(key: bool) -> None:
    with pytest.raises(ClosedProgramInvalid) as excinfo:
        ClosedProgram.from_artifact(_artifact(STRING, key=key))
    assert excinfo.value.rule == ('definition_key' if key else 'path_root')


@pytest.mark.parametrize('child', ['../report.md', '/report.md'])
def test_path_join_preserves_runtime_child_escape_guard(child: str) -> None:
    tree = json.loads(_artifact(ROOT))
    tree['body']['value']['child']['v'] = child
    program = ClosedProgram.from_artifact(json.dumps(tree))
    with pytest.raises(EvaluatedValueError) as excinfo:
        evaluate_closed_program(program, {})
    assert excinfo.value.code == 'path_join_under_escape'
