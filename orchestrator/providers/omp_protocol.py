"""Closed OMP JSON protocol validators for the pinned state machine (X3)."""
from __future__ import annotations

import json
import math
import os
import re
from types import MappingProxyType
from typing import Any, Mapping

from .types import OmpTransportExpectation

_RFC3339_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")
_HEX64_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_BASE64_PATTERN = re.compile(r"^[A-Za-z0-9+/]*={0,2}$")
_HEADER_REQUIRED = frozenset({"type", "id", "timestamp", "cwd"})
_HEADER_ALLOWED = _HEADER_REQUIRED | frozenset({"version", "title", "titleSource", "parentSession", "providerPromptCacheKey", "additionalDirectories", "previousSessionFiles"})
_ASSISTANT_MESSAGE_REQUIRED = frozenset({"role", "api", "provider", "model", "timestamp", "stopReason", "content", "usage"})
_USAGE_CORE = frozenset({"input", "output", "cacheRead", "cacheWrite", "totalTokens", "cost"})
_USAGE_OPTIONAL = frozenset({"contextTokens", "premiumRequests", "reasoningTokens", "orchestration", "cttl", "server"})
_USAGE_COST_KEYS = frozenset({"input", "output", "cacheRead", "cacheWrite", "total"})
_ORCHESTRATION_KEYS = frozenset({"input", "cacheRead", "output"})
_CTTL_KEYS = frozenset({"ephemeral5m", "ephemeral1h"})
_SERVER_KEYS = frozenset({"webSearch", "webFetch"})
_STOP_REASONS = frozenset({"stop", "length", "toolUse", "error", "aborted"})
_IMAGE_DETAILS = frozenset({"auto", "low", "high", "original"})
_FRAME_REQUIRED = frozenset({"type", "lane", "persistence", "binary", "child", "session", "conf", "confinement", "observed"})
_FRAME_LANES = frozenset({"ambient", "ambient-unrestricted", "no-tools", "conf", "conf-inference"})
_FRAME_SESSION_KEYS = frozenset({"id", "visit_key", "primary_relpath", "primary_sha256"})
_FRAME_CHILD_KEYS = frozenset({"argv", "cwd", "env_names", "exit_code"})
_FRAME_CONFINEMENT_KEYS = frozenset({"schema_version", "landlock_abi", "policy_sha256"})
_CONFINEMENT_SCHEMA_VERSION = "omp_write_confinement.v1"
_MIN_LANDLOCK_ABI = 3
_FRAME_OBSERVED_KEYS = frozenset({"advisor_relpaths", "child_relpaths"})
_FRAME_CONF_KEYS = frozenset({"manifest_sha256"})
_EVENT_TYPES = frozenset({"agent_start", "turn_start", "tool_execution_start", "tool_execution_update", "tool_execution_end", "message_start", "message_update", "message_end", "turn_end", "agent_end", "custom", "orchestrator.omp_launch.v1"})
_UPDATE_EVENT_TYPES = frozenset({"start", "text_start", "text_delta", "thinking_start", "thinking_delta", "toolcall_start", "text_end", "thinking_end", "image_end", "toolcall_end", "done", "error"})
_INDEX_EVENT_TYPES = frozenset({"text_start", "text_delta", "thinking_start", "thinking_delta", "toolcall_start"})
_CONTENT_END_TYPES = frozenset({"text_end", "thinking_end"})
_DONE_REASONS = frozenset({"stop", "length", "toolUse"})
_ERROR_REASONS = frozenset({"error", "aborted"})
_TOOL_EVENTS = {
    "tool_execution_start": (frozenset({"type", "toolCallId", "toolName", "args", "intent"}), frozenset({"type", "toolCallId", "toolName", "args"}), "isError"),
    "tool_execution_update": (frozenset({"type", "toolCallId", "toolName", "args", "partialResult"}), frozenset({"type", "toolCallId", "toolName", "args"}), "isError"),
    "tool_execution_end": (frozenset({"type", "toolCallId", "toolName", "result", "isError"}), frozenset({"type", "toolCallId", "toolName", "result"}), "isError"),
}
_TOOL_FLAG_ONLY = {"tool_execution_end": "isError"}


def is_event_type(value: Any) -> bool:
    """Return whether one discriminator is an admitted OMP event type."""
    return value in _EVENT_TYPES


def is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value)


def is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def is_nonnegative_number(value: Any) -> bool:
    return is_finite_number(value) and value >= 0


