from __future__ import annotations

import ast
import ctypes
from dataclasses import replace
import errno
import fcntl
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import selectors
import shutil
import stat
import struct
import subprocess
import sys

import pytest


PROVIDER_PREFIX = "/opt/orchestrator-provider"
CONVENTIONAL_LOADER = "/lib64/ld-linux-x86-64.so.2"
REVIEWED_X86_64_SYSTEM_PYTHON_RUNTIME = (
    "/lib64/ld-linux-x86-64.so.2",
    "/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
    "/lib/x86_64-linux-gnu/libm.so.6",
    "/lib/x86_64-linux-gnu/libz.so.1",
    "/lib/x86_64-linux-gnu/libexpat.so.1",
    "/lib/x86_64-linux-gnu/libc.so.6",
)
GLIBC_CACHE_PATH = "/etc/ld.so.cache"
GLIBC_CACHE_MAGIC = b"glibc-ld.so.cache"
GLIBC_CACHE_VERSION = b"1.1"
GLIBC_CACHE_X86_64_FLAGS = 0x303


def _api():
    return importlib.import_module("orchestrator.providers.provider_launch_shim")


def _environment_api():
    return importlib.import_module("orchestrator.providers.isolation_environment")


def _require_rootless_bwrap() -> None:
    command = [
        "/usr/bin/bwrap",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--disable-userns",
        "--assert-userns-disabled",
        "--ro-bind",
        "/",
        "/",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--",
        "/bin/true",
    ]
    try:
        result = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"reviewed rootless Bubblewrap is unavailable: {exc}")
    if result.returncode:
        pytest.skip(
            "reviewed rootless Bubblewrap is unavailable: "
            f"{result.stderr.strip()}"
        )


def test_credential_frame_round_trip_is_closed_and_binary() -> None:
    api = _api()
    frame = api.encode_credential_frame(
        {"TOKEN": b"\x00secret\xff", "EMPTY": b""},
        declared_names=("TOKEN", "EMPTY"),
    )
    assert frame.startswith(api.CREDENTIAL_FRAME_MAGIC)
    assert b"provider_launch_credentials.v1" not in frame
    assert api.decode_credential_frame(
        bytearray(frame), declared_names=("TOKEN", "EMPTY")
    ) == {"TOKEN": b"\x00secret\xff", "EMPTY": b""}


@pytest.mark.parametrize(
    ("credentials", "declared"),
    [
        ({"TOKEN": b"x"}, tuple(f"N{i}" for i in range(33))),
        ({"A" * 129: b"x"}, ("A" * 129,)),
        ({"TOKEN": b"x" * 65_537}, ("TOKEN",)),
        ({"TOKEN": b"x"}, ("TOKEN", "TOKEN")),
        ({"UNDECLARED": b"x"}, ("TOKEN",)),
        ({"bad-name": b"x"}, ("bad-name",)),
        ({"PYTHONPATH": b"x"}, ("PYTHONPATH",)),
    ],
)
def test_credential_frame_rejects_bound_and_declaration_violations(
    credentials: dict[str, bytes], declared: tuple[str, ...]
) -> None:
    with pytest.raises(_api().CredentialFrameError):
        _api().encode_credential_frame(credentials, declared_names=declared)


def test_credential_frame_rejects_total_over_262144_bytes() -> None:
    api = _api()
    credentials = {f"N{i}": b"x" * 65_536 for i in range(5)}
    with pytest.raises(api.CredentialFrameError, match="total"):
        api.encode_credential_frame(
            credentials, declared_names=tuple(credentials)
        )


@pytest.mark.parametrize(
    "mutator",
    [
        lambda api, frame: frame[:3],
        lambda api, frame: b"BADMAGIC" + frame[len(api.CREDENTIAL_FRAME_MAGIC) :],
        lambda api, frame: (
            frame[: len(api.CREDENTIAL_FRAME_MAGIC)]
            + b"\x00\x02"
            + frame[len(api.CREDENTIAL_FRAME_MAGIC) + 2 :]
        ),
        lambda api, frame: frame[:-1],
        lambda api, frame: frame + b"trailing",
    ],
)
def test_credential_frame_rejects_truncated_magic_version_and_trailing_data(
    mutator,
) -> None:
    api = _api()
    frame = api.encode_credential_frame({"TOKEN": b"value"}, declared_names=("TOKEN",))
    with pytest.raises(api.CredentialFrameError):
        api.decode_credential_frame(
            bytearray(mutator(api, frame)), declared_names=("TOKEN",)
        )


def test_credential_frame_rejects_duplicate_and_undeclared_wire_names() -> None:
    api = _api()

    def raw_frame(rows: list[tuple[str, bytes]]) -> bytes:
        payload = bytearray()
        for name, value in rows:
            encoded_name = name.encode("utf-8")
            payload += struct.pack(">HI", len(encoded_name), len(value))
            payload += encoded_name
            payload += value
        total = struct.calcsize(">8sHHI") + len(payload)
        return (
            struct.pack(
                ">8sHHI",
                api.CREDENTIAL_FRAME_MAGIC,
                api.CREDENTIAL_FRAME_VERSION,
                len(rows),
                total,
            )
            + payload
        )

    duplicate = raw_frame([("TOKEN", b"a"), ("TOKEN", b"b")])
    undeclared = raw_frame([("OTHER", b"a")])
    with pytest.raises(api.CredentialFrameError, match="duplicate"):
        api.decode_credential_frame(
            bytearray(duplicate), declared_names=("TOKEN",)
        )
    with pytest.raises(api.CredentialFrameError, match="undeclared"):
        api.decode_credential_frame(
            bytearray(undeclared), declared_names=("TOKEN",)
        )


def test_decode_zeroes_mutable_input_on_success_and_failure() -> None:
    api = _api()
    good = bytearray(
        api.encode_credential_frame({"TOKEN": b"value"}, declared_names=("TOKEN",))
    )
    assert api.decode_credential_frame(good, declared_names=("TOKEN",)) == {
        "TOKEN": b"value"
    }
    assert good == bytearray(len(good))

    bad = bytearray(b"secret malformed frame")
    with pytest.raises(api.CredentialFrameError):
        api.decode_credential_frame(bad, declared_names=("TOKEN",))
    assert bad == bytearray(len(bad))


def test_decode_zeroes_input_when_declarations_are_invalid() -> None:
    api = _api()
    frame = bytearray(
        api.encode_credential_frame(
            {"TOKEN": b"value"},
            declared_names=("TOKEN",),
        )
    )

    with pytest.raises(api.CredentialFrameError):
        api.decode_credential_frame(
            frame,
            declared_names=("TOKEN", "TOKEN"),
        )

    assert frame == bytearray(len(frame))


def test_encoder_zeroes_partial_payload_when_later_value_is_invalid(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    zeroed: list[bytes] = []
    real_zero = api._zero

    def observe_zero(value: bytearray) -> None:
        real_zero(value)
        zeroed.append(bytes(value))

    monkeypatch.setattr(api, "_zero", observe_zero)

    with pytest.raises(api.CredentialFrameError):
        api.encode_credential_frame(
            {"FIRST": b"secret", "SECOND": "not-bytes"},
            declared_names=("FIRST", "SECOND"),
        )

    assert zeroed
    assert all(value == bytes(len(value)) for value in zeroed)


@pytest.mark.parametrize(
    "row_header",
    [
        struct.pack(">HI", 129, 0),
        struct.pack(">HI", 1, 65_537),
    ],
)
def test_decode_rejects_oversized_wire_fields_and_zeroes_input(
    row_header: bytes,
) -> None:
    api = _api()
    payload = row_header + b"TOKEN"
    frame = bytearray(
        struct.pack(
            ">8sHHI",
            api.CREDENTIAL_FRAME_MAGIC,
            api.CREDENTIAL_FRAME_VERSION,
            1,
            struct.calcsize(">8sHHI") + len(payload),
        )
        + payload
    )

    with pytest.raises(api.CredentialFrameError):
        api.decode_credential_frame(frame, declared_names=("TOKEN",))

    assert frame == bytearray(len(frame))


def test_read_fd3_is_bounded_and_closes_descriptor() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    frame = api.encode_credential_frame({"TOKEN": b"value"}, declared_names=("TOKEN",))
    os.write(write_fd, frame)
    os.close(write_fd)
    try:
        assert api.read_credentials_from_fd(
            read_fd, declared_names=("TOKEN",)
        ) == {"TOKEN": b"value"}
        with pytest.raises(OSError):
            os.fstat(read_fd)
    finally:
        try:
            os.close(read_fd)
        except OSError:
            pass


def test_fdwalk_fallback_fails_closed_if_any_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()

    class _NoCloseRange:
        @staticmethod
        def syscall(*_args) -> int:
            ctypes.set_errno(errno.ENOSYS)
            return -1

    real_close = os.close

    def fail_one_close(fd: int) -> None:
        if fd == 91:
            raise OSError(errno.EIO, "injected close failure")
        real_close(fd)

    monkeypatch.setattr(api.ctypes, "CDLL", lambda *_args, **_kwargs: _NoCloseRange())
    monkeypatch.setattr(api.os, "listdir", lambda _path: ["91"])
    monkeypatch.setattr(api.os, "close", fail_one_close)

    with pytest.raises(OSError) as exc_info:
        api._close_fds_from(4)

    assert exc_info.value.errno == errno.EIO


def test_fdwalk_fallback_fails_unavailable_without_proc_inventory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()

    class _NoCloseRange:
        @staticmethod
        def syscall(*_args) -> int:
            ctypes.set_errno(errno.ENOSYS)
            return -1

    monkeypatch.setattr(api.ctypes, "CDLL", lambda *_args, **_kwargs: _NoCloseRange())
    monkeypatch.setattr(
        api.os,
        "listdir",
        lambda _path: (_ for _ in ()).throw(OSError(errno.ENOENT, "no proc")),
    )

    with pytest.raises(OSError) as exc_info:
        api._close_fds_from(4)

    assert exc_info.value.errno == errno.ENOTSUP


def test_two_fd_sweeps_close_inherited_and_bootstrap_opened_high_fds() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        os.dup2(write_fd, 1)
        if write_fd != 1:
            os.close(write_fd)
        try:
            inherited = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
            inherited_high = fcntl.fcntl(inherited, fcntl.F_DUPFD, 256)
            os.close(inherited)
            api._close_fds_from(4)
            try:
                os.fstat(inherited_high)
            except OSError as exc:
                inherited_closed = exc.errno == errno.EBADF
            else:
                inherited_closed = False

            bootstrap = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
            bootstrap_high = fcntl.fcntl(bootstrap, fcntl.F_DUPFD, 320)
            os.close(bootstrap)
            api._close_fds_from(3)
            try:
                os.fstat(bootstrap_high)
            except OSError as exc:
                bootstrap_closed = exc.errno == errno.EBADF
            else:
                bootstrap_closed = False

            os.write(
                1,
                json.dumps(
                    {
                        "inherited_closed": inherited_closed,
                        "bootstrap_closed": bootstrap_closed,
                    }
                ).encode("utf-8"),
            )
            os._exit(0)
        except BaseException:
            os._exit(127)

    os.close(write_fd)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(read_fd, 65_536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_fd)
    _waited_pid, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    assert json.loads(b"".join(chunks)) == {
        "inherited_closed": True,
        "bootstrap_closed": True,
    }


def test_shim_seccomp_denies_native_and_x32_key_syscall_numbers() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            api._install_key_syscall_filter()
            libc = ctypes.CDLL(None, use_errno=True)
            observed: dict[str, tuple[int, int]] = {}
            for syscall_number in (
                248,
                249,
                250,
                0x40000000 | 248,
                0x40000000 | 249,
                0x40000000 | 250,
            ):
                ctypes.set_errno(0)
                result = libc.syscall(
                    ctypes.c_long(syscall_number),
                    ctypes.c_void_p(),
                    ctypes.c_void_p(),
                    ctypes.c_void_p(),
                    ctypes.c_void_p(),
                    ctypes.c_void_p(),
                )
                observed[str(syscall_number)] = (result, ctypes.get_errno())
            os.write(write_fd, json.dumps(observed).encode("utf-8"))
            os._exit(0)
        except BaseException:
            os._exit(127)

    os.close(write_fd)
    chunks: list[bytes] = []
    while True:
        chunk = os.read(read_fd, 65_536)
        if not chunk:
            break
        chunks.append(chunk)
    os.close(read_fd)
    _waited_pid, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    observed = json.loads(b"".join(chunks))
    assert observed
    assert all(
        result == -1 and error == errno.EPERM
        for result, error in observed.values()
    )


def test_join_fresh_session_keyring_requests_anonymous_replacement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    calls: list[tuple[int | None, ...]] = []

    class _RecordingLibc:
        @staticmethod
        def syscall(*args) -> int:
            calls.append(
                tuple(getattr(argument, "value", argument) for argument in args)
            )
            return 77

    monkeypatch.setattr(
        api.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _RecordingLibc(),
    )

    api._join_fresh_session_keyring()

    assert calls == [(250, 1, None)]


@pytest.mark.parametrize("denial_errno", [errno.EPERM, errno.ENOSPC])
def test_validate_nested_userns_disabled_requires_kernel_denial(
    monkeypatch: pytest.MonkeyPatch,
    denial_errno: int,
) -> None:
    api = _api()
    calls: list[tuple[int | None, ...]] = []

    class _DeniedLibc:
        @staticmethod
        def syscall(*args) -> int:
            calls.append(
                tuple(getattr(argument, "value", argument) for argument in args)
            )
            ctypes.set_errno(denial_errno)
            return -1

    monkeypatch.setattr(
        api.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _DeniedLibc(),
    )

    api._validate_nested_userns_disabled()

    assert calls == [(272, 0x10000000)]


@pytest.mark.parametrize(
    ("result", "error"),
    [
        (0, 0),
        (-1, errno.EINVAL),
        (-1, errno.ENOSYS),
    ],
)
def test_validate_nested_userns_disabled_rejects_non_denial(
    monkeypatch: pytest.MonkeyPatch,
    result: int,
    error: int,
) -> None:
    api = _api()

    class _UnexpectedLibc:
        @staticmethod
        def syscall(*_args) -> int:
            ctypes.set_errno(error)
            return result

    monkeypatch.setattr(
        api.ctypes,
        "CDLL",
        lambda *_args, **_kwargs: _UnexpectedLibc(),
    )

    with pytest.raises(OSError):
        api._validate_nested_userns_disabled()


def _install_group_boundary_observations(
    api,
    monkeypatch: pytest.MonkeyPatch,
    *,
    overrides: dict[str, str] | None = None,
    groups: tuple[int, ...] = (0, 65534, 65534),
) -> None:
    observations = {
        "/proc/self/uid_map": "0 1000 1\n",
        "/proc/self/gid_map": "0 1000 1\n",
        "/proc/self/setgroups": "deny\n",
        "/proc/self/status": (
            "Name:\tprovider\n"
            "Uid:\t0\t0\t0\t0\n"
            "Gid:\t0\t0\t0\t0\n"
            f"Groups:\t{' '.join(str(group) for group in groups)}\n"
        ),
        "/proc/sys/kernel/overflowgid": "65534\n",
    }
    observations.update(overrides or {})

    def read_fixed_ascii(path, _max_bytes: int) -> str:
        return observations[os.fspath(path)]

    monkeypatch.setattr(api, "_read_fixed_ascii", read_fixed_ascii)
    monkeypatch.setattr(api.os, "getuid", lambda: 0)
    monkeypatch.setattr(api.os, "geteuid", lambda: 0)
    monkeypatch.setattr(api.os, "getgid", lambda: 0)
    monkeypatch.setattr(api.os, "getegid", lambda: 0)
    monkeypatch.setattr(api.os, "getgroups", lambda: list(groups))


def test_validate_rootless_group_boundary_accepts_normalized_observations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch)

    api._validate_rootless_group_boundary(
        expected_primary_count=1,
        expected_overflow_count=2,
    )


