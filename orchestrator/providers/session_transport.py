"""Incremental codecs for provider-session metadata transports."""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Literal, Mapping

from .types import ProviderSessionMetadataMode


_TRANSPORT_ERROR_TYPE = "provider_session_transport_error"
_IDENTITY_KEYS = ("thread_id", "session_id")
_TERMINAL_EVENT_TYPES = frozenset({"turn.completed", "response.completed"})


@dataclass(frozen=True)
class SessionIdentitySnapshot:
    """Immutable in-flight view of provider-session identity readiness."""

    status: Literal["missing", "unique", "ambiguous", "invalid"]
    session_ids: tuple[str, ...]
    terminal_seen: bool
    error: Mapping[str, Any] | None = None


def extract_codex_assistant_text(event: Mapping[str, Any]) -> str | None:
    """Extract normalized assistant text from one supported Codex JSONL event."""
    if event.get("type") == "item.completed":
        item = event.get("item")
        if (
            isinstance(item, Mapping)
            and item.get("type") == "agent_message"
            and isinstance(item.get("text"), str)
        ):
            return item["text"]

    if event.get("role") == "assistant":
        if isinstance(event.get("text"), str):
            return event["text"]
        if isinstance(event.get("delta"), str):
            return event["delta"]
        return None

    event_type = event.get("type")
    if isinstance(event_type, str) and "assistant" in event_type:
        if isinstance(event.get("text"), str):
            return event["text"]
        if isinstance(event.get("delta"), str):
            return event["delta"]
    return None


