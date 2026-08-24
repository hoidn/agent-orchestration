"""Closed OMP session-journal parsing, primary selection, graph, and tree manifests (X5/X8)."""
from __future__ import annotations

import hashlib
import json
import stat
from dataclasses import dataclass
from typing import Any

from .._common.safe_tree import SafeTreeError, read_regular_file, walk_regular_files
from .omp_protocol import (_closed_object, _is_rfc3339, is_finite_number, is_integer, is_nonempty_string, loads_strict,
                           validate_closed_assistant_message, validate_content_block, validate_session_header)

KNOWN_ENTRY_TYPES = frozenset({"message", "thinking_level_change", "model_change", "service_tier_change", "compaction",
                               "branch_summary", "custom", "custom_message", "label", "title_change", "ttsr_injection",
                               "session_init", "mode_change", "credential_pin", "reset_boundary"})
_TITLE_KEYS = frozenset({"type", "v", "title", "source", "updatedAt", "pad"})
_TITLE_SOURCES = frozenset({"auto", "user"})
_BASE_KEYS = frozenset({"type", "id", "parentId", "timestamp"})
_USER_MESSAGE_KEYS = frozenset({"role", "content", "timestamp", "attribution", "synthetic", "steering", "providerPayload"})
_DEVELOPER_MESSAGE_KEYS = _USER_MESSAGE_KEYS - frozenset({"synthetic", "steering"})
_TOOL_RESULT_KEYS = frozenset({"role", "toolCallId", "toolName", "content", "isError", "timestamp", "details",
                               "attribution", "prunedAt", "providerMetadata", "useless"})
_ASSISTANT_MESSAGE_KEYS = frozenset({"role", "api", "provider", "model", "timestamp", "stopReason", "content", "usage",
                                     "contextSnapshot", "retryRecovery", "responseId", "upstreamProvider", "stopDetails",
                                     "errorMessage", "toolCallAbortMessages", "errorStatus", "errorId", "disabledFeatures",
                                     "providerPayload", "duration", "ttft"})

_ENTRY_RULES = {
    "message": (frozenset({"message"}), frozenset(), {}),
    "thinking_level_change": (frozenset({"thinkingLevel", "configured"}), frozenset(), {"thinkingLevel": "str|null", "configured": "str|null"}),
    "model_change": (frozenset({"model", "role", "resolvedModelIsFallback"}), frozenset({"model"}), {"model": "str", "role": "str", "resolvedModelIsFallback": "bool"}),
    "service_tier_change": (frozenset({"serviceTier"}), frozenset({"serviceTier"}), {"serviceTier": "service_tier"}),
    "compaction": (frozenset({"summary", "shortSummary", "firstKeptEntryId", "tokensBefore", "details", "preserveData", "fromExtension", "warning"}), frozenset({"summary", "firstKeptEntryId", "tokensBefore"}), {"summary": "str", "shortSummary": "str", "firstKeptEntryId": "str", "tokensBefore": "int", "preserveData": "obj", "fromExtension": "bool", "warning": "str"}),
    "branch_summary": (frozenset({"fromId", "summary", "details", "fromExtension"}), frozenset({"fromId", "summary"}), {"fromId": "str", "summary": "str", "fromExtension": "bool"}),
    "custom": (frozenset({"customType", "data"}), frozenset({"customType"}), {"customType": "str"}),
    "custom_message": (frozenset({"customType", "content", "details", "display", "attribution"}), frozenset({"customType", "content", "display"}), {"customType": "str", "content": "content", "display": "bool", "attribution": "attribution"}),
    "label": (frozenset({"targetId", "label"}), frozenset({"targetId"}), {"targetId": "str", "label": "str"}),
    "title_change": (frozenset({"title", "previousTitle", "source", "trigger"}), frozenset({"title", "source"}), {"title": "str", "previousTitle": "str", "source": "title_source", "trigger": "str"}),
    "ttsr_injection": (frozenset({"injectedRules"}), frozenset({"injectedRules"}), {"injectedRules": "str_list"}),
    "session_init": (frozenset({"systemPrompt", "task", "tools", "agent", "modelRole", "resolvedModel", "readOnly", "outputSchema", "outputSchemaMode", "restrictToolNames", "spawns", "readSummarize", "advisor"}), frozenset({"systemPrompt", "task", "tools"}), {"systemPrompt": "str", "task": "str", "tools": "str_list", "agent": "nonempty_str", "modelRole": "str", "resolvedModel": "str", "readOnly": "bool", "outputSchemaMode": "schema_mode", "restrictToolNames": "bool", "spawns": "str", "readSummarize": "bool", "advisor": "str"}),
    "mode_change": (frozenset({"mode", "data"}), frozenset({"mode"}), {"mode": "str", "data": "obj"}),
    "credential_pin": (frozenset({"provider", "hash"}), frozenset({"provider", "hash"}), {"provider": "str", "hash": "str"}),
    "reset_boundary": (frozenset(), frozenset(), {}),
}


