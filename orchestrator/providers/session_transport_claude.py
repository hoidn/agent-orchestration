"""Incremental codec for `claude -p --output-format stream-json --verbose` stdout.

Binds one `session_id` (from `system/init` and later events), the assistant text
(from `assistant` events) and completion (from the terminal `result` event).
Stdout itself is never altered; this codec only observes it.
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

_TERMINAL_TYPE = "result"


def _assistant_text(event: Mapping[str, Any]) -> str:
    """Join the text blocks of one `assistant` event ('' for any other shape)."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, Mapping) else None
    if not isinstance(content, list):
        return ""
    return "".join(
        block["text"]
        for block in content
        if isinstance(block, Mapping)
        and block.get("type") == "text"
        and isinstance(block.get("text"), str)
    )


class ClaudeStreamJsonAccumulator:
    """Implements `SessionTransportAccumulator` for Claude stream-json stdout."""

    def __init__(
        self,
        *,
        assistant_text_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._callback = assistant_text_callback
        self._buffer = bytearray()
        self._session_ids: set[str] = set()
        self._text_parts: list[str] = []
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
        emitted: list[str] = []
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
                emitted.append(self._consume(line))
        self._emit(emitted)

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
        emitted: list[str] = []
        with self._lock:
            if not self._finalized:
                self._finalized = True
                tail = bytes(self._buffer)
                self._buffer.clear()
                if self._invalid is None and tail.strip():
                    emitted.append(self._consume(tail))
        self._emit(emitted)
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
        terminal = self._terminal or {}
        return {
            "session_id": session_id,
            "normalized_stdout": "".join(self._text_parts),
            "event_count": self._event_count,
            "result_subtype": terminal.get("subtype"),
            "is_error": bool(terminal.get("is_error", False)),
        }, None

    def _consume(self, raw: bytes) -> str:
        """Parse one line; return its assistant text ('' when it carries none)."""
        if not raw.strip():
            return ""
        self._line_number += 1
        try:
            event = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            self._invalid = self._error(
                "Session transport is not valid stream-json",
                {"line": self._line_number, "error": str(exc)},
            )
            return ""
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            self._invalid = self._error(
                "Session transport event must be a JSON object with a string type",
                {"line": self._line_number},
            )
            return ""
        self._event_count += 1
        session_id = event.get("session_id")
        if isinstance(session_id, str) and session_id:
            self._session_ids.add(session_id)
        if event["type"] == _TERMINAL_TYPE:
            self._terminal = event
            return ""
        if event["type"] != "assistant":
            return ""
        text = _assistant_text(event)
        if text:
            self._text_parts.append(text)
        return text

    def _emit(self, texts: list[str]) -> None:
        if self._callback is None:
            return
        for text in texts:
            if not text:
                continue
            try:
                self._callback(text)
            except Exception:
                # Streaming display is best-effort (as in CodexExecJsonlAccumulator);
                # parse state remains authoritative.
                pass

    def _conflict_error(self) -> dict[str, Any]:
        return self._error(
            "Session transport exposed conflicting session identifiers",
            {"session_ids": sorted(self._session_ids)},
        )

    @staticmethod
    def _error(message: str, context: Mapping[str, Any]) -> dict[str, Any]:
        return {"type": _TRANSPORT_ERROR_TYPE, "message": message, "context": dict(context)}


__all__ = ["ClaudeStreamJsonAccumulator"]
