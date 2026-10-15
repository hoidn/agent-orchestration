"""Private provider control channel and controller-only cancellation observer.

The channel conveys existing acknowledged records, never durable authority of
its own. The observer neither calls the lifecycle writer nor publishes events.
"""
from __future__ import annotations

import array
import errno
import json
import os
import re
import socket
import struct
import stat
import threading

from .confined_budget import boottime_ns
from .contracts import canonical_json_bytes

# The first existing reservation includes the exact retained catalog/policy
# (~500 KiB). This is an IPC bound, not the native RPC frame limit or a quota.
CONTROL_FRAME_BYTES = 1 << 20
CONTROL_OPERATIONS = 34  # bind, ready, and 32 reserves including the final denial


class ProviderControlRefused(RuntimeError):
    """Closed source-selected diagnostic; no private payload or exception text."""


class LeafCancellationObserver:
    """Independent until transport quiescence, including blocked emit/ACK waits.

    stop_scope must stop/verify the previously validated whole Holder scope
    within its existing bounded teardown window, without a lifecycle lock.
    """

    def __init__(self, *, deadline_ns, cancelled, stop_scope):
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise ProviderControlRefused('transport_deadline_invalid')
        self._deadline_ns = deadline_ns
        self._cancelled, self._stop_scope = cancelled, stop_scope
        self.revoked = threading.Event()
        self.quiesced = threading.Event()
        self.finished = threading.Event()
        self._done, self._wake = threading.Event(), threading.Event()
        self._lock = threading.Lock()
        self._channels = set()
        self._error = None
        self._thread = None
        self._terminal = False

    @property
    def deadline_ns(self):
        return self._deadline_ns

    def start(self):
        if self._thread is not None:
            raise ProviderControlRefused('transport_observer_already_started')
        self._thread = threading.Thread(target=self._observe, name='run-ref-transport-observer', daemon=True)
        self._thread.start()

    def register(self, channel):
        if type(channel) is not socket.socket:
            raise ProviderControlRefused('private_channel_type_invalid')
        # Only our raw socketpairs, never a wrapper with a blocking close/lock.
        channel.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack('ii', 0, 0))
        with self._lock:
            revoked = self._terminal or self.revoked.is_set()
            if not revoked:
                self._channels.add(channel)
        if revoked:
            self._close_channel(channel)

    @staticmethod
    def _close_channel(channel):
        try:
            channel.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        channel.close()

    def revoke(self):
        # No writer, send or IPC lock: even a blocked callback cannot delay this.
        self._terminal = True
        self.revoked.set()
        self._wake.set()

    def check(self):
        if self._cancelled.is_set() or boottime_ns() >= self._deadline_ns:
            self.revoke()
        if self._terminal or self.revoked.is_set():
            self._terminal = True
            raise ProviderControlRefused('transport_revoked')

    def _observe(self):
        while True:
            if (self._terminal or self.revoked.is_set() or self._cancelled.is_set()
                    or boottime_ns() >= self._deadline_ns):
                self._terminal = True
                self.revoked.set()
                with self._lock:
                    channels = tuple(self._channels)
                for channel in channels:
                    try:
                        self._close_channel(channel)
                    except Exception:
                        self._error = ProviderControlRefused('transport_scope_stop_failed')
                try:
                    self._stop_scope()
                    if self._error is None:
                        self.quiesced.set()
                except Exception:
                    self._error = ProviderControlRefused('transport_scope_stop_failed')
                finally:
                    self.finished.set()
                return
            if self._done.is_set():
                self.finished.set()
                return
            remaining = max(0, (self._deadline_ns - boottime_ns()) / 1e9)
            self._wake.wait(min(.01, remaining))
            self._wake.clear()

    def finish(self):
        """Call after transport shutdown/quiescence; never before its last ACK wait."""
        self._done.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(2.25)  # existing 2 s vacate window plus join scheduling
            if self._thread.is_alive():
                self._error = ProviderControlRefused('transport_scope_stop_failed')
        if self._error is not None:
            raise self._error


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate')
        result[key] = value
    return result


def _nonfinite(_value):
    raise ValueError('nonfinite')


