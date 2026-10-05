"""Public dynamic readers preserve authoritative native results without writes.

Local state fixtures cover shapes; Task9 extensions inspect real killed public processes.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import signal
import time

import pytest

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from orchestrator.monitor.classifier import classify_run
from orchestrator.monitor.messages import render_event_email
from orchestrator.monitor.models import MonitorEventKind
from tests.test_workflow_dynamic_cli import source
from tests.test_workflow_dynamic_state import effect_owner
from tests.test_workflow_evaluated_dashboard import _outputs
from tests.test_workflow_evaluated_monitor import _config, _scan
from tests.test_workflow_evaluated_watchdog_probe import _probe, _guard_loaded
from tests.test_workflow_evaluated_watchdog_watcher import _start
from tests.test_watch_workflow_usage_limit import watcher
from tests.test_monitor_cli import _write_config
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_dynamic_interruptions import (
    _events, _kill_known_processes, _live_cli, _run_root, _state,
    _tree_snapshot, _wait_file, _write_case,
)

ROOT = Path(__file__).resolve().parents[1]


def tree(root):
    return {str(p.relative_to(root)): (('symlink', os.readlink(p)) if p.is_symlink() else ('dir' if p.is_dir() else p.read_bytes()))
            for p in root.rglob('*')}


def cli(workspace, *arguments):
    return subprocess.run([sys.executable, '-B', '-m', 'orchestrator', *map(str, arguments)],
        cwd=workspace, env={**os.environ, 'PYTHONPATH': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=20)


def pure_run(workspace, value=0):
    workspace.mkdir(parents=True, exist_ok=True)
    body = '(defworkflow main () -> Int 0)' if value is not False else '(defworkflow main () -> Bool false)'
    if value is None:
        body = '(defworkflow main ((value Optional[Int])) -> Optional[Int] value)'
    path = source(workspace, body)
    compiled = cli(workspace, 'compile', path, '--diagnostics-json')
    assert compiled.returncode == 0, compiled.stderr
    arguments = []
    if value is None:
        inputs = workspace / 'inputs.json'
        inputs.write_text('{"value":null}')
        arguments = ['--input-file', inputs]
    result = cli(workspace, 'run', path, *arguments)
    assert result.returncode == 0, result.stderr
    path.unlink()
    (workspace / 'inputs.json').unlink(missing_ok=True)
    run_root, = (workspace / '.orchestrate/runs').iterdir()
    return run_root


def record(workspace):
    run, = RunScanner([workspace]).scan().runs
    return run


@pytest.mark.parametrize('value', [0, False, None])
def test_public_source_free_report_dashboard_monitor_probe(tmp_path, value):
    target, watch_workspace = tmp_path / 'T', tmp_path / 'W'
    root = pure_run(target, value)
    watch_workspace.mkdir()
    before = tree(target)
    result = cli(target, 'report', '--run-id', root.name, '--format', 'json')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report['run']['workflow_outputs'] == value
    assert type(report['run']['workflow_outputs']) is type(value)
    assert report['run']['resumable'] is False and report['steps'] == []
    expected_inputs = {'value': None} if value is None else {}
    assert report['run']['bound_inputs'] == expected_inputs
    assert not {'memo_offset', 'next_effect', 'heartbeat'} & report['run'].keys()
    markdown = cli(target, 'report', '--run-id', root.name)
    assert markdown.returncode == 0, markdown.stderr
    output = markdown.stdout.split('## Outputs\n```json\n')[1].split('\n```')[0]
    assert json.loads(output) == value
    app = DashboardApp(RunScanner([target]))
    assert root.name in app.handle('GET', '/runs').body.decode()
    response = app.handle('GET', f'/runs/w0/{root.name}')
    assert response.status == 200 and _outputs(response) == value
    scanned = record(target)
    detail = RunProjector().project_detail(scanned)
    assert type(detail.workflow_outputs) is type(value)
    assert detail.bound_inputs == expected_inputs
    assert detail.workflow_structure is None and detail.steps == [] and detail.cursor.nodes == []
    commands = CommandBuilder().build(scanned)
    assert commands.report is not None and commands.resume is None
    config = _write_config(watch_workspace, target)
    ledger = watch_workspace / 'notifications.json'
    monitor = cli(target, 'monitor', '--config', config, '--once', '--dry-run', '--ledger', ledger)
    assert monitor.returncode == 0, monitor.stderr
    outputs = monitor.stdout.split('Workflow outputs:\n')[1].split('\n\nSuggested commands:')[0]
    assert json.loads(outputs) == value and not ledger.exists()
    assert 'orchestrator resume' not in monitor.stdout and 'Heartbeat at:' not in monitor.stdout
    watch, evidence = _probe(watch_workspace, root)
    assert watch['watch_status'] == 'COMPLETED' and watch['recommended_recovery'] == 'NONE'
    assert watch['resumable'] is evidence['resumable'] is False
    assert tree(target) == before


def effect_run(workspace, status):
    workspace.mkdir(parents=True, exist_ok=True)
    run, files, definition, location = effect_owner(workspace)
    run.start_effect(definition, location, 'command', steps=1)
    row = run.state['effects'][0]
    files.create(row['stdout_path'], b'actual stdout')
    files.create(row['stderr_path'], b'actual stderr')
    files.create(row['result_path'], b'0')
    error = {'code': 'local_failure', 'message': 'provider usage limit reached', 'location': location, 'metadata': {}}
    if status != 'interrupted':
        run.finish_effect(steps=2, error=error if status == 'failed' else None)
        if status == 'failed': run.fail(error, steps=2)
        else: run.complete(0, steps=2)
    files.close()
    root = workspace / '.orchestrate/runs/run-1'
    root.parent.mkdir(parents=True)
    (workspace / 'run-1').rename(root)
    for path in workspace.rglob('*.orc'): path.unlink()
    return root


@pytest.mark.parametrize('status,kind', [('completed', MonitorEventKind.COMPLETED),
    ('failed', MonitorEventKind.FAILED), ('interrupted', MonitorEventKind.CRASHED)])
def test_reached_effect_timeline_paths_and_recovery_refusal(tmp_path, status, kind):
    target, W = tmp_path / 'T', tmp_path / 'W'
    root = effect_run(target, status)
    W.mkdir()
    before = tree(target)
    result = cli(target, 'report', '--run-id', root.name, '--format', 'json')
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    row, = report['steps']
    assert row['ordinal'] == 1 and row['location'] == '/definitions/demo~1main::main/body'
    detail = RunProjector().project_detail(record(target))
    step, = detail.steps
    assert step.ref == '1' and step.debug['location'] == row['location']
    assert {k: v.route_path for k, v in step.file_refs.items()} == {
        'result': row['result_path'], 'stdout': row['stdout_path'], 'stderr': row['stderr_path']}
    assert detail.row.display_status == status and detail.row.heartbeat_at is None
    assert bool(detail.cursor.nodes) == (status == 'interrupted')
    app = DashboardApp(RunScanner([target]))
    for key in step.file_refs:
        response = app.handle('GET', f'/runs/w0/{root.name}/files/run/{step.file_refs[key].route_path}')
        assert response.status == 200
    event = classify_run(_scan(target), stale_after_seconds=1)
    assert event.kind is kind
    body = render_event_email(event, _config(target)).get_content()
    assert 'actual stdout' in body and 'actual stderr' in body and 'orchestrator resume' not in body
    if status == 'failed': assert row['error']['code'] in body
    watch, evidence = _probe(W, root)
    assert watch['recommended_recovery'] == ('NONE' if status == 'completed' else 'INVESTIGATE')
    assert watch['resumable'] is evidence['resumable'] is False
    assert tree(target) == before


@pytest.mark.parametrize('damage', ['missing-state', 'missing-header', 'wrong-profile', 'mixed', 'bad-result', 'ordinal', 'current', 'path', 'header-symlink', 'program-symlink', 'state-symlink', 'bad-header-and-program'])
def test_invalid_authority_fail_closed_across_public_readers(tmp_path, damage):
    T, W = tmp_path / 'T', tmp_path / 'W'
    root = effect_run(T, 'completed')
    W.mkdir()
    header_path, state_path = root / 'run.json', root / 'state.json'
    state = json.loads(state_path.read_text())
    if damage == 'missing-state': state_path.unlink()
    elif damage == 'missing-header': header_path.unlink()
    elif damage == 'bad-header-and-program':
        header_path.write_text('broken header')
        (root / 'closed_program.json').write_text('broken program')
    elif damage.endswith('-symlink'):
        name = {'header-symlink': 'run.json', 'program-symlink': 'closed_program.json', 'state-symlink': 'state.json'}[damage]
        path = root / name
        copy = W / name
        copy.write_bytes(path.read_bytes()); path.unlink(); path.symlink_to(copy)
    elif damage == 'wrong-profile':
        header = json.loads(header_path.read_text()); header['result_persistence_profile'] = 'future'
        header_path.write_text(json.dumps(header))
    else:
        if damage == 'mixed': state['result_persistence_profile'] = 'evaluated_execution.v1'
        if damage == 'bad-result': state['workflow_outputs'] = False
        if damage == 'ordinal': state['effects'][0]['ordinal'] = 2
        if damage == 'current': state['current_effect'] = 1
        if damage == 'path': state['effects'][0]['stdout_path'] = '../escape'
        state_path.write_text(json.dumps(state))
    before = tree(T)
    report = cli(T, 'report', '--run-id', root.name, '--format', 'json')
    assert report.returncode == 1 and 'dynamic_state_invalid' in report.stderr
    scanned = record(T)
    assert scanned.state is None and 'dynamic_state_invalid' in (scanned.parse_error or scanned.read_error)
    assert CommandBuilder().build(scanned).resume is None
    from orchestrator.state import StateManager
    from orchestrator.workflow.dynamic.state import DynamicStateError
    with pytest.raises(DynamicStateError):
        StateManager(T, root.name).load()
    run = _scan(T)
    assert run.state is None and 'dynamic_state_invalid' in run.read_error
    assert classify_run(run, stale_after_seconds=1) is None
    watch, evidence = _probe(W, root)
    assert watch['recommended_recovery'] == 'INVESTIGATE'
    assert 'dynamic_state_invalid' in evidence['state_load_error']
    assert tree(T) == before


def test_monitor_revalidates_scanned_dynamic_terminal(tmp_path):
    root = pure_run(tmp_path)
    stale = _scan(tmp_path)
    assert stale.state['status'] == 'completed'
    (root / 'state.json').unlink()
    before = tree(tmp_path)
    assert classify_run(stale, stale_after_seconds=1) is None
    assert tree(tmp_path) == before


@pytest.mark.parametrize('profile', ['evaluated', 'dynamic'])
def test_nonobject_header_preserves_profile_error_ownership(tmp_path, profile):
    from orchestrator.state import StateManager, select_run_profile
    from orchestrator.workflow.dynamic.state import DynamicStateError, load_dynamic_view
    from orchestrator.workflow.evaluated.authority import RunAuthorityError
    from orchestrator.workflow.evaluated.memo import MemoError
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from tests.test_workflow_evaluated_readers import _pure_run

    root = _pure_run(tmp_path) if profile == 'evaluated' else pure_run(tmp_path)
    (root / 'run.json').write_text('[]')
    before = tree(tmp_path)
    selection_error = RunAuthorityError if profile == 'evaluated' else DynamicStateError
    state_error = MemoError if profile == 'evaluated' else DynamicStateError
    code = 'memo_inconsistent' if profile == 'evaluated' else 'dynamic_state_invalid'
    owner = load_evaluated_view if profile == 'evaluated' else load_dynamic_view
    for reader, expected_error in ((lambda: select_run_profile(root), selection_error),
                                   (lambda: owner(root), selection_error),
                                   (lambda: StateManager(tmp_path, root.name).load(), state_error)):
        with pytest.raises(expected_error) as caught:
            reader()
        assert type(caught.value) is expected_error and caught.value.code == code
        assert tree(tmp_path) == before


def test_dynamic_running_uses_real_writer_lock_without_heartbeat(tmp_path):
    root = effect_run(tmp_path, 'interrupted')
    with _subprocess_writer(root):
        before = tree(tmp_path)
        assert record(tmp_path).state['status'] == 'running'
        assert classify_run(_scan(tmp_path), stale_after_seconds=0) is None
        assert tree(tmp_path) == before
    before = tree(tmp_path)
    assert classify_run(_scan(tmp_path), stale_after_seconds=0).kind is MonitorEventKind.CRASHED
    assert tree(tmp_path) == before


@pytest.mark.parametrize('status', ['completed', 'failed', 'interrupted', 'invalid'])
def test_controlled_watcher_stops_dynamic_recovery_before_any_actions(watcher, status):
    root = effect_run(watcher.workspace, 'failed' if status == 'invalid' else status)
    if status == 'invalid': (root / 'state.json').unlink()
    # Count readiness probes separately from the existing run/resume stand-in.
    probe = watcher.log.parent / 'stand-ins/claude'
    counter = watcher.log.parent / 'probe-calls'
    probe.write_text(f'#!/bin/sh\necho probe >> {counter}\necho OK\n')
    before = tree(watcher.workspace)
    pane = watcher.capture()
    process = _start(watcher, RUN_ID=root.name)
    deadline = time.monotonic() + 12
    while process.poll() is None and time.monotonic() < deadline:
        time.sleep(.05)
    assert process.poll() is not None, watcher.log.read_text()
    text = watcher.log.read_text()
    assert ('resumable=false' in text) if status != 'invalid' else ('dynamic_state_invalid' in text)
    assert watcher.calls() == [] and not counter.exists()
    assert 'interrupting' not in text and 'requeued' not in text and 'relaunching' not in text
    assert watcher.capture() == pane and tree(watcher.workspace) == before
    assert _guard_loaded(process.reader_guard, '-')


def test_actual_public_pure_failure_remains_source_free_and_nonresumable(tmp_path):
    T, W = tmp_path / 'T', tmp_path / 'W'
    T.mkdir(); W.mkdir()
    path = source(T, '(defworkflow main () -> Int (if 1 0 1))')
    assert cli(T, 'compile', path, '--diagnostics-json').returncode == 0
    result = cli(T, 'run', path)
    assert result.returncode == 1
    root, = (T / '.orchestrate/runs').iterdir()
    path.unlink()
    before = tree(T)
    report = cli(T, 'report', '--run-id', root.name, '--format', 'json')
    assert report.returncode == 0, report.stderr
    payload = json.loads(report.stdout)
    assert payload['run']['status'] == 'failed' and payload['run']['resumable'] is False
    assert payload['steps'] == [] and payload['run']['workflow_outputs'] is None
    detail = RunProjector().project_detail(record(T))
    assert detail.row.display_status == 'failed' and detail.error == payload['run']['error']
    event = classify_run(_scan(T), stale_after_seconds=1)
    assert event.kind is MonitorEventKind.FAILED and event.run.state['error'] == detail.error
    watch, evidence = _probe(W, root)
    assert watch['recommended_recovery'] == 'INVESTIGATE' and evidence['error'] == detail.error
    assert tree(T) == before


def test_controlled_watcher_observes_active_dynamic_writer_without_actions(watcher):
    root = effect_run(watcher.workspace, 'interrupted')
    counter = watcher.log.parent / 'probe-calls'
    probe = watcher.log.parent / 'stand-ins/claude'
    probe.write_text(f'#!/bin/sh\necho probe >> {counter}\necho OK\n')
    with _subprocess_writer(root):
        before = tree(watcher.workspace)
        process = _start(watcher, RUN_ID=root.name)
        deadline = time.monotonic() + 15
        while 'state running' not in (watcher.log.read_text() if watcher.log.exists() else ''):
            assert process.poll() is None
            assert time.monotonic() < deadline
            time.sleep(.05)
        assert watcher.calls() == [] and not counter.exists()
        assert tree(watcher.workspace) == before
        assert _guard_loaded(process.reader_guard, '-')


def test_watcher_discovery_refuses_named_target_error_before_unrelated_legacy_root(tmp_path):
    # Execute the production read-only discovery function, with its normal setup.
    T, W = tmp_path / 'T', tmp_path / 'W'
    target = T / '.orchestrate/runs/target'
    target.mkdir(parents=True); W.mkdir()
    (target / 'run.json').write_text('{"schema_version":"unknown","result_persistence_profile":"unknown"}')
    (target / 'state.json').write_text('{"run_id":"target","status":"completed"}')
    unrelated = target.with_name('unrelated')
    unrelated.mkdir()
    (unrelated / 'state.json').write_text('{"run_id":"unrelated","status":"running"}')
    script = ROOT / 'scripts/watch_workflow_usage_limit.sh'
    setup = script.read_text().split('\nmkdir -p "$(dirname "$LOG")"\n', 1)[0]
    program = setup + '\nrefresh_run_id_from_latest_running\nresult=$?\nprintf "%s|%s\\n" "$result" "$RUN_ID"\n'
    before = tree(T)
    result = subprocess.run(['bash', '-c', program], env={**os.environ, 'TARGET': 'isolated:0.0',
        'RUN_ID': 'target', 'WORKSPACE': str(T), 'LOG': str(W / 'watch.log'),
        'AGENT_ORCHESTRATION': str(ROOT), 'PYTHONDONTWRITEBYTECODE': '1'},
        capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == '1|target'
    assert 'memo_inconsistent' in result.stderr
    assert tree(T) == before


def _killed_public_root(target, kind, barrier):
    case = _write_case(target, kind, two_effects=True)
    control = target / '.reader-kill-control'
    with _live_cli(case, control, barrier=barrier) as process:
        _wait_file(process, control / 'gate.json')
        root = _run_root(case)
        _kill_known_processes(process, control)
        assert process.returncode == -signal.SIGKILL
    case['source'].unlink()
    return root, control


@pytest.mark.parametrize('kind', ['command', 'provider'])
@pytest.mark.parametrize('barrier', ['before_row', 'before_terminal'])
def test_public_readers_inspect_actual_killed_source_free_root_without_actions(tmp_path, kind, barrier):
    target, workspace = tmp_path / 'T', tmp_path / 'W'
    root, control = _killed_public_root(target, kind, barrier)
    workspace.mkdir()
    before, calls = _tree_snapshot(root), _events(control)
    target_before = tree(target)
    stored = _state(root)
    assert stored['status'] == 'running'
    expected_statuses = ['running'] if barrier == 'before_row' else ['completed', 'completed']
    assert [row['status'] for row in stored['effects']] == expected_statuses
    report = cli(target, 'report', '--run-id', root.name, '--format', 'json')
    assert report.returncode == 0, report.stderr
    payload = json.loads(report.stdout)
    assert payload['run']['status'] == 'interrupted'
    assert payload['run']['workflow_outputs'] is None and payload['run']['resumable'] is False
    assert [row['status'] for row in payload['steps']] == expected_statuses
    assert [row['ordinal'] for row in payload['steps']] == list(range(1, len(expected_statuses) + 1))
    assert all(row['location'] and row['result_path'] for row in payload['steps'])
    scanned = record(target)
    detail = RunProjector().project_detail(scanned)
    assert detail.row.display_status == 'interrupted' and detail.workflow_outputs is None
    assert detail.workflow_structure is None and detail.bound_inputs == payload['run']['bound_inputs']
    assert len(detail.steps) == len(stored['effects'])
    commands = CommandBuilder().build(scanned)
    assert commands.report is not None and commands.resume is None
    app = DashboardApp(RunScanner([target]))
    assert root.name in app.handle('GET', '/runs').body.decode()
    response = app.handle('GET', f'/runs/w0/{root.name}')
    assert response.status == 200
    for step in detail.steps:
        for reference in step.file_refs.values():
            response = app.handle('GET', f'/runs/w0/{root.name}/files/run/{reference.route_path}')
            assert response.status == 200
    event = classify_run(_scan(target), stale_after_seconds=0)
    assert event.kind is MonitorEventKind.CRASHED
    assert event.run.state['workflow_outputs'] is None and event.run.state['resumable'] is False
    config = _write_config(workspace, target)
    ledger = workspace / 'notifications.json'
    monitor = cli(target, 'monitor', '--config', config, '--once', '--dry-run', '--ledger', ledger)
    assert monitor.returncode == 0, monitor.stderr
    assert not ledger.exists() and 'orchestrator resume' not in monitor.stdout
    watch, evidence = _probe(workspace, root)
    assert watch['watch_status'] == 'CRASHED' and watch['recommended_recovery'] == 'INVESTIGATE'
    assert watch['resumable'] is evidence['resumable'] is False
    assert _tree_snapshot(root) == before and tree(target) == target_before
    assert _events(control) == calls


@pytest.mark.parametrize('kind', ['command', 'provider'])
def test_controlled_watcher_refuses_recovery_of_actual_killed_prefix(watcher, kind):
    root, control = _killed_public_root(watcher.workspace, kind, 'second_dispatch')
    assert [row['status'] for row in _state(root)['effects']] == ['completed', 'running']
    counter = watcher.log.parent / 'probe-calls'
    probe = watcher.log.parent / 'stand-ins/claude'
    probe.write_text(f'#!/bin/sh\necho probe >> {counter}\necho OK\n')
    before, calls = _tree_snapshot(root), _events(control)
    target_before, pane = tree(watcher.workspace), watcher.capture()
    process = _start(watcher, RUN_ID=root.name)
    process.wait(timeout=15)
    text = watcher.log.read_text()
    assert 'resumable=false' in text
    assert watcher.calls() == [] and not counter.exists()
    assert 'interrupting' not in text and 'requeued' not in text and 'relaunching' not in text
    assert watcher.capture() == pane and tree(watcher.workspace) == target_before
    assert _guard_loaded(process.reader_guard, '-')
    assert _tree_snapshot(root) == before and _events(control) == calls


@pytest.mark.parametrize('snapshot', ['old', 'new'])
def test_monitor_reads_real_atomic_terminal_publication_as_one_valid_snapshot(tmp_path, monkeypatch, snapshot):
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    case = _write_case(tmp_path, 'command', two_effects=True)
    control = tmp_path / '.reader-publication-control'
    with _live_cli(case, control, barrier='before_terminal') as process:
        _wait_file(process, control / 'gate.json')
        root = _run_root(case)
        stale = _scan(tmp_path)
        assert stale.state['status'] == 'running'
        case['source'].unlink()
        calls = _events(control)
        read = WorkspaceFiles.read
        snapshots = []
        state_reads = []

        def read_during_publication(files, path, **kwargs):
            if str(path) != 'state.json' or files.workspace != root or snapshots:
                return read(files, path, **kwargs)
            state_reads.append(1)
            if len(state_reads) == 1:
                # Profile selection validates first; race the monitor snapshot itself.
                return read(files, path, **kwargs)
            old = read(files, path, **kwargs) if snapshot == 'old' else None
            (control / 'release').touch()
            stdout, stderr = process.communicate(timeout=15)
            assert process.returncode == 0, (stdout, stderr)
            snapshots.append(_tree_snapshot(root))
            return old if snapshot == 'old' else read(files, path, **kwargs)

        monkeypatch.setattr(WorkspaceFiles, 'read', read_during_publication)
        event = classify_run(stale, stale_after_seconds=0)
        assert event is not None
        assert event.kind is (MonitorEventKind.CRASHED if snapshot == 'old' else MonitorEventKind.COMPLETED)
        assert event.run.state['workflow_outputs'] == (None if snapshot == 'old' else [11, 22])
        assert _state(root)['status'] == 'completed'
        assert _tree_snapshot(root) == snapshots[0] and _events(control) == calls


def test_profile_race_refuses_mixed_authority_without_stale_completed_output(tmp_path, monkeypatch):
    from orchestrator.state import StateManager
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    from orchestrator.workflow.dynamic.state import DynamicStateError

    root = pure_run(tmp_path)
    stale = _scan(tmp_path)
    assert stale.state['status'] == 'completed' and stale.state['workflow_outputs'] == 0
    read = WorkspaceFiles.read
    changes = []

    def change_after_route_read(files, path, **kwargs):
        value = read(files, path, **kwargs)
        if str(path) == 'run.json' and files.workspace == root and not changes:
            header = json.loads(value)
            original_pin = header['runtime_pin']
            header.update(schema_version='3.0', result_persistence_profile='evaluated_execution.v1')
            files.write_atomic('run.json', json.dumps(header).encode())
            assert header['runtime_pin'] == original_pin
            changes.append(_tree_snapshot(root))
        return value

    monkeypatch.setattr(WorkspaceFiles, 'read', change_after_route_read)
    assert classify_run(stale, stale_after_seconds=0) is None
    assert changes and _tree_snapshot(root) == changes[0]
    with pytest.raises(DynamicStateError):
        StateManager(tmp_path, root.name).load()
    scanned = record(tmp_path)
    assert scanned.state is None and CommandBuilder().build(scanned).resume is None
    assert _tree_snapshot(root) == changes[0]


def test_actual_legacy_evaluated_and_dynamic_roots_keep_distinct_profile_pins(tmp_path):
    from orchestrator.state import StateManager, select_run_profile
    from orchestrator.workflow.dynamic.state import DynamicStateError, load_dynamic_view
    from tests.test_workflow_dynamic_source import write_source

    for target, profile, schema in (('2.34', 'legacy', '2.1'),
                                    ('2.35', 'evaluated', '3.0'),
                                    ('3.0', 'dynamic', '3.1')):
        workspace = tmp_path / target
        workspace.mkdir()
        body = '(record (value 17))' if profile == 'dynamic' else '(record Out :value 17)'
        source = write_source(workspace, 'demo/main',
            f'(export main) (defrecord Out (value Int)) (defworkflow main () -> Out {body})',
            target=target, budget=100 if profile == 'dynamic' else None)
        result = cli(workspace, 'run', source)
        assert result.returncode == 0, result.stderr
        root, = (workspace / '.orchestrate/runs').iterdir()
        authority = root / ('state.json' if profile == 'legacy' else 'run.json')
        assert json.loads(authority.read_text())['schema_version'] == schema
        if profile == 'legacy':
            assert not (root / 'run.json').exists()
        before = _tree_snapshot(root)
        assert select_run_profile(root) == profile
        manager = StateManager(workspace, root.name)
        try:
            if profile == 'dynamic':
                with pytest.raises(DynamicStateError):
                    manager.load()
                assert load_dynamic_view(root)['status'] == 'completed'
            else:
                state = manager.load()
                assert state.status == 'completed'
        finally:
            manager.close()
        report = cli(workspace, 'report', '--run-id', root.name, '--format', 'json')
        assert report.returncode == 0, report.stderr
        expected = {'return__value': 17} if profile == 'legacy' else {'value': 17}
        assert json.loads(report.stdout)['run']['workflow_outputs'] == expected
        assert _tree_snapshot(root) == before
