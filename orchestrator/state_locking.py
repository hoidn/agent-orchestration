"""Shared durable atomic-write primitive."""

from __future__ import annotations

import os
from pathlib import Path
import secrets


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
