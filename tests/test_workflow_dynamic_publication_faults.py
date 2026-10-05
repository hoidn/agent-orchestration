"""Public dynamic state faults retain real command/provider invocation evidence."""

from contextlib import closing
import json

import pytest

from orchestrator.cli.commands.run import run_workflow
from orchestrator.cli.main import create_parser
from orchestrator.state import StateManager
from orchestrator.workflow import workspace_files as files_module
from orchestrator.workflow.dynamic import runtime
from orchestrator.workflow.dynamic.state import DynamicStateError, load_dynamic_view
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_dynamic_interruptions import (
    _env, _events, _state, _tree_snapshot, _write_case,
)
from tests.test_workflow_dynamic_source import write_source


def _service_case(tmp_path, monkeypatch, kind, *, fail_second=False):
    case = _write_case(tmp_path, kind, two_effects=True)
    if kind == 'command':
        calls = [f'(command-result probe :argv ("python" "interrupt_probe.py" "TOKEN_{label}") :returns Int)'
                 for label in ('ONE', 'TWO', 'ONLY')]
        declarations, result = '', 'List[Int]'
    else:
        calls = [f'(provider-result providers.ask :prompt (request :label "TOKEN_{label}") '
                 ':model "fixture-model" :effort "low" :returns String)'
                 for label in ('ONE', 'TWO', 'ONLY')]
        declarations = '(defprompt request (:fills (label :text)) -> String "effect {label}")'
        result = 'List[String]'
        case['args'] = case['args'][:case['args'].index('--input')]
    write_source(tmp_path, 'demo/main',
        f'(export main) {declarations} (defworkflow main () -> {result} (list {" ".join(calls)}))', budget=100)
    if fail_second:
        probe = tmp_path / ('interrupt_probe.py' if kind == 'command' else 'bin/codex')
        probe.write_text(probe.read_text() + '\nif label == "two":\n    raise SystemExit(9)\n')
    control = tmp_path / '.fault-control'
    control.mkdir()
    for name, value in _env(case, control).items():
        if name.startswith('DYNAMIC_TEST_') or name == 'PATH':
            monkeypatch.setenv(name, value)
    monkeypatch.chdir(tmp_path)
    return case, control


def _invoke(case):
    return run_workflow(create_parser().parse_args(case['args']))


def _state_candidate_matches(state, phase):
    rows = state['effects']
    if phase == 'initial':
        return state['status'] == 'running' and not rows
    if phase == 'terminal':
        return state['status'] == 'completed'
    if phase == 'failed-terminal':
        return state['status'] == 'failed'
    if len(rows) != 2:
        return False
    return rows[-1]['status'] == {'start': 'running', 'success': 'completed', 'failure': 'failed'}[phase]


