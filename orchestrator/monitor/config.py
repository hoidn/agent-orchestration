"""Configuration loading for the workflow monitor."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

from .models import EmailConfig, MonitorConfig, MonitorTiming, MonitorWorkspace


def load_monitor_config(path: str | Path) -> MonitorConfig:
    """Load and validate a monitor YAML config."""

    config_path = Path(path).expanduser()
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"failed to read monitor config: {config_path}") from exc
    if not isinstance(raw, Mapping):
        raise ValueError("monitor config must be a YAML mapping")

    return MonitorConfig(
        workspaces=_parse_workspaces(raw.get("workspaces")),
        monitor=_parse_timing(raw.get("monitor", {})),
        email=_parse_email(raw.get("email")),
    )


def _parse_workspaces(value: Any) -> tuple[MonitorWorkspace, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("at least one workspace is required")

    workspaces: list[MonitorWorkspace] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(f"workspaces[{index}] must be a mapping")
        name = item.get("name")
        raw_path = item.get("path")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"workspaces[{index}].name is required")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError(f"workspaces[{index}].path is required")
        workspaces.append(MonitorWorkspace(name=name.strip(), path=Path(raw_path).expanduser()))
    return tuple(workspaces)


def _parse_timing(value: Any) -> MonitorTiming:
    if value is None:
        value = {}
    if not isinstance(value, Mapping):
        raise ValueError("monitor must be a mapping")

    poll = _positive_int(value.get("poll_interval_seconds", 60), "poll_interval_seconds")
    stale = _positive_int(value.get("stale_after_seconds", 900), "stale_after_seconds")
    return MonitorTiming(poll_interval_seconds=poll, stale_after_seconds=stale)


def _parse_email(value: Any) -> EmailConfig:
    if not isinstance(value, Mapping):
        raise ValueError("email must be a mapping")
    if "password" in value:
        raise ValueError("literal password values are not allowed; use password_env")

    backend = value.get("backend")
    if backend != "smtp":
        raise ValueError(f"unsupported email backend: {backend!r}")

    from_address = value.get("from")
    if not isinstance(from_address, str) or not from_address.strip():
        raise ValueError("email.from is required")

    recipients = value.get("to")
    if not isinstance(recipients, list) or not recipients:
        raise ValueError("email.to must contain at least one recipient")
    normalized_to: list[str] = []
    for index, recipient in enumerate(recipients):
        if not isinstance(recipient, str) or not recipient.strip():
            raise ValueError(f"email.to[{index}] must be a non-empty string")
        normalized_to.append(recipient.strip())

    smtp_host = value.get("smtp_host")
    if not isinstance(smtp_host, str) or not smtp_host.strip():
        raise ValueError("email.smtp_host is required")

    return EmailConfig(
        backend=backend,
        from_address=from_address.strip(),
        to=tuple(normalized_to),
        smtp_host=smtp_host.strip(),
        smtp_port=_positive_int(value.get("smtp_port", 587), "smtp_port"),
        use_starttls=_bool(value.get("use_starttls", True), "use_starttls"),
        username_env=_optional_str(value.get("username_env"), "username_env"),
        password_env=_optional_str(value.get("password_env"), "password_env"),
    )


def _positive_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _optional_str(value: Any, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    return value.strip()
