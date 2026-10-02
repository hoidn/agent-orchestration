"""Finite DC-1c source/closure cases; real leaf cases reuse the DC-1b fixture."""
from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.compiler import compile_stage1_entrypoint, linked_module_type_environment


@pytest.fixture(scope="module")
def type_env(tmp_path_factory):
    root = tmp_path_factory.mktemp("source-types")
    path = root / "types.orc"
    path.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
      (defmodule types) (export Answer)
      (defrecord Answer (accepted Bool)))''')
    return linked_module_type_environment(compile_stage1_entrypoint(path), "types")


def source(body, helpers="", *, inputs="", result="Value", budget=200, effects=""):
    return f'''(dynamic-core (:budget {budget}) (:inputs {inputs})
      (:result {result}) (:effects {effects}) {helpers} (run {body}))'''


def compile_text(text, type_env, path="sample.orc"):
    from experiments.dynamic_core_evaluation.source import compile_source
    return compile_source(text, source_path=path, type_env=type_env)


def execute(text, type_env, inputs=None):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    program = compile_text(text, type_env)
    restored = DynamicProgram.from_artifact(program.artifact())
    return evaluate(restored, inputs or {}).json_value()


def test_S02_one_helper_accepts_integer_and_record(type_env):
    text = source('(list (identity 7) (identity (record (title "draft"))))',
                  '(define (identity x) x)')
    assert execute(text, type_env) == [7, {"title": "draft"}]
    program = compile_text(text, type_env)
    assert len(program.definitions) == 2  # one entry and one authored helper


def test_S03_transitive_capture_and_shadowing(type_env):
    text = source('''(let* ((x 7) (maker (fn () (fn () x))))
                      (let* ((x 90) (f (maker))) (f)))''')
    assert execute(text, type_env) == 7
    assert execute(source('''(let* ((x 7) (f (fn (x) (fn () x))))
                              ((f 9)))'''), type_env) == 9


def test_S04_return_store_pass_and_select_callable(type_env):
    text = source('''(let* ((f (make 40))
                       (chosen (if choose f (fn (x) (- x 1))))
                       (box (record (callbacks (list chosen)))))
                     (apply-one (at (field box "callbacks") 0) 2))''',
                  '(define (make x) (fn (y) (+ x y))) '
                  '(define (apply-one f x) (f x))', inputs='(choose Bool)')
    assert execute(text, type_env, {"choose": True}) == 42
    assert execute(text, type_env, {"choose": False}) == 1


def test_S05_sequential_bindings_lazy_strict_conditions(type_env):
    assert execute(source('(let* ((x 1) (y (+ x 2))) (if true y (1)))'), type_env) == 3
    with pytest.raises(EvaluatedValueError) as error:
        execute(source('(if 1 true false)'), type_env)
    assert error.value.code == 'dynamic_condition_type'


def test_S06_zero_argument_and_collection_forms(type_env):
    assert execute(source('''(list ((fn () 7)) (record) (list)
       (field (record (x 1) ("spaced key" 2)) "spaced key") (at (list 3 4) 1))'''), type_env) == [7, {}, [], 2, 4]


def test_S07_forward_helpers_recursion_and_lexical_scope(type_env):
    helpers = '(define (first x) (second x)) (define (second x) x)'
    assert execute(source('(first 8)', helpers), type_env) == 8
    assert execute(source('(let* ((first (fn (x) (+ x 1)))) (first 8))', helpers), type_env) == 9
    assert execute(source('''(let* ((first (fn (x) (+ x 1)))
        (f (fn (x) (first x)))) (f 8))''', helpers), type_env) == 9
    with pytest.raises(EvaluatedValueError) as error:
        execute(source('(again)', '(define (again) (again))', budget=20), type_env)
    assert error.value.code == 'dynamic_budget_exhausted'
    with pytest.raises(EvaluatedValueError) as error:
        compile_text(source('(hidden)', '(define (hidden) goal)', inputs='(goal String)'), type_env)
    assert error.value.code == 'dynamic_source_invalid'


def test_S08_source_errors_and_dynamic_call_arity(type_env):
    for text in [source('(list ' * 2000 + '0' + ')' * 2000),
                 source('1', result='List[' * 2000 + 'Int' + ']' * 2000)]:
        with pytest.raises(EvaluatedValueError) as nesting:
            compile_text(text, type_env, 'deep.orc')
        assert nesting.value.code == 'dynamic_source_invalid'
        assert nesting.value.location.startswith('deep.orc:')
    for text in [source('(if true 1)'), source('(lambda (x) x)'),
                 source('1', '(define (unreachable) unknown)'), source('(field (record) x)')]:
        with pytest.raises(EvaluatedValueError) as error:
            compile_text(text, type_env, 'bad.orc')
        assert error.value.code == 'dynamic_source_invalid'
        assert 'bad.orc:' in error.value.location
    compile_text(source('((fn (x) x))'), type_env)
    with pytest.raises(EvaluatedValueError) as error:
        execute(source('((fn (x) x))'), type_env)
    assert error.value.code == 'dynamic_call_arity'
    assert execute(source('(if true 1 ((fn (x) x)))'), type_env) == 1


def test_S09_headers_binders_and_duplicate_fields(type_env):
    assert compile_text(source('(effect list (record))', effects='list'), type_env).effects == ('list',)
    good = source('1')
    bad = [good.replace('(:budget 200)', ''),
           good.replace('(:budget 200)', '(:budget true)'),
           good.replace('(:inputs )', '(:effects) (:inputs)'),
           good + ' (run 2)', source('1', '(define (f x x) x)'),
           source('(fn (if) if)'), source('(let* ((x 1) (x 2)) x)'),
           source('(record (x 1) ("x" 2))'), source('(effect unknown (record))'),
           source('1', '(define (f) 1) (define (f) 2)'),
           source('1', inputs='(x Int) (x Int)'), source('1', effects='review review')]
    for text in bad:
        assert text != good
        with pytest.raises(EvaluatedValueError) as error:
            compile_text(text, type_env)
        assert error.value.code == 'dynamic_source_invalid'


def test_S10_existing_schemas_guard_public_boundaries(type_env):
    text = source('answer', inputs='(answer Answer)', result='Answer')
    assert execute(text, type_env, {'answer': {'accepted': True}}) == {'accepted': True}
    with pytest.raises(EvaluatedValueError) as error:
        execute(text, type_env, {'answer': {'accepted': 'true'}})
    assert error.value.code == 'dynamic_boundary_invalid'
    with pytest.raises(EvaluatedValueError) as error:
        execute(source('(fn () 1)'), type_env)
    assert error.value.code == 'dynamic_boundary_invalid'
    from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
    with pytest.raises(LispFrontendCompileError):
        compile_text(source('1', result='Unknown'), type_env)


def test_S11_artifact_identity_ignores_source_layout(type_env):
    text = source('((fn (x) (+ x 1)) 7)')
    first = compile_text(text, type_env, 'first.orc')
    second = compile_text('; comment\n' + text.replace(' ', '\n '), type_env, 'moved.orc')
    assert first.digest == second.digest
    assert first.digest != compile_text(text.replace(' 7)', ' 8)'), type_env).digest


def leaf_program(tmp_path, monkeypatch):
    import shutil
    import sys
    from orchestrator.providers.types import InputMode, ProviderTemplate
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    fixture = Path('experiments/dynamic_core_evaluation/fixtures')
    shutil.copytree(fixture, tmp_path / fixture)
    (tmp_path / 'docs').mkdir()
    (tmp_path / 'docs/goal.txt').write_text('DOC_A: Keep the boundary contracts strict.\n')
    log = tmp_path / 'dispatch.jsonl'
    monkeypatch.setenv('DYNAMIC_CORE_DISPATCH_LOG', str(log))
    provider = ProviderTemplate(name='dynamic-fixture',
        command=[sys.executable, str(tmp_path / fixture / 'scripted_leaf.py'), 'provider'],
        input_mode=InputMode.STDIN)
    bridge = LeafBridge.compile(tmp_path / fixture / 'leaf.orc', tmp_path,
        operations={'review': 'leaf::review', 'annotate': 'leaf::annotate'},
        provider_externs={'providers.review': 'dynamic-fixture'},
        command_boundaries={'annotate': ExternalToolBinding(name='annotate',
            stable_command=('python', str(fixture / 'scripted_leaf.py'), 'command'))},
        provider_templates=(provider,))
    program = compile_text((fixture / 'composition.orc').read_text(), bridge.type_env,
                           str(fixture / 'composition.orc'))
    artifact = tmp_path / 'program.json'
    artifact.write_text(program.artifact())
    restored = DynamicProgram.from_artifact(artifact.read_text())
    assert restored.digest == program.digest
    return restored, bridge, log


def test_S01_authored_specimen_runs_real_provider_then_command(tmp_path, monkeypatch):
    import json
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    program, bridge, log = leaf_program(tmp_path, monkeypatch)
    inputs = {'goal': 'reject draft', 'rubric': 'clarity', 'target_doc': 'docs/goal.txt'}
    result = evaluate(program, inputs, leaf_bridge=bridge).json_value()
    events = [json.loads(line) for line in log.read_text().splitlines()]
    assert [event['mode'] for event in events] == ['provider', 'command']
    assert events[0]['payload']['approved'] is False
    assert result['return__approved'] is True
    assert result['return__feedback'].startswith('reject draft | clarity | ')
    assert 'DOC_A' in result['return__feedback']
    assert result['return__feedback'].endswith(' | draft')
    # The other validated decision really selects the other callable.
    log.unlink()
    approved = evaluate(program, {**inputs, 'goal': 'accept draft'}, leaf_bridge=bridge)
    assert approved.json_value() == {'title': 'draft'}
    assert [json.loads(line)['mode'] for line in log.read_text().splitlines()] == ['provider']


def test_S12_authored_closure_cannot_dispatch_in_read_only_mode(tmp_path, monkeypatch):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram
    _program, bridge, log = leaf_program(tmp_path, monkeypatch)
    text = source('''((fn () (effect review
        (record (goal "reject draft") (rubric "clarity") (target_doc "docs/goal.txt")))))''',
        effects='review annotate')
    program = compile_text(text, bridge.type_env)
    with pytest.raises(EvaluatedValueError) as error:
        evaluate(DynamicProgram.from_artifact(program.artifact()), {}, leaf_bridge=bridge, read_only=True)
    assert error.value.code == 'dynamic_effect_forbidden'
    assert not log.exists()
