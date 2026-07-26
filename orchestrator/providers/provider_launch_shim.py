"""Reviewed provider-launch shim and bounded fd-3 credential frame.

The file is both an importable controller helper and the exact resource copied
into sealed provider environments.  Imports used by the script path are kept
to Python built-ins and the small stdlib closure available under ``-I -S``.
"""

from __future__ import annotations

import ctypes
import errno
import os
import struct
import sys


CREDENTIAL_FRAME_MAGIC = b"OPLCRED1"
CREDENTIAL_FRAME_VERSION = 1
MAX_CREDENTIAL_NAMES = 32
MAX_CREDENTIAL_NAME_BYTES = 128
MAX_CREDENTIAL_VALUE_BYTES = 65_536
MAX_CREDENTIAL_FRAME_BYTES = 262_144
MAX_SUPPLEMENTARY_GROUPS = 65_536
MAX_GROUP_BOUNDARY_OBSERVATION_BYTES = 65_536
BOUNDARY_READY_FD = 7
BOUNDARY_READY_BYTE = b"R"

_FRAME_HEADER = struct.Struct(">8sHHI")
_ROW_HEADER = struct.Struct(">HI")
_ENVIRONMENT_NAME_BYTES = frozenset(
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_"
)
_RESERVED_EXACT_NAMES = frozenset(
    {
        "BASH_ENV",
        "CONDA_PREFIX",
        "ENV",
        "HOME",
        "LANG",
        "LANGUAGE",
        "LD_LIBRARY_PATH",
        "LD_PRELOAD",
        "NODE_OPTIONS",
        "NODE_PATH",
        "PATH",
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "SSH_AUTH_SOCK",
        "TEMP",
        "TMP",
        "TMPDIR",
        "TZ",
        "VIRTUAL_ENV",
    }
)
_RESERVED_PREFIXES = (
    "DYLD_",
    "LC_",
    "LD_",
    "ORCHESTRATOR_",
    "PYTHON",
    "XDG_",
)

_SYS_CLOSE_RANGE = 436
_SYS_KEYCTL = 250
_SYS_PIDFD_OPEN = 434
_SYS_UNSHARE = 272
_KEYCTL_JOIN_SESSION_KEYRING = 1
_CLONE_NEWUSER = 0x10000000
_UINT_MAX = (1 << 32) - 1

_PR_SET_NO_NEW_PRIVS = 38
_PR_SET_SECCOMP = 22
_SECCOMP_MODE_FILTER = 2
_AUDIT_ARCH_X86_64 = 0xC000003E
_SECCOMP_RET_KILL_PROCESS = 0x80000000
_SECCOMP_RET_ALLOW = 0x7FFF0000
_SECCOMP_RET_ERRNO = 0x00050000
_EPERM_RESULT = _SECCOMP_RET_ERRNO | errno.EPERM

_BPF_LD = 0x00
_BPF_W = 0x00
_BPF_ABS = 0x20
_BPF_JMP = 0x05
_BPF_JEQ = 0x10
_BPF_K = 0x00
_BPF_RET = 0x06

_X86_64_ADD_KEY = 248
_X86_64_REQUEST_KEY = 249
_X86_64_KEYCTL = 250
_X32_SYSCALL_BIT = 0x40000000


class CredentialFrameError(ValueError):
    """A stable, value-redacting credential frame rejection."""


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [
        ("len", ctypes.c_ushort),
        ("filter", ctypes.POINTER(_SockFilter)),
    ]


def _validate_declared_names(declared_names: tuple[str, ...]) -> tuple[str, ...]:
    if len(declared_names) > MAX_CREDENTIAL_NAMES:
        raise CredentialFrameError("too many predeclared credential names")
    if len(set(declared_names)) != len(declared_names):
        raise CredentialFrameError("predeclared credential names must be unique")
    for name in declared_names:
        if not isinstance(name, str):
            raise CredentialFrameError("credential name must be text")
        try:
            encoded = name.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise CredentialFrameError("credential name must be strict UTF-8") from exc
        if (
            not encoded
            or len(encoded) > MAX_CREDENTIAL_NAME_BYTES
            or encoded[0] not in b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
            or any(byte not in _ENVIRONMENT_NAME_BYTES for byte in encoded)
        ):
            raise CredentialFrameError("credential name is not a valid environment name")
        if name in _RESERVED_EXACT_NAMES or any(
            name.startswith(prefix) for prefix in _RESERVED_PREFIXES
        ):
            raise CredentialFrameError("credential name is reserved")
    return declared_names


def encode_credential_frame(
    credentials: dict[str, bytes],
    *,
    declared_names: tuple[str, ...],
) -> bytes:
    """Encode one deterministic bounded credential map for fixed descriptor 3."""

    declared = _validate_declared_names(tuple(declared_names))
    if not isinstance(credentials, dict):
        raise CredentialFrameError("credential map must be an object")
    unknown = set(credentials) - set(declared)
    if unknown:
        raise CredentialFrameError("credential frame contains an undeclared name")

    payload = bytearray()
    try:
        for name in declared:
            if name not in credentials:
                continue
            value = credentials[name]
            if not isinstance(value, bytes):
                raise CredentialFrameError("credential value must be bytes")
            if len(value) > MAX_CREDENTIAL_VALUE_BYTES:
                raise CredentialFrameError(
                    "credential value exceeds the per-value bound"
                )
            encoded_name = name.encode("utf-8")
            payload.extend(_ROW_HEADER.pack(len(encoded_name), len(value)))
            payload.extend(encoded_name)
            payload.extend(value)
        total = _FRAME_HEADER.size + len(payload)
        if total > MAX_CREDENTIAL_FRAME_BYTES:
            raise CredentialFrameError("credential frame exceeds the total byte bound")
        return (
            _FRAME_HEADER.pack(
                CREDENTIAL_FRAME_MAGIC,
                CREDENTIAL_FRAME_VERSION,
                sum(1 for name in declared if name in credentials),
                total,
            )
            + bytes(payload)
        )
    finally:
        _zero(payload)


