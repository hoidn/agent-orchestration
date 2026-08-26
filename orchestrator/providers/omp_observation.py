"""Close-time settlement, topology, hub, worktree, and manifest observation (X5/X8).

Consumes already-parsed journals (``omp_session``) and already-built
session-tree manifests and enforces the X5/X8 close-time contract: exactly one
settled direct primary selected by the stdout session id, every discovered
journal valid and settled, advisor/child/hub predicates, recognized-preset
topology counts, isolated child worktree cleanup, and frozen-snapshot versus
live session-manifest equality (modes stay recorded actual and may differ).
Safe-tree rejections and parse failures fail closed as ``OmpObservationError``.
"""
from __future__ import annotations

import functools
import hashlib
import os
import re
from dataclasses import dataclass

from .._common.safe_tree import SafeTreeError, read_regular_file, walk_regular_files
from .omp_launch_fs import PRIMARY_HASH_LIMIT
from .omp_session import OmpSessionError, ParsedJournal, parse_journal_bytes, validate_session_graph

_ADVISOR_JSONL = "__advisor.jsonl"
_ADVISOR_PREFIX = "__advisor."
_ADVISOR_SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_MAX_JOURNAL_FILES = 1024
_MAX_JOURNAL_BYTES = PRIMARY_HASH_LIMIT
SESSION_TREE_MAX_FILES = 2048
SESSION_TREE_MAX_BYTES = PRIMARY_HASH_LIMIT
SESSION_TREE_MAX_DEPTH = 64


class OmpObservationError(Exception):
    """A persisted session failed a close-time observation contract."""


@dataclass(frozen=True, slots=True)
class ExpectedTopology:
    """Exact counts a recognized preset requires at close."""

    advisor: int = 0
    child: int = 0
    hub_matched: bool = False


@dataclass(frozen=True, slots=True)
class ObservationReport:
    """Observed classification of one session at close."""

    primary_relpath: str
    primary_sha256: str
    advisor_relpaths: tuple[str, ...]
    child_relpaths: tuple[str, ...]
    hub_matched: bool
    unrecognized: bool


PRESET_TOPOLOGIES = {
    "neutral": ExpectedTopology(),
    "advised": ExpectedTopology(advisor=1),
    "fanout": ExpectedTopology(child=2),
    "peer-team": ExpectedTopology(child=2, hub_matched=True),
    "advised-fanout": ExpectedTopology(advisor=1, child=2),
}