class OmpSessionError(Exception):
    """A persisted OMP journal failed a closed parse or graph check."""


@dataclass(frozen=True, slots=True)
class TitleSlot:
    """The pinned 256-byte physical title slot."""
    title: str; updated_at: str; source: str | None; pad: str


@dataclass(frozen=True, slots=True)
class SessionHeaderRecord:
    """The sole closed ``type:"session"`` header."""
    id: str; version: int | None; timestamp: str; cwd: str; title: str | None
    title_source: str | None; parent_session: str | None; provider_prompt_cache_key: str | None
    additional_directories: tuple[str, ...]; previous_session_files: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SessionEntryRecord:
    """One validated pinned session entry with its raw payload."""
    type: str; id: str; parent_id: str | None; timestamp: str; payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class ParsedJournal:
    """A fully parsed journal: title slot, header, and ordered entries."""
    relpath: str; title_slot: TitleSlot; header: SessionHeaderRecord; entries: tuple[SessionEntryRecord, ...]


@dataclass(frozen=True, slots=True)
class SessionNode:
    """One branch-graph node; children are timestamp-ordered."""
    entry: SessionEntryRecord; children: tuple[SessionNode, ...]


def _parse_object(line: str, relpath: str, where: str) -> dict[str, Any]:
    try:
        return loads_strict(line)
    except ValueError as exc:
        raise OmpSessionError(f"{relpath}: {where} is not one strict JSON object: {exc}") from exc


def _validate_title_slot(obj: dict[str, Any], relpath: str) -> TitleSlot:
    if (error := _closed_object(obj, _TITLE_KEYS, "title slot", required=frozenset({"type", "v", "title", "updatedAt", "pad"}))) is not None \
            or obj["type"] != "title" or not is_integer(obj["v"]) or obj["v"] != 1 or not isinstance(obj["title"], str) \
            or not isinstance(obj["updatedAt"], str) or not _is_rfc3339(obj["updatedAt"]) \
            or not isinstance(obj["pad"], str) or any(ch != " " for ch in obj["pad"]):
        raise OmpSessionError(f"{relpath}: {error or 'title slot type/v/title/updatedAt/pad are invalid'}")
    if "source" in obj and (not isinstance(obj["source"], str) or obj["source"] not in _TITLE_SOURCES):
        raise OmpSessionError(f"{relpath}: title slot source is outside auto|user")
    return TitleSlot(obj["title"], obj["updatedAt"], obj.get("source"), obj["pad"])