def is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def loads_strict(text: str) -> dict[str, Any]:
    """Parse one transport line rejecting duplicate keys and non-finite numbers."""
    def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate JSON object key")
        return dict(pairs)

    def _reject_constant(value: str) -> Any:
        raise ValueError(f"non-finite JSON number {value!r}")

    try:
        parsed = json.loads(text, object_pairs_hook=_reject_duplicate_pairs, parse_constant=_reject_constant)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f"line is not one strict JSON object: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("transport line must be a JSON object")
    return parsed


def _unknown_keys(obj: Mapping[str, Any], allowed: frozenset[str]) -> list[str]:
    return sorted(str(key) for key in set(obj) - allowed)


def _closed_object(obj: Any, allowed: frozenset[str], where: str, *, required: frozenset[str] = frozenset()) -> str | None:
    if not isinstance(obj, dict):
        return f"{where} must be a JSON object"
    unknown = _unknown_keys(obj, allowed)
    if unknown:
        return f"{where} has unknown member(s): {', '.join(unknown)}"
    missing = required - set(obj)
    if missing:
        return f"{where} is missing required member(s): {', '.join(sorted(missing))}"
    return None


def validate_session_header(obj: Any) -> str | None:
    error = _closed_object(obj, _HEADER_ALLOWED, "session header", required=_HEADER_REQUIRED)
    if error is not None:
        return error
    if not is_nonempty_string(obj["id"]):
        return "session header id must be a non-empty string"
    if not is_nonempty_string(obj["timestamp"]) or _RFC3339_PATTERN.fullmatch(obj["timestamp"]) is None:
        return "session header timestamp must be an RFC 3339 string"
    if not is_nonempty_string(obj["cwd"]) or not os.path.isabs(obj["cwd"]):
        return "session header cwd must be an absolute path string"
    if "version" in obj and not is_integer(obj["version"]):
        return "session header version must be an integer"
    for key in ("title", "parentSession", "providerPromptCacheKey"):
        if key in obj and not isinstance(obj[key], str):
            return f"session header {key} must be a string"
    if "titleSource" in obj and obj["titleSource"] not in {"auto", "user"}:
        return "session header titleSource must be auto or user"
    for key in ("additionalDirectories", "previousSessionFiles"):
        if key in obj and (not isinstance(obj[key], list) or any(not isinstance(item, str) for item in obj[key])):
            return f"session header {key} must be an array of strings"
    return None


def validate_only_type(obj: Any, event_type: str) -> str | None:
    return _closed_object(obj, frozenset({"type"}), f"{event_type} event")


def _validate_tool_event(obj: Any, name: str) -> str | None:
    allowed, required, _flag = _TOOL_EVENTS[name]
    error = _closed_object(obj, allowed, f"{name} event", required=required)
    if error is not None:
        return error
    for key in ("toolCallId", "toolName"):
        if not is_nonempty_string(obj.get(key)):
            return f"{name} {key} must be a non-empty string"
    flag = _TOOL_FLAG_ONLY.get(name)
    if flag and flag in obj and not isinstance(obj[flag], bool):
        return f"{name} {flag} must be a boolean"
    return None


def validate_tool_execution_start(obj: Any) -> str | None:
    return _validate_tool_event(obj, "tool_execution_start")


def validate_tool_execution_update(obj: Any) -> str | None:
    return _validate_tool_event(obj, "tool_execution_update")


def validate_tool_execution_end(obj: Any) -> str | None:
    return _validate_tool_event(obj, "tool_execution_end")


def _message_role_error(message: Any, where: str) -> str | None:
    if not isinstance(message, dict):
        return f"{where} message must be a JSON object"
    if not is_nonempty_string(message.get("role")):
        return f"{where} message role must be a non-empty string"
    return None


def _validate_message_event(obj: Any, where: str) -> str | None:
    error = _closed_object(obj, frozenset({"type", "message"}), f"{where} event", required=frozenset({"type", "message"}))
    if error is not None:
        return error
    return _message_role_error(obj["message"], where)


def validate_message_start(obj: Any) -> str | None:
    return _validate_message_event(obj, "message_start")


def validate_message_end(obj: Any) -> str | None:
    return _validate_message_event(obj, "message_end")


