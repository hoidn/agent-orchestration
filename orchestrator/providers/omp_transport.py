"""Incremental OMP JSON stdout transport state machine (pinned X3).

``OmpJsonStdoutAccumulator`` owns the four ordered states
``awaiting_header -> streaming -> terminal_seen -> frame_seen`` and the
credential-minimized metadata projection. Raw stdout bytes are only held in
memory; the adapter launch frame is validated against the immutable
parent-derived ``OmpTransportExpectation``.
"""
from __future__ import annotations

import copy
import threading
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping

from .omp_protocol import (
    freeze_frame,
    is_event_type,
    is_nonempty_string,
    loads_strict,
    validate_agent_end,
    validate_closed_assistant_message,
    validate_custom,
    validate_launch_frame,
    validate_message_end,
    validate_message_start,
    validate_message_update,
    validate_only_type,
    validate_session_header,
    validate_tool_execution_end,
    validate_tool_execution_start,
    validate_tool_execution_update,
    validate_turn_end,
)
from .types import OmpTransportExpectation

_TRANSPORT_ERROR_TYPE = "provider_session_transport_error"
_FRAME_EVENT_TYPE = "orchestrator.omp_launch.v1"
_TransportState = Literal["awaiting_header", "streaming", "terminal_seen", "frame_seen"]


def _unfreeze_value(value: Any) -> Any:
    """Recursively thaw frozen MappingProxyType/tuple values to plain containers."""
    if isinstance(value, MappingProxyType):
        return {key: _unfreeze_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_unfreeze_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _unfreeze_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_unfreeze_value(item) for item in value]
    return value