def _validate_header(obj: dict[str, Any], relpath: str) -> SessionHeaderRecord:
    if obj.get("type") != "session":
        raise OmpSessionError(f"{relpath}: the second physical line must be the session header")
    if (error := validate_session_header(obj)) is not None:
        raise OmpSessionError(f"{relpath}: {error}")
    return SessionHeaderRecord(obj["id"], obj.get("version") if isinstance(obj.get("version"), int) else None, obj["timestamp"],
                               obj["cwd"], obj.get("title"), obj.get("titleSource"), obj.get("parentSession"),
                               obj.get("providerPromptCacheKey"), tuple(obj.get("additionalDirectories", ())),
                               tuple(obj.get("previousSessionFiles", ())))


def _validate_user_content(content: Any, where: str, allow_string: bool = True) -> str | None:
    if allow_string and isinstance(content, str):
        return None
    if not isinstance(content, list):
        return f"{where} content must be an array" if not allow_string else f"{where} content must be a string or an array"
    for block in content:
        if not isinstance(block, dict) or block.get("type") not in ("text", "image") or (error := validate_content_block(block)) is not None:
            return f"{where} content blocks must be text or image objects"
    return None


def _validate_shape(value: Any, keys, required, rules, where: str) -> str | None:
    if (error := _closed_object(value, keys, where, required=required)) is not None:
        return error
    for field, checker in rules:
        if field in value and (error := _check_value(value[field], checker, field, where)) is not None: return error
    return None


def _validate_model_ref(value: Any, where: str, field: str) -> str | None:
    if (error := _closed_object(value, frozenset({"model"}), f"{where} {field}", required=frozenset({"model"}))) is not None \
            or not isinstance(value["model"], str):
        return error or f"{where} {field} model must be a string"
    return None


_ACTION_SPEC = {"click": ("button x y", "keys", "button"), "double_click": ("x y keys", "", None),
                "drag": ("path", "keys", "path"), "keypress": ("keys", "", None), "move": ("x y", "keys", None),
                "screenshot": ("", "", None), "scroll": ("x y scroll_x scroll_y", "keys", None), "type": ("text", "", "text"), "wait": ("", "", None)}
_SAFETY_CHECK_KEYS = frozenset({"id", "code", "message"})


def _validate_computer_action(action: Any, where: str) -> str | None:
    kind = action.get("type") if isinstance(action, dict) else None
    if not isinstance(kind, str) or kind not in _ACTION_SPEC:
        return f"{where} computer action type is outside the pinned set"
    required, optional, special = _ACTION_SPEC[kind]
    allowed = {"type", *required.split(), *optional.split()}
    if set(action) - allowed or set(required.split()) - set(action):
        return f"{where} computer action members are invalid for {kind}"
    if any(c in action and not is_finite_number(action[c]) for c in ("x", "y", "scroll_x", "scroll_y")):
        return f"{where} computer action coordinates must be finite numbers"
    if special == "button" and action["button"] not in ("left", "right", "wheel", "back", "forward"):
        return f"{where} computer action button is outside left|right|wheel|back|forward"
    if special == "text" and not isinstance(action["text"], str):
        return f"{where} computer action text must be a string"
    if special == "path" and (not isinstance(action["path"], list) or not all(
            isinstance(p, dict) and set(p) == {"x", "y"} and is_finite_number(p["x"]) and is_finite_number(p["y"])
            for p in action["path"])):
        return f"{where} computer action path must be an array of finite x/y objects"
    if "keys" in action and (action["keys"] is None and kind == "keypress" or action["keys"] is not None
                             and (not isinstance(action["keys"], list) or not all(isinstance(k, str) for k in action["keys"]))):
        return f"{where} computer action keys must be a string array or null"
    return None


def _check_safety_checks(checks: Any, where: str) -> str | None:
    if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
        return f"{where} must be an array of objects"
    for check in checks:
        if (error := _closed_object(check, _SAFETY_CHECK_KEYS, f"{where} member", required=frozenset({"id"}))) is not None: return error
        if not isinstance(check["id"], str) or any(f in check and check[f] is not None and not isinstance(check[f], str)
                                                   for f in ("code", "message")):
            return f"{where} member id/code/message are invalid"
    return None


