from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class NativeEvidence:
    status: str
    reason: str
    session_id: str | None = None
    turn_id: str | None = None
    predecessor_turn_id: str | None = None
    result: dict[str, Any] | None = None
    refs: tuple[str, ...] = ()
    raw_sha256: str = ""


class _MalformedJSONL(ValueError):
    def __init__(self, reason: str, digest: str) -> None:
        super().__init__(reason)
        self.digest = digest


def _inconclusive(path: Path, reason: str | Exception, digest: str = "") -> NativeEvidence:
    return NativeEvidence(
        "INCONCLUSIVE",
        str(reason),
        refs=(str(path),),
        raw_sha256=reason.digest if isinstance(reason, _MalformedJSONL) else digest,
    )


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate native JSON key")
        value[key] = item
    return value


def _invalid_constant(value: str) -> None:
    raise ValueError(f"nonfinite native JSON number: {value}")


def _finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("nonfinite native JSON number")
    return number


def _read_jsonl(path: Path) -> tuple[list[tuple[int, dict[str, Any]]], str]:
    raw = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    records: list[tuple[int, dict[str, Any]]] = []
    for line_number, raw_line in enumerate(raw.splitlines(), start=1):
        try:
            value = json.loads(raw_line, object_pairs_hook=_unique_object, parse_constant=_invalid_constant, parse_float=_finite_float)
        except (ValueError, UnicodeDecodeError) as error:
            raise _MalformedJSONL("malformed native JSONL", digest) from error
        if not isinstance(value, dict):
            raise _MalformedJSONL("native JSONL row is not an object", digest)
        records.append((line_number, value))
    if not records:
        raise _MalformedJSONL("native JSONL is empty", digest)
    return records, digest


def _texts(content: Any, *, block_type: str = "text") -> str:
    if isinstance(content, str):
        return content if block_type == "text" else ""
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != block_type or not isinstance(block.get("text"), str):
            return ""
        parts.append(block["text"])
    return "".join(parts)


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_nonce(text: str, nonce: str) -> bool:
    return bool(nonce) and re.search(r"(?<![\w-])" + re.escape(nonce) + r"(?![\w-])", text) is not None


def _codex_session(records: list[tuple[int, dict[str, Any]]]) -> str:
    headers = [(line, row.get("payload")) for line, row in records if row.get("type") == "session_meta"]
    if len(headers) != 1 or headers[0][0] != 1 or not isinstance(headers[0][1], dict) or not _identity(headers[0][1].get("id")):
        raise ValueError("native session identity is missing or ambiguous")
    return headers[0][1]["id"]


def _json_result(value: Any, nonce: str) -> dict[str, Any] | None:
    if not isinstance(value, str):
        return None
    try:
        result = json.loads(value, object_pairs_hook=_unique_object, parse_constant=_invalid_constant, parse_float=_finite_float)
    except ValueError:
        return None
    if isinstance(result, dict) and result.get("nonce") == nonce:
        return result
    return None


def _codex_events(records: list[tuple[int, dict[str, Any]]]) -> list[tuple[int, str, dict[str, Any]]]:
    events: list[tuple[int, str, dict[str, Any]]] = []
    for line, record in records:
        if record.get("type") != "event_msg":
            continue
        payload = record.get("payload")
        if not isinstance(payload, dict):
            raise ValueError("native event envelope is malformed")
        event_type = payload.get("type")
        if not isinstance(event_type, str):
            raise ValueError("native event type is missing")
        events.append((line, event_type, payload))
    return events


