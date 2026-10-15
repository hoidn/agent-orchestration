"""Internal provider authority only; these tests do not admit or launch a provider."""
from dataclasses import replace

import pytest

from orchestrator.workflow.run_ref import ledger
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_run_ref_ledger import _allocated_bindings, _visit


def _policy():
    return dict(schema_version='run_ref_provider_policy.v1', max_requests=32,
        request_body_bytes=256 << 10, response_body_bytes=64 << 10,
        header_bytes=16 << 10, header_count=32, concurrency=1,
        native_frame_bytes=64 << 10, native_total_bytes=256 << 10,
        native_version='0.162.1', native_source='092d3acd6bec3e3a14bdc7e7a2810ab628ab759d',
        native_binary='sha256:628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1',
        cli_digest='sha256:' + '1' * 64, relay_digest='sha256:' + '2' * 64,
        endpoint='https://chatgpt.com:443/backend-api/codex/responses',
        model='gpt-5.5', reasoning='low', catalog='{}', tools='[]', config_recipe='{}')


def _allocate(path, tmp_path, ordinal=1):
    return ledger.allocate_attempt(path, visit=_visit(), bindings=_allocated_bindings(tmp_path, ordinal=ordinal),
        confined_opening=dict(limit_ns=1000000, boot_id='boot', since_ns=ordinal * 100))


def _reserve(path, ordinal=1, request=1, *, policy=None, identity='leaf-a', attempt=1):
    policy = _policy() if policy is None else policy
    return ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=ordinal,
        event_kind='provider_reservation', event=dict(request=request, identity=identity, attempt=attempt,
            policy_digest=canonical_sha256(policy), policy=policy if request == 1 else None))


def test_reservation_spends_capacity_preserving_work_and_wall(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    first = _allocate(path, tmp_path)
    reservation = _reserve(path)
    rows = ledger.load_attempt_ledger(path).rows
    assert reservation.stage == first.stage and reservation.bindings == first.bindings
    assert ledger.confined_budget(rows, _visit())['active']['opening_sequence'] == first.sequence
    from orchestrator.workflow.run_ref.confined_provider import provider_allowance
    state = provider_allowance(rows, _visit())
    assert state['consumed'] == 1 and state['binding_digest'] is None
    assert state['policy'] == _policy()


def test_capacity_carries_across_k4_without_refund_and_last_permit_can_close(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    reservation = _reserve(path)
    binding = 'sha256:' + 'b' * 64
    ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1, event_kind='provider_binding',
        event=dict(request=1, reservation_digest=reservation.row_digest,
                   policy_digest=canonical_sha256(_policy()), binding_digest=binding))
    ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1, event_kind='budget_close',
        event=dict(opening_sequence=1, boot_id='boot', until_ns=110))
    ledger.record_discarded_attempt(path, visit=_visit(), attempt_ordinal=1,
        disposition_digest='sha256:' + 'a' * 64, workspace_path=_allocated_bindings(tmp_path).workspace_path)
    _allocate(path, tmp_path, ordinal=2)
    for request in range(2, 33):
        _reserve(path, ordinal=2, request=request, identity='leaf-b')
    with pytest.raises(ledger.RunRefLedgerError, match='exhausted'):
        _reserve(path, ordinal=2, request=33)
    rows = ledger.load_attempt_ledger(path).rows
    opening = next(row for row in rows if row.event_kind == 'allocation' and row.attempt_ordinal == 2)
    ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=2, event_kind='budget_close',
        event=dict(opening_sequence=opening.sequence, boot_id='boot', until_ns=210))
    from orchestrator.workflow.run_ref.confined_provider import provider_allowance
    state = provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())
    assert state['consumed'] == 32 and state['binding_digest'] == binding


@pytest.mark.parametrize('change', [dict(request=2), dict(policy_digest='sha256:' + 'a' * 64),
    dict(bearer='must-never-be-durable'), dict(attempt=True)])
def test_reservation_closed_fields_sequence_and_policy_authority(tmp_path, change):
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    event = dict(request=1, identity='leaf-a', attempt=1,
                 policy_digest=canonical_sha256(_policy()), policy=_policy())
    before = path.read_bytes()
    with pytest.raises(ledger.RunRefLedgerError):
        ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1,
            event_kind='provider_reservation', event={**event, **change})
    assert path.read_bytes() == before


