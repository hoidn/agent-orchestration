#!/usr/bin/env python3
"""Classify final Lisp frontend work-item routing from phase state."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _read_required(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise SystemExit(f"Required state file is empty: {path}")
    return value


def _read_json_field(path: Path, field: str) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _read_state_value(path: Path, field: str) -> str:
    return _read_json_field(path, field) or _read_required(path)


def _write_output(path: Path, terminal_route: str, block_reason: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "route": terminal_route,
                "terminal_route": terminal_route,
                "block_reason": block_reason,
                "implementation_blocked": terminal_route == "IMPLEMENTATION_BLOCKED",
                "plan_review_exhausted": terminal_route == "PLAN_REVIEW_EXHAUSTED",
                "implementation_review_exhausted": terminal_route
                == "IMPLEMENTATION_REVIEW_EXHAUSTED",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _classify(plan_review_decision: str, implementation_state: str, implementation_review_decision: str) -> tuple[str, str]:
    if plan_review_decision == "REVISE":
        return "PLAN_REVIEW_EXHAUSTED", "plan_review_exhausted"
    if implementation_state == "BLOCKED":
        return "IMPLEMENTATION_BLOCKED", "implementation_blocked"
    if implementation_state == "COMPLETED":
        if implementation_review_decision == "APPROVE":
            return "COMPLETE", "none"
        if implementation_review_decision == "REVISE":
            return "IMPLEMENTATION_REVIEW_EXHAUSTED", "implementation_review_exhausted"
        raise SystemExit(f"Unexpected implementation review decision: {implementation_review_decision}")
    raise SystemExit(f"Unexpected implementation state: {implementation_state}")


def _run_adapter_payload(payload: dict[str, object]) -> int:
    output = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not output:
        raise SystemExit("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required for adapter invocation")
    terminal_route, block_reason = _classify(
        str(payload.get("plan_review_decision") or "").strip(),
        str(payload.get("implementation_state") or "").strip(),
        str(payload.get("implementation_review_decision") or "").strip(),
    )
    _write_output(Path(output), terminal_route, block_reason)
    return 0


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        return _run_adapter_payload(json.loads(sys.argv[1]))

    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-review-decision", required=True, choices=["APPROVE", "REVISE"])
    parser.add_argument("--implementation-state")
    parser.add_argument("--implementation-state-path")
    parser.add_argument("--implementation-review-decision")
    parser.add_argument("--implementation-review-decision-path")
    parser.add_argument("--implementation-bundle-path")
    parser.add_argument("--work-item-source", choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    if args.plan_review_decision == "REVISE":
        terminal_route, block_reason = _classify(args.plan_review_decision, "", "")
    else:
        implementation_state = (args.implementation_state or "").strip()
        if not implementation_state and args.implementation_bundle_path:
            implementation_state = _read_state_value(
                Path(args.implementation_bundle_path),
                "implementation_state",
            )
        if not implementation_state:
            implementation_state = _read_state_value(
                Path(args.implementation_state_path or ""),
                "implementation_state",
            )
        implementation_review_decision = ""
        if implementation_state == "COMPLETED":
            implementation_review_decision = (args.implementation_review_decision or "").strip()
            if not implementation_review_decision and args.implementation_bundle_path:
                implementation_review_decision = (
                    _read_json_field(Path(args.implementation_bundle_path), "implementation_review_decision")
                    or ""
                )
            if not implementation_review_decision:
                implementation_review_decision = _read_required(
                    Path(args.implementation_review_decision_path or "")
                ).strip()
        terminal_route, block_reason = _classify(
            args.plan_review_decision,
            implementation_state,
            implementation_review_decision,
        )
    _write_output(Path(args.output), terminal_route, block_reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
