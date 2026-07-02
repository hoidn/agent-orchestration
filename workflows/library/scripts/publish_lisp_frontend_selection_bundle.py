#!/usr/bin/env python3
"""Publish the authoritative selector bundle path as structured state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()
ALLOWED_STATUSES = {"SELECT_BACKLOG_ITEM", "DRAFT_DESIGN_GAP", "DONE", "BLOCKED"}


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).is_file():
        raise SystemExit(f"Required file does not exist: {value}")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing required JSON file: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise SystemExit(f"Expected JSON object: {path}")
    return payload


def _row_id(row: Any, *keys: str) -> str:
    if not isinstance(row, dict):
        return ""
    for key in keys:
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def _ids(rows: Any, *keys: str) -> set[str]:
    if not isinstance(rows, list):
        return set()
    return {item for row in rows if (item := _row_id(row, *keys))}


def _validate_against_manifest(selection: dict[str, Any], manifest: dict[str, Any]) -> None:
    status = str(selection.get("selection_status") or "").strip()
    eligible_items = _ids(manifest.get("eligible_items") or manifest.get("items"), "item_id", "id")
    eligible_gaps = _ids(
        manifest.get("eligible_design_gaps") or manifest.get("design_gaps"),
        "design_gap_id",
        "id",
    )

    if status == "SELECT_BACKLOG_ITEM":
        selected = str(selection.get("selected_item_id") or "").strip()
        if not selected:
            raise SystemExit("SELECT_BACKLOG_ITEM selection missing selected_item_id")
        if eligible_items and selected not in eligible_items:
            raise SystemExit(f"selected_item_id is not eligible: {selected}")
        return

    if status == "DRAFT_DESIGN_GAP":
        selected = str(selection.get("design_gap_id") or "").strip()
        if not selected:
            raise SystemExit("DRAFT_DESIGN_GAP selection missing design_gap_id")
        if eligible_gaps and selected not in eligible_gaps:
            raise SystemExit(f"design_gap_id is not eligible: {selected}")
        return


def _row_by_id(rows: Any, selected: str, *keys: str) -> dict[str, Any]:
    if not isinstance(rows, list):
        return {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        if _row_id(row, *keys) == selected:
            return dict(row)
    return {}


def _enrich_selection_bundle(selection: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(selection)
    history = manifest.get("attempt_history_summary")
    if isinstance(history, dict):
        enriched["attempt_history_summary"] = history

    status = str(selection.get("selection_status") or "").strip()
    if status == "DRAFT_DESIGN_GAP":
        selected = str(selection.get("design_gap_id") or "").strip()
        row = _row_by_id(
            manifest.get("eligible_design_gaps") or manifest.get("design_gaps"),
            selected,
            "design_gap_id",
            "id",
        )
        if row:
            enriched["selected_design_gap"] = row
    elif status == "SELECT_BACKLOG_ITEM":
        selected = str(selection.get("selected_item_id") or "").strip()
        row = _row_by_id(
            manifest.get("eligible_items") or manifest.get("items"),
            selected,
            "item_id",
            "id",
        )
        if row:
            enriched["selected_item"] = row
    return enriched


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-path", required=True)
    parser.add_argument("--manifest-path", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    selection_rel = _safe_relpath(args.selection_path, under="state", must_exist=True)
    selection = _load_json(REPO_ROOT / selection_rel)
    status = selection.get("selection_status")
    if status not in ALLOWED_STATUSES:
        raise SystemExit(f"Invalid selection_status: {status}")
    manifest = None
    if args.manifest_path:
        manifest_rel = _safe_relpath(args.manifest_path, under="state", must_exist=True)
        manifest = _load_json(REPO_ROOT / manifest_rel)
        _validate_against_manifest(selection, manifest)
        selection = _enrich_selection_bundle(selection, manifest)
        (REPO_ROOT / selection_rel).write_text(
            json.dumps(selection, indent=2) + "\n",
            encoding="utf-8",
        )

    output_rel = _safe_relpath(args.output, under="state")
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({"selection_bundle_path": selection_rel.as_posix()}, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
