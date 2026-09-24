"""Incremental codecs for provider-session metadata transports."""

from __future__ import annotations

import copy
import json
import threading
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Callable, Literal, Mapping, Protocol, runtime_checkable

from .types import OmpTransportExpectation, ProviderSessionMetadataMode


_TRANSPORT_ERROR_TYPE = "provider_session_transport_error"
_IDENTITY_KEYS = ("thread_id", "session_id")
_TERMINAL_EVENT_TYPES = frozenset({"turn.completed", "response.completed"})
_RESUME_BOUNDARY_EVENT_TYPE = "turn.started"
_FAILED_TERMINAL_EVENT_TYPE = "turn.failed"


def _freeze_snapshot_value(value: Any) -> Any:
    """Recursively detach and freeze one snapshot-owned value."""
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                key: _freeze_snapshot_value(nested_value)
                for key, nested_value in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_snapshot_value(item) for item in value)
    return value


def _freeze_snapshot_error(error: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(
        {
            key: _freeze_snapshot_value(value)
            for key, value in error.items()
        }
    )


@dataclass(frozen=True)
class SessionIdentitySnapshot:
    """Immutable in-flight view of provider-session identity readiness."""

    status: Literal["missing", "unique", "ambiguous", "invalid"]
    session_ids: tuple[str, ...]
    terminal_seen: bool
    error: Mapping[str, Any] | None = None
    resume_boundary_seen: bool = False

    def assistant_text_is_eligible(self, *, expected_session_id: str | None) -> bool:
        """Return whether assistant text may surface for this identity view."""
        return self.status not in {"ambiguous", "invalid"} and not (
            expected_session_id is not None
            and self.status == "unique"
            and self.session_ids != (expected_session_id,)
        )


@runtime_checkable
class SessionTransportAccumulator(Protocol):
    """Structural contract shared by every metadata transport codec."""

    @property
    def event_count(self) -> int: ...

    @property
    def normalized_stdout(self) -> str: ...

    def feed(self, chunk: bytes) -> None: ...

    def snapshot(self) -> SessionIdentitySnapshot: ...

    def finalize(
        self,
        *,
        expected_session_id: str | None,
        require_terminal: bool,
    ) -> tuple[Mapping[str, Any] | None, Mapping[str, Any] | None]: ...


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


def decode_codex_portable_context_v1(
    raw_stdout: bytes,
    *,
    provider: str,
    attempt: str,
    task: str,
) -> dict[str, Any]:
    """Decode one settled Codex JSONL trace into the closed portable value."""

    if not isinstance(raw_stdout, bytes):
        raise ValueError("portable context transport must be raw bytes")
    if not all(isinstance(value, str) and value for value in (provider, attempt)):
        raise ValueError("portable context provider and attempt must be non-empty")
    if not isinstance(task, str):
        raise ValueError("portable context task must be a string")
    try:
        lines = raw_stdout.decode("utf-8", errors="strict").split("\n")
    except UnicodeDecodeError as exc:
        raise ValueError("portable context transport is not UTF-8") from exc
    if lines[-1] == "":
        lines.pop()

    origin = {"variant": "CAPTURED", "provider": provider, "attempt": attempt}
    events: list[dict[str, Any]] = [
        {"variant": "TASK", "origin": origin, "sequence": 0, "text": task}
    ]
    item_lifecycles: dict[str, str] = {}
    completed_item_ids: set[str] = set()
    command_starts: dict[str, tuple[int, str]] = {}
    thread_seen = turn_seen = terminal_seen = False
    reasoning_seen = False
    file_change_seen = False
    for line_number, line in enumerate(lines, start=1):
        if not line:
            raise ValueError("portable context transport contains an empty JSONL record")
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"portable context transport line {line_number} is not JSON") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError("portable context transport event is malformed")
        event_type = event["type"]
        if terminal_seen:
            raise ValueError("portable context transport contains data after settlement")
        if event_type == "thread.started":
            if thread_seen or not isinstance(event.get("thread_id"), str) or not event["thread_id"]:
                raise ValueError("portable context thread start is malformed")
            thread_seen = True
            continue
        if event_type == "turn.started":
            if not thread_seen or turn_seen:
                raise ValueError("portable context turn start is malformed")
            turn_seen = True
            continue
        if event_type == "turn.completed":
            if not turn_seen or item_lifecycles:
                raise ValueError("portable context turn completion is incomplete")
            terminal_seen = True
            continue
        if event_type in {"turn.failed", "error"}:
            raise ValueError("portable context transport reports a failed turn")
        if event_type not in {"item.started", "item.updated", "item.completed"} or not turn_seen:
            raise ValueError(f"portable context transport envelope `{event_type}` is unsupported")
        item = event.get("item")
        if not isinstance(item, dict) or not isinstance(item.get("type"), str):
            raise ValueError("portable context item is malformed")
        item_type = item["type"]
        if item_type not in {"agent_message", "command_execution", "reasoning", "file_change"}:
            raise ValueError(f"portable context item `{item_type}` is unsupported")
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id:
            raise ValueError("portable context item identity is malformed")
        active_item_type = item_lifecycles.get(item_id)
        if active_item_type is not None and active_item_type != item_type:
            raise ValueError("portable context item identity changes kind")
        if event_type == "item.started":
            if item_id in item_lifecycles or item_id in completed_item_ids:
                raise ValueError("portable context item start is duplicated")
            item_lifecycles[item_id] = item_type
        elif event_type == "item.updated":
            if item_lifecycles.get(item_id) != item_type:
                raise ValueError("portable context item update lacks a matching start")
        elif item_type in {"agent_message", "reasoning", "file_change"} and item_id not in item_lifecycles:
            if item_id in completed_item_ids:
                raise ValueError("portable context item completion is duplicated")
        elif item_lifecycles.get(item_id) != item_type:
            raise ValueError("portable context item completion lacks a matching start")

        if item_type == "reasoning":
            reasoning_seen = True
            if event_type == "item.completed":
                item_lifecycles.pop(item_id, None)
                completed_item_ids.add(item_id)
            continue
        if item_type == "agent_message":
            if event_type == "item.started":
                continue
            if event_type == "item.updated":
                continue
            text = item.get("text")
            if not isinstance(text, str):
                raise ValueError("portable context assistant completion lacks text")
            events.append(
                {
                    "variant": "ASSISTANT",
                    "origin": origin,
                    "sequence": line_number,
                    "item_id": item_id,
                    "text": text,
                }
            )
            item_lifecycles.pop(item_id, None)
            completed_item_ids.add(item_id)
            continue
        if item_type == "file_change":
            status = item.get("status")
            changes = item.get("changes")
            if (
                not isinstance(status, str)
                or type(changes) is not list
                or any(
                    type(change) is not dict
                    or set(change) != {"path", "kind"}
                    or not isinstance(change["path"], str)
                    or not isinstance(change["kind"], str)
                    or change["kind"] not in {"add", "delete", "update"}
                    for change in changes
                )
            ):
                raise ValueError("portable context file change is malformed")
            if event_type in {"item.started", "item.updated"}:
                if status != "in_progress":
                    raise ValueError("portable context file change progress is malformed")
                continue
            if status not in {"completed", "failed"}:
                raise ValueError("portable context file change completion is malformed")
            events.append(
                {
                    "variant": "FILE_CHANGE",
                    "origin": origin,
                    "sequence": line_number,
                    "item_id": item_id,
                    "status": status,
                    "changes": changes,
                }
            )
            item_lifecycles.pop(item_id, None)
            completed_item_ids.add(item_id)
            file_change_seen = True
            continue
        if event_type == "item.started":
            command = item.get("command")
            if not isinstance(command, str):
                raise ValueError("portable context command start is malformed")
            command_starts[item_id] = (line_number, command)
            continue
        if event_type == "item.updated":
            continue
        call_sequence, command = command_starts.pop(item_id)
        output = item.get("aggregated_output")
        exit_code = item.get("exit_code")
        if (
            not isinstance(item.get("command"), str)
            or item["command"] != command
            or not isinstance(output, str)
            or type(exit_code) is not int
        ):
            raise ValueError("portable context command completion is malformed")
        events.append(
            {
                "variant": "COMMAND",
                "origin": origin,
                "call_sequence": call_sequence,
                "result_sequence": line_number,
                "item_id": item_id,
                "command": command,
                "output": output,
                "exit_code": exit_code,
            }
        )
        item_lifecycles.pop(item_id)
        completed_item_ids.add(item_id)
    if not thread_seen or not turn_seen or not terminal_seen:
        raise ValueError("portable context transport is not settled")

    from .portable_context import validate_portable_context_v1

    return validate_portable_context_v1(
        {
            "schema": "portable-context.v1",
            "events": events,
            "coverage": [
                {
                    "origin": origin,
                    "scope": "codex-exec-jsonl",
                    "retained_kinds": ["TASK", "ASSISTANT", "COMMAND", "FILE_CHANGE"],
                    "omitted_kinds": ["REASONING"] if reasoning_seen else [],
                    "conversions": (
                        ["codex-file-change-metadata-only"]
                        if file_change_seen
                        else []
                    ),
                }
            ],
            "lineage": [],
        }
    )


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
        self._resume_boundary_seen = False
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
                    error=_freeze_snapshot_error(self._invalid_error),
                    resume_boundary_seen=self._resume_boundary_seen,
                )
            if len(session_ids) > 1:
                return SessionIdentitySnapshot(
                    status="ambiguous",
                    session_ids=session_ids,
                    terminal_seen=self._terminal_seen,
                    error=_freeze_snapshot_error(
                        self._conflicting_identity_error()
                    ),
                    resume_boundary_seen=self._resume_boundary_seen,
                )
            return SessionIdentitySnapshot(
                status="unique" if session_ids else "missing",
                session_ids=session_ids,
                terminal_seen=self._terminal_seen,
                error=None,
                resume_boundary_seen=self._resume_boundary_seen,
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
                if self._invalid_error is None and raw_tail.strip():
                    self._line_number += 1
                    assistant_text = self._consume_line(raw_tail)
                    if assistant_text is not None:
                        emitted.append(assistant_text)

        self._emit_assistant_text(emitted)

        snapshot = self.snapshot()
        if snapshot.status == "invalid":
            with self._lock:
                assert self._invalid_error is not None
                return None, copy.deepcopy(self._invalid_error)
        if snapshot.status == "ambiguous":
            with self._lock:
                return None, self._conflicting_identity_error()

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

    @property
    def normalized_stdout(self) -> str:
        """Return the joined authoritative assistant text (display-safe use only)."""
        with self._lock:
            return "".join(self._text_parts)

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
        if len(self._session_ids) > 1:
            return None

        event_type = event.get("type")
        if event_type == _FAILED_TERMINAL_EVENT_TYPE:
            self._terminal_seen = True
            self._invalidate(
                "Session transport reported a failed provider turn",
                {"line": self._line_number},
            )
            return None
        if (
            isinstance(event_type, str)
            and event_type in _TERMINAL_EVENT_TYPES
        ):
            self._terminal_seen = True
        elif (
            event_type == _RESUME_BOUNDARY_EVENT_TYPE
            and len(self._session_ids) == 1
            and not self._terminal_seen
        ):
            self._resume_boundary_seen = True

        assistant_text = extract_codex_assistant_text(event)
        if assistant_text is not None:
            try:
                assistant_text.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                self._invalidate(
                    "Session transport assistant text is not valid Unicode",
                    {"line": self._line_number, "error": str(exc)},
                )
                return None
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
    expectation: OmpTransportExpectation | None = None,
) -> SessionTransportAccumulator | None:
    """Select a session codec structurally from the declared metadata mode."""
    if metadata_mode == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value:
        return CodexExecJsonlAccumulator(
            assistant_text_callback=assistant_text_callback,
        )
    if metadata_mode == ProviderSessionMetadataMode.OMP_JSON_STDOUT.value:
        if expectation is None:
            raise TypeError(
                "OMP JSON stdout transport requires a parent-derived "
                "OmpTransportExpectation"
            )
        from .omp_transport import OmpJsonStdoutAccumulator

        return OmpJsonStdoutAccumulator(
            expectation=expectation,
            assistant_text_callback=assistant_text_callback,
        )
    return None


def supports_resume_boundary_observation(
    metadata_mode: str | ProviderSessionMetadataMode | None,
) -> bool:
    """Return whether a metadata codec validates a resume-boundary marker."""
    return (
        metadata_mode
        == ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
    )


__all__ = [
    "CodexExecJsonlAccumulator",
    "SessionIdentitySnapshot",
    "SessionTransportAccumulator",
    "create_session_transport_accumulator",
    "supports_resume_boundary_observation",
]
