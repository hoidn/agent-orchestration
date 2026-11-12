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
    is_coordinator_class,
    reduce_memo,
)
from .memo_reducer_lineage import current_program_digest, lineage_digests, rebased_records


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
    """Read a journal snapshot without locking, repairing, or reconciling it.

    `site_classes` is the current program's table. A journal with `rebased` records is reduced with the tables of
    the earlier programs too, each from the artifact beside the journal, verified to its name (C10).
    """
    path = Path(path)
    raw = _read_bytes(path, run_files)
    records = rebased_records(raw, _unscanned(raw))
    if not records:
        return reduce_memo(raw, site_classes)
    return reduce_memo(raw, site_classes, _lineage_tables(path.parent, records, site_classes, run_files))


def _unscanned(raw: bytes) -> int:
    """Where a `rebased` record can begin: after the process's last fold, when that fold met none.

    `read_memo` runs at every effect start; without this, a run that never switched program would rescan its whole
    journal each time. The fold reduced exactly `cached[1]`, and any record there is in its `record_offsets`.
    """
    from . import memo_reducer
    cached = memo_reducer._LAST
    if cached is not None and not cached[0].record_offsets and raw.startswith(cached[1]):
        return len(cached[1])
    return 0


# A program's site table is a pure function of its verified digest. Each run root verifies its own copy once per
# process (key: run root, digest), so a second run root in the same process (the REPL) never borrows another's
# check. Process state like `memo_reducer._LAST`: tests reset both (tests/memo_fold_guard.py).
_TABLES: dict[tuple[str, str], dict[str, str]] = {}


def _site_table(root: Path, digest: str, load) -> dict[str, str]:
    key = (os.fspath(root), digest)
    if key not in _TABLES:
        from .machine import site_classes
        _TABLES[key] = site_classes(load())
    return _TABLES[key]


def _lineage_tables(root: Path, records, site_classes, run_files) -> tuple[dict[str, str], ...]:
    """The earlier programs' tables; the last record must name the caller's program (compared by table)."""
    from .authority import PROGRAM_FILENAME, _read_file, load_run_header, verified_program

    header_digest = load_run_header(root, run_files=run_files)["program_digest"]
    digests = lineage_digests(header_digest, [digest for _offset, digest in records])
    read = lambda name: _read_file(root / name, run_files)  # noqa: E731
    first = lambda: verified_program(read, header_digest, PROGRAM_FILENAME)  # noqa: E731
    tables = [_site_table(root, digests[0], first),
              *(_site_table(root, digest, lambda d=digest: verified_program(read, d)) for digest in digests[1:])]
    if tables[-1] != dict(site_classes):
        raise _inconsistent("journal's rebased records do not end at the caller's program")
    return tuple(tables[:-1])


def remember_tables(authority) -> None:
    """Record the site table of every program a checked authority verified, so that `read_memo` of its run root
    never parses those artifacts again in this process (the loader already did)."""
    _site_table(authority.run_root, authority.program.digest, lambda: authority.program)
    earlier_tables(authority)


def current_digest(run_root: Path, header_digest: str, *, run_files: WorkspaceFiles | None = None) -> str:
    """Resume step 7: the run's current program, from the journal's complete `rebased` records only (C10)."""
    return current_program_digest(_read_bytes(Path(run_root) / "memo.jsonl", run_files), header_digest)


def earlier_tables(authority) -> tuple[dict[str, str], ...]:
    """Site tables of a checked authority's earlier programs, for a direct reduction of bytes it captured."""
    return tuple(_site_table(authority.run_root, program.digest, lambda p=program: p) for program, _end in authority.earlier)


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
                  checked_authority=None, start_reached=False) -> JournalEntry:
    """Sync one row and publish its view when supplied the checked writer context.

    All production callers carry this context; raw synthetic journal tests do not.
    ``start_reached`` is passed to ``publish_evaluated_view``.
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
        publish_evaluated_view(checked_authority, entry, start_reached=start_reached)
        if checked_authority.observer is not None:
            checked_authority.observer(entry.data)
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


def _uncommitted_state(snapshot: MemoSnapshot, identity: str) -> str | None:
    """`pending`, `failed` (its latest attempt), `invalidated` (committed once, now cancelled) or None (unknown)."""
    if identity in snapshot.pending_starts:
        return "pending"
    latest = snapshot.latest_starts.get(identity)
    if latest is None:
        return None
    rows = [entry.data for entry in snapshot.entries if entry.data.get("identity") == identity]
    if any(row["record"] == "failed" and row.get("attempt") == latest.data["attempt"] for row in rows):
        return "failed"
    return "invalidated" if any(row["record"] == "committed" for row in rows) else None


def invalidate_suffix(path: Path, identity: str, site_classes: Mapping[str, str], *, run_files: WorkspaceFiles | None = None,
                      checked_authority=None) -> dict[str, Any]:
    """Append one C8 range after validating its active commit suffix; caller owns the lock."""
    path = Path(path)
    snapshot = read_memo(path, site_classes, run_files=run_files)
    chosen = snapshot.active_commits.get(identity)
    if chosen is None:
        error = MemoError("invalidate_not_committed", identity)
        error.identity, error.committed = identity, list(snapshot.active_commits)
        error.state = _uncommitted_state(snapshot, identity)
        raise error
    suffix = [item for item in snapshot.active_commits.values() if item.offset >= chosen.offset]
    coordinators = [item.data["identity"] for item in suffix if is_coordinator_class(item.data["effect_class"])]
    if coordinators:
        error = MemoError("invalidate_coordinator_committed", identity)
        error.coordinators = coordinators
        raise error
    if checked_authority is not None:
        from .run_ref import guard_confined_invalidation
        guard_confined_invalidation(checked_authority, snapshot, chosen.offset)
    from .agent_guards import check_invalidation_suffix
    check_invalidation_suffix(snapshot, chosen, run_files)     # receipt-aware agent history, before any write
    if snapshot.tail:
        repair_torn_tail(path, snapshot, run_files=run_files)
    row = {"record": "invalidated", "from_commit": chosen.offset, "time": time.time()}
    append_record(path, row, run_files=run_files, checked_authority=checked_authority)
    return row
