"""Strict journal reduction and append-only invalidation for evaluated runs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import json
import os
from pathlib import Path
import stat
import time
from typing import Any, Iterator

from orchestrator.run_lock import RunAlreadyActiveError, run_writer_lock
from orchestrator.workflow.workspace_files import WorkspaceFiles
from .memo_reducer import (
    MemoError,
    JournalEntry,
    MemoSnapshot,
    _DYNAMIC_INDEX,
    _RECORDS,
    _implementation_files,
    _inconsistent,
    _json_value,
    reduce_memo,
)


def _read_bytes(path: Path, run_files: WorkspaceFiles | None = None) -> bytes:
    if run_files is not None:
        try:
            return run_files.read(path)
        except OSError as exc:
            raise _inconsistent(f"memo journal cannot be opened: {exc}") from exc
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except OSError as exc:
        raise _inconsistent(f"memo journal cannot be opened: {exc}") from exc
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _inconsistent("memo journal is not a regular file")
        chunks: list[bytes] = []
        while chunk := os.read(fd, 1024 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def read_memo(path: Path, site_classes: Mapping[str, str], *, run_files: WorkspaceFiles | None = None) -> MemoSnapshot:
    """Read a journal snapshot without locking, repairing, or reconciling it."""
    return reduce_memo(_read_bytes(Path(path), run_files), site_classes)


@contextmanager
def memo_writer_lock(run_root: Path) -> Iterator[int]:
    """Hold the existing run writer lock, mapping contention to the memo code."""
    lock = run_writer_lock(Path(run_root))
    try:
        fd = lock.__enter__()
    except RunAlreadyActiveError as exc:
        raise MemoError("memo_busy", str(exc)) from exc
    try:
        yield fd
    finally:
        lock.__exit__(None, None, None)


def _open_append(path: Path, run_files: WorkspaceFiles | None = None) -> int:
    flags = os.O_RDWR | os.O_APPEND | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags) if run_files is None else run_files.open_journal(path)
    except OSError as exc:
        raise _inconsistent(f"memo journal cannot be opened for append: {exc}") from exc
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise _inconsistent("memo journal is not a regular file")
    return fd


def _encode_record(record: Mapping[str, Any]) -> bytes:
    if not isinstance(record, Mapping) or not _json_value(dict(record)):
        raise _inconsistent("record is not finite JSON with string keys")
    try:
        return json.dumps(dict(record), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8") + b"\n"
    except (TypeError, ValueError, UnicodeEncodeError) as exc:
        raise _inconsistent(f"record cannot be encoded as JSON: {exc}") from exc


def _checked_writer_context(path, run_files, authority):
    from orchestrator.workflow.evaluated.authority import RunAuthority

    if not isinstance(authority, RunAuthority) or run_files is None or authority.run_files is not run_files:
        raise _inconsistent("publication requires checked authority and its retained file owner")
    if path != authority.memo_path or run_files.workspace != authority.run_root:
        raise _inconsistent("publication authority and journal root disagree")


def append_record(path: Path, record: Mapping[str, Any], *, run_files: WorkspaceFiles | None = None,
                  checked_authority=None) -> JournalEntry:
    """Sync one row and publish its view when supplied the checked writer context.

    All production callers carry this context; raw synthetic journal tests do not.
    """
    path = Path(path)
    if checked_authority is not None:
        _checked_writer_context(path, run_files, checked_authority)
    encoded = _encode_record(record)
    kind = record.get("record")
    if not isinstance(kind, str) or kind not in _RECORDS:
        raise _inconsistent("record kind is missing or unknown")
    if kind in {"started", "committed"}:
        _implementation_files(record.get("implementation_files"))
    fd = _open_append(path, run_files)
    start = os.fstat(fd).st_size
    try:
        if start and os.pread(fd, 1, start - 1) != b"\n":
            raise MemoError("memo_torn_tail", "writer must repair the tail after preflight")
        try:
            written = os.write(fd, encoded)
        except OSError as exc:
            raise MemoError("memo_write_failed", str(exc)) from exc
        if written != len(encoded):
            raise MemoError("memo_write_failed", "journal append was shorter than one record")
        try:
            os.fsync(fd)
        except OSError as exc:
            # A complete row that survives a failed sync consumes its ordinal.
            raise MemoError("memo_sync_failed", str(exc)) from exc
    finally:
        os.close(fd)
    entry = JournalEntry(start, start + len(encoded), dict(record))
    if checked_authority is not None:
        from orchestrator.workflow.evaluated.views import publish_evaluated_view
        publish_evaluated_view(checked_authority, entry)
    return entry


def repair_torn_tail(path: Path, snapshot: MemoSnapshot, *, run_files: WorkspaceFiles | None = None) -> None:
    """Discard only a previously read incomplete suffix; caller owns the lock and completed preflight."""
    if not snapshot.tail:
        return
    path = Path(path)
    fd = _open_append(path, run_files)
    try:
        size = os.fstat(fd).st_size
        current = os.pread(fd, size, 0)
        if current != snapshot.raw or size != len(snapshot.raw):
            raise MemoError("memo_changed", "journal differs from the preflight snapshot")
        os.ftruncate(fd, snapshot.complete_bytes)
        os.fsync(fd)
    except OSError as exc:
        raise MemoError("memo_write_failed", str(exc)) from exc
    finally:
        os.close(fd)


def invalidate_suffix(path: Path, identity: str, site_classes: Mapping[str, str], *, run_files: WorkspaceFiles | None = None,
                      checked_authority=None) -> dict[str, Any]:
    """Append one C8 range after validating its active commit suffix; caller owns the lock."""
    path = Path(path)
    snapshot = read_memo(path, site_classes, run_files=run_files)
    chosen = snapshot.active_commits.get(identity)
    if chosen is None:
        raise MemoError("invalidate_not_committed", identity)
    suffix = [item for item in snapshot.active_commits.values() if item.offset >= chosen.offset]
    if any(item.data["effect_class"] == "run_ref" for item in suffix):
        raise MemoError("invalidate_coordinator_committed", identity)
    if snapshot.tail:
        repair_torn_tail(path, snapshot, run_files=run_files)
    row = {"record": "invalidated", "from_commit": chosen.offset, "time": time.time()}
    append_record(path, row, run_files=run_files, checked_authority=checked_authority)
    return row
