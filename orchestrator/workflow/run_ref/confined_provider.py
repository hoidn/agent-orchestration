"""Retained provider authority, without transport admission or native authentication."""
import json
import threading

from .contracts import canonical_json_bytes, canonical_sha256
from .ledger import (RUN_REF_CONFINED_LEDGER_SCHEMA, RunRefLedgerError, _closed_mapping,
                     _nonempty_text, _positive_integer, _reject_nonfinite, _sha256)

_LIMITS = dict(max_requests=32, request_body_bytes=256 << 10, response_body_bytes=64 << 10,
              header_bytes=16 << 10, header_count=32, concurrency=1,
              native_frame_bytes=64 << 10, native_total_bytes=256 << 10)
_FIXED = dict(schema_version='run_ref_provider_policy.v1', native_version='0.162.1',
    native_source='092d3acd6bec3e3a14bdc7e7a2810ab628ab759d',
    native_binary='sha256:628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1',
    endpoint='https://chatgpt.com:443/backend-api/codex/responses', model='gpt-5.5', reasoning='low')
_POLICY_KEYS = frozenset(_LIMITS) | frozenset(_FIXED) | {
    'cli_digest', 'relay_digest', 'catalog', 'tools', 'config_recipe'}


def validate_provider_policy(policy):
    """Validate retained structure; admission must separately validate recipe/tool semantics."""
    _closed_mapping(policy, _POLICY_KEYS, field='provider policy')
    if any(type(policy[key]) is not int or policy[key] != value for key, value in _LIMITS.items()):
        raise RunRefLedgerError('provider policy limits invalid')
    if any(policy[key] != value for key, value in _FIXED.items()):
        raise RunRefLedgerError('provider policy fixed route or pins invalid')
    for key in ('cli_digest', 'relay_digest'):
        _sha256(policy[key], field=key)
    for key in ('catalog', 'tools', 'config_recipe'):
        _nonempty_text(policy[key], field=key)
        try:
            value = json.loads(policy[key], parse_constant=_reject_nonfinite)
            if canonical_json_bytes(value) != policy[key].encode('utf-8'):
                raise ValueError('noncanonical bytes')
        except (ValueError, TypeError, UnicodeError) as exc:
            raise RunRefLedgerError('provider policy retained bytes are not canonical JSON') from exc
    return policy


def provider_binding_digest(visit, policy_digest, *, account, origin, routing):
    """Hash public native identity only, never bearer material or an auth response."""
    _sha256(policy_digest, field='policy_digest')
    for key, value in (('account', account), ('origin', origin), ('routing', routing)):
        _nonempty_text(value, field=key)
    return canonical_sha256(dict(schema_version='run_ref_provider_public_binding.v1',
        visit=visit.record, policy_digest=policy_digest, auth_mode='chatgpt',
        account=account, origin=origin, routing=routing))


def provider_allowance(rows, visit):
    """Reduce all durable reservations of a semantic visit, including discarded ordinals."""
    state, reservation = None, None
    for row in rows:
        if row.visit != visit or row.schema_version != RUN_REF_CONFINED_LEDGER_SCHEMA:
            continue
        event = row.event
        if row.event_kind == 'provider_reservation':
            _closed_mapping(event, frozenset({'request', 'identity', 'attempt', 'policy_digest', 'policy'}),
                            field='provider reservation')
            request = _positive_integer(event['request'], field='request')
            _nonempty_text(event['identity'], field='identity')
            _positive_integer(event['attempt'], field='attempt')
            _sha256(event['policy_digest'], field='policy_digest')
            if state is None:
                policy = validate_provider_policy(event['policy'])
                if canonical_sha256(policy) != event['policy_digest']:
                    raise RunRefLedgerError('provider policy digest disagrees')
                state = dict(policy=dict(policy), policy_digest=event['policy_digest'],
                             consumed=0, binding_digest=None)
            elif event['policy'] is not None or event['policy_digest'] != state['policy_digest']:
                raise RunRefLedgerError('provider policy drift')
            if request != state['consumed'] + 1:
                raise RunRefLedgerError('provider reservation sequence disagrees')
            if request > state['policy']['max_requests']:
                raise RunRefLedgerError('provider request capacity exhausted')
            state['consumed'] = request
            reservation = row
        elif row.event_kind == 'provider_binding':
            _closed_mapping(event, frozenset({'request', 'reservation_digest', 'policy_digest', 'binding_digest'}),
                            field='provider binding')
            _positive_integer(event['request'], field='request')
            for name in ('reservation_digest', 'policy_digest', 'binding_digest'):
                _sha256(event[name], field=name)
            if (state is None or state['binding_digest'] is not None or reservation is None
                    or reservation.attempt_ordinal != row.attempt_ordinal
                    or event['request'] != state['consumed']
                    or event['reservation_digest'] != reservation.row_digest
                    or event['policy_digest'] != state['policy_digest']):
                raise RunRefLedgerError('provider binding reservation disagrees or binding repeated')
            state['binding_digest'] = event['binding_digest']
    return state


