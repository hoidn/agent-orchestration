"""The effect memo (design section 7): an append-only journal under the run root, with one writer.

Each record is one JSON line, flushed and synchronized to disk before `append`
returns. Records of an effect: `started`, `committed`, `failed`, `suspended`,
`settled` (a coordinator's final commit, or its reconciliation, is done) and
`invalidated` (its commit no longer counts; the next resume runs it again). A
result exists only as a `committed` record that no later `invalidated` record
cancels. The run's own record, `terminal`, has no identity: written last, after
every settlement, it says the run completed or failed; any record after it
means the run went on.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

MEMO_FILE = "memo.jsonl"


class MemoBusy(RuntimeError):
    """Another writer holds the memo."""


@dataclass
class Entry:
    """What the memo holds for one identity."""

    attempts: list[int] = field(default_factory=list)
    committed: dict[str, Any] | None = None
    suspended: dict[str, Any] | None = None
    failed: dict[str, Any] | None = None
    settled: bool = False
    invalidated: bool = False  # the last attempt was committed, then invalidated: a rerun was asked for


def read_records(run_root: Path) -> list[dict[str, Any]]:
    """Every complete record. A final line without its newline was never written in full, and is not one."""

    path = run_root / MEMO_FILE
    if not path.exists():
        return []
    lines = path.read_bytes().split(b"\n")
    return [json.loads(line) for line in lines[:-1]]


class Memo:
    def __init__(self, run_root: Path) -> None:
        self.path = run_root / MEMO_FILE
        self.entries: dict[str, Entry] = {}
        self._file = None

    def __enter__(self) -> "Memo":
        self._file = open(self.path, "ab+")
        try:
            fcntl.flock(self._file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self._file.close()
            raise MemoBusy(f"the memo {self.path} has another writer") from exc
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            # A record torn by a crash was never synchronized whole; drop it before appending.
            self._file.truncate(data.rfind(b"\n") + 1)
        for record in read_records(self.path.parent):
            self._index(record)
        return self

    def __exit__(self, *_exc: object) -> None:
        self._file.close()

    def entry(self, identity: str) -> Entry:
        return self.entries.get(identity, Entry())

    def append(self, record: dict[str, Any]) -> None:
        record = {**record, "time": time.time()}
        line = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
        self._file.write(line.encode("utf-8") + b"\n")
        self._file.flush()
        os.fsync(self._file.fileno())
        self._index(record)

    def _index(self, record: dict[str, Any]) -> None:
        if "identity" not in record:  # the run's `terminal` record
            return
        entry = self.entries.setdefault(record["identity"], Entry())
        kind = record["record"]
        if kind == "started":
            entry.attempts.append(record["attempt"])
            entry.invalidated = False
        elif kind == "committed":
            entry.committed, entry.settled = record, False
        elif kind == "suspended":
            entry.suspended = record
        elif kind == "failed":
            entry.failed = record
        elif kind == "settled":
            entry.settled = True
        elif kind == "invalidated":
            entry.committed, entry.suspended, entry.settled, entry.invalidated = None, None, False, True


class MemoSnapshot(Memo):
    """The memo as a reader sees it: indexed, not locked, never written. A view reads a run in progress this way."""

    def __init__(self, run_root: Path) -> None:
        super().__init__(run_root)
        for record in read_records(run_root):
            self._index(record)

    def append(self, record: dict[str, Any]) -> None:
        raise RuntimeError("a memo snapshot is not written")

    def writer_alive(self) -> bool:
        """Whether a writer holds the memo: a process that died released its lock."""

        with open(self.path, "rb") as memo:
            try:
                fcntl.flock(memo.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(memo.fileno(), fcntl.LOCK_UN)
            return False


def answer(run_root: Path, identity: str, text: str) -> None:
    """The answer command of a request for input: commits the reply of a suspended effect."""

    with Memo(run_root) as memo:
        entry = memo.entry(identity)
        if entry.suspended is None or entry.committed is not None:
            raise ValueError(f"no pending request at `{identity}`")
        value = {"variant": "ANSWERED", "text": text}
        memo.append({"record": "committed", "identity": identity, "attempt": entry.suspended["attempt"],
                     "input_digest": entry.suspended["input_digest"], "value": value,
                     "depends_on": entry.suspended.get("depends_on", [])})
