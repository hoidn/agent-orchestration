"""Private confined-provider transport core; deliberately unreachable from admission.

The parent lifecycle owns reservations and binding authority. This module never
writes a ledger or launches a process. A future verified host-slot wrapper must
own startup, independent deadline observation and whole-scope quiescence.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import http.client
import importlib.resources
import json
import os
from pathlib import Path
import re
import secrets
import select
import socket
import ssl
import subprocess
import threading
import time

HEADER_BYTES = 16 << 10
HEADER_COUNT = 32
REQUEST_BODY_BYTES = 256 << 10
RESPONSE_BODY_BYTES = 64 << 10
NATIVE_FRAME_BYTES = 64 << 10
NATIVE_TOTAL_BYTES = 256 << 10
ORIGIN = 'https://chatgpt.com'
ROUTING = 'NO_CONSTRAINT'
ENDPOINT = 'https://chatgpt.com:443/backend-api/codex/responses'
MODEL = 'gpt-5.5'
_TOKEN = re.compile(rb"[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")


class InferenceTransportRefused(RuntimeError):
    """Source-selected categories only; never include native messages or payloads."""


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('nonfinite JSON')


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise InferenceTransportRefused('json_invalid') from None


class NativeFrames:
    """A lifetime ceiling, including notifications and initialize; no reset API."""

    def __init__(self):
        self._buffer = b''
        self._total = 0
        self._failed = False

    def feed(self, part: bytes) -> None:
        if self._failed or type(part) is not bytes:
            raise InferenceTransportRefused('native_frame_invalid')
        self._total += len(part)
        if self._total > NATIVE_TOTAL_BYTES:
            self._failed = True
            raise InferenceTransportRefused('native_total_excessive')
        self._buffer += part
        if any(len(frame) > NATIVE_FRAME_BYTES for frame in self._buffer.split(b'\n')):
            self._failed = True
            raise InferenceTransportRefused('native_frame_excessive')

    def take(self):
        if self._failed:
            raise InferenceTransportRefused('native_frame_invalid')
        if b'\n' not in self._buffer:
            return None
        raw, self._buffer = self._buffer.split(b'\n', 1)
        try:
            value = _json(raw)
            if type(value) is not dict:
                raise InferenceTransportRefused('native_frame_invalid')
            return value
        except InferenceTransportRefused:
            self._failed = True
            raise


@dataclass(frozen=True, slots=True)
class NativeAuthSnapshot:
    bearer: str = field(repr=False)
    account: str = field(repr=False)
    origin: str = field(repr=False)
    routing: str = field(repr=False)


def _header_value(value):
    return type(value) is str and bool(value) and all('!' <= char <= '~' for char in value)


def validate_native_snapshot(responses) -> NativeAuthSnapshot:
    if type(responses) is not list or len(responses) != 3:
        raise InferenceTransportRefused('native_snapshot_invalid')
    if any(type(response) is not dict or 'error' in response or
           type(response.get('result')) is not dict for response in responses):
        raise InferenceTransportRefused('native_snapshot_invalid')
    before, auth, after = (response['result'] for response in responses)
    if (auth.get('requiresOpenaiAuth') is not True or auth.get('authMethod') != 'chatgpt'
            or not _header_value(auth.get('authToken'))):
        raise InferenceTransportRefused('native_auth_refused')
    identities = []
    for read in (before, after):
        account, routing = read.get('account'), read.get('workspaceRouting')
        if (read.get('requiresOpenaiAuth') is not True or type(account) is not dict
                or account.get('type') != 'chatgpt' or type(routing) is not dict
                or not _header_value(routing.get('chatgptAccountId'))
                or routing.get('backendOrigin') != ORIGIN
                or routing.get('accountRoutingOverride') != ROUTING):
            raise InferenceTransportRefused('native_binding_refused')
        identities.append((routing['chatgptAccountId'], ORIGIN, ROUTING))
    if identities[0] != identities[1]:
        raise InferenceTransportRefused('native_binding_refused')
    return NativeAuthSnapshot(auth['authToken'], *identities[0])


def parse_header_block(raw: bytes) -> dict[str, str]:
    if type(raw) is not bytes or len(raw) > HEADER_BYTES or not raw.endswith(b'\r\n\r\n'):
        raise InferenceTransportRefused('http_headers_invalid')
    lines = raw[:-4].split(b'\r\n')
    if len(lines) > HEADER_COUNT:
        raise InferenceTransportRefused('http_header_count')
    result = {}
    for line in lines:
        name, separator, value = line.partition(b':')
        if (not separator or not _TOKEN.fullmatch(name)
                or any(byte < 32 or byte > 126 for byte in value)):
            raise InferenceTransportRefused('http_headers_invalid')
        key = name.decode('ascii').lower()
        if key in result:
            raise InferenceTransportRefused('http_header_duplicate')
        result[key] = value.strip(b' ').decode('ascii')
    return result


NATIVE_BINARY_DIGEST = 'sha256:628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1'
NATIVE_SOURCE = '092d3acd6bec3e3a14bdc7e7a2810ab628ab759d'
RELAY_DIGEST = 'sha256:41b630fccb31b697526f3ca8fd8b953a8fd278aa5b1de70d6918c5fb0021ff77'
_ASSET_PINS = {
    'catalog': ('run-ref-native-catalog-0.162.1.json',
                '943ca7fe1d19ed019054158303f0dbbd80b3bef43b3aa425a71aa7cb3fb52c2b'),
    'tools': ('run-ref-local-tools-0.162.1.json',
              '75ece7a5590cc316b6d1bcfbbd1ed0bd2d97bf902d98f433df22dfcc2cd15887'),
    'config_recipe': ('run-ref-native-recipe-0.162.1.json',
                      'f815ed0a3841b5a1ad6566e54bc56c8d77ff997843bca8c0bf2f10d625ffe543'),
}


def _canonical(value) -> bytes:
    from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
    return canonical_json_bytes(value)


def _digest(raw: bytes) -> str:
    return 'sha256:' + hashlib.sha256(raw).hexdigest()


def _assets():
    result = {}
    for key, (name, digest) in _ASSET_PINS.items():
        try:
            raw = importlib.resources.files('orchestrator.providers.inference_assets').joinpath(name).read_bytes()
        except OSError:
            raise InferenceTransportRefused('transport_asset_unavailable') from None
        if _digest(raw) != 'sha256:' + digest:
            raise InferenceTransportRefused('transport_asset_changed')
        result[key] = raw
    return result


@dataclass(frozen=True, slots=True)
class TransportPolicy:
    _record_bytes: bytes = field(repr=False)
    catalog_bytes: bytes = field(repr=False)
    tools_bytes: bytes = field(repr=False)
    recipe_bytes: bytes = field(repr=False)
    digest: str

    @property
    def record(self):
        return _json(self._record_bytes)


def _expected_policy(assets):
    # The outer policy field is canonical JSON; its decoded string preserves
    # qualified catalog/tools bytes exactly instead of normalizing their JSON.
    return dict(schema_version='run_ref_provider_policy.v1', max_requests=32,
                request_body_bytes=REQUEST_BODY_BYTES, response_body_bytes=RESPONSE_BODY_BYTES,
                header_bytes=HEADER_BYTES, header_count=HEADER_COUNT, concurrency=1,
                native_frame_bytes=NATIVE_FRAME_BYTES, native_total_bytes=NATIVE_TOTAL_BYTES,
                native_version='0.162.1', native_source=NATIVE_SOURCE,
                native_binary=NATIVE_BINARY_DIGEST, cli_digest=NATIVE_BINARY_DIGEST,
                relay_digest=RELAY_DIGEST, endpoint=ENDPOINT, model=MODEL, reasoning='low',
                catalog=_canonical(assets['catalog'].decode('utf-8')).decode('utf-8'),
                tools=_canonical(assets['tools'].decode('utf-8')).decode('utf-8'),
                config_recipe=assets['config_recipe'].decode('utf-8'))


def validate_transport_policy(record, *, require_hard_token_cap=False,
                              require_hard_cost_cap=False) -> TransportPolicy:
    if require_hard_token_cap or require_hard_cost_cap:
        raise InferenceTransportRefused('run_ref_provider_transport_unavailable')
    assets = _assets()
    expected = _expected_policy(assets)
    if type(record) is not dict or record != expected:
        raise InferenceTransportRefused('transport_policy_invalid')
    from orchestrator.workflow.run_ref.confined_provider import validate_provider_policy
    from orchestrator.workflow.run_ref.ledger import RunRefLedgerError
    try:
        validate_provider_policy(record)
    except RunRefLedgerError:
        raise InferenceTransportRefused('transport_policy_invalid') from None
    raw = _canonical(record)
    return TransportPolicy(raw, assets['catalog'], assets['tools'], assets['config_recipe'], _digest(raw))


def qualified_policy(*, require_hard_token_cap=False, require_hard_cost_cap=False) -> TransportPolicy:
    if require_hard_token_cap or require_hard_cost_cap:
        raise InferenceTransportRefused('run_ref_provider_transport_unavailable')
    return validate_transport_policy(_expected_policy(_assets()))


def boottime_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


class TransportGate:
    """A caller-supplied absolute deadline/revocation, not a containment observer."""

    def __init__(self, *, deadline_ns: int, revoked: threading.Event | None = None):
        if type(deadline_ns) is not int or deadline_ns <= 0:
            raise InferenceTransportRefused('transport_deadline_invalid')
        self._deadline_ns = deadline_ns
        self.revoked = threading.Event() if revoked is None else revoked
        self.send_gate = threading.RLock()
        self._terminal = False

    @property
    def deadline_ns(self):
        return self._deadline_ns

    def check(self):
        if self._terminal or self.revoked.is_set():
            self._terminal = True
            raise InferenceTransportRefused('transport_revoked')
        if boottime_ns() >= self.deadline_ns:
            self._terminal = True
            raise InferenceTransportRefused('transport_expired')

    def revoke(self):
        with self.send_gate:
            self._terminal = True
            self.revoked.set()


def _file_digest(path: Path) -> str:
    try:
        with path.open('rb') as source:
            digest = hashlib.file_digest(source, 'sha256').hexdigest()
    except OSError:
        raise InferenceTransportRefused('native_installation_unavailable') from None
    return 'sha256:' + digest


@dataclass(frozen=True, slots=True)
class NativeLaunch:
    argv: tuple[str, ...] = field(repr=False)
    env: dict[str, str] = field(repr=False)
    cwd: Path = field(repr=False)


def _native_guard(home: Path):
    if os.path.lexists(home / 'environments.toml'):
        raise InferenceTransportRefused('remote_environment_present')


def prepare_native_launch(policy: TransportPolicy, *, binary: Path, owner_dir: Path,
                          native_home: Path, host_home: Path, gate: TransportGate) -> NativeLaunch:
    """Prepare only. A future verified host-slot wrapper must perform the exec."""
    policy = validate_transport_policy(policy.record)
    gate.check()
    paths = (binary, owner_dir, native_home, host_home)
    if any(not isinstance(path, Path) for path in paths):
        raise InferenceTransportRefused('native_path_invalid')
    if any(not path.is_absolute() for path in paths):
        raise InferenceTransportRefused('native_path_invalid')
    _native_guard(native_home)
    if _file_digest(binary) != NATIVE_BINARY_DIGEST:
        raise InferenceTransportRefused('native_installation_changed')
    gate.check()
    recipe = _json(policy.recipe_bytes)
    replacements = {'<owner-dir>': str(owner_dir), '<native-home>': str(native_home),
                    '<host-home>': str(host_home)}

    def expand(value):
        if type(value) is not str:
            return value
        for marker, replacement in replacements.items():
            value = value.replace(marker, replacement)
        return value

    try:
        owner_dir.mkdir(mode=0o700)
        cwd = owner_dir / 'cwd'
        cwd.mkdir(mode=0o700)
        catalog = owner_dir / 'pinned-models.json'
        descriptor = os.open(catalog, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_CLOEXEC, 0o600)
        with os.fdopen(descriptor, 'wb') as target:
            target.write(policy.catalog_bytes)
    except OSError:
        raise InferenceTransportRefused('native_private_directory_unavailable') from None
    settings = {key: expand(value) for key, value in recipe['overrides'].items()}
    args = [str(binary)]
    for key, value in settings.items():
        args.extend(('-c', key + '=' + json.dumps(value)))
    args.extend(recipe['argv'])
    gate.check()
    _native_guard(native_home)
    return NativeLaunch(tuple(args), {key: expand(value) for key, value in recipe['env'].items()}, cwd)


class NativeAuthOwner:
    """Attach the single process returned by the future verified host-slot spawner.

    The spawner must provide private stdin/stdout pipes, discard stderr, verify
    parent death and containment, and never expose these pipes to the guest.
    This object does no process creation and never opens a credential store.
    """

    def __init__(self, process, *, gate: TransportGate, native_home: Path,
                 policy: TransportPolicy):
        self._process = process
        self._gate = gate
        self._home = native_home
        self._closed = False
        self._close_failed = False
        self._failed = False
        self._operation = threading.Lock()
        self._close_lock = threading.Lock()
        self._frames = NativeFrames()
        self._index = 0
        try:
            policy = validate_transport_policy(policy.record)
            self._recipe = _json(policy.recipe_bytes)
            self.check_environment()
            response = self._rpc('initialize', self._recipe['initialize'])
            if 'error' in response or type(response.get('result')) is not dict:
                raise InferenceTransportRefused('native_initialize_refused')
            self._write({'method': 'initialized'})
        except BaseException:
            self._failed = True
            self.close()
            raise

    def _write(self, message):
        self._gate.check()
        raw = _canonical(message) + b'\n'
        if len(raw) - 1 > NATIVE_FRAME_BYTES:
            raise InferenceTransportRefused('native_frame_excessive')
        self._gate.check()
        try:
            if self._process.stdin.write(raw) != len(raw):
                raise InferenceTransportRefused('native_write_incomplete')
            self._gate.check()
            self._process.stdin.flush()
        except (OSError, ValueError):
            raise InferenceTransportRefused('native_unavailable') from None
        self._gate.check()

    def _rpc(self, method, params):
        if method not in {'initialize', 'account/read', 'getAuthStatus'}:
            raise InferenceTransportRefused('native_method_refused')
        self._index += 1
        self._write({'id': self._index, 'method': method, 'params': params})
        while True:
            self._gate.check()
            value = self._frames.take()
            if value is not None:
                if 'id' not in value:
                    continue
                if (type(value['id']) is not int or value['id'] != self._index
                        or 'method' in value):
                    raise InferenceTransportRefused('native_response_invalid')
                self._gate.check()
                return value
            remaining = max(0, (self._gate.deadline_ns - boottime_ns()) / 1e9)
            try:
                # Poll only makes local cancellation observable. It does not
                # contain a blocked native process or replace the outer observer.
                ready = select.select([self._process.stdout], [], [], min(.05, remaining))[0]
                self._gate.check()
                if not ready:
                    continue
                part = os.read(self._process.stdout.fileno(), 4096)
            except (OSError, ValueError):
                raise InferenceTransportRefused('native_unavailable') from None
            if not part:
                raise InferenceTransportRefused('native_eof')
            self._frames.feed(part)

    def check_environment(self):
        self._gate.check()
        _native_guard(self._home)
        self._gate.check()

    def acquire(self) -> NativeAuthSnapshot:
        if not self._operation.acquire(blocking=False):
            raise InferenceTransportRefused('native_concurrent_acquisition')
        try:
            if self._closed or self._failed:
                raise InferenceTransportRefused('native_owner_closed')
            self.check_environment()
            responses = [self._rpc(item['method'], item['params'])
                         for item in self._recipe['snapshot']]
            self.check_environment()
            return validate_native_snapshot(responses)
        except Exception:
            self._failed = True
            raise
        finally:
            self._operation.release()

    def close(self):
        with self._close_lock:
            if self._closed:
                if self._close_failed:
                    raise InferenceTransportRefused('native_close_unconfirmed')
                return
            self._closed = True
            process = self._process
            try:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=.25)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=.25)
            except (OSError, subprocess.TimeoutExpired):
                self._close_failed = True
                raise InferenceTransportRefused('native_close_unconfirmed') from None
            finally:
                for stream in (process.stdin, process.stdout):
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass


class _HeaderReader:
    def __init__(self, reader):
        self.reader = reader
        self.total = 0
        self.count = 0
        self.status = False

    def __getattr__(self, name):
        return getattr(self.reader, name)

    def readline(self, _limit=-1):
        raw = self.reader.readline(max(1, HEADER_BYTES - self.total + 1))
        self.total += len(raw)
        if self.total > HEADER_BYTES:
            raise InferenceTransportRefused('upstream_metadata_bytes')
        if not self.status and raw not in {b'\r\n', b''}:
            self.count += 1
            name, separator, value = raw.removesuffix(b'\r\n').partition(b':')
            if (self.count > HEADER_COUNT or not separator or not _TOKEN.fullmatch(name)
                    or any(byte < 32 or byte > 126 for byte in value)):
                raise InferenceTransportRefused('upstream_headers_invalid')
        return raw


class BoundedResponse(http.client.HTTPResponse):
    """Count HTTP body and framing separately; neither can grow without bound."""

    def begin(self):
        original = self.fp
        reader = _HeaderReader(original)
        self.fp = reader
        try:
            super().begin()
        finally:
            if self.fp is not None:
                self.fp = original
        self._metadata_bytes = reader.total
        self._header_fields = reader.count
        self._body_bytes = 0

    def _read_status(self):
        reader = self.fp
        reader.status = True
        try:
            return super()._read_status()
        finally:
            reader.status = False

    def _metadata(self, raw, *, trailer=False):
        self._metadata_bytes += len(raw)
        if self._metadata_bytes > HEADER_BYTES:
            raise InferenceTransportRefused('upstream_metadata_bytes')
        if trailer and raw not in {b'\r\n', b''}:
            self._header_fields += 1
            name, separator, value = raw.removesuffix(b'\r\n').partition(b':')
            if (self._header_fields > HEADER_COUNT or not separator or not _TOKEN.fullmatch(name)
                    or any(byte < 32 or byte > 126 for byte in value)
                    or name.lower() in {b'content-length', b'transfer-encoding', b'content-encoding'}):
                raise InferenceTransportRefused('upstream_trailers_invalid')
        return raw

    def _read_next_chunk_size(self):
        line = self._metadata(self.fp.readline(max(1, HEADER_BYTES - self._metadata_bytes + 1)))
        if not line.endswith(b'\r\n') or any(byte > 126 or byte < 32 for byte in line[:-2]):
            raise InferenceTransportRefused('upstream_chunk_invalid')
        size = line[:-2].split(b';', 1)[0]
        if not re.fullmatch(rb'[0-9A-Fa-f]+', size):
            raise InferenceTransportRefused('upstream_chunk_invalid')
        count = int(size, 16)
        if count > RESPONSE_BODY_BYTES - self._body_bytes:
            raise InferenceTransportRefused('upstream_body_excessive')
        return count

    def _read_and_discard_trailer(self):
        while True:
            line = self._metadata(self.fp.readline(max(1, HEADER_BYTES - self._metadata_bytes + 1)),
                                  trailer=True)
            if line == b'\r\n':
                return
            if not line or not line.endswith(b'\r\n'):
                raise InferenceTransportRefused('upstream_trailer_incomplete')

    def _get_chunk_left(self):
        # Preserve http.client's dechunking state, but account/validate delimiters
        # that its default implementation otherwise consumes outside readline.
        left = self.chunk_left
        if not left:
            if left is not None:
                if self._metadata(self._safe_read(2)) != b'\r\n':
                    raise InferenceTransportRefused('upstream_chunk_invalid')
            left = self._read_next_chunk_size()
            if left == 0:
                self._read_and_discard_trailer()
                self._close_conn()
                left = None
            self.chunk_left = left
        return left

    def read1(self, n=-1):
        remaining = max(0, RESPONSE_BODY_BYTES - self._body_bytes)
        amount = remaining + 1 if n < 0 else min(n, remaining + 1)
        raw = super().read1(amount)
        if amount and not raw and not self.chunked and self.length:
            raise http.client.IncompleteRead(b'')
        self._body_bytes += len(raw)
        if self._body_bytes > RESPONSE_BODY_BYTES:
            raise InferenceTransportRefused('upstream_body_excessive')
        return raw


class FixedHTTPSConnection(http.client.HTTPSConnection):
    """Fixed verified endpoint; terminal close even when connect returns late."""
    response_class = BoundedResponse

    def __init__(self, gate: TransportGate):
        context = ssl.create_default_context()
        if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
            raise InferenceTransportRefused('tls_verification_required')
        # Use only the existing deadline's remainder. The caller's independent
        # observer/containment still owns the absolute operation limit.
        gate.check()
        timeout = max(.001, (gate.deadline_ns - boottime_ns()) / 1e9)
        super().__init__('chatgpt.com', 443, timeout=timeout, context=context)
        self._gate = gate
        self._terminal = False
        self.auto_open = 0

    def set_tunnel(self, *_args, **_kwargs):
        raise InferenceTransportRefused('http_tunnel_refused')

    def set_debuglevel(self, level):
        if level:
            raise InferenceTransportRefused('http_debug_refused')
        self.debuglevel = 0

    def _check_send(self):
        if self._terminal:
            raise InferenceTransportRefused('http_connection_terminal')
        self._gate.check()

    def connect(self):
        super().connect()
        self.transport = self.sock

    def request(self, method, url, body=None, headers=None, *, encode_chunked=False):
        if method != 'POST' or url != '/backend-api/codex/responses' or encode_chunked:
            raise InferenceTransportRefused('upstream_route_refused')
        with self._gate.send_gate:
            self._check_send()
        return super().request(method, url, body, {} if headers is None else headers)

    def send(self, data):
        if not isinstance(data, (bytes, bytearray, memoryview)):
            raise InferenceTransportRefused('http_send_type')
        with self._gate.send_gate:
            self._check_send()
            connect = self.sock is None
        if connect:
            self.connect()
        with self._gate.send_gate:
            self._check_send()
            if self.sock is None:
                raise InferenceTransportRefused('http_connection_absent')
            self.sock.sendall(data)

    def interrupt(self):
        for transport in (getattr(self, 'transport', None), self.sock):
            if transport is not None:
                try:
                    transport.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

    def cancel(self):
        self.interrupt()
        with self._gate.send_gate:
            self._gate.revoke()
            self.close()

    def close(self):
        with self._gate.send_gate:
            self._terminal = True
            super().close()
            self._buffer.clear()


@dataclass(frozen=True, slots=True)
class InferenceOutcome:
    complete: bool
    usage: dict[str, int] | str = 'UNKNOWN'
    cost: str = 'UNKNOWN'


def stream_outcome(raw: bytes) -> InferenceOutcome:
    created, completed = [], []
    failed = False
    # SSE dispatches an event only at its blank-line delimiter, not at EOF.
    for frame in raw.replace(b'\r\n', b'\n').split(b'\n\n')[:-1]:
        lines = [line[5:].removeprefix(b' ') for line in frame.splitlines() if line.startswith(b'data:')]
        if not lines:
            continue
        try:
            event = _json(b'\n'.join(lines))
        except InferenceTransportRefused:
            continue
        if type(event) is not dict:
            continue
        response = event.get('response')
        if event.get('type') in {'error', 'response.failed', 'response.incomplete', 'response.cancelled'}:
            failed = True
        if type(response) is not dict:
            continue
        if event.get('type') == 'response.created':
            created.append(response.get('id'))
        if event.get('type') == 'response.completed':
            completed.append(response)
    if (failed or len(created) != 1 or type(created[0]) is not str or not created[0]
            or len(completed) != 1 or completed[0].get('id') != created[0]):
        return InferenceOutcome(False)
    usage = completed[0].get('usage')
    keys = ('input_tokens', 'output_tokens', 'total_tokens')
    if (type(usage) is not dict or any(type(usage.get(key)) is not int or usage[key] < 0 for key in keys)
            or usage['input_tokens'] + usage['output_tokens'] != usage['total_tokens']):
        return InferenceOutcome(True)
    return InferenceOutcome(True, {key: usage[key] for key in keys})


_GUEST_FIELDS = frozenset({'client_metadata', 'include', 'input', 'model', 'parallel_tool_calls',
                           'prompt_cache_key', 'reasoning', 'store', 'stream', 'text', 'tool_choice', 'tools'})


def validate_guest_request(method, route, header_bytes, body, *, capability, policy):
    if method != 'POST' or route != '/v1/responses':
        raise InferenceTransportRefused('guest_route_refused')
    if len(header_bytes) + len(b'POST /v1/responses HTTP/1.1\r\n') > HEADER_BYTES:
        raise InferenceTransportRefused('guest_headers_excessive')
    headers = parse_header_block(header_bytes)
    if (type(capability) is not str or not capability or
            not secrets.compare_digest(headers.get('authorization', ''), 'Bearer ' + capability)):
        raise InferenceTransportRefused('capability_refused')
    if set(headers) & {'chatgpt-account-id', 'openai-organization', 'openai-project'}:
        raise InferenceTransportRefused('guest_identity_refused')
    length = headers.get('content-length', '')
    if ('transfer-encoding' in headers or 'content-encoding' in headers
            or not length.isascii() or not length.isdecimal()
            or type(body) is not bytes or not 0 < len(body) <= REQUEST_BODY_BYTES):
        raise InferenceTransportRefused('guest_body_framing_refused')
    try:
        if int(length) != len(body):
            raise InferenceTransportRefused('guest_body_framing_refused')
    except ValueError:
        raise InferenceTransportRefused('guest_body_framing_refused') from None
    value = _json(body)
    if type(value) is not dict or set(value) - _GUEST_FIELDS:
        raise InferenceTransportRefused('guest_schema_refused')
    if (value.get('model') != MODEL or value.get('stream') is not True
            or type(value.get('reasoning')) is not dict or value['reasoning'].get('effort') != 'low'
            or ('store' in value and value['store'] is not False)
            or ('input' in value and type(value['input']) is not list)
            or ('parallel_tool_calls' in value and type(value['parallel_tool_calls']) is not bool)):
        raise InferenceTransportRefused('guest_model_or_mode_refused')
    if _canonical(value.get('tools')) != _canonical(_json(policy.tools_bytes)):
        raise InferenceTransportRefused('guest_tools_refused')
    choice = value.get('tool_choice', 'auto')
    if type(choice) is not str or choice not in {'auto', 'none', 'required'}:
        raise InferenceTransportRefused('guest_tool_choice_refused')


def upstream_headers(auth: NativeAuthSnapshot, body_size: int) -> dict[str, str]:
    headers = {'Host': 'chatgpt.com', 'Accept-Encoding': 'identity', 'Content-Type': 'application/json',
               'Content-Length': str(body_size), 'Connection': 'close',
               'Authorization': 'Bearer ' + auth.bearer, 'chatgpt-account-id': auth.account}
    try:
        raw = (''.join(key + ': ' + value + '\r\n' for key, value in headers.items()) + '\r\n').encode('ascii')
    except (UnicodeError, TypeError):
        raise InferenceTransportRefused('upstream_headers_invalid') from None
    if len(raw) + len(b'POST /backend-api/codex/responses HTTP/1.1\r\n') > HEADER_BYTES:
        raise InferenceTransportRefused('upstream_headers_excessive')
    parse_header_block(raw)
    return headers


def _validate_upstream(response):
    if response.status != 200:
        raise InferenceTransportRefused('upstream_rejected')
    if response.getheader('Content-Encoding') is not None:
        raise InferenceTransportRefused('upstream_encoding_refused')
    lengths = response.headers.get_all('Content-Length', [])
    transfer = response.getheader('Transfer-Encoding')
    if (len(lengths) > 1 or (transfer and lengths) or transfer not in {None, 'chunked'}
            or (lengths and (not lengths[0].isascii() or not lengths[0].isdecimal()))):
        raise InferenceTransportRefused('upstream_framing_refused')
    if lengths and int(lengths[0]) > RESPONSE_BODY_BYTES:
        raise InferenceTransportRefused('upstream_body_excessive')
    if response.getheader('Content-Type') != 'text/event-stream':
        raise InferenceTransportRefused('upstream_format_refused')


class InferenceGatewayCore:
    """One private leaf, persistent owner, one-use ACK records, no listener.

    reserve/bind are trusted adapters to the common lifecycle authority, not
    gateway-thread calls to VisitProviderAllowance. The future private control
    path must serialize those callbacks on the lifecycle/writer owner. Parsing
    a returned row here does not confer authority or replace exact durable ACK.
    """

    def __init__(self, *, policy: TransportPolicy, gate: TransportGate, visit,
                 attempt_ordinal: int, identity: str, attempt: int, reserve, bind,
                 owner_factory, require_hard_token_cap=False, require_hard_cost_cap=False):
        self.policy = validate_transport_policy(policy.record,
                                               require_hard_token_cap=require_hard_token_cap,
                                               require_hard_cost_cap=require_hard_cost_cap)
        if (type(attempt_ordinal) is not int or attempt_ordinal <= 0 or type(attempt) is not int
                or attempt <= 0 or type(identity) is not str or not identity):
            raise InferenceTransportRefused('leaf_identity_invalid')
        self.gate = gate
        self._visit, self._ordinal, self._identity, self._attempt = visit, attempt_ordinal, identity, attempt
        self._reserve, self._bind, self._owner_factory = reserve, bind, owner_factory
        self._admission = threading.Lock()
        self._state_lock = threading.Lock()
        self._connections = set()
        self._owner = None
        self._started = False
        self._ready = False
        self._first_permit = False
        self._last_request = None
        self._last_row = None
        self._binding = None
        self._capability = None

    def _reservation(self):
        self.gate.check()
        from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
        try:
            row = self._reserve(self.policy.record, identity=self._identity, attempt=self._attempt)
        except RunRefRuntimeError as error:
            category = ('run_ref_budget_exhausted' if error.code == 'run_ref_budget_exhausted'
                        else 'reservation_authority_refused')
            raise InferenceTransportRefused(category) from None
        except Exception:
            raise InferenceTransportRefused('reservation_authority_refused') from None
        self.gate.check()
        from orchestrator.workflow.run_ref.ledger import RunRefAttemptRecord, RUN_REF_CONFINED_LEDGER_SCHEMA
        event = row.event if type(row) is RunRefAttemptRecord else None
        if (event is None or set(event) != {'request', 'identity', 'attempt', 'policy_digest', 'policy'}
                or row.event_kind != 'provider_reservation' or row.schema_version != RUN_REF_CONFINED_LEDGER_SCHEMA
                or row.visit != self._visit or row.attempt_ordinal != self._ordinal
                or event['identity'] != self._identity or event['attempt'] != self._attempt
                or event['policy_digest'] != self.policy.digest
                or type(event['request']) is not int or not 1 <= event['request'] <= 32
                or (event['policy'] is not None and _canonical(event['policy']) != self.policy._record_bytes)
                or not re.fullmatch(r'sha256:[0-9a-f]{64}', row.row_digest)
                or row.row_digest == self._last_row
                or (self._last_request is not None and event['request'] != self._last_request + 1)):
            raise InferenceTransportRefused('reservation_record_refused')
        self._last_request, self._last_row = event['request'], row.row_digest

    def _binding_digest(self, auth):
        from orchestrator.workflow.run_ref.confined_provider import provider_binding_digest
        return provider_binding_digest(self._visit, self.policy.digest, account=auth.account,
                                       origin=auth.origin, routing=auth.routing)

    def preflight(self) -> str:
        if not self._admission.acquire(blocking=False):
            self.cancel()
            raise InferenceTransportRefused('concurrent_request_refused')
        try:
            if self._started:
                raise InferenceTransportRefused('preflight_already_consumed')
            self._started = True
            self._reservation()
            self._first_permit = True
            self._owner = self._owner_factory(self.gate, self.policy)
            self.gate.check()
            auth = self._owner.acquire()
            self.gate.check()
            expected = self._binding_digest(auth)
            try:
                binding = self._bind(account=auth.account, origin=auth.origin, routing=auth.routing)
            except Exception:
                raise InferenceTransportRefused('binding_authority_refused') from None
            self.gate.check()
            if binding != expected:
                raise InferenceTransportRefused('binding_ack_refused')
            self._binding = expected
            # No preflight bearer is cached. Every dispatch acquires a fresh triple.
            del auth
            self._owner.check_environment()
            with self.gate.send_gate:
                self.gate.check()
                self._capability = secrets.token_urlsafe(32)
                self.gate.check()
                self._ready = True
                return self._capability
        except Exception as error:
            self.close()
            if isinstance(error, InferenceTransportRefused):
                raise
            raise InferenceTransportRefused('native_preflight_refused') from None
        finally:
            self._admission.release()

    def dispatch(self, method, route, headers, body, write_sse) -> InferenceOutcome:
        if not self._admission.acquire(blocking=False):
            self.cancel()
            raise InferenceTransportRefused('concurrent_request_refused')
        connection = response = None
        published = False
        try:
            self.gate.check()
            if not self._ready:
                raise InferenceTransportRefused('preflight_required')
            validate_guest_request(method, route, headers, body, capability=self._capability,
                                   policy=self.policy)
            if self._first_permit:
                self._first_permit = False
            else:
                self._reservation()
            self.gate.check()
            auth = self._owner.acquire()
            self.gate.check()
            if self._binding_digest(auth) != self._binding:
                raise InferenceTransportRefused('native_binding_changed')
            outbound = upstream_headers(auth, len(body))
            del auth
            connection = FixedHTTPSConnection(self.gate)
            with self._state_lock:
                self.gate.check()
                self._connections.add(connection)
            self._owner.check_environment()
            self.gate.check()
            connection.request('POST', '/backend-api/codex/responses', body, outbound)
            del outbound
            self.gate.check()
            response = connection.getresponse()
            self.gate.check()
            _validate_upstream(response)
            observed = bytearray()
            while True:
                self.gate.check()
                chunk = response.read1(4096)
                self.gate.check()
                if not chunk:
                    break
                observed.extend(chunk)
                write_sse(chunk)
                published = True
                self.gate.check()
            outcome = stream_outcome(bytes(observed))
            if not outcome.complete:
                self.close()
            return outcome
        except Exception as error:
            self.close()
            if isinstance(error, InferenceTransportRefused):
                raise
            if published and isinstance(error, (OSError, http.client.HTTPException)):
                return InferenceOutcome(False)
            raise InferenceTransportRefused('upstream_unavailable') from None
        finally:
            if response is not None:
                response.close()
            if connection is not None:
                with self._state_lock:
                    self._connections.discard(connection)
                connection.close()
            self._admission.release()

    def cancel(self):
        with self._state_lock:
            active = list(self._connections)
        # Shutdown precedes the shared send gate so cancellation can interrupt
        # a blocked socket send; late connect still fails its post-connect check.
        for connection in active:
            connection.interrupt()
        with self.gate.send_gate:
            self.gate.revoke()
            self._ready = False
            self._capability = None
            for connection in active:
                connection.close()

    def close(self):
        self.cancel()
        if self._owner is not None:
            try:
                self._owner.close()
            except Exception:
                raise InferenceTransportRefused('native_close_unconfirmed') from None
