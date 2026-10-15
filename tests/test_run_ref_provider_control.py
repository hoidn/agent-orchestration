"""Controller authority/observer boundaries; no native authentication or sandbox."""
from __future__ import annotations

import importlib
import array
import os
import socket
import threading
import time

import pytest


def test_listener_loan_exact_once_cloexec_and_controller_owned_inode(tmp_path):
    m = module()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns()+1_000_000_000,
                                         cancelled=threading.Event(), stop_scope=lambda: None)
    a, b = socket.socketpair()
    sender, receiver = m.PrivateChannel(a, observer), m.PrivateChannel(b, observer)
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    if not hasattr(sender, 'send_listener'):
        pytest.fail('bounded listener FD loan is not implemented')
    try:
        sender.send_listener(listener)
        copy = receiver.receive_listener()
        try:
            assert not os.get_inheritable(copy.fileno()) and copy.getsockname() == ''
            from orchestrator.workflow.run_ref.holder_scope import GatewayDirectory
            directory = GatewayDirectory(tmp_path/'gateway')
            identity = directory.bind_socket(copy)
            assert identity == directory.socket_identity()
        finally:
            copy.close()  # NOT shutdown: worker retains its socket description
        listener.listen(1)
        with pytest.raises(m.ProviderControlRefused):
            receiver.receive_listener()
        with pytest.raises(m.ProviderControlRefused):
            sender.send_listener(listener)
        directory.remove_socket(identity)
        directory.close()
    finally:
        listener.close()
        sender.close()
        receiver.close()


@pytest.mark.parametrize('kind', ['extra', 'regular', 'bound', 'listening', 'truncated', 'missing', 'datagram', 'inet', 'connected'])
def test_listener_loan_rejects_foreign_or_extra_fds_without_leaks(tmp_path, kind):
    m = module()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns()+1_000_000_000,
                                         cancelled=threading.Event(), stop_scope=lambda: None)
    a, b = socket.socketpair()
    receiver = m.PrivateChannel(b, observer)
    if not hasattr(receiver, 'receive_listener'):
        pytest.fail('bounded listener FD loan is not implemented')
    owned = [socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)]
    if kind == 'datagram':
        owned[0].close();owned = [socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM)]
    if kind == 'inet':
        owned[0].close();owned = [socket.socket(socket.AF_INET,socket.SOCK_STREAM)]
    if kind == 'connected':
        owned[0].close();owned = list(socket.socketpair())
    fd = os.open(tmp_path/'regular', os.O_CREAT|os.O_RDWR, 0o600)
    try:
        if kind in {'bound', 'listening'}:
            owned[0].bind(str(tmp_path/'foreign.sock'))
            if kind == 'listening':
                owned[0].listen(1)
        fds = [fd] if kind == 'regular' else [owned[0].fileno()]
        if kind in {'extra', 'truncated'}:
            fds *= (2 if kind == 'extra' else 10)
        ancillary = [] if kind == 'missing' else [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', fds))]
        a.sendmsg([b'\0'], ancillary)
        before = set(os.listdir('/proc/self/fd'))
        with pytest.raises(m.ProviderControlRefused):
            receiver.receive_listener()
        assert set(os.listdir('/proc/self/fd')) <= before  # rejected channel may also close
    finally:
        a.close()
        receiver.close()
        os.close(fd)
        for sock in owned:
            sock.close()


def test_ordinary_framed_rpc_rejects_replayed_rights_and_closes_all_delivered_fds():
    m = module()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns()+1_000_000_000,
                                         cancelled=threading.Event(),stop_scope=lambda:None)
    a,b = socket.socketpair()
    listener = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    channel = m.PrivateChannel(b,observer)
    try:
        a.sendmsg([b'\x00\x00\x00\x02{}'],[(socket.SOL_SOCKET,socket.SCM_RIGHTS,array.array('i',[listener.fileno()]))])
        before = set(os.listdir('/proc/self/fd'))
        with pytest.raises(m.ProviderControlRefused,match='private_rights_unexpected'):
            channel.receive()
        assert set(os.listdir('/proc/self/fd')) <= before
    finally:
        channel.close();a.close();listener.close()


def module():
    try:
        return importlib.import_module('orchestrator.workflow.run_ref.provider_control')
    except ModuleNotFoundError as error:
        if error.name != 'orchestrator.workflow.run_ref.provider_control':
            raise
        pytest.fail('private Holder control path is not implemented')


