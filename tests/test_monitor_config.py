from pathlib import Path

import pytest

from orchestrator.monitor.config import load_monitor_config


def test_load_monitor_config_accepts_explicit_workspaces_and_smtp_env_names(tmp_path: Path):
    config_path = tmp_path / "monitor.yaml"
    config_path.write_text(
        """
workspaces:
  - name: repo
    path: /tmp/repo
monitor:
  poll_interval_seconds: 10
  stale_after_seconds: 120
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
  smtp_port: 587
  use_starttls: true
  username_env: SMTP_USER
  password_env: SMTP_PASSWORD
""",
        encoding="utf-8",
    )

    cfg = load_monitor_config(config_path)

    assert cfg.workspaces[0].name == "repo"
    assert cfg.workspaces[0].path == Path("/tmp/repo")
    assert cfg.monitor.poll_interval_seconds == 10
    assert cfg.monitor.stale_after_seconds == 120
    assert cfg.email.backend == "smtp"
    assert cfg.email.from_address == "monitor@example.com"
    assert cfg.email.to == ("user@example.com",)
    assert cfg.email.password_env == "SMTP_PASSWORD"


@pytest.mark.parametrize(
    ("body", "message"),
    [
        (
            """
workspaces: []
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
            "at least one workspace",
        ),
        (
            """
workspaces:
  - name: repo
    path: /tmp/repo
monitor:
  poll_interval_seconds: 0
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
            "poll_interval_seconds",
        ),
        (
            """
workspaces:
  - name: repo
    path: /tmp/repo
monitor:
  stale_after_seconds: -1
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
            "stale_after_seconds",
        ),
        (
            """
workspaces:
  - name: repo
    path: /tmp/repo
email:
  backend: webhook
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
            "unsupported email backend",
        ),
        (
            """
workspaces:
  - name: repo
    path: /tmp/repo
email:
  backend: smtp
  from: monitor@example.com
  smtp_host: smtp.example.com
""",
            "email.to",
        ),
        (
            """
workspaces:
  - name: repo
    path: /tmp/repo
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
  password: literal-secret
""",
            "literal password",
        ),
    ],
)
def test_load_monitor_config_rejects_invalid_config(tmp_path: Path, body: str, message: str):
    config_path = tmp_path / "monitor.yaml"
    config_path.write_text(body, encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_monitor_config(config_path)
