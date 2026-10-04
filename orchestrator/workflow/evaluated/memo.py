"""Strict journal reduction and append-only invalidation for evaluated runs."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Iterator

from orchestrator.run_lock import RunAlreadyActiveError, run_writer_lock
from orchestrator.workflow.evaluated.closure_evidence import validate_implementation_evidence
from orchestrator.workflow.workspace_files import WorkspaceFiles

_RECORDS = {"started", "committed", "failed", "suspended", "settled", "invalidated", "terminal"}
_CLASSES = {"command", "provider", "run_ref"}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_DYNAMIC_INDEX = re.compile(r"\[(?:0|[1-9][0-9]*)\]")


class MemoError(ValueError):
    """A memo refusal with the diagnostic code consumed by evaluated callers."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class JournalEntry:
    offset: int
    end: int
    data: dict[str, Any]


@dataclass(frozen=True, slots=True)
class MemoSnapshot:
    raw: bytes
    complete_bytes: int
    tail: bytes
    entries: tuple[JournalEntry, ...]
    active_commits: dict[str, JournalEntry]
    latest_starts: dict[str, JournalEntry]
    pending_starts: dict[str, JournalEntry]
    settlements: frozenset[tuple[str, int]]
    unsettled_coordinators: dict[tuple[str, int], JournalEntry]
    terminal: JournalEntry | None


def _inconsistent(detail: str) -> MemoError:
    return MemoError("memo_inconsistent", detail)


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    row: dict[str, Any] = {}
    for key, value in pairs:
        if key in row:
            raise ValueError(f"duplicate JSON key {key!r}")
        row[key] = value
    return row


def _reject_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _json_value(value: Any) -> bool:
    if value is None or type(value) in {str, bool, int}:
        return True
    if type(value) is float:
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(type(key) is str and _json_value(item) for key, item in value.items())
    return False


