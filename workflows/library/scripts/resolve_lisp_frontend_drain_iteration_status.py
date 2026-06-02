#!/usr/bin/env python3
"""Resolve one drain iteration status after recovery-before-selection routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VALID_STATUS = {"CONTINUE", "DONE", "BLOCKED"}
VALID_RECOVERY_STATUS = {"CONTINUE", "BLOCKED", "RUN_RECOVERED_GAP"}


def _read_status(path: str) -> str:
    path_obj = Path(path)
    value = path_obj.read_text(encoding="utf-8").strip() if path_obj.exists() else path.strip()
    if value not in VALID_STATUS:
        raise SystemExit(f"Unexpected drain status in {path}: {value}")
    return value


def _read_recovery_status(value_or_path: str) -> str:
    path_obj = Path(value_or_path)
    value = path_obj.read_text(encoding="utf-8").strip() if path_obj.exists() else value_or_path.strip()
    if value not in VALID_RECOVERY_STATUS:
        raise SystemExit(f"Unexpected recovery status in {value_or_path}: {value}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-selection-bundle-path", required=True)
    parser.add_argument("--normal-status-path", required=True)
    parser.add_argument("--recovery-record-status-path", required=True)
    parser.add_argument("--recovered-work-item-status-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    route = json.loads(Path(args.pre_selection_bundle_path).read_text(encoding="utf-8")).get("pre_selection_route")
    if route == "SELECT_NORMAL_WORK":
        status = _read_status(args.normal_status_path)
    elif route == "RECOVER_BLOCKED_DESIGN_GAP":
        recovery_status = _read_recovery_status(args.recovery_record_status_path)
        if recovery_status == "RUN_RECOVERED_GAP":
            recovered_status_path = Path(args.recovered_work_item_status_path)
            status = _read_status(args.recovered_work_item_status_path) if recovered_status_path.exists() else "BLOCKED"
        elif recovery_status == "BLOCKED":
            status = "BLOCKED"
        else:
            status = "CONTINUE"
    elif route == "BLOCKED":
        status = "BLOCKED"
    else:
        raise SystemExit(f"Unexpected pre_selection_route: {route}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