def decode_credential_frame(
    frame: bytearray,
    *,
    declared_names: tuple[str, ...],
) -> dict[str, bytes]:
    """Decode and zero a mutable credential frame on every outcome."""

    try:
        declared = _validate_declared_names(tuple(declared_names))
        if len(frame) > MAX_CREDENTIAL_FRAME_BYTES:
            raise CredentialFrameError("credential frame exceeds the total byte bound")
        if len(frame) < _FRAME_HEADER.size:
            raise CredentialFrameError("credential frame is truncated")
        magic, version, count, total = _FRAME_HEADER.unpack_from(frame)
        if magic != CREDENTIAL_FRAME_MAGIC:
            raise CredentialFrameError("credential frame magic is invalid")
        if version != CREDENTIAL_FRAME_VERSION:
            raise CredentialFrameError("credential frame version is unsupported")
        if count > MAX_CREDENTIAL_NAMES:
            raise CredentialFrameError("credential frame has too many rows")
        if total != len(frame):
            raise CredentialFrameError("credential frame length is invalid")

        offset = _FRAME_HEADER.size
        result: dict[str, bytes] = {}
        declared_set = set(declared)
        for _index in range(count):
            if offset + _ROW_HEADER.size > len(frame):
                raise CredentialFrameError("credential row header is truncated")
            name_size, value_size = _ROW_HEADER.unpack_from(frame, offset)
            offset += _ROW_HEADER.size
            if not name_size or name_size > MAX_CREDENTIAL_NAME_BYTES:
                raise CredentialFrameError("credential name length is invalid")
            if value_size > MAX_CREDENTIAL_VALUE_BYTES:
                raise CredentialFrameError("credential value length is invalid")
            end_name = offset + name_size
            end_value = end_name + value_size
            if end_value > len(frame):
                raise CredentialFrameError("credential row is truncated")
            try:
                name = bytes(frame[offset:end_name]).decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise CredentialFrameError(
                    "credential name must be strict UTF-8"
                ) from exc
            if name not in declared_set:
                raise CredentialFrameError("credential frame contains an undeclared name")
            if name in result:
                raise CredentialFrameError("credential frame contains a duplicate name")
            result[name] = bytes(frame[end_name:end_value])
            offset = end_value
        if offset != len(frame):
            raise CredentialFrameError("credential frame has trailing data")
        return result
    finally:
        _zero(frame)


def read_credentials_from_fd(
    fd: int = 3,
    *,
    declared_names: tuple[str, ...],
) -> dict[str, bytes]:
    """Read one bounded frame to EOF and close the credential descriptor."""

    data = bytearray()
    try:
        while True:
            remaining = MAX_CREDENTIAL_FRAME_BYTES + 1 - len(data)
            if remaining <= 0:
                raise CredentialFrameError("credential frame exceeds the total byte bound")
            chunk = os.read(fd, min(65_536, remaining))
            if not chunk:
                break
            data.extend(chunk)
        if len(data) > MAX_CREDENTIAL_FRAME_BYTES:
            raise CredentialFrameError("credential frame exceeds the total byte bound")
        return decode_credential_frame(data, declared_names=declared_names)
    finally:
        _zero(data)
        try:
            os.close(fd)
        except OSError:
            pass


def _zero(value: bytearray) -> None:
    value[:] = b"\x00" * len(value)


def _close_fd_range(start: int, end: int) -> None:
    if start > end:
        return
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(_SYS_CLOSE_RANGE),
        ctypes.c_uint(start),
        ctypes.c_uint(end),
        ctypes.c_uint(0),
    )
    if result == 0:
        return
    error = ctypes.get_errno()
    if error not in {errno.ENOSYS, errno.EINVAL}:
        raise OSError(error, "close_range failed")

    try:
        names = os.listdir("/proc/self/fd")
    except OSError as exc:
        raise OSError(
            errno.ENOTSUP,
            "verified fd inventory is unavailable",
        ) from exc

    observed: set[int] = set()
    for name in names:
        try:
            fd = int(name)
        except ValueError:
            continue
        if fd < start or fd > end:
            continue
        observed.add(fd)
    for fd in sorted(observed):
        try:
            os.close(fd)
        except OSError as exc:
            if exc.errno != errno.EBADF:
                raise

    try:
        names_after = os.listdir("/proc/self/fd")
    except OSError as exc:
        raise OSError(
            errno.ENOTSUP,
            "fd closure could not be verified",
        ) from exc
    for name in names_after:
        try:
            fd = int(name)
        except ValueError:
            continue
        if fd < start or fd > end:
            continue
        try:
            os.fstat(fd)
        except OSError as exc:
            if exc.errno == errno.EBADF:
                continue
            raise
        raise OSError(errno.EBUSY, "fd closure verification found an open descriptor")


def _close_fds_from(start: int) -> None:
    """Close every descriptor from ``start`` without relying on CLOEXEC/bwrap."""

    _close_fd_range(start, _UINT_MAX)


