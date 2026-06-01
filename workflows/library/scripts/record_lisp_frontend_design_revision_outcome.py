#!/usr/bin/env python3
"""Record the terminal result of a Lisp frontend target-design revision loop."""

from __future__ import annotations

import argparse
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-decision", required=True, choices=["APPROVE", "REVISE", "BLOCKED"])
    parser.add_argument("--state-path", required=True)
    parser.add_argument("--item-id", required=True)
    parser.add_argument("--source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    parser.add_argument("--summary-path", required=True)
    parser.add_argument("--summary-pointer-path", required=True)
    parser.add_argument("--drain-status-path", required=True)
    args = parser.parse_args()

    command = [
        "python",
        "workflows/library/scripts/update_lisp_frontend_run_state.py",
        "--state-path",
        args.state_path,
    ]
    if args.review_decision == "APPROVE":
        command.extend(
            [
                "design_revision",
                "--item-id",
                args.item_id,
                "--source",
                args.source,
                "--reason",
                "implementation_design_revision_required",
            ]
        )
    else:
        command.extend(
            [
                "blocked",
                "--item-id",
                args.item_id,
                "--source",
                args.source,
                "--reason",
                "design_revision_exhausted",
            ]
        )
    command.extend(
        [
            "--summary-path",
            args.summary_path,
            "--summary-pointer-path",
            args.summary_pointer_path,
            "--drain-status-path",
            args.drain_status_path,
        ]
    )
    return subprocess.run(command).returncode


if __name__ == "__main__":
    raise SystemExit(main())
