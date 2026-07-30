"""Run-lifetime process coordination for mutable workflow execution."""

from __future__ import annotations

from contextlib import contextmanager
import errno
import fcntl
from pathlib import Path
from typing import Iterator


class RunAlreadyActiveError(RuntimeError):
    """Raised when another process already owns the run writer lock."""

    code = "run_already_active"

    def __init__(self, run_root: Path):
        self.run_root = Path(run_root)
        super().__init__(
            f"{self.code}: another writer is already active for {self.run_root}"
        )


@contextmanager
def run_writer_lock(run_root: Path) -> Iterator[None]:
    """Hold the non-blocking exclusive writer lock for one run root."""

    root = Path(run_root)
    with (root / "run.lock").open("a+b") as lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno not in {errno.EACCES, errno.EAGAIN}:
                raise
            raise RunAlreadyActiveError(root) from exc
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