def _close_fds_from_except(start: int, keep_fd: int) -> None:
    if keep_fd < start or keep_fd > _UINT_MAX:
        raise OSError(errno.EINVAL, "preserved descriptor is outside closure range")
    _close_fd_range(start, keep_fd - 1)
    _close_fd_range(keep_fd + 1, _UINT_MAX)
    os.fstat(keep_fd)


def _signal_boundary_ready(fd: int) -> None:
    if fd != BOUNDARY_READY_FD:
        raise OSError(errno.EINVAL, "boundary readiness descriptor is invalid")
    try:
        written = os.write(fd, BOUNDARY_READY_BYTE)
        if written != len(BOUNDARY_READY_BYTE):
            raise OSError(errno.EIO, "boundary readiness signal was truncated")
    finally:
        os.close(fd)
    try:
        os.fstat(fd)
    except OSError as exc:
        if exc.errno == errno.EBADF:
            return
        raise
    raise OSError(errno.EBUSY, "boundary readiness descriptor remained open")


def _wait_for_boundary_ready(
    fd: int,
    *,
    selector_factory,
    monotonic,
    timeout_seconds: float = 10.0,
) -> None:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 0 <= timeout_seconds <= 60
    ):
        raise OSError(errno.EINVAL, "provider boundary timeout is invalid")
    deadline = monotonic() + timeout_seconds
    selector = selector_factory()
    try:
        selector.register(fd, 1)

        remaining = deadline - monotonic()
        if remaining < 0 or not selector.select(remaining):
            raise OSError(
                errno.ETIMEDOUT,
                "provider boundary readiness timed out",
            )
        if os.read(fd, len(BOUNDARY_READY_BYTE) + 1) != BOUNDARY_READY_BYTE:
            raise OSError(
                errno.EPROTO,
                "provider boundary readiness signal is invalid",
            )
        remaining = deadline - monotonic()
        if remaining < 0 or not selector.select(remaining):
            raise OSError(
                errno.ETIMEDOUT,
                "provider boundary readiness descriptor remained open",
            )
        if os.read(fd, 1) != b"":
            raise OSError(
                errno.EPROTO,
                "provider boundary readiness signal is duplicated",
            )
    finally:
        selector.close()


def _wait_for_bwrap_child_pid(
    fd: int,
    *,
    selector_factory,
    json_loads,
    monotonic,
    timeout_seconds: float = 10.0,
) -> int:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not 0 <= timeout_seconds <= 60
    ):
        raise OSError(errno.EINVAL, "Bubblewrap child status timeout is invalid")
    deadline = monotonic() + timeout_seconds
    object_marker = object()
    buffered = bytearray()
    observed_bytes = 0
    selector = selector_factory()
    try:
        selector.register(fd, 1)
        while True:
            while b"\n" in buffered:
                raw_line, separator, remainder = buffered.partition(b"\n")
                assert separator
                buffered[:] = remainder
                if not raw_line.strip():
                    continue
                try:
                    parsed = json_loads(
                        raw_line,
                        object_pairs_hook=lambda pairs: (object_marker, pairs),
                    )
                except (TypeError, UnicodeDecodeError, ValueError) as exc:
                    raise OSError(
                        errno.EPROTO,
                        "Bubblewrap child status is malformed",
                    ) from exc
                if (
                    not isinstance(parsed, tuple)
                    or len(parsed) != 2
                    or parsed[0] is not object_marker
                ):
                    raise OSError(
                        errno.EPROTO,
                        "Bubblewrap child status is not an object",
                    )
                child_pids = [
                    value
                    for name, value in parsed[1]
                    if name == "child-pid"
                ]
                if not child_pids:
                    continue
                if len(child_pids) != 1:
                    raise OSError(
                        errno.EPROTO,
                        "Bubblewrap child status PID is duplicated",
                    )
                child_pid = child_pids[0]
                if (
                    isinstance(child_pid, bool)
                    or not isinstance(child_pid, int)
                    or child_pid <= 0
                    or child_pid > _UINT_MAX
                ):
                    raise OSError(
                        errno.EPROTO,
                        "Bubblewrap child status PID is invalid",
                    )
                return child_pid

            remaining = deadline - monotonic()
            if remaining < 0 or not selector.select(remaining):
                raise OSError(
                    errno.ETIMEDOUT,
                    "Bubblewrap child status timed out",
                )
            chunk = os.read(fd, 4096)
            if not chunk:
                raise OSError(
                    errno.EPROTO,
                    "Bubblewrap child status omitted the PID",
                )
            observed_bytes += len(chunk)
            if observed_bytes > 65_536:
                raise OSError(
                    errno.EOVERFLOW,
                    "Bubblewrap child status is oversized",
                )
            buffered.extend(chunk)
    finally:
        _zero(buffered)
        selector.close()


def _read_pinned_child_ascii(
    proc_dir_fd: int,
    name: str,
    max_bytes: int,
) -> str:
    if name not in {"stat", "uid_map", "gid_map", "setgroups", "status"}:
        raise RuntimeError("pinned child observation name is not fixed")
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
        or max_bytes > MAX_GROUP_BOUNDARY_OBSERVATION_BYTES
    ):
        raise RuntimeError("pinned child observation bound is invalid")
    fd = os.open(
        name,
        os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=proc_dir_fd,
    )
    try:
        value = bytearray()
        while len(value) <= max_bytes:
            block = os.read(fd, min(4096, max_bytes + 1 - len(value)))
            if not block:
                break
            value.extend(block)
        if len(value) > max_bytes:
            raise RuntimeError("pinned child observation is oversized")
        try:
            return bytes(value).decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                "pinned child observation is not strict ASCII"
            ) from exc
    finally:
        _zero(value)
        os.close(fd)


