"""Tests for dashboard workspace scanning."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.dashboard.scanner import RunScanner


def _write_state(workspace: Path, run_dir_id: str, payload: dict) -> Path:
    run_dir = workspace / ".orchestrate" / "runs" / run_dir_id
    run_dir.mkdir(parents=True)
    state_path = run_dir / "state.json"
    state_path.write_text(json.dumps(payload), encoding="utf-8")
    return state_path


def test_scanner_returns_zero_runs_for_empty_workspace(tmp_path: Path):
    result = RunScanner([tmp_path]).scan()

    assert [workspace.root for workspace in result.workspaces] == [tmp_path.resolve()]
    assert result.runs == []
    assert result.errors == []


def test_scanner_keys_duplicate_state_run_ids_by_workspace_and_directory(tmp_path: Path):
    workspace_a = tmp_path / "a"
    workspace_b = tmp_path / "b"
    workspace_a.mkdir()
    workspace_b.mkdir()
    _write_state(workspace_a, "run-a", {"run_id": "same", "status": "completed"})
    _write_state(workspace_b, "run-b", {"run_id": "same", "status": "failed"})

    result = RunScanner([workspace_a, workspace_b]).scan()

    keys = {(run.workspace.root, run.run_dir_id) for run in result.runs}
    assert keys == {(workspace_a.resolve(), "run-a"), (workspace_b.resolve(), "run-b")}
    assert {run.state_run_id for run in result.runs} == {"same"}


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


def test_scanner_preserves_malformed_state_candidate(tmp_path: Path):
    run_dir = tmp_path / ".orchestrate" / "runs" / "bad-run"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text("{not json", encoding="utf-8")

    result = RunScanner([tmp_path]).scan()

    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.run_dir_id == "bad-run"
    assert run.state is None
    assert run.parse_error is not None


def test_scanner_warns_on_state_run_id_mismatch(tmp_path: Path):
    _write_state(tmp_path, "dir-run", {"run_id": "state-run", "status": "completed"})

    result = RunScanner([tmp_path]).scan()

    assert result.runs[0].warnings == [
        "state.run_id 'state-run' differs from run directory 'dir-run'"
    ]


def test_scanner_rejects_state_json_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    external_state = outside / "state.json"
    external_state.write_text(
        json.dumps({"run_id": "external-run", "status": "completed"}),
        encoding="utf-8",
    )
    run_dir = tmp_path / ".orchestrate" / "runs" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").symlink_to(external_state)

    result = RunScanner([tmp_path]).scan()

    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.state is None
    assert run.state_run_id is None
    assert run.read_error is not None
    assert "outside workspace" in run.read_error
    assert run.run_root == run_dir.resolve()
    assert run.state_path == run_dir / "state.json"


def test_scanner_preserves_broken_state_json_symlink_candidate(tmp_path: Path):
    run_dir = tmp_path / ".orchestrate" / "runs" / "broken"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").symlink_to(run_dir / "missing-state.json")

    result = RunScanner([tmp_path]).scan()

    assert len(result.runs) == 1
    run = result.runs[0]
    assert run.run_dir_id == "broken"
    assert run.state is None
    assert run.read_error is not None
    assert run.run_root == run_dir.resolve()
    assert run.state_path == run_dir / "state.json"
