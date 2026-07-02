#!/usr/bin/env python3
"""Record the outcome selected by blocked implementation recovery classification."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        edge_to_json,
        evaluate_edge,
        normalize_edge,
    )
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from workflows.library.scripts.workflow_recovery_dependencies import (
        WorkRef,
        edge_from_blocked_entry,
        edge_to_json,
        evaluate_edge,
        normalize_edge,
    )


RECOVERY_ROUTES = {
    "GAP_DESIGN_REVISION_REQUIRED",
    "TARGET_DESIGN_REVISION_REQUIRED",
    "PREREQUISITE_GAP_REQUIRED",
    "TERMINAL_BLOCKED",
}

def _read_value_or_path(value: str) -> str:
    path = Path(value)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return value.strip()


def _write_summary(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "history": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_output_bundle(summary_path: str) -> None:
    bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not bundle_path:
        return
    path = Path(bundle_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"summary": summary_path}, indent=2) + "\n", encoding="utf-8")


def _run_adapter_payload(payload: dict[str, Any]) -> int:
    route = str(payload.get("recovery_route") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    terminal_action = str(payload.get("terminal_action") or "continue").strip()
    state_path = str(payload.get("run_state_path") or "").strip()
    item_id = str(payload.get("work_item_id") or "").strip()
    source = str(payload.get("work_item_source") or "").strip()
    summary_path = str(payload.get("summary_path") or "").strip()
    summary_pointer_path = str(payload.get("summary_pointer_path") or "").strip()
    drain_status_path = str(payload.get("drain_status_path") or "").strip()
    if route not in RECOVERY_ROUTES:
        raise SystemExit(f"Unexpected recovery route: {route}")
    if not all((reason, state_path, item_id, source, summary_path, summary_pointer_path, drain_status_path)):
        raise SystemExit("adapter payload missing required blocked recovery fields")
    if terminal_action not in {"block", "continue"}:
        raise SystemExit(f"Unexpected terminal_action: {terminal_action}")

    update_reason = "implementation_blocked" if route == "TERMINAL_BLOCKED" or terminal_action == "block" else reason
    command_args = [
        "python",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "--state-path",
        state_path,
        "blocked",
        "--item-id",
        item_id,
        "--source",
        source,
        "--reason",
        update_reason,
        "--summary-path",
        summary_path,
        "--summary-pointer-path",
        summary_pointer_path,
        "--drain-status-path",
        drain_status_path,
    ]
    optional = {
        "--recovery-route": route,
        "--recovery-reason": reason,
        "--progress-report-path": str(payload.get("progress_report_path") or "").strip(),
        "--implementation-state-path": str(payload.get("implementation_state_path") or "").strip(),
        "--architecture-path": str(payload.get("architecture_bundle_path") or "").strip(),
        "--plan-path": str(payload.get("plan_path") or "").strip(),
    }
    for flag, value in optional.items():
        if value:
            command_args.extend([flag, value])
    result = subprocess.run(command_args).returncode
    if result == 0 and terminal_action == "continue" and route != "TERMINAL_BLOCKED":
        Path(drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    if result == 0:
        _write_output_bundle(summary_path)
    return result


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _append_recovery_review_revise_event(
    *,
    state_path: str,
    item_id: str,
    source: str,
    route: str,
    reason: str,
    revision_report_path: Path | None,
    review_decision: str,
) -> None:
    path = Path(state_path)
    if not path.exists():
        return
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("history", []).append(
        {
            "event": "blocked_recovery_review_revise",
            "item_id": item_id,
            "source": source,
            "recovery_route": route,
            "reason": reason,
            "recovery_status": "TARGET_DESIGN_REVISION_REQUIRED",
            "revision_report_path": revision_report_path.as_posix() if revision_report_path else "",
            "review_decision": review_decision,
            "timestamp_utc": _timestamp(),
        }
    )
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_outputs(
    *,
    state_path: str,
    item_id: str,
    source: str,
    status: str,
    reason: str,
    summary_status: str,
    summary_path: str,
    summary_pointer_path: str,
    drain_status_path: str,
) -> None:
    summary = Path(summary_path)
    _write_summary(
        summary,
        {
            "work_item_id": item_id,
            "work_item_source": source,
            "item_status": summary_status,
            "reason": reason,
            "run_state_path": state_path,
        },
    )
    pointer = Path(summary_pointer_path)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(summary.as_posix() + "\n", encoding="utf-8")
    drain = Path(drain_status_path)
    drain.parent.mkdir(parents=True, exist_ok=True)
    drain.write_text(status + "\n", encoding="utf-8")


def _run_update(
    args: argparse.Namespace,
    command: str,
    reason: str,
    *,
    recovery_status: str = "",
    prerequisite_gap_hint: str = "",
    waiting_on_prerequisite_gap_id: str = "",
    waiting_on_prerequisite_source: str = "",
    prerequisite_recovery_status: str = "",
    prerequisite_recovery_reason: str = "",
    downstream_blocked_gap_id: str = "",
    blocking_failure_code: str = "",
    retry_condition: str = "",
    recovery_dependency_edge: dict[str, Any] | None = None,
) -> int:
    state_reason = "implementation_blocked" if command == "blocked" else reason
    command_args = [
        "python",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "--state-path",
        args.state_path,
        command,
        "--item-id",
        args.item_id,
        "--source",
        args.source,
        "--reason",
        state_reason,
        "--summary-path",
        args.summary_path,
        "--summary-pointer-path",
        args.summary_pointer_path,
        "--drain-status-path",
        args.drain_status_path,
    ]
    if command == "blocked":
        optional = {
            "--recovery-route": args.recovery_route,
            "--recovery-reason": reason,
            "--progress-report-path": args.progress_report_path,
            "--implementation-state-path": args.implementation_state_path,
            "--architecture-path": _architecture_path(args),
            "--plan-path": args.plan_path,
            "--recovery-event-id": args.recovery_event_id,
            "--recovery-status": recovery_status,
            "--prerequisite-gap-hint": prerequisite_gap_hint,
            "--waiting-on-prerequisite-gap-id": waiting_on_prerequisite_gap_id,
            "--waiting-on-prerequisite-source": waiting_on_prerequisite_source,
            "--prerequisite-recovery-status": prerequisite_recovery_status,
            "--prerequisite-recovery-reason": prerequisite_recovery_reason,
            "--downstream-blocked-gap-id": downstream_blocked_gap_id,
            "--blocking-failure-code": blocking_failure_code,
            "--retry-condition": retry_condition,
        }
        for flag, value in optional.items():
            if value:
                command_args.extend([flag, value])
        if recovery_dependency_edge:
            command_args.extend(["--recovery-dependency-edge-json", json.dumps(recovery_dependency_edge, sort_keys=True)])
    return subprocess.run(command_args).returncode


def _record_prerequisite_retry_ready(
    args: argparse.Namespace,
    reason: str,
    edge_json: dict[str, Any],
) -> int:
    edge_json = dict(edge_json)
    edge_json["status"] = "ready_to_retry"
    blocker = edge_json.get("blocker_work") if isinstance(edge_json.get("blocker_work"), dict) else {}

    state_path = Path(args.state_path)
    state = _load_state(state_path)
    blocked_key = "blocked_design_gaps" if args.source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(blocked_key) or {})
    entry = {
        "reason": "implementation_blocked",
        "timestamp_utc": _timestamp(),
        "recovery_route": args.recovery_route,
        "recovery_reason": reason,
        "progress_report_path": args.progress_report_path,
        "implementation_state_path": args.implementation_state_path,
        "architecture_path": _architecture_path(args),
        "plan_path": args.plan_path,
        "recovery_event_id": args.recovery_event_id,
        "recovery_status": "RETRY_READY",
        "waiting_on_prerequisite_gap_id": str(blocker.get("id") or "").strip(),
        "waiting_on_prerequisite_source": str(blocker.get("source") or "").strip(),
        "prerequisite_recovery_status": "COMPLETED",
        "prerequisite_recovery_reason": "prerequisite_completed",
        "original_blocked_gap_id": args.item_id,
        "recovery_dependency_edge": edge_json,
    }
    blocked[args.item_id] = {key: value for key, value in entry.items() if value}
    state[blocked_key] = blocked
    state.setdefault("history", []).append(
        {
            "event": "prerequisite_recovery_satisfied",
            "item_id": args.item_id,
            "source": args.source,
            "reason": "prerequisite_completed",
            "recovery_status": "RETRY_READY",
            "prerequisite_recovery_status": "COMPLETED",
            "waiting_on_prerequisite_gap_id": str(blocker.get("id") or "").strip(),
            "waiting_on_prerequisite_source": str(blocker.get("source") or "").strip(),
            "timestamp_utc": _timestamp(),
        }
    )
    _save_state(state_path, state)

    summary = {
        "record_status": "RETRY_READY",
        "original_blocked_gap_id": args.item_id,
        "selected_prerequisite_id": str(blocker.get("id") or "").strip(),
        "selected_prerequisite_source": str(blocker.get("source") or "").strip(),
        "reason": "prerequisite_completed",
        "run_state_path": args.state_path,
    }
    _write_summary(Path(args.summary_path), summary)
    pointer = Path(args.summary_pointer_path)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(Path(args.summary_path).as_posix() + "\n", encoding="utf-8")
    drain = Path(args.drain_status_path)
    drain.parent.mkdir(parents=True, exist_ok=True)
    drain.write_text("CONTINUE\n", encoding="utf-8")
    _write_output_bundle(args.summary_path)
    return 0


def _clear_retry_block_fields(entry: dict[str, Any]) -> None:
    for key in (
        "retry_block_reason",
        "retry_block_detail",
        "retry_blocked_at_utc",
        "recovered_architecture_validation_path",
    ):
        entry.pop(key, None)


def _record_gap_design_revision_retry_ready(args: argparse.Namespace, reason: str) -> None:
    state_path = Path(args.state_path)
    state = _load_state(state_path)
    blocked_key = "blocked_design_gaps" if args.source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(blocked_key) or {})
    existing = dict(blocked.get(args.item_id) or {})
    existing.update(
        {
            "reason": "implementation_blocked",
            "timestamp_utc": _timestamp(),
            "recovery_route": args.recovery_route,
            "recovery_reason": reason,
            "progress_report_path": args.progress_report_path,
            "implementation_state_path": args.implementation_state_path,
            "architecture_path": _architecture_path(args),
            "plan_path": args.plan_path,
            "recovery_event_id": args.recovery_event_id,
            "recovery_status": "RETRY_READY",
        }
    )
    _clear_retry_block_fields(existing)
    blocked[args.item_id] = {key: value for key, value in existing.items() if value}
    state[blocked_key] = blocked
    _save_state(state_path, state)


def _is_repeated_retry_failure(
    args: argparse.Namespace,
    state: dict[str, Any],
    edge_json: dict[str, Any],
) -> bool:
    blocked_key = "blocked_design_gaps" if args.source == "DESIGN_GAP" else "blocked_items"
    existing = (state.get(blocked_key) or {}).get(args.item_id)
    if not isinstance(existing, dict):
        return False
    if str(existing.get("recovery_status") or "").strip() != "RETRY_READY":
        return False
    blocker = edge_json.get("blocker_work") if isinstance(edge_json.get("blocker_work"), dict) else {}
    if str(existing.get("waiting_on_prerequisite_gap_id") or "").strip() != str(blocker.get("id") or "").strip():
        return False
    if str(existing.get("waiting_on_prerequisite_source") or "").strip() != str(blocker.get("source") or "").strip():
        return False
    existing_event = str(existing.get("recovery_event_id") or "").strip()
    current_event = str(args.recovery_event_id or "").strip()
    if current_event and existing_event and current_event != existing_event:
        return True
    existing_report = str(existing.get("progress_report_path") or "").strip()
    current_report = str(args.progress_report_path or "").strip()
    return bool(current_report and existing_report and current_report != existing_report)


def _record_prerequisite_retry_failed(
    args: argparse.Namespace,
    reason: str,
    edge_json: dict[str, Any],
    recovery_bundle: dict[str, Any],
) -> int:
    edge_json = dict(edge_json)
    edge_json["status"] = "blocked"
    edge_json["reason"] = "retry_failed_after_completed_prerequisite"
    metadata = _compat_metadata_from_edge(edge_json, recovery_bundle)
    result = _run_update(
        args,
        "blocked",
        "prerequisite_retry_failed_after_completion",
        recovery_status="PREREQUISITE_RETRY_FAILED",
        waiting_on_prerequisite_gap_id=metadata.get("waiting_on_prerequisite_gap_id", ""),
        waiting_on_prerequisite_source=metadata.get("waiting_on_prerequisite_source", ""),
        prerequisite_recovery_status="RETRY_FAILED",
        prerequisite_recovery_reason="completed_prerequisite_retry_failed",
        downstream_blocked_gap_id=metadata.get("downstream_blocked_gap_id", ""),
        blocking_failure_code=metadata.get("blocking_failure_code", ""),
        retry_condition=metadata.get("retry_condition", ""),
        recovery_dependency_edge=edge_json,
    )
    if result == 0:
        Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
    return result


def _record_completed_with_follow_up(
    args: argparse.Namespace,
    reason: str,
    edge_json: dict[str, Any],
) -> int:
    state_path = Path(args.state_path)
    state = _load_state(state_path)
    completed_key = "completed_design_gaps" if args.source == "DESIGN_GAP" else "completed_items"
    completed = list(state.get(completed_key) or [])
    if args.item_id not in completed:
        completed.append(args.item_id)
    state[completed_key] = completed

    blocked_key = "blocked_design_gaps" if args.source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(blocked_key) or {})
    blocked.pop(args.item_id, None)
    state[blocked_key] = blocked
    state.setdefault("history", []).append(
        {
            "event": "completed",
            "item_id": args.item_id,
            "source": args.source,
            "timestamp_utc": _timestamp(),
        }
    )
    state.setdefault("history", []).append(
        {
            "event": "follow_up_required",
            "item_id": args.item_id,
            "source": args.source,
            "reason": reason,
            "recovery_dependency_edge": edge_json,
            "timestamp_utc": _timestamp(),
        }
    )
    _save_state(state_path, state)

    _write_summary(
        Path(args.summary_path),
        {
            "work_item_id": args.item_id,
            "work_item_source": args.source,
            "item_status": "COMPLETED",
            "reason": reason,
            "run_state_path": args.state_path,
        },
    )
    pointer = Path(args.summary_pointer_path)
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text(Path(args.summary_path).as_posix() + "\n", encoding="utf-8")
    drain = Path(args.drain_status_path)
    drain.parent.mkdir(parents=True, exist_ok=True)
    drain.write_text("CONTINUE\n", encoding="utf-8")
    _write_output_bundle(args.summary_path)
    return 0


def _architecture_path(args: argparse.Namespace) -> str:
    if args.architecture_path:
        return args.architecture_path
    if not args.architecture_bundle_path:
        return ""
    bundle_path = Path(args.architecture_bundle_path)
    if not bundle_path.exists():
        return ""
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    return str(bundle.get("architecture_path") or "").strip()


def _existing_recovery_status(args: argparse.Namespace, state: dict[str, Any]) -> str:
    blocked_key = "blocked_design_gaps" if args.source == "DESIGN_GAP" else "blocked_items"
    existing = (state.get(blocked_key) or {}).get(args.item_id)
    if not isinstance(existing, dict):
        return ""
    return str(existing.get("recovery_status") or "").strip()


def _raw_edge_from_bundle(bundle: dict[str, Any], args: argparse.Namespace) -> dict[str, Any] | None:
    explicit = bundle.get("recovery_dependency_edge")
    if isinstance(explicit, dict):
        return explicit

    proposed = bundle.get("proposed_prerequisite")
    proposed_id = ""
    proposed_source = "DESIGN_GAP"
    proposed_payload: dict[str, str] = {}
    if isinstance(proposed, dict):
        proposed_id = str(proposed.get("id") or "").strip()
        proposed_source = str(proposed.get("source") or "DESIGN_GAP").strip()
        proposed_payload = {
            "id": proposed_id,
            "source": proposed_source,
            "title": str(proposed.get("title") or "").strip(),
            "scope": str(proposed.get("scope") or "").strip(),
            "reason": str(proposed.get("reason") or "").strip(),
        }
    if not proposed_id:
        proposed_id = str(bundle.get("proposed_prerequisite_id") or "").strip()
        if proposed_id:
            proposed_source = str(bundle.get("proposed_prerequisite_source") or "DESIGN_GAP").strip()
            proposed_payload = {
                "id": proposed_id,
                "source": proposed_source,
                "title": str(bundle.get("proposed_prerequisite_title") or "").strip(),
                "scope": str(bundle.get("proposed_prerequisite_scope") or "").strip(),
                "reason": str(bundle.get("proposed_prerequisite_reason") or "").strip(),
            }
    if proposed_id:
        blocked_id = str(bundle.get("blocked_work_id") or args.item_id or "").strip()
        retry_source = str(bundle.get("retry_target_source") or args.source or "DESIGN_GAP").strip()
        return {
            "blocked_work": {"source": str(bundle.get("blocked_work_source") or args.source or "DESIGN_GAP"), "id": blocked_id},
            "blocker_work": {"source": proposed_source, "id": proposed_id},
            "relation": "requires_completion",
            "reason_code": str(bundle.get("reason") or "prerequisite_gap_required").strip(),
            "ready_when": {"kind": "completed", "source": proposed_source, "id": proposed_id},
            "retry_target": {"source": retry_source, "id": str(bundle.get("retry_target_id") or blocked_id).strip()},
            "downstream_work": bundle.get("downstream_work") if isinstance(bundle.get("downstream_work"), list) else [],
            "evidence": {
                "created_by": "blocked_recovery_classifier",
                "proposed_prerequisite": proposed_payload,
            },
        }

    waiting_id = str(bundle.get("waiting_on_work_id") or "").strip()
    if waiting_id:
        blocked_id = str(bundle.get("blocked_work_id") or args.item_id or "").strip()
        waiting_source = str(bundle.get("waiting_on_work_source") or "DESIGN_GAP").strip()
        retry_target_id = str(bundle.get("retry_target_id") or blocked_id).strip()
        retry_source = str(bundle.get("retry_target_source") or args.source or "DESIGN_GAP").strip()
        return {
            "blocked_work": {"source": str(bundle.get("blocked_work_source") or args.source or "DESIGN_GAP"), "id": blocked_id},
            "blocker_work": {"source": waiting_source, "id": waiting_id},
            "relation": "requires_completion",
            "reason_code": str(bundle.get("reason") or "prerequisite_required").strip(),
            "ready_when": {"kind": "completed", "source": waiting_source, "id": waiting_id},
            "retry_target": {"source": retry_source, "id": retry_target_id},
            "downstream_work": bundle.get("downstream_work") if isinstance(bundle.get("downstream_work"), list) else [],
            "evidence": {"created_by": "blocked_recovery_classifier"},
        }

    blocked_id = str(bundle.get("blocked_work_id") or args.item_id or "").strip()
    blocker_id = str(bundle.get("blocker_work_id") or "").strip()
    relation = str(bundle.get("dependency_relation") or "").strip()
    reason_code = str(bundle.get("dependency_reason_code") or bundle.get("reason") or "").strip()
    retry_target_id = str(bundle.get("retry_target_id") or blocked_id).strip()
    has_generic_edge_fields = any(
        str(bundle.get(key) or "").strip()
        for key in (
            "blocked_work_id",
            "blocked_work_source",
            "blocker_work_id",
            "blocker_work_source",
            "dependency_relation",
            "dependency_reason_code",
            "retry_target_id",
            "retry_target_source",
        )
    )
    if has_generic_edge_fields:
        blocker_source = str(bundle.get("blocker_work_source") or "DESIGN_GAP").strip()
        retry_source = str(bundle.get("retry_target_source") or args.source or "DESIGN_GAP").strip()
        return {
            "blocked_work": {"source": str(bundle.get("blocked_work_source") or args.source or "DESIGN_GAP"), "id": blocked_id},
            "blocker_work": {"source": blocker_source, "id": blocker_id},
            "relation": relation or "requires_completion",
            "reason_code": reason_code,
            "ready_when": {"kind": "completed", "source": blocker_source, "id": blocker_id},
            "retry_target": {"source": retry_source, "id": retry_target_id},
            "downstream_work": bundle.get("downstream_work") if isinstance(bundle.get("downstream_work"), list) else [],
            "evidence": {"created_by": "blocked_recovery_classifier"},
        }
    return None


def _dependency_edge_from_bundle(bundle: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    raw = _raw_edge_from_bundle(bundle, args)
    if raw is not None:
        edge = normalize_edge(raw)
    else:
        edge = edge_from_blocked_entry(WorkRef(source=args.source, id=args.item_id), bundle)
    if edge is None:
        raise SystemExit("PREREQUISITE_GAP_REQUIRED requires recovery_dependency_edge")
    if edge.status in {"invalid_cycle", "missing_evidence"}:
        reason = edge.reason or edge.status
        raise SystemExit(f"Invalid recovery_dependency_edge: {reason}")
    return edge_to_json(edge)


def _compat_metadata_from_edge(edge_json: dict[str, Any], bundle: dict[str, Any]) -> dict[str, str]:
    blocker = edge_json.get("blocker_work") or {}
    retry = edge_json.get("retry_target") or {}
    downstream = edge_json.get("downstream_work") or []
    downstream_ref = downstream[0] if downstream and isinstance(downstream[0], dict) else {}
    evidence = edge_json.get("evidence") if isinstance(edge_json.get("evidence"), dict) else {}
    proposed = evidence.get("proposed_prerequisite") if isinstance(evidence.get("proposed_prerequisite"), dict) else {}
    hint_parts = [
        str(proposed.get("title") or "").strip(),
        str(proposed.get("scope") or "").strip(),
    ]
    prerequisite_gap_hint = str(bundle.get("prerequisite_gap_hint") or " - ".join(part for part in hint_parts if part)).strip()
    return {
        "prerequisite_gap_hint": prerequisite_gap_hint,
        "waiting_on_prerequisite_gap_id": str(blocker.get("id") or "").strip(),
        "waiting_on_prerequisite_source": str(blocker.get("source") or "").strip(),
        "prerequisite_recovery_status": str(bundle.get("prerequisite_recovery_status") or "WAITING_ON_PREREQUISITE").strip(),
        "prerequisite_recovery_reason": str(bundle.get("prerequisite_recovery_reason") or "prerequisite_required").strip(),
        "downstream_blocked_gap_id": str(downstream_ref.get("id") or "").strip(),
        "blocking_failure_code": str(edge_json.get("reason_code") or bundle.get("blocking_failure_code") or "").strip(),
        "retry_condition": str(
            bundle.get("retry_condition")
            or f"{blocker.get('source', '')}:{blocker.get('id', '')} satisfies {retry.get('source', '')}:{retry.get('id', '')}"
        ).strip(),
    }


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-route", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--recovery-bundle-path", default="")
    parser.add_argument("--revision-report", default="")
    parser.add_argument("--review-report-path", default="")
    parser.add_argument("--target-design-review-decision", required=True)
    parser.add_argument("--terminal-action", required=True, choices=["block", "continue"])
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--summary-pointer-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    parser.add_argument("--progress-report-path", default="")
    parser.add_argument("--implementation-state-path", default="")
    parser.add_argument("--architecture-path", default="")
    parser.add_argument("--architecture-bundle-path", default="")
    parser.add_argument("--plan-path", default="")
    parser.add_argument("--recovery-event-id", default="")
    args = parser.parse_args()

    route = args.recovery_route.strip()
    reason = args.reason.strip()
    recovery_bundle: dict[str, Any] = {}
    if args.recovery_bundle_path:
        recovery_bundle = json.loads(Path(args.recovery_bundle_path).read_text(encoding="utf-8"))
        route = str(recovery_bundle.get("blocked_recovery_route") or route).strip()
        reason = str(recovery_bundle.get("reason") or reason).strip()
    if route not in RECOVERY_ROUTES:
        raise SystemExit(f"Unexpected recovery route: {route}")
    if not reason:
        raise SystemExit("Recovery reason is required")
    args.recovery_route = route

    revision_report_path = Path(args.revision_report) if args.revision_report else None
    revision_report_exists = revision_report_path is not None and revision_report_path.exists()
    review_report_path = Path(args.review_report_path) if args.review_report_path else None
    review_report_exists = review_report_path is not None and review_report_path.exists()

    if route == "GAP_DESIGN_REVISION_REQUIRED":
        if revision_report_exists:
            report = json.loads(revision_report_path.read_text(encoding="utf-8"))
            decision = str(report.get("design_revision_decision") or "").strip()
            if decision == "BLOCKED":
                return _run_update(args, "blocked", "gap_design_revision_blocked")
            if decision != "REVISED":
                raise SystemExit(f"Unexpected gap design revision decision: {decision}")
            result = _run_update(args, "gap_design_revision", reason)
            if result == 0 and args.terminal_action == "continue":
                _record_gap_design_revision_retry_ready(args, reason)
                Path(args.drain_status_path).write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")
            return result
        result = _run_update(args, "blocked", reason)
        if result == 0 and args.terminal_action == "continue":
            Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
        return result
    if route == "TARGET_DESIGN_REVISION_REQUIRED":
        if not revision_report_exists:
            result = _run_update(args, "blocked", reason)
            if result == 0 and args.terminal_action == "continue":
                Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
            return result
        decision = _read_value_or_path(args.target_design_review_decision)
        if decision == "APPROVE":
            result = _run_update(args, "design_revision", "implementation_design_revision_required")
            if result == 0 and args.terminal_action == "continue":
                Path(args.drain_status_path).write_text("RUN_RECOVERED_GAP\n", encoding="utf-8")
            return result
        if decision == "REVISE":
            result = _run_update(
                args,
                "blocked",
                "target_design_revision_revise",
                recovery_status="TARGET_DESIGN_REVISION_REQUIRED",
            )
            if result == 0:
                _append_recovery_review_revise_event(
                    state_path=args.state_path,
                    item_id=args.item_id,
                    source=args.source,
                    route=route,
                    reason="target_design_revision_revise",
                    revision_report_path=revision_report_path,
                    review_decision=decision,
                )
                drain_state_root = Path(args.state_path).parent
                feedback_target = drain_state_root / f"blocked-revision-review-feedback.{args.item_id}.md"
                feedback_source_path = review_report_path if review_report_exists else revision_report_path
                feedback_target.write_text(
                    feedback_source_path.read_text(encoding="utf-8"), encoding="utf-8"
                )
                if args.terminal_action == "continue":
                    Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
            return result
        if decision == "BLOCKED":
            return _run_update(args, "blocked", "design_revision_blocked")
        raise SystemExit(f"Unexpected target design review decision: {decision}")
    if route == "PREREQUISITE_GAP_REQUIRED":
        if args.terminal_action == "block":
            return _run_update(args, "blocked", reason, recovery_status="TERMINAL_BLOCKED")
        state = _load_state(Path(args.state_path))
        if _existing_recovery_status(args, state) in {"PREREQUISITE_RETRY_FAILED", "TERMINAL_BLOCKED"}:
            return _run_update(
                args,
                "blocked",
                "prerequisite_retry_failed_requires_non_prerequisite_recovery",
                recovery_status="TERMINAL_BLOCKED",
            )
        dependency_edge = _dependency_edge_from_bundle(recovery_bundle, args)
        if str(recovery_bundle.get("current_work_status") or "").strip() == "COMPLETED":
            return _record_completed_with_follow_up(args, reason, dependency_edge)
        dependency_decision = evaluate_edge(normalize_edge(dependency_edge), state)
        if dependency_decision.route == "INVALID_EDGE":
            raise SystemExit(f"Invalid recovery_dependency_edge: {dependency_decision.reason}")
        if dependency_decision.route == "RETRY_TARGET":
            if _is_repeated_retry_failure(args, state, dependency_edge):
                return _record_prerequisite_retry_failed(args, reason, dependency_edge, recovery_bundle)
            return _record_prerequisite_retry_ready(args, reason, dependency_edge)
        metadata = _compat_metadata_from_edge(dependency_edge, recovery_bundle)
        result = _run_update(
            args,
            "blocked",
            reason,
            recovery_status="PREREQUISITE_WORK_PENDING",
            prerequisite_gap_hint=metadata.get("prerequisite_gap_hint", ""),
            waiting_on_prerequisite_gap_id=metadata.get("waiting_on_prerequisite_gap_id", ""),
            waiting_on_prerequisite_source=metadata.get("waiting_on_prerequisite_source", ""),
            prerequisite_recovery_status=metadata.get("prerequisite_recovery_status", ""),
            prerequisite_recovery_reason=metadata.get("prerequisite_recovery_reason", ""),
            downstream_blocked_gap_id=metadata.get("downstream_blocked_gap_id", ""),
            blocking_failure_code=metadata.get("blocking_failure_code", ""),
            retry_condition=metadata.get("retry_condition", ""),
            recovery_dependency_edge=dependency_edge,
        )
        if result == 0:
            Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
        return result

    if route == "TERMINAL_BLOCKED" or args.terminal_action == "block":
        return _run_update(args, "blocked", "implementation_blocked")

    _write_outputs(
        state_path=args.state_path,
        item_id=args.item_id,
        source=args.source,
        status="CONTINUE",
        reason="implementation_blocked",
        summary_status="BLOCKED_RECOVERY_SKIPPED",
        summary_path=args.summary_path,
        summary_pointer_path=args.summary_pointer_path,
        drain_status_path=args.drain_status_path,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