@pytest.mark.parametrize('kind', ['command', 'provider'])
@pytest.mark.parametrize('phase', ['initial', 'start', 'success', 'failure', 'terminal', 'failed-terminal'])
def test_real_dispatch_stops_at_failed_atomic_state_publication(tmp_path, monkeypatch, kind, phase):
    case, control = _service_case(tmp_path, monkeypatch, kind,
                                  fail_second=phase in ('failure', 'failed-terminal'))
    write = WorkspaceFiles.write_atomic
    observed = []

    def fail_state(files, path, content, **kwargs):
        if str(path) != 'state.json' or not files.workspace.is_relative_to(tmp_path):
            return write(files, path, content, **kwargs)
        state = json.loads(content)
        if not _state_candidate_matches(state, phase):
            return write(files, path, content, **kwargs)
        before = _tree_snapshot(files.workspace)
        observed.append((files.workspace, before, state))

        def refuse_replace(*args, **kwargs):
            raise OSError('injected atomic state replacement failure')

        # Fail the real atomic replace, before any new authority is published.
        with monkeypatch.context() as fault:
            fault.setattr(files_module.os, 'replace', refuse_replace)
            return write(files, path, content, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', fail_state)
    result = _invoke(case)
    assert result.exit_code == 1 and result.workflow_outputs is None
    assert len(observed) == 1
    root, before, attempted = observed[0]
    assert result.run_root == root and _tree_snapshot(root) == before
    expected = {'initial': [], 'start': ['one'], 'terminal': ['one', 'two', 'only']}.get(phase, ['one', 'two'])
    assert [row['label'] for row in _events(control)] == expected
    if phase == 'initial':
        assert not (root / 'state.json').exists()
        with pytest.raises(DynamicStateError):
            load_dynamic_view(root)
        return
    state = _state(root)
    assert state['status'] == 'running' and state['workflow_outputs'] is None and state['error'] is None
    assert state['effects'][0]['status'] == 'completed'
    assert (root / state['effects'][0]['result_path']).is_file()
    expected_rows = {'start': ['completed'], 'terminal': ['completed'] * 3,
                     'failed-terminal': ['completed', 'failed']}.get(phase, ['completed', 'running'])
    assert [row['status'] for row in state['effects']] == expected_rows
    assert state['current_effect'] == (2 if phase in ('success', 'failure') else None)
    assert load_dynamic_view(root)['status'] == 'interrupted'
    if phase in ('success', 'failure'):
        assert (root / state['effects'][1]['result_path']).is_file()
        assert attempted['effects'][1]['status'] == ('completed' if phase == 'success' else 'failed')


@pytest.mark.parametrize('kind', ['command', 'provider'])
@pytest.mark.parametrize('failure', ['allocation', 'collision'])
def test_real_dispatch_stops_at_exclusive_attempt_allocation_failure(tmp_path, monkeypatch, kind, failure):
    case, control = _service_case(tmp_path, monkeypatch, kind)
    mkdir = WorkspaceFiles.mkdir_exclusive
    observed = []

    def refuse(files, path):
        if str(path) != 'effects/2' or not files.workspace.is_relative_to(tmp_path):
            return mkdir(files, path)
        if failure == 'collision':
            with closing(mkdir(files, path)) as directory:
                with closing(directory.mkdir_exclusive('attempt-1')) as attempt:
                    attempt.create('result.json', b'99')
        observed.append((files.workspace, _tree_snapshot(files.workspace)))
        if failure == 'allocation':
            raise PermissionError('injected exclusive attempt allocation failure')
        return mkdir(files, path)

    monkeypatch.setattr(WorkspaceFiles, 'mkdir_exclusive', refuse)
    result = _invoke(case)
    assert result.exit_code == 1 and result.workflow_outputs is None
    assert [row['label'] for row in _events(control)] == ['one']
    (root, before), = observed
    assert _tree_snapshot(root) == before
    state = _state(root)
    assert state['status'] == 'running' and state['current_effect'] == 2
    assert [row['status'] for row in state['effects']] == ['completed', 'running']
    assert state['workflow_outputs'] is state['error'] is None
    assert (root / state['effects'][0]['result_path']).is_file()
    assert load_dynamic_view(root)['status'] == 'interrupted'


@pytest.mark.parametrize('kind', ['command', 'provider'])
def test_run_root_collision_dispatches_nothing_and_never_adopts_files(tmp_path, monkeypatch, kind):
    case, control = _service_case(tmp_path, monkeypatch, kind)
    root = tmp_path / '.orchestrate/runs/collision'
    root.mkdir(parents=True)
    (root / 'state.json').write_text('{"unrelated":"PRIVATE"}')
    before = _tree_snapshot(root)
    monkeypatch.setattr(StateManager, 'new_run_id', lambda: 'collision')
    result = _invoke(case)
    assert result.exit_code == 1 and result.workflow_outputs is None
    assert _events(control) == [] and _tree_snapshot(root) == before


@pytest.mark.parametrize('kind', ['command', 'provider'])
@pytest.mark.parametrize('replacement', ['attempt', 'run-root'])
def test_actual_shared_result_is_not_adopted_after_retained_owner_replacement(tmp_path, monkeypatch, kind, replacement):
    case, control = _service_case(tmp_path, monkeypatch, kind)
    name = 'perform_' + kind
    perform = getattr(runtime, name)
    mutations = []

    def replace_after_shared_performance(*args, **kwargs):
        result = perform(*args, **kwargs)
        attempt = kwargs['attempt_files'].workspace
        if attempt.parent.name == '2':
            prefix = attempt.parents[2] / 'effects/1'
            prefix_before = _tree_snapshot(prefix)
            target = attempt if replacement == 'attempt' else attempt.parents[2]
            displaced = target.with_name(target.name + '.displaced')
            target.rename(displaced)
            target.mkdir()
            (target / 'result.json').write_text('99')
            (target / 'sentinel').write_text('replacement is not authority')
            mutations.append((target, displaced, _tree_snapshot(target), _tree_snapshot(displaced), prefix_before))
        return result

    monkeypatch.setattr(runtime, name, replace_after_shared_performance)
    result = _invoke(case)
    assert result.exit_code == 1 and result.workflow_outputs is None
    assert [row['label'] for row in _events(control)] == ['one', 'two']
    (target, displaced, replacement_tree, original_tree, prefix_before), = mutations
    assert _tree_snapshot(target) == replacement_tree
    assert _tree_snapshot(displaced) == original_tree
    if replacement == 'attempt':
        state = _state(result.run_root)
        assert state['status'] == 'failed' and state['current_effect'] is None
        assert [row['status'] for row in state['effects']] == ['completed', 'failed']
        assert state['error']['code'] == 'dynamic_state_invalid'
        assert state['workflow_outputs'] is None
    else:
        state = _state(displaced)
        assert state['status'] == 'running' and state['current_effect'] == 2
        assert [row['status'] for row in state['effects']] == ['completed', 'running']
        assert not (target / 'state.json').exists()
    retained_result = displaced / ('result.json' if replacement == 'attempt' else state['effects'][0]['result_path'])
    assert retained_result.is_file()
    retained_root = result.run_root if replacement == 'attempt' else displaced
    assert _tree_snapshot(retained_root / 'effects/1') == prefix_before