def inspect_codex_turn(
    path: Path,
    *,
    nonce: str,
    expected_session: str | None,
    predecessor_turn: str | None,
) -> NativeEvidence:
    try:
        records, digest = _read_jsonl(path)
    except (OSError, ValueError) as error:
        return _inconclusive(path, error)
    try:
        session_id = _codex_session(records)
    except ValueError as error:
        return _inconclusive(path, str(error), digest)
    if expected_session is not None and session_id != expected_session:
        return _inconclusive(path, "native session identity differs from the expected session", digest)

    try:
        events = _codex_events(records)
    except ValueError as error:
        return _inconclusive(path, str(error), digest)
    active: str | None = None
    started: list[str] = []
    completed: list[str] = []
    item_ids: set[str] = set()
    for _, event_type, payload in events:
        if event_type not in {"task_started", "task_complete", "item_completed"}:
            continue
        event_turn = payload.get("turn_id")
        if not _identity(event_turn):
            return _inconclusive(path, "native lifecycle identity is missing", digest)
        if event_type == "task_started":
            if active is not None or event_turn in started:
                return _inconclusive(path, "native lifecycle overlaps or repeats a turn", digest)
            active = event_turn
            started.append(event_turn)
        elif active != event_turn:
            return _inconclusive(path, "native append is outside its active turn", digest)
        elif event_type == "task_complete":
            completed.append(event_turn)
            active = None
        else:
            item = payload.get("item")
            if payload.get("thread_id") != session_id or not isinstance(item, dict) or not _identity(item.get("id")):
                return _inconclusive(path, "native item identity or session is unsupported", digest)
            if item["id"] in item_ids:
                return _inconclusive(path, "native item identity is duplicated", digest)
            item_ids.add(item["id"])
    if active is not None:
        return _inconclusive(path, "native session head is incomplete", digest)
    matching_users: list[tuple[int, str]] = []
    for line, event_type, payload in events:
        item = payload.get("item")
        if event_type != "item_completed" or not isinstance(item, dict) or item.get("type") != "UserMessage":
            continue
        turn_id = payload.get("turn_id")
        if (
            payload.get("thread_id") == session_id
            and _identity(turn_id)
            and isinstance(item.get("content"), list)
            and all(isinstance(block, dict) and isinstance(block.get("text_elements"), list) for block in item["content"])
            and _has_nonce(_texts(item.get("content")), nonce)
        ):
            matching_users.append((line, turn_id))
    if len(matching_users) != 1:
        return _inconclusive(path, "submitted nonce does not identify exactly one native turn", digest)
    user_line, turn_id = matching_users[0]
    if sum(event_type == "item_completed" and payload.get("turn_id") == turn_id and payload["item"].get("type") == "UserMessage" for _, event_type, payload in events) != 1:
        return _inconclusive(path, "native turn contains multiple user messages", digest)

    starts = [
        line
        for line, event_type, payload in events
        if event_type == "task_started" and payload.get("turn_id") == turn_id
    ]
    finals: list[tuple[int, dict[str, Any]]] = []
    completions: list[tuple[int, dict[str, Any]]] = []
    for line, event_type, payload in events:
        if payload.get("turn_id") != turn_id:
            continue
        if event_type == "item_completed":
            item = payload.get("item")
            if (
                payload.get("thread_id") == session_id
                and isinstance(item, dict)
                and item.get("type") == "AgentMessage"
                and item.get("phase") == "final_answer"
            ):
                finals.append((line, item))
        elif event_type == "task_complete":
            completions.append((line, payload))
    if len(starts) != 1 or starts[0] >= user_line or len(finals) != 1 or len(completions) != 1:
        return _inconclusive(path, "native start, final message, or completion is missing or ambiguous", digest)
    final_line, final_item = finals[0]
    complete_line, completion = completions[0]
    if not (user_line < final_line < complete_line):
        return _inconclusive(path, "native message order does not establish a completed turn", digest)
    final_result = _json_result(_texts(final_item.get("content"), block_type="Text"), nonce)
    complete_result = _json_result(completion.get("last_agent_message"), nonce)
    if final_result is None or complete_result is None or final_result != complete_result:
        return _inconclusive(path, "native final result is absent or differs from the completion result", digest)

    if not completed or completed[-1] != turn_id:
        return _inconclusive(path, "submitted turn is not the native session head", digest)
    observed_predecessor = completed[-2] if len(completed) > 1 else None
    if observed_predecessor != predecessor_turn:
        return _inconclusive(path, "native predecessor does not match the expected position", digest)

    refs = (
        f"{path}:session_meta",
        f"{path}:{starts[0]}:task_started:{turn_id}",
        f"{path}:{user_line}:UserMessage",
        f"{path}:{final_line}:AgentMessage",
        f"{path}:{complete_line}:task_complete",
    )
    return NativeEvidence(
        "OBSERVED",
        "native nonce, session, turn, predecessor, final result, and completion are bound",
        session_id=session_id,
        turn_id=turn_id,
        predecessor_turn_id=predecessor_turn,
        result=final_result,
        refs=refs,
        raw_sha256=digest,
    )


