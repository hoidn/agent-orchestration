#!/usr/bin/env python3
"""Prepare per-iteration state roots for the Lisp frontend drain."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


REPO_ROOT = Path.cwd()


def _safe_relpath(value: str, *, under: str) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    return path


def _remove_path(path: Path) -> None:
    if path.is_symlink():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _reset_stale_iteration_outputs(iteration_root: Path, payload: dict[str, str]) -> None:
    for key in (
        "selector_state_root",
        "prerequisite_selector_state_root",
        "design_gap_architect_state_root",
        "backlog_work_item_state_root",
        "design_gap_work_item_state_root",
        "done_review_state_root",
    ):
        _remove_path(REPO_ROOT / payload[key])
    for name in (
        "blocked-recovery.json",
        "normal-drain-status.txt",
        "prerequisite-recovery-drain-status.txt",
        "blocked-recovery-drain-status.txt",
        "drain-status.txt",
        "selector-blocked-placeholder-path.txt",
        "blocked-progress-report.md",
        "blocked-gap-architecture.md",
        "blocked-gap-execution-plan.md",
        "blocked-recovery-decision.json",
        "blocked-design-revision-report.json",
        "blocked-design-revision-review-target-path.txt",
        "blocked-design-revision-review-decision.txt",
        "blocked-design-revision-review-report-path.txt",
        "blocked-design-revision-loop-decision.txt",
        "blocked-recovery-summary-path.txt",
        "recovered-retry-availability.json",
    ):
        _remove_path(REPO_ROOT / iteration_root / name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--drain-state-root", required=True)
    parser.add_argument("--iteration", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    drain_root = _safe_relpath(args.drain_state_root, under="state")
    try:
        iteration = int(str(args.iteration))
    except ValueError as exc:
        raise SystemExit(f"Iteration must be an integer: {args.iteration}") from exc
    if iteration < 0:
        raise SystemExit(f"Iteration must be non-negative: {iteration}")

    iteration_root = drain_root / "iterations" / str(iteration)
    payload = {
        "iteration_state_root": iteration_root.as_posix(),
        "selector_state_root": (iteration_root / "selector").as_posix(),
        "prerequisite_selector_state_root": (iteration_root / "prerequisite-selector").as_posix(),
        "design_gap_architect_state_root": (iteration_root / "design-gap-architect").as_posix(),
        "backlog_work_item_state_root": (iteration_root / "backlog-work-item").as_posix(),
        "design_gap_work_item_state_root": (iteration_root / "design-gap-work-item").as_posix(),
        "done_review_state_root": (iteration_root / "done-review").as_posix(),
        "done_review_design_gap_architect_state_root": (
            iteration_root / "done-review" / "design-gap-architect"
        ).as_posix(),
        "done_review_design_gap_work_item_state_root": (
            iteration_root / "done-review" / "design-gap-work-item"
        ).as_posix(),
    }
    _reset_stale_iteration_outputs(iteration_root, payload)
    for key in (
        "selector_state_root",
        "prerequisite_selector_state_root",
        "design_gap_architect_state_root",
        "backlog_work_item_state_root",
        "design_gap_work_item_state_root",
        "done_review_state_root",
        "done_review_design_gap_architect_state_root",
        "done_review_design_gap_work_item_state_root",
    ):
        (REPO_ROOT / payload[key]).mkdir(parents=True, exist_ok=True)

    output_rel = _safe_relpath(args.output, under="state")
    output_path = REPO_ROOT / output_rel
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
