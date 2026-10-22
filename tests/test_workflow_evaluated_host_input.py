from tests.workflow_evaluated_host_input_helpers import start, rows, resume, snapshot


def test_request_suspends_and_resumes_without_dispatch_or_journal_changes(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)
    assert result.exit_code == 0
    run_root = result.run_root
    records = rows(run_root)
    assert [row['record'] for row in records] == ['started', 'committed', 'started', 'suspended']
    request = records[-2]['host_request']
    assert request['deadline'] > request['created_at']
    assert snapshot(run_root).terminal is None
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from orchestrator.host_input import pending
    assert load_evaluated_view(run_root)['pending_host_input'] == pending(run_root)
    before = (run_root / 'memo.jsonl').read_bytes()
    for _ in range(2):
        assert resume(run_root) == 0
        assert (run_root / 'memo.jsonl').read_bytes() == before
    assert (tmp_path / 'dispatches.txt').read_text().splitlines() == ['emit']


def test_answer_is_durable_idempotent_and_continuation_requires_resume(tmp_path, monkeypatch):
    from orchestrator.host_input import pending, answer
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    reply = answer(root, request['request_id'], 'APPROVED', by='operator', attestation='ticket-7')
    assert reply == {'variant': 'ANSWERED', 'value': 'APPROVED', 'by': 'operator'}
    assert pending(root) is None
    assert snapshot(root).terminal is None
    before = (root / 'memo.jsonl').read_bytes()
    # Exact duplicates do not rebuild source or reread current evidence.
    source = tmp_path / 'host' / 'entry.orc'
    original = source.read_bytes()
    source.unlink()
    assert answer(root, request['request_id'], 'APPROVED', by='operator', attestation='ticket-7') == reply
    assert (root / 'memo.jsonl').read_bytes() == before
    source.write_bytes(original)
    assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == reply
    commit = snapshot(root).active_commits[request['identity']]
    assert not (root / commit.data['result_path']).exists()
    assert (root / commit.data['result_path']).with_name('reply.json').is_file()


def test_cancel_and_resume_return_typed_outcome(tmp_path, monkeypatch):
    from orchestrator.host_input import pending, cancel
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    assert cancel(result.run_root, request['request_id'], by='operator') == {'variant': 'CANCELLED', 'by': 'operator'}
    assert resume(result.run_root) == 0
    assert snapshot(result.run_root).terminal.data['value']['variant'] == 'CANCELLED'


import json
import pytest
from copy import deepcopy
from types import SimpleNamespace
from orchestrator.workflow.evaluated import host_input as owner
from tests.workflow_evaluated_host_input_helpers import files


@pytest.mark.parametrize('variant', ['answer', 'cancel'])
def test_deadline_is_observed_only_by_resume(tmp_path, monkeypatch, variant):
    from orchestrator.host_input import pending, answer, cancel
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: 100.0))
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    monkeypatch.setattr(owner, 'time', SimpleNamespace(time=lambda: request['deadline']))
    before = files(root)
    assert pending(root)['deadline_elapsed'] is True
    assert files(root) == before
    with pytest.raises(owner.HostInputError, match='host_input_deadline_elapsed'):
        if variant == 'answer':
            answer(root, request['request_id'], 'APPROVED', by='operator')
        else:
            cancel(root, request['request_id'], by='operator')
    assert files(root) == before
    assert resume(root) == 0
    assert snapshot(root).terminal.data['value'] == {'variant': 'EXPIRED'}
    assert rows(root)[-2]['host_reply']['origin'] == 'runtime'


