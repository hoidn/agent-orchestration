#!/usr/bin/env python3
"""Project backlog and gap state to the small selection prompt surface."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

try:
    from workflows.library.scripts.workflow_recovery_dependencies import build_recovery_eligibility
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from workflows.library.scripts.workflow_recovery_dependencies import build_recovery_eligibility


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).exists():
        raise SystemExit(f"Required path does not exist: {value}")
    return path


def _item_prompt_row(item: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "item_id",
        "title",
        "path",
        "priority",
        "plan_path",
        "summary",
        "prerequisites",
        "related_roadmap_phases",
        "signals_for_selection",
    )
    return {key: item.get(key) for key in keys if key in item}


def _first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.MULTILINE)
    return match.group(1).strip() if match else ""


def _gap_status(raw_status: str, gap_id: str, run_state: dict[str, Any]) -> str:
    status = raw_status.lower().strip()
    if status.startswith("retired"):
        return "retired"
    if gap_id in {str(item) for item in run_state.get("completed_design_gaps") or []}:
        return "completed"
    if gap_id in (run_state.get("blocked_design_gaps") or {}):
        return "blocked"
    return "available"


def _design_gap_rows(root: Path, run_state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not root.is_dir():
        return rows
    for path in sorted(root.glob("*/implementation_architecture.md")):
        text = path.read_text(encoding="utf-8")
        gap_id = _first_match(r"^Design gap id:\s*`?([^`\n]+)`?\s*$", text) or path.parent.name
        title = _first_match(r"^#\s+(.+?)\s*$", text) or gap_id
        raw_status = _first_match(r"^Status:\s*(.+?)\s*$", text)
        try:
            rel = path.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            continue
        rows.append(
            {
                "design_gap_id": gap_id,
                "title": title,
                "status": _gap_status(raw_status, gap_id, run_state),
                "architecture_path": rel,
            }
        )
    return rows


def _bool_arg(value: str) -> bool:
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got {value!r}")


def _ref_key(source: str, item_id: str) -> tuple[str, str]:
    return source, item_id


def _public_hidden_work(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        source = str(row.get("source") or "").strip()
        item_id = str(row.get("id") or "").strip()
        reason = str(row.get("reason") or "").strip()
        if source and item_id:
            result.append({"source": source, "id": item_id, "reason": reason})
    return result


def _public_mechanics_errors(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    result = []
    for row in rows:
        code = str(row.get("code") or row.get("reason") or "").strip()
        reason = str(row.get("reason") or code).strip()
        if code:
            result.append({"code": code, "reason": reason})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--architecture-index-root", required=True)
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--target-gap-discovery-allowed", type=_bool_arg, default=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    manifest_rel = _safe_relpath(args.manifest_path, under="state", must_exist=True)
    index_rel = _safe_relpath(args.architecture_index_root, under="docs/plans")
    run_state_rel = _safe_relpath(args.run_state_path, under="state", must_exist=True)
    output_rel = _safe_relpath(args.output, under="state")
    manifest = json.loads((REPO_ROOT / manifest_rel).read_text(encoding="utf-8"))
    run_state = json.loads((REPO_ROOT / run_state_rel).read_text(encoding="utf-8"))
    items = [item for item in manifest.get("items") or [] if isinstance(item, dict)]
    design_gaps = _design_gap_rows(REPO_ROOT / index_rel, run_state)
    prompt_items = [_item_prompt_row(item) for item in items]
    item_rows_by_key = {
        _ref_key("BACKLOG_ITEM", str(row.get("item_id") or "").strip()): row
        for row in prompt_items
        if str(row.get("item_id") or "").strip()
    }
    gap_rows_by_key = {
        _ref_key("DESIGN_GAP", str(row.get("design_gap_id") or "").strip()): row
        for row in design_gaps
        if str(row.get("design_gap_id") or "").strip()
    }
    known_work = [
        {"source": "BACKLOG_ITEM", "id": key[1], "status": "available"}
        for key in item_rows_by_key
    ]
    known_work.extend(
        {"source": "DESIGN_GAP", "id": key[1], "status": row.get("status") or "available"}
        for key, row in gap_rows_by_key.items()
    )
    eligibility = build_recovery_eligibility(
        known_work,
        run_state,
        target_gap_discovery_allowed=args.target_gap_discovery_allowed,
    )
    eligible_items = [
        item_rows_by_key[_ref_key(str(ref.get("source") or ""), str(ref.get("id") or ""))]
        for ref in eligibility["eligible_work"]
        if _ref_key(str(ref.get("source") or ""), str(ref.get("id") or "")) in item_rows_by_key
    ]
    eligible_design_gaps = [
        gap_rows_by_key[_ref_key(str(ref.get("source") or ""), str(ref.get("id") or ""))]
        for ref in eligibility["eligible_work"]
        if _ref_key(str(ref.get("source") or ""), str(ref.get("id") or "")) in gap_rows_by_key
    ]
    payload = {
        "manifest_version": 1,
        "manifest_path": output_rel.as_posix(),
        "backlog_root": manifest.get("backlog_root", ""),
        "active_count": len(eligible_items),
        "items": eligible_items,
        "eligible_items": eligible_items,
        "all_item_count_diagnostic": len(prompt_items),
        "design_gap_count": len(eligible_design_gaps),
        "design_gaps": eligible_design_gaps,
        "eligible_design_gaps": eligible_design_gaps,
        "all_design_gap_count_diagnostic": len(design_gaps),
        "priority_recovery_work": eligibility["priority_recovery_work"],
        "hidden_work": _public_hidden_work(eligibility["hidden_work"]),
        "hidden_summary": eligibility["hidden_summary"],
        "blocking_mechanics_errors": _public_mechanics_errors(eligibility["blocking_mechanics_errors"]),
        "diagnostic_mechanics_errors": _public_mechanics_errors(eligibility["diagnostic_mechanics_errors"]),
        "blocking_mechanics_error_count": len(eligibility["blocking_mechanics_errors"]),
        "target_gap_discovery_allowed": args.target_gap_discovery_allowed,
    }
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
