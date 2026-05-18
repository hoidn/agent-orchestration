#!/usr/bin/env python3
"""Normalize watchdog probe and optional repair output into one result bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()
REPAIR_STATUSES = {
    "NO_ACTION",
    "FIXED_AND_RESUMED",
    "FIXED_AND_RELAUNCHED",
    "PLAN_WRITTEN",
    "BLOCKED",
}
RECOVERY_ACTIONS = {"NONE", "RESUME", "RELAUNCH", "RESTART", "DECLINED"}


def _safe_relpath(value: str, *, under: str | None = None) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch-bundle-path", required=True)
    parser.add_argument("--repair-result-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    watch_rel = _safe_relpath(args.watch_bundle_path, under="state")
    repair_rel = _safe_relpath(args.repair_result_path, under="artifacts/work")
    output_rel = _safe_relpath(args.output, under="state")
    watch = _load_json(REPO_ROOT / watch_rel)

    repair_status = "NO_ACTION"
    fix_complexity = "NOT_APPLICABLE"
    recovery_action = "NONE"
    repair_report_path = ""
    plan_path = ""
    new_run_id = ""
    if watch.get("repair_required") == "YES":
        repair_path = REPO_ROOT / repair_rel
        if not repair_path.is_file():
            raise SystemExit(f"Repair was required but result is missing: {repair_rel}")
        repair = _load_json(repair_path)
        repair_status = str(repair.get("repair_status") or "")
        recovery_action = str(repair.get("recovery_action") or "")
        fix_complexity = str(repair.get("fix_complexity") or "")
        repair_report_path = str(repair.get("repair_report_path") or "")
        plan_path = str(repair.get("plan_path") or "")
        new_run_id = str(repair.get("new_run_id") or "")
        if repair_status not in REPAIR_STATUSES - {"NO_ACTION"}:
            raise SystemExit(f"Invalid repair_status: {repair_status}")
        if recovery_action not in RECOVERY_ACTIONS - {"NONE"}:
            raise SystemExit(f"Invalid recovery_action: {recovery_action}")
    result = {
        "schema": "orchestrator_run_watchdog_result/v1",
        "watchdog_result_path": output_rel.as_posix(),
        "target_run_id": watch.get("target_run_id"),
        "watch_status": watch.get("watch_status"),
        "repair_required": watch.get("repair_required"),
        "recommended_recovery": watch.get("recommended_recovery"),
        "repair_status": repair_status,
        "fix_complexity": fix_complexity,
        "recovery_action": recovery_action,
        "evidence_bundle_path": watch.get("evidence_bundle_path"),
        "repair_result_path": repair_rel.as_posix() if watch.get("repair_required") == "YES" else "",
        "repair_report_path": repair_report_path,
        "plan_path": plan_path,
        "new_run_id": new_run_id,
    }
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
