#!/usr/bin/env python3
"""Materialize work-item inputs for a recovered blocked design gap."""

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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _find_architecture_bundle(drain_state_root: Path, design_gap_id: str) -> dict[str, Any]:
    for path in sorted(drain_state_root.glob("iterations/*/design-gap-architect/architecture-validation.json")):
        payload = _load_json(path)
        if payload.get("architecture_validation_status") == "VALID" and payload.get("work_item_id") == design_gap_id:
            return payload
    raise SystemExit(f"No prior VALID architecture bundle found for recovered design gap: {design_gap_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--recovery-bundle-path", required=True)
    parser.add_argument("--drain-state-root", required=True)
    parser.add_argument("--architecture-bundle-path", default="")
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    recovery = _load_json(REPO_ROOT / _safe_relpath(args.recovery_bundle_path, under="state", must_exist=True))
    drain_state_root = REPO_ROOT / _safe_relpath(args.drain_state_root, under="state", must_exist=True)
    state_root = REPO_ROOT / _safe_relpath(args.state_root, under="state", must_exist=False)
    output_rel = _safe_relpath(args.output, under="state", must_exist=False)
    output_path = REPO_ROOT / output_rel

    design_gap_id = str(recovery.get("design_gap_id") or "").strip()
    if not design_gap_id:
        raise SystemExit("Recovery bundle missing design_gap_id")
    architecture_path = _safe_relpath(str(recovery.get("architecture_path") or ""), under="docs/plans", must_exist=True)
    plan_path = _safe_relpath(str(recovery.get("plan_path") or ""), under="docs/plans", must_exist=False)
    if args.architecture_bundle_path:
        previous_bundle = _load_json(REPO_ROOT / _safe_relpath(args.architecture_bundle_path, under="state", must_exist=True))
        if previous_bundle.get("architecture_validation_status") != "VALID":
            raise SystemExit("Recovered design gap requires a VALID architecture bundle")
    else:
        previous_bundle = _find_architecture_bundle(drain_state_root, design_gap_id)

    context_path = _safe_relpath(str(previous_bundle.get("work_item_context_path") or ""), under="state", must_exist=True)
    checks_path = _safe_relpath(str(previous_bundle.get("check_commands_path") or ""), under="state", must_exist=True)
    checks = json.loads((REPO_ROOT / checks_path).read_text(encoding="utf-8"))
    if not isinstance(checks, list) or not [str(item).strip() for item in checks if str(item).strip()]:
        raise SystemExit(f"Recovered design gap has invalid check commands: {checks_path}")

    selection_path = state_root / "selection.json"
    manifest_path = state_root / "manifest.json"
    architecture_bundle_path = state_root / "architecture-validation.json"
    recovered_work_item_state_root = state_root / "work-item"

    _write_json(
        selection_path,
        {
            "selection_status": "DRAFT_DESIGN_GAP",
            "design_gap_id": design_gap_id,
            "selection_rationale": "Retry a recovered blocked design gap after its gap design was revised.",
        },
    )
    _write_json(manifest_path, {"items": []})
    _write_json(
        architecture_bundle_path,
        {
            "architecture_validation_status": "VALID",
            "work_item_source": "DESIGN_GAP",
            "work_item_id": design_gap_id,
            "architecture_path": architecture_path.as_posix(),
            "work_item_context_path": context_path.as_posix(),
            "check_commands_path": checks_path.as_posix(),
            "plan_target_path": plan_path.as_posix(),
            "summary": str(previous_bundle.get("summary") or "Recovered blocked design gap retry.").strip(),
            "work_item_bundle_path": _repo_relpath(architecture_bundle_path),
        },
    )
    _write_json(
        output_path,
        {
            "selection_bundle_path": _repo_relpath(selection_path),
            "manifest_path": _repo_relpath(manifest_path),
            "architecture_bundle_path": _repo_relpath(architecture_bundle_path),
            "recovered_work_item_state_root": _repo_relpath(recovered_work_item_state_root),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