def _validate_computer_metadata(value: Any, where: str, result: bool) -> str | None:
    keys = frozenset({"type", "providerItemId", "actions", "pendingSafetyChecks"}) if not result else frozenset({"type", "screenshot", "acknowledgedSafetyChecks"})
    if (error := _closed_object(value, keys, where, required=keys)) is not None:
        return error
    if value["type"] != "computer":
        return f"{where} type must be computer"
    if result:
        screenshot = value["screenshot"]
        if not isinstance(screenshot, dict) or screenshot.get("type") != "computer_screenshot":
            return f"{where} screenshot must be a computer_screenshot object"
        if (error := _closed_object(screenshot, frozenset({"type", "image_url", "file_id"}), f"{where} screenshot",
                                    required=frozenset({"type"}))) is not None:
            return error
        if ("image_url" in screenshot) == ("file_id" in screenshot) \
                or not all(isinstance(screenshot[k], str) for k in ("image_url", "file_id") if k in screenshot):
            return f"{where} screenshot must carry exactly one string image_url|file_id"
        return _check_safety_checks(value["acknowledgedSafetyChecks"], f"{where} acknowledgedSafetyChecks")
    if not isinstance(value["providerItemId"], str):
        return f"{where} providerItemId must be a string"
    if not isinstance(value["actions"], list):
        return f"{where} actions must be an array"
    for action in value["actions"]:
        if (error := _validate_computer_action(action, where)) is not None:
            return error
    return _check_safety_checks(value["pendingSafetyChecks"], f"{where} pendingSafetyChecks")


_BLOCK_SHAPES = {
    "toolCall": (frozenset({"type", "id", "name", "arguments", "thoughtSignature", "intent", "rawBlock", "customWireName",
                            "providerMetadata"}), frozenset({"type", "id", "name", "arguments"}),
                 (("thoughtSignature", "str"), ("intent", "str"), ("rawBlock", "str"), ("customWireName", "str"),
                  ("providerMetadata", "computer_metadata"))),
    "thinking": (frozenset({"type", "thinking", "thinkingSignature", "itemId"}), frozenset({"type", "thinking"}),
                 (("thinking", "str"), ("thinkingSignature", "str"), ("itemId", "str"))),
    "redactedThinking": (frozenset({"type", "data"}), frozenset({"type", "data"}), (("data", "str"),)),
    "fallback": (frozenset({"type", "from", "to"}), frozenset({"type", "from", "to"}),
                 (("from", "model_ref"), ("to", "model_ref"))),
}


def _validate_assistant_block(block: Any, where: str) -> str | None:
    if not isinstance(block, dict):
        return f"{where} content blocks must be JSON objects"
    kind = block.get("type")
    if kind in ("text", "image"):
        return None  # already closed by the shared validator
    if kind in _BLOCK_SHAPES:
        return _validate_shape(block, *_BLOCK_SHAPES[kind], where=f"{kind} content block")
    if (error := _closed_object(block, frozenset({"type", "block"}), "anthropicServerTool content block",
                                required=frozenset({"type", "block"}))) is not None:
        return error
    inner = block["block"]
    if not isinstance(inner, dict):
        return "anthropicServerTool block must be a JSON object"
    if inner.get("type") == "server_tool_use":
        ok = is_nonempty_string(inner.get("id")) and inner.get("name") == "web_search" \
            and ("input" not in inner or inner["input"] is None or isinstance(inner["input"], dict))
        return None if ok else "server_tool_use block requires id, name web_search, and input object|null"
    if inner.get("type") == "web_search_tool_result":
        return None if is_nonempty_string(inner.get("tool_use_id")) and "content" in inner \
            else "web_search_tool_result block requires tool_use_id and content"
    return "anthropicServerTool block type is outside server_tool_use|web_search_tool_result"


