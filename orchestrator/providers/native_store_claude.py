"""Claude native-transcript lineage predicates, copied verbatim from the native-session probe.

Source: `scripts/experiments/native_session_cli_evidence.py` (`_claude_tool_result`, `_claude_descendants`,
`_claude_structured_result`, `_claude_resume_padding`). `native_store` composes them into the turn walk.
"""
from __future__ import annotations

import json
from typing import Any


def _identity(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
