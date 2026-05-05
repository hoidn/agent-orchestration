"""Runtime-owned pending managed-job policy sidecar."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def append_pending_record(path: Path, record: dict[str, Any]) -> None:
    """Append one pending classification record."""

    payload = dict(record)
    payload.setdefault("timestamp", time.time())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
        handle.write("\n")


def read_pending_records(path: Path) -> list[dict[str, Any]]:
    """Read pending classification records."""

    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            record = json.loads(line)
            if isinstance(record, dict):
                records.append(record)
    return records
