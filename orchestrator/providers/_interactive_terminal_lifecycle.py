"""Private durable ownership and bounded launch helpers for interactive tmux."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import json
import math
import os
from pathlib import Path
import signal
import select
import stat
import subprocess
import sys
import time
import uuid

# Helpers run by absolute filename so provider cwd and PYTHONPATH stay untouched.
if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.monitor.process import process_start_time_token


class OwnershipError(RuntimeError):
    pass


def boot_id():
    return Path('/proc/sys/kernel/random/boot_id').read_text(encoding='ascii').strip()


@dataclass(frozen=True)
class InteractiveTerminalReservation:
    root: Path
    schema_version: str
    adapter_token: str
    namespace: str
    namespace_dev: int
    namespace_ino: int
    namespace_uid: int
    lease_dev: int
    lease_ino: int
    boot_id: str

    def to_dict(self):
        record = asdict(self)
        del record['root']
        return record

    @classmethod
    def from_dict(cls, root, record):
        fields = set(cls.__dataclass_fields__) - {'root'}
        if not isinstance(record, dict) or set(record) != fields:
            raise OwnershipError('invalid reservation fields')
        token = record.get('adapter_token')
        if (record.get('schema_version') != 'interactive_terminal_reservation.v1'
                or not isinstance(token, str) or len(token) != 32
                or any(c not in '0123456789abcdef' for c in token)
                or record.get('namespace') != 'orc-peer-' + token
                or not isinstance(record.get('boot_id'), str)
                or record['boot_id'] != boot_id()
                or any(type(record[k]) is not int or record[k] < 0
                       for k in fields - {'schema_version','adapter_token','namespace','boot_id'})):
            raise OwnershipError('invalid reservation binding')
        return cls(root=Path(os.path.abspath(root)), **record)

    @property
    def path(self):
        return self.root / self.namespace

    @property
    def session(self):
        return 'orc-peer-' + self.adapter_token


def reserve(root):
    root = Path(os.path.abspath(root))
    token = uuid.uuid4().hex
    namespace = 'orc-peer-' + token
    if len(os.fsencode(root / namespace / 'tmux.sock')) > 103:
        raise OwnershipError('socket path too long')
    parent = WorkspaceFiles(root)
    files = None
    try:
        os.mkdir(namespace, 0o700, dir_fd=parent.root_fd)
        os.fsync(parent.root_fd)
        files = parent.subroot(namespace)
        os.fchmod(files.root_fd, 0o700)
        descriptor = os.open('launch.lock', os.O_RDWR | os.O_CREAT | os.O_EXCL
                             | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=files.root_fd)
        try:
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
            lock_info = os.fstat(descriptor)
        finally:
            os.close(descriptor)
        os.fsync(files.root_fd)
        info = os.fstat(files.root_fd)
        return InteractiveTerminalReservation(root, 'interactive_terminal_reservation.v1',
            token, namespace, info.st_dev, info.st_ino, info.st_uid,
            lock_info.st_dev, lock_info.st_ino, boot_id())
    finally:
        if files is not None:
            files.close()
        parent.close()


def _private(info, mode, kind):
    if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != mode or not kind(info.st_mode):
        raise OwnershipError('foreign resource owner/type/mode')


def validate(reservation, files):
    r = InteractiveTerminalReservation.from_dict(reservation.root, reservation.to_dict())
    info = os.fstat(files.root_fd)
    _private(info, 0o700, stat.S_ISDIR)
    if (info.st_dev, info.st_ino, info.st_uid) != (r.namespace_dev, r.namespace_ino, r.namespace_uid):
        raise OwnershipError('namespace identity changed')
    parent = WorkspaceFiles(r.root)
    try:
        linked = parent.stat(r.namespace)
        if (linked.st_dev, linked.st_ino) != (info.st_dev, info.st_ino):
            raise OwnershipError('namespace replaced')
    finally:
        parent.close()
    lock = files.stat('launch.lock')
    _private(lock, 0o600, stat.S_ISREG)
    if (lock.st_dev, lock.st_ino) != (r.lease_dev, r.lease_ino):
        raise OwnershipError('lease identity changed')


@contextmanager
def opened(reservation):
    parent = WorkspaceFiles(reservation.root)
    files = None
    try:
        files = parent.subroot(reservation.namespace)
        validate(reservation, files)
        yield files
    finally:
        if files is not None:
            files.close()
        parent.close()


def remaining(deadline):
    value = deadline - time.monotonic()
    if not math.isfinite(deadline) or value <= 0:
        raise TimeoutError('interactive deadline exhausted')
    return value


def acquire(reservation, files, deadline):
    validate(reservation, files)
    descriptor = os.open('launch.lock', os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=files.root_fd)
    try:
        info = os.fstat(descriptor)
        if (info.st_dev, info.st_ino) != (reservation.lease_dev, reservation.lease_ino):
            raise OwnershipError('opened lease replaced')
        while True:
            remaining(deadline)
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                time.sleep(min(.01, remaining(deadline)))
        validate(reservation, files)
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _read(files, name):
    try:
        with files.open_read(name) as source:
            _private(os.fstat(source.fileno()), 0o600, stat.S_ISREG)
            content = source.read(8193)
    except FileNotFoundError:
        return None
    if len(content) > 8192:
        raise OwnershipError('oversized operational record')
    return content


def write(reservation, files, name, value):
    validate(reservation, files)
    _read(files, name)
    content = value.encode('ascii') if isinstance(value, str) else json.dumps(value, sort_keys=True).encode('ascii')
    files.write_atomic(name, content, mode=0o600)
    validate(reservation, files)


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise OwnershipError('duplicate operational record key')
        value[key] = item
    return value


def record(reservation, files, name):
    validate(reservation, files)
    content = _read(files, name)
    if content is None:
        return None
    if name == 'revoked':
        if content != reservation.adapter_token.encode('ascii'):
            raise OwnershipError('foreign revocation')
        return reservation.adapter_token
    try:
        value = json.loads(content, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError) as exc:
        raise OwnershipError('invalid operational record') from exc
    common = {'schema_version', 'adapter_token'}
    expected = {
        'server.json': common | {'boot_id','server_pid','server_start_ticks','socket_dev','socket_ino'},
        'client.json': common | {'boot_id','leader_pid','pgid','sid','leader_start_ticks'},
        'command.json': common | {'operation_token','kind','state'},
    }[name]
    if name == 'command.json' and isinstance(value, dict) and value.get('state') == 'completed':
        expected = expected | {'outcome'}
    if (not isinstance(value, dict) or set(value) != expected
            or value['schema_version'] != 'interactive_terminal_' + name[:-5] + '.v1'
            or value['adapter_token'] != reservation.adapter_token):
        raise OwnershipError('foreign/malformed operational record')
    if name == 'command.json':
        token = value['operation_token']
        if (not isinstance(token, str) or len(token) != 32
                or any(c not in '0123456789abcdef' for c in token)
                or value['kind'] not in {'start_server','start_pane'}
                or value['state'] not in {'active','completed'}
                or (value['state'] == 'completed' and value['outcome'] not in {'success','failed','timed_out'})):
            raise OwnershipError('invalid command state')
    else:
        if value['boot_id'] != reservation.boot_id:
            raise OwnershipError('foreign boot')
        if any(type(value[k]) is not int or value[k] <= 0 for k in expected-common-{'boot_id'}):
            raise OwnershipError('invalid process/socket identity')
        if name == 'client.json' and not value['leader_pid'] == value['pgid'] == value['sid']:
            raise OwnershipError('provider is not isolated group leader')
    return value


def start_token(pid):
    token = process_start_time_token(pid)
    if token is None:
        try:
            os.stat(f'/proc/{pid}/stat')
        except FileNotFoundError:
            return None
        raise OwnershipError('unreadable process identity')
    return token


def check_leader(client):
    current = start_token(client['leader_pid'])
    if current is not None and current != str(client['leader_start_ticks']):
        raise OwnershipError('provider leader reused')


def group_empty(client):
    check_leader(client)
    try:
        os.killpg(client['pgid'], 0)
    except ProcessLookupError:
        return True
    return False


def stop_group(client, deadline):
    """Escalate while retaining the leader anchor; the caller proves subsequent absence."""
    if group_empty(client):
        return
    # Keep escalation and reap observation inside the caller's original budget.
    grace = time.monotonic() + min(.2, remaining(deadline) / 4)
    for sig, end in ((signal.SIGTERM, grace), (signal.SIGKILL, deadline)):
        check_leader(client)
        try:
            os.killpg(client['pgid'], sig)
        except ProcessLookupError:
            return
        if sig == signal.SIGKILL:
            return
        while True:
            if group_empty(client):
                return
            if time.monotonic() >= end:
                break
            time.sleep(min(.01, remaining(end)))


def helper_argv(reservation, mode, deadline):
    return [sys.executable, "-I", "-S", str(Path(__file__).absolute()), mode,
            str(reservation.root), json.dumps(reservation.to_dict()), repr(deadline)]


def run_creating(reservation, kind, argv, env, deadline):
    with opened(reservation) as files:
        lease = acquire(reservation, files, deadline)
        try:
            if record(reservation, files, 'revoked') is not None:
                raise OwnershipError('attempt revoked')
            previous = record(reservation, files, 'command.json')
            if previous is not None and previous['state'] != 'completed':
                raise OwnershipError('unsettled previous command')
            helper = subprocess.Popen(helper_argv(reservation, 'command', deadline)
                + [str(lease), kind, json.dumps(argv)], pass_fds=(lease,),
                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True)
        finally:
            # The helper owns the same open file description; LOCK_UN would release it.
            os.close(lease)
        stdout, stderr = helper.communicate(timeout=remaining(deadline))
        result = record(reservation, files, 'command.json')
        if result is None or result['state'] != 'completed':
            raise OwnershipError('creating helper did not prove settlement')
        if result['outcome'] == 'timed_out':
            raise TimeoutError('creating command timed out')
        return subprocess.CompletedProcess(argv, helper.returncode, stdout, stderr)


def _command(reservation, deadline, lease, kind, argv):
    with opened(reservation) as files:
        info = os.fstat(lease)
        if (info.st_dev, info.st_ino) != (reservation.lease_dev, reservation.lease_ino):
            raise OwnershipError('helper inherited foreign lease')
        if record(reservation, files, 'revoked') is not None:
            raise OwnershipError('attempt revoked')
        remaining(deadline)
        value = {'schema_version':'interactive_terminal_command.v1',
                 'adapter_token':reservation.adapter_token, 'operation_token':uuid.uuid4().hex,
                 'kind':kind, 'state':'active'}
        write(reservation, files, 'command.json', value)
        duration = remaining(deadline)
        work_end = time.monotonic() + duration * .7
        term_end = time.monotonic() + duration * .85
        remaining(deadline)
        child = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 start_new_session=True)
        outcome = 'success'
        try:
            stdout, stderr = child.communicate(timeout=remaining(work_end))
        except (subprocess.TimeoutExpired, TimeoutError):
            outcome = 'timed_out'
            try:
                os.killpg(child.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                stdout, stderr = child.communicate(timeout=remaining(term_end))
            except (subprocess.TimeoutExpired, TimeoutError):
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stdout, stderr = child.communicate(timeout=remaining(deadline))
        remaining(deadline)
        if outcome == 'success' and child.returncode != 0:
            outcome = 'failed'
        for descriptor, content in ((1, stdout), (2, stderr)):
            os.set_blocking(descriptor, False)
            view = memoryview(content)
            while view:
                budget = remaining(deadline)
                if not select.select([], [descriptor], [], budget)[1]:
                    raise TimeoutError('helper output settlement expired')
                try:
                    written = os.write(descriptor, view[:65536])
                except BrokenPipeError:
                    break  # A dead controller has no output consumer left to settle.
                except BlockingIOError:
                    continue
                view = view[written:]
        remaining(deadline)
        value.update(state='completed', outcome=outcome)
        write(reservation, files, 'command.json', value)
        os.close(lease)
        return child.returncode if outcome != 'timed_out' else 124


def _pane(reservation, deadline, argv):
    with opened(reservation) as files:
        lease = acquire(reservation, files, deadline)
        try:
            if record(reservation, files, 'revoked') is not None:
                raise OwnershipError('attempt revoked')
            pid = os.getpid()
            if pid != os.getpgrp() or pid != os.getsid(0):
                raise OwnershipError('pane not isolated')
            token = start_token(pid)
            if token is None:
                raise OwnershipError('missing pane identity')
            write(reservation, files, 'client.json', {
                'schema_version':'interactive_terminal_client.v1',
                'adapter_token':reservation.adapter_token, 'boot_id':reservation.boot_id,
                'leader_pid':pid, 'pgid':pid, 'sid':pid, 'leader_start_ticks':int(token)})
            remaining(deadline)
            if record(reservation, files, 'revoked') is not None:
                raise OwnershipError('attempt revoked')
            os.set_inheritable(lease, False)
            remaining(deadline)
            os.execvp(argv[0], argv)
        finally:
            os.close(lease)


if __name__ == '__main__':
    mode, root, raw, deadline_text, *args = sys.argv[1:]
    reservation = InteractiveTerminalReservation.from_dict(root, json.loads(raw))
    deadline = float(deadline_text)
    if mode == 'command':
        lease_text, kind, argv_text = args
        raise SystemExit(_command(reservation, deadline, int(lease_text), kind, json.loads(argv_text)))
    if mode == 'pane':
        _pane(reservation, deadline, args)
    raise SystemExit(125)