def validate_message_update(obj: Any) -> str | None:
    error = _closed_object(obj, frozenset({"type", "assistantMessageEvent"}), "message_update event", required=frozenset({"type", "assistantMessageEvent"}))
    if error is not None:
        return error
    event = obj["assistantMessageEvent"]
    if not isinstance(event, dict):
        return "message_update assistantMessageEvent must be a JSON object"
    event_type = event.get("type")
    if not is_nonempty_string(event_type) or event_type not in _UPDATE_EVENT_TYPES:
        return "assistantMessageEvent type is outside the pinned union"
    if event_type in _INDEX_EVENT_TYPES:
        allowed = frozenset({"type", "contentIndex", "delta"})
    elif event_type in _CONTENT_END_TYPES:
        allowed = frozenset({"type", "contentIndex", "content"})
    elif event_type == "image_end":
        allowed = frozenset({"type", "content"})
    elif event_type == "toolcall_end":
        allowed = frozenset({"type", "toolCall"})
    elif event_type in {"done", "error"}:
        allowed = frozenset({"type", "reason"})
    else:
        allowed = frozenset({"type"})
    error = _closed_object(event, allowed, f"assistantMessageEvent {event_type}")
    if error is not None:
        return error
    if event_type in _INDEX_EVENT_TYPES:
        if not is_integer(event.get("contentIndex")) or event["contentIndex"] < 0:
            return f"{event_type} contentIndex must be a non-negative integer"
        if event_type.endswith("_delta") and not isinstance(event.get("delta"), str):
            return f"{event_type} delta must be a string"
    elif event_type in _CONTENT_END_TYPES:
        if not isinstance(event.get("content"), str):
            return f"{event_type} content must be a string"
    elif event_type == "image_end":
        return _validate_image_object(event.get("content"))
    elif event_type == "toolcall_end":
        return _validate_tool_call_object(event.get("toolCall"))
    else:
        expected = _DONE_REASONS if event_type == "done" else _ERROR_REASONS
        if event.get("reason") not in expected:
            return f"{event_type} reason is outside the pinned set"
    return None


def validate_closed_assistant_message(message: Any) -> str | None:
    if not isinstance(message, dict):
        return "closed assistant message must be a JSON object"
    if message.get("role") != "assistant":
        return "closed assistant message role must be assistant"
    missing = _ASSISTANT_MESSAGE_REQUIRED - set(message)
    if missing:
        return "closed assistant message is missing member(s): " + ", ".join(sorted(missing))
    for key in ("api", "provider", "model"):
        if not is_nonempty_string(message.get(key)):
            return f"closed assistant message {key} must be a non-empty string"
    if not is_finite_number(message.get("timestamp")):
        return "closed assistant message timestamp must be a finite number"
    if message.get("stopReason") not in _STOP_REASONS:
        return "closed assistant message stopReason is outside the pinned set"
    content = message.get("content")
    if not isinstance(content, list):
        return "closed assistant message content must be an array"
    for block in content:
        block_error = validate_content_block(block)
        if block_error is not None:
            return block_error
    return validate_usage(message.get("usage"))


def validate_content_block(block: Any) -> str | None:
    if not isinstance(block, dict):
        return "assistant content block must be a JSON object"
    kind = block.get("type")
    if not is_nonempty_string(kind):
        return "assistant content block type must be a non-empty string"
    if kind == "text":
        error = _closed_object(block, frozenset({"type", "text", "textSignature"}), "text content block", required=frozenset({"type", "text"}))
        if error is not None:
            return error
        if not isinstance(block.get("text"), str):
            return "text content block text must be a string"
        if "textSignature" in block and not isinstance(block["textSignature"], str):
            return "text content block textSignature must be a string"
        return None
    if kind == "image":
        return _validate_image_object(block)
    if kind in {"tool_call", "tool_use"}:
        return _validate_tool_call_object(block)
    # Other pinned non-text block kinds are accepted but contribute no output.
    return None


def _validate_image_object(image: Any) -> str | None:
    error = _closed_object(image, frozenset({"type", "data", "mimeType", "detail"}), "image content object", required=frozenset({"type", "data", "mimeType"}))
    if error is not None:
        return error
    if not is_nonempty_string(image.get("data")) or len(image["data"]) % 4 != 0 or _BASE64_PATTERN.fullmatch(image["data"]) is None:
        return "image content object data must be a base64 string"
    if not is_nonempty_string(image.get("mimeType")):
        return "image content object mimeType must be a non-empty string"
    if "detail" in image and image["detail"] not in _IMAGE_DETAILS:
        return "image content object detail is outside auto|low|high|original"
    return None


def _validate_tool_call_object(tool_call: Any) -> str | None:
    error = _closed_object(tool_call, frozenset({"type", "id", "name", "arguments"}), "tool-call object", required=frozenset({"id", "name", "arguments"}))
    if error is not None:
        return error
    for key in ("id", "name"):
        if not is_nonempty_string(tool_call.get(key)):
            return f"tool-call object {key} must be a non-empty string"
    if not isinstance(tool_call.get("arguments"), dict):
        return "tool-call object arguments must be a JSON object"
    return None


