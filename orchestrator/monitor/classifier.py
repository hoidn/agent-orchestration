"""Run event classification for workflow monitoring."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from orchestrator.dashboard.cursor import ExecutionCursorProjector

from .models import MonitorEvent, MonitorEventKind, MonitorRun
from .process import process_identity_matches


def classify_run(
    run: MonitorRun,
    *,
    now: datetime | None = None,
    stale_after_seconds: int,
) -> MonitorEvent | None:
    """Classify a scanned run into a notification-worthy event."""

    if run.state is None:
        return None
    observed_at = _normalize_now(now).isoformat()
    status = run.state.get("status")

    if status == "completed":
        return MonitorEvent(MonitorEventKind.COMPLETED, run, "state_completed", observed_at)
    if status == "failed":
        return MonitorEvent(MonitorEventKind.FAILED, run, "state_failed", observed_at)
    if status != "running":
        return None

    if run.process is not None:
        process_match = process_identity_matches(run.process)
        if process_match is False:
            refreshed = _refresh_terminal_state(run)
            if refreshed is not run:
                return classify_run(refreshed, now=now, stale_after_seconds=stale_after_seconds)
            heartbeat = _active_cursor_heartbeat(run.state)
            if heartbeat is not None and (_normalize_now(now) - heartbeat).total_seconds() <= stale_after_seconds:
                return None
            updated_at = _parse_datetime(run.state.get("updated_at"))
            if updated_at is not None and (_normalize_now(now) - updated_at).total_seconds() <= stale_after_seconds:
                return None
            return MonitorEvent(MonitorEventKind.CRASHED, run, "process_not_alive", observed_at)

    heartbeat = _active_cursor_heartbeat(run.state)
    if heartbeat is not None:
        if (_normalize_now(now) - heartbeat).total_seconds() > stale_after_seconds:
            return MonitorEvent(MonitorEventKind.STALLED, run, "stale_heartbeat", observed_at)
        return None

    updated_at = _parse_datetime(run.state.get("updated_at"))
    if updated_at is not None and (_normalize_now(now) - updated_at).total_seconds() > stale_after_seconds:
        return MonitorEvent(MonitorEventKind.STALLED, run, "stale_updated_at", observed_at)

    return None


def _refresh_terminal_state(run: MonitorRun) -> MonitorRun:
    """Return a fresh terminal-state snapshot when a stale scan races finalization."""

    try:
        raw = json.loads(run.state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return run
    if not isinstance(raw, Mapping):
        return run
    if raw.get("status") not in {"completed", "failed"}:
        return run
    return replace(run, state=raw)


def _active_cursor_heartbeat(state: Any) -> datetime | None:
    if not isinstance(state, dict):
        return None
    cursor = ExecutionCursorProjector().project(state)
    current_nodes = [node for node in cursor.nodes if node.kind == "current_step"]
    for node in reversed(current_nodes):
        heartbeat = _parse_datetime(node.details.get("last_heartbeat_at"))
        if heartbeat is not None:
            return heartbeat
        started_at = _parse_datetime(node.details.get("started_at"))
        if started_at is not None:
            return started_at
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)
