"""Fatal publication drains workers; ordinary item faults drain siblings."""

from concurrent.futures import Future, ThreadPoolExecutor
import json
import sys
import threading

import pytest

from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated.parallel import ParallelCoordinator
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import read_memo
from tests.test_workflow_evaluated_parallel import _install_launcher
from tests.workflow_evaluated_parallel_helpers import COMMAND, replay_case, mapped, worker, effect


def _snapshot(authority):
    return read_memo(authority.memo_path, site_classes(authority.program))


def test_deferred_e1_reuses_drain_fifo_beyond_recursion_limit(tmp_path, monkeypatch):
    count = sys.getrecursionlimit() + 10
    replies = [Future() for _ in range(count)]
    granted = []
    with replay_case(tmp_path) as authority:
        coordinator = ParallelCoordinator(None, authority, {})
        def reuse(token, node, operands, identity, owner, reader, kwargs):
            granted.append(identity)
            return identity
        monkeypatch.setattr(coordinator, '_prepare', reuse)
        for index, reply in enumerate(replies):
            args = (object(), {'class': 'run_ref'}, (), index, 'owner', None, {})
            coordinator.deferred.append(('prepare', args, reply))
        coordinator._grant_deferred()
        assert granted == list(range(count))
        assert all(reply.done() for reply in replies)
        assert [reply.result() for reply in replies] == granted
        assert not coordinator.deferred
        assert coordinator.fatal is None


def test_commit_publication_error_stops_writes_and_releases_queued_workers(tmp_path, monkeypatch):
    calls, barrier = [], threading.Barrier(2)
    def outcome(event):
        barrier.wait(timeout=5)
        return 1
    _install_launcher(monkeypatch, outcome, calls)
    real_append = runtime.append_record
    def fail_commit(path, record, **kwargs):
        if record['record'] == 'committed':
            raise OSError('injected journal publication failure')
        return real_append(path, record, **kwargs)
    monkeypatch.setattr(runtime, 'append_record', fail_commit)
    with replay_case(tmp_path) as authority:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.execute_pure_run, authority, {}, run_id='run-1', workspace=tmp_path)
            assert future.result(timeout=10) == (1, None)
        assert len(calls) == 2
        assert [entry.data['record'] for entry in _snapshot(authority).entries] == ['started', 'started']


def test_failed_classification_read_releases_all_reply_waiters(tmp_path, monkeypatch):
    calls, barrier = [], threading.Barrier(2)
    published_failure = threading.Event()
    def outcome(event):
        barrier.wait(timeout=5)
        raise RuntimeError('ordinary external failure')
    _install_launcher(monkeypatch, outcome, calls)
    real_append, real_snapshot = runtime.append_record, ParallelCoordinator._snapshot
    def append(path, record, **kwargs):
        entry = real_append(path, record, **kwargs)
        if record['record'] == 'failed':
            published_failure.set()
        return entry
    def snapshot(coordinator):
        if published_failure.is_set():
            raise OSError('injected classification read failure')
        return real_snapshot(coordinator)
    monkeypatch.setattr(runtime, 'append_record', append)
    monkeypatch.setattr(ParallelCoordinator, '_snapshot', snapshot)
    with replay_case(tmp_path) as authority:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.execute_pure_run, authority, {}, run_id='run-1', workspace=tmp_path)
            assert future.result(timeout=10) == (1, None)
        assert len(calls) == 2
        assert [entry.data['record'] for entry in _snapshot(authority).entries] == ['started', 'started', 'failed']


def _pure_fault_program():
    command = COMMAND.replace(':returns Int', ':returns Float')
    body = f'(let* ((value {command})) (if (= repo "a") (/ value 0.0) value))'
    return mapped('(call worker :repo repo)'), worker(body, result='Float')


def _missing_siblings(authority):
    missing = {effect(authority, index)[0] for index in (1, 3)}
    rows = []
    for entry in _snapshot(authority).entries:
        row = entry.data
        if row['record'] == 'terminal':
            continue
        if row['record'] == 'committed' and row['identity'] in missing:
            row = dict(record='failed', identity=row['identity'], attempt=row['attempt'], code='test_interrupted', exit_info={})
        rows.append(row)
    authority.run_files.write_atomic('memo.jsonl', b''.join(json.dumps(row).encode() + b'\n' for row in rows))


@pytest.mark.parametrize('diverged', [False, True])
def test_resume_pure_item_fault_drains_missing_siblings_after_full_c7(tmp_path, monkeypatch, diverged):
    calls = []
    _install_launcher(monkeypatch, lambda event: 1.0, calls)
    body, definitions = _pure_fault_program()
    with replay_case(tmp_path, body, declarations=definitions, result='List[Float]') as authority:
        assert runtime.execute_pure_run(authority, {}, run_id='run-1', workspace=tmp_path) == (1, None)
        _missing_siblings(authority)
        if diverged:
            (tmp_path / 'c' / 'work' / 'probe.py').write_text('# diverged committed closure\n')
        before = authority.memo_path.read_bytes()
        calls.clear()
        result = runtime.execute_pure_resume(authority, {}, run_id='run-1', workspace=tmp_path)
        if diverged:
            assert result == (2, None)
            assert authority.memo_path.read_bytes() == before
            assert calls == []
        else:
            assert result == (1, None)
            assert {event['item'] for event in calls} == {'b', 'd'}
            assert len(_snapshot(authority).active_commits) == 4