def validate_usage(usage: Any) -> str | None:
    if not isinstance(usage, dict):
        return "usage must be a JSON object"
    unknown = _unknown_keys(usage, _USAGE_CORE | _USAGE_OPTIONAL)
    if unknown:
        return f"usage has unknown member(s): {', '.join(unknown)}"
    missing = _USAGE_CORE - set(usage)
    if missing:
        return "usage is missing core member(s): " + ", ".join(sorted(missing))
    for key in _USAGE_CORE - frozenset({"cost"}):
        if not is_nonnegative_number(usage.get(key)):
            return f"usage {key} must be a finite non-negative number"
    cost = usage.get("cost")
    if not isinstance(cost, dict):
        return "usage cost must be a JSON object"
    cost_unknown = _unknown_keys(cost, _USAGE_COST_KEYS)
    if cost_unknown:
        return f"usage cost has unknown member(s): {', '.join(cost_unknown)}"
    for key in _USAGE_COST_KEYS:
        if key not in cost:
            return f"usage cost is missing {key}"
        if not is_nonnegative_number(cost[key]):
            return f"usage cost {key} must be a finite non-negative number"
    for key in ("contextTokens", "premiumRequests", "reasoningTokens"):
        if key in usage and not is_nonnegative_number(usage[key]):
            return f"usage {key} must be a finite non-negative number"
    for group, keys in (("orchestration", _ORCHESTRATION_KEYS), ("cttl", _CTTL_KEYS), ("server", _SERVER_KEYS)):
        if group not in usage:
            continue
        group_value = usage[group]
        if not isinstance(group_value, dict):
            return f"usage {group} must be a JSON object"
        group_unknown = _unknown_keys(group_value, keys)
        if group_unknown:
            return f"usage {group} has unknown member(s): " + ", ".join(group_unknown)
        for key in keys:
            if key in group_value and not is_nonnegative_number(group_value[key]):
                return f"usage {group}.{key} must be a finite non-negative number"
    return None


def validate_turn_end(obj: Any) -> str | None:
    error = _closed_object(obj, frozenset({"type", "message", "toolResults"}), "turn_end event", required=frozenset({"type", "message", "toolResults"}))
    if error is not None:
        return error
    if not isinstance(obj["message"], dict):
        return "turn_end message must be a JSON object"
    if not isinstance(obj["toolResults"], list):
        return "turn_end toolResults must be an array"
    return None


def validate_agent_end(obj: Any) -> str | None:
    error = _closed_object(obj, frozenset({"type", "messages", "isTerminal", "telemetry", "coverage"}), "agent_end event", required=frozenset({"type", "messages"}))
    if error is not None:
        return error
    if not isinstance(obj["messages"], list):
        return "agent_end messages must be an array"
    if "isTerminal" in obj and not isinstance(obj["isTerminal"], bool):
        return "agent_end isTerminal must be a boolean"
    for key in ("telemetry", "coverage"):
        if key in obj and not isinstance(obj[key], dict):
            return f"agent_end {key} must be a JSON object"
    return None


def validate_custom(obj: Any) -> str | None:
    error = _closed_object(obj, frozenset({"type", "message"}), "custom event", required=frozenset({"type", "message"}))
    if error is not None:
        return error
    return _message_role_error(obj["message"], "custom")


def validate_launch_frame(obj: Any, expectation: OmpTransportExpectation, *, header_session_id: str) -> str | None:
    error = _closed_object(obj, _FRAME_REQUIRED, "adapter launch frame", required=_FRAME_REQUIRED)
    if error is not None:
        return error
    if obj["lane"] != expectation.lane:
        return "adapter launch frame lane does not match the expectation"
    if obj["persistence"] != expectation.persistence:
        return "adapter launch frame persistence does not match the expectation"
    if obj["lane"] not in _FRAME_LANES:
        return "adapter launch frame lane is outside the pinned set"
    if obj["persistence"] not in {"none", "fresh"}:
        return "adapter launch frame persistence must be none or fresh"
    if obj["binary"] != expectation.binary:
        return "adapter launch frame binary pin does not match the expectation"
    child_error = _validate_frame_child(obj["child"])
    if child_error is not None:
        return child_error
    if expectation.child_argv and tuple(obj["child"]["argv"]) != expectation.child_argv:
        return "adapter launch frame child argv does not match the expectation"
    session_error = _validate_frame_session(obj["session"], expectation, header_session_id=header_session_id)
    if session_error is not None:
        return session_error
    conf = obj["conf"]
    if not isinstance(conf, dict) or _unknown_keys(conf, _FRAME_CONF_KEYS) or "manifest_sha256" not in conf:
        return "adapter launch frame conf must be a closed object"
    if conf.get("manifest_sha256") != expectation.conf_manifest_sha256:
        return "adapter launch frame conf digest does not match the expectation"
    confinement_error = _validate_frame_confinement(obj["confinement"], expectation)
    if confinement_error is not None:
        return confinement_error
    observed = obj["observed"]
    if not isinstance(observed, dict) or _unknown_keys(observed, _FRAME_OBSERVED_KEYS):
        return "adapter launch frame observed must be a closed object"
    for key in ("advisor_relpaths", "child_relpaths"):
        value = observed.get(key)
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            return f"adapter launch frame observed.{key} must be an array of strings"
    if tuple(observed["child_relpaths"]) != expectation.observed_relpaths:
        return "adapter launch frame observed inventory does not match the expectation"
    if obj["persistence"] == "fresh":
        primary = obj["session"].get("primary_relpath")
        if primary not in observed["child_relpaths"]:
            return "adapter launch frame observed inventory must contain the primary session file"
    return None