_NESTED_SHAPES = {
    "contextSnapshot": (frozenset({"promptTokens", "nonMessageTokens", "historyRewriteTokensRemoved", "lastMessageTimestamp"}),
                        frozenset({"promptTokens", "nonMessageTokens"}),
                        (("promptTokens", "finite"), ("nonMessageTokens", "finite"), ("historyRewriteTokensRemoved", "finite"), ("lastMessageTimestamp", "finite"))),
    "providerPayload": (frozenset({"type", "provider", "dt", "items"}), frozenset({"type", "items"}),
                        (("type", "payload_type"), ("provider", "str"), ("dt", "bool"), ("items", "obj_list"))),
    "stopDetails": (frozenset({"type", "category", "explanation"}), frozenset({"type"}),
                    (("type", "str"), ("category", "str|null"), ("explanation", "str|null"))),
}


def _validate_retry_recovery(value: Any, where: str) -> str | None:
    if not isinstance(value, dict) or value.get("kind") != "auto-retry" \
            or value.get("recovery") not in ("credential", "model", "wait", "plain") \
            or not isinstance(value.get("note"), str) or not is_finite_number(value.get("attempt")):
        return f"{where} retryRecovery kind/recovery/note/attempt are invalid"
    status = value.get("status")
    if status not in ("recovered", "superseded"):
        return f"{where} retryRecovery status is outside recovered|superseded"
    keys = frozenset({"kind", "status", "attempt", "recoveredAt", "recovery", "note", "supersededBy"}) if status == "recovered" else frozenset({"kind", "status", "attempt", "recovery", "note"})
    required = keys if status == "superseded" else keys - frozenset({"supersededBy"})
    if (error := _closed_object(value, keys, f"{where} retryRecovery", required=required)) is not None:
        return error
    if status == "superseded" or not isinstance(value.get("recoveredAt"), str):
        return None if status == "superseded" else f"{where} retryRecovery recoveredAt must be a string"
    if (superseded := value.get("supersededBy")) is None:
        return None if "supersededBy" not in value else f"{where} retryRecovery supersededBy must not be null"
    if (error := _closed_object(superseded, frozenset({"timestamp", "responseId", "provider", "model"}),
                                f"{where} retryRecovery supersededBy",
                                required=frozenset({"timestamp", "provider", "model"}))) is not None \
            or not is_finite_number(superseded["timestamp"]) or not isinstance(superseded.get("provider"), str) \
            or not isinstance(superseded.get("model"), str) or ("responseId" in superseded and not isinstance(superseded["responseId"], str)):
        return error or f"{where} retryRecovery supersededBy members are invalid"
    return None


