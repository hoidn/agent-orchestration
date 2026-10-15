"""Private transport core only: no native processes, listener or public admission."""
from __future__ import annotations

import importlib
import io
import json
from pathlib import Path

import pytest


def module():
    try:
        return importlib.import_module('orchestrator.providers.inference_gateway')
    except ModuleNotFoundError as exc:
        if exc.name != 'orchestrator.providers.inference_gateway':
            raise
        pytest.fail('private inference transport core is not implemented')


def test_native_frames_limit_exact_plus_one_and_never_reset_per_owner():
    m = module()
    frame = m.NativeFrames()
    raw = b'{"padding":"' + b'x' * (65536 - len(b'{"padding":""}')) + b'"}'
    frame.feed(raw + b'\n')
    assert frame.take()['padding']
    with pytest.raises(m.InferenceTransportRefused):
        m.NativeFrames().feed(raw + b'x\n')
    frame = m.NativeFrames()
    notification = b'{"method":"notification","padding":"' + b'x' * 60000 + b'"}\n'
    for _ in range(4):
        frame.feed(notification)
        assert frame.take()['method'] == 'notification'
    with pytest.raises(m.InferenceTransportRefused):
        frame.feed(notification)
    frame = m.NativeFrames()
    raw = b'{"padding":"' + b'x' * (65535 - len(b'{"padding":""}')) + b'"}\n'
    for _ in range(4):
        frame.feed(raw)
        assert frame.take()['padding']
    assert len(raw) * 4 == 262144
    with pytest.raises(m.InferenceTransportRefused):
        frame.feed(b'x')


def snapshot(account='account-A', token='private-native-secret', origin='https://chatgpt.com'):
    account_read = {'requiresOpenaiAuth': True, 'account': {'type': 'chatgpt'},
                    'workspaceRouting': {'chatgptAccountId': account, 'backendOrigin': origin,
                                         'accountRoutingOverride': 'NO_CONSTRAINT'}}
    return [{'result': account_read},
            {'result': {'requiresOpenaiAuth': True, 'authMethod': 'chatgpt', 'authToken': token}},
            {'result': json.loads(json.dumps(account_read))}]


def test_native_binding_coherence_and_secret_repr():
    m = module()
    auth = m.validate_native_snapshot(snapshot())
    assert auth.account == 'account-A'
    assert auth.bearer == 'private-native-secret'
    assert 'private-native-secret' not in repr(auth)
    assert 'account-A' not in repr(auth)
    changed = snapshot()
    changed[-1]['result']['workspaceRouting']['chatgptAccountId'] = 'account-B'
    for bad in [changed, snapshot(origin='https://example.invalid'), snapshot(token='bad\r\nheader')]:
        with pytest.raises(m.InferenceTransportRefused) as error:
            m.validate_native_snapshot(bad)
        assert 'private-native-secret' not in str(error.value)


def test_http_headers_exact_limit_plus_one_and_duplicates():
    m = module()
    prefix = b'X: '
    tail = b'\r\n\r\n'
    exact = prefix + b'x' * (16384 - len(prefix) - len(tail)) + tail
    assert m.parse_header_block(exact)['x']
    for raw in [exact[:-4] + b'x' + tail, b'X: y\r\n' * 33 + b'\r\n',
                b'Content-Length: 1\r\ncontent-length: 1\r\n\r\n', b'X: a\r\n folded\r\n\r\n']:
        with pytest.raises(m.InferenceTransportRefused):
            m.parse_header_block(raw)


def test_qualified_policy_retains_exact_catalog_and_rejects_semantic_tampering():
    m = module()
    policy = m.qualified_policy()
    original = Path(m.__file__).parent / 'inference_assets' / 'run-ref-native-catalog-0.162.1.json'
    assert policy.catalog_bytes == original.read_bytes()
    # catalog is a canonical JSON string containing the exact original UTF-8 text.
    assert json.loads(policy.record['catalog']).encode() == original.read_bytes()
    assert policy.record['max_requests'] == 32
    for field, value in [('catalog', json.dumps('{}')), ('tools', json.dumps('[]')),
                         ('config_recipe', '{}'), ('relay_digest', 'sha256:' + '0' * 64),
                         ('cli_digest', 'sha256:' + '0' * 64), ('reasoning', 'high')]:
        bad = {**policy.record, field: value}
        with pytest.raises(m.InferenceTransportRefused):
            m.validate_transport_policy(bad)
    with pytest.raises(m.InferenceTransportRefused):
        m.qualified_policy(require_hard_token_cap=True)
    with pytest.raises(m.InferenceTransportRefused):
        m.qualified_policy(require_hard_cost_cap=True)