def test_binding_is_single_visit_policy_scoped_digest_and_retained_on_recovery(tmp_path):
    from orchestrator.workflow.run_ref.confined_provider import provider_binding_digest, provider_allowance
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    row = _reserve(path)
    digest = provider_binding_digest(_visit(), canonical_sha256(_policy()),
        account='public-account-id', origin='chatgpt', routing='managed')
    assert digest == canonical_sha256(dict(schema_version='run_ref_provider_public_binding.v1',
        visit=_visit().record, policy_digest=canonical_sha256(_policy()), auth_mode='chatgpt',
        account='public-account-id', origin='chatgpt', routing='managed'))
    assert digest != provider_binding_digest(replace(_visit(), visit_count=2), canonical_sha256(_policy()),
        account='public-account-id', origin='chatgpt', routing='managed')
    event = dict(request=1, reservation_digest=row.row_digest, policy_digest=canonical_sha256(_policy()),
                 binding_digest=digest)
    ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1,
        event_kind='provider_binding', event=event)
    with pytest.raises(ledger.RunRefLedgerError, match='binding'):
        ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1,
            event_kind='provider_binding', event=event)
    state = provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())
    assert state['binding_digest'] == digest
    assert b'public-account-id' not in path.read_bytes()


def test_policy_preserves_exact_canonical_nonsecret_bytes_and_rejects_drift(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    _reserve(path)
    with pytest.raises(ledger.RunRefLedgerError, match='policy drift'):
        _reserve(path, request=2, policy={**_policy(), 'config_recipe': '{"changed":true}'})
    bad = {**_policy(), 'tools': '[ ]'}
    other = tmp_path / 'other.jsonl'
    _allocate(other, tmp_path)
    with pytest.raises(ledger.RunRefLedgerError, match='canonical'):
        _reserve(other, policy=bad)


def _projection(path, tmp_path, *, lost=False, foreign=False):
    from orchestrator.workflow.run_ref.confined_provider import VisitProviderAllowance, provider_allowance
    from orchestrator.workflow.run_ref.runtime import RunRefLifecycleAcknowledgement, RunRefLifecycleEvent
    rows = ledger.load_attempt_ledger(path).rows
    def side(kind, event):
        row = ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=rows[-1].attempt_ordinal,
            event_kind=kind, event=event)
        if lost:
            raise ConnectionError('ack lost after durable append')
        request = RunRefLifecycleEvent.build(sequence=row.sequence, event_kind=kind, stage=row.stage,
            visit=_visit(), attempt_ordinal=row.attempt_ordinal, effect_instance_root=tmp_path,
            payload={'event': event})
        if foreign:
            row = replace(row, visit=replace(_visit(), visit_count=2))
        return RunRefLifecycleAcknowledgement._for_durable_row(request, authority=row)
    return VisitProviderAllowance(provider_allowance(rows, _visit()), _visit(), rows[-1].attempt_ordinal, side)


@pytest.mark.parametrize('lost,foreign', [(True, False), (False, True)])
def test_projection_requires_exact_ack_and_never_reuses_uncertain_reservation(tmp_path, lost, foreign):
    from orchestrator.workflow.run_ref.confined_provider import provider_allowance
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    owner = _projection(path, tmp_path, lost=lost, foreign=foreign)
    with pytest.raises((ConnectionError, ValueError)):
        owner.reserve(_policy(), identity='leaf-a', attempt=1)
    assert owner.state is None
    assert provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())['consumed'] == 1
    with pytest.raises(ValueError, match='authority'):
        owner.reserve(_policy(), identity='leaf-a', attempt=1)
    recovered = _projection(path, tmp_path)
    row = recovered.reserve(_policy(), identity='leaf-b', attempt=2)
    assert row.event['request'] == 2