@pytest.mark.parametrize(
    ("row_name", "column"),
    [("Uid", index) for index in range(4)]
    + [("Gid", index) for index in range(4)],
)
def test_validate_rootless_group_boundary_rejects_each_nonzero_status_identity(
    monkeypatch: pytest.MonkeyPatch,
    row_name: str,
    column: int,
) -> None:
    api = _api()
    values = ["0", "0", "0", "0"]
    values[column] = "1"
    status = (
        "Uid:\t0\t0\t0\t0\n"
        "Gid:\t0\t0\t0\t0\n"
        "Groups:\t0 65534 65534\n"
    ).replace(f"{row_name}:\t0\t0\t0\t0", f"{row_name}:\t" + "\t".join(values))
    _install_group_boundary_observations(
        api,
        monkeypatch,
        overrides={"/proc/self/status": status},
    )

    with pytest.raises(RuntimeError):
        api._validate_rootless_group_boundary(
            expected_primary_count=1,
            expected_overflow_count=2,
        )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("/proc/self/uid_map", ""),
        ("/proc/self/uid_map", "0 1000 1\n1 1001 1\n"),
        ("/proc/self/gid_map", "0 1000 2\n"),
        ("/proc/self/gid_map", "not a map\n"),
        ("/proc/self/setgroups", ""),
        ("/proc/self/setgroups", "allow\n"),
        ("/proc/self/setgroups", "deny\r\n"),
        ("/proc/self/setgroups", "deny\v"),
        ("/proc/sys/kernel/overflowgid", "0\n"),
        ("/proc/sys/kernel/overflowgid", f"{1 << 32}\n"),
        ("/proc/sys/kernel/overflowgid", "not-a-gid\n"),
        (
            "/proc/self/status",
            "Uid:\t0\t0\t0\t0\nGid:\t0\t0\t0\t0\n",
        ),
        (
            "/proc/self/status",
            "Uid:\t0\t0\t0\t0\n"
            "Gid:\t0\t0\t0\t0\n"
            "Groups:\t0 65534\n"
            "Groups:\t0 65534\n",
        ),
    ],
)
def test_validate_rootless_group_boundary_rejects_malformed_observation(
    monkeypatch: pytest.MonkeyPatch,
    path: str,
    value: str,
) -> None:
    api = _api()
    _install_group_boundary_observations(
        api,
        monkeypatch,
        overrides={path: value},
    )

    with pytest.raises((RuntimeError, ValueError)):
        api._validate_rootless_group_boundary(
            expected_primary_count=1,
            expected_overflow_count=2,
        )


@pytest.mark.parametrize(
    ("groups", "primary_count", "overflow_count"),
    [
        ((0, 27, 65534), 1, 1),
        ((0, 65534), 1, 2),
        ((0, 65534, 65534), 0, 3),
    ],
)
def test_validate_rootless_group_boundary_rejects_group_or_count_mismatch(
    monkeypatch: pytest.MonkeyPatch,
    groups: tuple[int, ...],
    primary_count: int,
    overflow_count: int,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch, groups=groups)

    with pytest.raises(RuntimeError):
        api._validate_rootless_group_boundary(
            expected_primary_count=primary_count,
            expected_overflow_count=overflow_count,
        )


def test_validate_rootless_group_boundary_rejects_disagreeing_group_views(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch)
    monkeypatch.setattr(api.os, "getgroups", lambda: [0, 65534])

    with pytest.raises(RuntimeError):
        api._validate_rootless_group_boundary(
            expected_primary_count=1,
            expected_overflow_count=2,
        )


@pytest.mark.parametrize(
    "getter_name",
    ["getuid", "geteuid", "getgid", "getegid"],
)
def test_validate_rootless_group_boundary_rejects_nonzero_process_identity(
    monkeypatch: pytest.MonkeyPatch,
    getter_name: str,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch)
    monkeypatch.setattr(api.os, getter_name, lambda: 1)

    with pytest.raises(RuntimeError, match="identity"):
        api._validate_rootless_group_boundary(
            expected_primary_count=1,
            expected_overflow_count=2,
        )


@pytest.mark.parametrize(
    ("primary_count", "overflow_count"),
    [
        (-1, 0),
        (True, 0),
        (0, 65_537),
        (65_536, 1),
    ],
)
def test_validate_rootless_group_boundary_rejects_invalid_expected_counts(
    monkeypatch: pytest.MonkeyPatch,
    primary_count,
    overflow_count,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch)

    with pytest.raises(RuntimeError):
        api._validate_rootless_group_boundary(
            expected_primary_count=primary_count,
            expected_overflow_count=overflow_count,
        )


def test_validate_rootless_group_boundary_rejects_unreadable_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    _install_group_boundary_observations(api, monkeypatch)
    read_observation = api._read_fixed_ascii

    def unreadable(path: str, _max_bytes: int) -> str:
        if path == "/proc/self/gid_map":
            raise OSError(errno.EACCES, "injected unreadable observation")
        return read_observation(path, _max_bytes)

    monkeypatch.setattr(api, "_read_fixed_ascii", unreadable)

    with pytest.raises(OSError, match="unreadable observation"):
        api._validate_rootless_group_boundary(
            expected_primary_count=1,
            expected_overflow_count=2,
        )


def test_fixed_group_boundary_reader_accepts_strict_ascii_and_closes_fd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"deny\n")
    os.close(write_fd)
    monkeypatch.setattr(api.os, "open", lambda *_args, **_kwargs: read_fd)

    assert api._read_fixed_ascii("/proc/self/setgroups", 32) == "deny\n"
    with pytest.raises(OSError) as exc_info:
        os.fstat(read_fd)
    assert exc_info.value.errno == errno.EBADF


@pytest.mark.parametrize(
    ("payload", "bound", "match"),
    [
        (b"\xff", 32, "strict ASCII"),
        (b"x" * 33, 32, "oversized"),
    ],
)
def test_fixed_group_boundary_reader_rejects_invalid_content_and_closes_fd(
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
    bound: int,
    match: str,
) -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    os.write(write_fd, payload)
    os.close(write_fd)
    monkeypatch.setattr(api.os, "open", lambda *_args, **_kwargs: read_fd)

    with pytest.raises(RuntimeError, match=match):
        api._read_fixed_ascii("/proc/self/status", bound)
    with pytest.raises(OSError) as exc_info:
        os.fstat(read_fd)
    assert exc_info.value.errno == errno.EBADF


@pytest.mark.parametrize("bound", [0, -1, True, 65_537])
def test_fixed_group_boundary_reader_rejects_invalid_bound_before_open(
    monkeypatch: pytest.MonkeyPatch,
    bound,
) -> None:
    api = _api()
    opened = False

    def observe_open(*_args, **_kwargs):
        nonlocal opened
        opened = True
        raise AssertionError("invalid bound must reject before open")

    monkeypatch.setattr(api.os, "open", observe_open)

    with pytest.raises(RuntimeError, match="bound"):
        api._read_fixed_ascii("/proc/self/status", bound)
    assert not opened


def test_fixed_group_boundary_reader_rejects_caller_supplied_path() -> None:
    with pytest.raises(RuntimeError, match="not fixed"):
        _api()._read_fixed_ascii("/tmp/caller-supplied", 32)


def test_boundary_readiness_signal_is_exact_and_closes_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    events: list[object] = []

    monkeypatch.setattr(
        api.os,
        "write",
        lambda fd, payload: events.append(("write", fd, payload)) or len(payload),
    )
    monkeypatch.setattr(api.os, "close", lambda fd: events.append(("close", fd)))

    def closed_fstat(fd: int):
        events.append(("fstat", fd))
        raise OSError(errno.EBADF, "closed")

    monkeypatch.setattr(api.os, "fstat", closed_fstat)

    api._signal_boundary_ready(api.BOUNDARY_READY_FD)

    assert events == [
        ("write", api.BOUNDARY_READY_FD, api.BOUNDARY_READY_BYTE),
        ("close", api.BOUNDARY_READY_FD),
        ("fstat", api.BOUNDARY_READY_FD),
    ]


def test_close_fds_except_sweeps_before_rejecting_missing_preserved_fd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    closed_ranges: list[tuple[int, int]] = []

    monkeypatch.setattr(
        api,
        "_close_fd_range",
        lambda start, end: closed_ranges.append((start, end)),
    )
    monkeypatch.setattr(
        api.os,
        "fstat",
        lambda _fd: (_ for _ in ()).throw(OSError(errno.EBADF, "missing")),
    )

    with pytest.raises(OSError) as exc_info:
        api._close_fds_from_except(4, api.BOUNDARY_READY_FD)

    assert exc_info.value.errno == errno.EBADF
    assert closed_ranges == [(4, 6), (8, (1 << 32) - 1)]


@pytest.mark.parametrize(
    ("payload", "expected_errno"),
    [
        (b"", errno.EPROTO),
        (b"RR", errno.EPROTO),
        (b"X", errno.EPROTO),
    ],
)
def test_wait_for_boundary_ready_rejects_missing_duplicate_or_malformed_signal(
    payload: bytes,
    expected_errno: int,
) -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    try:
        if payload:
            os.write(write_fd, payload)
        os.close(write_fd)
        write_fd = -1

        with pytest.raises(OSError) as exc_info:
            api._wait_for_boundary_ready(
                read_fd,
                selector_factory=selectors.DefaultSelector,
                monotonic=lambda: 0.0,
                timeout_seconds=0,
            )

        assert exc_info.value.errno == expected_errno
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


def test_wait_for_boundary_ready_rejects_surviving_write_descriptor() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    try:
        os.write(write_fd, api.BOUNDARY_READY_BYTE)

        with pytest.raises(OSError) as exc_info:
            api._wait_for_boundary_ready(
                read_fd,
                selector_factory=selectors.DefaultSelector,
                monotonic=lambda: 0.0,
                timeout_seconds=0,
            )

        assert exc_info.value.errno == errno.ETIMEDOUT
    finally:
        os.close(read_fd)
        os.close(write_fd)


def test_wait_for_bwrap_child_pid_ignores_unknown_status_then_accepts_pid() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    try:
        os.write(
            write_fd,
            b'{"future-status": true}\n'
            b'{"child-pid": 1234, "future-member": "ignored"}\n',
        )

        assert (
            api._wait_for_bwrap_child_pid(
                read_fd,
                selector_factory=selectors.DefaultSelector,
                json_loads=json.loads,
                monotonic=lambda: 0.0,
                timeout_seconds=0,
            )
            == 1234
        )
    finally:
        os.close(read_fd)
        os.close(write_fd)


@pytest.mark.parametrize(
    "status",
    [
        b"",
        b"not-json\n",
        b"[]\n",
        b'{"child-pid": true}\n',
        b'{"child-pid": 0}\n',
        b'{"child-pid": "1234"}\n',
        b'{"child-pid": 1, "child-pid": 2}\n',
    ],
)
def test_wait_for_bwrap_child_pid_rejects_invalid_or_missing_status(
    status: bytes,
) -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    try:
        if status:
            os.write(write_fd, status)
        os.close(write_fd)
        write_fd = -1

        with pytest.raises(OSError) as exc_info:
            api._wait_for_bwrap_child_pid(
                read_fd,
                selector_factory=selectors.DefaultSelector,
                json_loads=json.loads,
                monotonic=lambda: 0.0,
                timeout_seconds=0,
            )

        assert exc_info.value.errno == errno.EPROTO
    finally:
        os.close(read_fd)
        if write_fd >= 0:
            os.close(write_fd)


def test_wait_for_bwrap_child_pid_enforces_cumulative_byte_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    chunk = b'{"future-status":"' + (b"x" * 3975) + b'"}\n'
    chunks = [chunk] * 17

    class _AlwaysReadySelector:
        def register(self, _fd, _events) -> None:
            return None

        def select(self, _timeout=None):
            return [(object(), 1)]

        def close(self) -> None:
            return None

    monkeypatch.setattr(api.os, "read", lambda _fd, _bound: chunks.pop(0))

    with pytest.raises(OSError) as exc_info:
        api._wait_for_bwrap_child_pid(
            123,
            selector_factory=_AlwaysReadySelector,
            json_loads=json.loads,
            monotonic=lambda: 0.0,
            timeout_seconds=1,
        )

    assert exc_info.value.errno == errno.EOVERFLOW


def test_wait_for_bwrap_child_pid_uses_one_absolute_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    clock_values = iter((0.0, 0.5, 1.1))

    class _AlwaysReadySelector:
        def register(self, _fd, _events) -> None:
            return None

        def select(self, _timeout=None):
            return [(object(), 1)]

        def close(self) -> None:
            return None

    monkeypatch.setattr(api.os, "read", lambda _fd, _bound: b'{"future":true}\n')

    with pytest.raises(OSError) as exc_info:
        api._wait_for_bwrap_child_pid(
            123,
            selector_factory=_AlwaysReadySelector,
            json_loads=json.loads,
            monotonic=lambda: next(clock_values),
            timeout_seconds=1,
        )

    assert exc_info.value.errno == errno.ETIMEDOUT


def test_parse_shim_argv_requires_closed_group_and_readiness_binding() -> None:
    api = _api()

    assert api._parse_shim_argv(
        [
            "--provider-prefix",
            PROVIDER_PREFIX,
            "--credential-name",
            "TOKEN",
            "--expected-primary-group-count",
            "1",
            "--expected-overflow-group-count",
            "2",
            "--boundary-ready-fd",
            "7",
            "--",
            f"{PROVIDER_PREFIX}/bin/probe",
        ]
    ) == (
        PROVIDER_PREFIX,
        ("TOKEN",),
        1,
        2,
        7,
        None,
        (f"{PROVIDER_PREFIX}/bin/probe",),
    )


def test_parse_shim_argv_carries_one_runtime_bound_output_path() -> None:
    api = _api()
    output_path = "/workspace/product/.orchestrate/results/value.json"

    parsed = api._parse_shim_argv(
        [
            "--provider-prefix",
            PROVIDER_PREFIX,
            "--expected-primary-group-count",
            "1",
            "--expected-overflow-group-count",
            "2",
            "--boundary-ready-fd",
            "7",
            "--output-bundle",
            output_path,
            "--",
            f"{PROVIDER_PREFIX}/bin/probe",
        ]
    )

    assert parsed[-2] == output_path


@pytest.mark.parametrize(
    ("argument_name", "replacement"),
    [
        ("--expected-primary-group-count", None),
        ("--expected-overflow-group-count", None),
        ("--boundary-ready-fd", None),
        ("--expected-primary-group-count", "-1"),
        ("--expected-primary-group-count", "١"),
        ("--expected-primary-group-count", "65537"),
        ("--expected-overflow-group-count", "not-a-count"),
        ("--boundary-ready-fd", "6"),
    ],
)
def test_parse_shim_argv_rejects_missing_or_invalid_boundary_binding(
    argument_name: str,
    replacement: str | None,
) -> None:
    api = _api()
    arguments = [
        "--provider-prefix",
        PROVIDER_PREFIX,
        "--expected-primary-group-count",
        "1",
        "--expected-overflow-group-count",
        "2",
        "--boundary-ready-fd",
        "7",
    ]
    index = arguments.index(argument_name)
    if replacement is None:
        del arguments[index : index + 2]
    else:
        arguments[index + 1] = replacement
    arguments.extend(["--", f"{PROVIDER_PREFIX}/bin/probe"])

    with pytest.raises(api.CredentialFrameError):
        api._parse_shim_argv(arguments)


