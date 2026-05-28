#!/usr/bin/env python3
"""Normalize Lisp frontend backlog/design-gap selections into work-item inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path.cwd()
DEFAULT_ARTIFACT_WORK_ROOT = "artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN"
DEFAULT_ARTIFACT_CHECKS_ROOT = "artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN"
DEFAULT_ARTIFACT_REVIEW_ROOT = "artifacts/review/LISP-FRONTEND-AUTONOMOUS-DRAIN"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_relpath(value: str, *, under: str | None = None, must_exist: bool = False) -> Path:
    path = Path(str(value).strip())
    if path.is_absolute() or ".." in path.parts or not str(path):
        raise SystemExit(f"Unsafe relative path: {value}")
    if under is not None and path.parts[: len(Path(under).parts)] != Path(under).parts:
        raise SystemExit(f"Path {value} is not under {under}")
    target = REPO_ROOT / path
    if must_exist and not target.exists():
        raise SystemExit(f"Required path does not exist: {value}")
    return path


def _repo_relpath(path: Path) -> str:
    if not path.is_absolute():
        path = REPO_ROOT / path
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError as exc:
        raise SystemExit(f"Path escapes repo root: {path}") from exc


def _parse_frontmatter_and_body(path: Path) -> tuple[dict[str, Any], str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise SystemExit(f"Missing frontmatter start fence: {path}")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise SystemExit(f"Missing frontmatter end fence: {path}")
    parsed = yaml.safe_load(text[4:end]) or {}
    if not isinstance(parsed, dict):
        raise SystemExit(f"Frontmatter must be a mapping: {path}")
    return {str(key): value for key, value in parsed.items()}, text[end + len("\n---\n") :].strip()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _normalize_checks(value: object, *, source: str) -> list[str]:
    if not isinstance(value, list):
        raise SystemExit(f"{source} must provide check_commands as a list")
    checks = [str(item).strip() for item in value if str(item).strip()]
    if not checks:
        raise SystemExit(f"{source} must provide at least one check command")
    return checks


def _lookup_manifest_entry(manifest: dict[str, Any], item_id: str, item_path: str) -> dict[str, Any]:
    items = manifest.get("items")
    if not isinstance(items, list):
        raise SystemExit("Manifest is missing items list")
    for item in items:
        if item.get("item_id") == item_id and item.get("path") == item_path:
            return item
    raise SystemExit(f"Selected item {item_id} at {item_path} is not in manifest")


def _materialize_backlog(
    selection: dict[str, Any],
    manifest: dict[str, Any],
    state_root: Path,
    artifact_work_root: Path,
    artifact_checks_root: Path,
    artifact_review_root: Path,
) -> dict[str, Any]:
    item_id = str(selection.get("selected_item_id") or "").strip()
    item_path = str(selection.get("selected_item_path") or "").strip()
    if not item_id:
        raise SystemExit("Backlog selection missing selected_item_id")
    rel_item = _safe_relpath(item_path, under="docs/backlog/active", must_exist=True)
    entry = _lookup_manifest_entry(manifest, item_id, rel_item.as_posix())
    frontmatter, body = _parse_frontmatter_and_body(REPO_ROOT / rel_item)
    checks = _normalize_checks(entry.get("check_commands") or frontmatter.get("check_commands"), source=item_id)
    plan_path = str(entry.get("plan_path") or frontmatter.get("plan_path") or "").strip()
    rel_plan = _safe_relpath(plan_path, under="docs/plans", must_exist=True)

    item_root = state_root / "items" / item_id
    item_root.mkdir(parents=True, exist_ok=True)
    checks_path = item_root / "check_commands.json"
    context_path = item_root / "work_item_context.md"
    _write_json(checks_path, checks)
    context_path.write_text(
        "\n".join(
            [
                f"# Lisp Frontend Work Item: {item_id}",
                "",
                "- source: `BACKLOG_ITEM`",
                f"- selected_item_path: `{rel_item.as_posix()}`",
                f"- seed_plan_path: `{rel_plan.as_posix()}`",
                "",
                "## Selection Rationale",
                "",
                str(selection.get("selection_rationale") or "none").strip(),
                "",
                "## Backlog Item",
                "",
                body,
                "",
            ]
        ).rstrip()
        + "\n",
        encoding="utf-8",
    )
    return {
        "work_item_source": "BACKLOG_ITEM",
        "work_item_id": item_id,
        "work_item_context_path": _repo_relpath(context_path),
        "check_commands_path": _repo_relpath(checks_path),
        "plan_target_path": rel_plan.as_posix(),
        "execution_report_target_path": (artifact_work_root / item_id / "execution_report.md").as_posix(),
        "checks_report_target_path": (artifact_checks_root / f"{item_id}-checks.json").as_posix(),
        "implementation_review_report_target_path": (
            artifact_review_root / f"{item_id}-implementation-review.md"
        ).as_posix(),
        "item_summary_target_path": (artifact_work_root / f"{item_id}-summary.json").as_posix(),
    }


def _materialize_design_gap(
    architecture_bundle_path: str,
    state_root: Path,
    artifact_work_root: Path,
    artifact_checks_root: Path,
    artifact_review_root: Path,
) -> dict[str, Any]:
    rel_bundle = _safe_relpath(architecture_bundle_path, under="state", must_exist=True)
    bundle = _load_json(REPO_ROOT / rel_bundle)
    if bundle.get("architecture_validation_status") != "VALID":
        raise SystemExit("Design-gap work item requires a VALID architecture bundle")
    item_id = str(bundle.get("work_item_id") or "").strip()
    if not item_id:
        raise SystemExit("Architecture bundle missing work_item_id")
    context_path = _safe_relpath(str(bundle.get("work_item_context_path") or ""), under="state", must_exist=True)
    checks_path = _safe_relpath(str(bundle.get("check_commands_path") or ""), under="state", must_exist=True)
    plan_path = _safe_relpath(str(bundle.get("plan_target_path") or ""), under="docs/plans", must_exist=False)
    architecture_path = _safe_relpath(str(bundle.get("architecture_path") or ""), under="docs/plans", must_exist=True)
    checks = _normalize_checks(_load_json(REPO_ROOT / checks_path), source=item_id)
    _write_json(REPO_ROOT / checks_path, checks)
    return {
        "work_item_source": "DESIGN_GAP",
        "work_item_id": item_id,
        "architecture_path": architecture_path.as_posix(),
        "work_item_context_path": context_path.as_posix(),
        "check_commands_path": checks_path.as_posix(),
        "plan_target_path": plan_path.as_posix(),
        "execution_report_target_path": (
            artifact_work_root / "design-gaps" / item_id / "execution_report.md"
        ).as_posix(),
        "checks_report_target_path": (artifact_checks_root / "design-gaps" / f"{item_id}-checks.json").as_posix(),
        "implementation_review_report_target_path": (
            artifact_review_root / "design-gaps" / f"{item_id}-implementation-review.md"
        ).as_posix(),
        "item_summary_target_path": (artifact_work_root / "design-gaps" / f"{item_id}-summary.json").as_posix(),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection-path", required=True)
    parser.add_argument("--manifest-path", required=True)
    parser.add_argument("--state-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--architecture-bundle-path", default="")
    parser.add_argument("--artifact-work-root", default=DEFAULT_ARTIFACT_WORK_ROOT)
    parser.add_argument("--artifact-checks-root", default=DEFAULT_ARTIFACT_CHECKS_ROOT)
    parser.add_argument("--artifact-review-root", default=DEFAULT_ARTIFACT_REVIEW_ROOT)
    args = parser.parse_args()

    selection = _load_json(REPO_ROOT / _safe_relpath(args.selection_path, under="state", must_exist=True))
    manifest = _load_json(REPO_ROOT / _safe_relpath(args.manifest_path, under="state", must_exist=True))
    state_root = REPO_ROOT / _safe_relpath(args.state_root, under="state", must_exist=False)
    artifact_work_root = _safe_relpath(args.artifact_work_root, under="artifacts/work", must_exist=False)
    artifact_checks_root = _safe_relpath(args.artifact_checks_root, under="artifacts/checks", must_exist=False)
    artifact_review_root = _safe_relpath(args.artifact_review_root, under="artifacts/review", must_exist=False)
    status = selection.get("selection_status")
    if status == "SELECT_BACKLOG_ITEM":
        payload = _materialize_backlog(
            selection,
            manifest,
            state_root,
            artifact_work_root,
            artifact_checks_root,
            artifact_review_root,
        )
    elif status == "DRAFT_DESIGN_GAP":
        payload = _materialize_design_gap(
            args.architecture_bundle_path,
            state_root,
            artifact_work_root,
            artifact_checks_root,
            artifact_review_root,
        )
    else:
        raise SystemExit(f"Unsupported work-item selection_status: {status}")
    item_id = str(payload["work_item_id"])
    payload.update(
        {
            "plan_phase_state_root": _repo_relpath(state_root / "plan-phase"),
            "implementation_phase_state_root": _repo_relpath(state_root / "implementation-phase"),
            "plan_review_report_target_path": (artifact_review_root / f"{item_id}-plan-review.json").as_posix(),
            "progress_report_target_path": (artifact_work_root / item_id / "progress_report.md").as_posix(),
        }
    )

    _write_json(REPO_ROOT / _safe_relpath(args.output, under="state", must_exist=False), payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
