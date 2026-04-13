"""Structured copyable operator commands for dashboard runs."""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from orchestrator.dashboard.models import RunRecord


@dataclass(frozen=True)
class CommandModel:
    """One inert operator command rendered by the dashboard."""

    cwd: Path
    argv: list[str]
    shell_text: str
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CommandSet:
    """Copyable commands available for one run."""

    report: Optional[CommandModel]
    resume: Optional[CommandModel]
    tmux: list[CommandModel] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class CommandBuilder:
    """Build inert command text only from scanned workspace/run metadata."""

    def build(self, run: RunRecord) -> CommandSet:
        warnings = list(run.warnings)
        mismatch = bool(run.state_run_id and run.state_run_id != run.run_dir_id)
        if mismatch:
            warnings.append(
                f"state.run_id mismatch: using scanned run directory {run.run_dir_id!r}"
            )

        runs_root = run.run_root.parent
        default_runs_root = run.workspace.root / ".orchestrate" / "runs"
        runs_root_arg = self._runs_root_arg(runs_root, default_runs_root, run.workspace.root)

        report_argv = ["orchestrate", "report", "--run-id", run.run_dir_id]
        resume_argv = ["orchestrate", "resume", run.run_dir_id]
        if runs_root_arg is not None:
            report_argv.extend(["--runs-root", runs_root_arg])
            resume_argv.extend(["--state-dir", runs_root_arg])

        report = self._command(run.workspace.root, report_argv, warnings=[])
        resume = None if mismatch else self._command(run.workspace.root, resume_argv, warnings=[])
        return CommandSet(report=report, resume=resume, tmux=[], warnings=warnings)

    def _runs_root_arg(
        self,
        runs_root: Path,
        default_runs_root: Path,
        workspace_root: Path,
    ) -> Optional[str]:
        if runs_root.resolve(strict=False) == default_runs_root.resolve(strict=False):
            return None
        try:
            return runs_root.resolve(strict=False).relative_to(workspace_root).as_posix()
        except ValueError:
            return str(runs_root.resolve(strict=False))

    def _command(self, cwd: Path, argv: list[str], *, warnings: list[str]) -> CommandModel:
        shell_text = (
            f"cd {shlex.quote(str(cwd))} && "
            + " ".join(shlex.quote(token) for token in argv)
        )
        return CommandModel(cwd=cwd, argv=argv, shell_text=shell_text, warnings=warnings)
