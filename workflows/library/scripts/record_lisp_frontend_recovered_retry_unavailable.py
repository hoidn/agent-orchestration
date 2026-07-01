#!/usr/bin/env python3
"""Record when a recovered design-gap retry was requested but did not produce status."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_value_or_path(value: str) -> str:
    path = Path(value)
    return path.read_text(encoding="utf-8").strip() if path.exists() else value.strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _record_retry_unavailable(run_state_path: Path, *, design_gap_id: str, reason: str) -> None:
    state = _load_json(run_state_path)
    blocked = dict(state.get("blocked_design_gaps") or {})
    entry = dict(blocked.get(design_gap_id) or {})
    if not entry:
        entry = {"reason": "implementation_blocked"}
    entry.setdefault("reason", "implementation_blocked")
    entry["retry_block_reason"] = reason
    entry["retry_blocked_at_utc"] = _timestamp()
    blocked[design_gap_id] = entry
    state["blocked_design_gaps"] = blocked
    state.setdefault("history", []).append(
        {
            "event": "recovered_retry_unavailable",
            "item_id": design_gap_id,
            "source": "DESIGN_GAP",
            "reason": reason,
            "timestamp_utc": _timestamp(),
        }
    )
    _write_json(run_state_path, state)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-selection-bundle-path", required=True)
    parser.add_argument("--recovery-record-status-path", required=True)
    parser.add_argument("--recovered-work-item-status-path", required=True)
    parser.add_argument("--recovered-work-item-status-value", default="")
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pre_selection = _load_json(Path(args.pre_selection_bundle_path))
    route = str(pre_selection.get("pre_selection_route") or "").strip()
    design_gap_id = str(pre_selection.get("design_gap_id") or "").strip()
    recovery_status = _read_value_or_path(args.recovery_record_status_path)
    recovered_status = args.recovered_work_item_status_value.strip()
    recovered_status_exists = bool(recovered_status) or Path(args.recovered_work_item_status_path).exists()
    reason = ""
    record_status = "NOT_APPLICABLE"

    if route == "RECOVER_BLOCKED_DESIGN_GAP" and recovery_status == "RUN_RECOVERED_GAP":
        if recovered_status_exists:
            record_status = "RETRY_STATUS_AVAILABLE"
        else:
            if not design_gap_id:
                raise SystemExit("Missing design_gap_id for recovered retry unavailable record")
            reason = "recovered_retry_status_missing"
            _record_retry_unavailable(Path(args.run_state_path), design_gap_id=design_gap_id, reason=reason)
            record_status = "BLOCKED_RECORDED"

    _write_json(Path(args.output), {"record_status": record_status, "retry_block_reason": reason})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
