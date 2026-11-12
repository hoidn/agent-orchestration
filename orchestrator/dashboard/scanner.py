"""Workspace and run-directory scanning for the local dashboard."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from orchestrator.dashboard.attempt_files import utf8_name
from orchestrator.dashboard.models import RunRecord, ScanResult, WorkspaceRecord
from orchestrator.workflow.evaluated.views import has_evaluated_authority, load_evaluated_view


class RunScanner:
    """Scan explicit workspace roots for run directories under `.orchestrate/runs/`."""

    def __init__(self, workspace_roots: Iterable[str | Path]) -> None:
        self.workspaces = self._resolve_workspaces(workspace_roots)

    def _resolve_workspaces(self, roots: Iterable[str | Path]) -> list[WorkspaceRecord]:
        workspaces: list[WorkspaceRecord] = []
        seen: set[Path] = set()
        for root in roots:
            raw_path = Path(root).expanduser()
            try:
                resolved = raw_path.resolve(strict=True)
            except OSError as exc:
                raise ValueError(f"workspace is not a directory: {raw_path}") from exc
            if not resolved.is_dir():
                raise ValueError(f"workspace is not a directory: {raw_path}")
            if resolved in seen:
                continue
            seen.add(resolved)
            workspaces.append(
                WorkspaceRecord(
                    id=f"w{len(workspaces)}",
                    root=resolved,
                    label=resolved.name or str(resolved),
                )
            )
        if not workspaces:
            raise ValueError("at least one workspace is required")
        return workspaces

    def scan(self) -> ScanResult:
        runs: list[RunRecord] = []
        errors: list[str] = []
        for workspace in self.workspaces:
            runs_root = workspace.root / ".orchestrate" / "runs"
            if not runs_root.exists():
                continue
            try:
                run_dirs = sorted(path for path in runs_root.iterdir() if path.is_dir())
            except OSError as exc:
                errors.append(f"failed to scan {runs_root}: {exc}")
                continue
            for run_root in run_dirs:
                if not utf8_name(run_root.name):
                    shown = os.fsencode(run_root.name).decode("utf-8", "backslashreplace")
                    errors.append(f"run directory {shown} in {runs_root} has a name that is not UTF-8; not listed")
                    continue
                state_path = run_root / "state.json"
                run = self._read_run(workspace, run_root, state_path)
                if run is not None:
                    runs.append(run)
        return ScanResult(workspaces=list(self.workspaces), runs=runs, errors=errors)

    def _read_run(self, workspace: WorkspaceRecord, run_root: Path, state_path: Path) -> RunRecord | None:
        """An evaluated run, a retired run (a `state.json` entry and no evaluated authority), or nothing.

        A retired run's `state.json` is never opened beyond the view-hint check in
        `has_evaluated_authority` (regular file, no symlink follow, non-blocking).
        """
        try:
            resolved_root = run_root.resolve(strict=True)
            resolved_root.relative_to(workspace.root)
        except ValueError:
            return RunRecord(workspace, run_root.name, run_root, state_path,
                             read_error=f"run root escapes workspace: {run_root}")
        except (OSError, RuntimeError) as exc:
            return RunRecord(workspace, run_root.name, run_root, state_path, read_error=str(exc))
        if has_evaluated_authority(resolved_root):
            return self._read_evaluated_run(workspace, run_root.name, resolved_root, state_path)
        if not state_path.exists() and not state_path.is_symlink():
            return None
        return RunRecord(workspace, run_root.name, resolved_root, state_path, retired=True)

    def _read_evaluated_run(self, workspace, run_dir_id, run_root, state_path):
        try:
            state = load_evaluated_view(run_root)
        except (OSError, ValueError) as exc:
            return RunRecord(workspace, run_dir_id, run_root, state_path,
                             parse_error=f"{getattr(exc, 'code', 'memo_inconsistent')}: {exc}")
        return RunRecord(workspace, run_dir_id, run_root, state_path,
                         state=state, state_run_id=state["run_id"])

