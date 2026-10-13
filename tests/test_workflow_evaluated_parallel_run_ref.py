"""Parallel E1 coordination preserves the existing ledger authority."""

from orchestrator.workflow.run_ref import runtime as e1
from tests.test_workflow_run_ref_runtime import _runtime_request


def test_preparation_split_keeps_cleanup_selection_on_caller(tmp_path, monkeypatch):
    calls = []
    request = _runtime_request(tmp_path)
    effects = e1.RunRefRuntimeDependencies(monotonic_ns=lambda: 17)
    monkeypatch.setattr(e1, '_discard_incomplete_attempt', lambda request, effects: calls.append('discard'))
    allocation = object()
    monkeypatch.setattr(e1, 'select_run_ref_lifecycle_allocation', lambda request: calls.append('select') or allocation)
    prepare = getattr(e1, 'prepare_run_ref_lifecycle_allocation', None)
    assert prepare is not None, 'missing coordinator-owned preparation split'
    assert prepare(request, dependencies=effects) == (allocation, 17)
    assert calls == ['discard', 'select']


def test_live_parallel_map_reaches_external_work(tmp_path):
    from tests.workflow_evaluated_parallel_helpers import replay_case
    from orchestrator.workflow.evaluated.runtime import execute_pure_run
    with replay_case(tmp_path) as authority:
        script = 'import os\nfrom pathlib import Path\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7")\n'
        for item in 'abcd':
            (tmp_path / item / 'work' / 'probe.py').write_text(script)
        assert execute_pure_run(authority, {}, run_id='run-1', workspace=tmp_path) == (0, [7, 7, 7, 7])


import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import threading

import pytest

from orchestrator.workflow.evaluated import runtime as parent_runtime
from orchestrator.workflow.evaluated import run_ref as adapter
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from tests.test_workflow_evaluated_run_ref import _public_fixture, _authority, _assert_readonly_resumes
from tests.test_workflow_evaluated_run_ref_settlement import _service_run
from tests.test_workflow_evaluated_invalidate import _tree_bytes


def _parallel_e1_fixture(root, *, nested=False):
    def definitions(call):
        leaf = f'(defworkflow invoke ((repo String)) -> Bool (let* ((child {call})) child.value))'
        if not nested:
            return leaf
        inner = '(list/map-effect ((sub (list "x" "y"))) :max 2 :parallel 2 '
        inner += ':workspace (string/concat repo "/" sub) (call invoke :repo sub))'
        return leaf + f'(defworkflow inner ((repo String)) -> List[Bool] {inner})'
    body = '(list/map-effect ((repo (list "a" "b"))) :max 2 :parallel 2 :workspace repo '
    body += '(call inner :repo repo))' if nested else '(call invoke :repo repo))'
    parent, source, refs = _public_fixture(root, parent_target='2.37', child_target='2.35',
        definitions=definitions, body=lambda call: f'(let* ((items {body})) (= (list/length items) 2))')
    for item in 'ab':
        (parent / item).mkdir()
        if nested:
            for child in 'xy':
                (parent / item / child).mkdir()
    return parent, source, refs


def _wait(event):
    assert event.wait(10), 'E1 lifecycle did not reach its barrier'


def _observe_e1(monkeypatch, *, pause_stage=None, fail_stage=None):
    real_drive = e1.drive_run_ref_lifecycle
    real_persist = e1.persist_run_ref_lifecycle_event
    reached, release = threading.Event(), threading.Event()
    events, writer_threads = [], []

    def persist(request, event):
        events.append((request.parent_identity, event.stage))
        writer_threads.append(threading.get_ident())
        if event.stage == fail_stage:
            raise OSError('injected E1 acknowledgement publication failure')
        return real_persist(request, event)

    def drive(request, *, acknowledge, **kwargs):
        def acknowledged(event):
            ack = acknowledge(event)
            if event.stage == pause_stage and not reached.is_set():
                reached.set()
                _wait(release)
            return ack
        return real_drive(request, acknowledge=acknowledged, **kwargs)

    monkeypatch.setattr(e1, 'drive_run_ref_lifecycle', drive)
    monkeypatch.setattr(e1, 'persist_run_ref_lifecycle_event', persist)
    return reached, release, events, writer_threads