def _claude_tool_result(row: dict[str, Any]) -> bool:
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return bool(
        row.get("type") == "user"
        and isinstance(message, dict)
        and message.get("role") == "user"
        and isinstance(content, list)
        and content
        and all(
            isinstance(block, dict)
            and block.get("type") == "tool_result"
            and _identity(block.get("tool_use_id"))
            and isinstance(block.get("content"), (str, list))
            and ("is_error" not in block or isinstance(block["is_error"], bool))
            for block in content
        )
    )


def _claude_descendants(
    parent_id: Any,
    ancestor_id: str,
    by_id: dict[str, tuple[int, dict[str, Any]]],
    *,
    child_line: int,
    session_id: str,
    prompt_id: str,
) -> bool:
    current = parent_id
    while _identity(current):
        parent = by_id.get(current)
        if parent is None or parent[0] >= child_line or parent[1].get("sessionId") != session_id or parent[1].get("isSidechain", False) is not False:
            return False
        row = parent[1]
        if current == ancestor_id:
            return row.get("type") == "user" and row.get("promptId") == prompt_id
        if row.get("type") == "attachment":
            if not isinstance(row.get("attachment"), dict) or ("promptId" in row and row["promptId"] != prompt_id):
                return False
        elif row.get("type") == "assistant":
            if "promptId" in row and row["promptId"] != prompt_id:
                return False
        elif not _claude_tool_result(row) or row.get("promptId") != prompt_id:
            return False
        child_line, current = parent[0], row.get("parentUuid")
    return False


def _claude_structured_result(
    final_line: int, final: dict[str, Any], by_id: dict[str, tuple[int, dict[str, Any]]],
) -> dict[str, Any] | None:
    if not _claude_tool_result(final) or final.get("toolEndsTurn") is not True:
        return None
    parent_id = final.get("parentUuid")
    source = by_id.get(parent_id)
    if source is None or final.get("sourceToolAssistantUUID") != parent_id:
        return None
    source_line, assistant = source
    message = assistant.get("message")
    if (
        assistant.get("type") != "assistant" or not isinstance(message, dict)
        or message.get("stop_reason") != "tool_use" or assistant.get("sessionId") != final.get("sessionId")
        or not isinstance(message.get("content"), list)
    ):
        return None
    results = final["message"]["content"]
    tools = [block for block in message.get("content", []) if isinstance(block, dict) and block.get("type") == "tool_use"]
    if len(results) != 1 or len(tools) != 1:
        return None
    tool, result = tools[0], results[0]
    if (
        tool.get("name") != "StructuredOutput" or not _identity(tool.get("id"))
        or result.get("tool_use_id") != tool["id"] or result.get("is_error", False) is not False
        or not isinstance(tool.get("input"), dict)
    ):
        return None
    attachments = [
        row for line, row in by_id.values()
        if source_line < line < final_line and row.get("type") == "attachment"
        and isinstance(row.get("attachment"), dict) and row["attachment"].get("type") == "structured_output"
        and row.get("parentUuid") == parent_id
    ]
    if len(attachments) != 1:
        return None
    attachment = attachments[0]
    if (
        attachment.get("sessionId") != final.get("sessionId") or attachment.get("isSidechain", False) is not False
        or ("promptId" in attachment and attachment["promptId"] != final.get("promptId"))
        or attachment["attachment"].get("toolUseID") != tool["id"]
        or json.dumps(attachment["attachment"].get("data"), sort_keys=True) != json.dumps(tool["input"], sort_keys=True)
    ):
        return None
    return tool["input"]


