"""Tests for dashboard workspace scanning."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.dashboard.scanner import RunScanner


def test_scanner_returns_zero_runs_for_empty_workspace(tmp_path: Path):
    result = RunScanner([tmp_path]).scan()

    assert [workspace.root for workspace in result.workspaces] == [tmp_path.resolve()]
    assert result.runs == []
    assert result.errors == []


def test_scanner_deduplicates_symlinked_workspaces(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    link = tmp_path / "workspace-link"
    link.symlink_to(workspace, target_is_directory=True)

    result = RunScanner([workspace, link]).scan()

    assert len(result.workspaces) == 1
    assert result.workspaces[0].root == workspace.resolve()


def test_scanner_rejects_non_directory_workspace(tmp_path: Path):
    not_a_dir = tmp_path / "file.txt"
    not_a_dir.write_text("x", encoding="utf-8")

    with pytest.raises(ValueError, match="workspace is not a directory"):
        RunScanner([not_a_dir])
