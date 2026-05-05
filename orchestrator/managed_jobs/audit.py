"""JSONL audit helpers for managed provider jobs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class AuditEventError(ValueError):
    """Raised when a managed-job audit event is invalid."""


ALLOWED_EVENT_TYPES = {
    "classification",
    "job_submitted",
    "job_completed",
    "job_failed",
    "job_state",
}


def _validate_event(event: dict[str, Any]) -> None:
    event_type = event.get("event")
    if not isinstance(event_type, str) or not event_type:
        raise AuditEventError("audit event requires non-empty event")
    if event_type not in ALLOWED_EVENT_TYPES:
        raise AuditEventError(f"unknown event type '{event_type}'")


def append_event(path: Path, event: dict[str, Any]) -> None:
    """Append one validated event to a managed-job JSONL audit file."""

    _validate_event(event)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def read_events(path: Path) -> list[dict[str, Any]]:
    """Read and validate all events from a managed-job JSONL audit file."""

    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditEventError(f"malformed JSON at line {line_number}: {exc.msg}") from exc
            if not isinstance(event, dict):
                raise AuditEventError(f"audit event at line {line_number} must be an object")
            _validate_event(event)
            events.append(event)
    return events
