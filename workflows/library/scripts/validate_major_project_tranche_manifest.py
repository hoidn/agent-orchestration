#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ALLOWED_STATUSES = {"pending", "blocked", "done", "completed", "approved", "superseded"}
COMPLETED_STATUSES = {"done", "completed", "approved"}
ALLOWED_DESIGN_DEPTHS = {"big", "standard"}
ALLOWED_COMPLETION_GATES = {"implementation_approved"}

REQUIRED_TRANCHE_FIELDS = {
    "tranche_id",
    "title",
    "brief_path",
    "design_target_path",
    "design_review_report_target_path",
    "plan_target_path",
    "plan_review_report_target_path",
    "execution_report_target_path",
    "implementation_review_report_target_path",
    "item_summary_target_path",
    "prerequisites",
    "status",
    "design_depth",
    "completion_gate",
}


@dataclass(frozen=True)
class ValidationResult:
    tranche_count: int
    ready_tranche_count: int
    superseded_count: int = 0


def validate_manifest(
    *,
    root: Path,
    project_brief_path: str,
    project_roadmap_path: str,
    tranche_manifest_path: str,
) -> ValidationResult:
    root = root.resolve()
    project_brief_resolved = _require_relpath(root, project_brief_path, "project_brief_path")
    if not project_brief_resolved.is_file():
        raise ValueError(f"Project brief target does not exist: {project_brief_path}")

    project_roadmap_resolved = _require_under(root, project_roadmap_path, "project_roadmap_path", "docs/plans")
    if not project_roadmap_resolved.is_file():
        raise ValueError(f"Project roadmap target does not exist: {project_roadmap_path}")

    manifest_resolved = _require_under(root, tranche_manifest_path, "tranche_manifest_path", "state")
    manifest = json.loads(manifest_resolved.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("Tranche manifest must be a JSON object")
    if manifest.get("project_brief_path") != project_brief_path:
        raise ValueError("Manifest project_brief_path must match the roadmap input")
    if manifest.get("project_roadmap_path") != project_roadmap_path:
        raise ValueError("Manifest project_roadmap_path must match the roadmap output")

    project_id = manifest.get("project_id")
    tranches = manifest.get("tranches")
    if not isinstance(project_id, str) or not project_id:
        raise ValueError("Manifest missing non-empty project_id")
    if not isinstance(tranches, list) or not tranches:
        raise ValueError("Manifest tranches must be a non-empty array")

    tranche_ids: list[str] = []
    prereq_map: dict[str, list[str]] = {}
    tranche_statuses: dict[str, str] = {}
    for index, tranche in enumerate(tranches):
        if not isinstance(tranche, dict):
            raise ValueError(f"Tranche {index} must be a JSON object")
        missing = sorted(REQUIRED_TRANCHE_FIELDS - set(tranche))
        if missing:
            raise ValueError(f"Tranche {index} missing required fields: {', '.join(missing)}")

        tranche_id = _require_string(tranche["tranche_id"], f"tranches[{index}].tranche_id")
        if tranche_id in tranche_ids:
            raise ValueError(f"Duplicate tranche_id: {tranche_id}")
        tranche_ids.append(tranche_id)

        for field in [
            "title",
            "brief_path",
            "design_target_path",
            "design_review_report_target_path",
            "plan_target_path",
            "plan_review_report_target_path",
            "execution_report_target_path",
            "implementation_review_report_target_path",
            "item_summary_target_path",
            "status",
            "design_depth",
            "completion_gate",
        ]:
            _require_string(tranche[field], f"{tranche_id}.{field}")

        _require_allowed(tranche["status"], f"{tranche_id}.status", ALLOWED_STATUSES)
        _require_allowed(tranche["design_depth"], f"{tranche_id}.design_depth", ALLOWED_DESIGN_DEPTHS)
        _require_allowed(tranche["completion_gate"], f"{tranche_id}.completion_gate", ALLOWED_COMPLETION_GATES)
        tranche_statuses[tranche_id] = tranche["status"]

        prerequisites = tranche["prerequisites"]
        if not isinstance(prerequisites, list) or not all(isinstance(item, str) and item for item in prerequisites):
            raise ValueError(f"Tranche {tranche_id} prerequisites must be an array of strings")
        prereq_map[tranche_id] = list(prerequisites)

        brief_path = _require_relpath(root, tranche["brief_path"], f"{tranche_id}.brief_path")
        if not brief_path.is_file():
            raise ValueError(f"Tranche brief_path target does not exist: {tranche['brief_path']}")
        _require_under(root, tranche["design_target_path"], f"{tranche_id}.design_target_path", "docs/plans")
        _require_under(
            root,
            tranche["design_review_report_target_path"],
            f"{tranche_id}.design_review_report_target_path",
            "artifacts/review",
        )
        _require_under(root, tranche["plan_target_path"], f"{tranche_id}.plan_target_path", "docs/plans")
        _require_under(
            root,
            tranche["plan_review_report_target_path"],
            f"{tranche_id}.plan_review_report_target_path",
            "artifacts/review",
        )
        _require_under(
            root,
            tranche["execution_report_target_path"],
            f"{tranche_id}.execution_report_target_path",
            "artifacts/work",
        )
        _require_under(
            root,
            tranche["implementation_review_report_target_path"],
            f"{tranche_id}.implementation_review_report_target_path",
            "artifacts/review",
        )
        _require_under(
            root,
            tranche["item_summary_target_path"],
            f"{tranche_id}.item_summary_target_path",
            "artifacts/work",
        )

    known_ids = set(tranche_ids)
    for tranche_id, prerequisites in prereq_map.items():
        unknown = [item for item in prerequisites if item not in known_ids]
        if unknown:
            raise ValueError(f"Tranche {tranche_id} has unknown prerequisites: {', '.join(unknown)}")

    _validate_acyclic_prerequisites(tranche_ids, prereq_map)
    ready_count = sum(
        1
        for tranche_id, prerequisites in prereq_map.items()
        if tranche_statuses[tranche_id] == "pending"
        and all(tranche_statuses[prereq] in COMPLETED_STATUSES for prereq in prerequisites)
    )
    superseded_count = sum(1 for status in tranche_statuses.values() if status == "superseded")
    return ValidationResult(
        tranche_count=len(tranches),
        ready_tranche_count=ready_count,
        superseded_count=superseded_count,
    )


def read_pointer(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _require_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _require_allowed(value: Any, field: str, allowed: set[str]) -> None:
    text = _require_string(value, field)
    if text not in allowed:
        raise ValueError(f"{field} must be one of {sorted(allowed)}: {text}")


def _require_relpath(root: Path, value: Any, field: str) -> Path:
    rel = _require_string(value, field)
    resolved = (root / rel).resolve()
    if not resolved.is_relative_to(root):
        raise ValueError(f"{field} escapes workspace: {rel}")
    return resolved


def _require_under(root: Path, value: Any, field: str, under: str) -> Path:
    resolved = _require_relpath(root, value, field)
    allowed_root = (root / under).resolve()
    if not resolved.is_relative_to(allowed_root):
        raise ValueError(f"{field} must be under {under}: {value}")
    return resolved


def _validate_acyclic_prerequisites(tranche_ids: list[str], prereq_map: dict[str, list[str]]) -> None:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(tranche_id: str) -> None:
        if tranche_id in visited:
            return
        if tranche_id in visiting:
            raise ValueError(f"Tranche prerequisites contain a cycle at {tranche_id}")
        visiting.add(tranche_id)
        for prereq in prereq_map[tranche_id]:
            visit(prereq)
        visiting.remove(tranche_id)
        visited.add(tranche_id)

    for tranche_id in tranche_ids:
        visit(tranche_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a major-project tranche manifest.")
    parser.add_argument("--project-brief-path", required=True)
    parser.add_argument("--project-roadmap-pointer", type=Path, required=True)
    parser.add_argument("--tranche-manifest-pointer", type=Path, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()

    project_roadmap_path = read_pointer(args.project_roadmap_pointer)
    tranche_manifest_path = read_pointer(args.tranche_manifest_pointer)
    result = validate_manifest(
        root=args.root,
        project_brief_path=args.project_brief_path,
        project_roadmap_path=project_roadmap_path,
        tranche_manifest_path=tranche_manifest_path,
    )

    args.state_root.mkdir(parents=True, exist_ok=True)
    (args.state_root / "validated_tranche_count.txt").write_text(
        f"{result.tranche_count}\n",
        encoding="utf-8",
    )
    (args.state_root / "ready_tranche_count.txt").write_text(
        f"{result.ready_tranche_count}\n",
        encoding="utf-8",
    )
    (args.state_root / "superseded_tranche_count.txt").write_text(
        f"{result.superseded_count}\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
