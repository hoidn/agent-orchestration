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
_KEYCTL_JOIN_SESSION_KEYRING = 1
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


def _close_fds_from(start: int) -> None:
    """Close every descriptor from ``start`` without relying on CLOEXEC/bwrap."""

    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(
        ctypes.c_long(_SYS_CLOSE_RANGE),
        ctypes.c_uint(start),
        ctypes.c_uint(_UINT_MAX),
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
        if fd < start:
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
        if fd < start:
            continue
        try:
            os.fstat(fd)
        except OSError as exc:
            if exc.errno == errno.EBADF:
                continue
            raise
        raise OSError(errno.EBUSY, "fd closure verification found an open descriptor")


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


def _drop_supplementary_groups() -> None:
    try:
        os.setgroups([])
    except PermissionError:
        if os.getgroups():
            raise
    if os.getgroups():
        raise RuntimeError("supplementary groups remain after drop")


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


def _parse_shim_argv(argv: list[str]) -> tuple[str, tuple[str, ...], tuple[str, ...]]:
    provider_prefix = ""
    declared: list[str] = []
    index = 0
    while index < len(argv):
        argument = argv[index]
        if argument == "--":
            target = tuple(argv[index + 1 :])
            break
        if argument == "--provider-prefix" and index + 1 < len(argv):
            provider_prefix = argv[index + 1]
            index += 2
            continue
        if argument == "--credential-name" and index + 1 < len(argv):
            declared.append(argv[index + 1])
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
    ):
        raise CredentialFrameError("provider launch shim arguments are invalid")
    return provider_prefix, _validate_declared_names(tuple(declared)), target


def shim_main(argv: list[str] | None = None) -> int:
    """Run the fixed-fd bootstrap and replace the process with the provider."""

    try:
        provider_prefix, declared_names, target = _parse_shim_argv(
            list(sys.argv[1:] if argv is None else argv)
        )
        _close_fds_from(4)
        _join_fresh_session_keyring()
        _drop_supplementary_groups()
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
):
    """Controller-side test/raw-probe helper using only the fd-3 secret pipe."""

    import subprocess

    if bootstrap_environment is not None and bootstrap_environment != {}:
        raise CredentialFrameError(
            "provider bootstrap environment must be empty"
        )
    command = [
        os.fspath(python_executable),
        "-I",
        "-S",
        os.fspath(shim_path),
        "--provider-prefix",
        provider_prefix,
    ]
    for name in declared_names:
        command.extend(["--credential-name", name])
    command.append("--")
    command.extend(target_argv)

    frame = bytearray(
        encode_credential_frame(
            credentials,
            declared_names=tuple(declared_names),
        )
    )
    credential_read = -1
    credential_write = -1
    stdout_read = -1
    stdout_write = -1
    stderr_read = -1
    stderr_write = -1
    devnull = -1
    extras: list[int] = []
    extra_writes: list[int] = []
    stdio_reservations: list[int] = []
    pid: int | None = None
    waited = False
    try:
        for standard_fd in (0, 1, 2):
            try:
                os.fstat(standard_fd)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
                reservation = os.open(
                    os.devnull,
                    os.O_RDWR | os.O_CLOEXEC,
                )
                if reservation != standard_fd:
                    os.close(reservation)
                    raise OSError(
                        errno.EBUSY,
                        "standard descriptor reservation raced",
                    )
                stdio_reservations.append(reservation)

        credential_read, credential_write = os.pipe()
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
        ]
        for fd, target_fd in (
            (devnull, 0),
            (stdout_write, 1),
            (stderr_write, 2),
            (credential_read, 3),
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
        os.close(stdout_write)
        stdout_write = -1
        os.close(stderr_write)
        stderr_write = -1
        os.close(devnull)
        devnull = -1
        for index, fd in enumerate(stdio_reservations):
            os.close(fd)
            stdio_reservations[index] = -1
        for index, fd in enumerate(extras):
            os.close(fd)
            extras[index] = -1
        for index, fd in enumerate(extra_writes):
            os.close(fd)
            extra_writes[index] = -1

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

        import selectors

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
            stdout_read,
            stdout_write,
            stderr_read,
            stderr_write,
            devnull,
            *stdio_reservations,
            *extras,
            *extra_writes,
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
