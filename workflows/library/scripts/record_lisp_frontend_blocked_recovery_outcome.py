#!/usr/bin/env python3
"""Record the outcome selected by blocked implementation recovery classification."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


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
        }
        for flag, value in optional.items():
            if value:
                command_args.extend([flag, value])
    return subprocess.run(command_args).returncode


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


def _stored_prerequisite_retry_ready(args: argparse.Namespace) -> bool:
    state_path = Path(args.state_path)
    if not state_path.exists():
        return False
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = (state.get("blocked_design_gaps") or {}).get(args.item_id) or {}
    return (
        str(entry.get("recovery_route") or "").strip() == "PREREQUISITE_GAP_REQUIRED"
        and str(entry.get("recovery_status") or "").strip() == "RETRY_READY"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-route", default="")
    parser.add_argument("--reason", default="")
    parser.add_argument("--recovery-bundle-path", default="")
    parser.add_argument("--revision-report", default="")
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
    if args.recovery_bundle_path:
        bundle = json.loads(Path(args.recovery_bundle_path).read_text(encoding="utf-8"))
        route = str(bundle.get("blocked_recovery_route") or route).strip()
        reason = str(bundle.get("reason") or reason).strip()
    if route not in RECOVERY_ROUTES:
        raise SystemExit(f"Unexpected recovery route: {route}")
    if not reason:
        raise SystemExit("Recovery reason is required")
    args.recovery_route = route

    if _stored_prerequisite_retry_ready(args):
        _write_outputs(
            state_path=args.state_path,
            item_id=args.item_id,
            source=args.source,
            status="RUN_RECOVERED_GAP",
            reason="prerequisite_retry_ready",
            summary_status="PREREQUISITE_RETRY_READY",
            summary_path=args.summary_path,
            summary_pointer_path=args.summary_pointer_path,
            drain_status_path=args.drain_status_path,
        )
        return 0

    revision_report_path = Path(args.revision_report) if args.revision_report else None
    revision_report_exists = revision_report_path is not None and revision_report_path.exists()

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
        if decision in {"REVISE", "BLOCKED"}:
            return _run_update(args, "blocked", "design_revision_exhausted")
        raise SystemExit(f"Unexpected target design review decision: {decision}")
    if route == "PREREQUISITE_GAP_REQUIRED":
        if args.terminal_action == "block":
            return _run_update(args, "blocked", reason, recovery_status="TERMINAL_BLOCKED")
        if revision_report_exists:
            report = json.loads(revision_report_path.read_text(encoding="utf-8"))
            revision_decision = str(report.get("design_revision_decision") or "").strip()
            if revision_decision == "BLOCKED":
                return _run_update(args, "blocked", "prerequisite_target_design_revision_blocked")
            if revision_decision != "REVISED":
                raise SystemExit(f"Unexpected prerequisite target design revision decision: {revision_decision}")
            decision = _read_value_or_path(args.target_design_review_decision)
            if decision == "APPROVE":
                result = _run_update(
                    args,
                    "blocked",
                    reason,
                    recovery_status="PREREQUISITE_WORK_PENDING",
                    prerequisite_gap_hint=str(report.get("summary") or "").strip(),
                )
                if result == 0:
                    Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
                return result
            if decision in {"REVISE", "BLOCKED"}:
                return _run_update(
                    args,
                    "blocked",
                    "prerequisite_target_design_revision_exhausted",
                    recovery_status="TARGET_DESIGN_REVISION_REQUIRED",
                )
            raise SystemExit(f"Unexpected prerequisite target design review decision: {decision}")
        result = _run_update(args, "blocked", reason, recovery_status="TARGET_DESIGN_REVISION_REQUIRED")
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
