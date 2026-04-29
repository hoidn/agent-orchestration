"""Run process metadata helpers for workflow monitoring."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .models import ProcessMetadata

PROCESS_METADATA_FILENAME = "monitor_process.json"
PROCESS_METADATA_SCHEMA = "orchestrator-monitor-process/v1"


def process_metadata_path(run_root: Path) -> Path:
    """Return the run-local process metadata path."""

    return run_root / PROCESS_METADATA_FILENAME


def write_process_metadata(
    run_root: Path,
    *,
    pid: int | None = None,
    argv: Sequence[str] | None = None,
    process_start_time: str | None = None,
    executor_session_id: str | None = None,
) -> Path:
    """Write run-local process metadata for monitor crash detection."""

    run_root.mkdir(parents=True, exist_ok=True)
    path = process_metadata_path(run_root)
    effective_pid = os.getpid() if pid is None else int(pid)
    start_time = process_start_time
    if start_time is None:
        start_time = process_start_time_token(effective_pid)
    payload: dict[str, Any] = {
        "schema": PROCESS_METADATA_SCHEMA,
        "pid": effective_pid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "argv": list(sys.argv if argv is None else argv),
    }
    if start_time is not None:
        payload["process_start_time"] = start_time
    if executor_session_id is not None:
        payload["executor_session_id"] = executor_session_id
    tmux = os.environ.get("TMUX")
    if tmux:
        payload["tmux"] = tmux
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def read_process_metadata(run_root: Path) -> ProcessMetadata | None:
    """Read run process metadata if present and valid enough to use."""

    path = process_metadata_path(run_root)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, Mapping) or raw.get("schema") != PROCESS_METADATA_SCHEMA:
        return None
    pid = raw.get("pid")
    started_at = raw.get("started_at")
    if not isinstance(pid, int) or not isinstance(started_at, str):
        return None
    argv_raw = raw.get("argv", [])
    argv: tuple[str, ...] = ()
    if isinstance(argv_raw, list):
        argv = tuple(str(item) for item in argv_raw)
    tmux_raw = raw.get("tmux")
    start_time_raw = raw.get("process_start_time")
    return ProcessMetadata(
        pid=pid,
        started_at=started_at,
        process_start_time=start_time_raw if isinstance(start_time_raw, str) else None,
        argv=argv,
        tmux=tmux_raw if isinstance(tmux_raw, str) else None,
    )


def is_pid_alive(pid: int) -> bool:
    """Return whether a PID appears alive on this machine."""

    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def process_identity_matches(metadata: ProcessMetadata) -> bool | None:
    """Return whether metadata still identifies the current process for its PID.

    `None` means the platform or sidecar lacks a start-time token, so callers
    should fall back to heartbeat-based stale detection instead of suppressing
    crash/stall events solely because the PID exists.
    """

    if not is_pid_alive(metadata.pid):
        return False
    if metadata.process_start_time is None:
        return None
    current = process_start_time_token(metadata.pid)
    if current is None:
        return None
    return current == metadata.process_start_time


def process_start_time_token(pid: int) -> str | None:
    """Return a platform process start token when available.

    On Linux this is `/proc/<pid>/stat` field 22, expressed in clock ticks since
    boot. Other platforms return `None` and therefore do not use PID existence
    as a strong liveness identity.
    """

    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        after_comm = stat.rsplit(") ", 1)[1]
    except IndexError:
        return None
    fields = after_comm.split()
    if len(fields) <= 19:
        return None
    return fields[19]