class VisitProviderAllowance:
    """Lifecycle-thread projection: only the parent emit/ack can authorize new work."""

    def __init__(self, state, visit, attempt_ordinal, emit):
        self.state = None if state is None else json.loads(canonical_json_bytes(state))
        self.visit, self.attempt_ordinal, self._emit = visit, attempt_ordinal, emit
        self._thread = threading.get_ident()
        self._failed, self._reservation = False, None

    def _acknowledge(self, kind, event):
        from .runtime import RunRefLifecycleAcknowledgement
        if self._failed or threading.get_ident() != self._thread:
            raise ValueError('provider lifecycle authority unavailable')
        # An uncertain append permanently poisons this incarnation, even when no ack returns.
        self._failed = True
        ack = self._emit(kind, event)
        if type(ack) is not RunRefLifecycleAcknowledgement:
            raise ValueError('provider acknowledgement authority invalid')
        row = ack.authority
        payload = dict(row.record)
        payload.pop('row_digest')
        if (row.visit != self.visit or row.attempt_ordinal != self.attempt_ordinal
                or row.schema_version != RUN_REF_CONFINED_LEDGER_SCHEMA
                or row.event_kind != kind or row.event != event or ack.stage != row.stage
                or canonical_sha256(payload) != row.row_digest):
            raise ValueError('provider acknowledgement authority disagrees')
        self._failed = False
        return row

    def reserve(self, policy, *, identity, attempt):
        from .runtime import RunRefRuntimeError
        if self._failed:
            raise ValueError('provider lifecycle authority unavailable')
        validate_provider_policy(policy)
        digest = canonical_sha256(policy)
        if self.state is not None and self.state['policy_digest'] != digest:
            raise RunRefLedgerError('provider policy drift')
        consumed = 0 if self.state is None else self.state['consumed']
        if consumed >= policy['max_requests']:
            raise RunRefRuntimeError('run_ref_budget_exhausted', 'provider request capacity exhausted')
        event = dict(request=consumed + 1, identity=_nonempty_text(identity, field='identity'),
            attempt=_positive_integer(attempt, field='attempt'), policy_digest=digest,
            policy=policy if self.state is None else None)
        row = self._acknowledge('provider_reservation', event)
        self.state = dict(policy=json.loads(canonical_json_bytes(policy)), policy_digest=digest,
            consumed=consumed + 1, binding_digest=None if self.state is None else self.state['binding_digest'])
        self._reservation = row
        return row

    def bind(self, *, account, origin, routing):
        if self._failed or self._reservation is None or threading.get_ident() != self._thread:
            raise ValueError('provider binding requires fresh reservation authority')
        digest = provider_binding_digest(self.visit, self.state['policy_digest'],
                                         account=account, origin=origin, routing=routing)
        if self.state['binding_digest'] is not None:
            if self.state['binding_digest'] != digest:
                self._failed = True
                raise RunRefLedgerError('provider binding drift')
            return digest
        event = dict(request=self.state['consumed'], reservation_digest=self._reservation.row_digest,
                     policy_digest=self.state['policy_digest'], binding_digest=digest)
        self._acknowledge('provider_binding', event)
        self.state['binding_digest'] = digest
        return digest
