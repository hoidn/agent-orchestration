"""Run event classification for workflow monitoring."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import MonitorEvent, MonitorEventKind, MonitorRun
from .process import is_pid_alive


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

    if run.process is not None and not is_pid_alive(run.process.pid):
        return MonitorEvent(MonitorEventKind.CRASHED, run, "process_not_alive", observed_at)

    heartbeat = _current_step_heartbeat(run.state)
    if heartbeat is not None:
        if (_normalize_now(now) - heartbeat).total_seconds() > stale_after_seconds:
            return MonitorEvent(MonitorEventKind.STALLED, run, "stale_heartbeat", observed_at)
        return None

    updated_at = _parse_datetime(run.state.get("updated_at"))
    if updated_at is not None and (_normalize_now(now) - updated_at).total_seconds() > stale_after_seconds:
        return MonitorEvent(MonitorEventKind.STALLED, run, "stale_updated_at", observed_at)

    return None


def _current_step_heartbeat(state: Any) -> datetime | None:
    current_step = state.get("current_step") if isinstance(state, dict) else None
    if not isinstance(current_step, dict):
        return None
    heartbeat = _parse_datetime(current_step.get("last_heartbeat_at"))
    if heartbeat is not None:
        return heartbeat
    return _parse_datetime(current_step.get("started_at"))


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
