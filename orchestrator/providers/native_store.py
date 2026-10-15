"""Read-only position and completion evidence from provider-native session stores (D1, D7).

The checks are lifted from the native-session probe
(`scripts/experiments/native_session_cli_evidence.py`), adapted from nonce matching to
prompt-marker matching. Adapters read the provider's default home (or `CODEX_HOME` /
`CLAUDE_CONFIG_DIR` when the orchestrator's own environment sets them) and never write.

A position is the last completed turn's id and its terminal line. Anything the checks
cannot establish is reported as "incomplete" (`None` / `open_turn=True`), never guessed;
a file that is unreadable or structurally unsupported raises `NativeStoreError`.
"""
from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .native_store_claude import (
    _claude_descendants,
    _claude_resume_padding,
    _claude_structured_result,
    _claude_tool_result,
    _identity,
)
from .types import ProviderSessionMetadataMode

Records = list[tuple[int, dict[str, Any]]]
Events = list[tuple[int, str, dict[str, Any]]]


@dataclass(frozen=True)
class NativePosition:
    turn_id: str
    end_line: int

    def record(self) -> dict[str, Any]:
        return {"turn_id": self.turn_id, "end_line": self.end_line}

    @classmethod
    def from_record(cls, row: Any) -> "NativePosition":
        if (
            not isinstance(row, dict) or set(row) != {"turn_id", "end_line"} or not isinstance(row["turn_id"], str)
            or type(row["end_line"]) is not int or row["end_line"] < 1
        ):
            raise ValueError("native position record is malformed")
        return cls(row["turn_id"], row["end_line"])


@dataclass(frozen=True)
class NativeHead:
    locator: str
    path: Path
    position: NativePosition | None
    open_turn: bool


@dataclass(frozen=True)
class NativeTurn:
    position: NativePosition
    user_line: int


@dataclass(frozen=True)
class NativeLocate:
    path: Path | None
    ambiguous: bool = False


class NativeStoreError(ValueError):
    """The store is unreadable or structurally unsupported; never a permission to append."""


class NativeStoreAdapter(Protocol):
    metadata_mode: str
    home: Path

    def locate(self, locator: str) -> NativeLocate: ...
    def head(self, path: Path) -> NativeHead: ...
    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None: ...


# --- shared JSONL reading (probe `_read_jsonl`, `_has_nonce`) ------------------------------------------

def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate native JSON key")
        value[key] = item
    return value


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite native JSON number")
    return number


def _read_jsonl(path: Path) -> Records:
    try:
        raw = path.read_bytes()
    except OSError as error:
        raise NativeStoreError(f"native store {path} is unreadable: {error}") from error
    records: Records = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        try:
            value = json.loads(raw_line, object_pairs_hook=_unique_object, parse_constant=_finite_float, parse_float=_finite_float)
        except (ValueError, UnicodeDecodeError) as error:
            raise NativeStoreError(f"native store {path} line {line_number} is malformed JSONL") from error
        if not isinstance(value, dict):
            raise NativeStoreError(f"native store {path} line {line_number} is not an object")
        records.append((line_number, value))
    if not records:
        raise NativeStoreError(f"native store {path} is empty")
    return records


def _has_marker(text: str, marker: str) -> bool:
    return bool(marker) and re.search(r"(?<![\w-])" + re.escape(marker) + r"(?![\w-])", text) is not None


def _texts(content: Any) -> str:
    """Submitted text: a plain string, or `text` blocks (their `text` and string `text_elements`).

    Any other block type makes the whole content unreadable rather than guessed, as in the probe.
    """
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type", "text") != "text":
            return ""
        if isinstance(block.get("text"), str):
            parts.append(block["text"])
        parts.extend(t for t in block.get("text_elements") or () if isinstance(t, str))
    return "\n".join(parts)


def _plain_locator(locator: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]+", locator or ""):
        raise NativeStoreError(f"native locator {locator!r} is not a plain session id")
    return locator


def _unique_match(candidates: list[Path]) -> NativeLocate:
    if len(candidates) == 1:
        return NativeLocate(candidates[0])
    return NativeLocate(None, ambiguous=len(candidates) > 1)


def _successor(positions: list[NativePosition | None], after: NativePosition | None) -> NativePosition | None:
    """The head turn's position when it is complete and directly follows `after` (the first turn when None)."""
    if not positions or positions[-1] is None:
        return None
    if len(positions) == 1:
        return positions[0] if after is None else None
    return positions[-1] if after is not None and positions[-2] == after else None


# --- Codex (probe `_codex_session`, `_codex_events`, lifecycle walk) -------------------------------------------------

