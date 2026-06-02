#!/usr/bin/env python3
"""Materialize a fresh design-gap draft bundle for blocked recovery retry."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_relpath(value: str, *, under: str, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).exists():
        raise SystemExit(f"Required path does not exist: {value}")
    return path


def _repo_relpath(path: Path) -> str:
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"Path escapes repo root: {path}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _find_previous_bundle(drain_state_root: Path, design_gap_id: str) -> dict[str, Any]:
    candidates = [
        *sorted(drain_state_root.glob("iterations/*/design-gap-architect/architecture-validation.json")),
        *sorted(drain_state_root.glob("**/architecture-validation.json")),
    ]
    for path in candidates:
        payload = _load_json(path)
        if payload.get("architecture_validation_status") == "VALID" and payload.get("work_item_id") == design_gap_id:
            return payload
    raise SystemExit(f"No prior VALID architecture bundle found for recovered design gap: {design_gap_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-bundle-path", required=True)
    parser.add_argument("--drain-state-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    recovery = _load_json(REPO_ROOT / _safe_relpath(args.recovery_bundle_path, under="state", must_exist=True))
    drain_state_root = REPO_ROOT / _safe_relpath(args.drain_state_root, under="state", must_exist=True)
    output_rel = _safe_relpath(args.output, under="state", must_exist=False)
    design_gap_id = str(recovery.get("design_gap_id") or "").strip()
    if not design_gap_id:
        raise SystemExit("Recovery bundle missing design_gap_id")

    previous = _find_previous_bundle(drain_state_root, design_gap_id)
    architecture_path = _safe_relpath(str(recovery.get("architecture_path") or ""), under="docs/plans", must_exist=True)
    plan_path = _safe_relpath(str(recovery.get("plan_path") or ""), under="docs/plans", must_exist=False)
    context_path = _safe_relpath(str(previous.get("work_item_context_path") or ""), under="state", must_exist=True)
    checks_path = _safe_relpath(str(previous.get("check_commands_path") or ""), under="state", must_exist=True)

    checks = json.loads((REPO_ROOT / checks_path).read_text(encoding="utf-8"))
    if not isinstance(checks, list) or not [str(item).strip() for item in checks if str(item).strip()]:
        raise SystemExit(f"Recovered design gap has invalid check commands: {checks_path}")

    output_path = REPO_ROOT / output_rel
    _write_json(
        output_path,
        {
            "draft_status": "DRAFTED",
            "design_gap_id": design_gap_id,
            "architecture_path": architecture_path.as_posix(),
            "work_item_context_path": context_path.as_posix(),
            "check_commands_path": checks_path.as_posix(),
            "plan_target_path": plan_path.as_posix(),
            "summary": str(recovery.get("recovery_reason") or previous.get("summary") or "Recovered design gap."),
            "draft_bundle_path": _repo_relpath(output_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
