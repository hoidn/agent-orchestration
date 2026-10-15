"""Host reads and wipes of a holder's guest-owned tmpfs mounts (design D-c, R6, Task 6 notes).

Everything here works beneath a retained root descriptor opened from
`/proc/<holder>/root` and runs only after whole-slot quiescence. Every
component is opened `O_NOFOLLOW`, every file `O_NONBLOCK` and checked with
`fstat` for `S_ISREG` before a bounded read, and directories are pinned to the
mount's `st_dev`, so a planted FIFO, device, socket or symlink never blocks
the host or leads it off the tmpfs. Refusals the guest can cause (not a
regular file, a symlink, a missing or unreadable entry, too many entries) are
`GuestRefusal`; host faults (`EMFILE`, `EIO`, ...) propagate as `OSError`.
The small cgroup and `/proc` readers the holder protocol uses live here too.
"""

from __future__ import annotations

import errno
import os
import select
import stat
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from orchestrator._common.safe_tree import remove_tree_contents

from .holder_spawner import RESERVED_RESULT_NAMES

MAX_RESULT_ENTRIES = 4096
MAX_RESULT_DEPTH = 32
_GUEST_ERRNOS = frozenset({errno.ENOENT, errno.ELOOP, errno.ENOTDIR, errno.EISDIR, errno.EACCES, errno.EPERM,
                           errno.ENXIO, errno.ENODEV})
_VANISHED = (errno.ENOENT, errno.ENODEV)  # a cgroup being removed fails its file ops with ENODEV
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


def _open(name: str, flags: int, dir_fd: int, label: str) -> int:
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno in _GUEST_ERRNOS:
            raise GuestRefusal(f"{label}: {os.strerror(exc.errno)}") from exc
        raise


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


def read_leaf_results(result_fd: int, leaf: str, *, stdout_limit: int, stderr_limit: int,
                      max_bytes: int) -> LeafReads:
    """stdout/stderr (bounded, truncation flagged) and every other regular file under `/result/<leaf>`."""
    device = os.fstat(result_fd).st_dev
    root = _directory(leaf, result_fd, device, f"/result/{leaf}")
    try:
        stdout = read_bounded(root, "stdout", stdout_limit, f"/result/{leaf}/stdout")
        stderr = read_bounded(root, "stderr", stderr_limit, f"/result/{leaf}/stderr")
        files: dict[str, bytes] = {}
        _collect(root, "", device, files, max_bytes, f"/result/{leaf}")
    finally:
        os.close(root)
    return LeafReads(stdout[0], stdout[1], stderr[0], stderr[1], files)


def _collect(dir_fd: int, prefix: str, device: int, files: dict[str, bytes], budget: int, label: str) -> int:
    if prefix.count("/") >= MAX_RESULT_DEPTH:
        raise GuestRefusal(f"{label}/{prefix} is nested too deeply")
    for name in sorted(os.listdir(dir_fd)):
        relative = prefix + name
        if not prefix and name in RESERVED_RESULT_NAMES:
            continue
        if len(files) >= MAX_RESULT_ENTRIES:
            raise GuestRefusal(f"{label} holds too many entries")
        info = os.stat(name, dir_fd=dir_fd, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = _directory(name, dir_fd, device, f"{label}/{relative}")
            try:
                budget = _collect(child, relative + "/", device, files, budget, label)
            finally:
                os.close(child)
            continue
        data, truncated = read_bounded(dir_fd, name, budget, f"{label}/{relative}")
        if truncated:
            raise GuestRefusal(f"{label} exceeds {budget} bytes")
        files[relative] = data
        budget -= len(data)
    return budget


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
    """chmod then empty a guest tmpfs mount through its root descriptor; True when it is empty."""
    remove_tree_contents(root_fd)
    return not os.listdir(root_fd)


# -- cgroup and /proc readers ------------------------------------------------------------------
def memfd(data: bytes) -> int:
    fd = os.memfd_create("run-ref-holder")
    os.write(fd, data)
    os.lseek(fd, 0, os.SEEK_SET)
    return fd


def procs(cgroup: Path) -> set[int]:
    return {int(pid) for pid in (cgroup / "cgroup.procs").read_text().split()}


def populated(cgroup: Path) -> bool:
    try:
        return "populated 1" in (cgroup / "cgroup.events").read_text()
    except OSError as exc:
        if exc.errno in _VANISHED:
            return False
        raise


def kill_cgroup(cgroup: Path, timeout: float = 10.0) -> bool:
    """`cgroup.kill` and wait until unpopulated; a vanished cgroup is empty."""
    try:
        if populated(cgroup):
            (cgroup / "cgroup.kill").write_text("1")
    except OSError as exc:
        if exc.errno not in _VANISHED:
            raise
    deadline = time.monotonic() + timeout
    while populated(cgroup):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def nspid(pid: int) -> int:
    rows = [line for line in Path(f"/proc/{pid}/status").read_text().splitlines() if line.startswith("NSpid:")]
    return int(rows[0].split()[-1])


def drain(fd: int, deadline: float) -> bytes:
    data = b""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError("holder info pipe did not close")
            chunk = os.read(fd, 4096)
            if not chunk:
                return data
            data += chunk
    finally:
        os.close(fd)
