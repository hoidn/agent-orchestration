#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


COMPLETED_STATUSES = {"done", "completed", "approved"}
SUPERSEDED_STATUS = "superseded"
TRANCHE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")

REQUIRED_SELECTED_FIELDS = [
    "brief_path",
    "design_target_path",
    "design_review_report_target_path",
    "plan_target_path",
    "plan_review_report_target_path",
    "execution_report_target_path",
    "implementation_review_report_target_path",
    "item_summary_target_path",
]


def select_next_tranche(
    *,
    root: Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
    state_root: str,
) -> dict[str, Any]:
    root = root.resolve()
    _require_existing_file(root, project_brief_path, "project_brief_path")
    _require_existing_file(root, project_roadmap_path, "project_roadmap_path")
    manifest_path = _require_existing_file(root, tranche_manifest_path, "tranche_manifest_path")
    _require_relpath(root, state_root, "state_root")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Tranche manifest must be a JSON object")
    if manifest.get("project_brief_path") != project_brief_path:
        raise ValueError("Manifest project_brief_path must match the workflow input")
    if manifest.get("project_roadmap_path") != project_roadmap_path:
        raise ValueError("Manifest project_roadmap_path must match the roadmap output")

    project_id = _require_string(manifest.get("project_id"), "project_id")
    tranches = manifest.get("tranches")
    if not isinstance(tranches, list) or not tranches:
        raise ValueError("Manifest tranches must be a non-empty array")

    known_ids: set[str] = set()
    status_by_id: dict[str, str] = {}
    prereq_by_id: dict[str, list[str]] = {}
    selected: dict[str, Any] | None = None
    ready_count = 0
    pending_count = 0
    completed_count = 0
    superseded_count = 0

    for index, tranche in enumerate(tranches):
        if not isinstance(tranche, dict):
            raise ValueError(f"Tranche {index} must be a JSON object")
        tranche_id = _require_string(tranche.get("tranche_id"), f"tranches[{index}].tranche_id")
        if not TRANCHE_ID_RE.fullmatch(tranche_id):
            raise ValueError(f"Tranche id is not a safe slug: {tranche_id}")
        if tranche_id in known_ids:
            raise ValueError(f"Duplicate tranche_id: {tranche_id}")
        known_ids.add(tranche_id)

        status = _require_string(tranche.get("status"), f"{tranche_id}.status")
        prerequisites = tranche.get("prerequisites", [])
        if not isinstance(prerequisites, list) or not all(isinstance(item, str) and item for item in prerequisites):
            raise ValueError(f"Tranche {tranche_id} prerequisites must be an array of strings")
        status_by_id[tranche_id] = status
        prereq_by_id[tranche_id] = list(prerequisites)

    for tranche_id, prerequisites in prereq_by_id.items():
        missing = [prereq for prereq in prerequisites if prereq not in known_ids]
        if missing:
            raise ValueError(f"Tranche {tranche_id} has unknown prerequisites: {', '.join(missing)}")

    for tranche in tranches:
        tranche_id = tranche["tranche_id"]
        status = status_by_id[tranche_id]
        if status == SUPERSEDED_STATUS:
            superseded_count += 1
            continue
        if status in COMPLETED_STATUSES:
            completed_count += 1
            continue
        if status != "pending":
            continue
        pending_count += 1
        if all(status_by_id[prereq] in COMPLETED_STATUSES for prereq in prereq_by_id[tranche_id]):
            ready_count += 1
            if selected is None:
                selected = tranche

    blocked_count = len(tranches) - completed_count - superseded_count - ready_count
    base_payload: dict[str, Any] = {
        "project_brief_path": project_brief_path,
        "project_roadmap_path": project_roadmap_path,
        "tranche_manifest_path": tranche_manifest_path,
        "ready_count": ready_count,
        "pending_count": pending_count,
        "completed_count": completed_count,
        "superseded_count": superseded_count,
        "blocked_count": blocked_count,
    }

    if selected is None:
        if completed_count + superseded_count == len(tranches):
            return {
                **base_payload,
                "selection_status": "DONE",
                "reason": "All tranches are completed.",
            }
        return {
            **base_payload,
            "selection_status": "BLOCKED",
            "reason": "No pending tranche has satisfied prerequisites.",
        }

    selected_id = selected["tranche_id"]
    missing_fields = [field for field in REQUIRED_SELECTED_FIELDS if not isinstance(selected.get(field), str) or not selected[field]]
    if missing_fields:
        raise ValueError(f"Selected tranche missing required fields: {', '.join(missing_fields)}")

    item_state_root = f"{state_root.rstrip('/')}/items/{project_id}/{selected_id}"
    return {
        **base_payload,
        "selection_status": "SELECTED",
        "reason": "Selected first ready pending tranche.",
        "selected_tranche_id": selected_id,
        "item_state_root": item_state_root,
        "scope_boundary_path": f"{item_state_root}/scope_boundary.json",
        "upstream_escalation_context_path": f"{item_state_root}/upstream_escalation_context.json",
        "big_design_phase_state_root": f"{item_state_root}/big-design-phase",
        "plan_phase_state_root": f"{item_state_root}/plan-phase",
        "implementation_phase_state_root": f"{item_state_root}/implementation-phase",
        "tranche_brief_path": selected["brief_path"],
        "design_target_path": selected["design_target_path"],
        "design_review_report_target_path": selected["design_review_report_target_path"],
        "plan_target_path": selected["plan_target_path"],
        "plan_review_report_target_path": selected["plan_review_report_target_path"],
        "execution_report_target_path": selected["execution_report_target_path"],
        "implementation_review_report_target_path": selected["implementation_review_report_target_path"],
        "item_summary_target_path": selected["item_summary_target_path"],
    }


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
    parser = argparse.ArgumentParser(description="Select the next ready major-project tranche.")
    parser.add_argument("--project-brief-path", required=True)
    parser.add_argument("--project-roadmap-path", required=True)
    parser.add_argument("--tranche-manifest-path", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--output-bundle", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    payload = select_next_tranche(
        root=args.root,
        project_brief_path=args.project_brief_path,
        project_roadmap_path=args.project_roadmap_path,
        tranche_manifest_path=args.tranche_manifest_path,
        state_root=args.state_root,
    )
    args.output_bundle.parent.mkdir(parents=True, exist_ok=True)
    args.output_bundle.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
