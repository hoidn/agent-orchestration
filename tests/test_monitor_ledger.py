import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from orchestrator.monitor.ledger import NotificationLedger
from orchestrator.monitor.models import MonitorEvent, MonitorEventKind, MonitorRun, MonitorWorkspace


def _event(tmp_path: Path, kind: MonitorEventKind = MonitorEventKind.FAILED) -> MonitorEvent:
    workspace = MonitorWorkspace(name="repo", path=tmp_path / "repo")
    run_root = workspace.path / ".orchestrate" / "runs" / "run1"
    return MonitorEvent(
        kind=kind,
        run=MonitorRun(
            workspace=workspace,
            run_dir_id="run1",
            run_root=run_root,
            state_path=run_root / "state.json",
            state={"run_id": "run1", "status": kind.value.lower()},
        ),
        reason="test",
        observed_at=datetime(2026, 4, 28, tzinfo=timezone.utc).isoformat(),
    )


def test_missing_ledger_starts_empty(tmp_path: Path):
    ledger = NotificationLedger.load(tmp_path / "notifications.json")

    assert not ledger.has_sent(_event(tmp_path))


def test_ledger_records_and_suppresses_duplicates_across_reload(tmp_path: Path):
    path = tmp_path / "notifications.json"
    event = _event(tmp_path)

    ledger = NotificationLedger.load(path)
    assert not ledger.has_sent(event)

    ledger.mark_sent(event, sent_at="2026-04-28T12:00:00+00:00")
    ledger.save()

    reloaded = NotificationLedger.load(path)
    assert reloaded.has_sent(event)
    assert not reloaded.has_sent(_event(tmp_path, MonitorEventKind.COMPLETED))


def test_ledger_save_uses_temp_file_rename_without_leaving_temp_file(tmp_path: Path):
    path = tmp_path / "nested" / "notifications.json"
    ledger = NotificationLedger.load(path)
    ledger.mark_sent(_event(tmp_path), sent_at="2026-04-28T12:00:00+00:00")

    ledger.save()

    assert path.exists()
    assert not list(path.parent.glob("*.tmp"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema"] == "orchestrator-monitor-ledger/v1"


def test_malformed_ledger_raises_clear_error(tmp_path: Path):
    path = tmp_path / "notifications.json"
    path.write_text('{"schema": "wrong", "sent": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="monitor ledger"):
        NotificationLedger.load(path)
