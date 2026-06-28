#!/usr/bin/env python3
"""Detect blocked design-gap recovery work before normal drain selection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

try:
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        evaluate_edge,
        recovery_pointer_to_json,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        evaluate_edge,
        recovery_pointer_to_json,
    )


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
        "blocked_work_id": "",
        "blocked_work_source": "",
        "waiting_on_work_id": "",
        "waiting_on_work_source": "",
        "retry_target_id": "",
        "retry_target_source": "",
        "recovery_pointer_status": "",
    }


def _step_back_payload(decision: dict[str, Any]) -> dict[str, str]:
    payload = _block_payload("workflow_non_progress")
    payload.update(
        {
            "recovery_status": "STEP_BACK_REQUIRED",
            "blocker_class": "workflow_non_progress",
            "block_reason": str(decision.get("failure_fingerprint") or "workflow_non_progress").strip(),
            "recovery_event_id": str(decision.get("failure_fingerprint") or "workflow_non_progress").strip(),
        }
    )
    return payload


def _non_progress_payload(path: Path | None) -> dict[str, str] | None:
    if path is None or not path.exists():
        return None
    decision = _load_json(path)
    if str(decision.get("route") or "").strip() == "STEP_BACK_REQUIRED":
        return _step_back_payload(decision)
    return None


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
        "blocked_work_id": "",
        "blocked_work_source": "",
        "waiting_on_work_id": "",
        "waiting_on_work_source": "",
        "retry_target_id": "",
        "retry_target_source": "",
        "recovery_pointer_status": "",
    }


def _pointer_fields(decision: Any | None) -> dict[str, str]:
    if decision is None:
        return {
            "blocked_work_id": "",
            "blocked_work_source": "",
            "waiting_on_work_id": "",
            "waiting_on_work_source": "",
            "retry_target_id": "",
            "retry_target_source": "",
            "recovery_pointer_status": "",
        }
    return recovery_pointer_to_json(decision)


def _recovery_payload(
    run_state_path: Path,
    artifact_work_root: Path,
    architecture_index_root: Path,
    progress_copy_path: Path,
    architecture_copy_path: Path,
    plan_copy_path: Path,
    non_progress_decision_path: Path | None = None,
) -> dict[str, str]:
    non_progress = _non_progress_payload(non_progress_decision_path)
    if non_progress is not None:
        return non_progress

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
            edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=design_gap_id), entry)
            if edge is None:
                return _block_payload("missing_prerequisite_dependency_edge")
            decision = evaluate_edge(edge, state)
            if decision.route == "INVALID_EDGE":
                return _block_payload(decision.reason or "invalid_prerequisite_dependency_edge")
            if decision.route == "RETRY_TARGET":
                recovery_status = "RETRY_READY"
            elif decision.route in {"SELECT_BLOCKER", "BLOCKED_RECOVERABLE"}:
                payload = _none_payload(
                    recovery_route=recovery_route,
                    recovery_reason=recovery_reason,
                    pre_selection_route="SELECT_PREREQUISITE_WORK",
                    design_gap_id=design_gap_id,
                    recovery_event_id=recovery_event_id,
                    recovery_status=recovery_status,
                )
                payload.update(_pointer_fields(decision))
                return payload
            elif decision.route == "BLOCKED_TERMINAL":
                return _block_payload("prerequisite_blocker_terminal")
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
        payload = {
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
        edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=design_gap_id), entry)
        payload.update(_pointer_fields(evaluate_edge(edge, state) if edge is not None else None))
        return payload
    return _none_payload()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--architecture-index-root", default="")
    parser.add_argument("--non-progress-decision-path", default="")
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
        Path(args.non_progress_decision_path) if args.non_progress_decision_path else None,
    )
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