@pytest.mark.parametrize('value,by,attestation,override', [
    ('INVALID', 'operator', None, False), ({'variant': 'ANSWERED', 'value': 'APPROVED', 'by': 'forged'}, 'operator', None, False),
    (float('nan'), 'operator', None, False), ('APPROVED', '', None, False), ('APPROVED', 'a\0b', None, False),
    ('APPROVED', 'operator', {}, False), ('APPROVED', 'operator', None, 1),
])
def test_invalid_submissions_preserve_tail_and_views(tmp_path, monkeypatch, value, by, attestation, override):
    from orchestrator.host_input import pending, answer
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    request = pending(root)
    with (root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(root)
    with pytest.raises(ValueError):
        answer(root, request['request_id'], value, by=by, attestation=attestation, accept_changed_evidence=override)
    assert files(root) == before


@pytest.mark.parametrize('mutation', ['timeout', 'show', 'question', 'nominal', 'reply'])
def test_source_free_readers_bind_frozen_payload_to_semantics_and_checked_node(tmp_path, monkeypatch, mutation):
    from orchestrator.host_input import pending
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    _, result = start(tmp_path, monkeypatch)
    root = result.run_root
    records = rows(root)
    request = records[-2]['host_request']
    if mutation == 'timeout':
        request['timeout_sec'] = 1
        request['deadline'] = request['created_at'] + 1
    elif mutation == 'show':
        request['show'] = [{'path': 'reports/forged.txt', 'contract': {'kind': 'path', 'name': 'host/entry::Report', 'under': 'reports', 'must_exist_target': True}, 'sha256': 'sha256:' + '0' * 64}]
    elif mutation == 'question':
        request['question'] = 'Forged'
        request['question_digest'] = owner._digest(b'Forged')
    elif mutation == 'nominal':
        request['answer_contract']['name'] = 'forged::Approval'
        request['answer_contract_digest'] = canonical_sha256(request['answer_contract'])
        request['reply_contract']['name'] = 'std/host::HostReply[forged::Approval]'
        request['reply_contract_digest'] = canonical_sha256(request['reply_contract'])
    else:
        request['reply_contract']['variants'][0]['fields'].append({'name': 'extra', 'type': {'kind': 'primitive', 'name': 'String'}})
        request['reply_contract_digest'] = canonical_sha256(request['reply_contract'])
    request['payload_digest'] = canonical_sha256({k: v for k, v in request.items() if k != 'payload_digest'})
    (root / 'memo.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
    before = files(root)
    for reader in (pending, load_evaluated_view):
        with pytest.raises(ValueError):
            reader(root)
        assert files(root) == before


def test_duplicate_uses_canonical_json_value_identity(tmp_path, monkeypatch):
    from orchestrator.host_input import pending, answer
    _, result = start(tmp_path, monkeypatch, answer_type='Choice', declarations='(defunion Choice (DECIDE (payload Value)))')
    request = pending(result.run_root)
    answer(result.run_root, request['request_id'], {'variant': 'DECIDE', 'payload': 1}, by='operator')
    before = files(result.run_root)
    with pytest.raises(owner.HostInputError, match='request_already_settled'):
        answer(result.run_root, request['request_id'], {'variant': 'DECIDE', 'payload': True}, by='operator')
    assert files(result.run_root) == before


@pytest.mark.parametrize('case', ['payload-missing', 'payload-extra', 'request-id', 'payload-digest', 'start-proof',
    'suspend-attempt', 'suspend-id', 'suspend-duplicate', 'suspend-command', 'terminal', 'another-start'])
def test_reducer_refuses_malformed_request_transitions(tmp_path, monkeypatch, case):
    from orchestrator.workflow.evaluated.memo import reduce_memo, MemoError
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.authority import load_run_authority
    _, result = start(tmp_path, monkeypatch)
    records = rows(result.run_root)
    if case == 'payload-missing':
        del records[-2]['host_request']
    elif case == 'payload-extra':
        records[-2]['host_request']['extra'] = True
    elif case == 'request-id':
        records[-2]['host_request']['request_id'] = 'forged'
    elif case == 'payload-digest':
        records[-2]['host_request']['payload_digest'] = 'sha256:' + '0' * 64
    elif case == 'start-proof':
        records[-2]['proof'] = {}
    elif case == 'suspend-attempt':
        records[-1]['attempt'] += 1
    elif case == 'suspend-id':
        records[-1]['request_id'] = 'sha256:' + '0' * 64
    elif case == 'suspend-duplicate':
        records.append(deepcopy(records[-1]))
    elif case == 'suspend-command':
        records[-1]['identity'] = records[0]['identity']
    elif case == 'terminal':
        records.append({'record': 'terminal', 'outcome': 'completed', 'value': None})
    elif case == 'another-start':
        another = deepcopy(records[0])
        another['attempt'] += 1
        records.append(another)
    raw = b''.join(json.dumps(row).encode() + b'\n' for row in records)
    with pytest.raises(MemoError, match='memo_inconsistent'):
        reduce_memo(raw, site_classes(load_run_authority(result.run_root).program))


@pytest.mark.parametrize('case', ['missing-suspension', 'provenance-missing', 'provenance-extra', 'origin', 'principal',
    'unknown-variant', 'extra-value', 'result-digest', 'proof', 'runtime-answer', 'early-expiration'])
def test_reducer_refuses_invalid_reply_and_provenance(tmp_path, monkeypatch, case):
    from orchestrator.host_input import pending, answer
    from orchestrator.workflow.evaluated.memo import reduce_memo, MemoError
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    answer(result.run_root, request['request_id'], 'APPROVED', by='operator')
    records = rows(result.run_root)
    commit = records[-1]
    if case == 'missing-suspension':
        records.pop(-2)
    elif case == 'provenance-missing':
        del commit['host_reply']['attestation']
    elif case == 'provenance-extra':
        commit['host_reply']['extra'] = None
    elif case == 'origin':
        commit['host_reply']['origin'] = 'unknown'
    elif case == 'principal':
        commit['value']['by'] = ''
    elif case == 'unknown-variant':
        commit['value']['variant'] = 'UNKNOWN'
    elif case == 'extra-value':
        commit['value']['extra'] = True
    elif case == 'result-digest':
        commit['result_digest'] = 'sha256:' + '0' * 64
    elif case == 'proof':
        commit['proof'] = {}
    elif case == 'runtime-answer':
        commit['host_reply']['origin'] = 'runtime'
    elif case == 'early-expiration':
        commit['value'] = {'variant': 'EXPIRED'}
        commit['host_reply'] = {'request_id': request['request_id'], 'origin': 'runtime', 'reason': 'deadline', 'accept_changed_evidence': False, 'evidence_changes': []}
    if case != 'result-digest':
        commit['result_digest'] = canonical_sha256(commit['value'])
    raw = b''.join(json.dumps(row).encode() + b'\n' for row in records)
    with pytest.raises(MemoError, match='memo_inconsistent'):
        reduce_memo(raw, site_classes(load_run_authority(result.run_root).program))


@pytest.mark.parametrize('applied', [False, True])
def test_question_evidence_includes_the_answer_contract_through_shared_renderer(tmp_path, monkeypatch, applied):
    from orchestrator.host_input import pending
    from orchestrator.workflow.evaluated import prompts
    recorded = []
    original = getattr(prompts, 'render_answer_contract_block', None)
    assert original is not None
    def render(descriptor):
        recorded.append(descriptor)
        return original(descriptor)
    monkeypatch.setattr(prompts, 'render_answer_contract_block', render)
    kwargs = dict(question='(approval :summary question)', declarations='(defprompt approval (:fills (summary :text)) -> Approval "{summary}")') if applied else {}
    _, result = start(tmp_path, monkeypatch, **kwargs)
    request = pending(result.run_root)
    assert recorded and all(d == request['answer_contract'] for d in recorded)
    evidence = (result.run_root / request['result_path']).with_name('request.prompt.txt').read_bytes()
    assert owner._digest(evidence) == request['question_digest']


@pytest.mark.parametrize('value', [0, -1])
def test_dynamic_timeout_refuses_before_start(tmp_path, monkeypatch, value):
    _, result = start(tmp_path, monkeypatch, params=' (duration Int)', options=':timeout-sec duration', inputs=[f'duration={value}'])
    assert result.exit_code == 1
    assert not [row for row in rows(result.run_root) if 'host_request' in row]


@pytest.mark.parametrize('bad', [True, 1.0, 'a', None, {'variant': 'PICK'}, {'variant': 'PICK', 'count': 1, 'extra': True}])
def test_union_answer_rejects_missing_extra_or_wrong_payload_types(tmp_path, monkeypatch, bad):
    from orchestrator.host_input import pending, answer
    _, result = start(tmp_path, monkeypatch, answer_type='Choice', declarations='(defunion Choice (PICK (count Int)) (NONE))')
    request = pending(result.run_root)
    before = files(result.run_root)
    with pytest.raises(owner.HostInputError) as error:
        answer(result.run_root, request['request_id'], bad, by='operator')
    assert error.value.code == 'host_input_answer_invalid'
    assert files(result.run_root) == before


def test_initial_shown_directory_is_refused_before_request_start(tmp_path, monkeypatch):
    (tmp_path / 'reports').mkdir()
    _, result = start(tmp_path, monkeypatch, declarations='(defpath Report :kind relpath :under "reports" :must-exist true)',
        params=' (report Report)', inputs=['report=reports'], options=':show (report)')
    assert result.exit_code == 1
    assert not [row for row in rows(result.run_root) if 'host_request' in row]


@pytest.mark.parametrize('bad_path', ['../escape', '/absolute', 'elsewhere/a', 'reports/../a'])
def test_source_free_reply_checks_nested_path_constraints(tmp_path, monkeypatch, bad_path):
    from orchestrator.host_input import pending, answer
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    (tmp_path / 'reports').mkdir()
    _, result = start(tmp_path, monkeypatch, answer_type='Choice', declarations='''
        (defpath Report :kind relpath :under "reports" :must-exist false)
        (defunion Choice (PICK (report Report)))''')
    request = pending(result.run_root)
    answer(result.run_root, request['request_id'], {'variant': 'PICK', 'report': 'reports/a'}, by='operator')
    records = rows(result.run_root)
    commit = records[-1]
    commit['value']['value']['report'] = bad_path
    commit['result_digest'] = canonical_sha256(commit['value'])
    (result.run_root / 'memo.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
    before = files(result.run_root)
    for reader in (pending, load_evaluated_view):
        with pytest.raises(ValueError):
            reader(result.run_root)
        assert files(result.run_root) == before


@pytest.mark.parametrize('value', [10 ** 400, -(10 ** 400), float('inf'), float('nan'), True])
def test_timestamp_validator_refuses_unrepresentable_finite_times(value):
    assert owner._finite_time(value) is False


def test_free_text_answer_without_timeout_uses_same_typed_lifecycle(tmp_path, monkeypatch):
    from orchestrator.host_input import pending, answer
    _, result = start(tmp_path, monkeypatch, answer_type='String', options='')
    request = pending(result.run_root)
    assert request['deadline'] is None and request['timeout_sec'] is None
    text = 'An operator decision'
    reply = answer(result.run_root, request['request_id'], text, by='operator', attestation='')
    assert reply['value'] == text
    assert resume(result.run_root) == 0
    assert snapshot(result.run_root).terminal.data['value'] == reply


@pytest.mark.parametrize('settled', [False, True])
def test_self_consistent_forged_nominal_contract_cannot_supply_its_own_authority(tmp_path, monkeypatch, settled):
    from orchestrator.host_input import pending, answer
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    if settled:
        answer(result.run_root, request['request_id'], 'APPROVED', by='operator')
    records = rows(result.run_root)
    started = next(row for row in records if 'host_request' in row)
    frozen = started['host_request']
    frozen['answer_contract']['name'] = 'forged::Approval'
    frozen['reply_contract']['name'] = 'std/host::HostReply[forged::Approval]'
    frozen['reply_contract']['variants'][0]['fields'][0]['type'] = deepcopy(frozen['answer_contract'])
    for key in ('answer_contract', 'reply_contract'):
        frozen[key + '_digest'] = canonical_sha256(frozen[key])
        started['input_parts'][key] = frozen[key + '_digest']
    started['input_digest'] = canonical_sha256(started['input_parts'])
    frozen['payload_digest'] = canonical_sha256({k: v for k, v in frozen.items() if k != 'payload_digest'})
    if settled:
        records[-1]['input_parts'] = deepcopy(started['input_parts'])
        records[-1]['input_digest'] = started['input_digest']
    (result.run_root / 'memo.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
    before = files(result.run_root)
    for reader in (pending, load_evaluated_view):
        with pytest.raises(ValueError, match='checked node'):
            reader(result.run_root)
        assert files(result.run_root) == before


@pytest.mark.parametrize('settled', [False, True])
@pytest.mark.parametrize('bad', [{'variant': 'PICK', 'count': True}, {'variant': 'PICK'}, {'variant': 'PICK', 'count': 1, 'extra': True}])
def test_public_invalid_answer_code_preserves_fresh_and_duplicate_journals(tmp_path, monkeypatch, settled, bad):
    from orchestrator.host_input import pending, answer
    source, result = start(tmp_path, monkeypatch, answer_type='Choice', declarations='(defunion Choice (PICK (count Int)) (NONE))')
    request = pending(result.run_root)
    if settled:
        answer(result.run_root, request['request_id'], {'variant': 'PICK', 'count': 1}, by='operator')
        source.unlink()
    with (result.run_root / 'memo.jsonl').open('ab') as stream:
        stream.write(b'{"torn":')
    before = files(result.run_root)
    with pytest.raises(owner.HostInputError) as error:
        answer(result.run_root, request['request_id'], bad, by='operator')
    assert error.value.code == 'host_input_answer_invalid'
    assert '$/value' in str(error.value)
    assert files(result.run_root) == before


@pytest.mark.parametrize('mutation', ['missing', 'spurious'])
def test_readonly_request_validation_binds_reached_operand_dependencies(tmp_path, monkeypatch, mutation):
    from orchestrator.host_input import pending
    from orchestrator.workflow.evaluated.views import load_evaluated_view
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    _, result = start(tmp_path, monkeypatch, options=':timeout-sec before' if mutation == 'missing' else ':timeout-sec 60')
    assert result.exit_code == 0
    request = pending(result.run_root)
    records = rows(result.run_root)
    frozen = next(row['host_request'] for row in records if 'host_request' in row)
    producer = next(row['identity'] for row in records if row.get('effect_class') == 'command')
    assert frozen['depends_on'] == ([producer] if mutation == 'missing' else [])
    frozen['depends_on'] = [] if mutation == 'missing' else [producer]
    frozen['payload_digest'] = canonical_sha256({k: v for k, v in frozen.items() if k != 'payload_digest'})
    (result.run_root / 'memo.jsonl').write_text(''.join(json.dumps(row) + '\n' for row in records))
    before = files(result.run_root)
    for reader in (pending, load_evaluated_view):
        with pytest.raises(ValueError, match='dependencies'):
            reader(result.run_root)
        assert files(result.run_root) == before
