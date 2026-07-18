#!/usr/bin/env python3
"""Normalize watchdog probe and optional repair output into one result bundle."""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()
RUN_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]+$")
WATCH_STATUSES = {"RUNNING_OK", "COMPLETED", "FAILED", "CRASHED", "STALLED", "UNKNOWN"}
REPAIR_REQUIRED_VALUES = {"YES", "NO"}
RECOMMENDED_RECOVERIES = {"NONE", "RESUME", "RELAUNCH", "INVESTIGATE"}
REPAIR_STATUSES = {
    "NO_ACTION",
    "FIXED_AND_RESUMED",
    "FIXED_AND_RELAUNCHED",
    "PLAN_WRITTEN",
    "BLOCKED",
}
RECOVERY_ACTIONS = {"NONE", "RESUME", "RELAUNCH", "RESTART", "DECLINED"}
FIX_COMPLEXITIES = {"NOT_APPLICABLE", "TRIVIAL", "NONTRIVIAL"}
TYPED_ARGUMENTS = (
    "target_run_id",
    "watch_status",
    "repair_required",
    "recommended_recovery",
    "evidence_bundle_path",
    "repair_status",
    "fix_complexity",
    "recovery_action",
    "repair_report_path",
    "plan_path",
    "new_run_id",
)


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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_runtime_bundle(
    result: dict[str, Any], *, semantic_output_rel: Path
) -> None:
    raw_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not raw_path:
        return
    bundle_rel = _safe_relpath(raw_path)
    if bundle_rel == semantic_output_rel:
        return
    _write_json(
        REPO_ROOT / bundle_rel,
        {
            "watch_status": result["watch_status"],
            "repair_status": result["repair_status"],
            "recovery_action": result["recovery_action"],
            "watchdog_result_path": result["watchdog_result_path"],
        },
    )


def _require_member(name: str, value: str, allowed: set[str]) -> str:
    if value not in allowed:
        raise SystemExit(f"Invalid {name}: {value}")
    return value


def _optional_relpath(value: str, *, under: str | None = None) -> str:
    if not value:
        return ""
    return _safe_relpath(value, under=under).as_posix()


def _typed_result(args: argparse.Namespace, *, output_rel: Path) -> dict[str, Any]:
    missing = [name for name in TYPED_ARGUMENTS if getattr(args, name) is None]
    if missing:
        raise SystemExit(
            "Typed watchdog publication requires all typed fields; missing: "
            + ", ".join(missing)
        )
    if not RUN_ID_RE.fullmatch(args.target_run_id):
        raise SystemExit(f"Unsafe target run id: {args.target_run_id}")

    watch_status = _require_member("watch_status", args.watch_status, WATCH_STATUSES)
    repair_required = _require_member(
        "repair_required", args.repair_required, REPAIR_REQUIRED_VALUES
    )
    recommended_recovery = _require_member(
        "recommended_recovery", args.recommended_recovery, RECOMMENDED_RECOVERIES
    )
    repair_status = _require_member("repair_status", args.repair_status, REPAIR_STATUSES)
    fix_complexity = _require_member(
        "fix_complexity", args.fix_complexity, FIX_COMPLEXITIES
    )
    recovery_action = _require_member(
        "recovery_action", args.recovery_action, RECOVERY_ACTIONS
    )
    evidence_bundle_path = _safe_relpath(
        args.evidence_bundle_path, under="artifacts/work"
    ).as_posix()
    repair_result_path = _optional_relpath(
        args.repair_result_path, under="artifacts/work"
    )
    repair_report_path = _optional_relpath(
        args.repair_report_path, under="artifacts/work"
    )
    plan_path = _optional_relpath(args.plan_path)

    if repair_required == "NO":
        if (
            repair_status != "NO_ACTION"
            or fix_complexity != "NOT_APPLICABLE"
            or recovery_action != "NONE"
            or any(
                (
                    repair_result_path,
                    repair_report_path,
                    plan_path,
                    args.new_run_id,
                )
            )
        ):
            raise SystemExit("NO repair requires deterministic no-action typed fields")
    elif (
        repair_status == "NO_ACTION"
        or fix_complexity == "NOT_APPLICABLE"
        or recovery_action == "NONE"
        or not repair_result_path
        or not repair_report_path
    ):
        raise SystemExit("YES repair requires complete repair-result typed fields")

    return {
        "schema": "orchestrator_run_watchdog_result/v1",
        "watchdog_result_path": output_rel.as_posix(),
        "target_run_id": args.target_run_id,
        "watch_status": watch_status,
        "repair_required": repair_required,
        "recommended_recovery": recommended_recovery,
        "repair_status": repair_status,
        "fix_complexity": fix_complexity,
        "recovery_action": recovery_action,
        "evidence_bundle_path": evidence_bundle_path,
        "repair_result_path": repair_result_path,
        "repair_report_path": repair_report_path,
        "plan_path": plan_path,
        "new_run_id": args.new_run_id,
    }


def _legacy_result(args: argparse.Namespace, *, output_rel: Path) -> dict[str, Any]:
    if not args.watch_bundle_path:
        raise SystemExit("--watch-bundle-path is required for YAML compatibility mode")
    watch_rel = _safe_relpath(args.watch_bundle_path, under="state")
    repair_rel = _safe_relpath(args.repair_result_path, under="artifacts/work")
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
    return {
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
        "repair_result_path": repair_rel.as_posix()
        if watch.get("repair_required") == "YES"
        else "",
        "repair_report_path": repair_report_path,
        "plan_path": plan_path,
        "new_run_id": new_run_id,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--watch-bundle-path", default="")
    parser.add_argument("--repair-result-path", required=True)
    parser.add_argument("--target-run-id")
    parser.add_argument("--watch-status")
    parser.add_argument("--repair-required")
    parser.add_argument("--recommended-recovery")
    parser.add_argument("--evidence-bundle-path")
    parser.add_argument("--repair-status")
    parser.add_argument("--fix-complexity")
    parser.add_argument("--recovery-action")
    parser.add_argument("--repair-report-path")
    parser.add_argument("--plan-path")
    parser.add_argument("--new-run-id")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output_rel = _safe_relpath(args.output, under="state")
    typed_mode = any(getattr(args, name) is not None for name in TYPED_ARGUMENTS)
    result = (
        _typed_result(args, output_rel=output_rel)
        if typed_mode
        else _legacy_result(args, output_rel=output_rel)
    )
    _write_json(REPO_ROOT / output_rel, result)
    _write_runtime_bundle(result, semantic_output_rel=output_rel)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