class CodexExecJsonlAccumulator:
    """Incrementally parse Codex ``exec --json`` stdout without altering it."""

    def __init__(
        self,
        *,
        assistant_text_callback: Callable[[str], None] | None = None,
    ) -> None:
        self._assistant_text_callback = assistant_text_callback
        self._buffer = bytearray()
        self._session_ids: set[str] = set()
        self._text_parts: list[str] = []
        self._terminal_seen = False
        self._event_count = 0
        self._line_number = 0
        self._invalid_error: dict[str, Any] | None = None
        self._finalized = False
        self._lock = threading.RLock()

    def feed(self, chunk: bytes) -> None:
        """Feed an arbitrary raw stdout chunk into the JSONL line buffer."""
        if not isinstance(chunk, bytes):
            raise TypeError("session transport chunks must be bytes")
        if not chunk:
            return

        emitted: list[str] = []
        with self._lock:
            if self._finalized:
                raise RuntimeError("session transport accumulator is finalized")
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

    def snapshot(self) -> SessionIdentitySnapshot:
        """Return the current provisional identity and exact-terminal state."""
        with self._lock:
            session_ids = tuple(sorted(self._session_ids))
            if self._invalid_error is not None:
                return SessionIdentitySnapshot(
                    status="invalid",
                    session_ids=session_ids,
                    terminal_seen=self._terminal_seen,
                    error=copy.deepcopy(self._invalid_error),
                )
            if len(session_ids) > 1:
                return SessionIdentitySnapshot(
                    status="ambiguous",
                    session_ids=session_ids,
                    terminal_seen=self._terminal_seen,
                    error=self._conflicting_identity_error(),
                )
            return SessionIdentitySnapshot(
                status="unique" if session_ids else "missing",
                session_ids=session_ids,
                terminal_seen=self._terminal_seen,
                error=None,
            )

    def finalize(
        self,
        *,
        expected_session_id: str | None,
        require_terminal: bool,
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]:
        """Parse the one EOF tail and return normalized metadata or an error."""
        emitted: list[str] = []
        with self._lock:
            if not self._finalized:
                self._finalized = True
                raw_tail = bytes(self._buffer)
                self._buffer.clear()
                if raw_tail.strip():
                    self._line_number += 1
                    assistant_text = self._consume_line(raw_tail)
                    if assistant_text is not None:
                        emitted.append(assistant_text)

        self._emit_assistant_text(emitted)

        snapshot = self.snapshot()
        if snapshot.status in {"invalid", "ambiguous"}:
            return None, snapshot.error

        if require_terminal and not snapshot.terminal_seen:
            return None, self._error(
                "Session transport is missing a terminal completion marker",
                {"events": self.event_count},
            )

        if snapshot.status == "missing":
            return None, self._error(
                "Session transport did not expose a session_id",
                {"events": self.event_count},
            )

        session_id = snapshot.session_ids[0]
        if expected_session_id is not None and session_id != expected_session_id:
            return None, self._error(
                "Session transport did not match the requested session_id",
                {
                    "expected_session_id": expected_session_id,
                    "observed_session_id": session_id,
                },
            )

        with self._lock:
            metadata: dict[str, Any] = {
                "session_id": session_id,
                "normalized_stdout": "".join(self._text_parts),
                "event_count": self._event_count,
            }
        return metadata, None

    @property
    def event_count(self) -> int:
        """Return the number of non-empty JSONL event records observed."""
        with self._lock:
            return self._event_count

    def _consume_line(self, raw_line: bytes) -> str | None:
        if not raw_line.strip():
            return None

        self._event_count += 1
        try:
            decoded_line = raw_line.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            self._invalidate(
                "Session transport is not valid UTF-8",
                {"line": self._line_number, "error": str(exc)},
            )
            return None

        try:
            event = json.loads(decoded_line)
        except json.JSONDecodeError as exc:
            self._invalidate(
                "Session transport is not valid JSONL",
                {"line": self._line_number, "error": str(exc)},
            )
            return None

        if not isinstance(event, dict):
            self._invalidate(
                "Session transport event must be a JSON object",
                {"line": self._line_number},
            )
            return None

        event_session_ids: list[str] = []
        for key in _IDENTITY_KEYS:
            if key not in event:
                continue
            value = event[key]
            if not isinstance(value, str) or not value:
                self._invalidate(
                    "Session transport exposed a malformed session identifier",
                    {"line": self._line_number, "key": key},
                )
                return None
            event_session_ids.append(value)

        self._session_ids.update(event_session_ids)

        event_type = event.get("type")
        if isinstance(event_type, str) and event_type in _TERMINAL_EVENT_TYPES:
            self._terminal_seen = True

        assistant_text = extract_codex_assistant_text(event)
        if assistant_text is not None:
            self._text_parts.append(assistant_text)
        return assistant_text

    def _invalidate(self, message: str, context: Mapping[str, Any]) -> None:
        if self._invalid_error is None:
            self._invalid_error = self._error(message, context)

    def _conflicting_identity_error(self) -> dict[str, Any]:
        return self._error(
            "Session transport exposed conflicting session identifiers",
            {"session_ids": sorted(self._session_ids)},
        )

    def _emit_assistant_text(self, text_parts: list[str]) -> None:
        callback = self._assistant_text_callback
        if callback is None:
            return
        for text in text_parts:
            try:
                callback(text)
            except Exception:
                # Streaming display is best-effort; parse state remains authoritative.
                pass

    @staticmethod
    def _error(
        message: str,
        context: Mapping[str, Any],
    ) -> dict[str, Any]:
        return {
            "type": _TRANSPORT_ERROR_TYPE,
            "message": message,
            "context": dict(context),
        }


def create_session_transport_accumulator(
    metadata_mode: str | ProviderSessionMetadataMode | None,
    *,
    assistant_text_callback: Callable[[str], None] | None = None,
) -> CodexExecJsonlAccumulator | None:
    """Select a session codec structurally from the declared metadata mode."""
    if metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value:
        return CodexExecJsonlAccumulator(
            assistant_text_callback=assistant_text_callback,
        )
    return None


__all__ = [
    "CodexExecJsonlAccumulator",
    "SessionIdentitySnapshot",
    "create_session_transport_accumulator",
]
