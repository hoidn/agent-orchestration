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


RECOVERY_ROUTES = {
    "GAP_DESIGN_REVISION_REQUIRED",
    "TARGET_DESIGN_REVISION_REQUIRED",
    "PREREQUISITE_GAP_REQUIRED",
    "TERMINAL_BLOCKED",
}

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


def _read_value_or_path(value: str) -> str:
    path = Path(value)
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return value.strip()


def _write_summary(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


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


def _bootstrap_boundary_metadata(bundle: dict[str, Any], args: argparse.Namespace) -> dict[str, str]:
    if args.item_id != BOOTSTRAP_GAP_ID or args.source != "DESIGN_GAP":
        return {}
    metadata = {
        "waiting_on_prerequisite_gap_id": str(bundle.get("waiting_on_prerequisite_gap_id") or "").strip(),
        "waiting_on_prerequisite_source": str(bundle.get("waiting_on_prerequisite_source") or "").strip(),
        "prerequisite_recovery_status": str(bundle.get("prerequisite_recovery_status") or "").strip(),
        "prerequisite_recovery_reason": str(bundle.get("prerequisite_recovery_reason") or "").strip(),
        "downstream_blocked_gap_id": str(bundle.get("downstream_blocked_gap_id") or "").strip(),
        "blocking_failure_code": str(bundle.get("blocking_failure_code") or "").strip(),
        "retry_condition": str(bundle.get("retry_condition") or "").strip(),
    }
    if metadata == {
        "waiting_on_prerequisite_gap_id": BOOTSTRAP_GAP_ID,
        "waiting_on_prerequisite_source": "DESIGN_GAP",
        "prerequisite_recovery_status": BOOTSTRAP_WAIT_STATUS,
        "prerequisite_recovery_reason": BOOTSTRAP_WAIT_REASON,
        "downstream_blocked_gap_id": SUMMARY_OWNERSHIP_GAP_ID,
        "blocking_failure_code": BOOTSTRAP_FAILURE_CODE,
        "retry_condition": BOOTSTRAP_RETRY_CONDITION,
    }:
        return metadata
    if any(metadata.values()):
        raise SystemExit("Incomplete or invalid structured bootstrap boundary metadata in recovery bundle")
    return {
        "waiting_on_prerequisite_gap_id": "",
        "waiting_on_prerequisite_source": "",
        "prerequisite_recovery_status": "",
        "prerequisite_recovery_reason": "",
        "downstream_blocked_gap_id": "",
        "blocking_failure_code": "",
        "retry_condition": "",
    }


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

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
                if args.terminal_action == "continue":
                    Path(args.drain_status_path).write_text("CONTINUE\n", encoding="utf-8")
            return result
        if decision == "BLOCKED":
            return _run_update(args, "blocked", "design_revision_blocked")
        raise SystemExit(f"Unexpected target design review decision: {decision}")
    if route == "PREREQUISITE_GAP_REQUIRED":
        if args.terminal_action == "block":
            return _run_update(args, "blocked", reason, recovery_status="TERMINAL_BLOCKED")
        metadata = _bootstrap_boundary_metadata(recovery_bundle, args)
        result = _run_update(
            args,
            "blocked",
            reason,
            recovery_status="PREREQUISITE_WORK_PENDING",
            waiting_on_prerequisite_gap_id=metadata.get("waiting_on_prerequisite_gap_id", ""),
            waiting_on_prerequisite_source=metadata.get("waiting_on_prerequisite_source", ""),
            prerequisite_recovery_status=metadata.get("prerequisite_recovery_status", ""),
            prerequisite_recovery_reason=metadata.get("prerequisite_recovery_reason", ""),
            downstream_blocked_gap_id=metadata.get("downstream_blocked_gap_id", ""),
            blocking_failure_code=metadata.get("blocking_failure_code", ""),
            retry_condition=metadata.get("retry_condition", ""),
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