class PrivateChannel:
    """Length-framed private socketpair, with one initial unbound listener loan."""

    def __init__(self, sock, gate):
        self.socket, self.gate = sock, gate
        self._closed = False
        self._rights_done = False

    def send_listener(self, listener):
        try:
            self._check()
            if self._rights_done:
                raise ProviderControlRefused('private_rights_repeated')
            self._rights_done = True
            if self.socket.sendmsg([b'\0'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS,
                                             array.array('i', [listener.fileno()]))]) != 1:
                raise ProviderControlRefused('private_rights_invalid')
            self._check()
        except Exception:
            self.close()
            raise ProviderControlRefused('private_rights_invalid') from None

    @staticmethod
    def _rights(ancillary):
        descriptors = []
        for level, kind, data in ancillary:
            if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
                numbers = array.array('i')
                numbers.frombytes(data[:len(data) - len(data) % numbers.itemsize])
                descriptors.extend(numbers)
        return descriptors

    def receive_listener(self):
        descriptors, result = [], None
        try:
            self._check()
            if self._rights_done:
                raise ProviderControlRefused('private_rights_repeated')
            self._rights_done = True
            raw, ancillary, flags, _ = self.socket.recvmsg(
                1, socket.CMSG_SPACE(2 * array.array('i').itemsize), socket.MSG_CMSG_CLOEXEC)
            descriptors = self._rights(ancillary)
            if (raw != b'\0' or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC)
                    or len(ancillary) != 1 or ancillary[0][:2] != (socket.SOL_SOCKET, socket.SCM_RIGHTS)
                    or len(descriptors) != 1 or len(ancillary[0][2]) != array.array('i').itemsize
                    or not stat.S_ISSOCK(os.fstat(descriptors[0]).st_mode)):
                raise ProviderControlRefused('private_rights_invalid')
            result = socket.socket(fileno=descriptors[0])
            descriptors.pop()
            if (result.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN) != socket.AF_UNIX
                    or result.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) != socket.SOCK_STREAM
                    or result.getsockname() not in {'', b''}
                    or result.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN)):
                raise ProviderControlRefused('private_rights_invalid')
            try:
                result.getpeername()
            except OSError as error:
                if error.errno != errno.ENOTCONN:
                    raise
            else:
                raise ProviderControlRefused('private_rights_invalid')
            self._check()
            accepted, result = result, None
            return accepted
        except Exception:
            self.close()
            raise ProviderControlRefused('private_rights_invalid') from None
        finally:
            if result is not None:
                result.close()
            for descriptor in descriptors:
                os.close(descriptor)

    def close(self):
        self._closed = True
        try:
            self.socket.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.socket.close()

    def _check(self):
        self.gate.check()
        if self._closed:
            raise ProviderControlRefused('private_channel_closed')
        remaining = (self.gate.deadline_ns - boottime_ns()) / 1e9
        self.socket.settimeout(max(.001, remaining))

    def send(self, value):
        self._check()
        try:
            raw = canonical_json_bytes(value)
            if not 0 < len(raw) <= CONTROL_FRAME_BYTES:
                raise ProviderControlRefused('private_frame_excessive')
            self._check()
            self.socket.sendall(struct.pack('!I', len(raw)) + raw)
            self._check()
        except ProviderControlRefused:
            self.close()
            raise
        except (OSError, ValueError, RecursionError, UnicodeError):
            self.close()
            raise ProviderControlRefused('private_channel_unavailable') from None

    def _read(self, count):
        parts = bytearray()
        while len(parts) < count:
            self._check()
            part, ancillary, flags, _ = self.socket.recvmsg(
                min(4096, count - len(parts)), socket.CMSG_SPACE(2 * array.array('i').itemsize),
                socket.MSG_CMSG_CLOEXEC)
            for descriptor in self._rights(ancillary):
                os.close(descriptor)
            if ancillary or flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC):
                raise ProviderControlRefused('private_rights_unexpected')
            self._check()
            if not part:
                raise ProviderControlRefused('private_channel_eof')
            parts.extend(part)
        return bytes(parts)

    def receive(self):
        try:
            size = struct.unpack('!I', self._read(4))[0]
            if not 0 < size <= CONTROL_FRAME_BYTES:
                raise ProviderControlRefused('private_frame_excessive')
            raw = self._read(size)
            value = json.loads(raw, object_pairs_hook=_unique, parse_constant=_nonfinite)
            if type(value) is not dict:
                raise ValueError('object required')
            self._check()
            return value
        except ProviderControlRefused:
            self.close()
            raise
        except (OSError, ValueError, RecursionError, UnicodeError):
            self.close()
            raise ProviderControlRefused('private_frame_invalid') from None


def decode_reservation(value):
    """Validate existing row syntax/digest; trust still comes from common ACK."""
    from .ledger import _decode_row, RunRefLedgerError
    if type(value) is not dict or type(value.get('sequence')) is not int:
        raise ProviderControlRefused('reservation_record_invalid')
    try:
        return _decode_row(value, expected_sequence=value['sequence'])
    except (RunRefLedgerError, TypeError, ValueError):
        raise ProviderControlRefused('reservation_record_invalid') from None


def _context(row, policy):
    from .ledger import RunRefAttemptRecord
    if (type(row) is not RunRefAttemptRecord or row.event_kind != 'provider_reservation'
            or type(row.event) is not dict or row.event.get('policy_digest') != policy.digest):
        raise ProviderControlRefused('reservation_record_invalid')
    return dict(visit=row.visit.record, attempt_ordinal=row.attempt_ordinal,
                identity=row.event['identity'], attempt=row.event['attempt'],
                policy_digest=policy.digest, reservation_digest=row.row_digest)