def _codex_session(records: Records) -> str:
    headers = [(line, row.get("payload")) for line, row in records if row.get("type") == "session_meta"]
    if len(headers) != 1 or headers[0][0] != 1 or not isinstance(headers[0][1], dict) or not _identity(headers[0][1].get("id")):
        raise NativeStoreError("native session identity is missing or ambiguous")
    return headers[0][1]["id"]


def _codex_events(records: Records) -> Events:
    events: Events = []
    for line, record in records:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise NativeStoreError("native event envelope is malformed")
        event_type = payload.get("type")
        if not isinstance(event_type, str):
            raise NativeStoreError("native event type is missing")
        events.append((line, event_type, payload))
    return events


def _codex_check_item(payload: dict[str, Any], session_id: str, item_ids: set[str]) -> None:
    item = payload.get("item")
    if payload.get("thread_id") != session_id or not isinstance(item, dict) or not _identity(item.get("id")):
        raise NativeStoreError("native item identity or session is unsupported")
    if item["id"] in item_ids:
        raise NativeStoreError("native item identity is duplicated")
    item_ids.add(item["id"])


def _codex_walk(path: Path) -> tuple[str, Events, list[NativePosition], str | None]:
    """Session id, events, completed positions in order, and the open turn id (if any)."""
    records = _read_jsonl(path)
    session_id = _codex_session(records)
    events = _codex_events(records)
    active: str | None = None
    started: set[str] = set()
    completed: list[NativePosition] = []
    item_ids: set[str] = set()
    for line, event_type, payload in events:
        if event_type not in {"task_started", "task_complete", "item_completed"}:
            continue
        event_turn = payload.get("turn_id")
        if not _identity(event_turn):
            raise NativeStoreError("native lifecycle identity is missing")
        if event_type == "task_started":
            if active is not None or event_turn in started:
                raise NativeStoreError("native lifecycle overlaps or repeats a turn")
            active = event_turn
            started.add(event_turn)
        elif active != event_turn:
            raise NativeStoreError("native append is outside its active turn")
        elif event_type == "task_complete":
            completed.append(NativePosition(event_turn, line))
            active = None
        else:
            _codex_check_item(payload, session_id, item_ids)
    return session_id, events, completed, active


def _codex_user_text(payload: dict[str, Any]) -> str | None:
    item = payload["item"]
    content = item.get("content")
    if item.get("type") != "UserMessage" or not isinstance(content, list):
        return None
    if not all(isinstance(block, dict) and isinstance(block.get("text_elements"), list) for block in content):
        return None
    return _texts(content)


def _codex_turn_event_key(kind: str, payload: dict[str, Any]) -> Any:
    """`task_started`, `task_complete`, `UserMessage`, `final_answer` or another (ignored) key."""
    if kind != "item_completed":
        return kind
    item = payload["item"]
    if item.get("type") == "AgentMessage" and item.get("phase") == "final_answer":
        return "final_answer"
    return item.get("type")


def _codex_turn_complete(events: Events, turn_id: str, user_line: int) -> bool:
    """Exactly one start, user message, final answer and completion, in that order."""
    seen: dict[str, list[int]] = {"task_started": [], "UserMessage": [], "final_answer": [], "task_complete": []}
    for line, kind, payload in events:
        key = _codex_turn_event_key(kind, payload) if payload.get("turn_id") == turn_id else None
        if key in seen:
            seen[key].append(line)
    starts, users, finals, completions = seen.values()
    if users != [user_line] or not len(starts) == len(finals) == len(completions) == 1:
        return False
    return starts[0] < user_line < finals[0] < completions[0]


class _Codex:
    metadata_mode = ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value

    def __init__(self) -> None:
        self.home = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")

    def locate(self, locator: str) -> NativeLocate:
        store = self.home / "sessions"
        if not store.is_dir():
            return NativeLocate(None)
        pattern = f"*{_plain_locator(locator)}.jsonl"
        return _unique_match([path for path in sorted(store.rglob(pattern)) if self._may_hold(path, locator)])

    @staticmethod
    def _may_hold(path: Path, locator: str) -> bool:
        """A file named for the locator counts unless its header names another session (unverifiable counts)."""
        try:
            return _codex_session(_read_jsonl(path)) == locator
        except NativeStoreError:
            return True

    def head(self, path: Path) -> NativeHead:
        session_id, _events, completed, active = _codex_walk(path)
        return NativeHead(session_id, path, completed[-1] if completed else None, active is not None)

    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None:
        session_id, events, completed, active = _codex_walk(path)
        target = None if active is not None else _successor(list(completed), after)
        if target is None:
            return None
        users = []
        for line, kind, payload in events:
            text = _codex_user_text(payload) if kind == "item_completed" else None
            if text is not None and _has_marker(text, prompt_marker):
                users.append((line, payload["turn_id"]))
        if len(users) != 1 or users[0][1] != target.turn_id:
            return None
        if not _codex_turn_complete(events, target.turn_id, users[0][0]):
            return None
        return NativeTurn(target, users[0][0])


