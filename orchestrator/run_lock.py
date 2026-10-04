"""Run-lifetime process coordination for mutable workflow execution."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
import os
from pathlib import Path
import time
from typing import Iterator

from orchestrator.providers.omp_launch_fs import LaunchFsError, open_dir_no_follow

_LOCK_OPEN_FLAGS = os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW


class RunAlreadyActiveError(RuntimeError):
    """Raised when another process already owns the run writer lock."""

    code = "run_already_active"

    def __init__(self, run_root: Path):
        self.run_root = Path(run_root)
        super().__init__(
            f"{self.code}: another writer is already active for {self.run_root}"
        )


class WorkspaceAlreadyActiveError(RuntimeError):
    """Another run owns execution in this workspace, or is starting in it
    (``run_id`` is then None)."""

    code = "workspace_run_already_active"

    def __init__(self, workspace: Path, run_id: str | None):
        self.run_id = run_id
        self.detail = (
            f"run {run_id} is active in {workspace}"
            if run_id is not None
            else f"another run is starting in {workspace}: "
            ".orchestrate/workspace.guard is held"
        )
        super().__init__(f"{self.code}: {self.detail}")


@contextmanager
def workspace_run_lock(
    workspace: Path, run_id: str, guard_timeout: float = 5.0
) -> Iterator[None]:
    """Serialize execution; retained files carry metadata, never lock authority.

    Waits at most ``guard_timeout`` seconds for the start guard, then refuses.
    """
    root = Path(workspace) / ".orchestrate"
    root.mkdir(exist_ok=True)
    dir_fd = _open_root_no_follow(root)
    try:
        lock_fd = os.open("workspace.lock", _LOCK_OPEN_FLAGS, 0o600, dir_fd=dir_fd)
        try:
            guard_fd = os.open("workspace.guard", _LOCK_OPEN_FLAGS, 0o600, dir_fd=dir_fd)
            try:
                # Serialize acquisition and owner publication so a contender
                # cannot report the previous owner in the short publication gap.
                # Bounded, so a starter stopped inside this section cannot
                # block every later starter.
                deadline = time.monotonic() + guard_timeout
                while True:
                    try:
                        fcntl.flock(guard_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except OSError as exc:
                        if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                            raise
                        if time.monotonic() >= deadline:
                            raise WorkspaceAlreadyActiveError(workspace, None) from exc
                    time.sleep(0.01)
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                        raise
                    owner = os.pread(lock_fd, 4096, 0).decode("utf-8").strip()
                    raise WorkspaceAlreadyActiveError(workspace, owner) from exc
                os.ftruncate(lock_fd, 0)
                os.write(lock_fd, run_id.encode("utf-8"))
            finally:
                os.close(guard_fd)
            yield
        finally:
            # Do not unlink: other processes may already have opened this inode.
            os.close(lock_fd)
    finally:
        os.close(dir_fd)


class ReservedRunRootError(RuntimeError):
    """Externally reserved run root is missing, a symlink, or no longer the
    reserved identity; the caller must fail before any write."""

    code = "reserved_run_root_changed"

    def __init__(self, run_root: Path, detail: str):
        self.run_root = Path(run_root)
        super().__init__(
            f"{self.code}: reserved run root {self.run_root} {detail}"
        )


def _open_root_no_follow(run_root: Path) -> int:
    """Open a run root component-wise no-follow (absolute path required)."""
    absolute = os.path.abspath(os.fspath(run_root))
    try:
        return open_dir_no_follow(absolute)
    except LaunchFsError as exc:
        raise OSError(f"cannot open run root {run_root}: {exc}") from exc


def _acquire_flock(lock_fd: int, run_root: Path) -> None:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno not in {errno.EACCES, errno.EAGAIN}:
            raise
        raise RunAlreadyActiveError(run_root) from exc


@contextmanager
def _held_lock(lock_fd: int, run_root: Path) -> Iterator[None]:
    """Hold and release an already-open lock descriptor."""
    _acquire_flock(lock_fd, run_root)
    try:
        yield
    finally:
        fcntl.flock(lock_fd, fcntl.LOCK_UN)


def _open_lock_fd(dir_fd: int) -> int:
    return os.open("run.lock", _LOCK_OPEN_FLAGS, 0o600, dir_fd=dir_fd)


@contextmanager
def run_writer_lock(run_root: Path) -> Iterator[int]:
    """Hold the non-blocking exclusive writer lock for one run root.

    The root is opened no-follow and run.lock is created beneath that
    retained directory fd, so a root or lock-file symlink swap can never
    redirect the lock file into another directory.
    """
    root = Path(run_root)
    dir_fd = _open_root_no_follow(root)
    try:
        lock_fd = _open_lock_fd(dir_fd)
        try:
            with _held_lock(lock_fd, root):
                yield dir_fd
        finally:
            os.close(lock_fd)
    finally:
        os.close(dir_fd)


@contextmanager
def reserved_run_writer_lock(
    run_root: Path, expected_identity: tuple[int, int]
) -> Iterator[int]:
    """R7: open and identity-check an externally reserved run root no-follow
    BEFORE mkdir, lock creation, or any other write, then hold the writer
    lock beneath the retained directory authority.

    Yields the retained directory fd. Raises ``ReservedRunRootError`` when
    the root is missing, a symlink/non-directory at any component, or no
    longer the reserved identity. Because run.lock is created relative to
    the retained fd (the original directory inode), a concurrent directory
    or symlink swap can never place a file in the replacement target;
    ``run_root_matches_fd`` detects a swap before ``StateManager.initialize``.
    """
    root = Path(run_root)
    try:
        dir_fd = open_dir_no_follow(os.path.abspath(os.fspath(root)))
    except LaunchFsError as exc:
        raise ReservedRunRootError(
            root, f"cannot be opened no-follow: {exc}") from exc
    try:
        stat = os.fstat(dir_fd)
        if (stat.st_dev, stat.st_ino) != expected_identity:
            raise ReservedRunRootError(
                root,
                f"changed identity ({expected_identity} != "
                f"{(stat.st_dev, stat.st_ino)})",
            )
        try:
            lock_fd = _open_lock_fd(dir_fd)
        except OSError as exc:
            raise ReservedRunRootError(
                root, f"writer lock cannot be opened: {exc}") from exc
        try:
            with _held_lock(lock_fd, root):
                yield dir_fd
        finally:
            os.close(lock_fd)
    finally:
        os.close(dir_fd)


def run_root_matches_fd(run_root: Path, dir_fd: int) -> bool:
    """True when the run root path still resolves (no-follow) to the fd.

    Re-opens the path component-wise no-follow and compares inode identity
    with the retained directory authority, so a parent or leaf swap after
    the writer lock was taken is detected before any further path-based
    write (StateManager.initialize and friends).
    """
    try:
        check_fd = open_dir_no_follow(
            os.path.abspath(os.fspath(run_root))
        )
    except LaunchFsError:
        return False
    try:
        expected = os.fstat(dir_fd)
        actual = os.fstat(check_fd)
    finally:
        os.close(check_fd)
    return (actual.st_dev, actual.st_ino) == (expected.st_dev, expected.st_ino)


__all__ = [
    "ReservedRunRootError",
    "RunAlreadyActiveError",
    "WorkspaceAlreadyActiveError",
    "reserved_run_writer_lock",
    "run_root_matches_fd",
    "run_writer_lock",
    "workspace_run_lock",
]