@functools.lru_cache(maxsize=1)
def recognized_preset_topologies() -> dict[str, ExpectedTopology]:
    """One code-owned topology authority keyed by canonical packaged-conf digest.

    Computes the content-addressed manifest digest of each packaged preset
    conf (``orchestrator.omp_assets.confs.<name>``) and binds its exact X5
    expected counts. Preset labels and filesystem paths never select or
    change the counts: a renamed or copied packaged conf resolves the same
    digest and therefore the same topology; a substituted label is simply
    absent from this map and selects no counts.
    """
    from ..omp_assets import preset_conf_root
    from .omp_conf import admit_conf_tree

    result: dict[str, ExpectedTopology] = {}
    for name, topology in PRESET_TOPOLOGIES.items():
        descriptor = os.open(
            preset_conf_root(name), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            result[admit_conf_tree(descriptor).manifest_sha256] = topology
        finally:
            os.close(descriptor)
    return result


def compare_session_manifests(snapshot, live) -> bool:
    """Refuse missing/extra/type-swapped/byte drift between frozen and live manifests.

    Both inputs expose ``rows`` of records with ``relative_path``/``sha256``/
    ``size_bytes`` (``omp_session_manifest.SessionManifest`` qualifies). Modes stay
    recorded actual on each side and are not compared. Returns True when
    membership and content are identical; any drift raises OmpObservationError.
    """
    snapshot_paths = [row.relative_path for row in snapshot.rows]
    live_paths = [row.relative_path for row in live.rows]
    if snapshot_paths != live_paths:
        raise OmpObservationError("live session manifest membership differs from the frozen snapshot")
    for snapshot_row, live_row in zip(snapshot.rows, live.rows):
        if (snapshot_row.sha256, snapshot_row.size_bytes) != (live_row.sha256, live_row.size_bytes):
            raise OmpObservationError(f"live session manifest content drifted: {snapshot_row.relative_path!r}")
    return True


def is_settled(journal: ParsedJournal) -> bool:
    """True when the last assistant message stopped without an open tool call."""
    assistants: list[dict] = []
    for entry in journal.entries:
        if entry.type != "message":
            continue
        message = entry.payload.get("message")
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        assistants.append(message)
    if not assistants:
        return False
    last = assistants[-1]
    if last.get("stopReason") != "stop":
        return False
    content = last.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "toolCall":
                return False
    return True


def is_advisor_name(name: str) -> bool:
    """True for ``__advisor.jsonl`` or ``__advisor.<slug>.jsonl`` (pinned slug grammar)."""
    if name == _ADVISOR_JSONL:
        return True
    if not name.startswith(_ADVISOR_PREFIX) or not name.endswith(".jsonl"):
        return False
    return _ADVISOR_SLUG_RE.fullmatch(name[len(_ADVISOR_PREFIX):-len(".jsonl")]) is not None


def is_advisor_journal(relpath: str, journal: ParsedJournal) -> bool:
    """True when a direct advisor journal is non-empty and settled."""
    if not is_advisor_name(relpath.rsplit("/", 1)[-1]):
        return False
    if not journal.entries:
        return False
    return is_settled(journal)


def is_child_journal(journal: ParsedJournal) -> bool:
    """True when the journal holds exactly one session_init with an agent."""
    inits = [entry for entry in journal.entries if entry.type == "session_init"]
    return len(inits) == 1 and bool(inits[0].payload.get("agent"))

def _is_normal_exit(entry) -> bool:
    data = entry.payload.get("data")
    return (
        entry.type == "custom"
        and entry.payload.get("customType") == "session_exit"
        and isinstance(data, dict)
        and data.get("kind") == "normal"
        and data.get("reason") == "dispose"
    )


def is_terminal_child(journal: ParsedJournal) -> bool:
    """True for a settled child, or successful yield, without abnormal exit."""
    if not is_child_journal(journal):
        return False
    exits = [
        entry
        for entry in journal.entries
        if entry.type == "custom"
        and entry.payload.get("customType") == "session_exit"
    ]
    if is_settled(journal):
        return not exits or (
            len(exits) == 1
            and journal.entries[-1] is exits[0]
            and _is_normal_exit(exits[0])
        )
    if len(journal.entries) < 3:
        return False
    result_entry, exit_entry = journal.entries[-2:]
    result = result_entry.payload.get("message")
    details = result.get("details") if isinstance(result, dict) else None
    if (
        result_entry.type != "message"
        or not isinstance(result, dict)
        or result.get("role") != "toolResult"
        or result.get("toolName") != "yield"
        or result.get("isError") is not False
        or not isinstance(details, dict)
        or details.get("status") != "success"
        or len(exits) != 1
        or exit_entry is not exits[0]
        or not _is_normal_exit(exit_entry)
    ):
        return False
    call_id = result.get("toolCallId")
    if not isinstance(call_id, str) or not call_id:
        return False
    matches = 0
    for entry in journal.entries[:-2]:
        message = entry.payload.get("message")
        if entry.type != "message" or not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "toolCall" and block.get("name") == "yield" and block.get("id") == call_id:
                matches += 1
    return matches == 1


def hub_match(journal: ParsedJournal) -> tuple[int, tuple[str, ...]]:
    """One-to-one ordered hub correlation; failed/orphan/duplicate results fail."""
    calls: list[str] = []
    matched: set[str] = set()
    for entry in journal.entries:
        if entry.type != "message":
            continue
        message = entry.payload.get("message")
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role == "assistant":
            for block in message.get("content") or []:
                if (isinstance(block, dict) and block.get("type") == "toolCall"
                        and block.get("name") == "hub" and isinstance(block.get("id"), str)):
                    if block["id"] in calls or block["id"] in matched:
                        raise OmpObservationError(f"duplicate/reused hub call id {block['id']!r}")
                    calls.append(block["id"])
        elif role == "toolResult" and message.get("toolName") == "hub":
            call_id = message.get("toolCallId")
            if not isinstance(call_id, str) or call_id not in calls or call_id in matched:
                raise OmpObservationError(f"orphan or duplicate hub result {call_id!r}")
            if message.get("isError") is True:
                raise OmpObservationError(f"failed hub result for call {call_id!r}")
            matched.add(call_id)
    return len(matched), tuple(call_id for call_id in calls if call_id not in matched)


def _parse_journal(relpath: str, data: bytes) -> ParsedJournal:
    try:
        return parse_journal_bytes(data, relpath=relpath)
    except OmpSessionError as exc:
        raise OmpObservationError(str(exc)) from exc


def observe_close(*, session_root_fd: int, stdout_session_id: str, conf_manifest_sha256: str | None,
                  recognized_topologies, isolated_worktree_root: str | None = None) -> ObservationReport:
    """Observe one session tree at close against the X5 contract."""
    try:
        rows = list(walk_regular_files(
            session_root_fd,
            max_depth=SESSION_TREE_MAX_DEPTH,
            max_entries=SESSION_TREE_MAX_FILES,
        ))
    except SafeTreeError as exc:
        raise OmpObservationError(str(exc)) from exc
    if sum(row.size_bytes for row in rows) > SESSION_TREE_MAX_BYTES:
        raise OmpObservationError("session tree exceeds the tree-byte bound")
    journal_rows = [
        row for row in rows if row.relative_path.endswith(".jsonl")
    ]
    if len(journal_rows) > _MAX_JOURNAL_FILES:
        raise OmpObservationError("session tree exceeds the journal-count bound")
    if sum(row.size_bytes for row in journal_rows) > _MAX_JOURNAL_BYTES:
        raise OmpObservationError("session tree exceeds the journal-byte bound")
    for row in journal_rows:
        if row.uid != os.geteuid():
            raise OmpObservationError(
                f"journal is not owned by the effective user: {row.relative_path!r}"
            )
        if row.link_count != 1:
            raise OmpObservationError(
                f"journal is hard-linked: {row.relative_path!r}"
            )
    primary = None
    for row in rows:
        relpath = row.relative_path
        if "/" in relpath:
            continue
        if not relpath.endswith(".jsonl"):
            continue  # non-journal artifacts (token.out, spills) stay manifest-only
        if primary is not None:
            raise OmpObservationError("session root holds more than one direct journal")
        stem = relpath[:-len(".jsonl")]
        if "_" not in stem:
            raise OmpObservationError(f"primary journal name is not <timestamp>_<id>.jsonl: {relpath!r}")
        _timestamp, _separator, session_id = stem.rpartition("_")
        if not _timestamp or session_id != stdout_session_id:
            raise OmpObservationError(f"no primary journal selected by stdout session id {stdout_session_id!r}")
        primary = relpath
    if primary is None:
        raise OmpObservationError(f"no primary journal selected by stdout session id {stdout_session_id!r}")
    artifacts = primary[:-len(".jsonl")]
    journals: dict[str, ParsedJournal] = {}
    primary_bytes: bytes | None = None
    for row in rows:
        if not row.relative_path.endswith(".jsonl"):
            continue  # non-journal artifacts (spills, .md outputs) stay manifest-only
        try:
            data = read_regular_file(
                session_root_fd,
                row.relative_path,
                expected=row,
                max_bytes=PRIMARY_HASH_LIMIT,
            )
        except SafeTreeError as exc:
            raise OmpObservationError(str(exc)) from exc
        if row.relative_path == primary:
            primary_bytes = data
        journals[row.relative_path] = _parse_journal(row.relative_path, data)
    assert primary_bytes is not None
    primary_sha256 = hashlib.sha256(primary_bytes).hexdigest()
    primary_journal = journals[primary]
    if primary_journal.header.id != stdout_session_id:
        raise OmpObservationError("primary journal header id does not match the stdout session id")
    if primary[:-len(".jsonl")].rpartition("_")[0] != primary_journal.header.timestamp.replace(":", "-").replace(".", "-"):
        raise OmpObservationError("primary basename prefix does not match the header timestamp")
    for relpath, journal in journals.items():
        try:
            validate_session_graph(journal.entries)
        except OmpSessionError as exc:
            raise OmpObservationError(f"invalid session graph in {relpath!r}: {exc}") from exc
    if not is_settled(primary_journal):
        raise OmpObservationError(f"primary journal is not settled: {primary!r}")
    advisor_relpaths: list[str] = []
    child_relpaths: list[str] = []
    hub_matched = False
    for relpath, journal in journals.items():
        if relpath != primary:
            if not relpath.startswith(artifacts + "/"):
                raise OmpObservationError(f"unclassified journal outside the primary artifacts dir: {relpath!r}")
            if journal.header.id == stdout_session_id:
                raise OmpObservationError(f"journal duplicates the primary session id: {relpath!r}")
            under = relpath[len(artifacts) + 1:]
            name = under.rsplit("/", 1)[-1]
            advisor_candidate = is_advisor_name(name) and "/" not in under
            child_candidate = name.endswith(".jsonl") and is_child_journal(journal)
            if advisor_candidate and child_candidate:
                raise OmpObservationError(f"ambiguously classified journal: {relpath!r}")
            if advisor_candidate:
                if not is_advisor_journal(relpath, journal):
                    raise OmpObservationError(f"advisor journal failed its predicate: {relpath!r}")
                advisor_relpaths.append(relpath)
            elif child_candidate:
                if not is_terminal_child(journal):
                    raise OmpObservationError(f"child journal failed its predicate: {relpath!r}")
                child_relpaths.append(relpath)
            else:
                raise OmpObservationError(f"unclassified journal: {relpath!r}")
        matched, unmatched = hub_match(journal)
        if unmatched:
            raise OmpObservationError(f"unmatched hub call(s) {unmatched} in {relpath!r}")
        hub_matched = hub_matched or matched > 0
    unrecognized = conf_manifest_sha256 not in recognized_topologies
    if not unrecognized:
        topology = recognized_topologies[conf_manifest_sha256]
        if len(advisor_relpaths) != topology.advisor:
            raise OmpObservationError(
                f"advisor count {len(advisor_relpaths)} != expected {topology.advisor}")
        if len(child_relpaths) != topology.child:
            raise OmpObservationError(f"child count {len(child_relpaths)} != expected {topology.child}")
        if topology.hub_matched and not hub_matched:
            raise OmpObservationError("peer-team topology requires at least one matched hub call")
    if isolated_worktree_root is not None:
        root = os.path.normpath(isolated_worktree_root)
        for relpath in child_relpaths:
            cwd = journals[relpath].header.cwd
            try:
                beneath = os.path.commonpath([root, os.path.normpath(cwd)]) == root
            except ValueError:
                beneath = False
            if beneath and os.path.lexists(cwd):
                raise OmpObservationError(f"isolated child worktree still present at close: {cwd!r}")
    return ObservationReport(primary, primary_sha256, tuple(advisor_relpaths), tuple(child_relpaths),
                             hub_matched, unrecognized)