# --- Claude: per-turn walk of the probe's `inspect_claude_turn`, returning None per turn instead of INCONCLUSIVE ---

_UNLINKABLE = object()  # predecessor id after an incomplete turn: no later turn can descend from it


def _claude_row_in_lineage(line: int, row: dict[str, Any], submitted: dict[str, Any], by_id, session_id: str) -> bool:
    prompt_id = submitted["promptId"]
    return not (
        not _identity(row.get("uuid")) or not isinstance(row.get("message"), dict)
        or row.get("isSidechain", False) is not False
        or not _claude_descendants(
            row.get("parentUuid"), submitted["uuid"], by_id, child_line=line, session_id=session_id, prompt_id=prompt_id,
        )
        or ("promptId" in row and row["promptId"] != prompt_id)
        or (row.get("type") == "user" and not _claude_tool_result(row))
    )


def _claude_is_final(row: dict[str, Any]) -> bool:
    if row.get("type") == "assistant":
        return row["message"].get("stop_reason") == "end_turn"
    return row.get("type") == "user" and row.get("toolEndsTurn") is True


def _claude_message_id(row: dict[str, Any]) -> Any:
    return row["message"].get("id") if row.get("type") == "assistant" else None


def _claude_split_message_ok(rows: Records) -> bool:
    """Rows of one assistant message agree on `stop_reason` and `promptId`, each the parent of the next."""
    first = rows[0][1]
    return all(
        row["message"].get("stop_reason") == first["message"].get("stop_reason")
        and row.get("promptId") == first.get("promptId") and row.get("parentUuid") == previous["uuid"]
        for (_line, previous), (_next_line, row) in zip(rows, rows[1:])
    )


def _claude_logical_finals(turn: Records) -> Records | None:
    """Final rows, one per logical message; None when a final message split across rows is inconsistent.

    The CLI writes one row per content block of an assistant message (same `message.id`, observed with
    2.1.300 when a thinking block precedes the text); such a message ends at its last row.
    """
    groups: dict[str, Records] = {}
    for line, row in turn:
        if _identity(_claude_message_id(row)):
            groups.setdefault(row["message"]["id"], []).append((line, row))
    final_groups = [rows for rows in groups.values() if any(_claude_is_final(row) for _line, row in rows)]
    if not all(_claude_split_message_ok(rows) for rows in final_groups):
        return None
    singles = [(line, row) for line, row in turn if _claude_is_final(row) and not _identity(_claude_message_id(row))]
    return singles + [rows[-1] for rows in final_groups]


def _claude_next_parent(turn: Records, final_line: int, final_row: dict[str, Any], session_id: str, *, is_last: bool) -> str | None:
    """The id the next submitted turn must descend from: the final, or its one resume-padding row (never on the last turn)."""
    trailing = [row for line, row in turn if line > final_line]
    if not trailing:
        return final_row["uuid"]
    if is_last or len(trailing) != 1 or not _claude_resume_padding(trailing[0], final_row["uuid"], session_id):
        return None
    return trailing[0]["uuid"]


def _claude_turn_final(turn: Records, submitted: dict[str, Any], by_id, session_id: str, *, is_last: bool) -> tuple[int, str] | None:
    """(final line, id the next submitted turn must descend from) for a complete turn, else None."""
    if not all(_claude_row_in_lineage(line, row, submitted, by_id, session_id) for line, row in turn):
        return None
    finals = _claude_logical_finals(turn)
    if finals is None or len(finals) != 1:
        return None
    final_line, final_row = finals[0]
    if final_row.get("type") == "user" and _claude_structured_result(final_line, final_row, by_id) is None:
        return None
    next_parent = _claude_next_parent(turn, final_line, final_row, session_id, is_last=is_last)
    return None if next_parent is None else (final_line, next_parent)


def _claude_by_id(records: Records) -> dict[str, tuple[int, dict[str, Any]]]:
    by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for line, row in records:
        uuid = row.get("uuid")
        if _identity(uuid):
            if uuid in by_id:
                raise NativeStoreError("native message identity is duplicated")
            by_id[uuid] = (line, row)
    return by_id


def _claude_submitted(row: dict[str, Any]) -> bool:
    return row.get("type") == "user" and not _claude_tool_result(row)