def test_native_launch_recipe_fixed_environment_guard_and_no_spawn(tmp_path, monkeypatch):
    m = module()
    home = tmp_path / 'native-home'
    home.mkdir()
    binary = tmp_path / 'codex'
    binary.write_bytes(b'synthetic installation input')
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000)
    with pytest.raises(m.InferenceTransportRefused):
        m.prepare_native_launch(m.qualified_policy(), binary=binary, owner_dir=tmp_path / 'owner',
                                native_home=home, host_home=tmp_path, gate=gate)
    monkeypatch.setattr(m, '_file_digest', lambda _path: m.NATIVE_BINARY_DIGEST)
    launch = m.prepare_native_launch(m.qualified_policy(), binary=binary, owner_dir=tmp_path / 'owner',
                                     native_home=home, host_home=tmp_path, gate=gate)
    assert launch.argv[-4:] == ('app-server', '--strict-config', '--listen', 'stdio://')
    assert launch.env == {'PATH': '/usr/bin:/bin', 'HOME': str(tmp_path), 'CODEX_HOME': str(home),
                          'LANG': 'C.UTF-8', 'RUST_LOG': 'off',
                          'CODEX_INTERNAL_APP_SERVER_REMOTE_CONTROL_DISABLED': '1'}
    assert not any('remote-control' in value for value in launch.argv)
    assert (tmp_path / 'owner/pinned-models.json').read_bytes() == m.qualified_policy().catalog_bytes
    (home / 'environments.toml').symlink_to(tmp_path / 'unreadable-remote-canary')
    with pytest.raises(m.InferenceTransportRefused):
        m.prepare_native_launch(m.qualified_policy(), binary=binary, owner_dir=tmp_path / 'owner-2',
                                native_home=home, host_home=tmp_path, gate=gate)


class RPCProcess:
    """Native-protocol stand-in using pipes; never a subprocess or sandbox."""
    def __init__(self, respond):
        import os
        import threading
        self._os = os
        reader, self._writer = os.pipe()
        self.stdout = os.fdopen(reader, 'rb', buffering=0)
        self.stderr = None
        self.returncode = None
        self.requests = []
        self.threads = []
        self.respond = respond
        process = self

        class Input:
            def write(self, raw):
                request = json.loads(raw)
                process.requests.append(request)
                reply = process.respond(request)
                if reply is not None:
                    data = reply if isinstance(reply, bytes) else json.dumps(reply).encode() + b'\n'
                    def send():
                        try:
                            for offset in range(0, len(data), 4096):
                                os.write(process._writer, data[offset:offset + 4096])
                        except OSError:
                            pass
                    thread = threading.Thread(target=send, daemon=True)
                    process.threads.append(thread)
                    thread.start()
                return len(raw)

            def flush(self):
                pass

            def close(self):
                process.finish()
        self.stdin = Input()

    def poll(self):
        return self.returncode

    def finish(self):
        if self.returncode is None:
            self.returncode = 0
            self._os.close(self._writer)

    def terminate(self):
        self.finish()

    def kill(self):
        self.finish()

    def wait(self, timeout=None):
        self.finish()
        return self.returncode


def native_reply(request, *, token='private-native-secret'):
    if 'id' not in request:
        return None
    if request['method'] == 'initialize':
        return {'id': request['id'], 'result': {}}
    item = snapshot(token=token)[1 if request['method'] == 'getAuthStatus' else 0]
    return {'id': request['id'], **item}


@pytest.mark.parametrize('reply', [lambda r: {**native_reply(r), 'id': True},
                                 lambda r: {**native_reply(r), 'id': 99},
                                 lambda r: {**native_reply(r), 'method': 'host/execute'},
                                 lambda r: b'[]\n'])
def test_native_owner_rejects_invalid_expected_id_and_frame(tmp_path, reply):
    m = module()
    process = RPCProcess(reply)
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000)
    with pytest.raises(m.InferenceTransportRefused):
        m.NativeAuthOwner(process, gate=gate, native_home=tmp_path, policy=m.qualified_policy())
    assert len(process.requests) == 1
    assert process.poll() == 0


def test_native_owner_triple_is_serial_fresh_and_lifetime_aggregate(tmp_path):
    m = module()
    process = RPCProcess(lambda request: native_reply(request, token='t' * 14000))
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 5_000_000_000)
    owner = m.NativeAuthOwner(process, gate=gate, native_home=tmp_path, policy=m.qualified_policy())
    try:
        assert owner.acquire().bearer == 't' * 14000
        assert owner.acquire().bearer == 't' * 14000
        assert [request['method'] for request in process.requests] == [
            'initialize', 'initialized', 'account/read', 'getAuthStatus', 'account/read',
            'account/read', 'getAuthStatus', 'account/read']
        for _ in range(40):
            try:
                owner.acquire()
            except m.InferenceTransportRefused:
                break
        else:
            pytest.fail('native total was reset by acquisitions')
        before = len(process.requests)
        with pytest.raises(m.InferenceTransportRefused):
            owner.acquire()
        assert len(process.requests) == before
    finally:
        owner.close()