def _parse_proc_starttime(value: str, *, expected_pid: int) -> int:
    lines = value.splitlines()
    if len(lines) != 1:
        raise RuntimeError("pinned child stat record is malformed")
    line = lines[0]
    pid_text, separator, remainder = line.partition(" ")
    closing = remainder.rfind(")")
    if (
        not separator
        or not pid_text.isascii()
        or not pid_text.isdecimal()
        or int(pid_text, 10) != expected_pid
        or not remainder.startswith("(")
        or closing <= 0
        or closing + 1 >= len(remainder)
        or remainder[closing + 1] != " "
    ):
        raise RuntimeError("pinned child stat identity is malformed")
    fields = remainder[closing + 2 :].split()
    if (
        len(fields) < 20
        or len(fields[0]) != 1
        or not fields[19].isascii()
        or not fields[19].isdecimal()
    ):
        raise RuntimeError("pinned child stat start identity is malformed")
    return int(fields[19], 10)


def _assert_pidfd_live(pidfd: int, *, selector_factory) -> None:
    selector = selector_factory()
    try:
        selector.register(pidfd, 1)
        if selector.select(0):
            raise RuntimeError("pinned child is no longer live")
    finally:
        selector.close()


def _open_pidfd(pid: int) -> int:
    pidfd_open = getattr(os, "pidfd_open", None)
    if pidfd_open is not None:
        return pidfd_open(pid, 0)
    if os.uname().machine != "x86_64":
        raise OSError(errno.ENOTSUP, "pidfd_open is unavailable")
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(_SYS_PIDFD_OPEN),
        ctypes.c_int(pid),
        ctypes.c_uint(0),
    )
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, "pidfd_open failed")
    return int(result)


def _pin_rootless_child(
    child_pid: int,
    *,
    selector_factory,
) -> tuple[int, int, int]:
    if (
        isinstance(child_pid, bool)
        or not isinstance(child_pid, int)
        or child_pid <= 0
        or child_pid > _UINT_MAX
    ):
        raise RuntimeError("pinned child PID is invalid")
    pidfd = -1
    proc_root_fd = -1
    proc_dir_fd = -1
    try:
        pidfd = _open_pidfd(child_pid)
        proc_root_fd = os.open(
            "/proc",
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
        )
        proc_dir_fd = os.open(
            str(child_pid),
            os.O_RDONLY
            | os.O_DIRECTORY
            | os.O_CLOEXEC
            | getattr(os, "O_NOFOLLOW", 0),
            dir_fd=proc_root_fd,
        )
        starttime = _parse_proc_starttime(
            _read_pinned_child_ascii(proc_dir_fd, "stat", 4096),
            expected_pid=child_pid,
        )
        _assert_pidfd_live(pidfd, selector_factory=selector_factory)
        return pidfd, proc_dir_fd, starttime
    except BaseException:
        for fd in (proc_dir_fd, pidfd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        raise
    finally:
        if proc_root_fd >= 0:
            os.close(proc_root_fd)


def _validate_pinned_rootless_child_boundary(
    *,
    child_pid: int,
    pidfd: int,
    proc_dir_fd: int,
    starttime: int,
    controller_euid: int,
    controller_egid: int,
    controller_groups: tuple[int, ...],
    expected_primary_count: int,
    expected_overflow_count: int,
    selector_factory,
) -> dict[str, object]:
    if (
        expected_primary_count
        != controller_groups.count(controller_egid)
        or expected_overflow_count
        != len(controller_groups) - expected_primary_count
    ):
        raise RuntimeError("pinned child group-count binding is inconsistent")

    _assert_pidfd_live(pidfd, selector_factory=selector_factory)
    observed_starttime = _parse_proc_starttime(
        _read_pinned_child_ascii(proc_dir_fd, "stat", 4096),
        expected_pid=child_pid,
    )
    if observed_starttime != starttime:
        raise RuntimeError("pinned child start identity changed")

    uid_map = _parse_single_id_map(
        _read_pinned_child_ascii(proc_dir_fd, "uid_map", 4096)
    )
    gid_map = _parse_single_id_map(
        _read_pinned_child_ascii(proc_dir_fd, "gid_map", 4096)
    )
    if uid_map != (0, controller_euid, 1):
        raise RuntimeError("pinned child UID map does not match the controller")
    if gid_map != (0, controller_egid, 1):
        raise RuntimeError("pinned child GID map does not match the controller")
    if _read_pinned_child_ascii(proc_dir_fd, "setgroups", 32) != "deny\n":
        raise RuntimeError("pinned child setgroups state is not denied")

    uid_row, gid_row, status_groups = _parse_status_rows(
        _read_pinned_child_ascii(proc_dir_fd, "status", 65_536)
    )
    if uid_row != (controller_euid,) * 4:
        raise RuntimeError("pinned child UID status does not match the controller")
    if gid_row != (controller_egid,) * 4:
        raise RuntimeError("pinned child GID status does not match the controller")
    if tuple(sorted(status_groups)) != tuple(sorted(controller_groups)):
        raise RuntimeError("pinned child supplementary groups changed")

    final_starttime = _parse_proc_starttime(
        _read_pinned_child_ascii(proc_dir_fd, "stat", 4096),
        expected_pid=child_pid,
    )
    if final_starttime != starttime:
        raise RuntimeError("pinned child start identity changed")
    _assert_pidfd_live(pidfd, selector_factory=selector_factory)
    return {
        "child_pid": child_pid,
        "starttime": starttime,
        "uid_map": uid_map,
        "gid_map": gid_map,
        "setgroups": "deny",
        "controller_group_count": len(controller_groups),
        "expected_primary_count": expected_primary_count,
        "expected_overflow_count": expected_overflow_count,
    }


def _join_fresh_session_keyring() -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(_SYS_KEYCTL),
        ctypes.c_long(_KEYCTL_JOIN_SESSION_KEYRING),
        ctypes.c_void_p(),
    )
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, "fresh session keyring unavailable")