@pytest.mark.parametrize('reason', ['expiry', 'cancel'])
def test_observer_closes_channel_and_scope_while_lifecycle_ack_stays_blocked(reason):
    m = module()
    killed, entered, release = threading.Event(), threading.Event(), threading.Event()
    cancelled = threading.Event()
    controller, worker = socket.socketpair()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + (80_000_000 if reason == 'expiry' else 2_000_000_000),
                                          cancelled=cancelled, stop_scope=lambda: killed.set())
    observer.register(controller)
    observer.start()
    def lifecycle():
        entered.set()
        release.wait(2)
        with pytest.raises(m.ProviderControlRefused):
            observer.check()
    thread = threading.Thread(target=lifecycle)
    thread.start()
    try:
        assert entered.wait(1)
        if reason == 'cancel':
            cancelled.set()
        assert killed.wait(1) and observer.quiesced.wait(1)
        assert thread.is_alive() and not release.is_set()
        worker.settimeout(.2)
        assert worker.recv(1) == b''
    finally:
        release.set()
        thread.join(1)
        worker.close()
        observer.finish()


def test_observer_normal_finish_does_not_kill_scope_and_failed_stop_stays_failed():
    m = module()
    killed = []
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 1_000_000_000,
                                          cancelled=threading.Event(), stop_scope=lambda: killed.append(True))
    observer.start()
    observer.finish()
    assert not killed
    def fail():
        raise OSError('scope canary must not appear in refusal')
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 1_000_000_000,
                                          cancelled=threading.Event(), stop_scope=fail)
    observer.start()
    observer.revoke()
    assert observer.finished.wait(1) and not observer.quiesced.is_set()
    for _ in range(2):
        with pytest.raises(m.ProviderControlRefused, match='transport_scope_stop_failed'):
            observer.finish()


def test_private_channel_carries_existing_large_ack_row_and_rejects_excessive_frame(tmp_path):
    from tests.test_run_ref_provider_allowance import _allocate, _projection
    from orchestrator.providers.inference_gateway import qualified_policy
    m = module()
    path = tmp_path / 'ledger'
    _allocate(path, tmp_path)
    row = _projection(path, tmp_path).reserve(qualified_policy().record, identity='leaf', attempt=1)
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 2_000_000_000,
                                          cancelled=threading.Event(), stop_scope=lambda: None)
    first, second = socket.socketpair()
    sender, receiver = m.PrivateChannel(first, observer), m.PrivateChannel(second, observer)
    sent = []
    thread = threading.Thread(target=lambda: (sender.send({'reservation': row.record}), sent.append(True)))
    thread.start()
    try:
        value = receiver.receive()
        thread.join(1)
        assert sent and m.decode_reservation(value['reservation']) == row
        assert len(m.canonical_json_bytes(value)) > 65536
        with pytest.raises(m.ProviderControlRefused):
            sender.send({'padding': 'x' * m.CONTROL_FRAME_BYTES})
    finally:
        sender.close()
        receiver.close()
        thread.join(1)


@pytest.mark.parametrize('payload', [b'\x00\x10\x00\x01', b'\x00\x00\x00\x02[]',
                                    b'\x00\x00\x00\x0d{"a":1,"a":2}', b'\x00\x00\x00\x05{'])
def test_private_channel_rejects_bad_size_json_duplicates_and_eof(payload):
    m = module()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 1_000_000_000,
                                          cancelled=threading.Event(), stop_scope=lambda: None)
    first, second = socket.socketpair()
    channel = m.PrivateChannel(first, observer)
    try:
        second.sendall(payload)
        second.shutdown(socket.SHUT_WR)
        with pytest.raises(m.ProviderControlRefused):
            channel.receive()
        assert channel.socket.fileno() == -1
    finally:
        channel.close()
        second.close()


def test_observer_stops_scope_even_if_private_channel_close_fails(monkeypatch):
    m = module()
    killed = threading.Event()
    controller, worker = socket.socketpair()
    original = socket.socket.close
    def broken(sock):
        if sock is controller:
            raise OSError('private close canary')
        original(sock)
    monkeypatch.setattr(socket.socket, 'close', broken)
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 1_000_000_000,
                                          cancelled=threading.Event(), stop_scope=killed.set)
    try:
        observer.register(controller)
        observer.start()
        observer.revoke()
        assert killed.wait(1)
        with pytest.raises(m.ProviderControlRefused, match='transport_scope_stop_failed'):
            observer.finish()
    finally:
        monkeypatch.undo()
        controller.close()
        worker.close()


def test_observer_revocation_survives_event_clear_and_only_registers_raw_nonlingering_sockets():
    import struct
    m = module()
    killed = threading.Event()
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 2_000_000_000,
                                          cancelled=threading.Event(), stop_scope=killed.set)
    class BlockingWrapper:
        def close(self):
            pytest.fail('an unowned close callback reached the observer')
    with pytest.raises(m.ProviderControlRefused):
        observer.register(BlockingWrapper())
    controller, worker = socket.socketpair()
    try:
        controller.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 1, 300))
        observer.register(controller)
        assert struct.unpack('ii', controller.getsockopt(socket.SOL_SOCKET, socket.SO_LINGER, 8))[0] == 0
        observer.revoke()
        observer.revoked.clear()
        with pytest.raises(m.ProviderControlRefused):
            observer.check()
        observer.start()
        assert killed.wait(1)
        observer.finish()
    finally:
        controller.close()
        worker.close()