def test_native_error_response_received_but_binding_rejected_after_whole_triple(tmp_path):
    m = module()
    def respond(request):
        if request['method'] == 'getAuthStatus':
            return {'id': request['id'], 'error': {'message': 'private-error-secret'}}
        return native_reply(request)
    process = RPCProcess(respond)
    owner = m.NativeAuthOwner(process, gate=m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000),
                              native_home=tmp_path, policy=m.qualified_policy())
    try:
        with pytest.raises(m.InferenceTransportRefused) as error:
            owner.acquire()
        assert 'private-error-secret' not in str(error.value)
        assert [r['method'] for r in process.requests][-3:] == ['account/read', 'getAuthStatus', 'account/read']
    finally:
        owner.close()


class MemorySocket:
    def __init__(self, response=b''):
        self.response = response
        self.sent = []
        self.closed = False

    def makefile(self, _mode):
        return io.BytesIO(self.response)

    def sendall(self, raw):
        if self.closed:
            raise OSError('closed')
        self.sent.append(bytes(raw))

    def shutdown(self, _how):
        self.closed = True

    def close(self):
        self.closed = True


def http_response(body, *, chunked=False, extra=b'', status=200):
    head = b'HTTP/1.1 ' + str(status).encode() + b' Status\r\nContent-Type: text/event-stream\r\nConnection: close\r\n'
    if chunked:
        head += b'Transfer-Encoding: chunked\r\n'
        body = f'{len(body):x}'.encode() + extra + b'\r\n' + body + b'\r\n0\r\n\r\n'
    else:
        head += b'Content-Length: ' + str(len(body)).encode() + b'\r\n' + extra
    return head + b'\r\n' + body


@pytest.mark.parametrize('chunked', [False, True])
def test_upstream_body_exact_64k_and_one_extra_are_distinct_from_framing(chunked):
    m = module()
    for count, admitted in [(65536, True), (65537, False)]:
        response = m.BoundedResponse(MemorySocket(http_response(b'x' * count, chunked=chunked)))
        published = bytearray()
        try:
            response.begin()
            while chunk := response.read1(4096):
                published.extend(chunk)
            assert admitted
            assert len(published) == 65536
        except m.InferenceTransportRefused:
            assert not admitted
            assert len(published) <= 65536
        finally:
            response.close()


def test_chunk_metadata_exact_plus_one_and_trailer_count_are_independent():
    m = module()
    prefix = http_response(b'x' * 65536, chunked=True).split(b'\r\n\r\n', 1)[0] + b'\r\n\r\n'
    overhead = len(prefix) + len(b'10000;\r\n') + len(b'\r\n0\r\n\r\n')
    for extra, admitted in [(0, True), (1, False)]:
        extension = b';' + b'x' * (16384 - overhead + extra)
        response = m.BoundedResponse(MemorySocket(http_response(b'x' * 65536, chunked=True, extra=extension)))
        try:
            response.begin()
            total = 0
            while part := response.read1(4096):
                total += len(part)
            assert admitted and total == 65536
        except m.InferenceTransportRefused:
            assert not admitted
        finally:
            response.close()
    for trailers, admitted in [(29, True), (30, False)]:
        raw = prefix + b'1\r\nx\r\n0\r\n' + b'X: y\r\n' * trailers + b'\r\n'
        response = m.BoundedResponse(MemorySocket(raw))
        try:
            response.begin()
            while response.read1(4096):
                pass
            assert admitted
        except m.InferenceTransportRefused:
            assert not admitted
        finally:
            response.close()


def test_fixed_https_late_connect_cancel_is_terminal_and_no_implicit_reopen(monkeypatch):
    import threading
    m = module()
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 2_000_000_000)
    connection = m.FixedHTTPSConnection(gate)
    entered, release = threading.Event(), threading.Event()
    socket = MemorySocket()
    def paused(self):
        entered.set()
        assert release.wait(1)
        self.sock = self.transport = socket
    monkeypatch.setattr(m.FixedHTTPSConnection, 'connect', paused)
    errors = []
    def request():
        try:
            connection.request('POST', '/backend-api/codex/responses', b'{}', {})
        except m.InferenceTransportRefused:
            errors.append('refused')
    thread = threading.Thread(target=request)
    thread.start()
    try:
        assert entered.wait(1)
        connection.cancel()
        release.set()
        thread.join(1)
        assert not thread.is_alive() and errors == ['refused'] and not socket.sent
        with pytest.raises(m.InferenceTransportRefused):
            connection.request('POST', '/backend-api/codex/responses', b'{}', {})
        assert not socket.sent
    finally:
        release.set()
        thread.join(1)
        connection.close()


def test_terminal_stream_without_usage_is_complete_unknown_not_partial():
    m = module()
    created = {'type': 'response.created', 'response': {'id': 'response-1'}}
    completed = {'type': 'response.completed', 'response': {'id': 'response-1'}}
    raw = b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in [created, completed])
    result = m.stream_outcome(raw)
    assert result.complete and result.usage == 'UNKNOWN' and result.cost == 'UNKNOWN'
    partial = m.stream_outcome(b'data: ' + json.dumps(created).encode() + b'\n\n')
    assert not partial.complete and partial.usage == 'UNKNOWN'