def _validate_nested_userns_disabled() -> None:
    if os.uname().machine != "x86_64":
        raise OSError(
            errno.ENOTSUP,
            "nested user-namespace validation is x86_64-only",
        )
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(_SYS_UNSHARE),
        ctypes.c_ulong(_CLONE_NEWUSER),
    )
    error = ctypes.get_errno()
    if result == -1 and error in {errno.EPERM, errno.ENOSPC}:
        return
    if result == 0:
        raise OSError(
            errno.EBUSY,
            "nested user namespaces remain enabled",
        )
    raise OSError(
        error or errno.EIO,
        "nested user-namespace denial is unavailable",
    )


def _read_fixed_ascii(path: str, max_bytes: int) -> str:
    if path not in {
        "/proc/self/uid_map",
        "/proc/self/gid_map",
        "/proc/self/setgroups",
        "/proc/self/status",
        "/proc/sys/kernel/overflowgid",
    }:
        raise RuntimeError("group-boundary observation path is not fixed")
    if (
        isinstance(max_bytes, bool)
        or not isinstance(max_bytes, int)
        or max_bytes <= 0
        or max_bytes > MAX_GROUP_BOUNDARY_OBSERVATION_BYTES
    ):
        raise RuntimeError("group-boundary observation bound is invalid")
    fd = os.open(
        path,
        os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        value = bytearray()
        while len(value) <= max_bytes:
            block = os.read(fd, min(4096, max_bytes + 1 - len(value)))
            if not block:
                break
            value.extend(block)
        if len(value) > max_bytes:
            raise RuntimeError("group-boundary observation is oversized")
        try:
            return bytes(value).decode("ascii", errors="strict")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                "group-boundary observation is not strict ASCII"
            ) from exc
    finally:
        _zero(value)
        os.close(fd)


def _parse_single_id_map(value: str) -> tuple[int, int, int]:
    if (
        not value.endswith("\n")
        or value.count("\n") != 1
        or "\r" in value
        or "\v" in value
        or "\f" in value
    ):
        raise RuntimeError("group-boundary ID map must contain one row")
    fields = value[:-1].split()
    if len(fields) != 3 or any(not field.isdecimal() for field in fields):
        raise RuntimeError("group-boundary ID map row is malformed")
    row = tuple(int(field, 10) for field in fields)
    if row[0] != 0 or row[2] != 1 or any(
        field < 0 or field > _UINT_MAX for field in row
    ):
        raise RuntimeError("group-boundary ID map row is not normalized")
    return row


def _parse_status_rows(
    value: str,
) -> tuple[tuple[int, ...], tuple[int, ...], tuple[int, ...]]:
    if "\r" in value or "\v" in value or "\f" in value:
        raise RuntimeError("group-boundary status contains invalid whitespace")
    rows: dict[str, tuple[int, ...]] = {}
    for line in value.splitlines():
        name, separator, payload = line.partition(":")
        if not separator or name not in {"Uid", "Gid", "Groups"}:
            continue
        if name in rows:
            raise RuntimeError("group-boundary status row is duplicated")
        fields = payload.split()
        if any(not field.isdecimal() for field in fields):
            raise RuntimeError("group-boundary status row is malformed")
        rows[name] = tuple(int(field, 10) for field in fields)
    if set(rows) != {"Uid", "Gid", "Groups"}:
        raise RuntimeError("group-boundary status row is missing")
    if len(rows["Uid"]) != 4 or len(rows["Gid"]) != 4:
        raise RuntimeError("group-boundary identity row is malformed")
    return rows["Uid"], rows["Gid"], rows["Groups"]


def _validate_rootless_group_boundary(
    *,
    expected_primary_count: int,
    expected_overflow_count: int,
) -> None:
    for count in (expected_primary_count, expected_overflow_count):
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or count > MAX_SUPPLEMENTARY_GROUPS
        ):
            raise RuntimeError("group-boundary expected count is invalid")
    if expected_primary_count + expected_overflow_count > MAX_SUPPLEMENTARY_GROUPS:
        raise RuntimeError("group-boundary expected count is invalid")

    if (
        os.getuid(),
        os.geteuid(),
        os.getgid(),
        os.getegid(),
    ) != (0, 0, 0, 0):
        raise RuntimeError("group-boundary process identity is not normalized")

    _parse_single_id_map(_read_fixed_ascii("/proc/self/uid_map", 4096))
    _parse_single_id_map(_read_fixed_ascii("/proc/self/gid_map", 4096))
    if _read_fixed_ascii("/proc/self/setgroups", 32) != "deny\n":
        raise RuntimeError("group-boundary setgroups state is not denied")

    overflow_text = _read_fixed_ascii(
        "/proc/sys/kernel/overflowgid",
        32,
    )
    if (
        not overflow_text.endswith("\n")
        or overflow_text.count("\n") != 1
        or not overflow_text[:-1].isascii()
        or not overflow_text[:-1].isdecimal()
    ):
        raise RuntimeError("group-boundary overflow GID is malformed")
    overflow_gid = int(overflow_text[:-1], 10)
    if overflow_gid <= 0 or overflow_gid > _UINT_MAX:
        raise RuntimeError("group-boundary overflow GID is ambiguous")

    uid_row, gid_row, status_groups = _parse_status_rows(
        _read_fixed_ascii("/proc/self/status", 65_536)
    )
    if uid_row != (0, 0, 0, 0) or gid_row != (0, 0, 0, 0):
        raise RuntimeError("group-boundary status identity is not normalized")
    observed_groups = tuple(os.getgroups())
    if status_groups != observed_groups:
        raise RuntimeError("group-boundary group observations disagree")
    if any(group not in (0, overflow_gid) for group in observed_groups):
        raise RuntimeError("group-boundary group is not primary or overflow")
    if (
        observed_groups.count(0) != expected_primary_count
        or observed_groups.count(overflow_gid) != expected_overflow_count
    ):
        raise RuntimeError("group-boundary expected counts do not match")