def _validate_message(obj: dict[str, Any], where: str) -> str | None:
    message = obj.get("message")
    if not isinstance(message, dict):
        return f"{where} message must be a JSON object"
    role = message.get("role")
    if role == "assistant":
        if (error := validate_closed_assistant_message(message)) is not None:
            return error
        for field, checker in (("responseId", "str"), ("upstreamProvider", "str"), ("errorMessage", "str"), ("errorStatus", "finite"),
                               ("errorId", "finite"), ("duration", "finite"), ("ttft", "finite"), ("disabledFeatures", "str_list"),
                               ("toolCallAbortMessages", "str_map")):
            if field in message and (error := _check_value(message[field], checker, field, "assistant message")) is not None:
                return error
        for block in (message.get("content") or ()):
            if (error := _validate_assistant_block(block, "assistant message")) is not None: return error
        for field in _NESTED_SHAPES:
            if field in message and (field != "stopDetails" or message[field] is not None) \
                    and (error := _validate_shape(message[field], *_NESTED_SHAPES[field], where=f"assistant message {field}")) is not None:
                return error
        if "retryRecovery" in message and (error := _validate_retry_recovery(message["retryRecovery"], "assistant message")) is not None:
            return error
        return _closed_object(message, _ASSISTANT_MESSAGE_KEYS, "assistant message", required=frozenset())
    if role in ("user", "developer"):
        keys = _USER_MESSAGE_KEYS if role == "user" else _DEVELOPER_MESSAGE_KEYS
        if (error := _closed_object(message, keys, f"{role} message", required=frozenset({"role", "content", "timestamp"}))) is not None:
            return error
        if not is_finite_number(message["timestamp"]):
            return f"{role} message timestamp must be a finite number"
        if (error := _validate_user_content(message["content"], f"{role} message")) is not None:
            return error
        if "attribution" in message and message["attribution"] not in ("user", "agent"):
            return f"{role} message attribution must be user or agent"
        for field, checker in (("synthetic", "bool"), ("steering", "bool")):
            if field in message and (error := _check_value(message[field], checker, field, f"{role} message")) is not None: return error
        if "providerPayload" in message and (error := _validate_shape(
                message["providerPayload"], *_NESTED_SHAPES["providerPayload"], where=f"{role} message providerPayload")) is not None: return error
        return None
    if role == "toolResult":
        if (error := _closed_object(message, _TOOL_RESULT_KEYS, "toolResult message", required=frozenset({"role", "toolCallId", "toolName", "content", "isError", "timestamp"}))) is not None:
            return error
        for field, checker in (("toolCallId", "nonempty_str"), ("toolName", "nonempty_str"), ("isError", "bool"), ("timestamp", "finite"),
                               ("prunedAt", "finite"), ("providerMetadata", "computer_result_metadata"), ("useless", "bool")):
            if field in message and (error := _check_value(message[field], checker, field, "toolResult message")) is not None: return error
        if (error := _validate_user_content(message["content"], "toolResult message", allow_string=False)) is not None \
                or ("attribution" in message and message["attribution"] not in ("user", "agent")):
            return error or "toolResult message attribution is invalid"
        if "providerPayload" in message and (error := _validate_shape(
                message["providerPayload"], *_NESTED_SHAPES["providerPayload"], where="toolResult message providerPayload")) is not None: return error
        return None
    return f"{where} message role is outside the pinned set"


_CHECKS = {
    "str": (lambda v: isinstance(v, str), "must be a string"),
    "nonempty_str": (is_nonempty_string, "must be a non-empty string"),
    "str|null": (lambda v: v is None or isinstance(v, str), "must be a string or null"),
    "bool": (lambda v: isinstance(v, bool), "must be a boolean"),
    "int": (is_integer, "must be an integer"),
    "obj": (lambda v: isinstance(v, dict), "must be a JSON object"),
    "obj|null": (lambda v: v is None or isinstance(v, dict), "must be a JSON object or null"),
    "str_map": (lambda v: isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items()),
                "must be an object of string to string"),
    "str_list": (lambda v: isinstance(v, list) and all(isinstance(i, str) for i in v), "must be an array of strings"),
    "obj_list": (lambda v: isinstance(v, list) and all(isinstance(i, dict) for i in v), "must be an array of objects"),
    "finite": (is_finite_number, "must be a finite number"),
    "title_source": (lambda v: v in ("auto", "user"), "must be auto or user"),
    "attribution": (lambda v: v in ("user", "agent"), "must be user or agent"),
    "schema_mode": (lambda v: v in ("permissive", "strict"), "must be permissive or strict"),
    "payload_type": (lambda v: v == "openaiResponsesHistory", "must be openaiResponsesHistory"),
    "service_tier": (lambda v: v is None or (isinstance(v, dict) and all(k in ("openai", "anthropic", "google") for k in v)
                     and all(x in ("auto", "default", "flex", "scale", "priority") for x in v.values())),
                     "must be null or a partial openai|anthropic|google tier mapping"),
}