@pytest.mark.parametrize(
    "extra_binding",
    [
        ("--expected-primary-group-count", "1"),
        ("--expected-overflow-group-count", "2"),
        ("--boundary-ready-fd", "7"),
    ],
)
def test_parse_shim_argv_rejects_duplicate_boundary_binding(
    extra_binding: tuple[str, str],
) -> None:
    api = _api()
    arguments = [
        "--provider-prefix",
        PROVIDER_PREFIX,
        "--expected-primary-group-count",
        "1",
        "--expected-overflow-group-count",
        "2",
        "--boundary-ready-fd",
        "7",
        *extra_binding,
        "--",
        f"{PROVIDER_PREFIX}/bin/probe",
    ]

    with pytest.raises(api.CredentialFrameError):
        api._parse_shim_argv(arguments)


def test_parse_shim_argv_rejects_inconsistent_group_count_sum() -> None:
    api = _api()

    with pytest.raises(api.CredentialFrameError):
        api._parse_shim_argv(
            [
                "--provider-prefix",
                PROVIDER_PREFIX,
                "--expected-primary-group-count",
                "65536",
                "--expected-overflow-group-count",
                "1",
                "--boundary-ready-fd",
                "7",
                "--",
                f"{PROVIDER_PREFIX}/bin/probe",
            ]
        )


def test_raw_probe_launcher_uses_rootless_bwrap_and_bound_group_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    observed: dict[str, object] = {}

    monkeypatch.setattr(api.os, "getegid", lambda: 1000)
    monkeypatch.setattr(api.os, "getgroups", lambda: [1000, 4, 27])

    def inspect_spawn(
        path: str,
        argv: list[str],
        environment: dict[str, str],
        *,
        file_actions: list[tuple[int, ...]],
    ) -> int:
        observed.update(
            path=path,
            argv=argv,
            environment=environment,
            file_actions=file_actions,
        )
        raise OSError(errno.EIO, "stop after launch-plan inspection")

    monkeypatch.setattr(api.os, "posix_spawn", inspect_spawn)

    with pytest.raises(OSError, match="launch-plan inspection"):
        api.launch_provider_via_shim(
            python_executable=sys.executable,
            shim_path=Path(api.__file__),
            target_argv=("/definitely/missing",),
            declared_names=(),
            credentials={},
            _test_only_broad_host_root=True,
        )

    argv = observed["argv"]
    assert isinstance(argv, list)
    assert observed["path"] == "/usr/bin/bwrap"
    assert argv[:13] == [
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
    ]
    assert "--expected-primary-group-count" in argv
    assert argv[argv.index("--expected-primary-group-count") + 1] == "1"
    assert "--expected-overflow-group-count" in argv
    assert argv[argv.index("--expected-overflow-group-count") + 1] == "2"
    assert argv[argv.index("--boundary-ready-fd") + 1] == "7"
    assert argv[argv.index("--json-status-fd") + 1] == "8"
    actions = observed["file_actions"]
    assert isinstance(actions, list)
    mappings = [
        (action[1], action[2])
        for action in actions
        if action[0] == os.POSIX_SPAWN_DUP2
    ]
    assert {target for _source, target in mappings} == {0, 1, 2, 3, 7, 8}
    assert all(source > 8 for source, _target in mappings)


