"""Cross-process coordination primitives for durable root state mutation."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import secrets
from typing import Iterator


@contextmanager
def exclusive_file_lock(path: Path) -> Iterator[None]:
    """Hold one ordinary exclusive process lock for the context lifetime."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


@contextmanager
def provider_attempt_process_locks(run_root: Path) -> Iterator[None]:
    """Acquire state then aggregate-evidence process locks in canonical order."""

    root = Path(run_root)
    evidence_root = root / "workflow_lisp" / "prompt_dependencies"
    with exclusive_file_lock(root / ".state-mutation.lock"):
        evidence_root.mkdir(parents=True, exist_ok=True)
        with exclusive_file_lock(evidence_root / ".aggregate.lock"):
            yield


@contextmanager
def record_only_publication_locks(run_root: Path) -> Iterator[None]:
    """Hold only the two process locks used by record publication."""

    with provider_attempt_process_locks(run_root):
        yield


def durable_atomic_write(path: Path, payload: bytes) -> None:
    """Replace ``path`` only after a complete, file-synced temporary write.

    Success means both the replacement and its parent-directory entry have been
    synchronized. Any failed operation is propagated to the caller.
    """

    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(
        f".{destination.name}.{os.getpid()}.{secrets.token_hex(8)}.tmp"
    )
    fd: int | None = None
    directory_fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        remaining = memoryview(payload)
        while remaining:
            written = os.write(fd, remaining)
            if written <= 0:
                raise OSError("durable state write made no progress")
            remaining = remaining[written:]
        os.fsync(fd)
        os.close(fd)
        fd = None
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(directory_fd)
    finally:
        if fd is not None:
            os.close(fd)
        if directory_fd is not None:
            os.close(directory_fd)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