def control_fixture(m, tmp_path):
    from tests.test_run_ref_provider_allowance import _allocate, _projection
    from orchestrator.providers.inference_gateway import qualified_policy
    path = tmp_path / 'ledger'
    _allocate(path, tmp_path)
    authority = _projection(path, tmp_path)
    policy = qualified_policy()
    initial = authority.reserve(policy.record, identity='leaf', attempt=1)
    observer = m.LeafCancellationObserver(deadline_ns=m.boottime_ns() + 2_000_000_000,
                                          cancelled=threading.Event(), stop_scope=lambda: None)
    server = m.LifecycleControl(initial, authority=authority, policy=policy, observer=observer)
    return server, initial, authority, observer, path


def packet(server, index, operation, payload):
    return dict(id=index, context=server.context, operation=operation, payload=payload)


def test_control_serial_adapter_preserves_common_authority_and_never_debits_first_ack_twice(tmp_path):
    m = module()
    server, initial, authority, observer, path = control_fixture(m, tmp_path)
    messages = []
    class Channel:
        gate = observer
        def send(self, value):
            messages.append(value)
            self.reply = server.handle(value)
        def receive(self):
            return self.reply
    client = m.WorkerControlClient(Channel(), initial, policy=server.policy)
    assert client.reserve(server.policy.record, identity='leaf', attempt=1) == initial
    assert not messages and authority.state['consumed'] == 1
    binding = client.bind(account='synthetic-account-A', origin='https://chatgpt.com', routing='NO_CONSTRAINT')
    assert binding == authority.state['binding_digest']
    client.ready('c' * 43)
    assert server.capability == 'c' * 43
    second = client.reserve(server.policy.record, identity='leaf', attempt=1)
    assert second.event['request'] == 2 and authority.state['consumed'] == 2
    assert len(messages) == 3 and m.decode_reservation(second.record) == second
    assert b'synthetic-account-A' not in path.read_bytes() and b'c' * 43 not in path.read_bytes()


@pytest.mark.parametrize('change', ['id', 'foreign', 'operation', 'extra', 'capability_before_binding'])
def test_control_rejects_foreign_duplicate_unknown_or_wrong_phase_without_authority(tmp_path, change):
    m = module()
    server, _initial, authority, observer, _path = control_fixture(m, tmp_path)
    value = packet(server, 1, 'bind', dict(account='A', origin='https://chatgpt.com', routing='NO_CONSTRAINT'))
    if change == 'id':
        value['id'] = True
    elif change == 'foreign':
        value['context'] = {**value['context'], 'identity': 'another-leaf'}
    elif change == 'operation':
        value['operation'] = 'arbitrary-native-rpc'
    elif change == 'extra':
        value['extra'] = 'private canary'
    else:
        value = packet(server, 1, 'ready', {'capability': 'c' * 43})
    with pytest.raises(m.ProviderControlRefused):
        server.handle(value)
    assert authority.state['binding_digest'] is None and authority.state['consumed'] == 1
    assert server.capability is None and observer.revoked.is_set()
    with pytest.raises(m.ProviderControlRefused):
        server.handle(packet(server, 1, 'bind', dict(account='A', origin='https://chatgpt.com', routing='NO_CONSTRAINT')))


@pytest.mark.parametrize('reason', ['expiry', 'cancel'])
def test_binding_durable_ack_held_cannot_grant_after_observer_revokes(tmp_path, reason):
    m = module()
    server, _initial, authority, observer, path = control_fixture(m, tmp_path)
    if reason == 'expiry':
        observer._deadline_ns = m.boottime_ns() + 60_000_000
    entered, release, killed = threading.Event(), threading.Event(), threading.Event()
    observer._stop_scope = killed.set
    original = authority._emit
    def emit(kind, event):
        result = original(kind, event)
        entered.set()
        assert release.wait(1)
        return result
    authority._emit = emit
    observer.start()
    checked = []
    def inspect():
        try:
            assert entered.wait(1)
            if reason == 'cancel':
                observer._cancelled.set()
            assert killed.wait(1) and not release.is_set()
            assert server.capability is None
            assert b'provider_binding' in path.read_bytes()
            checked.append(True)
        finally:
            release.set()
    thread = threading.Thread(target=inspect)
    thread.start()
    try:
        with pytest.raises(m.ProviderControlRefused):
            server.handle(packet(server, 1, 'bind', dict(account='A', origin='https://chatgpt.com', routing='NO_CONSTRAINT')))
        assert checked and server.capability is None and authority.state['consumed'] == 1
        assert authority.state['binding_digest'] is not None
    finally:
        release.set()
        thread.join(1)
        observer.finish()


