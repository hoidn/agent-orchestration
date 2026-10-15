"""Host reads, writes and wipes of a holder's guest-owned tmpfs mounts (design D-c, R6, P27, P28).

Everything here works beneath a retained root descriptor opened from
`/proc/<holder>/root` and runs only after whole-slot quiescence, in the
controller (P27). Every component is opened `O_NOFOLLOW`, every file
`O_NONBLOCK` and checked with `fstat` for `S_ISREG` before a bounded read, and
directories are pinned to the mount's `st_dev`, so a planted FIFO, device,
socket or symlink never blocks the host or leads it off the tmpfs. Directory
listings stream through `os.scandir` and every entry is counted against one
cap before anything is sorted or kept; names must be UTF-8 and paths are
bounded. Refusals the guest can cause (not a regular file, a symlink, a
missing, unreadable or non-UTF-8 entry, too many entries, too deep, too many
bytes) are `GuestRefusal`; host faults (`EMFILE`, `EIO`, ...) propagate as
`OSError`. The wipe is iterative and holds at most `MAX_WIPE_DEPTH` descriptors.
"""

from __future__ import annotations

import errno
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass

from .holder_spawner import RESERVED_RESULT_NAMES

MAX_RESULT_ENTRIES = 4096    # every entry under /result/<leaf>, directories and stdout/stderr included
MAX_RESULT_DEPTH = 32
MAX_RESULT_PATH_BYTES = 4096
MAX_WIPE_DEPTH = 64          # descriptors one wipe may hold; a deeper guest tree is not wipeable
_GUEST_ERRNOS = frozenset({errno.ENOENT, errno.ELOOP, errno.ENOTDIR, errno.EISDIR, errno.EACCES, errno.EPERM,
                           errno.ENXIO, errno.ENODEV, errno.ENAMETOOLONG})
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_FILE = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class GuestRefusal(Exception):
    """A guest-controlled entry the host refuses to read (`run_ref_environment_escape_rejected`)."""


@dataclass(frozen=True)
class LeafReads:
    stdout: bytes
    stdout_truncated: bool
    stderr: bytes
    stderr_truncated: bool
    files: dict[str, bytes]


@dataclass
class _Budget:
    entries: int
    bytes: int


def _guest(exc: OSError, label: str) -> OSError | GuestRefusal:
    """The guest-caused errnos become refusals; anything else stays a host error."""
    if exc.errno in _GUEST_ERRNOS:
        return GuestRefusal(f"{label}: {os.strerror(exc.errno)}")
    return exc


def _open(name: str, flags: int, dir_fd: int, label: str) -> int:
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise _guest(exc, label) from exc


