"""Workspace and run-directory scanning for the local dashboard."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from orchestrator.dashboard.models import RunRecord, ScanResult, WorkspaceRecord


class RunScanner:
    """Scan explicit workspace roots for `.orchestrate/runs/*/state.json` files."""

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
                state_path = run_root / "state.json"
                if not state_path.exists() and not state_path.is_symlink():
                    continue
                runs.append(self._read_run(workspace, run_root, state_path))
        return ScanResult(workspaces=list(self.workspaces), runs=runs, errors=errors)

    def _read_run(self, workspace: WorkspaceRecord, run_root: Path, state_path: Path) -> RunRecord:
        run_dir_id = run_root.name
        warnings: list[str] = []
        try:
            resolved_scanned_run_root = run_root.resolve(strict=True)
        except OSError:
            resolved_scanned_run_root = run_root.resolve(strict=False)
        try:
            resolved_scanned_run_root.relative_to(workspace.root)
        except ValueError:
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=run_root,
                state_path=state_path,
                read_error=f"run root escapes workspace: {run_root}",
            )

        try:
            resolved_state_path = state_path.resolve(strict=True)
        except OSError as exc:
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=resolved_scanned_run_root,
                state_path=state_path,
                read_error=str(exc),
            )
        resolved_run_root = resolved_state_path.parent
        try:
            resolved_run_root.relative_to(workspace.root)
        except ValueError:
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=resolved_scanned_run_root,
                state_path=state_path,
                read_error=f"state.json resolves outside workspace: {state_path}",
            )

        try:
            raw_state = resolved_state_path.read_text(encoding="utf-8")
        except OSError as exc:
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=resolved_run_root,
                state_path=resolved_state_path,
                read_error=str(exc),
            )

        try:
            state = json.loads(raw_state)
        except json.JSONDecodeError as exc:
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=resolved_run_root,
                state_path=resolved_state_path,
                parse_error=str(exc),
            )

        if not isinstance(state, dict):
            return RunRecord(
                workspace=workspace,
                run_dir_id=run_dir_id,
                run_root=resolved_run_root,
                state_path=resolved_state_path,
                parse_error="state.json must contain a JSON object",
            )

        state_run_id = state.get("run_id") if isinstance(state.get("run_id"), str) else None
        if state_run_id and state_run_id != run_dir_id:
            warnings.append(
                f"state.run_id {state_run_id!r} differs from run directory {run_dir_id!r}"
            )
        return RunRecord(
            workspace=workspace,
            run_dir_id=run_dir_id,
            run_root=resolved_run_root,
            state_path=resolved_state_path,
            state=state,
            state_run_id=state_run_id,
            warnings=warnings,
        )