class LifecycleControl:
    """Only the lifecycle thread may adapt IPC to its existing allowance owner."""

    def __init__(self, initial_reservation, *, authority, policy, observer):
        from orchestrator.providers.inference_gateway import validate_transport_policy
        self.policy = validate_transport_policy(policy.record)
        initial = decode_reservation(initial_reservation.record)
        self._context = _context(initial, self.policy)
        self._authority, self._observer = authority, observer
        self._thread = threading.get_ident()
        self._index, self._phase, self._failed = 0, 'bind', False
        self.capability = None

    @property
    def context(self):
        return json.loads(canonical_json_bytes(self._context))

    def handle(self, message):
        from .runtime import RunRefRuntimeError
        try:
            self._observer.check()
            if (self._failed or threading.get_ident() != self._thread or type(message) is not dict
                    or set(message) != {'id', 'context', 'operation', 'payload'}
                    or type(message['id']) is not int or message['id'] != self._index + 1
                    or message['id'] > CONTROL_OPERATIONS or message['context'] != self._context
                    or type(message['payload']) is not dict):
                raise ProviderControlRefused('private_request_invalid')
            operation, payload = message['operation'], message['payload']
            self._index = message['id']
            if operation == 'bind' and self._phase == 'bind':
                if (set(payload) != {'account', 'origin', 'routing'}
                        or type(payload['account']) is not str or not 0 < len(payload['account']) <= 16384
                        or any(not '!' <= value <= '~' for value in payload['account'])
                        or payload['origin'] != 'https://chatgpt.com' or payload['routing'] != 'NO_CONSTRAINT'):
                    raise ProviderControlRefused('private_binding_invalid')
                result = self._authority.bind(**payload)
                self._observer.check()
                if type(result) is not str or not re.fullmatch(r'sha256:[0-9a-f]{64}', result):
                    raise ProviderControlRefused('private_binding_invalid')
                self._phase = 'ready'
            elif operation == 'ready' and self._phase == 'ready':
                if (set(payload) != {'capability'} or type(payload['capability']) is not str
                        or not re.fullmatch(r'[A-Za-z0-9_-]{43}', payload['capability'])):
                    raise ProviderControlRefused('private_capability_invalid')
                self._observer.check()
                self.capability = payload['capability']
                self._phase, result = 'active', True
            elif operation == 'reserve' and self._phase == 'active' and not payload:
                row = self._authority.reserve(self.policy.record, identity=self._context['identity'],
                                              attempt=self._context['attempt'])
                self._observer.check()
                result = decode_reservation(row.record).record
            else:
                raise ProviderControlRefused('private_operation_invalid')
            self._observer.check()
            return dict(id=self._index, context=self.context, result=result)
        except (ProviderControlRefused, RunRefRuntimeError):
            self._failed = True
            self.capability = None
            self._observer.revoke()
            raise
        except Exception:
            self._failed = True
            self.capability = None
            self._observer.revoke()
            raise ProviderControlRefused('provider_authority_refused') from None


class WorkerControlClient:
    """Ephemeral adapter to an ACK already obtained before this worker existed."""

    def __init__(self, channel, initial_reservation, *, policy):
        self._channel, self._policy = channel, policy
        self._initial = decode_reservation(initial_reservation.record)
        self._context = _context(self._initial, policy)
        self._index, self._failed = 0, False
        self._operation = threading.Lock()

    def _call(self, operation, payload):
        if not self._operation.acquire(blocking=False):
            raise ProviderControlRefused('private_concurrent_request')
        try:
            self._channel.gate.check()
            if self._failed or self._index >= CONTROL_OPERATIONS:
                raise ProviderControlRefused('private_client_closed')
            self._index += 1
            self._channel.send(dict(id=self._index, context=self._context,
                                    operation=operation, payload=payload))
            self._channel.gate.check()
            reply = self._channel.receive()
            self._channel.gate.check()
            if (type(reply) is not dict or set(reply) != {'id', 'context', 'result'}
                    or type(reply['id']) is not int or reply['id'] != self._index
                    or reply['context'] != self._context):
                raise ProviderControlRefused('private_reply_invalid')
            return reply['result']
        except Exception:
            self._failed = True
            raise
        finally:
            self._operation.release()

    def reserve(self, policy, *, identity, attempt):
        self._channel.gate.check()
        if (self._failed or identity != self._context['identity'] or type(attempt) is not int
                or attempt != self._context['attempt']
                or canonical_json_bytes(policy) != canonical_json_bytes(self._policy.record)):
            self._failed = True
            raise ProviderControlRefused('private_reservation_invalid')
        if self._initial is not None:
            result, self._initial = self._initial, None
            self._channel.gate.check()
            return result
        return decode_reservation(self._call('reserve', {}))

    def bind(self, *, account, origin, routing):
        return self._call('bind', dict(account=account, origin=origin, routing=routing))

    def ready(self, capability):
        if self._call('ready', {'capability': capability}) is not True:
            self._failed = True
            raise ProviderControlRefused('private_ready_refused')