def _decode_line(raw: bytes, offset: int) -> dict[str, Any]:
    try:
        row = json.loads(
            raw[:-1].decode("utf-8"),
            object_pairs_hook=_reject_duplicates,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise _inconsistent(f"invalid JSON line at byte {offset}: {exc}") from exc
    if not isinstance(row, dict) or not _json_value(row):
        raise _inconsistent(f"record at byte {offset} is not a finite JSON object")
    return row


def _shape(row: dict[str, Any], required: set[str], optional: set[str] = frozenset()) -> None:
    keys = set(row)
    if not required <= keys or keys - required - optional:
        raise _inconsistent("record has missing or unknown fields")


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or "\0" in value:
        raise _inconsistent(f"{field} must be non-empty NUL-free text")
    return value


def _ordinal(value: Any) -> int:
    if type(value) is not int or value < 1:
        raise _inconsistent("attempt must be a positive integer")
    return value


def _digest(value: Any, field: str) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise _inconsistent(f"{field} must be a canonical sha256 digest")
    return value


def _finite_time(value: Any) -> None:
    if type(value) is int:
        return
    if type(value) is not float or not math.isfinite(value):
        raise _inconsistent("time must be a finite number")


def _object(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not _json_value(value):
        raise _inconsistent(f"{field} must be a finite JSON object with string keys")
    return value


def _implementation_files(value: Any) -> None:
    try:
        validate_implementation_evidence(value)
    except (TypeError, ValueError) as exc:
        raise _inconsistent(str(exc)) from exc


class _Reducer:
    def __init__(self, site_classes: Mapping[str, str]) -> None:
        if not isinstance(site_classes, Mapping) or any(
            not isinstance(site, str) or not site or not isinstance(kind, str) or kind not in _CLASSES
            for site, kind in site_classes.items()
        ):
            raise _inconsistent("checked site table is malformed")
        self.site_classes = dict(site_classes)
        self.entries: list[JournalEntry] = []
        self.active: dict[str, JournalEntry] = {}
        self.latest: dict[str, JournalEntry] = {}
        self.pending: dict[str, JournalEntry] = {}
        self.settlements: set[tuple[str, int]] = set()
        self.unsettled: dict[tuple[str, int], JournalEntry] = {}
        self.terminal: JournalEntry | None = None
        self.next_ordinal: dict[str, int] = {}

    def reduce(self, raw: bytes) -> MemoSnapshot:
        complete_bytes = raw.rfind(b"\n") + 1
        complete, tail = raw[:complete_bytes], raw[complete_bytes:]
        offset = 0
        for record in complete.split(b"\n")[:-1]:
            line = record + b"\n"
            data = _decode_line(line, offset)
            entry = JournalEntry(offset, offset + len(line), data)
            self.accept(entry)
            self.entries.append(entry)
            offset = entry.end
        return MemoSnapshot(
            raw,
            complete_bytes,
            tail,
            tuple(self.entries),
            dict(self.active),
            dict(self.latest),
            dict(self.pending),
            frozenset(self.settlements),
            dict(self.unsettled),
            self.terminal,
        )

    def accept(self, entry: JournalEntry) -> None:
        row = entry.data
        kind = row.get("record")
        if not isinstance(kind, str) or kind not in _RECORDS:
            raise _inconsistent("record kind is missing or unknown")
        if self.terminal is not None and kind not in {"started", "invalidated"}:
            raise _inconsistent("record follows a terminal without reopening it")
        handlers = {
            "started": self.started,
            "committed": self.committed,
            "failed": self.failed,
            "suspended": self.suspended,
            "settled": self.settled,
            "invalidated": self.invalidated,
            "terminal": self.finish,
        }
        handlers[kind](entry)

    def identity_attempt(self, row: dict[str, Any]) -> tuple[str, int, str]:
        identity = _text(row.get("identity"), "identity")
        attempt = _ordinal(row.get("attempt"))
        return identity, attempt, self.site_class(identity)

    def site_class(self, identity: str) -> str:
        if "[*]" in identity:
            raise _inconsistent("identity contains an uninstantiated checked-site wildcard")
        kind = self.site_classes.get(identity)
        if kind is None:
            kind = self.site_classes.get(_DYNAMIC_INDEX.sub("[*]", identity))
        if kind not in _CLASSES:
            raise _inconsistent(f"identity does not resolve to a checked effect site: {identity}")
        return kind

    def started(self, entry: JournalEntry) -> None:
        row = entry.data
        _shape(row, {"record", "identity", "attempt", "input_digest", "input_parts", "implementation_files", "result_path", "time"})
        identity, attempt, _ = self.identity_attempt(row)
        expected = self.next_ordinal.get(identity, 1)
        if attempt != expected or identity in self.active:
            raise _inconsistent("started attempt ordinal is not the next available ordinal")
        if self.terminal is not None and self.terminal.data.get("outcome") != "failed":
            raise _inconsistent("a completed terminal cannot be reopened by started")
        _digest(row["input_digest"], "input_digest")
        self._parts(row["input_parts"])
        _implementation_files(row["implementation_files"])
        _text(row["result_path"], "result_path")
        _finite_time(row["time"])
        self.next_ordinal[identity] = attempt + 1
        self.latest[identity] = entry
        # A new ordinal is the durable retry boundary even if the last start tore
        # only after its complete row reached the journal.
        self.pending[identity] = entry
        self.terminal = None

    def _parts(self, value: Any) -> dict[str, str]:
        parts = _object(value, "input_parts")
        for name, digest in parts.items():
            _text(name, "input part name")
            _digest(digest, f"input_parts.{name}")
        return parts

    def committed(self, entry: JournalEntry) -> None:
        row = entry.data
        _shape(row, {"record", "identity", "attempt", "input_digest", "input_parts", "value", "result_path", "result_digest", "implementation_files", "depends_on", "effect_class", "time"}, {"proof"})
        identity, attempt, expected_class = self.identity_attempt(row)
        started = self.pending.get(identity)
        if started is None or started.data["attempt"] != attempt:
            raise _inconsistent("committed record has no matching started attempt")
        self._same_input(started.data, row)
        _digest(row["input_digest"], "input_digest")
        self._parts(row["input_parts"])
        _implementation_files(row["implementation_files"])
        _text(row["result_path"], "result_path")
        _digest(row["result_digest"], "result_digest")
        _finite_time(row["time"])
        if not _json_value(row["value"]):
            raise _inconsistent("committed value is not finite JSON")
        self._dependencies(identity, row["depends_on"])
        if row["effect_class"] != expected_class:
            raise _inconsistent("effect class disagrees with the checked site")
        if expected_class == "run_ref":
            self._proof(row.get("proof"), identity)
            self.unsettled[(identity, attempt)] = entry
        elif "proof" in row:
            raise _inconsistent("ordinary effect cannot carry coordinator proof")
        if identity in self.active:
            raise _inconsistent("effect identity already has an active commit")
        self.active[identity] = entry
        self.pending.pop(identity)

    def _same_input(self, started: dict[str, Any], committed: dict[str, Any]) -> None:
        fields = ("input_digest", "input_parts", "implementation_files", "result_path")
        if any(started[field] != committed[field] for field in fields):
            raise _inconsistent("committed evidence disagrees with its started reservation")

    def _dependencies(self, identity: str, value: Any) -> None:
        if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
            raise _inconsistent("depends_on must be an array of effect identities")
        if len(set(value)) != len(value) or identity in value:
            raise _inconsistent("depends_on contains a duplicate or self dependency")
        for dependency in value:
            self.site_class(dependency)
            if dependency not in self.active:
                raise _inconsistent("depends_on names an effect without an active commit")

    def _proof(self, value: Any, identity: str) -> None:
        proof = _object(value, "coordinator proof")
        if set(proof) != {"settled_result", "artifacts"}:
            raise _inconsistent("coordinator proof must contain settled_result and artifacts")
        artifacts = _object(proof["artifacts"], "coordinator artifacts")
        if not _json_value(artifacts):
            raise _inconsistent("coordinator artifacts are not finite JSON")
        try:
            from orchestrator.workflow.run_ref.contracts import canonical_sha256
            from orchestrator.workflow.run_ref.ledger import settled_result_binding_from_record

            settled = settled_result_binding_from_record(proof["settled_result"])
        except (TypeError, ValueError, OSError) as exc:
            raise _inconsistent(f"coordinator settled result is malformed: {exc}") from exc
        expected_step = f"root.{canonical_sha256(identity).removeprefix('sha256:')}"
        visit = settled.visit
        if (visit.execution_frame_id, visit.call_frame_id, visit.step_id, visit.visit_count) != (
            "root", None, expected_step, 1
        ):
            raise _inconsistent("coordinator proof is not bound to this checked effect identity")

    def failed(self, entry: JournalEntry) -> None:
        row = entry.data
        _shape(row, {"record", "identity", "attempt", "code", "exit_info"}, {"violations"})
        identity, attempt, _ = self.identity_attempt(row)
        self._pending_attempt(identity, attempt)
        _text(row["code"], "failure code")
        _object(row["exit_info"], "exit_info")
        if "violations" in row and not isinstance(row["violations"], list):
            raise _inconsistent("violations must be an array")
        self.pending.pop(identity)

    def suspended(self, _entry: JournalEntry) -> None:
        raise _inconsistent("suspended effects are not admitted by this profile")

    def _pending_attempt(self, identity: str, attempt: int) -> JournalEntry:
        started = self.pending.get(identity)
        if started is None or started.data["attempt"] != attempt:
            raise _inconsistent("record has no matching started attempt")
        return started

    def settled(self, entry: JournalEntry) -> None:
        row = entry.data
        _shape(row, {"record", "identity", "attempt", "by"})
        identity, attempt, kind = self.identity_attempt(row)
        key = (identity, attempt)
        commit = self.active.get(identity)
        if kind != "run_ref" or commit is None or commit.data["attempt"] != attempt or key not in self.unsettled:
            raise _inconsistent("settled record does not match one unsettled coordinator commit")
        if not isinstance(row["by"], str) or row["by"] not in {"settle", "reconcile"}:
            raise _inconsistent("settled.by must be settle or reconcile")
        self.unsettled.pop(key)
        self.settlements.add(key)

    def invalidated(self, entry: JournalEntry) -> None:
        row = entry.data
        _shape(row, {"record", "from_commit", "time"})
        anchor = row["from_commit"]
        if type(anchor) is not int or anchor < 0:
            raise _inconsistent("from_commit must be a non-negative byte offset")
        _finite_time(row["time"])
        self._check_invalidation(anchor)
        self.active = {identity: item for identity, item in self.active.items() if item.offset < anchor}
        self.terminal = None

    def _check_invalidation(self, anchor: int) -> None:
        if not any(item.offset == anchor for item in self.active.values()):
            raise _inconsistent("invalidation anchor is not an active commit")
        if any(item.offset >= anchor and item.data["effect_class"] == "run_ref" for item in self.active.values()):
            raise _inconsistent("invalidation range contains a committed coordinator")

    def finish(self, entry: JournalEntry) -> None:
        row = entry.data
        outcome = row.get("outcome")
        if outcome == "completed":
            _shape(row, {"record", "outcome", "value"})
            if not _json_value(row["value"]):
                raise _inconsistent("terminal value is not finite JSON")
        elif outcome == "failed":
            _shape(row, {"record", "outcome", "code", "message"})
            _text(row["code"], "terminal code")
            _text(row["message"], "terminal message")
        else:
            raise _inconsistent("terminal outcome must be completed or failed")
        if self.pending or self.unsettled:
            raise _inconsistent("terminal leaves an attempt or coordinator unsettled")
        if self.terminal is not None:
            raise _inconsistent("adjacent terminal records are inconsistent")
        self.terminal = entry


def reduce_memo(raw: bytes, site_classes: Mapping[str, str]) -> MemoSnapshot:
    """Reduce complete newline-terminated records without touching journal bytes."""
    if not isinstance(raw, bytes):
        raise TypeError("raw memo must be bytes")
    return _Reducer(site_classes).reduce(raw)


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
