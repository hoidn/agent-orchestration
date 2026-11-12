"""The `rebased` record (C10): a journal read row by row under the program that wrote each row.

A row's program is the number of complete `rebased` records before it. The reducer holds the site tables of the
run's programs in lineage order (the first program's, then one per record) and moves to the next table at each
record. `Lineage.class_at` answers for any historical row by the row's own offset, never by its identity's latest
row: an identity can change class across a record.

Depends on: `memo_reducer` (row validators) and `memo_reducer_agents` (the agent rule of C8). Pure, except that
`verified_program` reads an artifact through the caller's `read_artifact(name) -> bytes`. No command writes the
record yet (Phase 3b T7); readers accept a journal that holds one.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from . import memo_reducer_agents as agents
from .memo_reducer import (
    _CLASSES, _DYNAMIC_INDEX, _decode_line, _digest, _finite_time, _inconsistent, _shape, is_coordinator_class,
)

_FIELDS = {"record", "program_digest", "from_offset", "time"}


def _class_in(table: Mapping[str, str], identity: str) -> str | None:
    return table.get(identity) or table.get(_DYNAMIC_INDEX.sub("[*]", identity))


def class_at(tables, record_offsets, offset: int, identity: str) -> str:
    """The class of the row at `offset`: its identity in the table of the program in force when it was written."""
    kind = _class_in(tables[bisect.bisect_right(record_offsets, offset)], identity)
    if kind not in _CLASSES:
        raise _inconsistent(f"identity does not resolve to a checked effect site: {identity}")
    return kind


@dataclass(frozen=True, slots=True)
class Lineage:
    """Site tables in lineage order and the offsets of the `rebased` records between them."""

    tables: tuple[Mapping[str, str], ...]
    record_offsets: tuple[int, ...]

    def class_at(self, offset: int, identity: str) -> str:
        # One frame: views call this once per identity per published view.
        table = self.tables[bisect.bisect_right(self.record_offsets, offset)] if self.record_offsets else self.tables[0]
        kind = table.get(identity) or table.get(_DYNAMIC_INDEX.sub("[*]", identity))
        if kind not in _CLASSES:
            raise _inconsistent(f"identity does not resolve to a checked effect site: {identity}")
        return kind

    def keeps_class(self, offset: int, identity: str) -> bool:
        """Whether the row at `offset` has the class the last program gives its identity (none: False)."""
        return not self.record_offsets or self.class_at(offset, identity) == _class_in(self.tables[-1], identity)


def checked_tables(site_classes: Mapping[str, str], earlier) -> tuple[dict[str, str], ...]:
    """The earlier programs' tables in order, then the caller's (the current program's), each well formed."""
    tables = (*earlier, site_classes)
    if any(not isinstance(table, Mapping) or any(
            not isinstance(site, str) or not site or not isinstance(kind, str) or kind not in _CLASSES
            for site, kind in table.items()) for table in tables):
        raise _inconsistent("checked site table is malformed")
    return tuple(dict(table) for table in tables)


def fold_continues(cached, reducer) -> bool:
    """A saved fold continues only under the very tables it was folded with, at the same positions."""
    used = len(cached.record_offsets) + 1
    return reducer.tables[:used] == cached.tables[:used]


def apply_rebased(reducer, entry) -> None:
    """Check the cut with every row read under its own program, apply it as a C8 range does, then switch tables."""
    row = entry.data
    _shape(row, _FIELDS)
    _digest(row["program_digest"], "program_digest")
    _finite_time(row["time"])
    index = len(reducer.record_offsets) + 1
    if index >= len(reducer.tables):
        raise _inconsistent("rebased record names a program whose site table was not supplied")
    cut = row["from_offset"]
    if cut is not None:
        _check_cut(reducer, cut)
        reducer.active = {identity: item for identity, item in reducer.active.items() if item.offset < cut}
        reducer.pending = {identity: item for identity, item in reducer.pending.items() if item.offset < cut}
        reducer.suspensions = {i: item for i, item in reducer.suspensions.items() if i in reducer.pending}
    reducer.record_offsets.append(entry.offset)
    reducer.site_classes = reducer.tables[index]
    for identity, kept in (*reducer.active.items(), *reducer.pending.items()):
        if _class_in(reducer.site_classes, identity) != reducer.class_at(kept.offset, identity):
            raise _inconsistent(f"kept effect is not a site of the new program with the same class: {identity}")
    reducer.terminal = None


def _check_cut(reducer, cut) -> None:
    kept = (*reducer.active.values(), *reducer.pending.values())
    if type(cut) is not int or not any(item.offset == cut for item in kept):
        raise _inconsistent("rebased cut is neither an active commit nor a pending start")
    if any(item.offset >= cut and is_coordinator_class(item.data["effect_class"]) for item in reducer.active.values()):
        raise _inconsistent("rebased cut covers a committed coordinator")
    agents.check_invalidation_cut(reducer, cut)


def rebased_records(raw: bytes, start: int = 0) -> list[tuple[int, str]]:
    """(offset, program digest) of each complete `rebased` record from byte `start` on, in journal order.

    Only lines holding the text `rebased` are decoded, so a journal without it costs one scan; a torn tail is not a
    record (M3). The digest is checked before any caller turns it into a file name. A caller passes `start` only
    when it knows the bytes before it hold no record.
    """
    records, at = [], raw.find(b"rebased", start)
    while at != -1:
        start, end = raw.rfind(b"\n", 0, at) + 1, raw.find(b"\n", at)
        if end == -1:
            break
        row = _decode_line(raw[start:end + 1], start)
        if row.get("record") == "rebased":
            records.append((start, _digest(row.get("program_digest"), "program_digest")))
        at = raw.find(b"rebased", end)
    return records


def lineage_digests(header_digest: str, named: list[str]) -> list[str]:
    """The first program's digest, then each record's; a record naming the program in force is refused."""
    digests = [header_digest]
    for digest in named:
        if digest == digests[-1]:
            raise _inconsistent("rebased record names the program already in force")
        digests.append(digest)
    return digests


def current_program_digest(raw: bytes, header_digest: str) -> str:
    """The run's current program: the one the last complete `rebased` record names, else the header's."""
    return lineage_digests(header_digest, [digest for _offset, digest in rebased_records(raw)])[-1]


def program_artifact_name(digest: str) -> str:
    return f"closed_program.{digest.removeprefix('sha256:')}.json"


def verified_program(read_artifact: Callable[[str], bytes], digest: str, name: str | None = None):
    """The checked program stored under `name` (default: `digest`'s artifact name) with that digest.

    Missing, unloadable or another digest: `memo_inconsistent`; nothing is rebuilt from source.
    """
    from orchestrator.contracts.closed_program.program import ClosedProgram

    name = program_artifact_name(digest) if name is None else name
    try:
        program = ClosedProgram.from_artifact(read_artifact(name).decode("utf-8"))
    except (OSError, UnicodeError, TypeError, ValueError, RecursionError) as exc:
        raise _inconsistent(f"program artifact {name} is missing or does not load: {exc}") from exc
    if program.digest != digest:
        raise _inconsistent(f"program artifact {name} does not have the digest that names it")
    return program