def valid_body(m, **changes):
    return json.dumps({'model': 'gpt-5.5', 'stream': True, 'reasoning': {'effort': 'low'},
                       'tools': json.loads(m.qualified_policy().tools_bytes), **changes}).encode()


def guest_headers(capability, body, extra=b''):
    return (b'Host: guest\r\nAuthorization: Bearer ' + capability.encode() +
            b'\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n' + extra + b'\r\n')


def terminal_sse(*, usage=True):
    response = {'id': 'response-1'}
    if usage:
        response['usage'] = {'input_tokens': 1, 'output_tokens': 2, 'total_tokens': 3}
    events = [{'type': 'response.created', 'response': {'id': 'response-1'}},
              {'type': 'response.completed', 'response': response}]
    return b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events)


class AuthOwner:
    def __init__(self, m):
        self.m, self.calls, self.closed = m, 0, False
        self.block = None
        self.account = 'account-A'
        self.home = None

    def acquire(self):
        self.calls += 1
        if self.block and self.calls > 1:
            self.block()
        return self.m.validate_native_snapshot(snapshot(self.account, token=f'fresh-bearer-{self.calls}'))

    def close(self):
        self.closed = True

    def check_environment(self):
        if self.home is not None:
            self.m._native_guard(self.home)


def core_fixture(m, tmp_path, monkeypatch, *, response=None):
    from tests.test_run_ref_provider_allowance import _allocate, _projection
    from tests.test_workflow_run_ref_ledger import _visit
    path = tmp_path / 'ledger.jsonl'
    _allocate(path, tmp_path)
    authority = _projection(path, tmp_path)
    owner = AuthOwner(m)
    owner.home = tmp_path / 'synthetic-native-home'
    owner.home.mkdir()
    sockets = []
    def connect(connection):
        socket = MemorySocket(http_response(terminal_sse()) if response is None else response)
        sockets.append(socket)
        connection.sock = connection.transport = socket
    monkeypatch.setattr(m.FixedHTTPSConnection, 'connect', connect)
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 5_000_000_000)
    startups = []
    def start(shared_gate, policy):
        assert shared_gate is gate and policy.digest == m.qualified_policy().digest
        startups.append(True)
        return owner
    core = m.InferenceGatewayCore(policy=m.qualified_policy(), gate=gate, visit=_visit(),
                                   attempt_ordinal=1, identity='leaf-a', attempt=1,
                                   reserve=authority.reserve, bind=authority.bind, owner_factory=start)
    return core, owner, authority, sockets, startups, path


def test_core_reservation_precedes_startup_first_permit_once_and_fresh_auth(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, startups, path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    assert authority.state['consumed'] == 1 and len(startups) == 1 and owner.calls == 1
    for _ in range(2):
        body = valid_body(m)
        outcome = core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _chunk: None)
        assert outcome.complete and outcome.usage['total_tokens'] == 3
    assert authority.state['consumed'] == 2 and owner.calls == 3 and len(startups) == 1
    assert b'fresh-bearer-1' not in b''.join(raw for socket in sockets for raw in socket.sent)
    assert b'fresh-bearer-2' in b''.join(sockets[0].sent)
    assert b'fresh-bearer-3' in b''.join(sockets[1].sent)
    assert capability.encode() not in path.read_bytes()
    assert b'fresh-bearer' not in path.read_bytes() and b'account-A' not in path.read_bytes()
    core.close()
    assert owner.closed


@pytest.mark.parametrize('change', [{'max_output_tokens': 1}, {'background': True},
                                   {'previous_response_id': 'old'}, {'unknown': True},
                                   {'model': 'another-model'}, {'tools': [{'type': 'web_search'}]},
                                   {'reasoning': {'effort': 'high'}}])
def test_admission_rejects_invalid_guest_before_auth_or_additional_reservation(tmp_path, monkeypatch, change):
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    body = valid_body(m, **change)
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _chunk: None)
    assert owner.calls == 1 and authority.state['consumed'] == 1 and not sockets
    assert owner.closed and core.gate.revoked.is_set()


@pytest.mark.parametrize('status', [401, 302])
def test_first_upstream_rejection_never_refreshes_retries_or_forwards_error(tmp_path, monkeypatch, status):
    m = module()
    raw = http_response(b'private-upstream-error', status=status,
                        extra=b'WWW-Authenticate: private-upstream-error\r\n')
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch, response=raw)
    capability = core.preflight()
    body = valid_body(m)
    received = []
    with pytest.raises(m.InferenceTransportRefused) as error:
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, received.append)
    assert 'private-upstream-error' not in str(error.value)
    assert not received and len(sockets) == 1 and owner.calls == 2 and authority.state['consumed'] == 1
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, received.append)
    assert len(sockets) == 1 and owner.calls == 2


