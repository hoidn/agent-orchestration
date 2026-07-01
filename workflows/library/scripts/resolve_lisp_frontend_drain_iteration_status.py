#!/usr/bin/env python3
"""Resolve one drain iteration status after recovery-before-selection routing."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


VALID_STATUS = {"CONTINUE", "DONE", "BLOCKED"}
VALID_RECOVERY_STATUS = {"CONTINUE", "BLOCKED", "RUN_RECOVERED_GAP"}


def _read_status(path: str, *, valid: set[str], label: str) -> str:
    path_obj = Path(path)
    if not path_obj.exists():
        raise SystemExit(f"Missing required {label} status file: {path}")
    value = path_obj.read_text(encoding="utf-8").strip()
    if value not in valid:
        raise SystemExit(f"Unexpected {label} status in {path}: {value}")
    return value


def _read_optional_recovered_status(path: str) -> str:
    path_obj = Path(path)
    if not path_obj.exists():
        return "CONTINUE"
    return _read_status(path, valid=VALID_STATUS, label="recovered work-item")


def _read_optional_recovered_status_value_or_path(value: str, path: str) -> str:
    value = value.strip()
    if value:
        if value not in VALID_STATUS:
            raise SystemExit(f"Unexpected recovered work-item status value: {value}")
        return value
    return _read_optional_recovered_status(path)


def _read_optional_step_back_status(path: str) -> str:
    if not path:
        return ""
    path_obj = Path(path)
    if not path_obj.exists():
        return ""
    return _read_status(path, valid=VALID_STATUS, label="step-back")


def _has_recorded_blocked_work(run_state_path: str) -> bool:
    state_path = Path(run_state_path)
    if not state_path.exists():
        raise SystemExit(f"Missing required run state file for BLOCKED drain status: {run_state_path}")
    state = json.loads(state_path.read_text(encoding="utf-8"))
    return bool(state.get("blocked_items") or state.get("blocked_design_gaps") or state.get("blocked_run"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-selection-bundle-path", required=True)
    parser.add_argument("--normal-status-path", required=True)
    parser.add_argument("--prerequisite-recovery-status-path", required=True)
    parser.add_argument("--recovery-record-status-path", required=True)
    parser.add_argument("--recovered-work-item-status-path", required=True)
    parser.add_argument("--recovered-work-item-status-value", default="")
    parser.add_argument("--step-back-status-path", default="")
    parser.add_argument("--run-state-path", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    route = json.loads(Path(args.pre_selection_bundle_path).read_text(encoding="utf-8")).get("pre_selection_route")
    if route == "SELECT_NORMAL_WORK":
        status = _read_status(args.normal_status_path, valid=VALID_STATUS, label="normal")
    elif route == "SELECT_PREREQUISITE_WORK":
        status = _read_status(args.prerequisite_recovery_status_path, valid=VALID_STATUS, label="prerequisite recovery")
    elif route == "RECOVER_BLOCKED_DESIGN_GAP":
        recovery_status = _read_status(
            args.recovery_record_status_path,
            valid=VALID_RECOVERY_STATUS,
            label="recovery record",
        )
        if recovery_status == "RUN_RECOVERED_GAP":
            status = _read_optional_recovered_status_value_or_path(
                args.recovered_work_item_status_value,
                args.recovered_work_item_status_path,
            )
        elif recovery_status == "BLOCKED":
            status = "BLOCKED"
        else:
            status = "CONTINUE"
    elif route == "BLOCKED":
        status = _read_optional_step_back_status(args.step_back_status_path) or "BLOCKED"
    else:
        raise SystemExit(f"Unexpected pre_selection_route: {route}")

    if status == "BLOCKED" and args.run_state_path and not _has_recorded_blocked_work(args.run_state_path):
        raise SystemExit("BLOCKED drain status requires recorded blocked work or run-level blocker in run state")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
