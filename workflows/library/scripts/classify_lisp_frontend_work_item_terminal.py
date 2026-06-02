#!/usr/bin/env python3
"""Classify final Lisp frontend work-item routing from phase state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

def _read_required(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit(f"Required state file is empty: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-review-decision", required=True, choices=["APPROVE", "REVISE"])
    parser.add_argument("--implementation-state-path", required=True)
    parser.add_argument("--implementation-review-decision-path", required=True)
    parser.add_argument("--implementation-bundle-path")
    parser.add_argument("--work-item-source", choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.plan_review_decision == "REVISE":
        terminal_route = "PLAN_REVIEW_EXHAUSTED"
        block_reason = "plan_review_exhausted"
    else:
        implementation_state = _read_required(Path(args.implementation_state_path))
        if implementation_state == "BLOCKED":
            terminal_route = "IMPLEMENTATION_BLOCKED"
            block_reason = "implementation_blocked"
        elif implementation_state == "COMPLETED":
            review_decision = _read_required(Path(args.implementation_review_decision_path))
            if review_decision == "APPROVE":
                terminal_route = "COMPLETE"
                block_reason = "none"
            elif review_decision == "REVISE":
                terminal_route = "IMPLEMENTATION_REVIEW_EXHAUSTED"
                block_reason = "implementation_review_exhausted"
            else:
                raise SystemExit(f"Unexpected implementation review decision: {review_decision}")
        else:
            raise SystemExit(f"Unexpected implementation state: {implementation_state}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"terminal_route": terminal_route, "block_reason": block_reason}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
