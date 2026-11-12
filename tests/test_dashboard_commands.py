"""Tests for copyable dashboard operator commands."""

from __future__ import annotations

from pathlib import Path

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.models import RunRecord, WorkspaceRecord


def _record(
    workspace: Path,
    run_dir_id: str,
    *,
    state_run_id: str | None = None,
    runs_root: Path | None = None,
    state: dict | None = None,
) -> RunRecord:
    """A scanned run as `RunScanner` reports it: resolved workspace, scanned run directory."""
    root = workspace.resolve()
    run_root = (runs_root or root / ".orchestrate" / "runs") / run_dir_id
    return RunRecord(
        workspace=WorkspaceRecord(id="w0", root=root, label=root.name),
        run_dir_id=run_dir_id,
        run_root=run_root,
        state_path=run_root / "state.json",
        state=state or {"run_id": state_run_id or run_dir_id, "status": "completed"},
        state_run_id=state_run_id or run_dir_id,
    )


def test_command_builder_uses_scanned_workspace_and_run_directory_id(tmp_path: Path):
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()

    commands = CommandBuilder().build(_record(workspace, "run 1"))

    assert commands.report is not None
    assert commands.resume is not None
    assert commands.report.cwd == workspace.resolve()
    assert commands.report.argv == ["orchestrate", "report", "--run-id", "run 1"]
    assert commands.resume.argv == ["orchestrate", "resume", "run 1"]
    assert commands.report.shell_text == (
        f"cd {str(workspace.resolve())!r} && orchestrate report --run-id 'run 1'"
    )


def test_command_builder_suppresses_resume_on_run_id_mismatch(tmp_path: Path):
    commands = CommandBuilder().build(_record(tmp_path, "dir-run", state_run_id="state-run"))

    assert commands.report is not None
    assert commands.resume is None
    assert any("state.run_id mismatch" in warning for warning in commands.warnings)


def test_command_builder_adds_non_default_runs_root_flags(tmp_path: Path):
    workspace = tmp_path / "workspace"
    custom_runs = workspace.resolve() / "custom-runs"

    commands = CommandBuilder().build(_record(workspace, "run1", runs_root=custom_runs))

    assert commands.report is not None
    assert commands.resume is not None
    assert commands.report.argv == [
        "orchestrate",
        "report",
        "--run-id",
        "run1",
        "--runs-root",
        "custom-runs",
    ]
    assert commands.resume.argv == [
        "orchestrate",
        "resume",
        "run1",
        "--state-dir",
        "custom-runs",
    ]


def test_command_builder_never_uses_state_provided_run_root(tmp_path: Path):
    state = {"run_id": "run1", "run_root": "/tmp/outside", "status": "completed"}

    commands = CommandBuilder().build(_record(tmp_path, "run1", state=state))

    assert "/tmp/outside" not in commands.report.shell_text
    assert commands.tmux == []