def _install_key_syscall_filter() -> None:
    if os.uname().machine != "x86_64":
        raise OSError(errno.ENOTSUP, "reviewed seccomp filter is x86_64-only")
    instructions = [
        _SockFilter(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, 4),
        _SockFilter(_BPF_JMP | _BPF_JEQ | _BPF_K, 1, 0, _AUDIT_ARCH_X86_64),
        _SockFilter(_BPF_RET | _BPF_K, 0, 0, _SECCOMP_RET_KILL_PROCESS),
        _SockFilter(_BPF_LD | _BPF_W | _BPF_ABS, 0, 0, 0),
    ]
    for syscall_number in (
        _X86_64_ADD_KEY,
        _X86_64_REQUEST_KEY,
        _X86_64_KEYCTL,
        _X32_SYSCALL_BIT | _X86_64_ADD_KEY,
        _X32_SYSCALL_BIT | _X86_64_REQUEST_KEY,
        _X32_SYSCALL_BIT | _X86_64_KEYCTL,
    ):
        instructions.extend(
            (
                _SockFilter(
                    _BPF_JMP | _BPF_JEQ | _BPF_K,
                    0,
                    1,
                    syscall_number,
                ),
                _SockFilter(_BPF_RET | _BPF_K, 0, 0, _EPERM_RESULT),
            )
        )
    instructions.append(
        _SockFilter(_BPF_RET | _BPF_K, 0, 0, _SECCOMP_RET_ALLOW)
    )
    array_type = _SockFilter * len(instructions)
    array = array_type(*instructions)
    program = _SockFprog(len=len(array), filter=array)
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "PR_SET_NO_NEW_PRIVS failed")
    if libc.prctl(
        _PR_SET_SECCOMP,
        _SECCOMP_MODE_FILTER,
        ctypes.byref(program),
        0,
        0,
    ) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "seccomp filter installation failed")


def _fixed_environment(
    credentials: dict[str, bytes],
    *,
    provider_prefix: str,
) -> dict[str, str]:
    environment = {
        "HOME": "/home/provider",
        "LANG": "C",
        "LC_ALL": "C",
        "PATH": f"{provider_prefix}/bin",
        "TMPDIR": "/tmp",
    }
    for name, raw_value in credentials.items():
        try:
            value = raw_value.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CredentialFrameError(
                "credential value cannot be represented in an environment"
            ) from exc
        if "\x00" in value:
            raise CredentialFrameError(
                "credential value cannot be represented in an environment"
            )
        environment[name] = value
    return environment


def _parse_count_argument(value: str) -> int:
    if not value or not value.isascii() or not value.isdecimal():
        raise CredentialFrameError("provider launch shim arguments are invalid")
    count = int(value, 10)
    if count > MAX_SUPPLEMENTARY_GROUPS:
        raise CredentialFrameError("provider launch shim arguments are invalid")
    return count


def _parse_shim_argv(
    argv: list[str],
) -> tuple[str, tuple[str, ...], int, int, int, tuple[str, ...]]:
    provider_prefix = ""
    declared: list[str] = []
    primary_count: int | None = None
    overflow_count: int | None = None
    boundary_ready_fd: int | None = None
    provider_prefix_seen = False
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            target = tuple(argv[index + 1 :])
            break
        if argument == "--provider-prefix" and index + 1 < len(argv):
            if provider_prefix_seen:
                raise CredentialFrameError(
                    "provider launch shim arguments are invalid"
                )
            provider_prefix_seen = True
            provider_prefix = argv[index + 1]
            index += 2
            continue
        if argument == "--credential-name" and index + 1 < len(argv):
            declared.append(argv[index + 1])
            index += 2
            continue
        if (
            argument == "--expected-primary-group-count"
            and index + 1 < len(argv)
            and primary_count is None
        ):
            primary_count = _parse_count_argument(argv[index + 1])
            index += 2
            continue
        if (
            argument == "--expected-overflow-group-count"
            and index + 1 < len(argv)
            and overflow_count is None
        ):
            overflow_count = _parse_count_argument(argv[index + 1])
            index += 2
            continue
        if (
            argument == "--boundary-ready-fd"
            and index + 1 < len(argv)
            and boundary_ready_fd is None
        ):
            value = argv[index + 1]
            if not value.isdecimal() or int(value, 10) != BOUNDARY_READY_FD:
                raise CredentialFrameError(
                    "provider launch shim arguments are invalid"
                )
            boundary_ready_fd = BOUNDARY_READY_FD
            index += 2
            continue
        raise CredentialFrameError("provider launch shim arguments are invalid")
    else:
        target = ()
    if (
        not provider_prefix.startswith("/")
        or provider_prefix == "/"
        or not target
        or not target[0].startswith("/")
        or primary_count is None
        or overflow_count is None
        or primary_count + overflow_count > MAX_SUPPLEMENTARY_GROUPS
        or boundary_ready_fd != BOUNDARY_READY_FD
    ):
        raise CredentialFrameError("provider launch shim arguments are invalid")
    return (
        provider_prefix,
        _validate_declared_names(tuple(declared)),
        primary_count,
        overflow_count,
        boundary_ready_fd,
        target,
    )