@pytest.mark.parametrize('stage', ['allocated', 'program_prepared', 'launched', 'completed_pending_parent_commit'])
def test_parallel_e1_lifecycle_is_exclusive_through_settlement(tmp_path, monkeypatch, stage):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    reached, release, events, writer_threads = _observe_e1(monkeypatch, pause_stage=stage)
    # Wait for B to reach the scheduler, not a time-based absence assertion.
    from orchestrator.workflow.evaluated.parallel import ParallelCoordinator
    real_service = ParallelCoordinator._service
    deferred = threading.Event()

    def service(coordinator, request):
        real_service(coordinator, request)
        if coordinator.deferred:
            deferred.set()

    monkeypatch.setattr(ParallelCoordinator, '_service', service)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs)
        try:
            _wait(reached)
            _wait(deferred)
            assert {identity for identity, _stage in events} == {events[0][0]}
            authority, snapshot = _authority(parent)
            assert len(snapshot.latest_starts) == 1
            release.set()
            assert future.result(timeout=30).exit_code == 0
        finally:
            release.set()
    authority, snapshot = _authority(parent)
    assert len(snapshot.active_commits) == len(snapshot.settlements) == 2
    assert len(set(writer_threads)) == 1
    ledger = load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl')
    _assert_e1_adjacent_pairs(ledger, 2)
    assert [row.sequence for row in ledger.rows] == list(range(1, len(ledger.rows) + 1))
    _assert_readonly_resumes(parent, authority, refs)


def _assert_e1_adjacent_pairs(ledger, count):
    final = [row for row in ledger.rows if row.stage == 'committed']
    assert len(final) == count
    for row in final:
        pending = ledger.rows[row.sequence - 2]
        assert pending.stage == 'completed_pending_parent_commit'
        assert row.previous_row_digest == pending.row_digest
        assert row.visit == pending.visit


