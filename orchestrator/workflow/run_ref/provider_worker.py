"""Private per-leaf worker. It has no lifecycle writer or public entry point."""
from __future__ import annotations

import os
import re
import select
import socket
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from orchestrator.providers.inference_gateway import (
    HEADER_BYTES, HEADER_COUNT, REQUEST_BODY_BYTES, InferenceTransportRefused,
    InferenceGatewayCore, NativeAuthOwner, TransportGate, boottime_ns, parse_header_block,
    prepare_native_launch, validate_transport_policy,
)


@dataclass(frozen=True, slots=True)
class NativeInstallation:
    """Internal installation input, never an authored or guest-selected route."""
    binary: Path = field(repr=False)
    native_home: Path = field(repr=False)
    host_home: Path = field(repr=False)

    def __post_init__(self):
        if any(not isinstance(path, Path) or not path.is_absolute()
               for path in (self.binary, self.native_home, self.host_home)):
            raise InferenceTransportRefused('native_path_invalid')

    def check_environment(self, gate):
        gate.check()
        if os.path.lexists(self.native_home / 'environments.toml'):
            raise InferenceTransportRefused('remote_environment_present')
        gate.check()


def native_owner(installation, *, owner_dir, native_slot_fd, gate, policy):
    from .holder_scope import HELPER_TRAMPOLINE
    installation.check_environment(gate)
    launch = prepare_native_launch(policy, binary=installation.binary, owner_dir=owner_dir,
                                   native_home=installation.native_home,
                                   host_home=installation.host_home, gate=gate)
    gate.check()
    process = subprocess.Popen(
        [sys.executable, '-I', '-S', '-c', HELPER_TRAMPOLINE,
         str(native_slot_fd), str(os.getpid()), *launch.argv],
        pass_fds=(native_slot_fd,), env=launch.env, cwd=launch.cwd, bufsize=0,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    return NativeAuthOwner(process, gate=gate, native_home=installation.native_home, policy=policy)


def _timeout(sock, gate):
    gate.check()
    sock.settimeout(max(.001, (gate.deadline_ns - boottime_ns()) / 1e9))


def read_guest_request(sock, gate):
    """One Content-Length request; no keepalive, encoding or pipeline authority."""
    raw = bytearray()
    while b'\r\n\r\n' not in raw:
        if len(raw) > HEADER_BYTES:
            raise InferenceTransportRefused('guest_http_headers_excessive')
        _timeout(sock, gate)
        part = sock.recv(min(4096, HEADER_BYTES + 1 - len(raw)))
        gate.check()
        if not part:
            raise InferenceTransportRefused('guest_http_incomplete')
        raw.extend(part)
    header, body = bytes(raw).split(b'\r\n\r\n', 1)
    if len(header) + 4 > HEADER_BYTES:
        raise InferenceTransportRefused('guest_http_headers_excessive')
    first, separator, fields = header.partition(b'\r\n')
    if not separator or first != b'POST /v1/responses HTTP/1.1':
        raise InferenceTransportRefused('guest_http_route_refused')
    try:
        headers = parse_header_block(fields + b'\r\n\r\n')
        length = headers.get('content-length', '')
        if (not re.fullmatch(r'0|[1-9][0-9]{0,5}', length)
                or int(length) > REQUEST_BODY_BYTES
                or 'transfer-encoding' in headers or 'content-encoding' in headers
                or len(headers) > HEADER_COUNT):
            raise ValueError('framing')
        length = int(length)
    except (ValueError, InferenceTransportRefused):
        raise InferenceTransportRefused('guest_http_framing_refused') from None
    if len(body) > length:
        raise InferenceTransportRefused('guest_http_pipeline_refused')
    body = bytearray(body)
    while len(body) < length:
        _timeout(sock, gate)
        part = sock.recv(min(4096, length - len(body)))
        gate.check()
        if not part:
            raise InferenceTransportRefused('guest_http_incomplete')
        body.extend(part)
    gate.check()
    return 'POST', '/v1/responses', fields + b'\r\n\r\n', bytes(body)


def serve(listener, control_socket, gate, core):
    """At most one active client; a concurrent connection revokes, never queues work."""
    active, handler = None, None
    finished = threading.Event()
    normal_eof = False

    def handle(client):
        try:
            method, route, headers, body = read_guest_request(client, gate)
            published = False

            def write_sse(part):
                nonlocal published
                _timeout(client, gate)
                if not published:
                    client.sendall(b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n'
                                   b'Connection: close\r\n\r\n')
                    published = True
                gate.check()
                client.sendall(part)
                gate.check()
            core.dispatch(method, route, headers, body, write_sse)
        except Exception:
            core.cancel()
        finally:
            client.close()
            finished.set()

    try:
        while True:
            gate.check()
            if handler is not None and finished.is_set():
                handler.join()
                active, handler = None, None
            ready = select.select([listener, control_socket], [], [], .01)[0]
            gate.check()
            if control_socket in ready and not control_socket.recv(1, socket.MSG_PEEK | socket.MSG_DONTWAIT):
                normal_eof = True
                break
            if listener not in ready:
                continue
            client, _ = listener.accept()
            gate.check()
            if handler is not None and not finished.is_set():
                client.close()
                core.cancel()
                break
            if handler is not None:
                handler.join()
            active = client
            finished.clear()
            handler = threading.Thread(target=handle, args=(client,), name='run-ref-gateway-request', daemon=True)
            handler.start()
    except (OSError, InferenceTransportRefused):
        pass
    finally:
        if active is not None:
            try:
                active.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            active.close()
        if handler is not None:
            handler.join(.25)
            if handler.is_alive():
                normal_eof = False
    return normal_eof and not gate.revoked.is_set()


def main(control_fd, deadline_ns):
    """Called only by the trusted host-slot launcher, never by authored code."""
    from .provider_control import PrivateChannel, WorkerControlClient, decode_reservation
    gate = TransportGate(deadline_ns=deadline_ns)
    channel = PrivateChannel(socket.socket(fileno=control_fd), gate)
    listener = core = None
    native_fd = None
    result = 125
    try:
        setup = channel.receive()
        if set(setup) != {'reservation', 'policy', 'installation', 'owner_dir', 'native_slot_fd'}:
            raise InferenceTransportRefused('worker_bootstrap_invalid')
        row = decode_reservation(setup['reservation'])
        retained_policy = row.event.get('policy')
        if retained_policy is not None and setup['policy'] is not None:
            raise InferenceTransportRefused('worker_bootstrap_invalid')
        policy = validate_transport_policy(retained_policy if retained_policy is not None else setup['policy'])
        paths = setup['installation']
        if type(paths) is not dict or set(paths) != {'binary', 'native_home', 'host_home'}:
            raise InferenceTransportRefused('worker_bootstrap_invalid')
        installation = NativeInstallation(**{key: Path(value) for key, value in paths.items()})
        owner_dir, native_fd = Path(setup['owner_dir']), setup['native_slot_fd']
        if not owner_dir.is_absolute() or type(native_fd) is not int or native_fd < 3:
            raise InferenceTransportRefused('worker_bootstrap_invalid')
        client = WorkerControlClient(channel, row, policy=policy)
        installation.check_environment(gate)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        channel.send_listener(listener)
        acknowledged = channel.receive()
        if set(acknowledged) != {'socket_bound'} or acknowledged['socket_bound'] is not True:
            raise InferenceTransportRefused('worker_socket_ack_invalid')
        gate.check()
        listener.listen(1)
        core = InferenceGatewayCore(policy=policy, gate=gate, visit=row.visit,
            attempt_ordinal=row.attempt_ordinal, identity=row.event['identity'], attempt=row.event['attempt'],
            reserve=client.reserve, bind=client.bind,
            owner_factory=lambda current_gate, current_policy: native_owner(installation,
                owner_dir=owner_dir, native_slot_fd=native_fd, gate=current_gate, policy=current_policy))
        capability = core.preflight()
        client.ready(capability)
        del capability
        result = 0 if serve(listener, channel.socket, gate, core) else 125
    except Exception:
        pass  # private failure, never native exception/payload output
    finally:
        channel.close()
        if core is not None:
            try:
                core.close()
            except Exception:
                result = 125
        if listener is not None:
            listener.close()
        if native_fd is not None:
            os.close(native_fd)
    return result
