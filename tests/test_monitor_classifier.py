import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.monitor.classifier import classify_run
from orchestrator.monitor.config import load_monitor_config
from orchestrator.monitor.models import MonitorEventKind
from orchestrator.monitor.process import write_process_metadata
from orchestrator.monitor.scanner import scan_monitor_runs


NOW = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)


def _write_config(path: Path, workspace: Path) -> Path:
    config_path = path / "monitor.yaml"
    config_path.write_text(
        f"""
workspaces:
  - name: repo
    path: {workspace}
monitor:
  poll_interval_seconds: 10
  stale_after_seconds: 300
email:
  backend: smtp
  from: monitor@example.com
  to: [user@example.com]
  smtp_host: smtp.example.com
""",
        encoding="utf-8",
    )
    return config_path


def _write_state(workspace: Path, run_id: str, state: dict) -> Path:
    run_root = workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state_path = run_root / "state.json"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return run_root


def _scan_one(tmp_path: Path, workspace: Path):
    cfg = load_monitor_config(_write_config(tmp_path, workspace))
    return scan_monitor_runs(cfg)[0], cfg


def test_completed_state_produces_completed_event(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_state(workspace, "run1", {"run_id": "run1", "status": "completed"})

    run, cfg = _scan_one(tmp_path, workspace)
    event = classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds)

    assert event is not None
    assert event.kind is MonitorEventKind.COMPLETED


def test_failed_state_produces_failed_event(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_state(
        workspace,
        "run1",
        {"run_id": "run1", "status": "failed", "error": {"message": "boom"}},
    )

    run, cfg = _scan_one(tmp_path, workspace)
    event = classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds)

    assert event is not None
    assert event.kind is MonitorEventKind.FAILED
    assert event.run.state["error"]["message"] == "boom"


def test_running_state_with_fresh_heartbeat_produces_no_event(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_state(
        workspace,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "updated_at": (NOW - timedelta(hours=1)).isoformat(),
            "current_step": {
                "name": "Work",
                "last_heartbeat_at": (NOW - timedelta(seconds=30)).isoformat(),
            },
        },
    )

    run, cfg = _scan_one(tmp_path, workspace)

    assert classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds) is None


def test_running_state_with_stale_heartbeat_produces_stalled_event(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_state(
        workspace,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "current_step": {
                "name": "Work",
                "last_heartbeat_at": (NOW - timedelta(minutes=10)).isoformat(),
            },
        },
    )

    run, cfg = _scan_one(tmp_path, workspace)
    event = classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds)

    assert event is not None
    assert event.kind is MonitorEventKind.STALLED
    assert event.reason == "stale_heartbeat"


def test_running_state_without_heartbeat_falls_back_to_updated_at(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _write_state(
        workspace,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "updated_at": (NOW - timedelta(minutes=10)).isoformat(),
        },
    )

    run, cfg = _scan_one(tmp_path, workspace)
    event = classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds)

    assert event is not None
    assert event.kind is MonitorEventKind.STALLED
    assert event.reason == "stale_updated_at"


def test_running_state_with_dead_recorded_pid_produces_crashed_event(tmp_path: Path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    run_root = _write_state(
        workspace,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "updated_at": NOW.isoformat(),
            "current_step": {"last_heartbeat_at": NOW.isoformat()},
        },
    )
    write_process_metadata(run_root, pid=999_999_999, argv=["python", "-m", "orchestrator"])

    run, cfg = _scan_one(tmp_path, workspace)
    event = classify_run(run, now=NOW, stale_after_seconds=cfg.monitor.stale_after_seconds)

    assert event is not None
    assert event.kind is MonitorEventKind.CRASHED
    assert event.reason == "process_not_alive"


def test_scanner_records_invalid_state_without_crashing(tmp_path: Path):
    workspace = tmp_path / "repo"
    run_root = workspace / ".orchestrate" / "runs" / "bad"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text("{bad", encoding="utf-8")

    cfg = load_monitor_config(_write_config(tmp_path, workspace))
    runs = scan_monitor_runs(cfg)

    assert len(runs) == 1
    assert runs[0].state is None
    assert "Expecting property name" in (runs[0].read_error or "")
