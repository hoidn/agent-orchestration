"""Durable recovery and refusal boundaries use real retained run authority."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.host_input import pending, answer, cancel
from orchestrator.run_lock import ReservedRunRootError
from orchestrator.workflow.signatures import WorkflowSignatureError
from orchestrator.workflow.evaluated import host_input as owner
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.evaluated.memo import MemoError, memo_writer_lock
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.workflow_evaluated_host_input_helpers import start, rows, snapshot, resume, files


@pytest.mark.parametrize('fault', ['started', 'suspended', 'request-view'])
def test_start_and_suspension_publication_gaps_recover_same_attempt(tmp_path, monkeypatch, fault):
    original = WorkspaceFiles.write_atomic
    fired = []
    def fail_once(files_owner, path, content, **kwargs):
        if fired:
            return original(files_owner, path, content, **kwargs)
        if Path(path).name == 'state.json':
            records = [json.loads(line) for line in (files_owner.workspace / 'memo.jsonl').read_text().splitlines()]
            row = records[-1]
            target = row['record'] == fault and (fault == 'suspended' or 'host_request' in row)
        else:
            target = fault == 'request-view' and Path(path).name == 'request.json'
        if target:
            fired.append(True)
            raise OSError('injected publication gap')
        return original(files_owner, path, content, **kwargs)
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', fail_once)
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    assert result.exit_code == 1 and fired
    request_start = next(row for row in rows(root) if 'host_request' in row)
    assert snapshot(root).terminal is None
    if fault != 'suspended':
        assert pending(root) is None
        before = files(root)
        with pytest.raises(owner.HostInputError, match='host_input_not_suspended'):
            answer(root, request_start['host_request']['request_id'], 'APPROVED', by='operator')
        assert files(root) == before
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', original)
    assert resume(root) == 0
    request = pending(root)
    assert request['attempt'] == request_start['attempt'] == 1
    assert request['request_id'] == request_start['host_request']['request_id']
    assert request['deadline'] == request_start['host_request']['deadline']
    assert [r['record'] for r in rows(root)].count('suspended') == 1
    assert (tmp_path / 'dispatches.txt').read_text().splitlines() == ['emit']


@pytest.mark.parametrize('view', ['state.json', 'reply.json'])
def test_durable_reply_survives_view_failure_and_exact_duplicate(tmp_path, monkeypatch, view):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    original = WorkspaceFiles.write_atomic
    def fail(files_owner, path, content, **kwargs):
        if Path(path).name == view:
            raise OSError('injected reply publication gap')
        return original(files_owner, path, content, **kwargs)
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', fail)
    with pytest.raises(OSError):
        answer(root, request['request_id'], 'APPROVED', by='operator')
    before = files(root)
    assert answer(root, request['request_id'], 'APPROVED', by='operator')['variant'] == 'ANSWERED'
    assert files(root) == before
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', original)
    assert resume(root) == 0
    assert len([row for row in rows(root) if row.get('effect_class') == 'request_input']) == 1


@pytest.mark.parametrize('change', ['source', 'manifest', 'producer', 'doc', 'workspace'])
@pytest.mark.parametrize('settle', ['answer', 'cancel'])
def test_new_settlement_preflight_preserves_tail_and_views(tmp_path, monkeypatch, change, settle):
    kwargs = {}
    if change == 'doc':
        (tmp_path / 'reports').mkdir()
        (tmp_path / 'reports' / 'a.txt').write_text('old')
        kwargs = dict(declarations='''(defpath Report :kind relpath :under "reports" :must-exist true)
            (defprompt question-prompt (:fills (summary :text) (report :doc Report)) -> Approval "{summary}")''',
            question='(question-prompt :summary question :report report)', params=' (report Report)', inputs=['report=reports/a.txt'])
    source, result = start(tmp_path, monkeypatch, **kwargs)
    root = result.run_root
    request = pending(root)
    if change == 'source':
        source.write_text(source.read_text().replace('Approve?', 'Different'))
    elif change == 'manifest':
        (tmp_path / 'commands.json').write_text('{}')
    elif change == 'producer':
        (tmp_path / 'probe.py').write_text((tmp_path / 'probe.py').read_text() + '\n# producer changed\n')
    elif change == 'doc':
        (tmp_path / 'reports' / 'a.txt').write_text('changed')
    elif change == 'workspace':
        elsewhere = tmp_path / 'elsewhere'
        elsewhere.mkdir()
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(root)
    with pytest.raises(Exception):
        operation = answer if settle == 'answer' else cancel
        args = (root, request['request_id'], 'APPROVED') if settle == 'answer' else (root, request['request_id'])
        operation(*args, by='operator', accept_changed_evidence=True,
            workspace=elsewhere if change == 'workspace' else tmp_path)
    assert files(root) == before


def _shown(root):
    (root / 'reports').mkdir()
    (root / 'reports' / 'a.txt').write_text('original')
    return dict(options=':show (report)', declarations='(defpath Report :kind relpath :under "reports" :must-exist false)',
        params=' (report Report)', inputs=['report=reports/a.txt'])


@pytest.mark.parametrize('change', ['changed', 'missing', 'unreadable'])
@pytest.mark.parametrize('settle', ['answer', 'cancel'])
def test_accepted_show_drift_survives_resume_and_never_rewrites_request(tmp_path, monkeypatch, change, settle):
    kwargs = _shown(tmp_path)
    _, result = start(tmp_path, monkeypatch, **kwargs)
    root = result.run_root
    request = pending(root)
    evidence = tmp_path / 'reports' / 'a.txt'
    if change == 'changed':
        evidence.write_text('updated')
    elif change == 'missing':
        evidence.unlink()
    else:
        original_read = WorkspaceFiles.read
        def denied(files_owner, path, **kwargs):
            if files_owner.workspace == tmp_path and str(path) == 'reports/a.txt':
                raise PermissionError(13, 'injected read denial')
            return original_read(files_owner, path, **kwargs)
        monkeypatch.setattr(WorkspaceFiles, 'read', denied)
    operation = answer if settle == 'answer' else cancel
    args = (root, request['request_id'], 'APPROVED') if settle == 'answer' else (root, request['request_id'])
    before = files(root)
    with pytest.raises(owner.HostInputError, match='shown_evidence_changed'):
        operation(*args, by='operator')
    assert files(root) == before
    reply = operation(*args, by='operator', accept_changed_evidence=True)
    commit = snapshot(root).active_commits[request['identity']]
    assert commit.data['host_reply']['evidence_changes'][0]['observed']['status'] == {'changed': 'present', 'missing': 'missing', 'unreadable': 'unreadable'}[change]
    assert next(r['host_request'] for r in rows(root) if 'host_request' in r)['show'] == request['show']
    assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == reply


@pytest.mark.parametrize('substitution', ['symlink', 'directory'])
def test_evidence_override_cannot_waive_path_safety(tmp_path, monkeypatch, substitution):
    kwargs = _shown(tmp_path)
    _, result = start(tmp_path, monkeypatch, **kwargs)
    request = pending(result.run_root)
    evidence = tmp_path / 'reports' / 'a.txt'
    evidence.unlink()
    if substitution == 'symlink':
        evidence.symlink_to(tmp_path / 'probe.py')
    else:
        evidence.mkdir()
    before = files(result.run_root)
    with pytest.raises((owner.HostInputError, WorkflowSignatureError)):
        answer(result.run_root, request['request_id'], 'APPROVED', by='operator', accept_changed_evidence=True)
    assert files(result.run_root) == before


def test_valid_settlement_repairs_only_torn_tail_after_preflight(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    complete = (root / 'memo.jsonl').read_bytes()
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"partial":')
    answer(root, request['request_id'], 'APPROVED', by='operator')
    assert (root / 'memo.jsonl').read_bytes().startswith(complete)
    assert not snapshot(root).tail


def test_initial_publication_crossing_deadline_still_suspends(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: clock[0]))
    original = owner._publish_request_views
    def publish(*args, **kwargs):
        original(*args, **kwargs)
        clock[0] = 1000.0
    monkeypatch.setattr(owner, '_publish_request_views', publish)
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    assert result.exit_code == 0
    assert pending(root)['deadline_elapsed']
    assert snapshot(root).terminal is None
    assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == {'variant': 'EXPIRED'}


def test_writer_conflict_and_conflicting_duplicates_preserve_bytes(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    with memo_writer_lock(root):
        before = files(root)
        with pytest.raises(MemoError, match='memo_busy'):
            answer(root, request['request_id'], 'APPROVED', by='operator')
        assert files(root) == before
    answer(root, request['request_id'], 'APPROVED', by='operator')
    for kwargs in ({'value': 'DENIED'}, {'by': 'someone'}, {'attestation': 'other'}, {'accept_changed_evidence': True}):
        arguments = dict(value='APPROVED', by='operator') | kwargs
        before = files(root)
        with pytest.raises(owner.HostInputError, match='request_already_settled'):
            answer(root, request['request_id'], **arguments)
        assert files(root) == before


def test_unencodable_attestation_refuses_before_tail_repair(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(root)
    with pytest.raises(ValueError):
        answer(root, request['request_id'], 'APPROVED', by='operator', attestation='\ud800')
    assert files(root) == before


def test_retained_run_root_replacement_refuses_before_repair_or_commit(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(root)
    displaced = root.with_name(root.name + '-displaced')
    original = owner._show_changes
    calls = []
    def swapped(files_owner, frozen):
        changes = original(files_owner, frozen)
        calls.append(True)
        if len(calls) == 2:
            root.rename(displaced)
            root.mkdir()
        return changes
    monkeypatch.setattr(owner, '_show_changes', swapped)
    with pytest.raises(ReservedRunRootError):
        answer(root, request['request_id'], 'APPROVED', by='operator')
    assert files(displaced) == before
    assert not list(root.iterdir())


def test_show_override_preserves_independent_input_existence_contract(tmp_path, monkeypatch):
    kwargs = _shown(tmp_path)
    kwargs['declarations'] = kwargs['declarations'].replace(':must-exist false', ':must-exist true')
    _, result = start(tmp_path, monkeypatch, **kwargs)
    request = pending(result.run_root)
    (tmp_path / 'reports' / 'a.txt').unlink()
    before = files(result.run_root)
    with pytest.raises(Exception):
        answer(result.run_root, request['request_id'], 'APPROVED', by='operator', accept_changed_evidence=True)
    assert files(result.run_root) == before


def test_earlier_duplicate_remains_valid_while_later_request_waits(tmp_path, monkeypatch):
    body = '(let* ((first (request-input question :returns Approval))) (request-input question :returns Approval))'
    _, result = start(tmp_path, monkeypatch, body=body)
    root = result.run_root
    first = pending(root)
    reply = answer(root, first['request_id'], 'APPROVED', by='operator')
    assert resume(root) == 0
    second = pending(root)
    assert second['request_id'] != first['request_id']
    before = files(root)
    assert answer(root, first['request_id'], 'APPROVED', by='operator') == reply
    assert files(root) == before
    cancel(root, second['request_id'], by='operator')
    assert resume(root) == 0


@pytest.mark.parametrize('anchor', ['request', 'producer'])
def test_invalidation_retires_request_and_reissues_new_identity(tmp_path, monkeypatch, anchor):
    from orchestrator.cli.commands.invalidate import invalidate_run
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    old = pending(root)
    if anchor == 'request':
        answer(root, old['request_id'], 'APPROVED', by='operator')
        identity = old['identity']
    else:
        identity = next(iter(snapshot(root).active_commits))
    invalidate_run(root.name, identity)
    assert pending(root) is None
    before = files(root)
    with pytest.raises(owner.HostInputError, match='host_input_stale'):
        answer(root, old['request_id'], 'APPROVED', by='operator')
    assert files(root) == before
    assert resume(root) == 0
    new = pending(root)
    assert new['request_id'] != old['request_id']
    assert new['attempt'] == old['attempt'] + 1
    assert (tmp_path / 'dispatches.txt').read_text().splitlines() == ['emit'] * (2 if anchor == 'producer' else 1)


def test_custom_state_root_and_moved_workspace_keep_recorded_relationship(tmp_path, monkeypatch):
    runs = tmp_path / 'custom-runs'
    source, result = start(tmp_path, monkeypatch, state_dir=runs)
    request = pending(result.run_root)
    moved = tmp_path.with_name(tmp_path.name + '-moved')
    tmp_path.rename(moved)
    monkeypatch.chdir(moved)
    root = moved / result.run_root.relative_to(tmp_path)
    reply = answer(root, request['request_id'], 'APPROVED', by='operator')
    assert resume(root, state_dir=moved / 'custom-runs') == 0
    assert snapshot(root).terminal.data['value'] == reply


@pytest.mark.parametrize('halted', [False, True])
def test_settled_views_are_not_authority_and_live_resume_writer_follows_replay(tmp_path, monkeypatch, halted):
    body = None if halted else '(let* ((first (request-input question :returns Approval))) (request-input question :returns Approval))'
    _, result = start(tmp_path, monkeypatch, **({'body': body} if body else {}))
    root = result.run_root
    request = pending(root)
    reply = answer(root, request['request_id'], 'APPROVED', by='operator')
    assert load_evaluated_view(root)['status'] == 'interrupted'
    assert 'pending_host_input' not in load_evaluated_view(root)
    assert json.loads((root / 'state.json').read_text())['status'] == 'interrupted'
    with memo_writer_lock(root):
        assert load_evaluated_view(root)['status'] == ('settling' if halted else 'running')
    attempt = (root / request['result_path']).parent
    for name in ('request.json', 'request.prompt.txt', 'reply.json'):
        (attempt / name).write_text('corrupted evidence view')
    assert resume(root) == 0
    if not halted:
        second = pending(root)
        answer(root, second['request_id'], 'APPROVED', by='operator')
        assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == reply


def test_answer_rechecks_deadline_after_validation_without_repair(tmp_path, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: clock[0]))
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    original = owner._show_changes
    def cross(files_owner, frozen):
        observed = original(files_owner, frozen)
        clock[0] = request['deadline']
        return observed
    monkeypatch.setattr(owner, '_show_changes', cross)
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(root)
    with pytest.raises(owner.HostInputError, match='host_input_deadline_elapsed'):
        answer(root, request['request_id'], 'APPROVED', by='operator')
    assert files(root) == before


def test_resume_rebuilds_missing_pending_views_without_new_memo_rows(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    attempt = (root / request['result_path']).parent
    expected = (attempt / 'request.json').read_bytes()
    (attempt / 'request.json').unlink()
    (attempt / 'request.prompt.txt').write_text('stale')
    before = (root / 'memo.jsonl').read_bytes()
    assert resume(root) == 0
    assert (attempt / 'request.json').read_bytes() == expected
    assert owner._digest((attempt / 'request.prompt.txt').read_bytes()) == request['question_digest']
    assert (root / 'memo.jsonl').read_bytes() == before


def test_expiration_view_failure_does_not_append_failure_terminal(tmp_path, monkeypatch):
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: 100.0))
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: request['deadline']))
    original = WorkspaceFiles.write_atomic
    def fail_reply(files_owner, path, content, **kwargs):
        if Path(path).name == 'reply.json':
            raise OSError('injected expiration reply view failure')
        return original(files_owner, path, content, **kwargs)
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', fail_reply)
    assert resume(root) == 1
    assert snapshot(root).terminal is None
    assert rows(root)[-1]['value'] == {'variant': 'EXPIRED'}
    monkeypatch.setattr(WorkspaceFiles, 'write_atomic', original)
    assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == {'variant': 'EXPIRED'}
