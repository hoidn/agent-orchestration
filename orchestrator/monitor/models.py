"""Data models for workflow monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class MonitorWorkspace:
    """One workspace root monitored for orchestrator runs."""

    name: str
    path: Path


@dataclass(frozen=True)
class MonitorTiming:
    """Polling and stale-run timing configuration."""

    poll_interval_seconds: int = 60
    stale_after_seconds: int = 900


@dataclass(frozen=True)
class EmailConfig:
    """Headless email delivery configuration."""

    backend: str
    from_address: str
    to: tuple[str, ...]
    smtp_host: str
    smtp_port: int = 587
    use_starttls: bool = True
    username_env: str | None = None
    password_env: str | None = None


@dataclass(frozen=True)
class MonitorConfig:
    """Complete monitor configuration."""

    workspaces: tuple[MonitorWorkspace, ...]
    monitor: MonitorTiming
    email: EmailConfig


class MonitorEventKind(Enum):
    """Notification-worthy monitor event kinds."""

    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CRASHED = "CRASHED"
    STALLED = "STALLED"


@dataclass(frozen=True)
class ProcessMetadata:
    """Run-local process metadata used for crash classification."""

    pid: int
    started_at: str
    process_start_time: str | None = None
    argv: tuple[str, ...] = ()
    tmux: str | None = None


@dataclass(frozen=True)
class MonitorRun:
    """One scanned run state from a configured workspace."""

    workspace: MonitorWorkspace
    run_dir_id: str
    run_root: Path
    state_path: Path
    state: Mapping[str, Any] | None = None
    read_error: str | None = None
    process: ProcessMetadata | None = None


@dataclass(frozen=True)
class MonitorEvent:
    """One event that may be sent as a notification."""

    kind: MonitorEventKind
    run: MonitorRun
    reason: str
    observed_at: str