@pytest.mark.parametrize('complete', [False, True])
def test_partial_stream_terminal_while_complete_missing_usage_remains_unknown(tmp_path, monkeypatch, complete):
    m = module()
    stream = terminal_sse(usage=False) if complete else b'data: {"type":"response.created","response":{"id":"r"}}\n\n'
    core, owner, _authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch, response=http_response(stream))
    capability = core.preflight()
    body = valid_body(m)
    outcome = core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _chunk: None)
    assert outcome.complete is complete and outcome.usage == 'UNKNOWN' and outcome.cost == 'UNKNOWN'
    assert core.gate.revoked.is_set() is not complete
    assert len(sockets) == 1 and owner.calls == 2
    core.close()


def test_core_denies_concurrent_request_without_queue(tmp_path, monkeypatch):
    import threading
    import time
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    entered, release = threading.Event(), threading.Event()
    def block():
        entered.set()
        assert release.wait(1)
    owner.block = block
    body = valid_body(m)
    errors = []
    def first():
        try:
            core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _chunk: None)
        except m.InferenceTransportRefused:
            errors.append('refused')
    thread = threading.Thread(target=first)
    thread.start()
    try:
        assert entered.wait(1)
        before = time.monotonic()
        with pytest.raises(m.InferenceTransportRefused):
            core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _chunk: None)
        assert time.monotonic() - before < .1
        assert authority.state['consumed'] == 1 and not sockets
    finally:
        release.set()
        thread.join(1)
        core.close()
    assert errors == ['refused'] and not thread.is_alive()


def test_https_timeout_is_remaining_absolute_deadline_not_an_idle_policy(monkeypatch):
    m = module()
    clock = [10_000_000_000]
    monkeypatch.setattr(m, 'boottime_ns', lambda: clock[0])
    gate = m.TransportGate(deadline_ns=100_000_000_000)
    clock[0] += 7_000_000_000
    connection = m.FixedHTTPSConnection(gate)
    assert connection.timeout == 83
    connection.close()
    clock[0] = gate.deadline_ns
    with pytest.raises(m.InferenceTransportRefused, match='transport_expired'):
        m.FixedHTTPSConnection(gate)


@pytest.mark.parametrize('checkpoint', ['reserve', 'owner', 'acquire', 'bind', 'capability'])
def test_late_callback_ack_never_activates_after_revocation(tmp_path, monkeypatch, checkpoint):
    m = module()
    core, owner, authority, sockets, startups, _path = core_fixture(m, tmp_path, monkeypatch)
    if checkpoint == 'reserve':
        original = core._reserve
        def reserve(*args, **kwargs):
            row = original(*args, **kwargs)
            core.gate.revoke()
            return row
        core._reserve = reserve
    elif checkpoint == 'owner':
        original = core._owner_factory
        def start(*args):
            result = original(*args)
            core.gate.revoke()
            return result
        core._owner_factory = start
    elif checkpoint == 'acquire':
        original = owner.acquire
        def acquire():
            result = original()
            core.gate.revoke()
            return result
        owner.acquire = acquire
    elif checkpoint == 'bind':
        original = core._bind
        def bind(**kwargs):
            digest = original(**kwargs)
            core.gate.revoke()
            return digest
        core._bind = bind
    else:
        def token(_length):
            core.gate.revoke()
            return 'capability-must-not-be-released'
        monkeypatch.setattr(m.secrets, 'token_urlsafe', token)
    with pytest.raises(m.InferenceTransportRefused):
        core.preflight()
    assert not core._ready and core._capability is None and not sockets
    assert authority.state['consumed'] == 1
    assert len(startups) == (checkpoint != 'reserve')
    assert owner.calls == (checkpoint not in {'reserve', 'owner'})
    assert owner.closed is (checkpoint != 'reserve')


@pytest.mark.parametrize('change', ['duplicate', 'foreign', 'policy', 'ordinal', 'request'])
def test_reservation_ack_cannot_be_reused_or_rebound(tmp_path, monkeypatch, change):
    from dataclasses import replace
    from tests.test_workflow_run_ref_ledger import _visit
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    body = valid_body(m)
    core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _part: None)
    original = core._reserve
    previous = authority._reservation
    def reserve(*args, **kwargs):
        row = original(*args, **kwargs)
        if change == 'duplicate':
            return previous
        if change == 'foreign':
            return replace(row, visit=replace(_visit(), parent_run_id='foreign'))
        if change == 'ordinal':
            return replace(row, attempt_ordinal=2)
        return replace(row, event={**row.event, **({'policy_digest': 'sha256:' + '0' * 64}
                                                  if change == 'policy' else {'request': 1})})
    core._reserve = reserve
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _part: None)
    assert owner.calls == 2 and len(sockets) == 1 and owner.closed
    # The trusted authority's new durable reservation stays consumed despite refusal.
    assert authority.state['consumed'] == 2


