"""Data models for workflow monitoring."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


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
