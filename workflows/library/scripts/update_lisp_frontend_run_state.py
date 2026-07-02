#!/usr/bin/env python3
"""Maintain durable run state for the Lisp frontend autonomous drain."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema": "lisp_frontend_autonomous_drain_run_state/v1",
            "completed_items": [],
            "completed_design_gaps": [],
            "blocked_items": {},
            "blocked_design_gaps": {},
            "blocked_run": None,
            "history": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def _save(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _write_output_bundle(summary_path: str) -> None:
    bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not bundle_path:
        return
    path = Path(bundle_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"summary": summary_path}, indent=2) + "\n", encoding="utf-8")


def _clear_run_blocked(state: dict[str, Any]) -> None:
    if state.get("blocked_run") is not None:
        state["blocked_run"] = None


def _run_adapter_payload(payload: dict[str, Any]) -> int:
    state_path = str(payload.get("run_state_path") or "").strip()
    item_id = str(payload.get("work_item_id") or "").strip()
    source = str(payload.get("work_item_source") or "").strip()
    reason = str(payload.get("reason") or "").strip()
    summary_path = str(payload.get("item_summary_target_path") or "").strip()
    summary_pointer_path = str(payload.get("item_summary_pointer_path") or "").strip()
    drain_status_path = str(payload.get("drain_status_path") or "").strip()
    if not all((state_path, item_id, source, reason, summary_path)):
        raise SystemExit("adapter payload requires run_state_path, work_item_id, work_item_source, reason, and item_summary_target_path")
    if source not in {"BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"}:
        raise SystemExit(f"Unexpected work_item_source: {source}")

    path = Path(state_path)
    state = _load(path)
    if reason == "complete":
        _record_completed(state, item_id=item_id, source=source)
        summary_status = "COMPLETED"
        drain_status = "CONTINUE"
    else:
        _record_blocked(state, item_id=item_id, source=source, reason=reason)
        summary_status = "BLOCKED"
        drain_status = "BLOCKED"

    summary = Path(summary_path)
    summary.parent.mkdir(parents=True, exist_ok=True)
    summary.write_text(
        json.dumps(
            {
                "work_item_id": item_id,
                "work_item_source": source,
                "item_status": summary_status,
                "reason": "" if reason == "complete" else reason,
                "run_state_path": path.as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    if summary_pointer_path:
        pointer = Path(summary_pointer_path)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        pointer.write_text(summary.as_posix() + "\n", encoding="utf-8")
    if drain_status_path:
        drain = Path(drain_status_path)
        drain.parent.mkdir(parents=True, exist_ok=True)
        drain.write_text(drain_status + "\n", encoding="utf-8")
    _save(path, state)
    _write_output_bundle(summary.as_posix())
    return 0


def _record_completed(state: dict[str, Any], *, item_id: str, source: str) -> None:
    _clear_run_blocked(state)
    key = "completed_design_gaps" if source == "DESIGN_GAP" else "completed_items"
    values = list(state.get(key, []))
    if item_id not in values:
        values.append(item_id)
    state[key] = values
    blocked_key = "blocked_design_gaps" if source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(blocked_key, {}))
    blocked.pop(item_id, None)
    state[blocked_key] = blocked
    state.setdefault("history", []).append(
        {"event": "completed", "item_id": item_id, "source": source, "timestamp_utc": _timestamp()}
    )


def _record_blocked(
    state: dict[str, Any],
    *,
    item_id: str,
    source: str,
    reason: str,
    recovery_route: str = "",
    recovery_reason: str = "",
    progress_report_path: str = "",
    implementation_state_path: str = "",
    architecture_path: str = "",
    plan_path: str = "",
    recovery_event_id: str = "",
    recovery_status: str = "",
    prerequisite_gap_hint: str = "",
    prerequisite_selection_bundle_path: str = "",
    waiting_on_prerequisite_gap_id: str = "",
    waiting_on_prerequisite_source: str = "",
    prerequisite_recovery_status: str = "",
    prerequisite_recovery_reason: str = "",
    original_blocked_gap_id: str = "",
    downstream_blocked_gap_id: str = "",
    blocking_failure_code: str = "",
    retry_condition: str = "",
    recovery_dependency_edge: dict[str, Any] | None = None,
) -> None:
    _clear_run_blocked(state)
    key = "blocked_design_gaps" if source == "DESIGN_GAP" else "blocked_items"
    blocked = dict(state.get(key, {}))
    entry = {"reason": reason, "timestamp_utc": _timestamp()}
    optional_fields = {
        "recovery_route": recovery_route,
        "recovery_reason": recovery_reason,
        "progress_report_path": progress_report_path,
        "implementation_state_path": implementation_state_path,
        "architecture_path": architecture_path,
        "plan_path": plan_path,
        "recovery_event_id": recovery_event_id,
        "recovery_status": recovery_status,
        "prerequisite_gap_hint": prerequisite_gap_hint,
        "prerequisite_selection_bundle_path": prerequisite_selection_bundle_path,
        "waiting_on_prerequisite_gap_id": waiting_on_prerequisite_gap_id,
        "waiting_on_prerequisite_source": waiting_on_prerequisite_source,
        "prerequisite_recovery_status": prerequisite_recovery_status,
        "prerequisite_recovery_reason": prerequisite_recovery_reason,
        "original_blocked_gap_id": original_blocked_gap_id,
        "downstream_blocked_gap_id": downstream_blocked_gap_id,
        "blocking_failure_code": blocking_failure_code,
        "retry_condition": retry_condition,
    }
    entry.update({key: value for key, value in optional_fields.items() if value})
    if recovery_dependency_edge:
        entry["recovery_dependency_edge"] = recovery_dependency_edge
    blocked[item_id] = entry
    state[key] = blocked
    history_entry = {
        "event": "blocked",
        "item_id": item_id,
        "source": source,
        "reason": reason,
        "timestamp_utc": _timestamp(),
    }
    history_entry.update({key: value for key, value in optional_fields.items() if value})
    if recovery_dependency_edge:
        history_entry["recovery_dependency_edge"] = recovery_dependency_edge
    state.setdefault("history", []).append(history_entry)


def _record_run_blocked(
    state: dict[str, Any],
    *,
    reason: str,
    selection_path: str = "",
) -> None:
    selection: dict[str, Any] = {}
    if selection_path:
        selection = json.loads(Path(selection_path).read_text(encoding="utf-8"))
    if "pre_selection_route" in selection:
        if selection.get("pre_selection_route") != "RECOVER_BLOCKED_DESIGN_GAP":
            state["blocked_run"] = {
                "reason": str(
                    selection.get("block_reason") or selection.get("recovery_reason") or "workflow_run_blocked"
                ).strip(),
                "timestamp_utc": _timestamp(),
            }
        return
    timestamp = _timestamp()
    entry = {
        "reason": reason,
        "timestamp_utc": timestamp,
    }
    selection_rationale = str(selection.get("selection_rationale") or "").strip()
    blocking_reasons = selection.get("blocking_reasons")
    if selection_path:
        entry["selection_path"] = selection_path
    if selection_rationale:
        entry["selection_rationale"] = selection_rationale
    if isinstance(blocking_reasons, list):
        entry["blocking_reasons"] = blocking_reasons
    state["blocked_run"] = entry
    state.setdefault("history", []).append({"event": "run_blocked", **entry})


def _record_design_revision(state: dict[str, Any], *, item_id: str, source: str, reason: str) -> None:
    _clear_run_blocked(state)
    state.setdefault("history", []).append(
        {
            "event": "design_revision",
            "item_id": item_id,
            "source": source,
            "reason": reason,
            "timestamp_utc": _timestamp(),
        }
    )


def _record_gap_design_revision(state: dict[str, Any], *, item_id: str, source: str, reason: str) -> None:
    _clear_run_blocked(state)
    state.setdefault("history", []).append(
        {
            "event": "gap_design_revision",
            "item_id": item_id,
            "source": source,
            "reason": reason,
            "timestamp_utc": _timestamp(),
        }
    )


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--state-path", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--run-id", required=True)
    complete = sub.add_parser("complete")
    complete.add_argument("--item-id", required=True)
    complete.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    complete.add_argument("--summary-path")
    complete.add_argument("--summary-pointer-path")
    complete.add_argument("--drain-status-path")
    blocked = sub.add_parser("blocked")
    blocked.add_argument("--item-id")
    blocked.add_argument("--selection-path")
    blocked.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    blocked.add_argument("--reason", required=True)
    blocked.add_argument("--summary-path")
    blocked.add_argument("--summary-pointer-path")
    blocked.add_argument("--drain-status-path")
    blocked.add_argument("--recovery-route", default="")
    blocked.add_argument("--recovery-reason", default="")
    blocked.add_argument("--progress-report-path", default="")
    blocked.add_argument("--implementation-state-path", default="")
    blocked.add_argument("--architecture-path", default="")
    blocked.add_argument("--plan-path", default="")
    blocked.add_argument("--recovery-event-id", default="")
    blocked.add_argument("--recovery-status", default="")
    blocked.add_argument("--prerequisite-gap-hint", default="")
    blocked.add_argument("--prerequisite-selection-bundle-path", default="")
    blocked.add_argument("--waiting-on-prerequisite-gap-id", default="")
    blocked.add_argument("--waiting-on-prerequisite-source", default="")
    blocked.add_argument("--prerequisite-recovery-status", default="")
    blocked.add_argument("--prerequisite-recovery-reason", default="")
    blocked.add_argument("--original-blocked-gap-id", default="")
    blocked.add_argument("--downstream-blocked-gap-id", default="")
    blocked.add_argument("--blocking-failure-code", default="")
    blocked.add_argument("--retry-condition", default="")
    blocked.add_argument("--recovery-dependency-edge-json", default="")
    run_blocked = sub.add_parser("run_blocked")
    run_blocked.add_argument("--reason", required=True)
    run_blocked.add_argument("--selection-path", default="")
    run_blocked.add_argument("--drain-status-path")
    design_revision = sub.add_parser("design_revision")
    design_revision.add_argument("--item-id", required=True)
    design_revision.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    design_revision.add_argument("--reason", required=True)
    design_revision.add_argument("--summary-path")
    design_revision.add_argument("--summary-pointer-path")
    design_revision.add_argument("--drain-status-path")
    gap_design_revision = sub.add_parser("gap_design_revision")
    gap_design_revision.add_argument("--item-id", required=True)
    gap_design_revision.add_argument(
        "--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"]
    )
    gap_design_revision.add_argument("--reason", required=True)
    gap_design_revision.add_argument("--summary-path")
    gap_design_revision.add_argument("--summary-pointer-path")
    gap_design_revision.add_argument("--drain-status-path")
    args = parser.parse_args()

    path = Path(args.state_path)
    state = _load(path)
    if args.command == "init":
        state["run_id"] = args.run_id
        state.setdefault("started_at_utc", _timestamp())
        state.setdefault("history", []).append({"event": "init", "run_id": args.run_id, "timestamp_utc": _timestamp()})
    elif args.command == "complete":
        _record_completed(state, item_id=args.item_id, source=args.source)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": args.item_id,
                        "work_item_source": args.source,
                        "item_status": "COMPLETED",
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
            _write_output_bundle(summary_path.as_posix())
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("CONTINUE\n", encoding="utf-8")
    elif args.command == "blocked":
        item_id = args.item_id
        if not item_id and args.selection_path:
            selection = json.loads(Path(args.selection_path).read_text(encoding="utf-8"))
            if args.source == "DESIGN_GAP":
                item_id = str(selection.get("design_gap_id") or "").strip()
            else:
                item_id = str(selection.get("selected_item_id") or "").strip()
        if not item_id:
            raise SystemExit("blocked requires --item-id or --selection-path with an item id")
        _record_blocked(
            state,
            item_id=item_id,
            source=args.source,
            reason=args.reason,
            recovery_route=args.recovery_route,
            recovery_reason=args.recovery_reason,
            progress_report_path=args.progress_report_path,
            implementation_state_path=args.implementation_state_path,
            architecture_path=args.architecture_path,
            plan_path=args.plan_path,
            recovery_event_id=args.recovery_event_id,
            recovery_status=args.recovery_status,
            prerequisite_gap_hint=args.prerequisite_gap_hint,
            prerequisite_selection_bundle_path=args.prerequisite_selection_bundle_path,
            waiting_on_prerequisite_gap_id=args.waiting_on_prerequisite_gap_id,
            waiting_on_prerequisite_source=args.waiting_on_prerequisite_source,
            prerequisite_recovery_status=args.prerequisite_recovery_status,
            prerequisite_recovery_reason=args.prerequisite_recovery_reason,
            original_blocked_gap_id=args.original_blocked_gap_id,
            downstream_blocked_gap_id=args.downstream_blocked_gap_id,
            blocking_failure_code=args.blocking_failure_code,
            retry_condition=args.retry_condition,
            recovery_dependency_edge=(
                json.loads(args.recovery_dependency_edge_json) if args.recovery_dependency_edge_json else None
            ),
        )
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": item_id,
                        "work_item_source": args.source,
                        "item_status": "BLOCKED",
                        "reason": args.reason,
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("BLOCKED\n", encoding="utf-8")
    elif args.command == "run_blocked":
        _record_run_blocked(state, reason=args.reason, selection_path=args.selection_path)
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("BLOCKED\n", encoding="utf-8")
    elif args.command == "design_revision":
        _record_design_revision(state, item_id=args.item_id, source=args.source, reason=args.reason)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": args.item_id,
                        "work_item_source": args.source,
                        "item_status": "DESIGN_REVISED",
                        "reason": args.reason,
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("CONTINUE\n", encoding="utf-8")
    elif args.command == "gap_design_revision":
        _record_gap_design_revision(state, item_id=args.item_id, source=args.source, reason=args.reason)
        if args.summary_path:
            summary_path = Path(args.summary_path)
            summary_path.parent.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(
                json.dumps(
                    {
                        "work_item_id": args.item_id,
                        "work_item_source": args.source,
                        "item_status": "GAP_DESIGN_REVISED",
                        "reason": args.reason,
                        "run_state_path": path.as_posix(),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            if args.summary_pointer_path:
                pointer_path = Path(args.summary_pointer_path)
                pointer_path.parent.mkdir(parents=True, exist_ok=True)
                pointer_path.write_text(summary_path.as_posix() + "\n", encoding="utf-8")
        if args.drain_status_path:
            status_path = Path(args.drain_status_path)
            status_path.parent.mkdir(parents=True, exist_ok=True)
            status_path.write_text("CONTINUE\n", encoding="utf-8")
    _save(path, state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