def _check_value(value: Any, checker: str, field: str, where: str) -> str | None:
    if checker == "model_ref": return _validate_model_ref(value, where, field)
    if checker == "content": return _validate_user_content(value, where)
    if checker in ("computer_metadata", "computer_result_metadata"):
        return _validate_computer_metadata(value, f"{where} {field}", checker == "computer_result_metadata")
    predicate, message = _CHECKS[checker]
    if not predicate(value):
        return f"{where} {field} {message}"
    return None


def _validate_entry(obj: dict[str, Any]) -> str | None:
    kind = obj.get("type")
    if not isinstance(kind, str) or kind not in KNOWN_ENTRY_TYPES:
        return f"session entry type {kind!r} is outside the pinned union"
    extra, required, rules = _ENTRY_RULES[kind]
    if (error := _closed_object(obj, _BASE_KEYS | extra, f"{kind} session entry", required=_BASE_KEYS)) is not None \
            or not is_nonempty_string(obj["id"]) or (obj["parentId"] is not None and not isinstance(obj["parentId"], str)) \
            or not is_nonempty_string(obj["timestamp"]) or not _is_rfc3339(obj["timestamp"]):
        return error or "session entry id/parentId/timestamp are invalid"
    if kind == "message":
        return _validate_message(obj, "message")
    if (missing := required - set(obj)):
        return f"{kind} session entry is missing required member(s): {', '.join(sorted(missing))}"
    for field, checker in rules.items():
        if field in obj and (error := _check_value(obj[field], checker, field, f"{kind} session entry")) is not None:
            return error
    return None