def test_changed_account_and_missing_binding_ack_never_reach_http(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    owner.account = 'account-B'
    body = valid_body(m)
    with pytest.raises(m.InferenceTransportRefused, match='native_binding_changed'):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _part: None)
    assert owner.calls == 2 and not sockets and authority.state['consumed'] == 1
    second = tmp_path / 'second'
    second.mkdir()
    core, owner, _authority, sockets, _startups, _path = core_fixture(m, second, monkeypatch)
    core._bind = lambda **_kwargs: None
    with pytest.raises(m.InferenceTransportRefused, match='binding_ack_refused'):
        core.preflight()
    assert not core._ready and core._capability is None and owner.closed and not sockets


def test_exhaustion_keeps_common_runtime_refusal_without_startup(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, startups, _path = core_fixture(m, tmp_path, monkeypatch)
    authority.state = dict(policy=core.policy.record, policy_digest=core.policy.digest,
                           consumed=32, binding_digest=None)
    with pytest.raises(m.InferenceTransportRefused, match='^run_ref_budget_exhausted$'):
        core.preflight()
    assert not startups and owner.calls == 0 and not sockets


@pytest.mark.parametrize('kind', ['tokens', 'cost'])
def test_mandatory_economic_cap_rejects_before_callbacks(tmp_path, monkeypatch, kind):
    m = module()
    core, owner, _authority, sockets, startups, _path = core_fixture(m, tmp_path, monkeypatch)
    def forbidden(*_args, **_kwargs):
        pytest.fail('authority or owner reached before mandatory economic cap rejection')
    kwargs = {'require_hard_token_cap': True} if kind == 'tokens' else {'require_hard_cost_cap': True}
    with pytest.raises(m.InferenceTransportRefused, match='run_ref_provider_transport_unavailable'):
        m.InferenceGatewayCore(policy=core.policy, gate=core.gate, visit=core._visit,
                               attempt_ordinal=1, identity='leaf-a', attempt=1,
                               reserve=forbidden, bind=forbidden, owner_factory=forbidden, **kwargs)
    assert not startups and owner.calls == 0 and not sockets


def test_guest_and_outbound_header_bytes_exact_plus_one():
    m = module()
    policy = m.qualified_policy()
    body = valid_body(m)
    base = guest_headers('ephemeral', body)
    overhead = len(base) + len(b'POST /v1/responses HTTP/1.1\r\n') + len(b'X: \r\n')
    for extra, admitted in [(0, True), (1, False)]:
        headers = guest_headers('ephemeral', body, b'X: ' + b'x' * (16384 - overhead + extra) + b'\r\n')
        if admitted:
            m.validate_guest_request('POST', '/v1/responses', headers, body,
                                     capability='ephemeral', policy=policy)
        else:
            with pytest.raises(m.InferenceTransportRefused):
                m.validate_guest_request('POST', '/v1/responses', headers, body,
                                         capability='ephemeral', policy=policy)
    auth = m.validate_native_snapshot(snapshot(token='x'))
    headers = m.upstream_headers(auth, len(body))
    raw = ''.join(key + ': ' + value + '\r\n' for key, value in headers.items()).encode() + b'\r\n'
    padding = 16384 - len(raw) - len(b'POST /backend-api/codex/responses HTTP/1.1\r\n')
    m.upstream_headers(m.validate_native_snapshot(snapshot(token='x' * (padding + 1))), len(body))
    with pytest.raises(m.InferenceTransportRefused, match='upstream_headers_excessive'):
        m.upstream_headers(m.validate_native_snapshot(snapshot(token='x' * (padding + 2))), len(body))


def test_guest_body_exact_256k_one_extra_and_ambiguous_framing_before_auth(tmp_path, monkeypatch):
    m = module()
    base = valid_body(m)
    exact = valid_body(m, prompt_cache_key='x' * (262144 - len(base) - len(', "prompt_cache_key": ""')))
    assert len(exact) == 262144
    m.validate_guest_request('POST', '/v1/responses', guest_headers('ephemeral', exact), exact,
                             capability='ephemeral', policy=m.qualified_policy())
    for index, (body, framing) in enumerate([(exact + b' ', b''), (base, b'Transfer-Encoding: chunked\r\n'),
                                           (base, b'Content-Encoding: gzip\r\n'),
                                           (base, b'Content-Length: 1\r\n')]):
        home = tmp_path / str(index)
        home.mkdir()
        core, owner, authority, sockets, _startups, _path = core_fixture(m, home, monkeypatch)
        capability = core.preflight()
        with pytest.raises(m.InferenceTransportRefused):
            core.dispatch('POST', '/v1/responses', guest_headers(capability, body, framing), body, lambda _part: None)
        assert not sockets and owner.calls == 1 and authority.state['consumed'] == 1


@pytest.mark.parametrize('extra', [b'Transfer-Encoding: chunked\r\n', b'Content-Encoding: gzip\r\n',
                                 b'Content-Length: 1\r\n', b'X: y\r\n' * 30])
def test_ambiguous_compressed_or_excessive_upstream_headers_never_forward_body(tmp_path, monkeypatch, extra):
    m = module()
    core, owner, _authority, sockets, _startups, _path = core_fixture(
        m, tmp_path, monkeypatch, response=http_response(terminal_sse(), extra=extra))
    capability = core.preflight()
    body, published = valid_body(m), []
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
    assert not published and len(sockets) == 1 and owner.calls == 2


def test_write_sse_late_return_cannot_trigger_later_auth_or_replay(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    body, published = valid_body(m), []
    def write(part):
        published.append(part)
        core.gate.revoke()
    with pytest.raises(m.InferenceTransportRefused, match='transport_revoked'):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, write)
    assert published and len(sockets) == 1 and owner.calls == 2 and authority.state['consumed'] == 1
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
    assert len(sockets) == 1 and owner.calls == 2


def test_native_unconfirmed_close_remains_failure_on_repeat(tmp_path):
    import subprocess
    m = module()
    process = RPCProcess(native_reply)
    owner = m.NativeAuthOwner(process, gate=m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000),
                              native_home=tmp_path, policy=m.qualified_policy())
    process.terminate = process.kill = lambda: None
    def wait(timeout=None):
        raise subprocess.TimeoutExpired('private-native', timeout)
    process.wait = wait
    try:
        for _ in range(2):
            with pytest.raises(m.InferenceTransportRefused, match='native_close_unconfirmed'):
                owner.close()
    finally:
        process.finish()


