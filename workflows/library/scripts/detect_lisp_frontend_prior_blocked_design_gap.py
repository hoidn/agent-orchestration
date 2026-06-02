#!/usr/bin/env python3
"""Compatibility wrapper for blocked design-gap recovery detection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from detect_lisp_frontend_blocked_design_gap_recovery import _recovery_payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--architecture-index-root", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    architecture_index_root = Path(args.architecture_index_root or "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps")
    payload = _recovery_payload(
        Path(args.run_state_path),
        Path(args.artifact_work_root),
        architecture_index_root,
        output.with_name("prior-blocked-progress-report.md"),
        output.with_name("prior-blocked-gap-architecture.md"),
        output.with_name("prior-blocked-gap-execution-plan.md"),
    )
    legacy = {
        "recovery_status": "RECOVER_BLOCKED_DESIGN_GAP"
        if payload["pre_selection_route"] == "RECOVER_BLOCKED_DESIGN_GAP"
        else "NONE",
        "design_gap_id": payload["design_gap_id"],
        "progress_report_path": payload["progress_report_path"],
        "architecture_path": payload["architecture_path"],
        "plan_path": payload["plan_path"],
        "architecture_copy_path": payload["architecture_copy_path"],
        "plan_copy_path": payload["plan_copy_path"],
        "blocker_class": payload["blocker_class"],
        "block_reason": payload["block_reason"],
    }
    output.write_text(json.dumps(legacy, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
