"""Notification de-duplication ledger for workflow monitor emails."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .models import MonitorEvent

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
        workspace, run_dir_id, event_kind = self._event_key(event)
        self.sent.append(
            {
                "workspace": workspace,
                "run_dir_id": run_dir_id,
                "event_kind": event_kind,
                "sent_at": sent_at,
            }
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f"{self.path.name}.tmp")
        payload = {"schema": LEDGER_SCHEMA, "sent": self.sent}
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _event_key(self, event: MonitorEvent) -> tuple[str, str, str]:
        workspace = str(event.run.workspace.path.expanduser().resolve(strict=False))
        return (workspace, event.run.run_dir_id, event.kind.value)

    def _entry_key(self, entry: Mapping[str, str]) -> tuple[str, str, str]:
        workspace = str(Path(entry.get("workspace", "")).expanduser().resolve(strict=False))
        return (workspace, entry.get("run_dir_id", ""), entry.get("event_kind", ""))