def test_raw_probe_launcher_rejects_broad_host_root_without_test_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    spawned = False

    def observe_spawn(*_args, **_kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("test-only marker rejection must precede spawn")

    monkeypatch.setattr(api.os, "posix_spawn", observe_spawn)

    with pytest.raises(api.CredentialFrameError, match="test-only"):
        api.launch_provider_via_shim(
            python_executable=sys.executable,
            shim_path=Path(api.__file__),
            target_argv=("/definitely/missing",),
            declared_names=(),
            credentials={},
        )

    assert not spawned


def test_raw_probe_launcher_rejects_privileged_controller(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    spawned = False
    monkeypatch.setattr(api.os, "geteuid", lambda: 0)

    def observe_spawn(*_args, **_kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("privileged-controller rejection must precede spawn")

    monkeypatch.setattr(api.os, "posix_spawn", observe_spawn)

    with pytest.raises(api.CredentialFrameError, match="unprivileged"):
        api.launch_provider_via_shim(
            python_executable=sys.executable,
            shim_path=Path(api.__file__),
            target_argv=("/definitely/missing",),
            declared_names=(),
            credentials={},
            _test_only_broad_host_root=True,
        )

    assert not spawned


def test_raw_probe_launcher_withholds_credentials_until_exact_readiness(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_rootless_bwrap()
    api = _api()
    fake_shim = tmp_path / "readiness-probe.py"
    fake_shim.write_text(
        """
import fcntl
import os

flags = fcntl.fcntl(3, fcntl.F_GETFL)
fcntl.fcntl(3, fcntl.F_SETFL, flags | os.O_NONBLOCK)
try:
    os.read(3, 1)
except BlockingIOError:
    pass
else:
    raise SystemExit(91)
os.write(7, b"R")
os.close(7)
fcntl.fcntl(3, fcntl.F_SETFL, flags)
if not os.read(3, 1):
    raise SystemExit(92)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    observations: list[dict[str, object]] = []
    events: list[str] = []
    validate_boundary = api._validate_pinned_rootless_child_boundary

    def observe_boundary(**values) -> None:
        events.append("observer")
        observations.append(values)

    def validate_after_observer(**values):
        events.append("validate")
        return validate_boundary(**values)

    monkeypatch.setattr(
        api,
        "_validate_pinned_rootless_child_boundary",
        validate_after_observer,
    )

    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=fake_shim,
        target_argv=("/unused",),
        declared_names=(),
        credentials={},
        _test_only_broad_host_root=True,
        _host_boundary_observer=observe_boundary,
    )

    assert result.returncode == 0, result.stderr
    assert events == ["observer", "validate"]
    assert len(observations) == 1
    assert isinstance(observations[0]["child_pid"], int)
    assert observations[0]["controller_euid"] == os.geteuid()
    assert observations[0]["controller_egid"] == os.getegid()
    assert observations[0]["controller_groups"] == tuple(os.getgroups())


def test_raw_probe_host_boundary_failure_releases_no_credentials(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_rootless_bwrap()
    api = _api()
    fake_shim = tmp_path / "boundary-failure-probe.py"
    fake_shim.write_text(
        """
import os

os.write(7, b"R")
os.close(7)
os.read(3, 1)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    credential_writes: list[bytes] = []
    real_write = api.os.write

    def observe_write(fd: int, payload) -> int:
        value = bytes(payload)
        if api.CREDENTIAL_FRAME_MAGIC in value:
            credential_writes.append(value)
        return real_write(fd, payload)

    def reject_boundary(**_values) -> None:
        raise RuntimeError("injected host-boundary mismatch")

    monkeypatch.setattr(api.os, "write", observe_write)
    monkeypatch.setattr(
        api,
        "_validate_pinned_rootless_child_boundary",
        reject_boundary,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="host-boundary mismatch"):
        api.launch_provider_via_shim(
            python_executable=sys.executable,
            shim_path=fake_shim,
            target_argv=("/unused",),
            declared_names=(),
            credentials={},
            _test_only_broad_host_root=True,
        )

    assert credential_writes == []


def test_parse_proc_starttime_handles_spaces_and_closing_parenthesis() -> None:
    api = _api()
    tail = ["S", *(str(index) for index in range(1, 30))]
    value = f"123 (worker ) name) {' '.join(tail)}\n"

    assert api._parse_proc_starttime(value, expected_pid=123) == 19


@pytest.mark.parametrize(
    "value",
    [
        "",
        "124 (worker) S 1 2 3\n",
        "123 worker S 1 2 3\n",
        "123 (worker) S 1 2 3\n",
        "123 (worker) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 nope\n",
    ],
)
def test_parse_proc_starttime_rejects_malformed_or_mismatched_stat(
    value: str,
) -> None:
    with pytest.raises(RuntimeError):
        _api()._parse_proc_starttime(value, expected_pid=123)


def _host_boundary_observations(
    *,
    overrides: dict[str, str] | None = None,
) -> dict[str, str]:
    tail = ["S", *(str(index) for index in range(1, 30))]
    observations = {
        "stat": f"123 (provider shim) {' '.join(tail)}\n",
        "uid_map": "0 1000 1\n",
        "gid_map": "0 1000 1\n",
        "setgroups": "deny\n",
        "status": (
            "Uid:\t1000\t1000\t1000\t1000\n"
            "Gid:\t1000\t1000\t1000\t1000\n"
            "Groups:\t4 27 1000\n"
        ),
    }
    observations.update(overrides or {})
    return observations


def test_validate_pinned_rootless_child_boundary_accepts_exact_binding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    observations = _host_boundary_observations()
    monkeypatch.setattr(api, "_assert_pidfd_live", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api,
        "_read_pinned_child_ascii",
        lambda _fd, name, _bound: observations[name],
    )

    result = api._validate_pinned_rootless_child_boundary(
        child_pid=123,
        pidfd=10,
        proc_dir_fd=11,
        starttime=19,
        controller_euid=1000,
        controller_egid=1000,
        controller_groups=(4, 27, 1000),
        expected_primary_count=1,
        expected_overflow_count=2,
        selector_factory=selectors.DefaultSelector,
    )

    assert result["uid_map"] == (0, 1000, 1)
    assert result["gid_map"] == (0, 1000, 1)
    assert result["controller_group_count"] == 3


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("uid_map", "0 1001 1\n"),
        ("gid_map", "0 1000 1\n1 1001 1\n"),
        ("setgroups", "allow\n"),
        (
            "status",
            "Uid:\t1000\t1000\t1000\t1000\n"
            "Gid:\t1000\t1000\t1000\t1000\n"
            "Groups:\t4 1000\n",
        ),
    ],
)
def test_validate_pinned_rootless_child_boundary_rejects_tamper(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    api = _api()
    observations = _host_boundary_observations(overrides={name: value})
    monkeypatch.setattr(api, "_assert_pidfd_live", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        api,
        "_read_pinned_child_ascii",
        lambda _fd, observed_name, _bound: observations[observed_name],
    )

    with pytest.raises(RuntimeError):
        api._validate_pinned_rootless_child_boundary(
            child_pid=123,
            pidfd=10,
            proc_dir_fd=11,
            starttime=19,
            controller_euid=1000,
            controller_egid=1000,
            controller_groups=(4, 27, 1000),
            expected_primary_count=1,
            expected_overflow_count=2,
            selector_factory=selectors.DefaultSelector,
        )


def test_validate_pinned_rootless_child_boundary_rejects_starttime_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    observations = _host_boundary_observations()
    stat_reads = 0

    def read_observation(_fd: int, name: str, _bound: int) -> str:
        nonlocal stat_reads
        if name != "stat":
            return observations[name]
        stat_reads += 1
        if stat_reads == 1:
            return observations[name]
        tail = ["S", *(str(index) for index in range(1, 30))]
        tail[19] = "20"
        return f"123 (provider shim) {' '.join(tail)}\n"

    monkeypatch.setattr(api, "_assert_pidfd_live", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(api, "_read_pinned_child_ascii", read_observation)

    with pytest.raises(RuntimeError, match="start identity changed"):
        api._validate_pinned_rootless_child_boundary(
            child_pid=123,
            pidfd=10,
            proc_dir_fd=11,
            starttime=19,
            controller_euid=1000,
            controller_egid=1000,
            controller_groups=(4, 27, 1000),
            expected_primary_count=1,
            expected_overflow_count=2,
            selector_factory=selectors.DefaultSelector,
        )


def test_shim_bootstrap_orders_both_sweeps_before_exact_exec_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    events: list[object] = []

    monkeypatch.setattr(
        api,
        "_close_fds_from_except",
        lambda start, keep_fd: events.append(("close-except", start, keep_fd)),
    )
    monkeypatch.setattr(
        api,
        "_close_fds_from",
        lambda start: events.append(("close", start)),
    )
    monkeypatch.setattr(
        api,
        "_join_fresh_session_keyring",
        lambda: events.append("fresh-keyring"),
    )
    monkeypatch.setattr(
        api,
        "_validate_rootless_group_boundary",
        lambda **counts: events.append(("group-boundary", counts)),
    )
    monkeypatch.setattr(
        api,
        "_validate_nested_userns_disabled",
        lambda: events.append("nested-userns-disabled"),
    )
    monkeypatch.setattr(
        api,
        "_signal_boundary_ready",
        lambda fd: events.append(("ready", fd)),
    )

    def read_credentials(fd: int, *, declared_names: tuple[str, ...]):
        events.append(("credentials", fd, declared_names))
        return {"TOKEN": b"secret"}

    monkeypatch.setattr(api, "read_credentials_from_fd", read_credentials)
    monkeypatch.setattr(
        api,
        "_install_key_syscall_filter",
        lambda: events.append("seccomp"),
    )

    def observe_exec(path: str, argv: tuple[str, ...], environment: dict[str, str]):
        events.append(("exec", path, argv, environment))
        raise OSError(errno.EIO, "stop before replacement")

    monkeypatch.setattr(api.os, "execve", observe_exec)
    monkeypatch.setattr(api.os, "write", lambda _fd, payload: len(payload))

    result = api.shim_main(
        [
            "--provider-prefix",
            PROVIDER_PREFIX,
            "--credential-name",
            "TOKEN",
            "--expected-primary-group-count",
            "1",
            "--expected-overflow-group-count",
            "2",
            "--boundary-ready-fd",
            "7",
            "--output-bundle",
            "/workspace/product/.orchestrate/results/value.json",
            "--",
            f"{PROVIDER_PREFIX}/bin/probe",
            "--version",
        ]
    )

    assert result == 125
    assert events == [
        ("close-except", 4, 7),
        "fresh-keyring",
        (
            "group-boundary",
            {
                "expected_primary_count": 1,
                "expected_overflow_count": 2,
            },
        ),
        "nested-userns-disabled",
        ("ready", 7),
        ("close", 4),
        ("credentials", 3, ("TOKEN",)),
        "seccomp",
        ("close", 3),
        (
            "exec",
            f"{PROVIDER_PREFIX}/bin/probe",
            (f"{PROVIDER_PREFIX}/bin/probe", "--version"),
            {
                "HOME": "/run/provider-home",
                "XDG_CONFIG_HOME": "/run/provider-home/.config",
                "XDG_CACHE_HOME": "/run/provider-home/.cache",
                "XDG_DATA_HOME": "/run/provider-home/.local/share",
                "TMPDIR": "/tmp",
                "TMP": "/tmp",
                "TEMP": "/tmp",
                "LANG": "C",
                "LC_ALL": "C",
                "TZ": "UTC",
                "ORCHESTRATOR_OUTPUT_BUNDLE": (
                    "/workspace/product/.orchestrate/results/value.json"
                ),
                "PATH": f"{PROVIDER_PREFIX}/bin",
                "TOKEN": "secret",
            },
        ),
    ]


def test_shim_sweeps_high_fds_before_rejecting_malformed_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    events: list[tuple[int, int]] = []
    monkeypatch.setattr(
        api,
        "_close_fds_from_except",
        lambda start, keep: events.append((start, keep)),
    )
    monkeypatch.setattr(api.os, "write", lambda _fd, payload: len(payload))

    assert api.shim_main(["--invalid"]) == 125
    assert events == [(4, api.BOUNDARY_READY_FD)]


def test_failure_after_secret_read_has_redacted_stderr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    observed_stderr: list[bytes] = []
    monkeypatch.setattr(api, "_close_fds_from_except", lambda _start, _keep: None)
    monkeypatch.setattr(api, "_close_fds_from", lambda _start: None)
    monkeypatch.setattr(api, "_join_fresh_session_keyring", lambda: None)
    monkeypatch.setattr(
        api,
        "_validate_rootless_group_boundary",
        lambda **_counts: None,
    )
    monkeypatch.setattr(api, "_validate_nested_userns_disabled", lambda: None)
    monkeypatch.setattr(api, "_signal_boundary_ready", lambda _fd: None)
    monkeypatch.setattr(
        api,
        "read_credentials_from_fd",
        lambda _fd, *, declared_names: {"TOKEN": b"never-print-this"},
    )
    monkeypatch.setattr(
        api,
        "_install_key_syscall_filter",
        lambda: (_ for _ in ()).throw(OSError(errno.EPERM, "injected")),
    )
    monkeypatch.setattr(
        api.os,
        "write",
        lambda fd, payload: observed_stderr.append(payload) or len(payload),
    )

    assert api.shim_main(
        [
            "--provider-prefix",
            PROVIDER_PREFIX,
            "--credential-name",
            "TOKEN",
            "--expected-primary-group-count",
            "1",
            "--expected-overflow-group-count",
            "2",
            "--boundary-ready-fd",
            "7",
            "--",
            f"{PROVIDER_PREFIX}/bin/probe",
        ]
    ) == 125

    assert observed_stderr == [b"provider_launch_shim_failed\n"]
    assert b"never-print-this" not in b"".join(observed_stderr)


def test_shim_closes_every_fd_at_or_above_four_itself(tmp_path: Path) -> None:
    _require_rootless_bwrap()
    api = _api()
    probe = tmp_path / "close-probe.py"
    probe.write_text(
        """
import json
import os
fds = []
for fd in range(3, 128):
    try:
        os.fstat(fd)
    except OSError:
        continue
    fds.append(fd)
print(json.dumps(fds))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=Path(api.__file__),
        target_argv=(sys.executable, "-I", "-S", str(probe)),
        declared_names=(),
        credentials={},
        extra_setup_fds=3,
        _test_only_broad_host_root=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == []


def test_shim_builds_only_fixed_environment_and_declared_credentials(
    tmp_path: Path,
) -> None:
    _require_rootless_bwrap()
    api = _api()
    probe = tmp_path / "env-probe.py"
    probe.write_text(
        "import json, os\n"
        "print(json.dumps(dict(sorted(os.environ.items()))))\n",
        encoding="utf-8",
    )
    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=Path(api.__file__),
        target_argv=(sys.executable, "-I", "-S", str(probe)),
        declared_names=("TOKEN",),
        credentials={"TOKEN": b"secret-value"},
        provider_prefix=PROVIDER_PREFIX,
        _test_only_broad_host_root=True,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert observed == {
        "HOME": "/run/provider-home",
        "XDG_CONFIG_HOME": "/run/provider-home/.config",
        "XDG_CACHE_HOME": "/run/provider-home/.cache",
        "XDG_DATA_HOME": "/run/provider-home/.local/share",
        "TMPDIR": "/tmp",
        "TMP": "/tmp",
        "TEMP": "/tmp",
        "LANG": "C",
        "LC_ALL": "C",
        "TZ": "UTC",
        "PATH": f"{PROVIDER_PREFIX}/bin",
        "TOKEN": "secret-value",
    }


def test_launcher_rejects_nonempty_bootstrap_environment_before_spawn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    spawned = False

    def observe_spawn(*_args, **_kwargs):
        nonlocal spawned
        spawned = True
        raise AssertionError("bootstrap rejection must precede spawn")

    monkeypatch.setattr(api.os, "posix_spawn", observe_spawn)

    with pytest.raises(api.CredentialFrameError):
        api.launch_provider_via_shim(
            python_executable=sys.executable,
            shim_path=Path(api.__file__),
            target_argv=("/definitely/missing",),
            declared_names=(),
            credentials={},
            bootstrap_environment={"PYTHONPATH": "/candidate"},
            _test_only_broad_host_root=True,
        )

    assert not spawned


def test_launcher_setup_failure_closes_allocated_fds_and_zeroes_frame(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _api()
    allocated: list[int] = []
    zeroed: list[bytes] = []
    real_pipe = api.os.pipe
    real_zero = api._zero
    pipe_calls = 0

    def fail_second_pipe() -> tuple[int, int]:
        nonlocal pipe_calls
        pipe_calls += 1
        if pipe_calls == 2:
            raise OSError(errno.EMFILE, "injected setup failure")
        pair = real_pipe()
        allocated.extend(pair)
        return pair

    def observe_zero(value: bytearray) -> None:
        real_zero(value)
        zeroed.append(bytes(value))

    monkeypatch.setattr(api.os, "pipe", fail_second_pipe)
    monkeypatch.setattr(api, "_zero", observe_zero)

    try:
        with pytest.raises(OSError) as exc_info:
            api.launch_provider_via_shim(
                python_executable=sys.executable,
                shim_path=Path(api.__file__),
                target_argv=("/definitely/missing",),
                declared_names=("TOKEN",),
                credentials={"TOKEN": b"setup-secret"},
                _test_only_broad_host_root=True,
            )
        assert exc_info.value.errno == errno.EMFILE
        assert zeroed
        assert all(value == bytes(len(value)) for value in zeroed)
        for fd in allocated:
            with pytest.raises(OSError) as fd_error:
                os.fstat(fd)
            assert fd_error.value.errno == errno.EBADF
    finally:
        for fd in allocated:
            try:
                os.close(fd)
            except OSError:
                pass


def test_launcher_spawn_sources_do_not_collide_when_fixed_fds_start_closed() -> None:
    api = _api()
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        report_fd = fcntl.fcntl(write_fd, fcntl.F_DUPFD, 200)
        os.close(write_fd)
        for fd in range(9):
            try:
                os.close(fd)
            except OSError:
                pass

        def inspect_spawn(
            _path: str,
            _argv: list[str],
            _environment: dict[str, str],
            *,
            file_actions: list[tuple[int, ...]],
        ) -> int:
            mappings = [
                (action[1], action[2])
                for action in file_actions
                if action[0] == os.POSIX_SPAWN_DUP2
            ]
            os.write(
                report_fd,
                json.dumps(
                    {
                        "mappings": mappings,
                        "collision_free": bool(mappings)
                        and all(source > 8 for source, _target in mappings)
                        and {
                            target for _source, target in mappings
                        }
                        == {0, 1, 2, 3, 7, 8},
                    }
                ).encode("utf-8"),
            )
            raise OSError(errno.EIO, "stop after action audit")

        api.os.posix_spawn = inspect_spawn
        try:
            api.launch_provider_via_shim(
                python_executable=sys.executable,
                shim_path=Path(api.__file__),
                target_argv=("/definitely/missing",),
                declared_names=(),
                credentials={},
                _test_only_broad_host_root=True,
            )
        except OSError:
            os._exit(0)
        os._exit(127)

    os.close(write_fd)
    payload = os.read(read_fd, 65_536)
    os.close(read_fd)
    _waited_pid, status = os.waitpid(pid, 0)

    assert os.waitstatus_to_exitcode(status) == 0
    observed = json.loads(payload)
    assert observed["collision_free"] is True


def test_launcher_closes_selector_when_registration_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_rootless_bwrap()
    api = _api()
    selector_fds: list[int] = []
    created: list[selectors.BaseSelector] = []
    real_selector = selectors.DefaultSelector

    class _FailingSelector:
        def __init__(self) -> None:
            self.inner = real_selector()
            created.append(self.inner)
            selector_fds.append(self.inner.fileno())
            self.registrations = 0

        def register(self, fileobj, events, data=None):
            self.registrations += 1
            if self.registrations == 2:
                raise OSError(errno.EIO, "injected selector registration failure")
            return self.inner.register(fileobj, events, data)

        def unregister(self, fileobj):
            return self.inner.unregister(fileobj)

        def select(self, timeout=None):
            return self.inner.select(timeout)

        def get_map(self):
            return self.inner.get_map()

        def close(self) -> None:
            self.inner.close()

    monkeypatch.setattr(selectors, "DefaultSelector", _FailingSelector)

    try:
        with pytest.raises(OSError) as exc_info:
            api.launch_provider_via_shim(
                python_executable=sys.executable,
                shim_path=Path(api.__file__),
                target_argv=("/definitely/missing",),
                declared_names=(),
                credentials={},
                _test_only_broad_host_root=True,
            )
        assert exc_info.value.errno == errno.EIO
        assert selector_fds
        for fd in selector_fds:
            with pytest.raises(OSError) as fd_error:
                os.fstat(fd)
            assert fd_error.value.errno == errno.EBADF
    finally:
        for selector in created:
            selector.close()


def test_launcher_uses_spawn_fd_actions_without_subprocess_preexec(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _require_rootless_bwrap()
    api = _api()

    def reject_popen(*_args, **_kwargs):
        raise AssertionError("subprocess preexec launch path is forbidden")

    monkeypatch.setattr(subprocess, "Popen", reject_popen)

    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=Path(api.__file__),
        target_argv=("/definitely/missing",),
        declared_names=(),
        credentials={},
        _test_only_broad_host_root=True,
    )

    assert result.returncode == 125
    assert result.stderr == "provider_launch_shim_failed\n"


def test_shim_reports_normalized_groups_key_denial_and_no_bootstrap_fd(
    tmp_path: Path,
) -> None:
    _require_rootless_bwrap()
    api = _api()
    controller_groups = tuple(os.getgroups())
    controller_primary_gid = os.getegid()
    expected_primary_count = controller_groups.count(controller_primary_gid)
    expected_overflow_count = len(controller_groups) - expected_primary_count
    overflow_gid = int(
        Path("/proc/sys/kernel/overflowgid").read_text(encoding="ascii").strip()
    )
    probe = tmp_path / "security-probe.py"
    probe.write_text(
        """
import ctypes
import errno
import json
import os

fds = []
for fd in range(3, 128):
    try:
        os.fstat(fd)
    except OSError:
        continue
    fds.append(fd)
libc = ctypes.CDLL(None, use_errno=True)
result = libc.syscall(250, 0, 0, 0, 0, 0)
error = ctypes.get_errno()
print(json.dumps({
    "groups": os.getgroups(),
    "fds": fds,
    "keyctl_result": result,
    "keyctl_errno": error,
    "expected_errno": errno.EPERM,
}))
""".strip()
        + "\n",
        encoding="utf-8",
    )
    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=Path(api.__file__),
        target_argv=(sys.executable, "-I", "-S", str(probe)),
        declared_names=(),
        credentials={},
        _test_only_broad_host_root=True,
    )
    assert result.returncode == 0, result.stderr
    observed = json.loads(result.stdout)
    assert set(observed["groups"]) <= {0, overflow_gid}
    assert observed["groups"].count(0) == expected_primary_count
    assert observed["groups"].count(overflow_gid) == expected_overflow_count
    assert observed["fds"] == []
    assert observed["keyctl_result"] == -1
    assert observed["keyctl_errno"] == observed["expected_errno"]


def test_secret_is_absent_from_argv_stderr_and_artifacts(tmp_path: Path) -> None:
    _require_rootless_bwrap()
    api = _api()
    secret = b"task1a-super-secret"
    artifact = tmp_path / "artifact"
    probe = tmp_path / "secret-probe.py"
    probe.write_text(
        "import json, os, sys\n"
        "print(json.dumps({'argv': sys.argv, 'token': os.environ['TOKEN']}))\n",
        encoding="utf-8",
    )
    result = api.launch_provider_via_shim(
        python_executable=sys.executable,
        shim_path=Path(api.__file__),
        target_argv=(sys.executable, "-I", "-S", str(probe)),
        declared_names=("TOKEN",),
        credentials={"TOKEN": secret},
        artifact_paths=(artifact,),
        _test_only_broad_host_root=True,
    )
    assert result.returncode == 0
    observed = json.loads(result.stdout)
    assert observed["token"] == secret.decode()
    assert secret.decode() not in json.dumps(observed["argv"])
    assert secret.decode() not in result.stderr
    assert not artifact.exists()


def _rootfs(tmp_path: Path) -> Path:
    root = tmp_path / "rootfs"
    (root / PROVIDER_PREFIX.lstrip("/") / "bin").mkdir(parents=True)
    (root / "usr" / "bin").mkdir(parents=True)
    (root / "lib64").mkdir()
    root.chmod(0o755)
    _write_minimal_elf64(root / CONVENTIONAL_LOADER.lstrip("/"))
    return root


def _write_minimal_elf64(
    path: Path,
    *,
    interpreter: str | None = None,
    needed: tuple[str, ...] = (),
    rpath: tuple[str, ...] = (),
    runpath: tuple[str, ...] = (),
    elf_class: int = 2,
    data_encoding: int = 1,
    ident_version: int = 1,
    elf_type: int = 3,
    machine: int = 62,
    header_version: int = 1,
) -> None:
    """Write a non-runnable ELF64 fixture with a real dynamic string table."""

    strings = bytearray(b"\0")

    def add_string(value: str) -> int:
        offset = len(strings)
        strings.extend(value.encode("utf-8"))
        strings.append(0)
        return offset

    needed_offsets = tuple(add_string(value) for value in needed)
    rpath_offset = add_string(":".join(rpath)) if rpath else None
    runpath_offset = add_string(":".join(runpath)) if runpath else None

    dynamic_rows: list[tuple[int, int]] = []
    if needed or rpath or runpath:
        dynamic_rows.extend((1, offset) for offset in needed_offsets)  # DT_NEEDED
        if rpath_offset is not None:
            dynamic_rows.append((15, rpath_offset))  # DT_RPATH
        if runpath_offset is not None:
            dynamic_rows.append((29, runpath_offset))  # DT_RUNPATH

    has_dynamic = bool(dynamic_rows)
    program_header_count = 1 + int(interpreter is not None) + int(has_dynamic)
    elf_header_size = 64
    program_header_size = 56
    cursor = elf_header_size + program_header_count * program_header_size

    interpreter_bytes = (
        interpreter.encode("utf-8") + b"\0" if interpreter is not None else b""
    )
    interpreter_offset = cursor if interpreter_bytes else None
    cursor += len(interpreter_bytes)
    cursor = (cursor + 7) & ~7
    string_table_offset = cursor if has_dynamic else None
    if has_dynamic:
        cursor += len(strings)
        cursor = (cursor + 7) & ~7
    dynamic_offset = cursor if has_dynamic else None
    if has_dynamic:
        dynamic_rows = [
            (5, string_table_offset),
            (10, len(strings)),
            *dynamic_rows,
            (0, 0),
        ]
        cursor += len(dynamic_rows) * 16

    image = bytearray(cursor)
    ident = (
        b"\x7fELF"
        + bytes((elf_class, data_encoding, ident_version, 0))
        + b"\0" * 8
    )
    struct.pack_into(
        "<16sHHIQQQIHHHHHH",
        image,
        0,
        ident,
        elf_type,
        machine,
        header_version,
        0,
        elf_header_size,
        0,
        0,
        elf_header_size,
        program_header_size,
        program_header_count,
        0,
        0,
        0,
    )
    program_headers: list[tuple[int, int, int, int, int, int, int, int]] = [
        (1, 5, 0, 0, 0, len(image), len(image), 0x1000),  # PT_LOAD
    ]
    if interpreter_offset is not None:
        program_headers.append(
            (
                3,  # PT_INTERP
                4,
                interpreter_offset,
                interpreter_offset,
                interpreter_offset,
                len(interpreter_bytes),
                len(interpreter_bytes),
                1,
            )
        )
    if dynamic_offset is not None:
        program_headers.append(
            (
                2,  # PT_DYNAMIC
                4,
                dynamic_offset,
                dynamic_offset,
                dynamic_offset,
                len(dynamic_rows) * 16,
                len(dynamic_rows) * 16,
                8,
            )
        )
    for index, row in enumerate(program_headers):
        struct.pack_into(
            "<IIQQQQQQ",
            image,
            elf_header_size + index * program_header_size,
            *row,
        )
    if interpreter_offset is not None:
        image[
            interpreter_offset : interpreter_offset + len(interpreter_bytes)
        ] = interpreter_bytes
    if string_table_offset is not None:
        image[
            string_table_offset : string_table_offset + len(strings)
        ] = strings
    if dynamic_offset is not None:
        for index, row in enumerate(dynamic_rows):
            struct.pack_into("<qQ", image, dynamic_offset + index * 16, *row)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    path.chmod(0o555)


def _write_dynamic_executable(
    path: Path,
    *,
    needed: tuple[str, ...],
    rpath: tuple[str, ...] = (),
    runpath: tuple[str, ...] = (),
    elf_type: int = 3,
) -> None:
    _write_minimal_elf64(
        path,
        interpreter=CONVENTIONAL_LOADER,
        needed=needed,
        rpath=rpath,
        runpath=runpath,
        elf_type=elf_type,
    )


BOOTSTRAP_PURE_MODULES = (
    "encodings/__init__.py",
    "encodings/aliases.py",
    "encodings/utf_8.py",
    "ctypes/__init__.py",
    "ctypes/_endian.py",
    "types.py",
    "struct.py",
    "os.py",
)


def _fixed_bootstrap_rootfs(
    tmp_path: Path,
    *,
    shim_materialization: str = "virtual_injected",
) -> tuple[Path, object, int]:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "python",
        needed=("libpython3.12.so.1.0",),
        runpath=(f"{PROVIDER_PREFIX}/lib",),
    )
    _write_minimal_elf64(prefix / "lib" / "libpython3.12.so.1.0")
    stdlib = prefix / "lib" / "python3.12"
    for relative in BOOTSTRAP_PURE_MODULES:
        path = stdlib / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"# {relative}\n", encoding="utf-8")
    (stdlib / "bootstrap_projection_extra.py").write_text(
        "# projection-only member\n",
        encoding="utf-8",
    )
    extension = (
        stdlib
        / "lib-dynload"
        / "_ctypes.cpython-312-x86_64-linux-gnu.so"
    )
    _write_minimal_elf64(
        extension,
        needed=("libffi.so.8",),
        runpath=(f"{PROVIDER_PREFIX}/lib",),
    )
    _write_minimal_elf64(prefix / "lib" / "libffi.so.8")

    if shim_materialization == "present":
        shim = (
            prefix
            / "libexec"
            / "provider-launch-shim-v1.py"
        )
        shim.parent.mkdir(parents=True, exist_ok=True)
        shim.write_bytes(Path(_api().__file__).read_bytes())

    for path in (root, *root.rglob("*")):
        if path.is_symlink():
            continue
        mode = stat.S_IMODE(path.stat().st_mode)
        path.chmod(mode & ~0o022)

    root_fd = os.open(
        root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    if shim_materialization == "virtual_injected":
        manifest = api._build_provider_environment_manifest_from_fd(
            root_fd,
            PROVIDER_PREFIX,
            inject_launch_shim=True,
            finalized_snapshot=False,
        )
    else:
        manifest = api._build_provider_environment_manifest_from_fd(
            root_fd,
            PROVIDER_PREFIX,
            inject_launch_shim=False,
            finalized_snapshot=False,
        )
    return root, manifest, root_fd


@pytest.mark.parametrize(
    "shim_materialization",
    ["virtual_injected", "present"],
)
def test_fixed_bootstrap_closure_is_canonical_and_manifest_backed(
    tmp_path: Path,
    shim_materialization: str,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(
        tmp_path,
        shim_materialization=shim_materialization,
    )
    try:
        closure = api.validate_fixed_provider_bootstrap_from_fd(
            root_fd,
            manifest,
            PROVIDER_PREFIX,
            shim_materialization=shim_materialization,
        )
        os.fstat(root_fd)
    finally:
        os.close(root_fd)

    assert closure.schema_version == "provider_bootstrap_closure.v1"
    assert closure.environment_digest == manifest.digest
    assert closure.provider_prefix == PROVIDER_PREFIX
    assert closure.python_path == f"{PROVIDER_PREFIX}/bin/python"
    assert closure.python_flags == ("-I", "-S")
    assert closure.profile == "cpython312_isolated_no_site.v1"
    assert closure.prospective_sys_path == (
        f"{PROVIDER_PREFIX}/lib/python312.zip",
        f"{PROVIDER_PREFIX}/lib/python3.12",
        f"{PROVIDER_PREFIX}/lib/python3.12/lib-dynload",
    )
    assert closure.allowed_import_roots == (
        f"{PROVIDER_PREFIX}/lib/python3.12",
        f"{PROVIDER_PREFIX}/lib/python3.12/lib-dynload",
    )
    assert closure.required_pure_module_paths == tuple(
        f"{PROVIDER_PREFIX}/lib/python3.12/{relative}"
        for relative in BOOTSTRAP_PURE_MODULES
    )
    assert closure.ctypes_extension_path.endswith(
        "/_ctypes.cpython-312-x86_64-linux-gnu.so"
    )
    assert closure.ctypes_libffi_path == f"{PROVIDER_PREFIX}/lib/libffi.so.8"
    assert closure.shim_materialization == shim_materialization
    assert closure.shim_mode == 0o444
    assert closure.shim_imports == (
        "module:from:__future__:annotations",
        "module:import:ctypes",
        "module:import:errno",
        "module:import:os",
        "module:import:struct",
        "module:import:sys",
        "function:launch_provider_via_shim:import:json",
        "function:launch_provider_via_shim:import:selectors",
        "function:launch_provider_via_shim:import:subprocess",
        "function:launch_provider_via_shim:import:time",
    )
    assert closure.canonical_json == api.canonical_isolation_json_bytes(
        closure.to_dict()
    )
    assert closure.digest == (
        f"sha256:{sha256(closure.canonical_json).hexdigest()}"
    )


def test_fixed_bootstrap_closure_uses_only_the_borrowed_root_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    before = api.validate_fixed_provider_bootstrap_from_fd(
        root_fd,
        manifest,
        PROVIDER_PREFIX,
    )
    renamed = root.with_name("renamed-after-open")
    root.rename(renamed)

    def reject_path_reopen(*_args, **_kwargs):
        raise AssertionError("bootstrap validation reopened a root pathname")

    monkeypatch.setattr(api, "_open_source_binding", reject_path_reopen)
    try:
        after = api.validate_fixed_provider_bootstrap_from_fd(
            root_fd,
            manifest,
            PROVIDER_PREFIX,
        )
        os.fstat(root_fd)
    finally:
        os.close(root_fd)
    assert after.canonical_json == before.canonical_json
    assert after.digest == before.digest


def test_fixed_bootstrap_closure_is_immune_to_caller_fd_close_and_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    decoy = tmp_path / "decoy-root"
    decoy.mkdir(mode=0o700)
    real_validate_imports = api._validate_bootstrap_shim_imports
    replacement_fd = -1

    def close_and_reuse_caller_fd(source: bytes) -> tuple[str, ...]:
        nonlocal replacement_fd
        imports = real_validate_imports(source)
        os.close(root_fd)
        replacement_fd = os.open(
            decoy,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        assert replacement_fd == root_fd
        return imports

    monkeypatch.setattr(
        api,
        "_validate_bootstrap_shim_imports",
        close_and_reuse_caller_fd,
    )
    try:
        closure = api.validate_fixed_provider_bootstrap_from_fd(
            root_fd,
            manifest,
            PROVIDER_PREFIX,
        )
    finally:
        if replacement_fd >= 0:
            os.close(replacement_fd)
    assert closure.environment_digest == manifest.digest


@pytest.mark.parametrize(
    "manifest_mutator",
    [
        lambda manifest: object(),
        lambda manifest: replace(
            manifest,
            digest="sha256:" + "0" * 64,
        ),
        lambda manifest: replace(
            manifest,
            provider_prefix="/opt/other-provider",
        ),
    ],
)
def test_fixed_bootstrap_closure_rejects_bad_manifest_or_digest(
    tmp_path: Path,
    manifest_mutator,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest_mutator(manifest),
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_prefix_mismatch(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                "/opt/other-provider",
            )
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    "relative_path",
    [
        "bin/python",
        "lib/python3.12/encodings/aliases.py",
        (
            "lib/python3.12/lib-dynload/"
            "_ctypes.cpython-312-x86_64-linux-gnu.so"
        ),
        "lib/libffi.so.8",
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_fixed_bootstrap_closure_rejects_missing_or_tampered_runtime_member(
    tmp_path: Path,
    relative_path: str,
    mutation: str,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    target = root / PROVIDER_PREFIX.lstrip("/") / relative_path
    target.unlink()
    if mutation == "tampered":
        target.write_bytes(b"tampered bootstrap member")
        target.chmod(0o555)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_tampered_projection_only_module(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    (
        root
        / PROVIDER_PREFIX.lstrip("/")
        / "lib"
        / "python3.12"
        / "bootstrap_projection_extra.py"
    ).write_text("# changed outside the required subset\n", encoding="utf-8")
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_tampered_present_shim(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(
        tmp_path,
        shim_materialization="present",
    )
    shim = (
        root
        / PROVIDER_PREFIX.lstrip("/")
        / "libexec"
        / "provider-launch-shim-v1.py"
    )
    shim.write_bytes(shim.read_bytes() + b"\n# tampered\n")
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
                shim_materialization="present",
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_missing_present_shim(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(
        tmp_path,
        shim_materialization="present",
    )
    (
        root
        / PROVIDER_PREFIX.lstrip("/")
        / "libexec"
        / "provider-launch-shim-v1.py"
    ).unlink()
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
                shim_materialization="present",
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_virtual_shim_manifest_tamper(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    document = manifest.to_dict()
    shim_path = (
        f"{PROVIDER_PREFIX.lstrip('/')}/"
        "libexec/provider-launch-shim-v1.py"
    )
    shim_row = next(
        row for row in document["entries"] if row["path"] == shim_path
    )
    shim_row["digest"] = "sha256:" + "0" * 64
    tampered_manifest = api.load_provider_environment_manifest(document)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                tampered_manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    "source_mutator",
    [
        lambda source: source.replace(
            "import sys\n",
            "import sys\nimport pathlib\n",
            1,
        ),
        lambda source: source
        + "\ndef misplaced_bootstrap_import():\n    import selectors\n",
        lambda source: source + "\n_dynamic_import = __import__('pathlib')\n",
        lambda source: source
        + "\n_dynamic_import = eval(\"__import__('pathlib')\")\n",
        lambda source: source
        + "\n_dynamic_loader = __import__\n"
        + "_dynamic_import = _dynamic_loader('pathlib')\n",
        lambda source: source
        + "\n_dynamic_import = "
        + "getattr(__builtins__, '__import__')('pathlib')\n",
        lambda source: source
        + "\n_dynamic_loader = getattr("
        + "__builtins__, '_' * 2 + 'import' + '_' * 2)\n"
        + "_dynamic_import = _dynamic_loader('pathlib')\n",
    ],
)
def test_fixed_bootstrap_closure_rejects_extra_misplaced_or_dynamic_shim_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_mutator,
) -> None:
    api = _environment_api()
    changed = source_mutator(Path(_api().__file__).read_text(encoding="utf-8"))
    monkeypatch.setattr(
        api,
        "_packaged_launch_shim_bytes",
        lambda: changed.encode("utf-8"),
        raising=False,
    )
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    "import_name",
    ["json", "selectors", "subprocess", "time"],
)
def test_fixed_bootstrap_closure_requires_all_reviewed_local_shim_imports(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    import_name: str,
) -> None:
    api = _environment_api()
    tree = ast.parse(Path(_api().__file__).read_text(encoding="utf-8"))
    removed = 0

    class RemoveReviewedLocalImport(ast.NodeTransformer):
        inside_launch_helper = False

        def visit_FunctionDef(self, node: ast.FunctionDef):
            prior = self.inside_launch_helper
            self.inside_launch_helper = (
                prior or node.name == "launch_provider_via_shim"
            )
            updated = self.generic_visit(node)
            self.inside_launch_helper = prior
            return updated

        def visit_Import(self, node: ast.Import):
            nonlocal removed
            if (
                self.inside_launch_helper
                and len(node.names) == 1
                and node.names[0].name == import_name
            ):
                removed += 1
                return None
            return node

    changed_tree = RemoveReviewedLocalImport().visit(tree)
    ast.fix_missing_locations(changed_tree)
    assert removed == 1
    changed = (ast.unparse(changed_tree) + "\n").encode("utf-8")
    monkeypatch.setattr(
        api,
        "_packaged_launch_shim_bytes",
        lambda: changed,
    )
    monkeypatch.setattr(
        api,
        "_REVIEWED_BOOTSTRAP_SHIM_DIGEST",
        f"sha256:{sha256(changed).hexdigest()}",
    )
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_unreviewed_shim_semantic_ast(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    source = Path(_api().__file__).read_text(encoding="utf-8")
    changed = source.replace(
        "MAX_CREDENTIAL_NAMES = 32",
        "MAX_CREDENTIAL_NAMES = 33",
        1,
    )
    assert changed != source
    monkeypatch.setattr(
        api,
        "_packaged_launch_shim_bytes",
        lambda: changed.encode("utf-8"),
    )
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


@pytest.mark.parametrize(
    "relative_path",
    [
        "pyvenv.cfg",
        "bin/pyvenv.cfg",
        "bin/python._pth",
        "bin/python3._pth",
        "bin/python312._pth",
        "bin/python3.12._pth",
        "lib/python312.zip",
        "lib/python3.12/sitecustomize.py",
        "lib/python3.12/usercustomize.py",
    ],
)
def test_fixed_bootstrap_closure_rejects_startup_configuration_presence(
    tmp_path: Path,
    relative_path: str,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    config = root / PROVIDER_PREFIX.lstrip("/") / relative_path
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_bytes(b"forbidden startup configuration")
    config.chmod(0o444)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_system_sitecustomize_presence(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    config = root / "etc" / "python3.12" / "sitecustomize.py"
    config.parent.mkdir(parents=True)
    config.write_bytes(b"forbidden startup configuration")
    config.chmod(0o444)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_duplicate_ctypes_extension(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, _manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    duplicate = (
        root
        / PROVIDER_PREFIX.lstrip("/")
        / "lib"
        / "python3.12"
        / "lib-dynload"
        / "_ctypes.cpython-312-second.so"
    )
    _write_minimal_elf64(
        duplicate,
        needed=("libffi.so.8",),
        runpath=(f"{PROVIDER_PREFIX}/lib",),
    )
    os.close(root_fd)
    root_fd = os.open(
        root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    manifest = api._build_provider_environment_manifest_from_fd(
        root_fd,
        PROVIDER_PREFIX,
        inject_launch_shim=True,
        finalized_snapshot=False,
    )
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_rejects_manifest_without_ctypes_extension(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root, _manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    extension = (
        root
        / PROVIDER_PREFIX.lstrip("/")
        / "lib"
        / "python3.12"
        / "lib-dynload"
        / "_ctypes.cpython-312-x86_64-linux-gnu.so"
    )
    extension.unlink()
    os.close(root_fd)
    root_fd = os.open(
        root,
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
    )
    manifest = api._build_provider_environment_manifest_from_fd(
        root_fd,
        PROVIDER_PREFIX,
        inject_launch_shim=True,
        finalized_snapshot=False,
    )
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_revalidates_mutated_runtime_member(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    python = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "python"
    real_hash = api._hash_regular_file
    exchanged = False

    def exchange_python_after_hash(fd: int) -> tuple[int, str]:
        nonlocal exchanged
        result = real_hash(fd)
        if not exchanged and os.path.samestat(os.fstat(fd), python.stat()):
            replacement = python.with_name("python.replacement")
            replacement.write_bytes(python.read_bytes())
            replacement.chmod(0o555)
            replacement.replace(python)
            exchanged = True
        return result

    monkeypatch.setattr(api, "_hash_regular_file", exchange_python_after_hash)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
    finally:
        os.close(root_fd)
    assert exchanged


@pytest.mark.parametrize("fail", [False, True])
def test_fixed_bootstrap_closure_closes_every_duplicated_descriptor(
    tmp_path: Path,
    fail: bool,
) -> None:
    api = _environment_api()
    root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    if fail:
        (
            root
            / PROVIDER_PREFIX.lstrip("/")
            / "lib"
            / "python3.12"
            / "types.py"
        ).unlink()
    before = set(os.listdir("/proc/self/fd"))
    try:
        if fail:
            with pytest.raises(api.ProviderIsolationEnvironmentError):
                api.validate_fixed_provider_bootstrap_from_fd(
                    root_fd,
                    manifest,
                    PROVIDER_PREFIX,
                )
        else:
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
        after = set(os.listdir("/proc/self/fd"))
        assert after == before
        os.fstat(root_fd)
    finally:
        os.close(root_fd)


def test_fixed_bootstrap_closure_closes_dup_when_cloexec_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    _root, manifest, root_fd = _fixed_bootstrap_rootfs(tmp_path)
    before = set(os.listdir("/proc/self/fd"))

    def fail_cloexec(_fd: int, _inheritable: bool) -> None:
        raise OSError("set_inheritable failed")

    monkeypatch.setattr(api.os, "set_inheritable", fail_cloexec)
    try:
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.validate_fixed_provider_bootstrap_from_fd(
                root_fd,
                manifest,
                PROVIDER_PREFIX,
            )
        assert set(os.listdir("/proc/self/fd")) == before
    finally:
        os.close(root_fd)


def _copy_reviewed_x86_64_system_python_runtime(root: Path) -> None:
    missing = [
        raw_path
        for raw_path in REVIEWED_X86_64_SYSTEM_PYTHON_RUNTIME
        if not Path(raw_path).exists()
    ]
    if missing:
        pytest.skip(
            "reviewed x86_64 system Python runtime fixture is unavailable: "
            + ", ".join(missing)
        )
    for raw_path in REVIEWED_X86_64_SYSTEM_PYTHON_RUNTIME:
        source = Path(raw_path)
        destination = root / source.as_posix().lstrip("/")
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            destination.unlink()
        shutil.copy2(source, destination)


def _write_glibc_new_cache(
    root: Path,
    entries: tuple[tuple[str, str, int, int], ...],
    *,
    magic: bytes = GLIBC_CACHE_MAGIC,
    version: bytes = GLIBC_CACHE_VERSION,
    endian_flag: int = 2,
) -> Path:
    header_size = 48
    entry_size = 24
    strings = bytearray()
    encoded_entries: list[tuple[int, int, int, int]] = []
    strings_start = header_size + entry_size * len(entries)
    for key, value, flags, hwcap in entries:
        key_offset = strings_start + len(strings)
        strings.extend(key.encode("utf-8") + b"\0")
        value_offset = strings_start + len(strings)
        strings.extend(value.encode("utf-8") + b"\0")
        encoded_entries.append((flags, key_offset, value_offset, hwcap))
    image = bytearray(
        struct.pack(
            "<17s3sIIB3xI3I",
            magic,
            version,
            len(entries),
            len(strings),
            endian_flag,
            0,
            0,
            0,
            0,
        )
    )
    for flags, key_offset, value_offset, hwcap in encoded_entries:
        image.extend(
            struct.pack(
                "<iIIIQ",
                flags,
                key_offset,
                value_offset,
                0,
                hwcap,
            )
        )
    image.extend(strings)
    path = root / GLIBC_CACHE_PATH.lstrip("/")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(image)
    path.chmod(0o444)
    return path


def test_closure_discovery_resolves_path_only_at_declared_prefix(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    shutil.copy2("/usr/bin/busybox", executable)
    closure = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )
    assert closure.entrypoint == f"{PROVIDER_PREFIX}/bin/probe"
    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe"
    }
    assert closure.entries[0].size == executable.stat().st_size
    assert closure.entries[0].digest == (
        f"sha256:{sha256(executable.read_bytes()).hexdigest()}"
    )

    ambient = tmp_path / "probe"
    ambient.write_bytes(b"ambient")
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, str(ambient), provider_prefix=PROVIDER_PREFIX
        )


def test_closure_discovery_never_searches_ambient_path(
    tmp_path: Path, monkeypatch
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    ambient_bin = tmp_path / "ambient-bin"
    ambient_bin.mkdir()
    shutil.copy2("/usr/bin/busybox", ambient_bin / "probe")
    monkeypatch.setenv("PATH", str(ambient_bin))

    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )


def test_closure_discovery_parses_without_executing_target(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    marker = tmp_path / "executed"
    script = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    script.write_text(
        f"#!/usr/bin/env busybox\n/bin/touch {marker}\n",
        encoding="utf-8",
    )
    script.chmod(0o555)
    shutil.copy2("/usr/bin/busybox", root / "usr" / "bin" / "env")
    shutil.copy2(
        "/usr/bin/busybox",
        root / PROVIDER_PREFIX.lstrip("/") / "bin" / "busybox",
    )
    closure = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )
    assert not marker.exists()
    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe",
        "/usr/bin/env",
        f"{PROVIDER_PREFIX}/bin/busybox",
    }


def test_closure_env_requires_both_sealed_env_and_prefix_target(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    script = prefix / "bin" / "probe"
    script.write_text("#!/usr/bin/env busybox\n", encoding="utf-8")
    script.chmod(0o555)
    shutil.copy2("/usr/bin/busybox", prefix / "bin" / "busybox")
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )

    shutil.copy2("/usr/bin/busybox", root / "usr" / "bin" / "env")
    (prefix / "bin" / "busybox").unlink()
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )


def test_closure_accepts_absolute_in_prefix_shebang_and_conventional_loader(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    shutil.copy2("/usr/bin/busybox", prefix / "bin" / "python")
    script = prefix / "bin" / "probe"
    script.write_text(
        f"#!{PROVIDER_PREFIX}/bin/python -I\n",
        encoding="utf-8",
    )
    script.chmod(0o555)
    script_closure = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )
    assert f"{PROVIDER_PREFIX}/bin/python" in {
        row.path for row in script_closure.entries
    }

    shutil.copy2("/usr/bin/true", prefix / "bin" / "dynamic")
    (root / "lib64" / "ld-linux-x86-64.so.2").unlink()
    shutil.copy2(
        "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
        root / "lib64" / "ld-linux-x86-64.so.2",
    )
    (root / "lib" / "x86_64-linux-gnu").mkdir(parents=True)
    shutil.copy2(
        "/usr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2",
        root / "lib" / "x86_64-linux-gnu" / "ld-linux-x86-64.so.2",
    )
    shutil.copy2(
        "/usr/lib/x86_64-linux-gnu/libc.so.6",
        root / "lib" / "x86_64-linux-gnu" / "libc.so.6",
    )
    dynamic_closure = api.discover_provider_runtime_closure(
        root, "dynamic", provider_prefix=PROVIDER_PREFIX
    )
    assert {
        f"{PROVIDER_PREFIX}/bin/dynamic",
        "/lib64/ld-linux-x86-64.so.2",
        "/lib/x86_64-linux-gnu/libc.so.6",
    }.issubset({row.path for row in dynamic_closure.entries})


def test_closure_rejects_non_current_elf_ident_version(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable, ident_version=2)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="ident|version",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_elf32_member(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable, elf_class=1)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="64-bit|profile",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_big_endian_elf_member(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable, data_encoding=2)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="little-endian|profile",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_non_current_elf_header_version(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable, header_version=2)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="header version",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_dynamically_needed_entry_without_pt_interp(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_minimal_elf64(
        prefix / "bin" / "probe",
        needed=("libcandidate.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(prefix / "lib" / "libcandidate.so")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="dynamically-needed.*loader",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_unreviewed_elf_type_and_accepts_static_et_exec(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable, elf_type=1)
    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="type|ET_",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )

    executable.unlink()
    _write_minimal_elf64(executable, elf_type=2)
    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )
    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe",
    }


def test_closure_rejects_et_exec_dt_needed_member(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libcandidate.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        prefix / "lib" / "libcandidate.so",
        elf_type=2,
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="ET_DYN|dependency",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_script_as_direct_dt_needed_member(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libscript.so",),
        runpath=("$ORIGIN/../lib",),
    )
    script = prefix / "lib" / "libscript.so"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(
        f"#!{PROVIDER_PREFIX}/bin/busybox\n",
        encoding="utf-8",
    )
    script.chmod(0o555)
    shutil.copy2("/usr/bin/busybox", prefix / "bin" / "busybox")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="script.*dependency",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_script_as_direct_pt_interp_member(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    loader = root / CONVENTIONAL_LOADER.lstrip("/")
    loader.unlink()
    loader.write_text(
        f"#!{PROVIDER_PREFIX}/bin/busybox\n",
        encoding="utf-8",
    )
    loader.chmod(0o555)
    shutil.copy2("/usr/bin/busybox", prefix / "bin" / "busybox")
    _write_minimal_elf64(
        prefix / "bin" / "probe",
        interpreter=CONVENTIONAL_LOADER,
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="script.*interpreter",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_script_reused_as_dependency_after_shebang_visit(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    entrypoint = f"{PROVIDER_PREFIX}/bin/probe"
    script = prefix / "bin" / "probe"
    script.write_text(
        f"#!{PROVIDER_PREFIX}/bin/helper\n",
        encoding="utf-8",
    )
    script.chmod(0o555)
    _write_dynamic_executable(
        prefix / "bin" / "helper",
        needed=(entrypoint,),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="script.*dependency",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_script_reused_as_interpreter_after_shebang_visit(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    script = prefix / "bin" / "probe"
    script.write_text(
        f"#!{CONVENTIONAL_LOADER}\n",
        encoding="utf-8",
    )
    script.chmod(0o555)
    loader = root / CONVENTIONAL_LOADER.lstrip("/")
    loader.unlink()
    loader.write_text(
        f"#!{PROVIDER_PREFIX}/bin/helper\n",
        encoding="utf-8",
    )
    loader.chmod(0o555)
    _write_minimal_elf64(
        prefix / "bin" / "helper",
        interpreter=CONVENTIONAL_LOADER,
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="script.*interpreter",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_cross_machine_dt_needed_member(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libcandidate.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        prefix / "lib" / "libcandidate.so",
        machine=183,
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="x86_64|machine",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_unreviewed_dynamic_loader(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    unreviewed_loader = "/lib64/ld-unreviewed.so"
    _write_minimal_elf64(root / unreviewed_loader.lstrip("/"))
    _write_minimal_elf64(
        prefix / "bin" / "probe",
        interpreter=unreviewed_loader,
        needed=("libcandidate.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(prefix / "lib" / "libcandidate.so")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="loader|interpreter",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_uses_only_reviewed_x86_64_default_directories(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    assert api._DEFAULT_LOADER_DIRECTORIES == (
        "/lib/x86_64-linux-gnu",
        "/usr/lib/x86_64-linux-gnu",
        "/lib",
        "/usr/lib",
    )
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libdefault.so",),
    )
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / "libdefault.so"
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )
    assert "/lib/x86_64-linux-gnu/libdefault.so" in {
        row.path for row in closure.entries
    }


def test_closure_resolves_first_base_x86_64_glibc_cache_row(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    first = prefix / "cache-first" / "libcached.so"
    second = prefix / "cache-second" / "libcached.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libcached.so",),
    )
    _write_minimal_elf64(first)
    _write_minimal_elf64(second)
    cache = _write_glibc_new_cache(
        root,
        (
            (
                "libcached.so",
                f"{PROVIDER_PREFIX}/cache-first/libcached.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
            (
                "libcached.so",
                f"{PROVIDER_PREFIX}/cache-second/libcached.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    paths = {row.path for row in closure.entries}
    assert GLIBC_CACHE_PATH in paths
    assert f"{PROVIDER_PREFIX}/cache-first/libcached.so" in paths
    assert f"{PROVIDER_PREFIX}/cache-second/libcached.so" not in paths
    cache_row = next(
        row for row in closure.entries if row.path == GLIBC_CACHE_PATH
    )
    assert cache_row.digest == f"sha256:{sha256(cache.read_bytes()).hexdigest()}"


def test_closure_glibc_cache_selection_precedes_exact_default(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    cached = prefix / "cache" / "libsame.so"
    default = root / "lib" / "x86_64-linux-gnu" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(cached)
    _write_minimal_elf64(default)
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    paths = {row.path for row in closure.entries}
    assert f"{PROVIDER_PREFIX}/cache/libsame.so" in paths
    assert "/lib/x86_64-linux-gnu/libsame.so" not in paths


def test_closure_glibc_cache_is_lazy_after_direct_runpath_match(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libdirect.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(prefix / "lib" / "libdirect.so")
    cache = _write_glibc_new_cache(root, ())
    cache.chmod(0o644)
    cache.write_bytes(b"not a cache")
    cache.chmod(0o444)

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    paths = {row.path for row in closure.entries}
    assert f"{PROVIDER_PREFIX}/lib/libdirect.so" in paths
    assert GLIBC_CACHE_PATH not in paths


@pytest.mark.parametrize(
    "corruption",
    [
        "magic",
        "version",
        "endian",
        "padding",
        "reserved",
        "entry_bounds",
        "extension_bounds",
        "extension_directory_bounds",
        "extension_payload_bounds",
        "string_offset",
        "unterminated_string",
    ],
)
def test_closure_rejects_malformed_glibc_new_cache(
    tmp_path: Path,
    corruption: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libtarget.so",),
    )
    cache = _write_glibc_new_cache(
        root,
        (
            (
                "libtarget.so",
                f"{PROVIDER_PREFIX}/lib/libtarget.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )
    image = bytearray(cache.read_bytes())
    if corruption == "magic":
        image[0] ^= 0x01
    elif corruption == "version":
        image[17:20] = b"9.9"
    elif corruption == "endian":
        image[28] = 3
    elif corruption == "padding":
        image[29] = 1
    elif corruption == "reserved":
        struct.pack_into("<I", image, 36, 1)
    elif corruption == "entry_bounds":
        struct.pack_into("<I", image, 20, 1_000_000)
    elif corruption == "extension_bounds":
        struct.pack_into("<I", image, 32, len(image) + 1)
    elif corruption == "extension_directory_bounds":
        extension_offset = (len(image) + 3) & ~3
        image.extend(b"\0" * (extension_offset - len(image)))
        struct.pack_into("<I", image, 32, extension_offset)
        image.extend(struct.pack("<II", 0xEAA42174, 1))
    elif corruption == "extension_payload_bounds":
        extension_offset = (len(image) + 3) & ~3
        image.extend(b"\0" * (extension_offset - len(image)))
        struct.pack_into("<I", image, 32, extension_offset)
        image.extend(struct.pack("<II", 0xEAA42174, 1))
        image.extend(
            struct.pack(
                "<IIII",
                0,
                0,
                extension_offset + 24,
                1,
            )
        )
    elif corruption == "string_offset":
        struct.pack_into("<I", image, 52, len(image))
    else:
        image[-1] = ord("x")
    cache.chmod(0o644)
    cache.write_bytes(image)
    cache.chmod(0o444)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="ld[.]so[.]cache|glibc cache",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


@pytest.mark.parametrize(
    ("flags", "hwcap"),
    [
        (0x203, 0),
        (GLIBC_CACHE_X86_64_FLAGS, 1),
    ],
)
def test_closure_rejects_unsupported_priority_glibc_cache_match(
    tmp_path: Path,
    flags: int,
    hwcap: int,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / "libsame.so"
    )
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                flags,
                hwcap,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="unsupported.*cache|cache.*unsupported",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_stops_at_supported_cache_row_before_later_unsupported_match(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(selected)
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/unsupported/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                1,
            ),
        ),
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert f"{PROVIDER_PREFIX}/cache/libsame.so" in {
        row.path for row in closure.entries
    }


@pytest.mark.parametrize("cache_state", ["absent", "empty"])
def test_closure_skips_cache_comparator_domain_when_no_cache_rows_exist(
    tmp_path: Path,
    cache_state: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    needed = "lib2147483648.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=(needed,),
    )
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / needed
    )
    if cache_state == "empty":
        _write_glibc_new_cache(root, ())

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert f"/lib/x86_64-linux-gnu/{needed}" in {
        row.path for row in closure.entries
    }


@pytest.mark.parametrize(
    ("first_key", "second_key"),
    [
        ("liba.so", "libz.so"),
        ("libnumeric9.so", "libnumeric10.so"),
    ],
)
def test_closure_rejects_glibc_cache_outside_exact_loader_sort_order(
    tmp_path: Path,
    first_key: str,
    second_key: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / first_key
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=(first_key,),
    )
    _write_minimal_elf64(selected)
    _write_glibc_new_cache(
        root,
        (
            (
                first_key,
                f"{PROVIDER_PREFIX}/cache/{first_key}",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
            (
                second_key,
                f"{PROVIDER_PREFIX}/cache/{second_key}",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="sort|order",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_accepts_glibc_cache_exact_numeric_loader_sort_order(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libnumeric9.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libnumeric9.so",),
    )
    _write_minimal_elf64(selected)
    _write_glibc_new_cache(
        root,
        (
            (
                "libnumeric10.so",
                f"{PROVIDER_PREFIX}/cache/libnumeric10.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
            (
                "libnumeric9.so",
                f"{PROVIDER_PREFIX}/cache/libnumeric9.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert f"{PROVIDER_PREFIX}/cache/libnumeric9.so" in {
        row.path for row in closure.entries
    }


def test_closure_matches_glibc_cache_numeric_equivalent_key(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libselected.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libnumeric9.so",),
    )
    _write_minimal_elf64(selected)
    _write_glibc_new_cache(
        root,
        (
            (
                "libnumeric09.so",
                f"{PROVIDER_PREFIX}/cache/libselected.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert f"{PROVIDER_PREFIX}/cache/libselected.so" in {
        row.path for row in closure.entries
    }


def test_closure_rejects_glibc_cache_numeric_run_outside_comparator_domain(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    key = "libnumeric2147483648.so"
    selected = prefix / "cache" / key
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=(key,),
    )
    _write_minimal_elf64(selected)
    _write_glibc_new_cache(
        root,
        (
            (
                key,
                f"{PROVIDER_PREFIX}/cache/{key}",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="numeric|comparator",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


@pytest.mark.parametrize(
    ("target_kind", "match"),
    [
        ("missing", "not packaged"),
        ("directory", "regular file"),
        ("script", "script.*dependency"),
    ],
)
def test_closure_rejects_selected_invalid_cache_target_without_default_fallback(
    tmp_path: Path,
    target_kind: str,
    match: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / "libsame.so"
    )
    if target_kind == "directory":
        selected.mkdir(parents=True)
    elif target_kind == "script":
        selected.parent.mkdir(parents=True)
        selected.write_text(
            f"#!{PROVIDER_PREFIX}/bin/busybox\n",
            encoding="utf-8",
        )
        selected.chmod(0o555)
        shutil.copy2("/usr/bin/busybox", prefix / "bin" / "busybox")
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(api.ProviderIsolationEnvironmentError, match=match):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_selected_glibc_cache_overlay_target(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(root / "tmp" / "libsame.so")
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / "libsame.so"
    )
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                "/tmp/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_selected_cache_target_resolving_into_overlay(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(root / "tmp" / "libsame.so")
    _write_minimal_elf64(
        root / "lib" / "x86_64-linux-gnu" / "libsame.so"
    )
    selected = root / "lib" / "cache-selected.so"
    selected.symlink_to("/tmp/libsame.so")
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                "/lib/cache-selected.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_rejects_runpath_member_resolving_into_writable_overlay(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
        runpath=(f"{PROVIDER_PREFIX}/lib",),
    )
    _write_minimal_elf64(root / "tmp" / "libsame.so")
    (prefix / "lib").mkdir(parents=True)
    (prefix / "lib" / "libsame.so").symlink_to("/tmp/libsame.so")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_accepts_runpath_member_resolving_within_sealed_rootfs(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
        runpath=(f"{PROVIDER_PREFIX}/lib",),
    )
    target = prefix / "sealed-libs" / "libsame.so"
    _write_minimal_elf64(target)
    (prefix / "lib").mkdir(parents=True)
    (prefix / "lib" / "libsame.so").symlink_to(
        "../sealed-libs/libsame.so"
    )

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    selected = next(
        row
        for row in closure.entries
        if row.path == f"{PROVIDER_PREFIX}/lib/libsame.so"
    )
    assert selected.resolved_path == (
        f"{PROVIDER_PREFIX}/sealed-libs/libsame.so"
    )


def test_closure_rejects_writable_overlay_request_resolving_to_safe_member(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    safe = root / "opt" / "sealed" / "probe"
    _write_minimal_elf64(safe)
    requested = root / "tmp" / "provider" / "bin" / "probe"
    requested.parent.mkdir(parents=True)
    requested.symlink_to("/opt/sealed/probe")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix="/tmp/provider",
        )


def test_closure_rejects_glibc_cache_resolving_into_overlay(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(selected)
    cache = _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )
    overlay_cache = root / "tmp" / "ld.so.cache"
    overlay_cache.parent.mkdir(parents=True, exist_ok=True)
    cache.rename(overlay_cache)
    cache.symlink_to("/tmp/ld.so.cache")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_recorded_closure_rejects_glibc_cache_digest_tamper(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(selected)
    cache = _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )
    recorded = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )
    cache.chmod(0o644)
    _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
            (
                "libunrelated.so",
                f"{PROVIDER_PREFIX}/cache/libunrelated.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="mismatch|no longer|digest",
    ):
        api.verify_provider_runtime_closure(root, recorded)


def test_closure_rejects_glibc_cache_mutation_during_revalidation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    selected = prefix / "cache" / "libsame.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libsame.so",),
    )
    _write_minimal_elf64(selected)
    cache = _write_glibc_new_cache(
        root,
        (
            (
                "libsame.so",
                f"{PROVIDER_PREFIX}/cache/libsame.so",
                GLIBC_CACHE_X86_64_FLAGS,
                0,
            ),
        ),
    )
    real_parse = api._parse_glibc_cache_fd
    mutated = False

    def mutate_after_parse(fd: int):
        nonlocal mutated
        parsed = real_parse(fd)
        cache.chmod(0o644)
        cache.write_bytes(cache.read_bytes() + b"\0")
        cache.chmod(0o444)
        mutated = True
        return parsed

    monkeypatch.setattr(api, "_parse_glibc_cache_fd", mutate_after_parse)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert mutated


@pytest.mark.parametrize("tag", ["rpath", "runpath"])
@pytest.mark.parametrize(
    "overlay_path",
    [
        "/home",
        "/workspace/build",
        "/tmp",
        "/run/provider",
        "/candidate",
        "/proc/self",
        "/dev",
        "/sys/kernel",
    ],
)
def test_closure_rejects_writable_overlay_loader_search_directories(
    tmp_path: Path,
    tag: str,
    overlay_path: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libcandidate.so",),
        **{tag: (overlay_path,)},
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


@pytest.mark.parametrize(
    "absolute_needed",
    [
        "/home/libcandidate.so",
        "/workspace/build/libcandidate.so",
        "/tmp/libcandidate.so",
        "/run/provider/libcandidate.so",
        "/candidate/libcandidate.so",
        "/proc/self/libcandidate.so",
        "/dev/libcandidate.so",
        "/sys/kernel/libcandidate.so",
    ],
)
def test_closure_rejects_absolute_needed_below_writable_overlay(
    tmp_path: Path,
    absolute_needed: str,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=(absolute_needed,),
    )

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="writable|overlay",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_accepts_actual_sealed_system_python_chain(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    host_python = Path("/usr/bin/python3")
    if not host_python.exists():
        pytest.skip("system Python fixture is unavailable")
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "python"
    shutil.copy2(host_python, executable)
    _copy_reviewed_x86_64_system_python_runtime(root)

    closure = api.discover_provider_runtime_closure(
        root,
        "python",
        provider_prefix=PROVIDER_PREFIX,
    )

    paths = {row.path for row in closure.entries}
    assert paths == {
        f"{PROVIDER_PREFIX}/bin/python",
        *REVIEWED_X86_64_SYSTEM_PYTHON_RUNTIME,
    }


def test_reviewed_system_python_fixture_never_invokes_subprocess(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _rootfs(tmp_path)

    def reject_subprocess(*_args, **_kwargs):
        raise AssertionError("runtime fixture must not execute ldd or a target")

    monkeypatch.setattr(subprocess, "run", reject_subprocess)
    _copy_reviewed_x86_64_system_python_runtime(root)

    assert (root / CONVENTIONAL_LOADER.lstrip("/")).is_file()
    assert (
        root / "lib" / "x86_64-linux-gnu" / "libc.so.6"
    ).is_file()


def test_closure_accepts_actual_static_codex_pie(tmp_path: Path) -> None:
    api = _environment_api()
    codex_launcher = shutil.which("codex")
    if codex_launcher is None:
        pytest.skip("Codex launcher is unavailable")
    package_root = Path(codex_launcher).resolve().parents[1]
    candidates = sorted(
        package_root.glob(
            "node_modules/@openai/codex-linux-*/vendor/*/bin/codex"
        )
    )
    if not candidates:
        pytest.skip("native Codex binary is unavailable")
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "codex"
    shutil.copy2(candidates[0], executable)

    closure = api.discover_provider_runtime_closure(
        root,
        "codex",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/codex",
    }


@pytest.mark.parametrize(
    ("tag", "token"),
    [("rpath", "$ORIGIN"), ("runpath", "${ORIGIN}")],
)
def test_closure_parses_rpath_and_runpath_and_recurses_dependencies(
    tmp_path: Path, tag: str, token: str
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    loader = root / CONVENTIONAL_LOADER.lstrip("/")
    leaf = prefix / "lib" / "nested" / "libleaf.so"
    dependency = prefix / "lib" / "libfirst.so"
    executable = prefix / "bin" / "probe"
    _write_minimal_elf64(leaf)
    _write_minimal_elf64(
        dependency,
        needed=("libleaf.so",),
        **{tag: (f"{token}/nested",)},
    )
    _write_minimal_elf64(
        executable,
        interpreter=CONVENTIONAL_LOADER,
        needed=("libfirst.so",),
        **{tag: (f"{token}/../lib",)},
    )

    closure = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )

    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe",
        CONVENTIONAL_LOADER,
        f"{PROVIDER_PREFIX}/lib/libfirst.so",
        f"{PROVIDER_PREFIX}/lib/nested/libleaf.so",
    }


def test_closure_entry_rpath_is_inherited_by_pathless_grandchild(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    parent = prefix / "lib" / "libparent.so"
    grandchild = prefix / "lib" / "libgrandchild.so"
    _write_dynamic_executable(
        executable,
        needed=("libparent.so",),
        rpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        parent,
        needed=("libgrandchild.so",),
    )
    _write_minimal_elf64(grandchild)

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe",
        CONVENTIONAL_LOADER,
        f"{PROVIDER_PREFIX}/lib/libparent.so",
        f"{PROVIDER_PREFIX}/lib/libgrandchild.so",
    }


def test_closure_entry_runpath_is_not_inherited_by_pathless_grandchild(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    parent = prefix / "lib" / "libparent.so"
    grandchild = prefix / "lib" / "libgrandchild.so"
    _write_dynamic_executable(
        executable,
        needed=("libparent.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        parent,
        needed=("libgrandchild.so",),
    )
    _write_minimal_elf64(grandchild)

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="libgrandchild",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_child_runpath_locates_its_direct_child(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    parent = prefix / "lib" / "libparent.so"
    child = prefix / "lib" / "nested" / "libchild.so"
    _write_dynamic_executable(
        executable,
        needed=("libparent.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        parent,
        needed=("libchild.so",),
        runpath=("$ORIGIN/nested",),
    )
    _write_minimal_elf64(child)

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert {row.path for row in closure.entries} == {
        f"{PROVIDER_PREFIX}/bin/probe",
        CONVENTIONAL_LOADER,
        f"{PROVIDER_PREFIX}/lib/libparent.so",
        f"{PROVIDER_PREFIX}/lib/nested/libchild.so",
    }


def test_closure_runpath_suppresses_same_object_rpath(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libparent.so",),
        rpath=("$ORIGIN/../rpath-only",),
        runpath=("$ORIGIN/../runpath-missing",),
    )
    _write_minimal_elf64(prefix / "rpath-only" / "libparent.so")

    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="libparent",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )


def test_closure_ordered_search_uses_first_packaged_location(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    first = prefix / "first" / "libsame.so"
    second = prefix / "second" / "libsame.so"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=(
            "$ORIGIN/../first",
            "$ORIGIN/../second",
        ),
    )
    _write_minimal_elf64(first)
    _write_minimal_elf64(second)

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert f"{PROVIDER_PREFIX}/first/libsame.so" in {
        row.path for row in closure.entries
    }
    assert f"{PROVIDER_PREFIX}/second/libsame.so" not in {
        row.path for row in closure.entries
    }


@pytest.mark.parametrize("first_parent_exists", [True, False])
def test_closure_rejects_earlier_search_candidate_created_after_later_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    first_parent_exists: bool,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    if first_parent_exists:
        (root / "first").mkdir()
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    second = root / "second" / "libsame.so"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=("/first", "/second"),
    )
    _write_minimal_elf64(second)
    real_hash = api._hash_regular_file
    hash_count = 0

    def create_earlier_candidate_after_later_hash(
        fd: int,
    ) -> tuple[int, str]:
        nonlocal hash_count
        result = real_hash(fd)
        hash_count += 1
        if hash_count == 3:
            _write_minimal_elf64(root / "first" / "libsame.so")
        return result

    monkeypatch.setattr(
        api,
        "_hash_regular_file",
        create_earlier_candidate_after_later_hash,
    )
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert hash_count == 3


def test_closure_uses_later_search_location_when_earlier_absence_is_stable(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=("/first", "/second"),
    )
    _write_minimal_elf64(root / "second" / "libsame.so")

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert "/second/libsame.so" in {row.path for row in closure.entries}
    assert "/first/libsame.so" not in {row.path for row in closure.entries}


def test_closure_closes_negative_lookup_descriptors_on_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    (root / "first").mkdir()
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=("/first", "/second"),
    )
    _write_minimal_elf64(root / "second" / "libsame.so")
    opened: list[int] = []
    real_open_directory = api._open_directory
    real_open_directory_at = api._open_directory_at
    real_open_regular_at = api._open_regular_at
    real_parse = api._parse_elf_fd

    def record_directory(path) -> int:
        fd = real_open_directory(path)
        opened.append(fd)
        return fd

    def record_directory_at(directory_fd: int, name: str) -> int:
        fd = real_open_directory_at(directory_fd, name)
        opened.append(fd)
        return fd

    def record_regular_at(directory_fd: int, name: str) -> int:
        fd = real_open_regular_at(directory_fd, name)
        opened.append(fd)
        return fd

    def fail_selected_dependency(fd: int, provider_path: str):
        if provider_path == "/second/libsame.so":
            raise RuntimeError("injected post-negative-lookup failure")
        return real_parse(fd, provider_path)

    monkeypatch.setattr(api, "_open_directory", record_directory)
    monkeypatch.setattr(api, "_open_directory_at", record_directory_at)
    monkeypatch.setattr(api, "_open_regular_at", record_regular_at)
    monkeypatch.setattr(api, "_parse_elf_fd", fail_selected_dependency)

    with pytest.raises(
        RuntimeError,
        match="injected post-negative-lookup failure",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )

    assert opened
    for fd in set(opened):
        with pytest.raises(OSError) as exc_info:
            os.fstat(fd)
        assert exc_info.value.errno == errno.EBADF


@pytest.mark.parametrize("via_symlink", [False, True])
def test_closure_rejects_earlier_non_directory_blocker_replaced_after_selection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    via_symlink: bool,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    blocker = root / ("target-blocker" if via_symlink else "first")
    blocker.write_bytes(b"not a directory")
    blocker.chmod(0o444)
    first_search = "/alias" if via_symlink else "/first"
    if via_symlink:
        (root / "alias").symlink_to("target-blocker")
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=(first_search, "/second"),
    )
    _write_minimal_elf64(root / "second" / "libsame.so")
    real_hash = api._hash_regular_file
    hash_count = 0

    def replace_blocker_after_later_hash(fd: int) -> tuple[int, str]:
        nonlocal hash_count
        result = real_hash(fd)
        hash_count += 1
        if hash_count == 3:
            blocker.unlink()
            _write_minimal_elf64(blocker / "libsame.so")
        return result

    monkeypatch.setattr(
        api,
        "_hash_regular_file",
        replace_blocker_after_later_hash,
    )
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert hash_count == 3


@pytest.mark.parametrize("via_symlink", [False, True])
def test_closure_uses_later_location_while_non_directory_blocker_is_stable(
    tmp_path: Path,
    via_symlink: bool,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    blocker = root / ("target-blocker" if via_symlink else "first")
    blocker.write_bytes(b"not a directory")
    blocker.chmod(0o444)
    first_search = "/alias" if via_symlink else "/first"
    if via_symlink:
        (root / "alias").symlink_to("target-blocker")
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=(first_search, "/second"),
    )
    _write_minimal_elf64(root / "second" / "libsame.so")

    closure = api.discover_provider_runtime_closure(
        root,
        "probe",
        provider_prefix=PROVIDER_PREFIX,
    )

    assert "/second/libsame.so" in {row.path for row in closure.entries}


def test_closure_closes_held_blocker_descriptor_on_later_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    assert hasattr(api, "_open_runtime_node_at")
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    blocker = root / "first"
    blocker.write_bytes(b"not a directory")
    blocker.chmod(0o444)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_dynamic_executable(
        executable,
        needed=("libsame.so",),
        rpath=("/first", "/second"),
    )
    _write_minimal_elf64(root / "second" / "libsame.so")
    real_open_node = api._open_runtime_node_at
    real_parse = api._parse_elf_fd
    blocker_fds: list[int] = []

    def record_blocker(directory_fd: int, name: str) -> int:
        fd = real_open_node(directory_fd, name)
        blocker_fds.append(fd)
        return fd

    def fail_selected_dependency(fd: int, provider_path: str):
        if provider_path == "/second/libsame.so":
            raise RuntimeError("injected post-blocker failure")
        return real_parse(fd, provider_path)

    monkeypatch.setattr(api, "_open_runtime_node_at", record_blocker)
    monkeypatch.setattr(api, "_parse_elf_fd", fail_selected_dependency)

    with pytest.raises(RuntimeError, match="injected post-blocker failure"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )

    assert blocker_fds
    for fd in blocker_fds:
        with pytest.raises(OSError) as exc_info:
            os.fstat(fd)
        assert exc_info.value.errno == errno.EBADF


@pytest.mark.parametrize(
    "shebang",
    [
        "#!relative/python\n",
        "#!/missing/python\n",
        "#!/usr/bin/env missing\n",
    ],
)
def test_closure_rejects_missing_unpacked_or_relative_shebangs(
    tmp_path: Path, shebang: str
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    script = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    script.write_text(shebang, encoding="utf-8")
    script.chmod(0o555)
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )


def test_closure_rejects_missing_loader_library_and_ld_so_preload(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "dynamic"
    shutil.copy2("/usr/bin/true", executable)
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "dynamic", provider_prefix=PROVIDER_PREFIX
        )

    shutil.copy2("/usr/bin/busybox", executable)
    (root / "etc").mkdir()
    (root / "etc" / "ld.so.preload").write_text("/candidate/evil.so\n")
    with pytest.raises(
        api.ProviderIsolationEnvironmentError, match="ld[.]so[.]preload"
    ):
        api.discover_provider_runtime_closure(
            root, "dynamic", provider_prefix=PROVIDER_PREFIX
        )


def test_closure_rejects_unknown_origin_tokens_and_escape(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.expand_loader_search_path(
            "$LIB/../candidate",
            containing_object=f"{PROVIDER_PREFIX}/bin/tool",
            allowed_root=PROVIDER_PREFIX,
        )
    assert api.expand_loader_search_path(
        "${ORIGIN}/../lib",
        containing_object=f"{PROVIDER_PREFIX}/bin/tool",
        allowed_root=PROVIDER_PREFIX,
    ) == (f"{PROVIDER_PREFIX}/lib",)
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.expand_loader_search_path(
            "$ORIGIN/../../../outside",
            containing_object=f"{PROVIDER_PREFIX}/bin/tool",
            allowed_root=PROVIDER_PREFIX,
        )


def test_closure_rejects_relative_empty_and_unknown_loader_search_entries(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    for value in ("relative", "$ORIGIN:", "$PLATFORM/lib", "${LIB}/lib"):
        with pytest.raises(api.ProviderIsolationEnvironmentError):
            api.expand_loader_search_path(
                value,
                containing_object=f"{PROVIDER_PREFIX}/bin/tool",
                allowed_root=PROVIDER_PREFIX,
            )


def test_closure_rejects_malformed_elf_and_rootfs_escaping_symlink(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    executable.write_bytes(b"\x7fELF\x02\x01\x01")
    executable.chmod(0o555)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="ELF"):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )

    executable.unlink()
    executable.symlink_to("/usr/bin/true")
    with pytest.raises(api.ProviderIsolationEnvironmentError):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )


def test_closure_rejects_unresolved_recursive_dependency(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libfirst.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(
        prefix / "lib" / "libfirst.so",
        needed=("libmissing.so",),
        runpath=("$ORIGIN",),
    )
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="libmissing"):
        api.discover_provider_runtime_closure(
            root, "probe", provider_prefix=PROVIDER_PREFIX
        )


def test_recorded_closure_rejects_interpreter_swap(tmp_path: Path) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    shutil.copy2("/usr/bin/busybox", executable)
    recorded = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )
    original = executable.read_bytes()
    executable.chmod(0o755)
    executable.write_bytes(original + b"\0")
    executable.chmod(0o555)
    with pytest.raises(api.ProviderIsolationEnvironmentError) as exc_info:
        api.verify_provider_runtime_closure(root, recorded)
    assert exc_info.value.code == "provider_isolation_environment_mismatch"


def test_recorded_closure_rejects_transitive_dependency_digest_swap(
    tmp_path: Path,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    dependency = prefix / "lib" / "libfirst.so"
    _write_dynamic_executable(
        prefix / "bin" / "probe",
        needed=("libfirst.so",),
        runpath=("$ORIGIN/../lib",),
    )
    _write_minimal_elf64(dependency)
    recorded = api.discover_provider_runtime_closure(
        root, "probe", provider_prefix=PROVIDER_PREFIX
    )
    dependency.chmod(0o755)
    dependency.write_bytes(dependency.read_bytes() + b"\0")
    dependency.chmod(0o555)
    with pytest.raises(api.ProviderIsolationEnvironmentError) as exc_info:
        api.verify_provider_runtime_closure(root, recorded)
    assert exc_info.value.code == "provider_isolation_environment_mismatch"


def test_closure_rejects_entry_exchange_after_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    replacement = executable.with_name("replacement")
    displaced = executable.with_name("displaced")
    _write_minimal_elf64(executable)
    _write_minimal_elf64(replacement)
    replacement.chmod(0o755)
    replacement.write_bytes(replacement.read_bytes() + b"\0")
    replacement.chmod(0o555)
    real_hash = api._hash_regular_file
    exchanged = False

    def exchange_after_digest(fd: int) -> tuple[int, str]:
        nonlocal exchanged
        result = real_hash(fd)
        if not exchanged:
            executable.rename(displaced)
            replacement.rename(executable)
            exchanged = True
        return result

    monkeypatch.setattr(api, "_hash_regular_file", exchange_after_digest)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert exchanged


def test_closure_rejects_ancestor_exchange_after_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix = root / PROVIDER_PREFIX.lstrip("/")
    executable = prefix / "bin" / "probe"
    replacement_bin = prefix / "replacement-bin"
    replacement = replacement_bin / "probe"
    displaced_bin = prefix / "displaced-bin"
    _write_minimal_elf64(executable)
    _write_minimal_elf64(replacement)
    real_hash = api._hash_regular_file
    exchanged = False

    def exchange_after_digest(fd: int) -> tuple[int, str]:
        nonlocal exchanged
        result = real_hash(fd)
        if not exchanged:
            executable.parent.rename(displaced_bin)
            replacement_bin.rename(executable.parent)
            exchanged = True
        return result

    monkeypatch.setattr(api, "_hash_regular_file", exchange_after_digest)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert exchanged


def test_closure_uses_one_held_file_across_aba_exchange(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    assert hasattr(api, "_parse_elf_fd")
    root = _rootfs(tmp_path)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    replacement = executable.with_name("replacement")
    displaced = executable.with_name("displaced")
    _write_minimal_elf64(executable)
    original_bytes = executable.read_bytes()
    _write_minimal_elf64(
        replacement,
        needed=("lib-from-replacement.so",),
        runpath=("$ORIGIN",),
    )
    real_hash = api._hash_regular_file
    real_parse_fd = api._parse_elf_fd
    observed_digest: str | None = None
    observed_parse = None
    exchanged = False

    def exchange_after_digest(fd: int) -> tuple[int, str]:
        nonlocal exchanged, observed_digest
        result = real_hash(fd)
        observed_digest = result[1]
        executable.rename(displaced)
        replacement.rename(executable)
        exchanged = True
        return result

    def parse_then_restore(fd: int, provider_path: str):
        nonlocal observed_parse
        observed_parse = real_parse_fd(fd, provider_path)
        executable.unlink()
        displaced.rename(executable)
        return observed_parse

    monkeypatch.setattr(api, "_hash_regular_file", exchange_after_digest)
    monkeypatch.setattr(api, "_parse_elf_fd", parse_then_restore)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )

    assert exchanged
    assert observed_digest == f"sha256:{sha256(original_bytes).hexdigest()}"
    assert observed_parse == api.ParsedElf(
        elf_class=2,
        data_encoding=1,
        ident_version=1,
        elf_type=3,
        machine=62,
        header_version=1,
        interpreter=None,
        needed=(),
        rpath=(),
        runpath=(),
    )


def test_closure_rejects_symlink_exchange_without_following_host_namespace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    prefix_bin = root / PROVIDER_PREFIX.lstrip("/") / "bin"
    executable = prefix_bin / "probe"
    target = prefix_bin / "real-probe"
    packaged_absolute_target = root / "usr" / "bin" / "true"
    _write_minimal_elf64(target)
    _write_minimal_elf64(packaged_absolute_target)
    executable.symlink_to("real-probe")
    real_hash = api._hash_regular_file
    exchanged = False

    def exchange_after_digest(fd: int) -> tuple[int, str]:
        nonlocal exchanged
        result = real_hash(fd)
        if not exchanged:
            executable.unlink()
            executable.symlink_to("/usr/bin/true")
            exchanged = True
        return result

    monkeypatch.setattr(api, "_hash_regular_file", exchange_after_digest)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert exchanged


def test_closure_rejects_ld_so_preload_created_after_first_member_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    etc = root / "etc"
    etc.mkdir()
    etc.chmod(0o755)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable)
    real_hash = api._hash_regular_file
    created = False

    def create_preload_after_digest(fd: int) -> tuple[int, str]:
        nonlocal created
        result = real_hash(fd)
        if not created:
            (etc / "ld.so.preload").write_text(
                "/opt/late/libcandidate.so\n",
                encoding="utf-8",
            )
            created = True
        return result

    monkeypatch.setattr(
        api,
        "_hash_regular_file",
        create_preload_after_digest,
    )
    with pytest.raises(
        api.ProviderIsolationEnvironmentError,
        match="preload|changed",
    ):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert created


def test_closure_rejects_etc_authority_exchange_after_first_member_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    root = _rootfs(tmp_path)
    etc = root / "etc"
    etc.mkdir()
    etc.chmod(0o755)
    replacement = root / "replacement-etc"
    replacement.mkdir()
    replacement.chmod(0o755)
    displaced = root / "displaced-etc"
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable)
    real_hash = api._hash_regular_file
    exchanged = False

    def exchange_etc_after_digest(fd: int) -> tuple[int, str]:
        nonlocal exchanged
        result = real_hash(fd)
        if not exchanged:
            etc.rename(displaced)
            replacement.rename(etc)
            exchanged = True
        return result

    monkeypatch.setattr(api, "_hash_regular_file", exchange_etc_after_digest)
    with pytest.raises(api.ProviderIsolationEnvironmentError, match="changed"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )
    assert exchanged


def test_closure_closes_all_pinned_descriptors_on_parser_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _environment_api()
    assert hasattr(api, "_parse_elf_fd")
    root = _rootfs(tmp_path)
    (root / "etc").mkdir()
    (root / "etc").chmod(0o755)
    executable = root / PROVIDER_PREFIX.lstrip("/") / "bin" / "probe"
    _write_minimal_elf64(executable)
    opened: list[int] = []
    real_open_directory = api._open_directory
    real_open_directory_at = api._open_directory_at
    real_open_regular_at = api._open_regular_at

    def record_directory(path) -> int:
        fd = real_open_directory(path)
        opened.append(fd)
        return fd

    def record_directory_at(directory_fd: int, name: str) -> int:
        fd = real_open_directory_at(directory_fd, name)
        opened.append(fd)
        return fd

    def record_regular_at(directory_fd: int, name: str) -> int:
        fd = real_open_regular_at(directory_fd, name)
        opened.append(fd)
        return fd

    def fail_parse(_fd: int, _provider_path: str):
        raise RuntimeError("injected descriptor parser failure")

    monkeypatch.setattr(api, "_open_directory", record_directory)
    monkeypatch.setattr(api, "_open_directory_at", record_directory_at)
    monkeypatch.setattr(api, "_open_regular_at", record_regular_at)
    monkeypatch.setattr(api, "_parse_elf_fd", fail_parse)

    with pytest.raises(RuntimeError, match="injected descriptor parser failure"):
        api.discover_provider_runtime_closure(
            root,
            "probe",
            provider_prefix=PROVIDER_PREFIX,
        )

    assert opened
    for fd in set(opened):
        with pytest.raises(OSError) as exc_info:
            os.fstat(fd)
        assert exc_info.value.errno == errno.EBADF
