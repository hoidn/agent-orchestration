#!/usr/bin/env python3
"""Detect a prior blocked design gap that should start with target-design revision."""

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


def _recovery_payload(run_state_path: Path, artifact_work_root: Path, progress_copy_path: Path) -> dict[str, str]:
    state = _load_json(run_state_path)
    blocked = state.get("blocked_design_gaps") or {}
    for design_gap_id in sorted(blocked):
        entry = blocked.get(design_gap_id) or {}
        if entry.get("reason") != "implementation_blocked":
            continue
        progress_path = _find_progress_report(artifact_work_root, design_gap_id)
        if progress_path is None:
            continue
        progress_text = progress_path.read_text(encoding="utf-8")
        if "roadmap_conflict" not in progress_text:
            continue
        progress_copy_path.parent.mkdir(parents=True, exist_ok=True)
        progress_copy_path.write_text(progress_text, encoding="utf-8")
        return {
            "recovery_status": "RECOVER_BLOCKED_DESIGN_GAP",
            "design_gap_id": design_gap_id,
            "progress_report_path": progress_path.as_posix(),
            "blocker_class": "roadmap_conflict",
            "block_reason": "implementation_blocked",
        }
    return {
        "recovery_status": "NONE",
        "design_gap_id": "",
        "progress_report_path": "",
        "blocker_class": "",
        "block_reason": "",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-state-path", required=True)
    parser.add_argument("--artifact-work-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    progress_copy_path = output.with_name("prior-blocked-progress-report.md")
    payload = _recovery_payload(Path(args.run_state_path), Path(args.artifact_work_root), progress_copy_path)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