def _claude_users(records: Records, expected_session_id: str) -> tuple[str, Records]:
    """The session id and its submitted (non-tool-result) user rows."""
    first = next((row for _line, row in records if _claude_submitted(row)), {})
    session_id = first.get("sessionId")
    if not _identity(session_id) or session_id != expected_session_id:
        raise NativeStoreError("native session identity does not match its store filename")
    session_rows = [(line, row) for line, row in records if row.get("sessionId") == session_id]
    users = [(line, row) for line, row in session_rows if _claude_submitted(row)]
    if any(row.get("type") == "assistant" for line, row in session_rows if line < users[0][0]):
        raise NativeStoreError("native assistant precedes the first submitted turn")
    return session_id, users


def _claude_follows(prior_final_id: object, line: int, submitted: dict[str, Any], by_id, session_id: str) -> bool:
    """The submitted row's parent is `prior_final_id` (None: a root), directly or via earlier promptless attachments.

    Session-start hooks and resumes write such a chain before the prompt (CLI 2.1.300); any other row breaks the link.
    """
    current = submitted.get("parentUuid")
    while _identity(current) and current != prior_final_id:
        parent = by_id.get(current)
        line, row = parent if parent is not None and parent[0] < line else (0, {})
        if (
            row.get("type") != "attachment" or not isinstance(row.get("attachment"), dict) or "promptId" in row
            or row.get("sessionId") != session_id or row.get("isSidechain", False) is not False
        ):
            return False
        current = row.get("parentUuid")
    return current == prior_final_id and (current is None or by_id[current][0] < line)


def _claude_links(line: int, submitted: dict[str, Any], prior_final_id: object, prompts: set[str], by_id, session_id: str) -> bool:
    """Fresh prompt and row identities, and the row follows the previous turn's final (or its padding)."""
    prompt_id = submitted.get("promptId")
    return (
        _identity(prompt_id) and _identity(submitted.get("uuid")) and prompt_id not in prompts
        and "parentUuid" in submitted and _claude_follows(prior_final_id, line, submitted, by_id, session_id)
    )


def _claude_turns(path: Path) -> tuple[str, Records, list[NativePosition | None]]:
    """Session id, submitted user rows, and per submitted turn its position (None: incomplete or unsupported)."""
    records = _read_jsonl(path)
    by_id = _claude_by_id(records)
    session_id, users = _claude_users(records, path.stem)
    positions: list[NativePosition | None] = []
    prior_final_id: object = None
    prompts: set[str] = set()
    for index, (start_line, submitted) in enumerate(users):
        final = None
        if _claude_links(start_line, submitted, prior_final_id, prompts, by_id, session_id):
            next_line = users[index + 1][0] if index + 1 < len(users) else len(records) + 1
            turn = [
                (line, row) for line, row in records
                if start_line < line < next_line and row.get("sessionId") == session_id and row.get("type") in {"assistant", "user"}
            ]
            final = _claude_turn_final(turn, submitted, by_id, session_id, is_last=index + 1 >= len(users))
            prompts.add(submitted["promptId"])
        positions.append(None if final is None else NativePosition(submitted["promptId"], final[0]))
        prior_final_id = _UNLINKABLE if final is None else final[1]
    return session_id, users, positions


def _claude_user_text(row: dict[str, Any]) -> str:
    message = row.get("message")
    return _texts(message.get("content")) if isinstance(message, dict) else ""


class _Claude:
    metadata_mode = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value

    def __init__(self) -> None:
        self.home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")

    def locate(self, locator: str) -> NativeLocate:
        store = self.home / "projects"
        if not store.is_dir():
            return NativeLocate(None)
        return _unique_match(sorted(store.rglob(f"{_plain_locator(locator)}.jsonl")))

    def head(self, path: Path) -> NativeHead:
        session_id, _users, positions = _claude_turns(path)
        last = next((position for position in reversed(positions) if position is not None), None)
        return NativeHead(session_id, path, last, positions[-1] is None)

    def completed_turn(self, path: Path, *, after: NativePosition | None, prompt_marker: str) -> NativeTurn | None:
        _session_id, users, positions = _claude_turns(path)
        target = _successor(positions, after)
        if target is None:
            return None
        matching = [line for line, row in users if _has_marker(_claude_user_text(row), prompt_marker)]
        if matching != [users[-1][0]]:
            return None
        return NativeTurn(target, users[-1][0])


def native_store_adapter(metadata_mode: str | None) -> NativeStoreAdapter | None:
    """Select the store reader structurally from the template's metadata mode."""
    for adapter in (_Codex, _Claude):
        if metadata_mode == adapter.metadata_mode:
            return adapter()
    return None
