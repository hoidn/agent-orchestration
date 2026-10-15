"""Private worker HTTP framing; no native processes or public admission."""
import importlib
import socket

import pytest

from orchestrator.providers.inference_gateway import HEADER_BYTES, REQUEST_BODY_BYTES, TransportGate, boottime_ns


def module():
    try:
        return importlib.import_module('orchestrator.workflow.run_ref.provider_worker')
    except ModuleNotFoundError:
        pytest.fail('bounded private worker is not implemented')


def parse(raw):
    first, second = socket.socketpair()
    try:
        second.sendall(raw)
        second.shutdown(socket.SHUT_WR)
        return module().read_guest_request(first, TransportGate(deadline_ns=boottime_ns()+1_000_000_000))
    finally:
        first.close()
        second.close()


def test_worker_parser_exact_header_bound_and_first_extra_refused():
    prefix = b'POST /v1/responses HTTP/1.1\r\nContent-Length: 2\r\nX-Padding: '
    raw = prefix + b'x'*(HEADER_BYTES-len(prefix)-4) + b'\r\n\r\n{}'
    assert parse(raw)[:2] == ('POST', '/v1/responses')
    assert parse(raw)[3] == b'{}'
    assert type(parse(raw)[2]) is bytes  # core validates exact bounded header bytes
    with pytest.raises(Exception, match='guest_http'):
        parse(raw.replace(b'X-Padding: ', b'X-Padding: x'))


@pytest.mark.parametrize('raw', [
    b'POST /v1/responses HTTP/1.1\r\nContent-Length: 2\r\nContent-Length: 2\r\n\r\n{}',
    b'POST /v1/responses HTTP/1.1\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n',
    b'POST /v1/responses HTTP/1.1\r\nContent-Length: 2\r\n\r\n{',
    b'POST /v1/responses HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}extra',
    b'POST /v1/responses HTTP/1.1\r\nContent-Length: -1\r\n\r\n',
    b'CONNECT /v1/responses HTTP/1.1\r\nContent-Length: 0\r\n\r\n',
    b'POST /v1/responses HTTP/1.0\r\nContent-Length: 0\r\n\r\n',
    b'POST /v1/responses HTTP/1.1\r\nContent-Length: '+str(REQUEST_BODY_BYTES+1).encode()+b'\r\n\r\n',
])
def test_worker_parser_rejects_ambiguous_truncated_or_excessive_without_core(raw):
    with pytest.raises(Exception):
        parse(raw)


def test_native_factory_only_executes_through_inherited_host_fd_and_fixed_recipe(tmp_path, monkeypatch):
    import os
    from types import SimpleNamespace
    from orchestrator.providers import inference_gateway as core
    from orchestrator.workflow.run_ref.holder_scope import HELPER_TRAMPOLINE
    m = module()
    if not hasattr(m, 'NativeInstallation'):
        pytest.fail('native host-slot factory is not implemented')
    gate = TransportGate(deadline_ns=boottime_ns()+1_000_000_000)
    installation = m.NativeInstallation(tmp_path/'codex', tmp_path/'native', tmp_path/'host')
    env = {'PINNED': 'private-no-inheritance'}
    launch = SimpleNamespace(argv=(str(installation.binary), 'app-server', '--strict-config'), env=env,
                             cwd=tmp_path/'owner'/'cwd')
    monkeypatch.setattr(m, 'prepare_native_launch', lambda *a, **kw: launch)
    calls = []
    process = object()
    def spawn(*args, **kwargs):
        calls.append((args, kwargs))
        return process
    monkeypatch.setattr(m.subprocess, 'Popen', spawn)
    monkeypatch.setattr(m, 'NativeAuthOwner', lambda p, **kw: (p, kw))
    result = m.native_owner(installation, owner_dir=tmp_path/'owner', native_slot_fd=91,
                            gate=gate, policy=core.qualified_policy())
    argv = calls[0][0][0]
    assert argv[4] == HELPER_TRAMPOLINE and argv[5:7] == ['91', str(os.getpid())]
    assert argv[7:] == list(launch.argv)
    assert calls[0][1]['pass_fds'] == (91,) and calls[0][1]['env'] is env
    assert calls[0][1]['bufsize'] == 0 and calls[0][1]['stderr'] is m.subprocess.DEVNULL
    assert result[0] is process and result[1]['native_home'] == installation.native_home


def test_worker_rejects_second_client_while_first_read_is_blocked_without_queue(tmp_path):
    import threading
    import time
    m = module()
    if not hasattr(m, 'serve'):
        pytest.fail('bounded worker service is not implemented')
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(tmp_path/'gateway.sock'))
    listener.listen(1)
    controller, control = socket.socketpair()
    revoked = threading.Event()
    gate = TransportGate(deadline_ns=boottime_ns()+2_000_000_000, revoked=revoked)
    calls = []
    class Core:
        def dispatch(self, *args):
            calls.append('dispatch')
        def cancel(self):
            calls.append('cancel')
            gate.revoke()
    result = []
    thread = threading.Thread(target=lambda: result.append(m.serve(listener, control, gate, Core())))
    thread.start()
    first = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    second = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        first.connect(str(tmp_path/'gateway.sock'))
        # First client holds an actual incomplete-header read, not a core stub.
        first.sendall(b'POST ')
        time.sleep(.03)
        second.connect(str(tmp_path/'gateway.sock'))
        second.settimeout(1)
        assert second.recv(1) == b''
        thread.join(1)
        assert not thread.is_alive() and revoked.is_set() and calls and set(calls) == {'cancel'}
        assert result == [False]
        first.settimeout(.1)
        assert first.recv(1) == b''
    finally:
        controller.close()
        control.close()
        listener.close()
        first.close()
        second.close()
        thread.join(2)


def test_worker_only_reports_graceful_for_controller_eof_not_a_transport_failure(tmp_path):
    import threading
    m = module()
    for fail in [False, True]:
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        path = tmp_path/str(fail)
        listener.bind(str(path))
        listener.listen(1)
        controller, control = socket.socketpair()
        gate = TransportGate(deadline_ns=boottime_ns()+2_000_000_000)
        class Core:
            def dispatch(self, *args):
                raise ValueError('private-error-canary')
            def cancel(self):
                gate.revoke()
        results = []
        thread = threading.Thread(target=lambda: results.append(m.serve(listener, control, gate, Core())))
        thread.start()
        client = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            if fail:
                client.connect(str(path))
                client.sendall(b'POST /v1/responses HTTP/1.1\r\nContent-Length: 2\r\n\r\n{}')
                client.settimeout(1)
                assert client.recv(1) == b''
            else:
                controller.close()
            thread.join(1)
            assert not thread.is_alive() and results == [not fail]
        finally:
            controller.close()
            control.close()
            listener.close()
            client.close()
            thread.join(2)
