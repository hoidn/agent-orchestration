#!/usr/bin/env python3
"""Detect blocked design-gap recovery work before normal drain selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

BOOTSTRAP_GAP_ID = "workflow-lisp-runtime-native-drain-runtime-phase-context-bootstrap-for-imported-stdlib-adapters"
SUMMARY_OWNERSHIP_GAP_ID = (
    "workflow-lisp-runtime-native-drain-work-item-summary-ownership-over-imported-finalize-selected-item"
)
BOOTSTRAP_FAILURE_CODE = "private_exec_context_bootstrap_unsupported"
BOOTSTRAP_WAIT_STATUS = "WAITING_ON_BOOTSTRAP_REACHABILITY"
BOOTSTRAP_WAIT_REASON = "bootstrap_reachability_missing"
BOOTSTRAP_RETRY_CONDITION = (
    "imported stdlib-adapter selector path reaches imported finalizer branches "
    "without private_exec_context_bootstrap_unsupported"
)
BOOTSTRAP_BOUNDARY_DIAGNOSTIC = "prerequisite_boundary_bootstrap_reachability_missing"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_progress_paths(artifact_work_root: Path, design_gap_id: str, entry: dict[str, Any]) -> list[Path]:
    paths = []
    if entry.get("progress_report_path"):
        paths.append(Path(str(entry["progress_report_path"])))
    paths.extend(
        [
            artifact_work_root / "design-gaps" / design_gap_id / "progress_report.md",
            artifact_work_root / design_gap_id / "progress_report.md",
        ]
    )
    return paths


def _find_progress_report(artifact_work_root: Path, design_gap_id: str, entry: dict[str, Any]) -> Path | None:
    for path in _candidate_progress_paths(artifact_work_root, design_gap_id, entry):
        if path.is_file():
            return path
    return None


def _gap_design_paths(architecture_index_root: Path, design_gap_id: str, entry: dict[str, Any]) -> tuple[str, str]:
    architecture_path = str(entry.get("architecture_path") or "").strip()
    plan_path = str(entry.get("plan_path") or "").strip()
    gap_root = architecture_index_root / design_gap_id
    return (
        architecture_path or (gap_root / "implementation_architecture.md").as_posix(),
        plan_path or (gap_root / "execution_plan.md").as_posix(),
    )


def _is_completed_prerequisite(state: dict[str, Any], entry: dict[str, Any]) -> bool:
    prerequisite_id = str(entry.get("waiting_on_prerequisite_gap_id") or "").strip()
    if not prerequisite_id:
        return False
    source = str(entry.get("waiting_on_prerequisite_source") or "DESIGN_GAP").strip()
    if source == "DESIGN_GAP":
        return prerequisite_id in set(state.get("completed_design_gaps") or [])
    if source == "BACKLOG_ITEM":
        return prerequisite_id in set(state.get("completed_items") or [])
    return False


def _has_valid_bootstrap_boundary_metadata(design_gap_id: str, entry: dict[str, Any]) -> bool:
    if design_gap_id != BOOTSTRAP_GAP_ID:
        return True
    metadata = {
        "waiting_on_prerequisite_gap_id": str(entry.get("waiting_on_prerequisite_gap_id") or "").strip(),
        "waiting_on_prerequisite_source": str(entry.get("waiting_on_prerequisite_source") or "").strip(),
        "prerequisite_recovery_status": str(entry.get("prerequisite_recovery_status") or "").strip(),
        "prerequisite_recovery_reason": str(entry.get("prerequisite_recovery_reason") or "").strip(),
        "downstream_blocked_gap_id": str(entry.get("downstream_blocked_gap_id") or "").strip(),
        "blocking_failure_code": str(entry.get("blocking_failure_code") or "").strip(),
        "retry_condition": str(entry.get("retry_condition") or "").strip(),
    }
    return metadata == {
        "waiting_on_prerequisite_gap_id": BOOTSTRAP_GAP_ID,
        "waiting_on_prerequisite_source": "DESIGN_GAP",
        "prerequisite_recovery_status": BOOTSTRAP_WAIT_STATUS,
        "prerequisite_recovery_reason": BOOTSTRAP_WAIT_REASON,
        "downstream_blocked_gap_id": SUMMARY_OWNERSHIP_GAP_ID,
        "blocking_failure_code": BOOTSTRAP_FAILURE_CODE,
        "retry_condition": BOOTSTRAP_RETRY_CONDITION,
    }


def _block_payload(reason: str) -> dict[str, str]:
    return {
        "pre_selection_route": "BLOCKED",
        "design_gap_id": "",
        "recovery_route": "TERMINAL_BLOCKED",
        "recovery_reason": reason,
        "recovery_status": "",
        "progress_report_path": "",
        "architecture_path": "",
        "plan_path": "",
        "architecture_copy_path": "",
        "plan_copy_path": "",
        "blocker_class": "",
        "block_reason": reason,
        "implementation_state_path": "",
        "recovery_event_id": "",
    }


def _requires_user_input(entry: dict[str, Any]) -> bool:
    recovery_reason = str(entry.get("recovery_reason") or "").strip()
    recovery_status = str(entry.get("recovery_status") or "").strip()
    user_input_reason = str(entry.get("user_input_reason") or "").strip()
    prerequisite_reason = str(entry.get("prerequisite_recovery_reason") or "").strip()
    return (
        recovery_status == "USER_INPUT_REQUIRED"
        or recovery_reason == "user_decision_required"
        or bool(user_input_reason)
        or prerequisite_reason == "selected_prerequisite_user_input_required"
    )


def _none_payload(
    recovery_route: str = "NOT_APPLICABLE",
    recovery_reason: str = "not_blocked",
    *,
    pre_selection_route: str = "SELECT_NORMAL_WORK",
    design_gap_id: str = "",
    recovery_event_id: str = "",
    recovery_status: str = "",
) -> dict[str, str]:
    return {
        "pre_selection_route": pre_selection_route,
        "design_gap_id": design_gap_id,
        "recovery_route": recovery_route,
        "recovery_reason": recovery_reason,
        "recovery_status": recovery_status,
        "progress_report_path": "",
        "architecture_path": "",
        "plan_path": "",
        "architecture_copy_path": "",
        "plan_copy_path": "",
        "blocker_class": "",
        "block_reason": "",
        "implementation_state_path": "",
        "recovery_event_id": recovery_event_id,
    }


def _recovery_payload(
    run_state_path: Path,
    artifact_work_root: Path,
    architecture_index_root: Path,
    progress_copy_path: Path,
    architecture_copy_path: Path,
    plan_copy_path: Path,
) -> dict[str, str]:
    state = _load_json(run_state_path)
    blocked = state.get("blocked_design_gaps") or {}
    for design_gap_id in sorted(blocked):
        entry = blocked.get(design_gap_id) or {}
        if entry.get("reason") != "implementation_blocked":
            continue
        recovery_route = str(entry.get("recovery_route") or "").strip()
        recovery_reason = str(entry.get("recovery_reason") or "").strip()
        recovery_event_id = str(entry.get("recovery_event_id") or "").strip()
        if not recovery_route:
            return _block_payload("missing_blocked_recovery_route")
        if not recovery_reason:
            return _block_payload("missing_blocked_recovery_reason")
        if not recovery_event_id:
            return _block_payload("missing_blocked_recovery_event_id")
        recovery_status = str(entry.get("recovery_status") or "").strip()
        if _requires_user_input(entry):
            return _block_payload("user_decision_required")
        if recovery_route == "PREREQUISITE_GAP_REQUIRED" and recovery_status == "PREREQUISITE_BLOCKED":
            recovery_status = "PREREQUISITE_WORK_PENDING"
        if recovery_route == "PREREQUISITE_GAP_REQUIRED" and recovery_status == "PREREQUISITE_WORK_PENDING":
            if _is_completed_prerequisite(state, entry):
                recovery_status = "RETRY_READY"
            elif not _has_valid_bootstrap_boundary_metadata(design_gap_id, entry):
                recovery_reason = BOOTSTRAP_BOUNDARY_DIAGNOSTIC
            else:
                return _none_payload(
                    recovery_route=recovery_route,
                    recovery_reason=recovery_reason,
                    pre_selection_route="SELECT_PREREQUISITE_WORK",
                    design_gap_id=design_gap_id,
                    recovery_event_id=recovery_event_id,
                    recovery_status=recovery_status,
                )
        progress_path = _find_progress_report(artifact_work_root, design_gap_id, entry)
        if progress_path is None:
            return _block_payload("missing_blocked_progress_report")
        progress_copy_path.parent.mkdir(parents=True, exist_ok=True)
        progress_copy_path.write_text(progress_path.read_text(encoding="utf-8"), encoding="utf-8")
        blocker_class = str(entry.get("blocker_class") or "").strip()
        if not blocker_class:
            progress_text = progress_path.read_text(encoding="utf-8")
            blocker_class = "roadmap_conflict" if "roadmap_conflict" in progress_text else "unknown"
        architecture_path, plan_path = _gap_design_paths(architecture_index_root, design_gap_id, entry)
        architecture = Path(architecture_path)
        plan = Path(plan_path)
        if not architecture.is_file():
            return _block_payload("missing_blocked_architecture")
        architecture_copy_path.write_text(architecture.read_text(encoding="utf-8"), encoding="utf-8")
        if plan.is_file():
            plan_copy_path.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "pre_selection_route": "RECOVER_BLOCKED_DESIGN_GAP",
            "design_gap_id": design_gap_id,
            "recovery_route": recovery_route,
            "recovery_reason": recovery_reason,
            "recovery_status": recovery_status,
            "progress_report_path": progress_path.as_posix(),
            "architecture_path": architecture_path,
            "plan_path": plan_path,
            "architecture_copy_path": architecture_copy_path.as_posix(),
            "plan_copy_path": plan_copy_path.as_posix(),
            "blocker_class": blocker_class,
            "block_reason": "implementation_blocked",
            "implementation_state_path": str(entry.get("implementation_state_path") or "").strip(),
            "recovery_event_id": recovery_event_id,
        }
    return _none_payload()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--architecture-index-root", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    progress_copy_path = output.with_name("blocked-progress-report.md")
    architecture_copy_path = output.with_name("blocked-gap-architecture.md")
    plan_copy_path = output.with_name("blocked-gap-execution-plan.md")
    architecture_index_root = Path(args.architecture_index_root or "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps")
    payload = _recovery_payload(
        Path(args.run_state_path),
        Path(args.artifact_work_root),
        architecture_index_root,
        progress_copy_path,
        architecture_copy_path,
        plan_copy_path,
    )
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
