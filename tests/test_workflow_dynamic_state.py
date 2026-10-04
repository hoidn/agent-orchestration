"""Exact fresh authority and transitions; no typed memo or effect dispatch."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path

import pytest

from tests.test_workflow_dynamic_cli import source, args
from orchestrator.cli.commands.dynamic import prepare_dynamic_run
from orchestrator.workflow.workspace_files import WorkspaceFiles


def owner(tmp_path, *, body='(defworkflow main () -> Int 0)'):
    from orchestrator.workflow.dynamic.state import publish_dynamic_run
    path = source(tmp_path, body)
    built, inputs = prepare_dynamic_run(args(path), workflow_path=path, workspace=tmp_path)
    root = tmp_path / 'run-1'
    root.mkdir()
    files = WorkspaceFiles(root)
    run = publish_dynamic_run(files, built.program, run_id=root.name, workflow_file=str(path),
                              workflow_checksum='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(),
                              bound_inputs=inputs, workspace=tmp_path)
    return run, files


def test_exact_initial_authority_and_readonly_liveness(tmp_path):
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    run, files = owner(tmp_path)
    try:
        assert set(run.header) == {'schema_version', 'result_persistence_profile', 'run_id', 'workflow_file',
          'workflow_checksum', 'started_at', 'program_digest', 'input_digest', 'bound_inputs', 'representation',
          'interpreters', 'workspace', 'runtime_pin', 'provenance_digest'}
        assert set(run.state) == {'schema_version', 'result_persistence_profile', 'run_id', 'program_digest',
          'updated_at', 'status', 'steps_used', 'current_effect', 'effects', 'workflow_outputs', 'error'}
        assert not (files.workspace / 'memo.jsonl').exists()
        before = snapshot(tmp_path)
        view = load_dynamic_view(files.workspace)
        assert view['status'] == 'interrupted' and view['resumable'] is False
        assert snapshot(tmp_path) == before
        with pytest.raises(TypeError):
            run.header['run_id'] = 'changed'
    finally:
        files.close()


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*') if p.is_file()}


@pytest.mark.parametrize('body,value', [('(defworkflow main () -> Int 0)', 0),
    ('(defworkflow main () -> Bool false)', False),
    ('(defworkflow main ((value Value :default null)) -> Value value)', None)])
def test_scalar_terminal_result_and_source_free_read(tmp_path, body, value):
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    if value is None:
        body = '(defworkflow main ((value Value)) -> Value value)'
    run, files = owner(tmp_path, body=body) if value is not None else owner_optional(tmp_path)
    try:
        run.complete(value, steps=1)
        for path in tmp_path.rglob('*.orc'):
            path.unlink()
        view = load_dynamic_view(files.workspace)
        assert view['status'] == 'completed'
        assert view['workflow_outputs'] is value
    finally:
        files.close()


def owner_optional(tmp_path):
    # JSON null is an input value, not an authored literal.
    from orchestrator.workflow.dynamic.state import publish_dynamic_run
    path = source(tmp_path, '(defworkflow main ((value Value)) -> Value value)')
    inp = tmp_path / 'input.json'
    inp.write_text('{"value":null}')
    built, inputs = prepare_dynamic_run(args(path, '--input-file', str(inp)), workflow_path=path, workspace=tmp_path)
    root = tmp_path / 'run-1'
    root.mkdir()
    files = WorkspaceFiles(root)
    return publish_dynamic_run(files, built.program, run_id=root.name, workflow_file=str(path),
        workflow_checksum='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(), bound_inputs=inputs, workspace=tmp_path), files


@pytest.mark.parametrize('field,value', [('extra', 1), ('schema_version','3.0'),
    ('result_persistence_profile','evaluated_execution.v1'), ('run_id','wrong'),
    ('program_digest','sha256:'+'0'*64), ('steps_used',True), ('steps_used',1001),
    ('status','interrupted'), ('current_effect',1), ('workflow_outputs',1),
    ('error', {'code':'bad'}), ('effects',[{}])])
def test_invalid_state_never_reconstructs(tmp_path, field, value):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError
    run, files = owner(tmp_path)
    try:
        raw = deepcopy(dict(run.state)); raw[field] = value
        files.write_atomic('state.json', json.dumps(raw).encode())
        before = snapshot(tmp_path)
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
        assert snapshot(tmp_path) == before
    finally: files.close()


@pytest.mark.parametrize('field,value', [('extra',1), ('runtime_pin','bad'),
    ('provenance_digest','sha256:'+'0'*64), ('input_digest','sha256:'+'0'*64),
    ('workflow_checksum','bad'), ('workspace','relative'), ('interpreters',{'python':{}}),
    ('representation','typed/1'), ('bound_inputs',{'extra':1})])
def test_invalid_immutable_pins_refuse(tmp_path, field, value):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError
    run, files = owner(tmp_path)
    try:
        raw = json.loads(files.read("run.json")); raw[field] = value
        files.write_atomic('run.json', json.dumps(raw).encode())
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
    finally: files.close()


def test_missing_state_refuses_and_publication_collision_is_not_adopted(tmp_path):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError, publish_dynamic_run
    run, files = owner(tmp_path)
    try:
        before = files.read('run.json')
        with pytest.raises(FileExistsError):
            publish_dynamic_run(files, run.program, run_id='run-1', workflow_file=run.header['workflow_file'],
                workflow_checksum=run.header['workflow_checksum'], bound_inputs={}, workspace=tmp_path)
        assert files.read('run.json') == before
        files.unlink('state.json')
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
        assert not files.exists('state.json')
    finally: files.close()


def test_failed_state_write_stops_owner_without_changing_inmemory_progress(tmp_path, monkeypatch):
    run, files = owner(tmp_path)
    original = files.read('state.json')
    def fail(*a, **kw): raise OSError('injected publication failure')
    monkeypatch.setattr(files, 'write_atomic', fail)
    with pytest.raises(OSError): run.complete(0, steps=1)
    assert run.state['status'] == 'running' and files.read('state.json') == original
    with pytest.raises(ValueError): run.complete(0, steps=1)
    files.close()


def test_replaced_root_refuses_all_transitions(tmp_path):
    run, files = owner(tmp_path)
    files.workspace.rename(tmp_path / 'old')
    files.workspace.mkdir()
    try:
        with pytest.raises(ValueError): run.complete(0, steps=1)
        assert not list(files.workspace.iterdir())
        assert json.loads((tmp_path / 'old/state.json').read_text())['status'] == 'running'
    finally: files.close()


@pytest.mark.parametrize('operation', ['resume', 'restart', 'invalidate', 'manager'])
@pytest.mark.parametrize('damage', ['none', 'missing-state', 'mixed-state', 'missing-header', 'unknown-profile'])
def test_recovery_refuses_before_any_files_or_locks(tmp_path, monkeypatch, operation, damage):
    run, files = owner(tmp_path)
    root = files.workspace
    if damage == 'missing-state': files.unlink('state.json')
    elif damage == 'missing-header': files.unlink('run.json')
    elif damage == 'mixed-state':
        state = json.loads(files.read('state.json'))
        state['result_persistence_profile'] = 'evaluated_execution.v1'
        files.write_atomic('state.json', json.dumps(state).encode())
    elif damage == 'unknown-profile':
        header = json.loads(files.read('run.json'))
        header['result_persistence_profile'] = 'unknown.v1'
        files.write_atomic('run.json', json.dumps(header).encode())
    monkeypatch.chdir(tmp_path)
    before = snapshot(tmp_path)
    try:
        if operation in {'resume','restart'}:
            from orchestrator.cli.commands.resume import resume_workflow
            assert resume_workflow(root.name, state_dir=str(root.parent), force_restart=operation == 'restart') == 2
        elif operation == 'invalidate':
            from orchestrator.cli.commands.invalidate import invalidate_command
            assert invalidate_command(root.name, 'anything', state_dir=str(root.parent)) == 2
        else:
            from orchestrator.state import StateManager
            manager = StateManager(tmp_path, run_id=root.name, state_dir=root.parent)
            with pytest.raises(ValueError): manager.load()
            manager.close()
        assert snapshot(tmp_path) == before
        assert not (tmp_path / '.orchestrate').exists()
        assert not files.exists('run.lock')
    finally: files.close()


def effect_owner(tmp_path):
    from orchestrator.workflow.dynamic.state import publish_dynamic_run, _effect_nodes
    path = source(tmp_path, '(defworkflow main () -> Int (command-result tool :argv ("python") :returns Int))')
    manifest = tmp_path / 'commands.json'
    manifest.write_text('{"tool":{"kind":"external_tool","stable_command":["python"],"closure":[]}}')
    built, inputs = prepare_dynamic_run(args(path, '--command-boundaries-file', str(manifest)),
                                       workflow_path=path, workspace=tmp_path)
    root = tmp_path / 'run-1'; root.mkdir()
    files = WorkspaceFiles(root)
    run = publish_dynamic_run(files, built.program, run_id=root.name, workflow_file=str(path),
        workflow_checksum='sha256:' + hashlib.sha256(path.read_bytes()).hexdigest(), bound_inputs=inputs, workspace=tmp_path)
    location, (definition, _) = next(iter(_effect_nodes(run.program).items()))
    return run, files, definition, location


def test_effect_order_exclusive_allocation_and_failure_before_terminal(tmp_path):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, EFFECT_FIELDS
    run, files, code, location = effect_owner(tmp_path)
    try:
        row = run.start_effect(code, location, 'command', steps=1)
        assert set(row) == EFFECT_FIELDS and row['ordinal'] == 1
        assert files.exists('effects/1/attempt-1')
        assert row['prompt_path'] is None
        with pytest.raises(ValueError): run.start_effect(code, location, 'command', steps=2)
        files.create(row['result_path'], b'0')
        run.finish_effect(steps=2)
        row2 = run.start_effect(code, location, 'command', steps=3)
        assert row2['ordinal'] == 2
        error = {'code':'controlled_failure', 'message':'safe', 'location': location, 'metadata':{}}
        run.finish_effect(steps=4, error=error)
        assert json.loads(files.read('state.json'))['status'] == 'running'
        run.fail(error, steps=4)
        view = load_dynamic_view(files.workspace)
        assert view['status'] == 'failed' and view['current_effect'] is None
        assert [row['status'] for row in view['effects']] == ['completed', 'failed']
        assert files.read('effects/1/attempt-1/result.json') == b'0'
    finally: files.close()


@pytest.mark.parametrize('field,value', [('ordinal',2), ('ordinal',True), ('definition','wrong'),
    ('location','/definitions/wrong/body'), ('effect_class','provider'), ('status','pending'),
    ('result_path','../outside'), ('stdout_path','effects/1/attempt-2/stdout.txt'),
    ('stderr_path','/tmp/stderr'), ('prompt_path','effects/1/attempt-1/prompt.txt'),
    ('started_at','bad'), ('finished_at','2020-01-01T00:00:00Z'),
    ('error',{'code':'bad'}), ('extra',1)])
def test_effect_row_admission_is_exact(tmp_path, field, value):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError
    run, files, code, location = effect_owner(tmp_path)
    try:
        run.start_effect(code, location, 'command', steps=1)
        state = json.loads(files.read('state.json'))
        state['effects'][0][field] = value
        files.write_atomic('state.json', json.dumps(state).encode())
        before = snapshot(tmp_path)
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
        assert snapshot(tmp_path) == before
    finally: files.close()


@pytest.mark.parametrize('damage', ['two-running', 'current-mismatch', 'completed-active',
    'failed-active', 'completed-failed', 'result-wrong-bool', 'failed-no-error', 'effect-symlink'])
def test_crossfield_effect_terminal_invariants(tmp_path, damage):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError
    run, files, code, location = effect_owner(tmp_path)
    try:
        run.start_effect(code, location, 'command', steps=1)
        state = json.loads(files.read('state.json'))
        if damage == 'two-running':
            row = deepcopy(state['effects'][0]); row['ordinal'] = 2
            for field in ('result_path','stdout_path','stderr_path'): row[field] = row[field].replace('/1/', '/2/')
            state['effects'].append(row); state['current_effect'] = 2
        elif damage == 'current-mismatch': state['current_effect'] = None
        elif damage in {'completed-active','failed-active'}:
            state['status'] = damage.split('-')[0]
            state['workflow_outputs'] = 0 if state['status'] == 'completed' else None
        elif damage == 'effect-symlink':
            files.remove_tree('effects')
            (tmp_path / 'outside').mkdir()
            (files.workspace / 'effects').symlink_to(tmp_path / 'outside', target_is_directory=True)
        else:
            state['current_effect'] = None
            row = state['effects'][0]
            row.update(status='completed', finished_at=state['updated_at'])
            state['status'] = 'completed'; state['workflow_outputs'] = 0
            if damage == 'completed-failed':
                row.update(status='failed', error={'code':'bad','message':'safe','location':location,'metadata':{}})
            elif damage == 'result-wrong-bool': state['workflow_outputs'] = False
            elif damage == 'failed-no-error': state.update(status='failed',workflow_outputs=None,error=None)
        files.write_atomic('state.json', json.dumps(state).encode())
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
    finally: files.close()


@pytest.mark.parametrize('failure', ['collision', 'allocation', 'write'])
def test_start_failure_stops_before_any_later_invocation(tmp_path, monkeypatch, failure):
    run, files, code, location = effect_owner(tmp_path)
    try:
        if failure == 'collision':
            existing = files.mkdir_exclusive('effects/1'); existing.close()
            files.create('effects/1/existing.txt', b'evidence')
        def fail(*a, **kw): raise OSError('injected failure')
        if failure == 'allocation': monkeypatch.setattr(files, 'mkdir_exclusive', fail)
        elif failure == 'write': monkeypatch.setattr(files, 'write_atomic', fail)
        with pytest.raises(OSError): run.start_effect(code, location, 'command', steps=1)
        state = json.loads(files.read('state.json'))
        assert len(state['effects']) == (0 if failure == 'write' else 1)
        assert not files.exists('effects/1/attempt-1')
        with pytest.raises(ValueError): run.start_effect(code, location, 'command', steps=1)
        if failure == 'collision': assert files.read('effects/1/existing.txt') == b'evidence'
    finally: files.close()


def test_completed_state_cannot_transition_or_publish_again(tmp_path):
    run, files = owner(tmp_path)
    try:
        run.complete(0, steps=1)
        before = files.read('state.json')
        with pytest.raises(ValueError): run.complete(0, steps=2)
        assert files.read('state.json') == before
    finally: files.close()


def test_checksum_must_match_captured_program_source_without_reread(tmp_path):
    from orchestrator.workflow.dynamic.state import load_dynamic_view, DynamicStateError
    run, files = owner(tmp_path)
    try:
        header = json.loads(files.read('run.json'))
        header['workflow_checksum'] = 'sha256:' + '0'*64
        files.write_atomic('run.json', json.dumps(header).encode())
        for path in tmp_path.rglob('*.orc'): path.unlink()
        with pytest.raises(DynamicStateError): load_dynamic_view(files.workspace)
    finally: files.close()


def test_reader_pin_validation_never_rereads_runtime_or_executable(tmp_path, monkeypatch):
    from orchestrator.workflow.dynamic import state
    run, files, _, _ = effect_owner(tmp_path)
    def forbidden(*a, **kw): pytest.fail('reader reobserved runtime/interpreter')
    monkeypatch.setattr(state, 'compute_compiler_runtime_identity', forbidden)
    monkeypatch.setattr(state, 'pin_command_interpreter', forbidden)
    try:
        assert state.load_dynamic_view(files.workspace)['status'] == 'interrupted'
    finally: files.close()


def test_pinned_reader_does_not_close_borrowed_file_owner(tmp_path):
    from orchestrator.workflow.dynamic.state import load_dynamic_view
    run, files = owner(tmp_path)
    try:
        assert load_dynamic_view(files.workspace, run_files=files)['resumable'] is False
        os.fstat(files.root_fd)
        assert not files.closed
    finally: files.close()


def test_mixed_typed_header_dynamic_state_refuses_before_workspace_lock(tmp_path, monkeypatch):
    from orchestrator.cli.commands.resume import resume_workflow
    run, files = owner(tmp_path)
    try:
        header = json.loads(files.read('run.json'))
        header.update(schema_version='3.0', result_persistence_profile='evaluated_execution.v1')
        files.write_atomic('run.json', json.dumps(header).encode())
        monkeypatch.chdir(tmp_path)
        before = snapshot(tmp_path)
        assert resume_workflow(files.workspace.name, state_dir=str(tmp_path)) == 2
        assert snapshot(tmp_path) == before and not (tmp_path / '.orchestrate').exists()
    finally: files.close()


@pytest.mark.parametrize('operation', ['resume', 'restart', 'invalidate', 'manager'])
@pytest.mark.parametrize('artifact_schema', ['workflow-lisp/dynamic-program/1', 'workflow-lisp/dynamic-program/unknown'])
def test_visible_dynamic_artifact_with_typed_header_never_writes_locks(tmp_path, monkeypatch, operation, artifact_schema):
    run, files = owner(tmp_path)
    try:
        header = json.loads(files.read('run.json'))
        header.update(schema_version='3.0', result_persistence_profile='evaluated_execution.v1')
        files.write_atomic('run.json', json.dumps(header).encode())
        files.unlink('state.json')
        program = json.loads(files.read('closed_program.json'))
        program['schema'] = artifact_schema
        files.write_atomic('closed_program.json', json.dumps(program).encode())
        monkeypatch.chdir(tmp_path)
        before = {str(p.relative_to(tmp_path)): None if p.is_dir() else p.read_bytes()
                  for p in tmp_path.rglob('*')}
        if operation in {'resume','restart'}:
            from orchestrator.cli.commands.resume import resume_workflow
            assert resume_workflow(files.workspace.name, state_dir=str(tmp_path), force_restart=operation == 'restart') == 2
        elif operation == 'invalidate':
            from orchestrator.cli.commands.invalidate import invalidate_command
            assert invalidate_command(files.workspace.name, 'x', state_dir=str(tmp_path)) == 2
        else:
            from orchestrator.state import StateManager
            manager = StateManager(tmp_path, run_id=files.workspace.name, state_dir=tmp_path)
            with pytest.raises(ValueError): manager.load()
        after = {str(p.relative_to(tmp_path)): None if p.is_dir() else p.read_bytes()
                 for p in tmp_path.rglob('*')}
        assert after == before
    finally: files.close()


def test_reader_error_redacts_runtime_keys_and_preserves_list_index(tmp_path):
    from orchestrator.workflow.dynamic.state import DynamicStateError, load_dynamic_view
    run, files = owner(tmp_path, body='(defworkflow main () -> Value 0)')
    try:
        run.complete(0, steps=1)
        state = json.loads(files.read('state.json'))
        state['workflow_outputs'] = {'SECRET_RUNTIME_KEY/~': [2**63]}
        files.write_atomic('state.json', json.dumps(state).encode())
        before = snapshot(tmp_path)
        with pytest.raises(DynamicStateError) as exc:
            load_dynamic_view(files.workspace)
        message = str(exc.value)
        assert 'SECRET_RUNTIME_KEY' not in message
        assert exc.value.__cause__.value_path.split('/')[-1] == '0'
        assert snapshot(tmp_path) == before
    finally: files.close()


def test_invalidation_uses_declared_dynamic_diagnostic_code(tmp_path, monkeypatch):
    from orchestrator.cli.commands.invalidate import invalidate_run
    run, files = owner(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = snapshot(tmp_path)
    try:
        with pytest.raises(ValueError) as exc:
            invalidate_run(files.workspace.name, 'x', state_dir=str(tmp_path))
        assert exc.value.code == 'dynamic_invalidation_unsupported'
        assert snapshot(tmp_path) == before
    finally: files.close()
