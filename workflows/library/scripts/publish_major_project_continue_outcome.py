#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


BLOCKED_OUTCOMES = {"ESCALATE_ROADMAP_REVISION"}


def publish_continue_outcome(
    *,
    root: Path,
    selection_bundle_path: str,
    item_outcome: str,
    output_bundle_path: str,
) -> dict[str, Any]:
    if item_outcome not in BLOCKED_OUTCOMES:
        raise ValueError(f"Unsupported continue outcome: {item_outcome}")

    root = root.resolve()
    selection = _read_json_file(root, selection_bundle_path, "selection_bundle_path")
    item_state_root = _require_string(selection.get("item_state_root"), "item_state_root")
    item_state_path = _require_existing_dir(root, item_state_root, "item_state_root")
    tranche_manifest_path = _require_string(selection.get("tranche_manifest_path"), "tranche_manifest_path")
    _require_existing_file(root, tranche_manifest_path, "tranche_manifest_path")

    published_outcome = _read_text_file(item_state_path / "item_outcome.txt", "item_outcome").strip()
    if published_outcome != item_outcome:
        raise ValueError(f"Published item_outcome {published_outcome!r} does not match requested {item_outcome!r}")

    execution_report_path = _read_text_file(
        item_state_path / "final_execution_report_path.txt",
        "execution_report_path",
    ).strip()
    item_summary_path = _read_text_file(item_state_path / "final_item_summary_path.txt", "item_summary_path").strip()
    _require_existing_file(root, execution_report_path, "execution_report_path")
    _require_existing_file(root, item_summary_path, "item_summary_path")

    payload: dict[str, Any] = {
        "drain_status": "BLOCKED",
        "item_outcome": item_outcome,
        "tranche_manifest_path": tranche_manifest_path,
        "execution_report_path": execution_report_path,
        "item_summary_path": item_summary_path,
    }

    roadmap_pointer_path = item_state_path / "final_roadmap_change_request_path.txt"
    if roadmap_pointer_path.is_file():
        roadmap_change_request_path = roadmap_pointer_path.read_text(encoding="utf-8").strip()
        _require_existing_file(root, roadmap_change_request_path, "roadmap_change_request_path")
        payload["roadmap_change_request_path"] = roadmap_change_request_path

    output_path = _require_relpath(root, output_bundle_path, "output_bundle_path")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


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


def _require_existing_dir(root: Path, value: str, field: str) -> Path:
    resolved = _require_relpath(root, value, field)
    if not resolved.is_dir():
        raise ValueError(f"{field} target does not exist: {value}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a controlled blocked outcome for continuation workflows.")
    parser.add_argument("--selection-bundle", required=True)
    parser.add_argument("--item-outcome", required=True)
    parser.add_argument("--output-bundle", required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    publish_continue_outcome(
        root=args.root,
        selection_bundle_path=args.selection_bundle,
        item_outcome=args.item_outcome,
        output_bundle_path=args.output_bundle,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
