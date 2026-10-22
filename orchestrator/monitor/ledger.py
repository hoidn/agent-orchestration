"""Notification de-duplication ledger for workflow monitor emails."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .._common.io_atomic import atomic_write_text
from .models import MonitorEvent, MonitorEventKind

LEDGER_SCHEMA = "orchestrator-monitor-ledger/v1"


@dataclass
class NotificationLedger:
    """Persistent record of monitor notifications already sent."""

    path: Path
    sent: list[dict[str, str]] = field(default_factory=list)

    @classmethod
    def load(cls, path: str | Path) -> "NotificationLedger":
        ledger_path = Path(path).expanduser()
        if not ledger_path.exists():
            return cls(path=ledger_path)
        try:
            payload = json.loads(ledger_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"failed to read monitor ledger: {ledger_path}") from exc
        if not isinstance(payload, Mapping) or payload.get("schema") != LEDGER_SCHEMA:
            raise ValueError(f"invalid monitor ledger schema: {ledger_path}")
        sent = payload.get("sent")
        if not isinstance(sent, list):
            raise ValueError(f"invalid monitor ledger entries: {ledger_path}")
        entries: list[dict[str, str]] = []
        for index, entry in enumerate(sent):
            if not isinstance(entry, Mapping):
                raise ValueError(f"invalid monitor ledger entry at index {index}")
            entries.append({str(key): str(value) for key, value in entry.items()})
        return cls(path=ledger_path, sent=entries)

    def has_sent(self, event: MonitorEvent) -> bool:
        key = self._event_key(event)
        return any(self._entry_key(entry) == key for entry in self.sent)

    def mark_sent(self, event: MonitorEvent, *, sent_at: str) -> None:
        if self.has_sent(event):
            return
        workspace, run_dir_id, event_kind, request_id = self._event_key(event)
        entry = {
            "workspace": workspace,
            "run_dir_id": run_dir_id,
            "event_kind": event_kind,
            "sent_at": sent_at,
        }
        if event.kind is MonitorEventKind.SUSPENDED:
            if not request_id:
                raise ValueError("suspended monitor event is missing request_id")
            entry["request_id"] = request_id
        self.sent.append(entry)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema": LEDGER_SCHEMA, "sent": self.sent}
        atomic_write_text(self.path, json.dumps(payload, indent=2))

    def _event_key(self, event: MonitorEvent) -> tuple[str, str, str, str | None]:
        workspace = str(event.run.workspace.path.expanduser().resolve(strict=False))
        request_id = event.request_id if event.kind is MonitorEventKind.SUSPENDED else None
        return (workspace, event.run.run_dir_id, event.kind.value, request_id)

    def _entry_key(self, entry: Mapping[str, str]) -> tuple[str, str, str, str | None]:
        workspace = str(Path(entry.get("workspace", "")).expanduser().resolve(strict=False))
        request_id = entry.get("request_id") if entry.get("event_kind") == MonitorEventKind.SUSPENDED.value else None
        return (workspace, entry.get("run_dir_id", ""), entry.get("event_kind", ""), request_id)