def parse_journal_bytes(data: bytes, *, relpath: str) -> ParsedJournal:
    """Parse one journal's bytes; every malformed construct fails closed."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise OmpSessionError(f"{relpath}: journal is not valid UTF-8") from exc
    lines = text.split("\n")
    if lines and lines[-1] == "": lines.pop()
    if not lines or len(lines[0].encode("utf-8")) != 255: raise OmpSessionError(f"{relpath}: empty journal or title slot not exactly 256 bytes including LF")
    if len(lines) < 2: raise OmpSessionError(f"{relpath}: missing session header")
    title_slot = _validate_title_slot(_parse_object(lines[0], relpath, "title slot"), relpath)
    header = _validate_header(_parse_object(lines[1], relpath, "session header"), relpath)
    entries = []
    for line in lines[2:]:
        if not line.strip(): raise OmpSessionError(f"{relpath}: empty or whitespace journal line")
        obj = _parse_object(line, relpath, "session entry")
        if (error := _validate_entry(obj)) is not None: raise OmpSessionError(f"{relpath}: {error}")
        entries.append(SessionEntryRecord(obj["type"], obj["id"], obj["parentId"], obj["timestamp"], obj))
    return ParsedJournal(relpath, title_slot, header, tuple(entries))


def parse_journal(root_fd: int, relative_path: str) -> ParsedJournal:
    """Descriptor-relative no-follow read then parse; SafeTreeError propagates."""
    return parse_journal_bytes(read_regular_file(root_fd, relative_path), relpath=relative_path)


def select_primary(candidates, resume_arg: str) -> str:
    """Tiered case-insensitive selection: header-id, basename, after-first-underscore."""
    if not is_nonempty_string(resume_arg): raise OmpSessionError("resume argument must be a non-empty string")
    needle = resume_arg.lower()
    tiers: list[list[str]] = [[], [], []]
    for relpath, session_id in candidates:
        basename = relpath.rsplit("/", 1)[-1]
        tail = basename.split("_", 1)[1].lower() if "_" in basename else ""
        if str(session_id).lower().startswith(needle): tiers[0].append(relpath)
        elif basename.lower().startswith(needle): tiers[1].append(relpath)
        elif tail.startswith(needle): tiers[2].append(relpath)
    for tier in tiers:
        if len(tier) > 1: raise OmpSessionError(f"ambiguous primary match for {resume_arg!r}: {sorted(tier)}")
        if tier: return tier[0]
    raise OmpSessionError(f"no session matches resume argument {resume_arg!r}")


def validate_session_graph(entries) -> None:
    """Strict X8 724 graph: nonempty, unique ids, one null-parent root, parents precede children."""
    if not entries: raise OmpSessionError("session graph must be non-empty")
    seen: set[str] = set()
    roots = 0
    for entry in entries:
        if entry.id in seen or (entry.parent_id is not None and entry.parent_id not in seen):
            raise OmpSessionError(f"duplicate id or parent not preceding: {entry.id!r}")
        roots += entry.parent_id is None; seen.add(entry.id)
    if roots != 1: raise OmpSessionError(f"session graph must have exactly one null-parent root, found {roots}")


def build_session_tree(entries) -> tuple[SessionNode, ...]:
    """Build the branch forest; the strict X8 graph rules are enforced."""
    validate_session_graph(entries)
    root = next(entry for entry in entries if entry.parent_id is None)
    children: dict[str, list[SessionEntryRecord]] = {}
    for entry in entries:
        if entry.parent_id is not None: children.setdefault(entry.parent_id, []).append(entry)
    nodes: dict[str, SessionNode] = {}
    for entry in reversed(entries):
        kids = sorted(children.get(entry.id, ()), key=lambda child: (child.timestamp, child.id))
        nodes[entry.id] = SessionNode(entry, tuple(nodes[kid.id] for kid in kids))
    return (nodes[root.id],)


def path_to_root(entries, entry_id: str) -> tuple[SessionEntryRecord, ...]:
    """Return the ancestry of one entry, root-first (X8 724)."""
    validate_session_graph(entries)
    by_id = {entry.id: entry for entry in entries}
    if entry_id not in by_id: raise OmpSessionError(f"no session entry with id {entry_id!r}")
    chain = []
    while entry_id is not None:
        chain.append(by_id[entry_id]); entry_id = by_id[entry_id].parent_id
    return tuple(reversed(chain))


def session_leaf(entries) -> SessionEntryRecord:
    """Return the active leaf: the last entry in file order (X8)."""
    if not entries: raise OmpSessionError("cannot select a leaf from an empty journal")
    return entries[-1]


SESSION_MANIFEST_SCHEMA = "omp_session_manifest.v1"


@dataclass(frozen=True, slots=True)
class SessionManifestRow:
    """One session-tree file: path, size, sha256, actual permission mode (octal string)."""
    relative_path: str; size_bytes: int; sha256: str; mode: str


@dataclass(frozen=True, slots=True)
class SessionManifest:
    """Canonical live/snapshot session-tree manifest (X8 745)."""
    rows: tuple[SessionManifestRow, ...]; manifest_bytes: bytes; manifest_sha256: str


def build_session_manifest(root_fd: int) -> SessionManifest:
    """Canonical descriptor-safe manifest: no-follow walk/read, actual modes, closed on SafeTreeError."""
    try:
        rows = sorted(walk_regular_files(root_fd), key=lambda row: row.relative_path.encode("utf-8"))
        content = {row.relative_path: read_regular_file(root_fd, row.relative_path, expected=row) for row in rows}
    except SafeTreeError as exc:
        raise OmpSessionError(str(exc)) from exc
    records = tuple(SessionManifestRow(row.relative_path, len(content[row.relative_path]),
                                       hashlib.sha256(content[row.relative_path]).hexdigest(),
                                       f"{stat.S_IMODE(row.mode):04o}") for row in rows)
    files = [{"mode": r.mode, "path": r.relative_path, "sha256": r.sha256, "size": r.size_bytes} for r in records]
    manifest_bytes = json.dumps({"schema_version": SESSION_MANIFEST_SCHEMA, "files": files},
                                sort_keys=True, separators=(",", ":")).encode("utf-8")
    return SessionManifest(records, manifest_bytes, hashlib.sha256(manifest_bytes).hexdigest())