def test_installed_asset_tampering_rejected_without_auth_or_policy_reinterpretation(monkeypatch):
    m = module()
    original = Path.read_bytes
    def read(path):
        raw = original(path)
        return raw + b' ' if path.name == 'run-ref-native-catalog-0.162.1.json' else raw
    monkeypatch.setattr(Path, 'read_bytes', read)
    with pytest.raises(m.InferenceTransportRefused, match='transport_asset_changed'):
        m.qualified_policy()


def test_revocation_between_header_and_body_send_cannot_send_body_or_reopen():
    m = module()
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000)
    connection = m.FixedHTTPSConnection(gate)
    class RevokeOnHeader(MemorySocket):
        def sendall(self, raw):
            super().sendall(raw)
            gate.revoke()
    transport = RevokeOnHeader()
    connection.sock = connection.transport = transport
    try:
        with pytest.raises(m.InferenceTransportRefused):
            connection.request('POST', '/backend-api/codex/responses', b'private-body', {})
        assert len(transport.sent) == 1 and b'private-body' not in transport.sent[0]
        connection.close()
        with pytest.raises(m.InferenceTransportRefused):
            connection.request('POST', '/backend-api/codex/responses', b'private-body', {})
        assert len(transport.sent) == 1
    finally:
        connection.close()


def test_non_string_tool_choice_is_a_closed_refusal_before_auth():
    m = module()
    body = valid_body(m, tool_choice={'type': 'hosted-canary'})
    with pytest.raises(m.InferenceTransportRefused, match='guest_tool_choice_refused'):
        m.validate_guest_request('POST', '/v1/responses', guest_headers('ephemeral', body), body,
                                 capability='ephemeral', policy=m.qualified_policy())


def test_deadline_is_not_resettable_and_revocation_is_irreversible():
    m = module()
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000)
    with pytest.raises(AttributeError):
        gate.deadline_ns += 1_000_000_000
    gate.revoke()
    gate.revoked.clear()
    with pytest.raises(m.InferenceTransportRefused, match='transport_revoked'):
        gate.check()


def test_installed_wheel_retains_policy_assets_outside_source_tree(tmp_path):
    import subprocess
    import sys
    from tests.test_provider_isolation_schema_resources import (
        test_built_wheel_imports_only_installed_package_and_loads_every_schema,
    )
    # Reuse the existing isolated wheel/installation oracle, then exercise the
    # data package separately: schemas and qualified installation data differ.
    test_built_wheel_imports_only_installed_package_and_loads_every_schema(tmp_path)
    probe = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import orchestrator.providers.inference_gateway as transport