def _claude_resume_padding(row: dict[str, Any], parent_id: str, session_id: str) -> bool:
    message = row.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
        return False
    return (
        row.get("type") == "assistant" and row.get("parentUuid") == parent_id
        and row.get("sessionId") == session_id and row.get("isSidechain", False) is False
        and row.get("isApiErrorMessage") is False and _identity(message.get("id"))
        and message.get("model") == "<synthetic>" and message.get("role") == "assistant"
        and message.get("type") == "message" and message.get("stop_reason") == "stop_sequence"
        and message.get("stop_sequence") == ""
        and message.get("content") == [{"type": "text", "text": "No response requested."}]
        and all(type(message["usage"].get(key)) is int and message["usage"][key] == 0
                for key in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    )


def inspect_claude_turn(
    path: Path,
    *,
    nonce: str,
    expected_session: str | None,
    predecessor_turn: str | None,
) -> NativeEvidence:
    try:
        records, digest = _read_jsonl(path)
    except (OSError, ValueError) as error:
        return _inconclusive(path, error)
    by_id: dict[str, tuple[int, dict[str, Any]]] = {}
    for line, row in records:
        uuid = row.get("uuid")
        if _identity(uuid):
            if uuid in by_id:
                return _inconclusive(path, "native message identity is duplicated", digest)
            by_id[uuid] = (line, row)
    users = [
        (line, row)
        for line, row in records
        if row.get("type") == "user"
        and isinstance(row.get("message"), dict)
        and _has_nonce(_texts(row["message"].get("content")), nonce)
    ]
    if len(users) != 1:
        return _inconclusive(path, "submitted nonce does not identify exactly one native user message", digest)
    user_line, user = users[0]
    session_id, turn_id, user_id = user.get("sessionId"), user.get("promptId"), user.get("uuid")
    if (
        not all(_identity(value) for value in (session_id, turn_id, user_id))
        or (expected_session is not None and session_id != expected_session)
    ):
        return _inconclusive(path, "native user message lacks the expected session or prompt identity", digest)
    session_users = [
        (line, row) for line, row in records
        if row.get("type") == "user" and row.get("sessionId") == session_id and not _claude_tool_result(row)
    ]
    if session_users[-1][0] != user_line:
        return _inconclusive(path, "submitted user message is not the native session head", digest)
    if any(line < session_users[0][0] and row.get("sessionId") == session_id and row.get("type") == "assistant" for line, row in records):
        return _inconclusive(path, "native assistant precedes the first submitted turn", digest)

    prior_turn: str | None = None
    prior_final_id: str | None = None
    prompts: set[str] = set()
    for index, (start_line, submitted) in enumerate(session_users):
        prompt_id, submitted_id = submitted.get("promptId"), submitted.get("uuid")
        if (
            not _identity(prompt_id) or not _identity(submitted_id) or prompt_id in prompts
            or "parentUuid" not in submitted
            or submitted.get("parentUuid") != prior_final_id
        ):
            return _inconclusive(path, "native predecessor identity or parent is unsupported", digest)
        if start_line == user_line and prior_turn != predecessor_turn:
            return _inconclusive(path, "native predecessor does not match the expected position", digest)
        prompts.add(prompt_id)
        next_line = session_users[index + 1][0] if index + 1 < len(session_users) else len(records) + 1
        turns = [
            (line, row) for line, row in records
            if start_line < line < next_line and row.get("sessionId") == session_id
            and row.get("type") in {"assistant", "user"}
        ]
        for line, row in turns:
            if (
                not _identity(row.get("uuid")) or not isinstance(row.get("message"), dict)
                or row.get("isSidechain", False) is not False
                or not _claude_descendants(
                    row.get("parentUuid"), submitted_id, by_id,
                    child_line=line, session_id=session_id, prompt_id=prompt_id,
                )
                or ("promptId" in row and row["promptId"] != prompt_id)
                or (row.get("type") == "user" and not _claude_tool_result(row))
            ):
                return _inconclusive(path, "native message lineage is unsupported or unordered", digest)
        finals = [
            (line, row) for line, row in turns
            if (row.get("type") == "assistant" and row["message"].get("stop_reason") == "end_turn")
            or (row.get("type") == "user" and row.get("toolEndsTurn") is True)
        ]
        if len(finals) != 1:
            return _inconclusive(path, "native end marker or current head is missing or ambiguous", digest)
        final_line, final_row = finals[0]
        if final_row.get("type") == "user" and _claude_structured_result(final_line, final_row, by_id) is None:
            return _inconclusive(path, "native structured result or its terminal tool binding is unsupported", digest)
        prior_turn, prior_final_id = prompt_id, final_row["uuid"]
        trailing = [(line, row) for line, row in turns if line > final_line]
        if trailing:
            if (
                index + 1 >= len(session_users) or len(trailing) != 1
                or not _claude_resume_padding(trailing[0][1], prior_final_id, session_id)
            ):
                return _inconclusive(path, "native trailing message is not supported resume padding", digest)
            prior_final_id = trailing[0][1]["uuid"]
    if final_row.get("type") == "user":
        structured = _claude_structured_result(final_line, final_row, by_id)
        result = _json_result(json.dumps(structured), nonce) if structured is not None else None
        completion_ref = f"{path}:{final_line}:user:{final_row['uuid']}:toolEndsTurn"
        structured_refs = tuple(
            f"{path}:{line}:{row['type']}:{row['uuid']}:StructuredOutput"
            for line, row in by_id.values()
            if row["uuid"] == final_row["sourceToolAssistantUUID"]
            or (row.get("type") == "attachment" and row.get("parentUuid") == final_row["sourceToolAssistantUUID"]
                and isinstance(row.get("attachment"), dict) and row["attachment"].get("type") == "structured_output")
        )
    else:
        result = _json_result(_texts(final_row["message"].get("content")), nonce)
        completion_ref = f"{path}:{final_line}:assistant:{final_row['uuid']}:end_turn"
        structured_refs = ()
    if result is None:
        return _inconclusive(path, "native final content is not a supported text JSON result", digest)
    return NativeEvidence(
        "OBSERVED",
        "native nonce ancestry, session, prompt, final result, and end marker are bound",
        session_id=session_id,
        turn_id=turn_id,
        predecessor_turn_id=predecessor_turn,
        result=result,
        refs=(f"{path}:{user_line}:user:{user_id}", *structured_refs, completion_ref),
        raw_sha256=digest,
    )


def inspect_native_user_turn(
    provider: str,
    path: Path,
    *,
    nonce: str,
    expected_session: str | None,
) -> NativeEvidence:
    try:
        records, digest = _read_jsonl(path)
        if provider == "codex":
            session_id = _codex_session(records)
            if expected_session is not None and session_id != expected_session:
                return _inconclusive(path, "native session differs from expected session", digest)
            events = _codex_events(records)
            item_ids = [payload["item"].get("id") if isinstance(payload.get("item"), dict) else None for _, event_type, payload in events if event_type == "item_completed"]
            if not all(_identity(value) for value in item_ids) or len(item_ids) != len(set(item_ids)):
                return _inconclusive(path, "native item identity is missing or duplicated", digest)
            matches = [
                (line, payload)
                for line, event_type, payload in events
                if event_type == "item_completed"
                and isinstance(payload.get("item"), dict)
                and payload["item"].get("type") == "UserMessage"
                and payload.get("thread_id") == session_id
                and _identity(payload["item"].get("id"))
                and isinstance(payload["item"].get("content"), list)
                and all(isinstance(block, dict) and isinstance(block.get("text_elements"), list) for block in payload["item"]["content"])
                and _has_nonce(_texts(payload["item"].get("content")), nonce)
            ]
            if len(matches) != 1 or not _identity(matches[0][1].get("turn_id")):
                return _inconclusive(path, "native user message is missing or ambiguous", digest)
            line, payload = matches[0]
            turn_id = payload["turn_id"]
            ref = f"{path}:{line}:UserMessage:{turn_id}"
        elif provider == "claude":
            message_ids = [row.get("uuid") for _, row in records if row.get("type") in {"user", "assistant"}]
            if not all(_identity(value) for value in message_ids) or len(message_ids) != len(set(message_ids)):
                return _inconclusive(path, "native message identity is missing or duplicated", digest)
            matches = [
                (line, row)
                for line, row in records
                if row.get("type") == "user"
                and isinstance(row.get("message"), dict)
                and _has_nonce(_texts(row["message"].get("content")), nonce)
            ]
            if len(matches) != 1:
                return _inconclusive(path, "native user message is missing or ambiguous", digest)
            line, row = matches[0]
            session_id = row.get("sessionId")
            turn_id = row.get("promptId")
            if (
                not all(_identity(value) for value in (session_id, turn_id, row.get("uuid")))
                or (expected_session is not None and session_id != expected_session)
            ):
                return _inconclusive(path, "native user message identity is unsupported", digest)
            ref = f"{path}:{line}:user:{row.get('uuid')}"
        else:
            return _inconclusive(path, "unsupported provider", digest)
    except (OSError, ValueError) as error:
        return _inconclusive(path, error)
    return NativeEvidence(
        "INCONCLUSIVE",
        "native user append is present; completion and expected-position proof are absent",
        session_id=session_id,
        turn_id=turn_id,
        refs=(ref,),
        raw_sha256=digest,
    )


def native_turn_open_at_append(provider: str, path: Path, first: NativeEvidence, second: NativeEvidence) -> bool:
    if not first.session_id or first.session_id != second.session_id or not first.turn_id or not second.turn_id:
        return False
    try:
        records, _ = _read_jsonl(path)
        if provider == 'codex':
            if _codex_session(records) != first.session_id:
                return False
            events = _codex_events(records)
            users = {turn: [line for line, kind, row in events if kind == 'item_completed' and row.get('turn_id') == turn and row.get('thread_id') == first.session_id and isinstance(row.get('item'), dict) and row['item'].get('type') == 'UserMessage'] for turn in (first.turn_id, second.turn_id)}
            starts = [line for line, kind, row in events if kind == 'task_started' and row.get('turn_id') == first.turn_id]
            other_starts = [line for line, kind, row in events if kind == 'task_started' and row.get('turn_id') == second.turn_id]
            closes = [line for line, kind, row in events if kind == 'task_complete' and row.get('turn_id') == first.turn_id]
            if len(starts) != 1 or len(other_starts) != 1 or len(closes) > 1:
                return False
        elif provider == 'claude':
            users = {turn: [line for line, row in records if row.get('type') == 'user' and row.get('promptId') == turn and row.get('sessionId') == first.session_id and not _claude_tool_result(row)] for turn in (first.turn_id, second.turn_id)}
            starts = users[first.turn_id]
            closes = [line for line, row in records if row.get('type') == 'assistant' and row.get('sessionId') == first.session_id and isinstance(row.get('message'), dict) and row['message'].get('stop_reason') == 'end_turn']
            by_id = {row['uuid']: (line, row) for line, row in records if _identity(row.get('uuid'))}
            if len(by_id) != sum(_identity(row.get('uuid')) for _, row in records):
                return False
            for line, row in records:
                if row.get('type') == 'user' and row.get('sessionId') == first.session_id and row.get('toolEndsTurn') is True:
                    if _claude_structured_result(line, row, by_id) is None or row.get('isSidechain', False) is not False:
                        return False
                    closes.append(line)
        else:
            return False
        if any(len(lines) != 1 for lines in users.values()):
            return False
        a, b = users[first.turn_id][0], users[second.turn_id][0]
        if provider == 'codex' and not starts[0] < a < other_starts[0] < b:
            return False
        return starts[0] <= a < b and not any(line < b and (provider == 'codex' or line > a) for line in closes)
    except (OSError, ValueError):
        return False