def _validate_frame_child(child: Any) -> str | None:
    error = _closed_object(child, _FRAME_CHILD_KEYS, "adapter launch frame child", required=_FRAME_CHILD_KEYS)
    if error is not None:
        return error
    argv = child["argv"]
    if not isinstance(argv, list) or any(not isinstance(token, str) for token in argv):
        return "adapter launch frame child argv must be an array of strings"
    if not isinstance(child["cwd"], str) or not os.path.isabs(child["cwd"]):
        return "adapter launch frame child cwd must be an absolute path string"
    env_names = child["env_names"]
    if not isinstance(env_names, list) or any(not isinstance(name, str) or not name for name in env_names) or env_names != sorted(env_names):
        return "adapter launch frame child env_names must be a sorted array of non-empty strings"
    if not is_integer(child.get("exit_code")):
        return "adapter launch frame child exit_code must be an integer"
    return None


def _validate_frame_session(session: Any, expectation: OmpTransportExpectation, *, header_session_id: str) -> str | None:
    error = _closed_object(session, _FRAME_SESSION_KEYS, "adapter launch frame session", required=_FRAME_SESSION_KEYS)
    if error is not None:
        return error
    if not is_nonempty_string(session["id"]):
        return "adapter launch frame session id must be a non-empty string"
    if session["id"] != header_session_id:
        return "adapter launch frame session id does not match the session header"
    if expectation.stdout_session_id is not None and session["id"] != expectation.stdout_session_id:
        return "adapter launch frame session id does not match the expectation"
    if session.get("visit_key") != expectation.visit_key:
        return "adapter launch frame visit key does not match the expectation"
    for key in ("primary_relpath", "primary_sha256"):
        value = session.get(key)
        if expectation.persistence == "fresh":
            if not is_nonempty_string(value):
                return f"adapter launch frame session {key} must be non-null for fresh persistence"
            if key == "primary_sha256" and _HEX64_PATTERN.fullmatch(value) is None:
                return "adapter launch frame primary_sha256 must be 64 lowercase hex"
        elif value is not None:
            return f"adapter launch frame session {key} must be null for transient persistence"
    return None


def _validate_frame_confinement(confinement: Any, expectation: OmpTransportExpectation) -> str | None:
    policy_sha256 = expectation.confinement_policy_sha256
    if policy_sha256 is None:
        if confinement is not None:
            return "adapter launch frame confinement must be null for this lane"
        return None
    error = _closed_object(confinement, _FRAME_CONFINEMENT_KEYS, "adapter launch frame confinement", required=_FRAME_CONFINEMENT_KEYS)
    if error is not None:
        return error
    if confinement.get("schema_version") != _CONFINEMENT_SCHEMA_VERSION:
        return "adapter launch frame confinement schema_version is unsupported"
    abi = confinement.get("landlock_abi")
    if not is_integer(abi) or abi < _MIN_LANDLOCK_ABI:
        return f"adapter launch frame confinement landlock_abi must be an integer of at least {_MIN_LANDLOCK_ABI}"
    if confinement.get("policy_sha256") != policy_sha256:
        return "adapter launch frame confinement policy digest does not match the expectation"
    return None


def freeze_frame(frame: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a deeply frozen copy of one validated adapter launch frame."""
    return MappingProxyType({key: _freeze_value(value) for key, value in frame.items()})


def _freeze_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_value(item) for key, item in value.items()})
    if isinstance(value, list):
        return tuple(_freeze_value(item) for item in value)
    return value
