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


def _run_update(args: argparse.Namespace, command: str, reason: str) -> int:
    return subprocess.run(
        [
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
            reason,
            "--summary-path",
            args.summary_path,
            "--summary-pointer-path",
            args.summary_pointer_path,
            "--drain-status-path",
            args.drain_status_path,
        ]
    ).returncode


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

    if route == "GAP_DESIGN_REVISION_REQUIRED":
        if args.revision_report:
            report = json.loads(Path(args.revision_report).read_text(encoding="utf-8"))
            decision = str(report.get("design_revision_decision") or "").strip()
            if decision == "BLOCKED":
                return _run_update(args, "blocked", "gap_design_revision_blocked")
            if decision != "REVISED":
                raise SystemExit(f"Unexpected gap design revision decision: {decision}")
        return _run_update(args, "gap_design_revision", reason)
    if route == "TARGET_DESIGN_REVISION_REQUIRED":
        decision = _read_value_or_path(args.target_design_review_decision)
        if decision == "APPROVE":
            return _run_update(args, "design_revision", "implementation_design_revision_required")
        if decision in {"REVISE", "BLOCKED"}:
            return _run_update(args, "blocked", "design_revision_exhausted")
        raise SystemExit(f"Unexpected target design review decision: {decision}")

    if args.terminal_action == "block":
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