@pytest.mark.parametrize('part', ['source', 'workspace', 'serial-before'])
def test_preparation_and_serial_pure_faults_do_not_reserve_parallel_attempts(tmp_path, monkeypatch, part):
    bad_condition = '(< (/ 1.0 denominator) 0.0)'
    if part == 'source':
        body = mapped(source=f'(if {bad_condition} (list "a") (list "b"))')
    elif part == 'workspace':
        body = mapped().replace('(string/concat repo "/work")', f'(if {bad_condition} "a/work" "b/work")')
    else:
        body = f'(if {bad_condition} {mapped()} {mapped()})'
    calls = []
    _install_launcher(monkeypatch, lambda event: 0, calls)
    from tests.workflow_lisp_closed_program_helpers import build
    from tests.test_workflow_evaluated_command_lifecycle import _publish
    program = build(tmp_path, f'(workflow-lisp (:language "0.1") (:target-dsl "2.37") '
        f'(defmodule parallel) (export run) (defworkflow run ((denominator Float)) -> List[Int] {body}))')
    with _publish(tmp_path, program, inputs={'denominator': 0.0}) as authority:
        before = authority.memo_path.read_bytes()
        assert runtime.execute_pure_run(authority, {'denominator': 0.0}, run_id='run-1', workspace=tmp_path) == (1, None)
        assert not _snapshot(authority).latest_starts
        assert calls == []


def test_failed_record_view_failure_stops_later_writes_until_workers_drain(tmp_path, monkeypatch):
    from orchestrator.workflow.evaluated import views
    from orchestrator.workflow.evaluated.commands import CommandPerformerError
    from orchestrator.workflow.evaluated.views import ViewPublicationError
    failed_view, release_b = threading.Event(), threading.Event()
    calls, barrier = [], threading.Barrier(2)
    def outcome(event):
        if event['item'] in 'ab':
            barrier.wait(timeout=5)
        if event['item'] == 'a':
            raise CommandPerformerError('item_failed', 'ordinary failure')
        if event['item'] == 'b':
            assert release_b.wait(5)
        return 1
    _install_launcher(monkeypatch, outcome, calls)
    real_publish = views.publish_evaluated_view
    def publish(authority, entry):
        if entry.data['record'] == 'failed':
            failed_view.set()
            raise ViewPublicationError('failed record view publication failed')
        return real_publish(authority, entry)
    monkeypatch.setattr(views, 'publish_evaluated_view', publish)
    with replay_case(tmp_path) as authority:
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(runtime.execute_pure_run, authority, {}, run_id='run-1', workspace=tmp_path)
            try:
                assert failed_view.wait(5)
                release_b.set()
                assert future.result(timeout=10) == (1, None)
            finally:
                release_b.set()
        assert len(calls) == 2
        assert [entry.data['record'] for entry in _snapshot(authority).entries] == ['started', 'started', 'failed']


def test_resume_workspace_fault_is_not_reclassified_by_later_body_fault(tmp_path, monkeypatch):
    from tests.workflow_lisp_closed_program_helpers import build
    from tests.test_workflow_evaluated_command_lifecycle import _publish
    condition = '(< (/ 1.0 denominator) 0.0)'
    cwd = f'(if (= repo "a") (if {condition} "a/work" "a/work") (string/concat repo "/work"))'
    body = mapped('(call worker :repo repo :denominator denominator)').replace('(string/concat repo "/work")', cwd)
    command = COMMAND.replace(':returns Int', ':returns Float')
    definitions = f'(defworkflow worker ((repo String) (denominator Float)) -> Float (if (= repo "b") (/ 1.0 denominator) {command}))'
    program = build(tmp_path, f'(workflow-lisp (:language "0.1") (:target-dsl "2.37") '
        f'(defmodule parallel) (export run) {definitions} (defworkflow run ((denominator Float)) -> List[Float] {body}))')
    for item in 'abcd':
        (tmp_path / item / 'work').mkdir(parents=True)
    calls = []
    _install_launcher(monkeypatch, lambda event: 1.0, calls)
    with _publish(tmp_path, program, inputs={'denominator': 0.0}) as authority:
        before = b'{"record":'
        authority.run_files.write_atomic('memo.jsonl', before)
        assert runtime.execute_pure_resume(authority, {'denominator': 0.0}, run_id='run-1', workspace=tmp_path) == (2, None)
        assert authority.memo_path.read_bytes() == before
        assert calls == []
