#!/usr/bin/env python3
"""Write a selector bundle from deterministic prerequisite recovery state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise SystemExit(f"Missing required JSON file: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_relpath(value: str, *, under: str | None = None) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def _active_item_by_id(manifest: dict[str, Any], item_id: str) -> dict[str, Any] | None:
    for item in manifest.get("items") or []:
        if isinstance(item, dict) and str(item.get("item_id") or "").strip() == item_id:
            return item
    return None


def _row_refs(rows: Any) -> set[tuple[str, str]]:
    refs: set[tuple[str, str]] = set()
    if not isinstance(rows, list):
        return refs
    for row in rows:
        if not isinstance(row, dict):
            continue
        source = str(row.get("source") or "").strip()
        ref_id = str(row.get("id") or "").strip()
        if not source and row.get("design_gap_id"):
            source = "DESIGN_GAP"
            ref_id = str(row.get("design_gap_id") or "").strip()
        if not source and row.get("item_id"):
            source = "BACKLOG_ITEM"
            ref_id = str(row.get("item_id") or "").strip()
        if source and ref_id:
            refs.add((source, ref_id))
    return refs


def _eligible_ref(manifest: dict[str, Any], source: str, item_id: str) -> bool:
    source = str(source or "").strip()
    item_id = str(item_id or "").strip()
    if not source or not item_id:
        return False
    if source == "DESIGN_GAP":
        return (source, item_id) in (
            _row_refs(manifest.get("eligible_design_gaps")) | _row_refs(manifest.get("priority_recovery_work"))
        )
    if source == "BACKLOG_ITEM":
        return (source, item_id) in (
            _row_refs(manifest.get("eligible_items")) | _row_refs(manifest.get("priority_recovery_work"))
        )
    return False


def _hidden_ref(manifest: dict[str, Any], source: str, item_id: str) -> bool:
    return (source, item_id) in _row_refs(manifest.get("hidden_work"))


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "selection_status": "BLOCKED",
        "selection_rationale": reason,
        "blocking_reasons": [reason],
    }


def _selected_ref(pre_selection: dict[str, Any]) -> tuple[str, str, str]:
    status = str(pre_selection.get("recovery_pointer_status") or "").strip()
    if status == "WAITING":
        return (
            str(pre_selection.get("waiting_on_work_source") or "").strip(),
            str(pre_selection.get("waiting_on_work_id") or "").strip(),
            "waiting_on_prerequisite",
        )
    if status == "READY_TO_RETRY":
        return (
            str(pre_selection.get("retry_target_source") or "").strip(),
            str(pre_selection.get("retry_target_id") or "").strip(),
            "ready_to_retry",
        )
    return "", "", status.lower() or "missing_recovery_pointer_status"


def _proposed_prerequisite(pre_selection: dict[str, Any], source: str, item_id: str) -> dict[str, str]:
    proposed_id = str(pre_selection.get("proposed_prerequisite_id") or "").strip()
    proposed_source = str(pre_selection.get("proposed_prerequisite_source") or "DESIGN_GAP").strip()
    if proposed_id and proposed_id == item_id and proposed_source == source:
        return {
            "title": str(pre_selection.get("proposed_prerequisite_title") or "").strip(),
            "scope": str(pre_selection.get("proposed_prerequisite_scope") or "").strip(),
            "reason": str(pre_selection.get("proposed_prerequisite_reason") or "").strip(),
        }
    hint = str(pre_selection.get("prerequisite_gap_hint") or "").strip()
    if hint and source == "DESIGN_GAP":
        return {"title": "", "scope": hint, "reason": ""}
    return {}


def _selection_for_ref(
    *,
    source: str,
    item_id: str,
    relation: str,
    manifest: dict[str, Any],
    target_design_path: str,
    proposed_prerequisite: dict[str, str] | None = None,
) -> dict[str, Any]:
    if source == "DESIGN_GAP":
        proposed = proposed_prerequisite or {}
        missing_component = proposed.get("title") or "Prerequisite target-design work"
        proposed_scope = proposed.get("scope") or "Draft one bounded implementation architecture only."
        return {
            "selection_status": "DRAFT_DESIGN_GAP",
            "design_gap_id": item_id,
            "source_design_path": target_design_path,
            "source_sections": [],
            "missing_component": missing_component,
            "proposed_scope": proposed_scope,
            "prerequisite_relation": relation,
            "selection_rationale": "Selected by deterministic prerequisite recovery state.",
        }
    if source == "BACKLOG_ITEM":
        item = _active_item_by_id(manifest, item_id)
        if item is None:
            return _blocked(f"active backlog item not found for prerequisite recovery: {item_id}")
        item_path = str(item.get("path") or "").strip()
        if not item_path:
            return _blocked(f"active backlog item is missing path: {item_id}")
        return {
            "selection_status": "SELECT_BACKLOG_ITEM",
            "selected_item_id": item_id,
            "selected_item_path": item_path,
            "prerequisite_relation": relation,
            "selection_rationale": "Selected by deterministic prerequisite recovery state.",
        }
    return _blocked(f"unsupported prerequisite work source: {source or '<missing>'}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pre-selection-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--target-design-path", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    pre_selection = _load_json(REPO_ROOT / _safe_relpath(args.pre_selection_path, under="state"))
    manifest = _load_json(REPO_ROOT / _safe_relpath(args.manifest_path, under="state"))
    target_design_path = _safe_relpath(args.target_design_path, under="docs/design").as_posix()
    output_rel = _safe_relpath(args.output, under="state")

    if str(pre_selection.get("pre_selection_route") or "").strip() != "SELECT_PREREQUISITE_WORK":
        payload = _blocked("pre-selection route is not prerequisite recovery")
    else:
        source, item_id, relation = _selected_ref(pre_selection)
        if not item_id:
            payload = _blocked(relation)
        elif not _eligible_ref(manifest, source, item_id):
            proposed = _proposed_prerequisite(pre_selection, source, item_id)
            if proposed and source == "DESIGN_GAP" and not _hidden_ref(manifest, source, item_id):
                payload = _selection_for_ref(
                    source=source,
                    item_id=item_id,
                    relation=relation,
                    manifest=manifest,
                    target_design_path=target_design_path,
                    proposed_prerequisite=proposed,
                )
            elif _hidden_ref(manifest, source, item_id):
                payload = _blocked(f"ineligible_prerequisite_work: {source} {item_id}")
            else:
                payload = _blocked(f"missing_dependency_target: {source} {item_id}")
        else:
            payload = _selection_for_ref(
                source=source,
                item_id=item_id,
                relation=relation,
                manifest=manifest,
                target_design_path=target_design_path,
            )

    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