def read_bounded(dir_fd: int, name: str, limit: int, label: str) -> tuple[bytes, bool]:
    """At most `limit` bytes of a regular file beneath `dir_fd`, and whether more existed."""
    fd = _open(name, _FILE, dir_fd, label)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise GuestRefusal(f"{label} is not a regular file")
        chunks, size = [], 0
        while size <= limit:
            chunk = os.read(fd, min(1 << 20, limit + 1 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
        data = b"".join(chunks)
        return data[:limit], len(data) > limit
    finally:
        os.close(fd)


def _directory(name: str, dir_fd: int, device: int, label: str) -> int:
    fd = _open(name, _DIRECTORY, dir_fd, label)
    if os.fstat(fd).st_dev != device:
        os.close(fd)
        raise GuestRefusal(f"{label} leaves the result mount")
    return fd


def _scan(dir_fd: int, prefix: str, budget: _Budget, label: str) -> list[tuple[str, os.stat_result]]:
    """Stream one directory, charging every entry before keeping it; returns sorted (name, lstat) rows."""
    rows = []
    try:
        with os.scandir(dir_fd) as entries:
            for entry in entries:
                budget.entries -= 1
                if budget.entries < 0:
                    raise GuestRefusal(f"{label} holds more than {MAX_RESULT_ENTRIES} entries")
                try:
                    encoded = (prefix + entry.name).encode("utf-8")
                except UnicodeEncodeError as exc:
                    raise GuestRefusal(f"{label}/{prefix} holds a name that is not UTF-8") from exc
                if len(encoded) > MAX_RESULT_PATH_BYTES:
                    raise GuestRefusal(f"{label}/{prefix} holds a path longer than {MAX_RESULT_PATH_BYTES} bytes")
                rows.append((entry.name, os.stat(entry.name, dir_fd=dir_fd, follow_symlinks=False)))
    except OSError as exc:
        raise _guest(exc, f"{label}/{prefix}") from exc
    return sorted(rows, key=lambda row: row[0])


def read_leaf_results(result_fd: int, leaf: str, *, stdout_limit: int, stderr_limit: int,
                      max_bytes: int) -> LeafReads:
    """stdout/stderr (bounded, truncation flagged) and every other regular file under `/result/<leaf>`."""
    device = os.fstat(result_fd).st_dev
    label = f"/result/{leaf}"
    root = _directory(leaf, result_fd, device, label)
    try:
        stdout = read_bounded(root, "stdout", stdout_limit, f"{label}/stdout")
        stderr = read_bounded(root, "stderr", stderr_limit, f"{label}/stderr")
        files: dict[str, bytes] = {}
        _collect(root, "", device, files, _Budget(MAX_RESULT_ENTRIES, max_bytes), label)
    finally:
        os.close(root)
    return LeafReads(stdout[0], stdout[1], stderr[0], stderr[1], files)


def _collect(dir_fd: int, prefix: str, device: int, files: dict[str, bytes], budget: _Budget, label: str) -> None:
    if prefix.count("/") >= MAX_RESULT_DEPTH:
        raise GuestRefusal(f"{label}/{prefix} is nested too deeply")
    for name, info in _scan(dir_fd, prefix, budget, label):
        relative = prefix + name
        if not prefix and name in RESERVED_RESULT_NAMES:
            continue
        if stat.S_ISDIR(info.st_mode):
            child = _directory(name, dir_fd, device, f"{label}/{relative}")
            try:
                _collect(child, relative + "/", device, files, budget, label)
            finally:
                os.close(child)
            continue
        data, truncated = read_bounded(dir_fd, name, budget.bytes, f"{label}/{relative}")
        if truncated:
            raise GuestRefusal(f"{label} holds more result bytes than the result mount")
        files[relative] = data
        budget.bytes -= len(data)


def write_inputs(result_fd: int, leaf: str, files: Mapping[str, bytes]) -> None:
    """Host-written input files in the freshly created `/result/<leaf>` (exclusive, no-follow)."""
    directory = os.open(leaf, _DIRECTORY, dir_fd=result_fd)
    try:
        for name, data in files.items():
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o644,
                         dir_fd=directory)
            with os.fdopen(fd, "wb") as handle:
                handle.write(data)
    finally:
        os.close(directory)


def wipe_mount(root_fd: int) -> bool:
    """chmod then empty a guest tmpfs mount through its root descriptor; True when it is empty.

    Iterative, at most `MAX_WIPE_DEPTH` descriptors open: a deeper tree is left
    in place and reported as not wipeable, which fails the culprit's attempt.
    """
    # ponytail: listdir per directory holds one level's names in memory; tmpfs inode counts are not
    # bounded by --size, so a guest with millions of empty files makes this slow (charged to the wall).
    device = os.fstat(root_fd).st_dev
    os.fchmod(root_fd, 0o700)
    stack = [(os.dup(root_fd), "", iter(os.listdir(root_fd)))]
    try:
        while stack:
            fd, _name, names = stack[-1]
            name = next(names, None)
            if name is None:
                stack.pop()
                os.close(fd)
                if stack:
                    os.rmdir(_name, dir_fd=stack[-1][0])
                continue
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                os.unlink(name, dir_fd=fd)
                continue
            if len(stack) >= MAX_WIPE_DEPTH or info.st_dev != device:
                return False
            os.chmod(name, 0o700, dir_fd=fd, follow_symlinks=False)
            child = os.open(name, _DIRECTORY, dir_fd=fd)
            stack.append((child, name, iter(os.listdir(child))))
    finally:
        for fd, _name, _names in stack:
            os.close(fd)
    return not os.listdir(root_fd)
