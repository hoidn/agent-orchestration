#!/usr/bin/env python3
"""Detect blocked design-gap recovery work before normal drain selection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

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


def _write_recovered_validation_progress_report(
    progress_copy_path: Path,
    *,
    design_gap_id: str,
    entry: Mapping[str, Any],
) -> bool:
    retry_reason = str(entry.get("retry_block_reason") or "").strip()
    if retry_reason not in {"recovered_architecture_invalid", "recovered_architecture_blocked"}:
        return False
    validation_path = str(entry.get("recovered_architecture_validation_path") or "").strip()
    detail = str(entry.get("retry_block_detail") or "").strip()
    lines = [
        "Status: BLOCKED",
        "",
        "Recovered blocked-gap retry did not run because the recovered architecture bundle failed validation.",
        "",
        f"Design gap: `{design_gap_id}`",
        f"Recovery validation reason: `{retry_reason}`",
    ]
    if validation_path:
        lines.append(f"Validation bundle: `{validation_path}`")
    if detail:
        lines.extend(["", "Validation detail:", detail])
    lines.extend(
        [
            "",
            "The next recovery decision should revise the gap architecture or plan to satisfy this validation failure.",
            "Do not classify stale implementation-progress evidence as the current blocker for this retry.",
        ]
    )
    progress_copy_path.parent.mkdir(parents=True, exist_ok=True)
    progress_copy_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return True


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


def _last_step_back_event(history: list[Any]) -> tuple[dict[str, Any] | None, bool]:
    """Return the most recent step_back history entry and whether a later non-step_back entry follows it."""
    last_step_back: dict[str, Any] | None = None
    followed_by_other_event = False
    for entry in history:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("event") or "").strip() == "step_back":
            last_step_back = entry
            followed_by_other_event = False
        elif last_step_back is not None:
            followed_by_other_event = True
    return last_step_back, followed_by_other_event


def _step_back_already_handled(state: Mapping[str, Any], decision: Mapping[str, Any]) -> bool:
    history = state.get("history")
    if not isinstance(history, list):
        return False
    last_step_back, followed_by_other_event = _last_step_back_event(history)
    if last_step_back is None or followed_by_other_event:
        return False
    if str(last_step_back.get("action") or "").strip() != "CONTINUE_WITH_CURRENT_PLAN":
        return False
    last_fingerprint = str(last_step_back.get("failure_fingerprint") or "").strip()
    current_fingerprint = str(decision.get("failure_fingerprint") or "").strip()
    return bool(last_fingerprint) and last_fingerprint == current_fingerprint


def _non_progress_payload(path: Path | None, state: Mapping[str, Any]) -> dict[str, str] | None:
    if path is None or not path.exists():
        return None
    decision = _load_json(path)
    if str(decision.get("route") or "").strip() != "STEP_BACK_REQUIRED":
        return None
    if _step_back_already_handled(state, decision):
        return None
    return _step_back_payload(decision)


def _selector_manifest_mechanics_payload(path: Path | None) -> dict[str, str] | None:
    if path is None or not path.exists():
        return None
    manifest = _load_json(path)
    errors = manifest.get("blocking_mechanics_errors") or []
    if not isinstance(errors, list) or not errors:
        return None
    first = errors[0] if isinstance(errors[0], dict) else {}
    reason = str(first.get("code") or first.get("reason") or "recovery_dependency_mechanics_error").strip()
    return _block_payload(reason or "recovery_dependency_mechanics_error")


def _selector_manifest_payload(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    return _load_json(path)


def _selector_manifest_has_selectable_work(manifest: Mapping[str, Any]) -> bool:
    for key in ("items", "design_gaps", "eligible_items", "eligible_design_gaps", "priority_recovery_work"):
        value = manifest.get(key)
        if isinstance(value, list) and value:
            return True
    return False


def _selector_manifest_requests_done_review(manifest: Mapping[str, Any]) -> bool:
    if not manifest:
        return False
    if manifest.get("blocking_mechanics_errors"):
        return False
    if manifest.get("diagnostic_mechanics_errors") and manifest.get("target_gap_discovery_allowed", True):
        return False
    return not _selector_manifest_has_selectable_work(manifest)


def _manifest_ref_set(rows: Any) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if not isinstance(rows, list):
        return refs
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        item_id = str(row.get("id") or "").strip()
        if not source and row.get("design_gap_id"):
            source = "DESIGN_GAP"
            item_id = str(row.get("design_gap_id") or "").strip()
        if not source and row.get("item_id"):
            source = "BACKLOG_ITEM"
            item_id = str(row.get("item_id") or "").strip()
        if source and item_id:
            refs.add((source, item_id))
    return refs


def _manifest_ref_is_selectable(manifest: Mapping[str, Any], ref: WorkRef | None) -> bool:
    if ref is None:
        return False
    selectable = set()
    for key in ("eligible_design_gaps", "eligible_items", "priority_recovery_work"):
        selectable.update(_manifest_ref_set(manifest.get(key)))
    return (ref.source, ref.id) in selectable


def _manifest_has_diagnostic_only_errors(manifest: Mapping[str, Any]) -> bool:
    return bool(manifest.get("diagnostic_mechanics_errors")) and not bool(manifest.get("blocking_mechanics_errors"))


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


def _proposed_prerequisite_fields(entry: Mapping[str, Any], edge: Any | None) -> dict[str, str]:
    evidence = getattr(edge, "evidence", {}) if edge is not None else {}
    proposed = evidence.get("proposed_prerequisite") if isinstance(evidence, Mapping) else None
    if not isinstance(proposed, Mapping):
        proposed = {}
    return {
        "prerequisite_gap_hint": str(entry.get("prerequisite_gap_hint") or "").strip(),
        "proposed_prerequisite_id": str(proposed.get("id") or "").strip(),
        "proposed_prerequisite_source": str(proposed.get("source") or "").strip(),
        "proposed_prerequisite_title": str(proposed.get("title") or "").strip(),
        "proposed_prerequisite_scope": str(proposed.get("scope") or "").strip(),
        "proposed_prerequisite_reason": str(proposed.get("reason") or "").strip(),
    }


def _has_active_prerequisite_pointer(recovery_route: str, recovery_status: str) -> bool:
    return recovery_route == "PREREQUISITE_GAP_REQUIRED" and recovery_status in {
        "PREREQUISITE_WORK_PENDING",
        "PREREQUISITE_BLOCKED",
        "RETRY_READY",
    }


def _blocked_recovery_order(blocked: dict[str, Any]) -> list[str]:
    ids = sorted(str(item) for item in blocked)
    dependents_by_blocker: dict[str, set[str]] = {item: set() for item in ids}
    for design_gap_id in ids:
        entry = blocked.get(design_gap_id) or {}
        if not isinstance(entry, dict):
            continue
        edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=design_gap_id), entry)
        blocker = edge.blocker_work if edge is not None else None
        if blocker is not None and blocker.source == "DESIGN_GAP" and blocker.id in dependents_by_blocker:
            dependents_by_blocker[blocker.id].add(design_gap_id)

    def dependent_depth(design_gap_id: str, seen: set[str] | None = None) -> int:
        seen = set(seen or ())
        if design_gap_id in seen:
            return 0
        seen.add(design_gap_id)
        return max(
            (1 + dependent_depth(dependent, seen) for dependent in dependents_by_blocker.get(design_gap_id, ())),
            default=0,
        )

    return sorted(ids, key=lambda item: (-dependent_depth(item), item))


def _recovery_payload(
    run_state_path: Path,
    artifact_work_root: Path,
    architecture_index_root: Path,
    progress_copy_path: Path,
    architecture_copy_path: Path,
    plan_copy_path: Path,
    non_progress_decision_path: Path | None = None,
    selector_manifest_path: Path | None = None,
) -> dict[str, str]:
    state = _load_json(run_state_path)
    selector_mechanics = _selector_manifest_mechanics_payload(selector_manifest_path)
    if selector_mechanics is not None:
        return selector_mechanics
    selector_manifest = _selector_manifest_payload(selector_manifest_path)

    blocked = state.get("blocked_design_gaps") or {}
    for design_gap_id in _blocked_recovery_order(blocked):
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
                if _manifest_has_diagnostic_only_errors(selector_manifest) and not _manifest_ref_is_selectable(
                    selector_manifest, decision.target
                ):
                    continue
                payload = _none_payload(
                    recovery_route=recovery_route,
                    recovery_reason=recovery_reason,
                    pre_selection_route="SELECT_PREREQUISITE_WORK",
                    design_gap_id=design_gap_id,
                    recovery_event_id=recovery_event_id,
                    recovery_status=recovery_status,
                )
                payload.update(_pointer_fields(decision))
                payload.update(_proposed_prerequisite_fields(entry, edge))
                return payload
            elif decision.route == "BLOCKED_TERMINAL":
                return _block_payload("prerequisite_blocker_terminal")
        wrote_recovered_validation_report = _write_recovered_validation_progress_report(
            progress_copy_path,
            design_gap_id=design_gap_id,
            entry=entry,
        )
        progress_path = _find_progress_report(artifact_work_root, design_gap_id, entry)
        if not wrote_recovered_validation_report:
            if progress_path is None:
                return _block_payload("missing_blocked_progress_report")
            progress_copy_path.parent.mkdir(parents=True, exist_ok=True)
            progress_copy_path.write_text(progress_path.read_text(encoding="utf-8"), encoding="utf-8")
        blocker_class = str(entry.get("blocker_class") or "").strip()
        if not blocker_class:
            if wrote_recovered_validation_report:
                blocker_class = "recovery_validation"
            else:
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
            "progress_report_path": (
                progress_copy_path.as_posix()
                if wrote_recovered_validation_report
                else progress_path.as_posix()
            ),
            "architecture_path": architecture_path,
            "plan_path": plan_path,
            "architecture_copy_path": architecture_copy_path.as_posix(),
            "plan_copy_path": plan_copy_path.as_posix(),
            "blocker_class": blocker_class,
            "block_reason": "implementation_blocked",
            "implementation_state_path": str(entry.get("implementation_state_path") or "").strip(),
            "recovery_event_id": recovery_event_id,
        }
        feedback_path = run_state_path.parent / f"blocked-revision-review-feedback.{design_gap_id}.md"
        if feedback_path.is_file():
            payload["prior_revision_review_feedback_path"] = feedback_path.as_posix()
        edge = edge_from_blocked_entry(WorkRef(source="DESIGN_GAP", id=design_gap_id), entry)
        decision = (
            evaluate_edge(edge, state)
            if edge is not None and _has_active_prerequisite_pointer(recovery_route, recovery_status)
            else None
        )
        payload.update(_pointer_fields(decision))
        return payload
    non_progress = _non_progress_payload(non_progress_decision_path, state)
    if non_progress is not None:
        return non_progress
    if _selector_manifest_requests_done_review(selector_manifest):
        return _none_payload(
            recovery_reason="no_selectable_manifest_work",
            pre_selection_route="SELECT_DONE_REVIEW",
            recovery_status="DONE_REVIEW_REQUIRED",
        )
    return _none_payload()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--architecture-index-root", default="")
    parser.add_argument("--non-progress-decision-path", default="")
    parser.add_argument("--selector-manifest-path", default="")
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
        Path(args.selector_manifest_path) if args.selector_manifest_path else None,
    )
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
