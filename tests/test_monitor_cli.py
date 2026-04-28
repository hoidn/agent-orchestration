import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.cli.main import main


def _write_config(tmp_path: Path, workspace: Path) -> Path:
    config = tmp_path / "monitor.yaml"
    config.write_text(
        f"""
workspaces:
  - name: repo
    path: {workspace}
monitor:
  poll_interval_seconds: 1
  stale_after_seconds: 300
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
        encoding="utf-8",
    )
    return config


def _write_completed_run(workspace: Path) -> None:
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": "workflows/demo.yaml",
                "updated_at": datetime(2026, 4, 28, tzinfo=timezone.utc).isoformat(),
            }
        ),
        encoding="utf-8",
    )


def test_monitor_help_exposes_expected_flags():
    result = subprocess.run(
        [sys.executable, "-m", "orchestrator", "monitor", "--help"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )

    assert result.returncode == 0
    assert "--config" in result.stdout
    assert "--once" in result.stdout
    assert "--dry-run" in result.stdout
    assert "--dry-run-mark-sent" in result.stdout
    assert "--ledger" in result.stdout


def test_monitor_once_dry_run_prints_notification_without_marking_ledger(
    tmp_path: Path,
    capsys,
):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_completed_run(workspace)
    config = _write_config(tmp_path, workspace)
    ledger = tmp_path / "notifications.json"

    exit_code = main(
        [
            "monitor",
            "--config",
            str(config),
            "--once",
            "--dry-run",
            "--ledger",
            str(ledger),
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "[orchestrator] COMPLETED repo run1" in captured.out
    assert not ledger.exists()


def test_monitor_dry_run_mark_sent_suppresses_second_notification(tmp_path: Path, capsys):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_completed_run(workspace)
    config = _write_config(tmp_path, workspace)
    ledger = tmp_path / "notifications.json"
    args = [
        "monitor",
        "--config",
        str(config),
        "--once",
        "--dry-run",
        "--dry-run-mark-sent",
        "--ledger",
        str(ledger),
    ]

    assert main(args) == 0
    first = capsys.readouterr()
    assert "[orchestrator] COMPLETED repo run1" in first.out

    assert main(args) == 0
    second = capsys.readouterr()
    assert "[orchestrator] COMPLETED repo run1" not in second.out
    assert "No monitor notifications" in second.out


def test_monitor_missing_config_exits_nonzero(capsys):
    exit_code = main(["monitor", "--config", "/tmp/does-not-exist.yaml", "--once", "--dry-run"])

    captured = capsys.readouterr()
    assert exit_code == 1
    assert "failed to read monitor config" in captured.err