assert Path(transport.__file__).is_relative_to(Path(sys.argv[1]))
policy = transport.qualified_policy()
assert len(policy.catalog_bytes) == 472072
assert policy.digest.startswith('sha256:')
print('installed_policy_assets_valid')
'''
    result = subprocess.run([sys.executable, '-I', '-c', probe, str(tmp_path / 'installed')],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout == 'installed_policy_assets_valid\n'


def test_http_body_truncated_after_sse_completed_is_incomplete_and_never_replayed(tmp_path, monkeypatch):
    m = module()
    stream = terminal_sse()
    raw = http_response(stream).replace(b'Content-Length: ' + str(len(stream)).encode() + b'\r\n',
                                        b'Content-Length: ' + str(len(stream) + 1).encode() + b'\r\n')
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch, response=raw)
    capability = core.preflight()
    body, published = valid_body(m), []
    outcome = core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
    assert not outcome.complete and outcome.usage == 'UNKNOWN' and outcome.cost == 'UNKNOWN'
    assert core.gate.revoked.is_set() and owner.closed and len(sockets) == 1
    assert owner.calls == 2 and authority.state['consumed'] == 1 and b''.join(published) == stream
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
    assert len(sockets) == 1 and owner.calls == 2


@pytest.mark.parametrize('ending', ['missing_chunk_zero', 'missing_chunk_trailer', 'missing_sse_separator'])
def test_chunked_eof_and_unterminated_sse_cannot_complete_or_replay(tmp_path, monkeypatch, ending):
    m = module()
    stream = terminal_sse()
    if ending == 'missing_sse_separator':
        raw = http_response(stream.removesuffix(b'\n\n'))
    else:
        head = http_response(b'x', chunked=True).split(b'\r\n\r\n')[0] + b'\r\n\r\n'
        raw = head + f'{len(stream):x}'.encode() + b'\r\n' + stream + b'\r\n'
        if ending == 'missing_chunk_trailer':
            raw += b'0\r\n'
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch, response=raw)
    capability = core.preflight()
    body, published = valid_body(m), []
    try:
        result = core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
        assert not result.complete and result.usage == 'UNKNOWN' and result.cost == 'UNKNOWN'
    except m.InferenceTransportRefused:
        assert ending != 'missing_sse_separator'
    assert published and core.gate.revoked.is_set() and owner.closed
    assert len(sockets) == 1 and owner.calls == 2 and authority.state['consumed'] == 1
    with pytest.raises(m.InferenceTransportRefused):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, published.append)
    assert len(sockets) == 1 and owner.calls == 2


@pytest.mark.parametrize('point', ['serialize', 'write'])
def test_native_revocation_during_preparation_never_writes_or_flushes_afterward(tmp_path, monkeypatch, point):
    m = module()
    process = RPCProcess(native_reply)
    gate = m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000)
    owner = m.NativeAuthOwner(process, gate=gate, native_home=tmp_path, policy=m.qualified_policy())
    flushes = []
    process.stdin.flush = lambda: flushes.append(True)
    if point == 'serialize':
        original = m._canonical
        def serialize(value):
            raw = original(value)
            if value.get('method') == 'account/read':
                gate.revoke()
            return raw
        monkeypatch.setattr(m, '_canonical', serialize)
    else:
        original = process.stdin.write
        def write(raw):
            count = original(raw)
            gate.revoke()
            return count
        process.stdin.write = write
    try:
        with pytest.raises(m.InferenceTransportRefused, match='transport_revoked'):
            owner.acquire()
        assert len(process.requests) == (2 if point == 'serialize' else 3)
        assert not flushes
        before = len(process.requests)
        with pytest.raises(m.InferenceTransportRefused):
            owner.acquire()
        assert len(process.requests) == before
    finally:
        owner.close()


def test_environment_created_during_binding_ack_never_issues_capability(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    original = core._bind
    def bind(**kwargs):
        binding = original(**kwargs)
        (owner.home / 'environments.toml').symlink_to(tmp_path / 'unreadable-canary')
        return binding
    core._bind = bind
    with pytest.raises(m.InferenceTransportRefused, match='remote_environment_present'):
        core.preflight()
    assert core._capability is None and not core._ready and owner.closed and not sockets
    assert authority.state['binding_digest'] is not None and authority.state['consumed'] == 1


def test_environment_created_during_triple_poisoned_owner_before_binding(tmp_path):
    m = module()
    def respond(request):
        if request.get('id') == 4:
            (tmp_path / 'environments.toml').mkdir()
        return native_reply(request)
    process = RPCProcess(respond)
    owner = m.NativeAuthOwner(process, gate=m.TransportGate(deadline_ns=m.boottime_ns() + 1_000_000_000),
                              native_home=tmp_path, policy=m.qualified_policy())
    try:
        with pytest.raises(m.InferenceTransportRefused, match='remote_environment_present'):
            owner.acquire()
        before = len(process.requests)
        with pytest.raises(m.InferenceTransportRefused):
            owner.acquire()
        assert len(process.requests) == before
    finally:
        owner.close()


def test_environment_created_after_acquisition_before_post_never_sends(tmp_path, monkeypatch):
    m = module()
    core, owner, authority, sockets, _startups, _path = core_fixture(m, tmp_path, monkeypatch)
    capability = core.preflight()
    original = m.upstream_headers
    def headers(*args):
        result = original(*args)
        (owner.home / 'environments.toml').write_text('not read')
        return result
    monkeypatch.setattr(m, 'upstream_headers', headers)
    body = valid_body(m)
    with pytest.raises(m.InferenceTransportRefused, match='remote_environment_present'):
        core.dispatch('POST', '/v1/responses', guest_headers(capability, body), body, lambda _part: None)
    assert owner.calls == 2 and not sockets and owner.closed and authority.state['consumed'] == 1
