"""Incremental codec for `agy --output-format stream-json` stdout.

One JSON object per line, keyed by `event` (`init`, `step_update`, `result`). Binds one conversation id
(every non-empty `conversation_id`: top level, in `step_update`, in `result`), the assistant text (the
`text_delta` strings of `agent_response` steps) and completion (the `result` line, whose `status` is the
`result_subtype`; any status but `SUCCESS` is an error). Stdout itself is never altered; this codec only
observes it.
"""

from __future__ import annotations

import copy
import json
import threading
from typing import Any, Callable, Mapping

from .session_transport import (
    _TRANSPORT_ERROR_TYPE,
    SessionIdentitySnapshot,
    _freeze_snapshot_error,
)

_TERMINAL_EVENT = "result"


class AgyStreamJsonAccumulator:
    """Implements `SessionTransportAccumulator` for `agy` stream-json stdout."""

    def __init__(
        self,
        *,
        assistant_text_callback: Callable[[str], None] | None = None,
        tool_activity_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._callback = assistant_text_callback
        self._tool_activity_callback = tool_activity_callback
        self._buffer = bytearray()
        self._session_ids: set[str] = set()
        self._text_parts: list[str] = []
        self._tool_states: dict[int, str] = {}
        self._terminal: dict[str, Any] | None = None
        self._event_count = 0
        self._line_number = 0
        self._invalid: dict[str, Any] | None = None
        self._finalized = False
        self._lock = threading.RLock()

    @property
    def event_count(self) -> int:
        with self._lock:
            return self._event_count

    @property
    def normalized_stdout(self) -> str:
        with self._lock:
            return "".join(self._text_parts)

    def feed(self, chunk: bytes) -> None:
        if not isinstance(chunk, bytes):
            raise TypeError("session transport chunks must be bytes")
        emitted: list[tuple[str, str]] = []
        with self._lock:
            if self._finalized:
                raise RuntimeError("session transport accumulator is finalized")
            if self._invalid is not None or not chunk:
                return
            self._buffer.extend(chunk)
            while self._invalid is None:
                offset = self._buffer.find(b"\n")
                if offset < 0:
                    break
                line = bytes(self._buffer[:offset])
                del self._buffer[: offset + 1]
                emitted.extend(self._consume(line))
        self._emit_events(emitted)

    def snapshot(self) -> SessionIdentitySnapshot:
        with self._lock:
            ids = tuple(sorted(self._session_ids))
            terminal_seen = self._terminal is not None
            error = self._invalid or (self._conflict_error() if len(ids) > 1 else None)
            if error is not None:
                status = "invalid" if self._invalid is not None else "ambiguous"
                return SessionIdentitySnapshot(
                    status, ids, terminal_seen, _freeze_snapshot_error(error)
                )
            return SessionIdentitySnapshot(
                "unique" if ids else "missing", ids, terminal_seen, None
            )

    def finalize(
        self,
        *,
        expected_session_id: str | None,
        require_terminal: bool,
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """Parse the EOF tail and return normalized metadata or an error."""
        emitted: list[tuple[str, str]] = []
        with self._lock:
            if not self._finalized:
                self._finalized = True
                tail = bytes(self._buffer)
                self._buffer.clear()
                if self._invalid is None and tail.strip():
                    emitted.extend(self._consume(tail))
        self._emit_events(emitted)
        with self._lock:
            return self._settle(expected_session_id, require_terminal)

    def _settle(
        self, expected_session_id: str | None, require_terminal: bool
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        if self._invalid is not None:
            return None, copy.deepcopy(self._invalid)
        if len(self._session_ids) > 1:
            return None, self._conflict_error()
        if require_terminal and self._terminal is None:
            return None, self._error(
                "Session transport is missing a terminal result event",
                {"events": self._event_count},
            )
        if not self._session_ids:
            return None, self._error(
                "Session transport did not expose a session_id",
                {"events": self._event_count},
            )
        (session_id,) = self._session_ids
        if expected_session_id is not None and session_id != expected_session_id:
            return None, self._error(
                "Session transport did not match the requested session_id",
                {
                    "expected_session_id": expected_session_id,
                    "observed_session_id": session_id,
                },
            )
        status = (self._terminal or {}).get("status")
        return {
            "session_id": session_id,
            "normalized_stdout": "".join(self._text_parts),
            "event_count": self._event_count,
            "result_subtype": status,
            "is_error": self._terminal is not None and status != "SUCCESS",
        }, None

    def _consume(self, raw: bytes) -> list[tuple[str, str]]:
        """Parse one line; return its ordered display callbacks."""
        if not raw.strip():
            return []
        self._line_number += 1
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, RecursionError) as exc:
            self._invalid = self._error(
                "Session transport is not valid stream-json",
                {"line": self._line_number, "error": str(exc)},
            )
            return []
        if not isinstance(event, dict) or not isinstance(event.get("event"), str):
            self._invalid = self._error(
                "Session transport event must be a JSON object with a string event",
                {"line": self._line_number},
            )
            return []
        self._event_count += 1
        payload = event.get(event["event"])
        payload = payload if isinstance(payload, dict) else {}
        for candidate in (event.get("conversation_id"), payload.get("conversation_id")):
            if isinstance(candidate, str) and candidate:
                self._session_ids.add(candidate)
        if event["event"] == _TERMINAL_EVENT:
            self._terminal = payload
            return []
        if event["event"] != "step_update":
            return []
        return self._step_events(payload)

    def _step_events(self, step: Mapping[str, Any]) -> list[tuple[str, str]]:
        kind = step.get("step_type")
        if kind == "agent_response":
            text = step.get("text_delta")
            if isinstance(text, str) and text:
                self._text_parts.append(text)
                return [("text", text)]
            return []
        index, name, state = step.get("step_index"), step.get("tool_name"), step.get("state")
        if kind != "tool" or type(index) is not int or not isinstance(name, str) or not name:
            return []
        label = {"ACTIVE": "started", "DONE": "completed"}.get(state)
        if label is None or self._tool_states.get(index) in (state, "DONE"):
            return []
        self._tool_states[index] = state
        return [("activity", f"Tool {label}: {name[:64]}")]

    def _emit_events(self, events: list[tuple[str, str]]) -> None:
        for kind, text in events:
            callback = (
                self._callback if kind == "text" else self._tool_activity_callback
            )
            if callback is None or not text:
                continue
            try:
                callback(text)
            except Exception:
                # Streaming display is best-effort; parse state remains authoritative.
                pass

    def _conflict_error(self) -> dict[str, Any]:
        return self._error(
            "Session transport exposed conflicting session identifiers",
            {"session_ids": sorted(self._session_ids)},
        )

    @staticmethod
    def _error(message: str, context: Mapping[str, Any]) -> dict[str, Any]:
        return {"type": _TRANSPORT_ERROR_TYPE, "message": message, "context": dict(context)}


__all__ = ["AgyStreamJsonAccumulator"]
