import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.monitor.emailer import SmtpEmailSender
from orchestrator.monitor.messages import render_event_email
from orchestrator.monitor.models import (
    EmailConfig,
    MonitorConfig,
    MonitorEvent,
    MonitorEventKind,
    MonitorRun,
    MonitorTiming,
    MonitorWorkspace,
)


def _config() -> MonitorConfig:
    return MonitorConfig(
        workspaces=(MonitorWorkspace(name="repo", path=Path("/tmp/repo")),),
        monitor=MonitorTiming(),
        email=EmailConfig(
            backend="smtp",
            from_address="monitor@example.com",
            to=("user@example.com",),
            smtp_host="smtp.example.com",
            username_env="SMTP_USER",
            password_env="SMTP_PASSWORD",
        ),
    )


def _event(tmp_path: Path, kind: MonitorEventKind = MonitorEventKind.FAILED) -> MonitorEvent:
    workspace = MonitorWorkspace(name="repo", path=tmp_path)
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "Step.stderr").write_text("token=super-secret\n" + ("x" * 9000), encoding="utf-8")
    (logs / "Step.stdout").write_text("normal stdout\n", encoding="utf-8")
    (logs / "Step.prompt.txt").write_text("prompt audit must not appear", encoding="utf-8")
    (run_root / "provider_sessions").mkdir(exist_ok=True)
    (run_root / "provider_sessions" / "Step.transport.log").write_text(
        "transport must not appear",
        encoding="utf-8",
    )
    state = {
        "run_id": "run1",
        "status": "failed",
        "workflow_file": "workflows/demo.yaml",
        "started_at": "2026-04-28T11:00:00+00:00",
        "updated_at": "2026-04-28T12:00:00+00:00",
        "current_step": {
            "name": "Step",
            "last_heartbeat_at": "2026-04-28T11:59:00+00:00",
        },
        "steps": {
            "Step": {
                "status": "failed",
                "error": {"type": "command_failed", "message": "boom"},
            }
        },
        "workflow_outputs": {"report": "artifacts/report.md"},
    }
    return MonitorEvent(
        kind=kind,
        run=MonitorRun(
            workspace=workspace,
            run_dir_id="run1",
            run_root=run_root,
            state_path=run_root / "state.json",
            state=state,
        ),
        reason="state_failed",
        observed_at=datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc).isoformat(),
    )


def test_render_event_email_includes_context_and_safe_capped_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SMTP_PASSWORD", "super-secret")

    message = render_event_email(_event(tmp_path), _config())
    body = message.get_content()

    assert message["Subject"] == "[orchestrator] FAILED repo run1"
    assert message["From"] == "monitor@example.com"
    assert message["To"] == "user@example.com"
    assert "Workspace: repo" in body
    assert f"Workspace path: {tmp_path}" in body
    assert "Workflow: workflows/demo.yaml" in body
    assert "Current/failed step: Step" in body
    assert "Error: command_failed: boom" in body
    assert "artifacts/report.md" in body
    assert "python -m orchestrator report --run-id run1" in body
    assert "normal stdout" in body
    assert "[REDACTED]" in body
    assert "super-secret" not in body
    assert "prompt audit must not appear" not in body
    assert "transport must not appear" not in body
    assert len(body) < 10_000


def test_smtp_sender_dry_run_returns_message_without_network(tmp_path: Path):
    message = render_event_email(_event(tmp_path), _config())

    result = SmtpEmailSender(_config().email).send(message, dry_run=True)

    assert result.sent is False
    assert "FAILED repo run1" in result.preview


def test_smtp_sender_reads_credentials_from_environment(monkeypatch: pytest.MonkeyPatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, username, password):
            calls.append(("login", username, password))

        def send_message(self, message):
            calls.append(("send", message["Subject"]))

    monkeypatch.setenv("SMTP_USER", "user")
    monkeypatch.setenv("SMTP_PASSWORD", "password")
    monkeypatch.setattr("orchestrator.monitor.emailer.smtplib.SMTP", FakeSMTP)

    message = render_event_email(_event(Path("/tmp/repo")), _config())
    result = SmtpEmailSender(_config().email).send(message)

    assert result.sent is True
    assert ("login", "user", "password") in calls
    assert ("send", "[orchestrator] FAILED repo run1") in calls


def test_smtp_sender_missing_secret_error_does_not_leak_configured_secret_name(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="required SMTP credential"):
        SmtpEmailSender(_config().email).send(
            render_event_email(_event(Path("/tmp/repo")), _config()),
        )
