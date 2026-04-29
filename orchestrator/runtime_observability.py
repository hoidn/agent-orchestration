"""Active workflow runtime observability helpers.

These helpers track executor-process sessions for human-readable reporting. They
do not enforce deadlines, alter routing, or affect provider execution.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, MutableMapping

from orchestrator.monitor.process import is_pid_alive, process_start_time_token


RuntimeState = MutableMapping[str, Any] | Any
ProcessLiveness = Callable[[Mapping[str, Any]], bool | None]


def _now() -> datetime:
    return datetime.now(timezone.utc)


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


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _duration_ms(started_at: Any, ended_at: Any) -> int | None:
    start = _parse_datetime(started_at)
    end = _parse_datetime(ended_at)
    if start is None or end is None or end < start:
        return None
    return int((end - start).total_seconds() * 1000)


def _state_get(state: RuntimeState, key: str, default: Any = None) -> Any:
    if isinstance(state, Mapping):
        return state.get(key, default)
    return getattr(state, key, default)


def _state_set(state: RuntimeState, key: str, value: Any) -> None:
    if isinstance(state, MutableMapping):
        state[key] = value
    else:
        setattr(state, key, value)


def _runtime_payload(state: RuntimeState, *, create: bool = False) -> MutableMapping[str, Any] | None:
    payload = _state_get(state, "runtime_observability")
    if isinstance(payload, MutableMapping):
        sessions = payload.get("executor_sessions")
        if not isinstance(sessions, list):
            payload["executor_sessions"] = []
        return payload
    if not create:
        return None
    payload = {"schema_version": 1, "executor_sessions": []}
    _state_set(state, "runtime_observability", payload)
    return payload


def _sessions(state: RuntimeState, *, create: bool = False) -> list[MutableMapping[str, Any]]:
    payload = _runtime_payload(state, create=create)
    if payload is None:
        return []
    sessions = payload.get("executor_sessions")
    if not isinstance(sessions, list):
        sessions = []
        payload["executor_sessions"] = sessions
    return sessions


def _next_session_id(sessions: list[MutableMapping[str, Any]]) -> str:
    max_seen = 0
    for session in sessions:
        raw = session.get("session_id")
        if not isinstance(raw, str) or not raw.startswith("exec-"):
            continue
        try:
            max_seen = max(max_seen, int(raw.removeprefix("exec-")))
        except ValueError:
            continue
    return f"exec-{max_seen + 1:04d}"


def _default_process_is_live(session: Mapping[str, Any]) -> bool | None:
    pid = session.get("pid")
    if not isinstance(pid, int):
        return False
    if pid == os.getpid():
        expected_start = session.get("process_start_time")
        current_start = process_start_time_token(pid)
        if isinstance(expected_start, str) and current_start is not None:
            return expected_start == current_start
        return True
    if not is_pid_alive(pid):
        return False
    expected_start = session.get("process_start_time")
    if isinstance(expected_start, str):
        current_start = process_start_time_token(pid)
        if current_start is not None:
            return current_start == expected_start
    return None


def format_duration(ms: int | None) -> str | None:
    """Return a compact human-readable duration."""

    if ms is None:
        return None
    total_seconds = max(0, int(round(ms / 1000)))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes}m {seconds}s"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def _session_contributes_live_time(
    session: Mapping[str, Any],
    *,
    process_is_live: ProcessLiveness | None,
) -> bool:
    live_checker = process_is_live or _default_process_is_live
    try:
        return live_checker(session) is True
    except Exception:
        return False


def compute_active_runtime(
    state: RuntimeState,
    *,
    now: datetime | None = None,
    process_is_live: ProcessLiveness | None = None,
) -> dict[str, Any]:
    """Compute active executor runtime from persisted session records."""

    sessions = _sessions(state)
    if not sessions:
        return {
            "active_runtime_ms": None,
            "active_runtime": None,
            "executor_session_count": 0,
        }

    effective_now = now or _now()
    active_ms = 0
    normalized: list[tuple[datetime, datetime | None]] = []
    current_session: dict[str, Any] | None = None

    for session in sessions:
        started_at = _parse_datetime(session.get("started_at"))
        ended_at = _parse_datetime(session.get("ended_at"))
        if started_at is not None:
            normalized.append((started_at, ended_at))

        duration = session.get("duration_ms")
        if isinstance(duration, int) and duration >= 0:
            active_ms += duration
            continue

        if (
            session.get("status") == "running"
            and ended_at is None
            and started_at is not None
            and _session_contributes_live_time(session, process_is_live=process_is_live)
        ):
            live_ms = max(0, int((effective_now - started_at).total_seconds() * 1000))
            active_ms += live_ms
            current_session = {
                "session_id": session.get("session_id"),
                "entrypoint": session.get("entrypoint"),
                "status": session.get("status"),
                "started_at": session.get("started_at"),
                "active_ms": live_ms,
            }

    excluded_ms = 0
    previous_end: datetime | None = None
    for started_at, ended_at in sorted(normalized, key=lambda item: item[0]):
        if previous_end is not None and started_at > previous_end:
            excluded_ms += int((started_at - previous_end).total_seconds() * 1000)
        if ended_at is not None and (previous_end is None or ended_at > previous_end):
            previous_end = ended_at

    result: dict[str, Any] = {
        "active_runtime_ms": active_ms,
        "active_runtime": format_duration(active_ms),
        "executor_session_count": len(sessions),
    }
    if current_session is not None:
        result["current_executor_session"] = current_session
    if excluded_ms > 0:
        result["excluded_suspended_ms"] = excluded_ms
        result["suspended_gap_excluded"] = format_duration(excluded_ms)
    return result


def reconcile_open_sessions(
    state: RuntimeState,
    *,
    now: datetime | None = None,
    process_is_live: ProcessLiveness | None = None,
    trusted_end_at: datetime | None = None,
) -> None:
    """Close dead open sessions as abandoned using a trusted end timestamp."""

    fallback_end = trusted_end_at or _parse_datetime(_state_get(state, "updated_at")) or now or _now()
    for session in _sessions(state):
        if session.get("status") != "running" or session.get("ended_at") is not None:
            continue
        if _session_contributes_live_time(session, process_is_live=process_is_live):
            continue
        session["ended_at"] = _iso(fallback_end)
        session["status"] = "abandoned"
        duration = _duration_ms(session.get("started_at"), session.get("ended_at"))
        if duration is not None:
            session["duration_ms"] = duration


def open_executor_session(
    state: RuntimeState,
    *,
    entrypoint: str,
    pid: int | None = None,
    process_start_time: str | None = None,
    now: datetime | None = None,
    process_is_live: ProcessLiveness | None = None,
) -> str:
    """Open a new executor session for this run state."""

    reconcile_open_sessions(state, now=now, process_is_live=process_is_live)
    sessions = _sessions(state, create=True)
    live_open = [
        session
        for session in sessions
        if session.get("status") == "running"
        and session.get("ended_at") is None
        and _session_contributes_live_time(session, process_is_live=process_is_live)
    ]
    if live_open:
        existing = live_open[0].get("session_id")
        raise RuntimeError(f"Run already has a live executor session: {existing}")

    effective_now = now or _now()
    session_id = _next_session_id(sessions)
    sessions.append(
        {
            "session_id": session_id,
            "entrypoint": entrypoint,
            "pid": os.getpid() if pid is None else int(pid),
            "process_start_time": process_start_time,
            "started_at": _iso(effective_now),
            "ended_at": None,
            "status": "running",
            "duration_ms": None,
        }
    )
    return session_id


def close_executor_session(
    state: RuntimeState,
    *,
    session_id: str,
    status: str,
    now: datetime | None = None,
) -> None:
    """Close an executor session if it is still open."""

    effective_now = now or _now()
    for session in _sessions(state):
        if session.get("session_id") != session_id:
            continue
        if session.get("ended_at") is not None:
            return
        session["ended_at"] = _iso(effective_now)
        session["status"] = status
        duration = _duration_ms(session.get("started_at"), session.get("ended_at"))
        if duration is not None:
            session["duration_ms"] = duration
        return
    raise KeyError(f"Unknown executor session: {session_id}")
