"""Deterministic email rendering for workflow monitor events."""

from __future__ import annotations

import os
import re
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Mapping

from .models import MonitorConfig, MonitorEvent

MAX_STREAM_PREVIEW_CHARS = 4096
MAX_TOTAL_LOG_PREVIEW_CHARS = 8192
SECRET_LINE_RE = re.compile(r"(?i)\\b(password|secret|token|api[_-]?key)\\b\\s*[:=]")


def render_event_email(event: MonitorEvent, config: MonitorConfig) -> EmailMessage:
    """Render a deterministic plaintext email for a monitor event."""

    message = EmailMessage()
    message["Subject"] = f"[orchestrator] {event.kind.value} {event.run.workspace.name} {event.run.run_dir_id}"
    message["From"] = config.email.from_address
    message["To"] = ", ".join(config.email.to)
    message.set_content(_render_body(event, config))
    return message


def _render_body(event: MonitorEvent, config: MonitorConfig) -> str:
    state = event.run.state if isinstance(event.run.state, Mapping) else {}
    step_name = _current_or_failed_step(state)
    lines = [
        f"Event: {event.kind.value}",
        f"Reason: {event.reason}",
        f"Workspace: {event.run.workspace.name}",
        f"Workspace path: {event.run.workspace.path}",
        f"Run: {event.run.run_dir_id}",
        f"Run root: {event.run.run_root}",
        f"Workflow: {state.get('workflow_file', '')}",
        f"Persisted status: {state.get('status', '')}",
        f"Started at: {state.get('started_at', '')}",
        f"Updated at: {state.get('updated_at', '')}",
        f"Heartbeat at: {_heartbeat_at(state) or ''}",
        f"Observed at: {event.observed_at}",
        f"Current/failed step: {step_name or ''}",
    ]
    error = _error_summary(state, step_name)
    if error:
        lines.append(f"Error: {error}")
    workflow_outputs = state.get("workflow_outputs")
    if isinstance(workflow_outputs, Mapping) and workflow_outputs:
        lines.append("")
        lines.append("Workflow outputs:")
        for key, value in workflow_outputs.items():
            lines.append(f"- {key}: {value}")
    lines.extend(
        [
            "",
            "Suggested commands:",
            f"- cd {event.run.workspace.path}",
            f"- python -m orchestrator report --run-id {event.run.run_dir_id}",
            f"- python -m orchestrator resume {event.run.run_dir_id}",
        ]
    )
    previews = _safe_log_previews(event.run.run_root, step_name, _secret_values(config))
    if previews:
        lines.append("")
        lines.append("Log previews:")
        lines.extend(previews)
    return "\n".join(lines).rstrip() + "\n"


def _current_or_failed_step(state: Mapping[str, Any]) -> str | None:
    current_step = state.get("current_step")
    if isinstance(current_step, Mapping):
        name = current_step.get("name") or current_step.get("step_id")
        if isinstance(name, str) and name:
            return name
    steps = state.get("steps")
    if isinstance(steps, Mapping):
        for name, payload in reversed(list(steps.items())):
            if isinstance(payload, Mapping) and payload.get("status") == "failed":
                return str(name)
    return None


def _error_summary(state: Mapping[str, Any], step_name: str | None) -> str:
    error = state.get("error")
    if isinstance(error, Mapping):
        return _format_error(error)
    steps = state.get("steps")
    if isinstance(steps, Mapping) and step_name and isinstance(steps.get(step_name), Mapping):
        step_error = steps[step_name].get("error")
        if isinstance(step_error, Mapping):
            return _format_error(step_error)
    if isinstance(steps, Mapping):
        for payload in reversed(list(steps.values())):
            if isinstance(payload, Mapping) and isinstance(payload.get("error"), Mapping):
                return _format_error(payload["error"])
    return ""


def _format_error(error: Mapping[str, Any]) -> str:
    error_type = error.get("type")
    message = error.get("message")
    if error_type and message:
        return f"{error_type}: {message}"
    if message:
        return str(message)
    return str(error)


def _heartbeat_at(state: Mapping[str, Any]) -> str | None:
    current_step = state.get("current_step")
    if not isinstance(current_step, Mapping):
        return None
    heartbeat = current_step.get("last_heartbeat_at") or current_step.get("started_at")
    return heartbeat if isinstance(heartbeat, str) else None


def _safe_log_previews(run_root: Path, step_name: str | None, secrets: tuple[str, ...]) -> list[str]:
    if not step_name:
        return []
    logs_root = (run_root / "logs").resolve(strict=False)
    previews: list[str] = []
    total = 0
    for suffix in ("stdout", "stderr"):
        path = logs_root / f"{step_name}.{suffix}"
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(run_root.resolve(strict=False))
        except (OSError, ValueError):
            continue
        if resolved.name.endswith(".prompt.txt") or "provider_sessions" in resolved.parts:
            continue
        try:
            text = resolved.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        text = _redact(text[:MAX_STREAM_PREVIEW_CHARS], secrets)
        remaining = MAX_TOTAL_LOG_PREVIEW_CHARS - total
        if remaining <= 0:
            break
        text = text[:remaining]
        total += len(text)
        previews.append(f"--- {resolved.relative_to(run_root)} ---")
        previews.append(text.rstrip())
    return previews


def _secret_values(config: MonitorConfig) -> tuple[str, ...]:
    values: list[str] = []
    for env_name in (config.email.username_env, config.email.password_env):
        if not env_name:
            continue
        value = os.environ.get(env_name)
        if value:
            values.append(value)
    return tuple(values)


def _redact(text: str, secrets: tuple[str, ...]) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    lines = []
    for line in redacted.splitlines():
        if SECRET_LINE_RE.search(line):
            lines.append("[REDACTED]")
        else:
            lines.append(line)
    return "\n".join(lines)
