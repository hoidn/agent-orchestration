#!/usr/bin/env python3
"""Detect a prior blocked design gap that should start recovery."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _candidate_progress_paths(artifact_work_root: Path, design_gap_id: str) -> list[Path]:
    return [
        artifact_work_root / "design-gaps" / design_gap_id / "progress_report.md",
        artifact_work_root / design_gap_id / "progress_report.md",
    ]


def _find_progress_report(artifact_work_root: Path, design_gap_id: str) -> Path | None:
    for path in _candidate_progress_paths(artifact_work_root, design_gap_id):
        if path.is_file():
            return path
    return None


def _gap_design_paths(architecture_index_root: Path, design_gap_id: str) -> tuple[str, str]:
    gap_root = architecture_index_root / design_gap_id
    return (
        (gap_root / "implementation_architecture.md").as_posix(),
        (gap_root / "execution_plan.md").as_posix(),
    )


def _recovery_payload(
    run_state_path: Path,
    artifact_work_root: Path,
    architecture_index_root: Path,
    progress_copy_path: Path,
    architecture_copy_path: Path,
    plan_copy_path: Path,
) -> dict[str, str]:
    state = _load_json(run_state_path)
    blocked = state.get("blocked_design_gaps") or {}
    for design_gap_id in sorted(blocked):
        entry = blocked.get(design_gap_id) or {}
        if entry.get("reason") != "implementation_blocked":
            continue
        progress_path = _find_progress_report(artifact_work_root, design_gap_id)
        if progress_path is None:
            continue
        progress_copy_path.parent.mkdir(parents=True, exist_ok=True)
        progress_copy_path.write_text(progress_path.read_text(encoding="utf-8"), encoding="utf-8")
        blocker_class = str(entry.get("blocker_class") or "").strip()
        if not blocker_class:
            progress_text = progress_path.read_text(encoding="utf-8")
            blocker_class = "roadmap_conflict" if "roadmap_conflict" in progress_text else "unknown"
        architecture_path, plan_path = _gap_design_paths(architecture_index_root, design_gap_id)
        architecture = Path(architecture_path)
        plan = Path(plan_path)
        if architecture.is_file():
            architecture_copy_path.write_text(architecture.read_text(encoding="utf-8"), encoding="utf-8")
        if plan.is_file():
            plan_copy_path.write_text(plan.read_text(encoding="utf-8"), encoding="utf-8")
        return {
            "recovery_status": "RECOVER_BLOCKED_DESIGN_GAP",
            "design_gap_id": design_gap_id,
            "progress_report_path": progress_path.as_posix(),
            "architecture_path": architecture_path,
            "plan_path": plan_path,
            "architecture_copy_path": architecture_copy_path.as_posix(),
            "plan_copy_path": plan_copy_path.as_posix(),
            "blocker_class": blocker_class,
            "block_reason": "implementation_blocked",
        }
    return {
        "recovery_status": "NONE",
        "design_gap_id": "",
        "progress_report_path": "",
        "architecture_path": "",
        "plan_path": "",
        "architecture_copy_path": "",
        "plan_copy_path": "",
        "blocker_class": "",
        "block_reason": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--architecture-index-root", default="")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    progress_copy_path = output.with_name("prior-blocked-progress-report.md")
    architecture_copy_path = output.with_name("prior-blocked-gap-architecture.md")
    plan_copy_path = output.with_name("prior-blocked-gap-execution-plan.md")
    architecture_index_root = Path(args.architecture_index_root or "docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps")
    payload = _recovery_payload(
        Path(args.run_state_path),
        Path(args.artifact_work_root),
        architecture_index_root,
        progress_copy_path,
        architecture_copy_path,
        plan_copy_path,
    )
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
