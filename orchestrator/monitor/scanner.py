"""Workspace scanning for workflow monitor runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping

from orchestrator.workflow.evaluated.views import has_evaluated_authority, load_evaluated_view

from .models import MonitorConfig, MonitorRun, MonitorWorkspace
from .process import read_process_metadata


def scan_monitor_runs(config: MonitorConfig) -> list[MonitorRun]:
    """Scan configured workspaces for orchestrator run states."""

    runs: list[MonitorRun] = []
    for workspace in config.workspaces:
        runs.extend(_scan_workspace(workspace))
    return runs


def _scan_workspace(workspace: MonitorWorkspace) -> list[MonitorRun]:
    root = workspace.path.expanduser()
    runs_root = root / ".orchestrate" / "runs"
    if not runs_root.exists():
        return []
    try:
        run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
    except OSError as exc:
        return [
            MonitorRun(
                workspace=workspace,
                run_dir_id=runs_root.name,
                run_root=runs_root,
                state_path=runs_root / "state.json",
                read_error=str(exc),
            )
        ]

    runs: list[MonitorRun] = []
    for run_root in run_dirs:
        state_path = run_root / "state.json"
        run = _read_run(workspace, run_root, state_path)
        if run is not None:
            runs.append(run)
    return runs


def _read_run(workspace: MonitorWorkspace, run_root: Path, state_path: Path) -> MonitorRun | None:
    try:
        resolved = run_root.resolve(strict=True)
        resolved.relative_to(workspace.path.expanduser().resolve(strict=False))
    except (OSError, ValueError, RuntimeError) as exc:
        return MonitorRun(workspace, run_root.name, run_root, state_path,
                          read_error=f"run root is unsafe or escapes workspace: {exc}")
    if has_evaluated_authority(resolved):
        return _read_evaluated_run(workspace, run_root.name, resolved, state_path)
    if not state_path.exists() and not state_path.is_symlink():
        return None
    return _read_legacy_run(workspace, run_root, state_path)


def _read_evaluated_run(workspace, run_dir_id, run_root, state_path):
    try:
        state = load_evaluated_view(run_root)
    except (OSError, ValueError) as exc:
        return MonitorRun(workspace, run_dir_id, run_root, state_path,
                          read_error=f"{getattr(exc, 'code', 'memo_inconsistent')}: {exc}")
    return MonitorRun(workspace, run_dir_id, run_root, state_path, state=state)


def _read_legacy_run(workspace: MonitorWorkspace, run_root: Path, state_path: Path) -> MonitorRun:
    try:
        resolved_run_root = run_root.resolve(strict=False)
        resolved_state_path = state_path.resolve(strict=True)
        resolved_run_root.relative_to(workspace.path.expanduser().resolve(strict=False))
        resolved_state_path.relative_to(workspace.path.expanduser().resolve(strict=False))
    except OSError as exc:
        return _error_run(workspace, run_root, state_path, str(exc))
    except ValueError:
        return _error_run(workspace, run_root, state_path, "run state escapes workspace")

    try:
        raw = json.loads(resolved_state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _error_run(workspace, resolved_run_root, resolved_state_path, str(exc))

    if not isinstance(raw, Mapping):
        return _error_run(workspace, resolved_run_root, resolved_state_path, "state.json must be an object")

    return MonitorRun(
        workspace=workspace,
        run_dir_id=run_root.name,
        run_root=resolved_run_root,
        state_path=resolved_state_path,
        state=raw,
        process=read_process_metadata(resolved_run_root),
    )


def _error_run(
    workspace: MonitorWorkspace,
    run_root: Path,
    state_path: Path,
    message: str,
) -> MonitorRun:
    return MonitorRun(
        workspace=workspace,
        run_dir_id=run_root.name,
        run_root=run_root,
        state_path=state_path,
        read_error=message,
        process=read_process_metadata(run_root),
    )
