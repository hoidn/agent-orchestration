#!/usr/bin/env python3
"""Classify whether a Lisp frontend implementation blocker can revise design."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REVISION_ALLOWED = {"roadmap_conflict"}
BLOCKED_CLASSES = {
    "missing_resource",
    "unavailable_hardware",
    "roadmap_conflict",
    "external_dependency_outside_authority",
    "user_decision_required",
    "unrecoverable_after_fix_attempt",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation-state-path", required=True)
    parser.add_argument("--work-item-source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP"])
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    payload = json.loads(Path(args.implementation_state_path).read_text(encoding="utf-8"))
    if payload.get("implementation_state") != "BLOCKED":
        raise SystemExit("Implementation blocker classifier requires BLOCKED implementation_state")

    blocker_class = str(payload.get("blocker_class") or "").strip()
    if blocker_class not in BLOCKED_CLASSES:
        raise SystemExit(f"Unexpected blocker_class: {blocker_class}")

    if args.work_item_source == "DESIGN_GAP" and blocker_class in REVISION_ALLOWED:
        route = "DESIGN_REVISION_ALLOWED"
        reason = "implementation_design_revision_required"
    else:
        route = "TERMINAL_BLOCK"
        reason = "implementation_blocked"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {"blocker_route": route, "blocker_class": blocker_class, "block_reason": reason},
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
