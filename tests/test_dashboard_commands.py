"""Tests for copyable dashboard operator commands."""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.dashboard.commands import CommandBuilder
from orchestrator.dashboard.scanner import RunScanner


def _write_run(workspace: Path, run_dir_id: str, state_run_id: str | None = None) -> None:
    run_dir = workspace / ".orchestrate" / "runs" / run_dir_id
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": state_run_id or run_dir_id, "status": "completed"}),
        encoding="utf-8",
    )


def _scan_one(workspace: Path):
    return RunScanner([workspace]).scan().runs[0]


def test_command_builder_uses_scanned_workspace_and_run_directory_id(tmp_path: Path):
    workspace = tmp_path / "workspace with spaces"
    workspace.mkdir()
    _write_run(workspace, "run 1")

    commands = CommandBuilder().build(_scan_one(workspace))

    assert commands.report is not None
    assert commands.resume is not None
    assert commands.report.cwd == workspace.resolve()
    assert commands.report.argv == ["orchestrate", "report", "--run-id", "run 1"]
    assert commands.resume.argv == ["orchestrate", "resume", "run 1"]
    assert commands.report.shell_text == (
        f"cd {str(workspace.resolve())!r} && orchestrate report --run-id 'run 1'"
    )


def test_command_builder_suppresses_resume_on_run_id_mismatch(tmp_path: Path):
    _write_run(tmp_path, "dir-run", "state-run")

    commands = CommandBuilder().build(_scan_one(tmp_path))

    assert commands.report is not None
    assert commands.resume is None
    assert any("state.run_id mismatch" in warning for warning in commands.warnings)


def test_command_builder_adds_non_default_runs_root_flags(tmp_path: Path):
    workspace = tmp_path / "workspace"
    custom_runs = workspace / "custom-runs"
    run_dir = custom_runs / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )
    run = RunScanner([workspace])._read_run(RunScanner([workspace]).workspaces[0], run_dir, run_dir / "state.json")

    commands = CommandBuilder().build(run)

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
    run_dir = tmp_path / ".orchestrate" / "runs" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": "run1", "run_root": "/tmp/outside", "status": "completed"}),
        encoding="utf-8",
    )

    commands = CommandBuilder().build(_scan_one(tmp_path))

    assert "/tmp/outside" not in commands.report.shell_text
    assert commands.tmux == []
