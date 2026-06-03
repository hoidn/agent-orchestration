#!/usr/bin/env python3
"""Validate a drafted Lisp frontend design-gap architecture bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REPO_ROOT = Path.cwd()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_relpath(value: str, *, under: str | None = None, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise ValueError(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise ValueError(f"Path {value} is not under {under}")
    if must_exist and not (REPO_ROOT / path).exists():
        raise ValueError(f"Required path does not exist: {value}")
    return path


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _invalid(reason: str, *, output_path: Path) -> int:
    _write_json(output_path, {"architecture_validation_status": "INVALID", "reason": reason})
    return 0


def _validate_current_target(draft: dict[str, Any], targets: dict[str, Any]) -> None:
    for field in (
        "design_gap_id",
        "architecture_path",
        "work_item_context_path",
        "check_commands_path",
        "plan_target_path",
    ):
        draft_value = str(draft.get(field) or "").strip()
        target_value = str(targets.get(field) or "").strip()
        if draft_value != target_value:
            raise ValueError(
                f"Draft field {field}={draft_value!r} does not match current architecture target {target_value!r}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--draft-bundle-path", required=True)
    parser.add_argument("--architecture-targets-path")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    try:
        draft_path = REPO_ROOT / _safe_relpath(args.draft_bundle_path, under="state", must_exist=True)
        targets_path = None
        if args.architecture_targets_path:
            targets_path = REPO_ROOT / _safe_relpath(args.architecture_targets_path, under="state", must_exist=True)
        output_rel = _safe_relpath(args.output, under="state", must_exist=False)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    output_path = REPO_ROOT / output_rel
    draft = _load_json(draft_path)

    if draft.get("draft_status") == "BLOCKED":
        _write_json(
            output_path,
            {
                "architecture_validation_status": "BLOCKED",
                "reason": str(draft.get("reason") or "Design-gap architect reported a blocker."),
            },
        )
        return 0
    if draft.get("draft_status") != "DRAFTED":
        return _invalid(f"Unsupported draft_status: {draft.get('draft_status')}", output_path=output_path)

    try:
        item_id = str(draft.get("design_gap_id") or "").strip()
        if not item_id:
            raise ValueError("Missing design_gap_id")
        architecture_path = _safe_relpath(str(draft.get("architecture_path") or ""), under="docs/plans", must_exist=True)
        context_path = _safe_relpath(str(draft.get("work_item_context_path") or ""), under="state", must_exist=True)
        checks_path = _safe_relpath(str(draft.get("check_commands_path") or ""), under="state", must_exist=True)
        plan_path = _safe_relpath(str(draft.get("plan_target_path") or ""), under="docs/plans", must_exist=False)
        checks = _load_json(REPO_ROOT / checks_path)
        if not isinstance(checks, list) or not [str(item).strip() for item in checks if str(item).strip()]:
            raise ValueError("check_commands_path must contain a non-empty JSON list")
        if targets_path is not None:
            targets = _load_json(targets_path)
            if not isinstance(targets, dict):
                raise ValueError("architecture_targets_path must contain a JSON object")
            _validate_current_target(draft, targets)
    except (ValueError, json.JSONDecodeError) as exc:
        return _invalid(str(exc), output_path=output_path)

    _write_json(
        output_path,
        {
            "architecture_validation_status": "VALID",
            "work_item_source": "DESIGN_GAP",
            "work_item_id": item_id,
            "architecture_path": architecture_path.as_posix(),
            "work_item_context_path": context_path.as_posix(),
            "check_commands_path": checks_path.as_posix(),
            "plan_target_path": plan_path.as_posix(),
            "summary": str(draft.get("summary") or "").strip(),
            "work_item_bundle_path": output_rel.as_posix(),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