class OmpJsonStdoutAccumulator:
    """Incrementally parse pinned OMP JSON stdout without altering it."""

    def __init__(self, *, expectation: OmpTransportExpectation, assistant_text_callback: Callable[[str], None] | None = None) -> None:
        self._expectation = expectation
        self._assistant_text_callback = assistant_text_callback
        self._buffer = bytearray()
        self._state: _TransportState = "awaiting_header"
        self._session_id: str | None = None
        self._event_count = 0
        self._line_number = 0
        self._open_role: str | None = None
        self._pending_error_stop_reason: str | None = None
        self._text_parts: list[str] = []
        self._message_rows: list[dict[str, Any]] = []
        self._final_provider: str | None = None
        self._final_model: str | None = None
        self._last_closed_assistant: dict[str, Any] | None = None
        self._settlement_seen = False
        self._frame: Mapping[str, Any] | None = None
        self._invalid_error: dict[str, Any] | None = None
        self._eof_tail_parsed = False
        self._settled = False
        self._settled_metadata: dict[str, Any] | None = None
        self._settled_error: dict[str, Any] | None = None
        self._pending_emission: str | None = None
        self._lock = threading.RLock()

    @property
    def event_count(self) -> int:
        """Return the number of child event objects after the header."""
        with self._lock:
            return self._event_count

    @property
    def normalized_stdout(self) -> str:
        """Return joined authoritative assistant text (display-safe use only)."""
        with self._lock:
            return "\n".join(self._text_parts)

    def feed(self, chunk: bytes) -> None:
        """Feed one arbitrary raw stdout chunk into the strict line buffer."""
        if not isinstance(chunk, bytes):
            raise TypeError("OMP transport chunks must be bytes")
        if not chunk:
            return
        emitted: list[str] = []
        with self._lock:
            if self._settled:
                raise RuntimeError("OMP transport accumulator is settled")
            if self._invalid_error is not None:
                return
            self._buffer.extend(chunk)
            while self._invalid_error is None:
                newline_offset = self._buffer.find(b"\n")
                if newline_offset < 0:
                    break
                raw_line = bytes(self._buffer[:newline_offset])
                del self._buffer[: newline_offset + 1]
                self._line_number += 1
                assistant_text = self._consume_line(raw_line)
                if assistant_text is not None:
                    emitted.append(assistant_text)
        self._emit_assistant_text(emitted)

    def snapshot(self):
        """Return the immutable in-flight identity/terminal view."""
        from .session_transport import SessionIdentitySnapshot

        with self._lock:
            error = (MappingProxyType({key: _freeze_snapshot_value(value) for key, value in self._invalid_error.items()}) if self._invalid_error is not None else None)
            terminal_seen = self._state in {"terminal_seen", "frame_seen"}
            session_ids = (self._session_id,) if self._session_id is not None else ()
            if self._invalid_error is not None:
                return SessionIdentitySnapshot(status="invalid", session_ids=session_ids, terminal_seen=terminal_seen, error=error)
            if self._session_id is None:
                return SessionIdentitySnapshot(status="missing", session_ids=(), terminal_seen=terminal_seen, error=None)
            return SessionIdentitySnapshot(status="unique", session_ids=session_ids, terminal_seen=terminal_seen, error=None)

    def finalize(self, *, expected_session_id: str | None, require_terminal: bool) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """Parse the EOF tail and apply the requested finality level.

        ``require_terminal=False`` observations parse the final non-LF object
        and return a provisional view without settling; the mandatory
        ``require_terminal=True`` call re-runs every terminal/frame check and
        is idempotent.
        """
        emitted: list[str] = []
        with self._lock:
            if self._settled:
                return copy.deepcopy(self._settled_metadata), copy.deepcopy(self._settled_error)
            if not self._eof_tail_parsed and self._invalid_error is None:
                self._eof_tail_parsed = True
                raw_tail = bytes(self._buffer)
                self._buffer.clear()
                if raw_tail:
                    self._line_number += 1
                    assistant_text = self._consume_line(raw_tail)
                    if assistant_text is not None:
                        emitted.append(assistant_text)
        self._emit_assistant_text(emitted)
        with self._lock:
            if not require_terminal:
                return self._provisional_result()
            if self._invalid_error is not None:
                self._settled = True
                self._settled_error = copy.deepcopy(self._invalid_error)
                return None, self._settled_error
            error = self._mandatory_checks()
            metadata = self._build_metadata() if error is None else None
            self._settled = True
            self._settled_metadata = metadata
            self._settled_error = error
            return (copy.deepcopy(metadata) if metadata is not None else None, copy.deepcopy(error) if error is not None else None)

    def _fail(self, message: str, **context: Any) -> None:
        self._invalidate(message, context)

    def _consume_line(self, raw_line: bytes) -> str | None:
        """Validate one line and return assistant text to emit, if any."""
        if not raw_line:
            return None
        if not raw_line.strip():
            self._fail("OMP transport line contains only whitespace", line=self._line_number)
            return None
        try:
            event = loads_strict(raw_line.decode("utf-8", errors="strict"))
        except UnicodeDecodeError as exc:
            self._fail("OMP transport is not valid UTF-8", line=self._line_number, error=str(exc))
            return None
        except ValueError as exc:
            self._fail("OMP transport line is not one strict JSON object", line=self._line_number, error=str(exc))
            return None
        event_type = event.get("type")
        if not is_nonempty_string(event_type):
            self._fail("OMP transport event type must be a non-empty string", line=self._line_number)
            return None
        if self._state == "awaiting_header":
            self._consume_header(event, event_type)
        elif event_type == "session":
            self._fail("OMP transport has a duplicate session header", line=self._line_number)
        elif self._state == "frame_seen":
            self._fail("OMP transport has a non-empty object after the adapter frame", line=self._line_number)
        elif event_type == _FRAME_EVENT_TYPE:
            # The adapter frame is metadata, not a child event.
            self._consume_frame(event)
        else:
            self._event_count += 1
            if not is_event_type(event_type):
                # Opaque forward-compatibility envelope: count only.
                pass
            elif self._state == "terminal_seen":
                self._consume_post_terminal(event, event_type)
            else:
                self._consume_streaming_event(event, event_type)
        emission = self._pending_emission
        self._pending_emission = None
        return emission

    def _consume_header(self, event: dict[str, Any], event_type: str) -> None:
        if event_type != "session":
            self._fail("OMP transport first object must be the sole session header", line=self._line_number)
            return
        error = validate_session_header(event)
        if error is not None:
            self._fail("OMP transport session header is invalid", line=self._line_number, error=error)
            return
        self._session_id = event["id"]
        self._state = "streaming"

    def _consume_frame(self, event: dict[str, Any]) -> None:
        if self._state != "terminal_seen":
            self._fail("OMP adapter frame must follow settlement", line=self._line_number)
            return
        if self._open_role is not None:
            self._fail("OMP adapter frame arrives with an open message lifecycle", line=self._line_number)
            return
        error = validate_launch_frame(event, self._expectation, header_session_id=(self._session_id if self._session_id is not None else ""))
        if error is not None:
            self._fail("OMP adapter launch frame does not match the expectation", line=self._line_number, error=error)
            return
        self._frame = freeze_frame(event)
        self._state = "frame_seen"

    def _consume_post_terminal(self, event: dict[str, Any], event_type: str) -> None:
        if event_type == "agent_end":
            error = validate_agent_end(event)
            if error is not None:
                self._fail("Repeated terminal agent_end is malformed", line=self._line_number, error=error)
                return
            if event.get("isTerminal", True) is False:
                # Nonterminal returns to streaming; a later terminal is
                # still required before the adapter frame.
                self._state = "streaming"
            return
        if event_type == "custom":
            self._consume_custom(event, late=True)
            return
        self._fail("OMP transport event is not legal after settlement", line=self._line_number, event_type=event_type)

    def _consume_streaming_event(self, event: dict[str, Any], event_type: str) -> None:
        if event_type in {"agent_start", "turn_start"}:
            error = validate_only_type(event, event_type)
        elif event_type == "tool_execution_start":
            error = validate_tool_execution_start(event)
        elif event_type == "tool_execution_update":
            error = validate_tool_execution_update(event)
        elif event_type == "tool_execution_end":
            error = validate_tool_execution_end(event)
        elif event_type == "message_start":
            error = validate_message_start(event)
            if error is None:
                error = self._open_lifecycle(event["message"]["role"])
        elif event_type == "message_update":
            error = self._consume_message_update(event)
        elif event_type == "message_end":
            error = self._consume_message_end(event)
        elif event_type == "turn_end":
            error = validate_turn_end(event)
        elif event_type == "agent_end":
            error = self._consume_agent_end(event)
        elif event_type == "custom":
            error = "OMP custom message is only legal after settlement"
        else:
            error = "unrecognized OMP event type"
        if error is not None:
            self._invalidate("OMP transport recognized event is malformed", {"line": self._line_number, "error": error})

    def _open_lifecycle(self, role: str) -> str | None:
        if self._open_role is not None:
            return f"message lifecycle overlap: {self._open_role!r} is already open"
        self._open_role = role
        return None

    def _consume_message_update(self, event: dict[str, Any]) -> str | None:
        if self._open_role != "assistant":
            return "message_update is only legal inside an assistant lifecycle"
        error = validate_message_update(event)
        if error is not None:
            return error
        union = event["assistantMessageEvent"]
        if union["type"] == "error":
            self._pending_error_stop_reason = union["reason"]
        return None

    def _consume_message_end(self, event: dict[str, Any]) -> str | None:
        error = validate_message_end(event)
        if error is not None:
            return error
        role = event["message"]["role"]
        if self._open_role is None:
            return "message_end closes no open lifecycle"
        if self._open_role != role:
            return f"message_end role {role!r} does not match open lifecycle {self._open_role!r}"
        self._open_role = None
        if role != "assistant":
            return None
        message = event["message"]
        error = validate_closed_assistant_message(message)
        if error is not None:
            return error
        if self._pending_error_stop_reason is not None and message["stopReason"] != self._pending_error_stop_reason:
            self._pending_error_stop_reason = None
            return "assistant message_end stopReason does not match the preceding error update"
        self._pending_error_stop_reason = None
        message_text = "\n".join(block["text"] for block in message["content"] if isinstance(block, dict) and block.get("type") == "text")
        if message_text:
            self._text_parts.append(message_text)
            self._pending_emission = message_text
        self._message_rows.append({"provider": message["provider"], "model": message["model"], "usage": copy.deepcopy(message["usage"]), "stop_reason": message["stopReason"]})
        self._final_provider = message["provider"]
        self._final_model = message["model"]
        self._last_closed_assistant = message
        return None

    def _consume_agent_end(self, event: dict[str, Any]) -> str | None:
        error = validate_agent_end(event)
        if error is not None:
            return error
        if event.get("isTerminal", True) is False:
            return None
        if self._open_role is not None:
            return "terminal agent_end arrives with an open message lifecycle"
        last = self._last_closed_assistant
        if last is None:
            return "terminal agent_end requires a closed assistant message"
        if last.get("stopReason") != "stop":
            return "terminal agent_end requires the final assistant stopReason to be stop"
        if any(isinstance(block, dict) and block.get("type") in {"tool_call", "tool_use"} for block in last.get("content", [])):
            return "terminal agent_end requires no tool-call block in the final assistant"
        self._settlement_seen = True
        self._state = "terminal_seen"
        return None

    def _consume_custom(self, event: dict[str, Any], *, late: bool) -> str | None:
        if not late:
            return "custom events are only pinned after settlement"
        error = validate_custom(event)
        if error is not None:
            return error
        role = event["message"]["role"]
        marker = f"custom:{role}"
        if self._open_role is None:
            self._open_role = marker
            return None
        if self._open_role == marker:
            self._open_role = None
            return None
        return "custom lifecycle pair does not match its open role"

    def _mandatory_checks(self) -> dict[str, Any] | None:
        if self._invalid_error is not None:
            return copy.deepcopy(self._invalid_error)
        if self._open_role is not None:
            return self._error("OMP transport ends with an open message lifecycle", {"line": self._line_number})
        if self._state != "frame_seen":
            return self._error("OMP transport ended before the adapter launch frame", {"state": self._state, "events": self._event_count})
        if not self._message_rows:
            return self._error("OMP transport produced zero closed assistant messages", {"events": self._event_count})
        return None

    def _provisional_result(self) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """Return an incomplete observation without settling any finality."""
        if self._invalid_error is not None:
            return None, copy.deepcopy(self._invalid_error)
        if self._state == "frame_seen" and self._open_role is None and self._text_parts:
            return self._build_metadata(), None
        return None, None

    def _build_metadata(self) -> dict[str, Any]:
        total_tokens = 0
        total_cost = 0.0
        for row in self._message_rows:
            total_tokens += row["usage"].get("totalTokens", 0)
            total_cost += row["usage"].get("cost", {}).get("total", 0.0)
        return {
            "session_id": self._session_id,
            "event_count": self._event_count,
            "messages": [
                {"provider": row["provider"], "model": row["model"], "usage": _unfreeze_value(row["usage"]), "stop_reason": row["stop_reason"]}
                for row in self._message_rows
            ],
            "total_tokens": total_tokens,
            "total_cost": total_cost,
            "final_provider": self._final_provider,
            "final_model": self._final_model,
            "launch_frame": _unfreeze_value(self._frame),
        }

    def _invalidate(self, message: str, context: Mapping[str, Any]) -> None:
        if self._invalid_error is None:
            self._invalid_error = self._error(message, context)

    def _emit_assistant_text(self, text_parts: list[str]) -> None:
        callback = self._assistant_text_callback
        if callback is None:
            return
        for text in text_parts:
            try:
                callback(text)
            except Exception:
                # Display is best-effort; parse state remains authoritative.
                pass

    @staticmethod
    def _error(message: str, context: Mapping[str, Any]) -> dict[str, Any]:
        return {"type": _TRANSPORT_ERROR_TYPE, "message": message, "context": dict(context)}


def _freeze_snapshot_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_snapshot_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_snapshot_value(item) for item in value)
    return value


__all__ = ["OmpJsonStdoutAccumulator"]
