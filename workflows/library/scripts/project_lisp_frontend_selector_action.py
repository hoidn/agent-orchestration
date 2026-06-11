from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in {"1", "true", "yes"}


def _load_args(args: list[str]) -> dict[str, object]:
    if len(args) == 1 and args[0].lstrip().startswith("{"):
        payload = json.loads(args[0])
        if not isinstance(payload, dict):
            raise SystemExit("selector action adapter input must be a JSON object")
        return payload
    if len(args) == 7:
        (
            selection_status,
            selection_bundle_path,
            is_selected,
            is_design_gap,
            is_done,
            is_blocked,
            blocked_reason,
        ) = args
        return {
            "selection_status": selection_status,
            "selection_bundle_path": selection_bundle_path,
            "is_selected": is_selected,
            "is_design_gap": is_design_gap,
            "is_done": is_done,
            "is_blocked": is_blocked,
            "blocked_reason": blocked_reason,
        }
    raise SystemExit(
        "usage: project_lisp_frontend_selector_action.py "
        "<json-payload> OR <status> <selection-bundle> <is-selected> "
        "<is-design-gap> <is-done> <is-blocked> <blocked-reason>"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    payload_args = _load_args(args)
    selection_status = str(payload_args.get("selection_status") or "").strip()
    selection_bundle = str(payload_args.get("selection_bundle_path") or "").strip()
    is_selected = _as_bool(payload_args.get("is_selected"))
    is_design_gap = _as_bool(payload_args.get("is_design_gap"))
    is_done = _as_bool(payload_args.get("is_done"))
    is_blocked = _as_bool(payload_args.get("is_blocked"))
    blocked_reason = str(payload_args.get("blocked_reason") or "").strip()

    expected_flags = {
        "SELECT_BACKLOG_ITEM": (True, False, False, False),
        "DRAFT_DESIGN_GAP": (False, True, False, False),
        "DONE": (False, False, True, False),
        "BLOCKED": (False, False, False, True),
    }
    expected = expected_flags.get(selection_status)
    if expected is None:
        raise SystemExit(f"invalid selection_status: {selection_status or '<empty>'}")
    actual = (is_selected, is_design_gap, is_done, is_blocked)
    if actual != expected:
        raise SystemExit(
            "selection_status conflicts with selector flags: "
            f"status={selection_status} flags={actual}"
        )

    if selection_status in {"SELECT_BACKLOG_ITEM", "DRAFT_DESIGN_GAP"} and not selection_bundle:
        raise SystemExit(f"selection_bundle_path is required for {selection_status}")

    if selection_status == "SELECT_BACKLOG_ITEM":
        payload = {
            "variant": "SELECTED_ITEM",
            "selected_item_selection_bundle": selection_bundle,
        }
    elif selection_status == "DRAFT_DESIGN_GAP":
        payload = {
            "variant": "DRAFT_DESIGN_GAP",
            "design_gap_selection_bundle": selection_bundle,
        }
    elif selection_status == "DONE":
        payload = {"variant": "DONE"}
    elif selection_status == "BLOCKED":
        payload = {
            "variant": "BLOCKED",
            "blocked_reason": blocked_reason or "selector_blocked",
        }
    else:
        payload = {
            "variant": "EXHAUSTED",
            "exhausted_reason": "selector_action_unclassified",
        }

    output_bundle_path = os.environ.get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", "").strip()
    if not output_bundle_path:
        raise SystemExit("ORCHESTRATOR_OUTPUT_BUNDLE_PATH is required")
    bundle_path = Path(output_bundle_path)
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