def test_projection_binding_matches_across_leaves_and_rejects_drift_without_append(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    owner = _projection(path, tmp_path)
    owner.reserve(_policy(), identity='leaf-a', attempt=1)
    digest = owner.bind(account='account-a', origin='chatgpt', routing='managed')
    recovered = _projection(path, tmp_path)
    recovered.reserve(_policy(), identity='leaf-b', attempt=1)
    before = path.read_bytes()
    assert recovered.bind(account='account-a', origin='chatgpt', routing='managed') == digest
    with pytest.raises(ledger.RunRefLedgerError, match='binding drift'):
        recovered.bind(account='account-b', origin='chatgpt', routing='managed')
    assert path.read_bytes() == before


def test_duplicate_ack_cannot_authorize_next_reservation(tmp_path):
    from orchestrator.workflow.run_ref.runtime import RunRefLifecycleAcknowledgement, RunRefLifecycleEvent
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    owner = _projection(path, tmp_path)
    row = owner.reserve(_policy(), identity='leaf-a', attempt=1)
    event = RunRefLifecycleEvent.build(sequence=row.sequence, event_kind=row.event_kind, stage=row.stage,
        visit=_visit(), attempt_ordinal=1, effect_instance_root=tmp_path, payload={'event': row.event})
    old = RunRefLifecycleAcknowledgement._for_durable_row(event, authority=row)
    owner._emit = lambda *_args: old
    with pytest.raises(ValueError, match='acknowledgement'):
        owner.reserve(_policy(), identity='leaf-a', attempt=1)
    assert owner.state['consumed'] == 1


def test_append_precedes_ack_and_local_permission_never_appears_early(tmp_path):
    from threading import Event, Thread
    from orchestrator.workflow.run_ref.confined_provider import VisitProviderAllowance, provider_allowance
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    written, release = Event(), Event()
    owners, errors, granted = [], [], []
    def run():
        try:
            base = _projection(path, tmp_path)
            def delayed(kind, event):
                ack = base._emit(kind, event)
                written.set()
                assert release.wait(5)
                return ack
            owner = VisitProviderAllowance(None, _visit(), 1, delayed)
            owners.append(owner)
            granted.append(owner.reserve(_policy(), identity='leaf-a', attempt=1))
        except BaseException as exc:
            errors.append(exc)
            written.set()
    thread = Thread(target=run)
    thread.start()
    try:
        assert written.wait(5)
        assert not errors and not granted and owners[0].state is None
        assert provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())['consumed'] == 1
    finally:
        release.set()
        thread.join(5)
    assert not thread.is_alive() and not errors and len(granted) == 1


def test_reader_rejects_coherently_rehashed_missing_policy_authority(tmp_path):
    import json
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    _reserve(path)
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    rows[-1]['event']['policy'] = None
    rows[-1]['row_digest'] = canonical_sha256({key: value for key, value in rows[-1].items() if key != 'row_digest'})
    path.write_bytes(b''.join(canonical_json_bytes(row) + b'\n' for row in rows))
    with pytest.raises(ledger.RunRefLedgerError, match='provider policy'):
        ledger.load_attempt_ledger(path)


def test_binding_requires_new_reservation_and_closed_wall_refuses_provider_facts(tmp_path):
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    owner = _projection(path, tmp_path)
    with pytest.raises(ValueError, match='fresh reservation'):
        owner.bind(account='a', origin='chatgpt', routing='managed')
    ledger.append_confined_event(path, visit=_visit(), attempt_ordinal=1, event_kind='budget_close',
        event=dict(opening_sequence=1, boot_id='boot', until_ns=110))
    with pytest.raises(ledger.RunRefLedgerError, match='active child budget'):
        _reserve(path)


def test_policy_uses_existing_evidence_allowance_without_an_extra_rpc_sized_cap(tmp_path):
    import json
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    policy = {**_policy(), 'config_recipe': json.dumps({'template': 'x' * (300 << 10)}, separators=(',', ':'))}
    _reserve(path, policy=policy)
    from orchestrator.workflow.run_ref.confined_provider import provider_allowance
    assert provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())['policy'] == policy


def test_binding_append_with_lost_ack_is_retained_and_incarnation_cannot_continue(tmp_path):
    from orchestrator.workflow.run_ref.confined_provider import provider_allowance
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    owner = _projection(path, tmp_path)
    owner.reserve(_policy(), identity='leaf-a', attempt=1)
    emit = owner._emit
    def lost(kind, event):
        emit(kind, event)
        raise ConnectionError('binding ack lost')
    owner._emit = lost
    with pytest.raises(ConnectionError):
        owner.bind(account='account-a', origin='chatgpt', routing='managed')
    assert owner.state['binding_digest'] is None
    state = provider_allowance(ledger.load_attempt_ledger(path).rows, _visit())
    assert state['consumed'] == 1 and state['binding_digest'] is not None
    with pytest.raises(ValueError, match='authority'):
        owner.reserve(_policy(), identity='leaf-b', attempt=1)


@pytest.mark.parametrize('field', ['catalog', 'tools', 'config_recipe'])
@pytest.mark.parametrize('payload', ['NaN', '{"x":Infinity}', '{"x":-Infinity}'])
def test_policy_nested_json_rejects_nonfinite_constants(field, payload):
    from orchestrator.workflow.run_ref.confined_provider import validate_provider_policy
    with pytest.raises(ledger.RunRefLedgerError, match='canonical JSON'):
        validate_provider_policy({**_policy(), field: payload})
