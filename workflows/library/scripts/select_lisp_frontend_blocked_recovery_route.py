#!/usr/bin/env python3
"""Normalize blocked implementation recovery routing."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


RECOVERY_ROUTES = {
    "GAP_DESIGN_REVISION_REQUIRED",
    "TARGET_DESIGN_REVISION_REQUIRED",
    "PREREQUISITE_GAP_REQUIRED",
    "TERMINAL_BLOCKED",
}

_REPO_SCOPE_TERMS = (
    "repo-local",
    "contract",
    "import-boundary",
    "adapter",
    "verification",
    "target-design",
    "gap-design",
    "prerequisite-design",
)

_EXTERNAL_USER_TERMS = (
    "external human authority",
    "credential",
    "environment",
    "local setup",
    "user intervention",
    "major unresolvable ambiguity",
    "cannot be resolved",
)


def _load_optional_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_design_gap_recovery(route: str, reason: str, summary: str) -> tuple[str, str]:
    if route != "TERMINAL_BLOCKED" or reason != "user_decision_required":
        return route, reason
    normalized = summary.lower()
    if any(term in normalized for term in _EXTERNAL_USER_TERMS):
        return route, reason
    if any(term in normalized for term in _REPO_SCOPE_TERMS):
        return "GAP_DESIGN_REVISION_REQUIRED", "implementation_architecture_under_scoped"
    return route, reason


def main() -> int:
    if len(sys.argv) == 2 and sys.argv[1].lstrip().startswith("{"):
        payload = json.loads(sys.argv[1])
        output = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
        if not output:
            raise SystemExit("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required for adapter invocation")
        terminal_route = str(payload.get("terminal_route") or "").strip()
        work_item_source = str(payload.get("work_item_source") or "").strip()
        route = "NOT_APPLICABLE"
        reason = "not_blocked"
        if terminal_route == "IMPLEMENTATION_BLOCKED":
            if work_item_source == "DESIGN_GAP":
                route = str(payload.get("blocked_recovery_route") or "").strip()
                reason = str(payload.get("reason") or "").strip()
                if route not in RECOVERY_ROUTES:
                    raise SystemExit(f"Unexpected blocked_recovery_route: {route}")
                if not reason:
                    raise SystemExit("Blocked recovery classifier payload missing reason")
                route, reason = _normalize_design_gap_recovery(
                    route,
                    reason,
                    str(payload.get("summary") or ""),
                )
            else:
                route = "TERMINAL_BLOCKED"
                reason = "implementation_blocked"
        target = Path(output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps({"blocked_recovery_route": route, "reason": reason}, indent=2) + "\n",
            encoding="utf-8",
        )
        return 0

    parser = argparse.ArgumentParser()
    parser.add_argument("--terminal-route", required=True)
    parser.add_argument("--work-item-source", required=True, choices=["BACKLOG_ITEM", "DESIGN_GAP", "RECOVERED_IN_PROGRESS"])
    parser.add_argument("--classifier-bundle-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    terminal_route = args.terminal_route.strip()
    route = "NOT_APPLICABLE"
    reason = "not_blocked"

    if terminal_route == "IMPLEMENTATION_BLOCKED":
        if args.work_item_source == "DESIGN_GAP":
            bundle = _load_optional_json(Path(args.classifier_bundle_path))
            if bundle is None:
                raise SystemExit(f"Missing blocked recovery classifier bundle: {args.classifier_bundle_path}")
            route = str(bundle.get("blocked_recovery_route") or "").strip()
            reason = str(bundle.get("reason") or "").strip()
            if route not in RECOVERY_ROUTES:
                raise SystemExit(f"Unexpected blocked_recovery_route: {route}")
            if not reason:
                raise SystemExit("Blocked recovery classifier bundle missing reason")
            route, reason = _normalize_design_gap_recovery(
                route,
                reason,
                str(bundle.get("summary") or ""),
            )
        else:
            route = "TERMINAL_BLOCKED"
            reason = "implementation_blocked"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"blocked_recovery_route": route, "reason": reason}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
