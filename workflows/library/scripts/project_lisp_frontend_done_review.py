#!/usr/bin/env python3
"""Project a terminal DONE review into the selector bundle contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()
REJECTION_FIELDS = (
    "design_gap_id",
    "source_design_path",
    "source_sections",
    "missing_component",
    "proposed_scope",
)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SystemExit(f"Required JSON file does not exist: {path}") from exc
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object in {path}")
    return payload


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    raw = str(value).strip()
    path = Path(raw)
    if not raw or path.is_absolute() or ".." in path.parts:
        raise SystemExit(f"Unsafe relative path: {value}")
    under_path = Path(under)
    if path.parts[: len(under_path.parts)] != under_path.parts:
        raise SystemExit(f"Path {value} is not under {under}")
    resolved = (REPO_ROOT / path).resolve()
    try:
        resolved.relative_to(REPO_ROOT.resolve())
    except ValueError as exc:
        raise SystemExit(f"Path {value} escapes workspace") from exc
    if must_exist and not resolved.is_file():
        raise SystemExit(f"Required file does not exist: {value}")
    return path


def _required_text(payload: dict[str, Any], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SystemExit(f"missing required rejection field: {field}")
    return value.strip()


def _required_string_list(payload: dict[str, Any], field: str) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list) or not value:
        raise SystemExit(f"missing required rejection field: {field}")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise SystemExit(f"invalid rejection field item: {field}")
        result.append(item.strip())
    return result


def _approval_payload(review: dict[str, Any], original_selection_path: Path) -> dict[str, Any]:
    return {
        "selection_status": "DONE",
        "selection_rationale": _required_text(review, "review_rationale"),
        "terminal_review_decision": "APPROVE_DONE",
        "original_selection_bundle_path": original_selection_path.as_posix(),
    }


def _rejection_payload(review: dict[str, Any], original_selection_path: Path) -> dict[str, Any]:
    for field in REJECTION_FIELDS:
        if field not in review:
            raise SystemExit(f"missing required rejection field: {field}")
    source_design_path = _required_text(review, "source_design_path")
    _safe_relpath(source_design_path, under="docs/design")
    return {
        "selection_status": "DRAFT_DESIGN_GAP",
        "design_gap_id": _required_text(review, "design_gap_id"),
        "source_design_path": source_design_path,
        "source_sections": _required_string_list(review, "source_sections"),
        "missing_component": _required_text(review, "missing_component"),
        "proposed_scope": _required_text(review, "proposed_scope"),
        "selection_rationale": _required_text(review, "review_rationale"),
        "terminal_review_decision": "REJECT_DONE",
        "original_selection_bundle_path": original_selection_path.as_posix(),
    }


def _check_not_known_design_gap(review: dict[str, Any], run_state_path: str) -> None:
    run_state_rel = _safe_relpath(run_state_path, under="state", must_exist=True)
    run_state = _load_json(REPO_ROOT / run_state_rel)
    gap_id = str(review.get("design_gap_id") or "").strip()
    completed = {str(x) for x in (run_state.get("completed_design_gaps") or [])}
    blocked_value = run_state.get("blocked_design_gaps")
    blocked = (
        {str(k) for k in blocked_value}
        if isinstance(blocked_value, dict)
        else {str(x) for x in (blocked_value or [])}
    )
    if gap_id in completed | blocked:
        raise SystemExit(
            f"done-review rejection re-mints a known design gap: {gap_id}; "
            "route it through blocked-gap recovery or approve DONE"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review-path", required=True)
    parser.add_argument("--original-selection-path", required=True)
    parser.add_argument("--selection-output", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-state-path", required=False)
    args = parser.parse_args()

    review_rel = _safe_relpath(args.review_path, under="state", must_exist=True)
    original_selection_rel = _safe_relpath(args.original_selection_path, under="state", must_exist=True)
    selection_output_rel = _safe_relpath(args.selection_output, under="state")
    output_rel = _safe_relpath(args.output, under="state")

    review = _load_json(REPO_ROOT / review_rel)
    original_selection = _load_json(REPO_ROOT / original_selection_rel)
    if original_selection.get("selection_status") != "DONE":
        raise SystemExit("original selection must have selection_status=DONE")

    decision = str(review.get("done_decision") or "").strip()
    if decision == "APPROVE_DONE":
        projected = _approval_payload(review, original_selection_rel)
    elif decision == "REJECT_DONE":
        if args.run_state_path:
            _check_not_known_design_gap(review, args.run_state_path)
        projected = _rejection_payload(review, original_selection_rel)
    else:
        raise SystemExit(f"invalid done_decision: {decision or '<empty>'}")

    selection_output_path = REPO_ROOT / selection_output_rel
    output_path = REPO_ROOT / output_rel
    selection_output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    selection_output_path.write_text(json.dumps(projected, indent=2) + "\n", encoding="utf-8")
    output_path.write_text(
        json.dumps(
            {
                "selection_status": projected["selection_status"],
                "selection_bundle_path": selection_output_rel.as_posix(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