def test_nested_parallel_maps_share_e1_owner(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path, nested=True)
    _reached, _release, events, writer_threads = _observe_e1(monkeypatch)
    result = _service_run(monkeypatch, parent, source, refs)
    assert result.exit_code == 0
    authority, snapshot = _authority(parent)
    assert len(snapshot.active_commits) == len(snapshot.settlements) == 4
    assert len(set(writer_threads)) == 1
    _assert_e1_adjacent_pairs(load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl'), 4)


def test_e1_ack_failure_releases_deferred_and_event_waiters(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    _reached, _release, events, _threads = _observe_e1(monkeypatch, fail_stage='materialized')
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs)
        assert future.result(timeout=30).exit_code == 1
    authority, snapshot = _authority(parent)
    assert len(snapshot.latest_starts) == 1
    assert len({identity for identity, _stage in events}) == 1
    assert not snapshot.terminal
    assert [entry.data['record'] for entry in snapshot.entries] == ['started']


@pytest.mark.parametrize('gap', ['pending', 'committed'])
def test_parallel_resume_inventory_handles_pending_head_and_historical_pair(tmp_path, monkeypatch, gap):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    result = _service_run(monkeypatch, parent, source, refs)
    assert result.exit_code == 0
    authority, snapshot = _authority(parent)
    # Keep the first historical pair and the final global-head pending obligation together.
    rows = [entry.data for entry in snapshot.entries if entry.data['record'] not in {'settled', 'terminal'}]
    authority.memo_path.write_bytes(b''.join(json.dumps(row).encode() + b'\n' for row in rows))
    ledger_path = authority.run_root / 'run-ref-attempts.jsonl'
    if gap == 'pending':
        ledger_path.write_bytes(b''.join(ledger_path.read_bytes().splitlines(keepends=True)[:-1]))
    before_children = len(list(refs.rglob('child-request.json')))
    from tests.test_workflow_evaluated_resume import _resume_cli
    assert _resume_cli(parent, authority.run_root.name).returncode == 0
    authority, after = _authority(parent)
    assert len(after.settlements) == 2
    assert len(list(refs.rglob('child-request.json'))) == before_children
    assert [entry.data for entry in after.active_commits.values()] == [entry.data for entry in snapshot.active_commits.values()]
    _assert_readonly_resumes(parent, authority, refs)


@pytest.mark.parametrize('stage', ['program_prepared', 'launched'])
def test_command_sibling_commits_while_e1_waits_before_actual_launch_checks(tmp_path, monkeypatch, stage):
    def definitions(call):
        command = '(command-result emit :argv ("python" "probe.py") :returns Int)'
        return f'''(defworkflow invoke ((repo String)) -> Bool
            (if (= repo "c") (let* ((value {command})) (= value 0))
                (let* ((child {call})) child.value)))'''
    body = '''(let* ((items (list/map-effect ((repo (list "a" "b" "c")))
        :max 3 :parallel 3 :workspace repo (call invoke :repo repo))))
        (= (list/length items) 3))'''
    parent, source, refs = _public_fixture(tmp_path, parent_target='2.37', child_target='2.35',
        definitions=definitions, body=lambda call: body)
    from tests.test_workflow_evaluated_command_template_scopes import _write_probe, _write_boundaries
    for item in 'abc':
        (parent / item).mkdir()
    _write_probe(parent)
    _write_probe(parent / 'c')
    boundaries = _write_boundaries(parent)
    reached, release, events, writer_threads = _observe_e1(monkeypatch, pause_stage=stage)
    command_committed = threading.Event()
    from orchestrator.workflow.evaluated import effect_execution
    real_launch = effect_execution.launch_command
    def launch(*args, **kwargs):
        _wait(reached)
        return real_launch(*args, **kwargs)
    monkeypatch.setattr(effect_execution, 'launch_command', launch)
    real_append = parent_runtime.append_record
    def append(path, row, **kwargs):
        entry = real_append(path, row, **kwargs)
        if row['record'] == 'committed' and row['effect_class'] == 'command':
            command_committed.set()
        return entry
    monkeypatch.setattr(parent_runtime, 'append_record', append)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs,
            '--command-boundaries-file', str(boundaries))
        try:
            _wait(reached)
            _wait(command_committed)
            assert len({identity for identity, _stage in events}) == 1
            release.set()
            assert future.result(timeout=30).exit_code == 0
        finally:
            release.set()
    authority, snapshot = _authority(parent)
    assert len(snapshot.active_commits) == 3 and len(snapshot.settlements) == 2
    assert len(set(writer_threads)) == 1
    _assert_e1_adjacent_pairs(load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl'), 2)


def test_ordinary_e1_failure_releases_sibling_and_resume_retries_only_failed_item(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    real_drive, launches = e1.drive_run_ref_lifecycle, []
    first = True
    def drive(request, **kwargs):
        dependencies = e1.RunRefRuntimeDependencies()
        def launch(launch):
            nonlocal first
            launches.append(request.parent_identity)
            if first:
                first = False
                raise RuntimeError('ordinary child launch operation failure')
            return dependencies.launch_child(launch)
        return real_drive(request, dependencies=replace(dependencies, launch_child=launch), **kwargs)
    from dataclasses import replace
    monkeypatch.setattr(e1, 'drive_run_ref_lifecycle', drive)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 1
    authority, before = _authority(parent)
    assert len(before.active_commits) == 1 and not before.pending_starts
    failed = [entry.data for entry in before.entries if entry.data['record'] == 'failed']
    assert len(failed) == 1
    failed_identity = failed[0]['identity']
    committed_identity = next(iter(before.active_commits))
    from tests.test_workflow_evaluated_resume import _resume_cli
    assert _resume_cli(parent, authority.run_root.name).returncode == 0
    authority, after = _authority(parent)
    _assert_e1_retry(parent, refs, authority, before, after, failed_identity, committed_identity)


def _assert_e1_retry(parent, refs, authority, before, after, failed_identity, committed_identity):
    assert len(after.active_commits) == 2
    assert after.active_commits[failed_identity].data['attempt'] == 2
    assert after.active_commits[committed_identity].data == before.active_commits[committed_identity].data
    ledger = load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl')
    assert any(row.status == 'discarded' for row in ledger.rows)
    assert [row.attempt_ordinal for row in ledger.rows if row.stage == 'committed'] == [1, 2]
    assert len(list(refs.rglob('child-request.json'))) == 3


@pytest.mark.parametrize('tamper', ['sequence', 'root', 'bindings'])
def test_e1_event_must_match_coordinator_retained_allocation_before_append(tmp_path, monkeypatch, tamper):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    real_drive = e1.drive_run_ref_lifecycle
    def drive(request, *, acknowledge, **kwargs):
        def forge(event):
            payload = event.payload
            if tamper == 'bindings':
                payload['bindings']['child_run_id'] = 'wrong-child'
            wrong = e1.RunRefLifecycleEvent.build(sequence=event.sequence + (tamper == 'sequence'),
                event_kind=event.event_kind, stage=event.stage, visit=event.visit,
                attempt_ordinal=event.attempt_ordinal,
                effect_instance_root=request.parent_workspace if tamper == 'root' else event.effect_instance_root,
                payload=payload)
            return acknowledge(wrong)
        return real_drive(request, acknowledge=forge, **kwargs)
    monkeypatch.setattr(e1, 'drive_run_ref_lifecycle', drive)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs)
        assert future.result(timeout=15).exit_code == 1
    authority, snapshot = _authority(parent)
    assert [entry.data['record'] for entry in snapshot.entries] == ['started']
    assert not load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl').rows
    assert not list(refs.rglob('child-request.json'))


def test_parallel_recovery_inventory_rejects_later_pending_before_any_write(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 0
    authority, snapshot = _authority(parent)
    rows = [entry.data for entry in snapshot.entries if entry.data['record'] not in {'settled', 'terminal'}]
    authority.memo_path.write_bytes(b''.join(json.dumps(row).encode() + b'\n' for row in rows))
    ledger_path = authority.run_root / 'run-ref-attempts.jsonl'
    ledger_path.write_bytes(b''.join(ledger_path.read_bytes().splitlines(keepends=True)[:-1]))
    ledger = load_attempt_ledger(ledger_path)
    from dataclasses import replace
    from orchestrator.workflow.run_ref.ledger import allocate_attempt
    first = ledger.rows[0]
    allocate_attempt(ledger_path, visit=replace(first.visit, step_id='extra-visit'),
        bindings=replace(first.bindings, workspace_path=refs / 'extra' / 'workspace', child_run_id='extra-child'))
    # First obligation is a valid historical pair; second is pending below the new global head.
    before = _tree_bytes(parent), _tree_bytes(refs)
    from tests.test_workflow_evaluated_resume import _resume_cli
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 2, result.stderr
    assert 'parallel E1 recovery' in result.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_lost_e1_ack_is_fatal_before_sibling_grant(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    real_persist = e1.persist_run_ref_lifecycle_event
    def lose(request, event):
        real_persist(request, event)
        return None
    monkeypatch.setattr(e1, 'persist_run_ref_lifecycle_event', lose)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs)
        assert future.result(timeout=15).exit_code == 1
    authority, snapshot = _authority(parent)
    assert [entry.data['record'] for entry in snapshot.entries] == ['started']
    assert len(load_attempt_ledger(authority.run_root / 'run-ref-attempts.jsonl').rows) == 1
    assert not list(refs.rglob('child-request.json'))


@pytest.mark.parametrize('failure', ['preparation-publication', 'parent-launch-authority'])
def test_e1_fatal_authority_or_preparation_failure_never_appends_failed(tmp_path, monkeypatch, failure):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    if failure == 'preparation-publication':
        def refuse(*args, **kwargs):
            raise OSError('injected cleanup/allocation publication failure')
        monkeypatch.setattr(e1, 'prepare_run_ref_lifecycle_allocation', refuse)
    else:
        def refuse(*args, **kwargs):
            raise e1.RunRefRuntimeError('run_ref_child_launch_failed', 'parent_launch_authority_invalid')
        monkeypatch.setattr(e1, '_checked_launch_descriptor', refuse)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(_service_run, monkeypatch, parent, source, refs)
        assert future.result(timeout=20).exit_code == 1
    authority, snapshot = _authority(parent)
    assert [entry.data['record'] for entry in snapshot.entries] == ['started']
    assert not list(refs.rglob('child-request.json')) if failure == 'preparation-publication' else not snapshot.terminal


def _without_e1_finals(authority, snapshot):
    from orchestrator.workflow.run_ref import ledger as ledger_module
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    ledger_path = authority.run_root / 'run-ref-attempts.jsonl'
    ledger = load_attempt_ledger(ledger_path)
    rows, digests = [], {}
    for row in ledger.rows:
        if row.stage == 'committed':
            continue
        rebuilt = ledger_module._build_row(sequence=len(rows) + 1,
            previous_row_digest=rows[-1].row_digest if rows else None,
            visit=row.visit, attempt_ordinal=row.attempt_ordinal, stage=row.stage,
            status=row.status, recorded_at=row.recorded_at, bindings=row.bindings)
        rows.append(rebuilt)
        digests[row.row_digest] = rebuilt.row_digest
    ledger_path.write_bytes(b''.join(canonical_json_bytes(row.record) + b'\n' for row in rows))
    memo = []
    for entry in snapshot.entries:
        row = json.loads(json.dumps(entry.data))
        if row['record'] in {'settled', 'terminal'}:
            continue
        if row['record'] == 'committed':
            proof = row['proof']['settled_result']
            proof['pending_row_digest'] = digests[proof['pending_row_digest']]
        memo.append(row)
    authority.memo_path.write_bytes(b''.join(json.dumps(row).encode() + b'\n' for row in memo))


def test_parallel_recovery_inventory_rejects_multiple_missing_e1_finals_readonly(tmp_path, monkeypatch):
    parent, source, refs = _parallel_e1_fixture(tmp_path)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 0
    authority, snapshot = _authority(parent)
    _without_e1_finals(authority, snapshot)
    before = _tree_bytes(parent), _tree_bytes(refs)
    from tests.test_workflow_evaluated_resume import _resume_cli
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 2, result.stderr
    assert 'parallel E1 recovery' in result.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before