def test_gateway_directory_two_socket_generations_and_foreign_replacement_preserved(tmp_path):
    from orchestrator.workflow.run_ref import holder_scope as scope
    if not hasattr(scope, 'GatewayDirectory'):
        pytest.fail('private gateway directory is not implemented')
    directory = scope.GatewayDirectory(tmp_path / 'gateway')
    sockets = []
    try:
        directory.require_empty()
        generations = []
        for _ in range(2):
            sock = socket.socket(socket.AF_UNIX)
            sockets.append(sock)
            sock.bind(f'/proc/self/fd/{directory.fd}/gateway.sock')
            (directory.path / 'gateway.sock').chmod(0o600)
            identity = directory.socket_identity()
            generations.append(identity)
            sock.close()
            directory.remove_socket(identity)
            directory.require_empty()
        # Keep the first socket alive so the kernel cannot reuse its inode.
        first, replacement = socket.socket(socket.AF_UNIX), socket.socket(socket.AF_UNIX)
        sockets.extend([first, replacement])
        first.bind(f'/proc/self/fd/{directory.fd}/gateway.sock')
        (directory.path / 'gateway.sock').chmod(0o600)
        owned = directory.socket_identity()
        (directory.path / 'gateway.sock').unlink()
        replacement.bind(f'/proc/self/fd/{directory.fd}/gateway.sock')
        (directory.path / 'gateway.sock').chmod(0o600)
        foreign = (directory.path / 'gateway.sock').lstat().st_ino
        assert foreign != owned[1]
        with pytest.raises(scope.HolderDeathError):
            directory.remove_socket(owned)
        assert (directory.path / 'gateway.sock').lstat().st_ino == foreign
        for _ in range(2):
            with pytest.raises(scope.HolderDeathError):
                directory.close()
        assert directory.fd is None
    finally:
        for sock in sockets:
            sock.close()
        if directory.fd is not None:
            import os
            os.close(directory.fd)
        (directory.path / 'gateway.sock').unlink(missing_ok=True)
        directory.path.rmdir()


def test_gateway_directory_rejects_unknown_content_and_changed_directory_identity(tmp_path):
    from orchestrator.workflow.run_ref import holder_scope as scope
    if not hasattr(scope, 'GatewayDirectory'):
        pytest.fail('private gateway directory is not implemented')
    directory = scope.GatewayDirectory(tmp_path / 'gateway')
    moved = tmp_path / 'moved'
    try:
        directory.path.rename(moved)
        directory.path.mkdir(mode=0o700)
        (directory.path / 'foreign').write_bytes(b'preserve')
        with pytest.raises(scope.HolderDeathError):
            directory.require_empty()
        with pytest.raises(scope.HolderDeathError):
            directory.close()
        assert directory.fd is None
        assert (directory.path / 'foreign').read_bytes() == b'preserve'
    finally:
        import os
        if directory.fd is not None:
            os.close(directory.fd)
        (directory.path / 'foreign').unlink()
        directory.path.rmdir()
        moved.rmdir()


def test_gateway_directory_normal_close_is_idempotent_and_requires_only_socket(tmp_path):
    from orchestrator.workflow.run_ref import holder_scope as scope
    if not hasattr(scope, 'GatewayDirectory'):
        pytest.fail('private gateway directory is not implemented')
    directory = scope.GatewayDirectory(tmp_path / 'gateway')
    path = directory.path
    directory.close()
    directory.close()
    assert not path.exists() and directory.fd is None

@pytest.mark.parametrize('replacement', [False, True])
def test_gateway_close_after_scope_cleanup_retires_only_captured_bind_inode(tmp_path, replacement):
    from orchestrator.workflow.run_ref.holder_scope import GatewayDirectory, HolderDeathError
    directory = GatewayDirectory(tmp_path/'gateway')
    original, foreign = socket.socket(socket.AF_UNIX), socket.socket(socket.AF_UNIX)
    try:
        owned = directory.bind_socket(original)
        if replacement:
            (directory.path/'gateway.sock').unlink()
            foreign.bind(str(directory.path/'gateway.sock'))
            (directory.path/'gateway.sock').chmod(0o600)
            with pytest.raises(HolderDeathError):
                directory.close()
            assert (directory.path/'gateway.sock').lstat().st_ino != owned[1]
        else:
            # The transport failed before its own remove_socket step. Only the
            # later scope-empty teardown calls this directory close boundary.
            directory.close()
            assert not directory.path.exists()
    finally:
        original.close()
        foreign.close()
        if directory.fd is not None:
            import os
            os.close(directory.fd)
        if directory.path.exists():
            (directory.path/'gateway.sock').unlink(missing_ok=True)
            directory.path.rmdir()
