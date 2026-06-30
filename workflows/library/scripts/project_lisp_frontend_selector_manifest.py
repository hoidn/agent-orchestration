#!/usr/bin/env python3
"""Project backlog and gap state to the small selection prompt surface."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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


def _edge_ref(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    source = str(raw.get("source") or "").strip()
    item_id = str(raw.get("id") or "").strip()
    return {"source": source, "id": item_id} if source and item_id else {}


def _dependency_edges(run_state: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    for gap_id, entry in sorted((run_state.get("blocked_design_gaps") or {}).items()):
        if not isinstance(entry, dict):
            continue
        edge = entry.get("recovery_dependency_edge")
        if not isinstance(edge, dict):
            continue
        edges.append(
            {
                "blocked_work": _edge_ref(edge.get("blocked_work")) or {"source": "DESIGN_GAP", "id": str(gap_id)},
                "blocker_work": _edge_ref(edge.get("blocker_work")),
                "relation": str(edge.get("relation") or "").strip(),
                "status": str(edge.get("status") or "").strip(),
                "retry_target": _edge_ref(edge.get("retry_target")),
            }
        )
    return edges


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--architecture-index-root", required=True)
    parser.add_argument("--run-state-path", required=True)
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
    payload = {
        "manifest_version": 1,
        "manifest_path": output_rel.as_posix(),
        "backlog_root": manifest.get("backlog_root", ""),
        "active_count": len(items),
        "items": [_item_prompt_row(item) for item in items],
        "design_gap_count": len(design_gaps),
        "design_gaps": design_gaps,
        "dependency_edges": _dependency_edges(run_state),
    }
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