def shim_main(argv: list[str] | None = None) -> int:
    """Run the fixed-fd bootstrap and replace the process with the provider."""

    try:
        _close_fds_from_except(4, BOUNDARY_READY_FD)
        (
            provider_prefix,
            declared_names,
            expected_primary_count,
            expected_overflow_count,
            boundary_ready_fd,
            target,
        ) = _parse_shim_argv(list(sys.argv[1:] if argv is None else argv))
        _join_fresh_session_keyring()
        _validate_rootless_group_boundary(
            expected_primary_count=expected_primary_count,
            expected_overflow_count=expected_overflow_count,
        )
        _validate_nested_userns_disabled()
        _signal_boundary_ready(boundary_ready_fd)
        _close_fds_from(4)
        credentials = read_credentials_from_fd(3, declared_names=declared_names)
        environment = _fixed_environment(
            credentials,
            provider_prefix=provider_prefix,
        )
        credentials.clear()
        _install_key_syscall_filter()
        _close_fds_from(3)
        os.execve(target[0], target, environment)
    except BaseException:
        try:
            os.write(2, b"provider_launch_shim_failed\n")
        except OSError:
            pass
        return 125
    return 125


def launch_provider_via_shim(
    *,
    python_executable,
    shim_path,
    target_argv: tuple[str, ...],
    declared_names: tuple[str, ...],
    credentials: dict[str, bytes],
    provider_prefix: str = "/opt/orchestrator-provider",
    bootstrap_environment: dict[str, str] | None = None,
    extra_setup_fds: int = 0,
    artifact_paths: tuple[object, ...] = (),
    _test_only_broad_host_root: bool = False,
    _host_boundary_observer=None,
):
    """Test-only rootless wrapper; not an accepted isolation mount plan."""

    import json
    import selectors
    import subprocess
    import time

    if _test_only_broad_host_root is not True:
        raise CredentialFrameError(
            "broad host-root projection is test-only"
        )
    if bootstrap_environment is not None and bootstrap_environment != {}:
        raise CredentialFrameError(
            "provider bootstrap environment must be empty"
        )
    controller_groups = tuple(os.getgroups())
    controller_euid = os.geteuid()
    controller_primary_gid = os.getegid()
    if controller_euid == 0:
        raise CredentialFrameError(
            "rootless provider launch requires an unprivileged controller"
        )
    if len(controller_groups) > MAX_SUPPLEMENTARY_GROUPS:
        raise CredentialFrameError(
            "provider launch has too many supplementary groups"
        )
    primary_count = sum(
        group == controller_primary_gid for group in controller_groups
    )
    overflow_count = len(controller_groups) - primary_count

    shim_command = [
        os.fspath(python_executable),
        "-I",
        "-S",
        os.fspath(shim_path),
        "--provider-prefix",
        provider_prefix,
    ]
    for name in declared_names:
        shim_command.extend(["--credential-name", name])
    shim_command.extend(
        [
            "--expected-primary-group-count",
            str(primary_count),
            "--expected-overflow-group-count",
            str(overflow_count),
            "--boundary-ready-fd",
            str(BOUNDARY_READY_FD),
            "--",
        ]
    )
    shim_command.extend(target_argv)
    command = [
        "/usr/bin/bwrap",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--disable-userns",
        "--assert-userns-disabled",
        "--die-with-parent",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--clearenv",
        "--json-status-fd",
        "8",
        "--",
        *shim_command,
    ]

    frame = bytearray(
        encode_credential_frame(
            credentials,
            declared_names=tuple(declared_names),
        )
    )
    credential_read = -1
    credential_write = -1
    readiness_read = -1
    readiness_write = -1
    status_read = -1
    status_write = -1
    stdout_read = -1
    stdout_write = -1
    stderr_read = -1
    stderr_write = -1
    devnull = -1
    extras: list[int] = []
    extra_writes: list[int] = []
    fixed_fd_reservations: list[int] = []
    pid: int | None = None
    pinned_pidfd = -1
    pinned_proc_dir_fd = -1
    waited = False
    try:
        for fixed_fd in range(9):
            try:
                os.fstat(fixed_fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
                reservation = os.open(
                    os.devnull,
                    os.O_RDWR | os.O_CLOEXEC,
                )
                if reservation != fixed_fd:
                    os.close(reservation)
                    raise OSError(
                        errno.EBUSY,
                        "fixed descriptor reservation raced",
                    )
                fixed_fd_reservations.append(reservation)

        credential_read, credential_write = os.pipe()
        readiness_read, readiness_write = os.pipe()
        status_read, status_write = os.pipe()
        stdout_read, stdout_write = os.pipe()
        stderr_read, stderr_write = os.pipe()
        devnull = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
        for _index in range(extra_setup_fds):
            read_fd, write_fd = os.pipe()
            extras.append(read_fd)
            extra_writes.append(write_fd)

        for fd in extras:
            os.set_inheritable(fd, True)
        file_actions: list[tuple[int, ...]] = [
            (os.POSIX_SPAWN_DUP2, devnull, 0),
            (os.POSIX_SPAWN_DUP2, stdout_write, 1),
            (os.POSIX_SPAWN_DUP2, stderr_write, 2),
            (os.POSIX_SPAWN_DUP2, credential_read, 3),
            (os.POSIX_SPAWN_DUP2, readiness_write, BOUNDARY_READY_FD),
            (os.POSIX_SPAWN_DUP2, status_write, 8),
        ]
        for fd, target_fd in (
            (devnull, 0),
            (stdout_write, 1),
            (stderr_write, 2),
            (credential_read, 3),
            (readiness_write, BOUNDARY_READY_FD),
            (status_write, 8),
        ):
            if fd != target_fd:
                file_actions.append((os.POSIX_SPAWN_CLOSE, fd))
        pid = os.posix_spawn(
            command[0],
            command,
            {},
            file_actions=file_actions,
        )

        os.close(credential_read)
        credential_read = -1
        os.close(readiness_write)
        readiness_write = -1
        os.close(status_write)
        status_write = -1
        os.close(stdout_write)
        stdout_write = -1
        os.close(stderr_write)
        stderr_write = -1
        os.close(devnull)
        devnull = -1
        for index, fd in enumerate(fixed_fd_reservations):
            os.close(fd)
            fixed_fd_reservations[index] = -1
        for index, fd in enumerate(extras):
            os.close(fd)
            extras[index] = -1
        for index, fd in enumerate(extra_writes):
            os.close(fd)
            extra_writes[index] = -1

        child_pid = _wait_for_bwrap_child_pid(
            status_read,
            selector_factory=selectors.DefaultSelector,
            json_loads=json.loads,
            monotonic=time.monotonic,
        )
        (
            pinned_pidfd,
            pinned_proc_dir_fd,
            pinned_starttime,
        ) = _pin_rootless_child(
            child_pid,
            selector_factory=selectors.DefaultSelector,
        )
        _wait_for_boundary_ready(
            readiness_read,
            selector_factory=selectors.DefaultSelector,
            monotonic=time.monotonic,
        )
        os.close(readiness_read)
        readiness_read = -1
        if _host_boundary_observer is not None:
            _host_boundary_observer(
                child_pid=child_pid,
                controller_euid=controller_euid,
                controller_egid=controller_primary_gid,
                controller_groups=controller_groups,
                expected_primary_count=primary_count,
                expected_overflow_count=overflow_count,
            )
        _validate_pinned_rootless_child_boundary(
            child_pid=child_pid,
            pidfd=pinned_pidfd,
            proc_dir_fd=pinned_proc_dir_fd,
            starttime=pinned_starttime,
            controller_euid=controller_euid,
            controller_egid=controller_primary_gid,
            controller_groups=controller_groups,
            expected_primary_count=primary_count,
            expected_overflow_count=overflow_count,
            selector_factory=selectors.DefaultSelector,
        )

        view = memoryview(frame)
        try:
            offset = 0
            while offset < len(frame):
                offset += os.write(credential_write, view[offset:])
        except BrokenPipeError:
            pass
        finally:
            view.release()
            os.close(credential_write)
            credential_write = -1

        selector = selectors.DefaultSelector()
        output = {"stdout": bytearray(), "stderr": bytearray()}
        try:
            selector.register(stdout_read, selectors.EVENT_READ, "stdout")
            selector.register(stderr_read, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                for key, _events in selector.select():
                    chunk = os.read(key.fd, 65_536)
                    if chunk:
                        output[key.data].extend(chunk)
                        continue
                    selector.unregister(key.fd)
                    os.close(key.fd)
                    if key.data == "stdout":
                        stdout_read = -1
                    else:
                        stderr_read = -1
        finally:
            selector.close()

        _waited_pid, status = os.waitpid(pid, 0)
        waited = True
        return subprocess.CompletedProcess(
            args=command,
            returncode=os.waitstatus_to_exitcode(status),
            stdout=bytes(output["stdout"]).decode("utf-8", errors="replace"),
            stderr=bytes(output["stderr"]).decode("utf-8", errors="replace"),
        )
    finally:
        _zero(frame)
        for fd in [
            credential_read,
            credential_write,
            readiness_read,
            readiness_write,
            status_read,
            status_write,
            stdout_read,
            stdout_write,
            stderr_read,
            stderr_write,
            devnull,
            *fixed_fd_reservations,
            *extras,
            *extra_writes,
            pinned_pidfd,
            pinned_proc_dir_fd,
        ]:
            if fd < 0:
                continue
            try:
                os.close(fd)
            except OSError:
                pass
        if pid is not None and not waited:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
            try:
                os.waitpid(pid, 0)
            except ChildProcessError:
                pass
        # This helper never creates artifacts; the argument exists so callers
        # can assert the no-persistence contract over selected authorities.
        tuple(artifact_paths)


if __name__ == "__main__":
    raise SystemExit(shim_main())


__all__ = [
    "CREDENTIAL_FRAME_MAGIC",
    "CREDENTIAL_FRAME_VERSION",
    "CredentialFrameError",
    "MAX_CREDENTIAL_FRAME_BYTES",
    "MAX_CREDENTIAL_NAMES",
    "MAX_CREDENTIAL_NAME_BYTES",
    "MAX_CREDENTIAL_VALUE_BYTES",
    "decode_credential_frame",
    "encode_credential_frame",
    "launch_provider_via_shim",
    "read_credentials_from_fd",
    "shim_main",
]
