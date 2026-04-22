#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


APPROVED_OUTCOME = "APPROVED"
SKIPPED_OUTCOMES = {"SKIPPED_AFTER_DESIGN", "SKIPPED_AFTER_PLAN", "SKIPPED_AFTER_IMPLEMENTATION"}
COMPLETED_STATUSES = {"done", "completed", "approved"}


def update_manifest(
    *,
    root: Path,
    selection_bundle_path: str,
    tranche_manifest_path: str,
    item_outcome: str | None = None,
    execution_report_path: str | None = None,
    item_summary_path: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    selection_bundle = _read_json_file(root, selection_bundle_path, "selection_bundle_path")
    selected_tranche_id = _require_string(selection_bundle.get("selected_tranche_id"), "selected_tranche_id")
    item_state_root = _require_string(selection_bundle.get("item_state_root"), "item_state_root")
    item_state_path = _require_relpath(root, item_state_root, "item_state_root")
    manifest_path = _require_existing_file(root, tranche_manifest_path, "tranche_manifest_path")

    if item_outcome is None:
        item_outcome = _read_text_file(item_state_path / "item_outcome.txt", "item_outcome").strip()
    if execution_report_path is None:
        execution_report_path = _read_text_file(
            item_state_path / "final_execution_report_path.txt",
            "execution_report_path",
        ).strip()
    if item_summary_path is None:
        item_summary_path = _read_text_file(
            item_state_path / "final_item_summary_path.txt",
            "item_summary_path",
        ).strip()

    _require_existing_file(root, execution_report_path, "execution_report_path")
    _require_existing_file(root, item_summary_path, "item_summary_path")

    if item_outcome == APPROVED_OUTCOME:
        next_status = "completed"
        drain_status = "CONTINUE"
    elif item_outcome in SKIPPED_OUTCOMES:
        next_status = "blocked"
        drain_status = "BLOCKED"
    else:
        raise ValueError(f"Unsupported item_outcome: {item_outcome}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    tranches = manifest.get("tranches") if isinstance(manifest, dict) else None
    if not isinstance(tranches, list):
        raise ValueError("Manifest tranches must be an array")

    found = False
    for tranche in tranches:
        if not isinstance(tranche, dict):
            raise ValueError("Every tranche must be a JSON object")
        if tranche.get("tranche_id") != selected_tranche_id:
            continue
        tranche["status"] = next_status
        tranche["last_item_outcome"] = item_outcome
        tranche["last_execution_report_path"] = execution_report_path
        tranche["last_item_summary_path"] = item_summary_path
        found = True
        break
    if not found:
        raise ValueError(f"Selected tranche not found in manifest: {selected_tranche_id}")

    tmp_path = manifest_path.with_suffix(manifest_path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(manifest_path)

    counts = _count_manifest_state(manifest)
    return {
        "drain_status": drain_status,
        "updated_tranche_id": selected_tranche_id,
        "item_outcome": item_outcome,
        "tranche_manifest_path": tranche_manifest_path,
        "execution_report_path": execution_report_path,
        "item_summary_path": item_summary_path,
        **counts,
    }


def _count_manifest_state(manifest: dict[str, Any]) -> dict[str, int]:
    tranches = manifest.get("tranches", [])
    status_by_id = {
        tranche["tranche_id"]: tranche.get("status")
        for tranche in tranches
        if isinstance(tranche, dict) and isinstance(tranche.get("tranche_id"), str)
    }
    completed_count = 0
    pending_count = 0
    ready_count = 0
    for tranche in tranches:
        if not isinstance(tranche, dict):
            continue
        status = tranche.get("status")
        if status in COMPLETED_STATUSES:
            completed_count += 1
            continue
        if status != "pending":
            continue
        pending_count += 1
        prerequisites = tranche.get("prerequisites", [])
        if isinstance(prerequisites, list) and all(status_by_id.get(prereq) in COMPLETED_STATUSES for prereq in prerequisites):
            ready_count += 1
    return {
        "ready_count": ready_count,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "blocked_count": len(tranches) - completed_count - ready_count,
    }


def _read_json_file(root: Path, value: str, field: str) -> dict[str, Any]:
    path = _require_existing_file(root, value, field)
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{field} must contain a JSON object")
    return data


def _read_text_file(path: Path, field: str) -> str:
    if not path.is_file():
        raise ValueError(f"{field} source file does not exist: {path}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"{field} source file is empty: {path}")
    return text


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_relpath(root: Path, value: str, field: str) -> Path:
    rel = _require_string(value, field)
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field} escapes workspace: {rel}")
    return resolved


def _require_existing_file(root: Path, value: str, field: str) -> Path:
    resolved = _require_relpath(root, value, field)
    if not resolved.is_file():
        raise ValueError(f"{field} target does not exist: {value}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Update a major-project tranche manifest after one tranche run.")
    parser.add_argument("--selection-bundle", required=True)
    parser.add_argument("--tranche-manifest-path", required=True)
    parser.add_argument("--item-outcome")
    parser.add_argument("--execution-report-path")
    parser.add_argument("--item-summary-path")
    parser.add_argument("--output-bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    payload = update_manifest(
        root=args.root,
        selection_bundle_path=args.selection_bundle,
        tranche_manifest_path=args.tranche_manifest_path,
        item_outcome=args.item_outcome,
        execution_report_path=args.execution_report_path,
        item_summary_path=args.item_summary_path,
    )
    args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
    args.output_bundle.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
