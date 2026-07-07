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


def _find_previous_bundle(drain_state_root: Path, design_gap_id: str) -> dict[str, Any] | None:
    candidates = [
        *sorted(drain_state_root.glob("iterations/*/design-gap-architect/architecture-validation.json")),
        *sorted(drain_state_root.glob("**/architecture-validation.json")),
    ]
    for path in candidates:
        payload = _load_json(path)
        if (
            payload.get("architecture_validation_status") == "VALID"
            and payload.get("work_item_id") == design_gap_id
            and _bundle_input_paths_exist(payload)
        ):
            return payload
    return None


def _bundle_input_paths_exist(payload: dict[str, Any]) -> bool:
    try:
        context_path = _safe_relpath(str(payload.get("work_item_context_path") or ""), under="state", must_exist=True)
        checks_path = _safe_relpath(str(payload.get("check_commands_path") or ""), under="state", must_exist=True)
    except SystemExit:
        return False
    try:
        checks = json.loads((REPO_ROOT / checks_path).read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False
    return (REPO_ROOT / context_path).is_file() and isinstance(checks, list) and any(
        str(item).strip() for item in checks
    )


def _materialize_retry_bundle(
    *,
    design_gap_id: str,
    recovery: dict[str, Any],
    architecture_path: Path,
    plan_path: Path,
    output_path: Path,
    previous: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    context_path = output_path.with_name("recovered-work-item-context.md")
    checks_path = output_path.with_name("recovered-check-commands.json")
    progress_report_rel = str(recovery.get("progress_report_path") or "").strip()
    progress_report_file = None
    if progress_report_rel:
        try:
            progress_report_path = _safe_relpath(progress_report_rel, under="artifacts/work")
        except SystemExit:
            progress_report_path = _safe_relpath(progress_report_rel, under="state")
        progress_report_file = REPO_ROOT / progress_report_path
    prior_progress_lines: list[str] = []
    if progress_report_file is not None and progress_report_file.is_file():
        prior_progress_lines = [
            "## Prior Attempt Progress Report",
            "",
            progress_report_file.read_text(encoding="utf-8").rstrip(),
            "",
        ]
    context_path.write_text(
        "\n".join(
            [
                f"# Recovered Design Gap Retry: {design_gap_id}",
                "",
                "The prior architecture-validation bundle for this recovered retry was not available.",
                "This retry bundle was reconstructed from durable blocked recovery state.",
                "",
                "## Recovery State",
                "",
                f"- recovery_route: `{str(recovery.get('recovery_route') or '').strip()}`",
                f"- recovery_status: `{str(recovery.get('recovery_status') or '').strip()}`",
                f"- recovery_reason: `{str(recovery.get('recovery_reason') or '').strip()}`",
                f"- recovery_event_id: `{str(recovery.get('recovery_event_id') or '').strip()}`",
                "",
                "## Durable Inputs",
                "",
                f"- architecture_path: `{architecture_path.as_posix()}`",
                f"- plan_target_path: `{plan_path.as_posix()}`",
                f"- progress_report_path: `{progress_report_rel}`",
                "",
                *prior_progress_lines,
                "## Runtime Artifacts",
                "",
                "Recovered retry context and check-command files are runtime artifacts.",
                "Do not copy their generated `state/...` paths into durable design or plan documents.",
                "If a durable document needs to mention them, describe the artifact role instead.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    checks = [
        f"test -f {architecture_path.as_posix()}",
        "python -m compileall orchestrator/workflow_lisp",
    ]
    if (REPO_ROOT / plan_path).exists():
        checks.insert(1, f"test -f {plan_path.as_posix()}")
    _write_json(checks_path, checks)
    return {
        "work_item_context_path": _repo_relpath(context_path),
        "check_commands_path": _repo_relpath(checks_path),
        "summary": (
            "Recovered design gap retry reconstructed from durable blocked state "
            + ((
                "with regenerated retry artifacts rather than reusing prior generated "
                "architecture-validation paths."
            )
                if previous is not None
                else "because the prior architecture-validation bundle was unavailable."
            )
        ),
    }


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

    architecture_path = _safe_relpath(str(recovery.get("architecture_path") or ""), under="docs/plans", must_exist=True)
    plan_path = _safe_relpath(str(recovery.get("plan_path") or ""), under="docs/plans", must_exist=False)
    previous = _find_previous_bundle(drain_state_root, design_gap_id)
    previous = _materialize_retry_bundle(
        design_gap_id=design_gap_id,
        recovery=recovery,
        architecture_path=architecture_path,
        plan_path=plan_path,
        output_path=REPO_ROOT / output_rel,
        previous=previous,
    )
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
            "summary": str(previous.get("summary") or recovery.get("recovery_reason") or "Recovered design gap."),
            "draft_bundle_path": _repo_relpath(output_path),
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
