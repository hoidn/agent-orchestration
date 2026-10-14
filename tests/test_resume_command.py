"""Tests for the CLI resume command (AT-4)."""

import os
import json
import pytest
from pathlib import Path
import stat
import tempfile
from unittest.mock import (
    patch,
)
import hashlib

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.state import StateManager


def _persisted_tree_entries(run_root: Path) -> tuple[tuple[str, bytes, bytes], ...]:
    entries: list[tuple[str, bytes, bytes]] = []

    def visit(directory: Path, relative_directory: Path) -> None:
        with os.scandir(directory) as children:
            sorted_children = sorted(children, key=lambda child: child.name)
        for child in sorted_children:
            relative_path = relative_directory / child.name
            relative_text = relative_path.as_posix()
            if relative_text == "run.lock":
                # The command-lifetime coordination inode is not persisted
                # workflow state or evidence.
                continue
            mode = child.stat(follow_symlinks=False).st_mode
            if stat.S_ISDIR(mode):
                entries.append((relative_text, b"d", b""))
                visit(Path(child.path), relative_path)
            elif stat.S_ISREG(mode):
                entries.append((relative_text, b"f", Path(child.path).read_bytes()))
            elif stat.S_ISLNK(mode):
                entries.append((relative_text, b"l", os.readlink(child.path).encode("utf-8")))
            else:
                raise AssertionError(f"unsupported persisted run-tree entry type: {relative_text}")

    visit(run_root, Path())
    return tuple(sorted(entries, key=lambda entry: entry[0]))


def _persisted_tree_snapshot(run_root: Path) -> bytes:
    entries = _persisted_tree_entries(run_root)
    encoded = bytearray(b"orchestrator-persisted-tree-snapshot-v1\x00")
    encoded.extend(len(entries).to_bytes(8, "big"))
    for relative_path, entry_type, payload in entries:
        encoded_path = relative_path.encode("utf-8")
        encoded.extend(entry_type)
        encoded.extend(len(encoded_path).to_bytes(8, "big"))
        encoded.extend(encoded_path)
        encoded.extend(len(payload).to_bytes(8, "big"))
        encoded.extend(payload)
    return bytes(encoded)


def _persisted_tree_digest(snapshot: bytes) -> str:
    return f"sha256:{hashlib.sha256(snapshot).hexdigest()}"


def test_persisted_tree_snapshot_tracks_symlink_targets_and_empty_directories(temp_workspace):
    run_root = temp_workspace / "run-tree"
    run_root.mkdir()
    first_target = run_root / "target-a.txt"
    second_target = run_root / "target-b.txt"
    first_target.write_bytes(b"equal contents\n")
    second_target.write_bytes(b"equal contents\n")
    link = run_root / "current.txt"
    link.symlink_to(first_target.name)

    first_link_snapshot = _persisted_tree_snapshot(run_root)
    link.unlink()
    link.symlink_to(second_target.name)
    second_link_snapshot = _persisted_tree_snapshot(run_root)

    assert second_link_snapshot != first_link_snapshot
    assert _persisted_tree_digest(second_link_snapshot) != _persisted_tree_digest(first_link_snapshot)

    first_empty_directory = run_root / "empty-a"
    first_empty_directory.mkdir()
    first_directory_snapshot = _persisted_tree_snapshot(run_root)
    first_empty_directory.rename(run_root / "empty-b")
    second_directory_snapshot = _persisted_tree_snapshot(run_root)

    assert second_directory_snapshot != first_directory_snapshot
    assert _persisted_tree_digest(second_directory_snapshot) != _persisted_tree_digest(first_directory_snapshot)


@pytest.fixture
def temp_workspace():
    """Create a temporary workspace directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        yield workspace


def test_at4_resume_nonexistent_run(temp_workspace):
    """Test resuming a run that doesn't exist."""
    with patch('os.getcwd', return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id="nonexistent-run",
            repair=False,
            force_restart=False
        )

    assert result == 1  # Should fail


def test_completed_legacy_resume_refuses_without_mutating_run_state(
    temp_workspace,
    capsys,
):
    run_id = "completed-yml-run"
    state_dir = temp_workspace / ".orchestrate" / "runs" / run_id
    state_dir.mkdir(parents=True)
    state = {
        "schema_version": StateManager.SCHEMA_VERSION,
        "run_id": run_id,
        "workflow_file": "retired.yml",
        "workflow_checksum": "sha256:retired-source",
        "started_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:01:00Z",
        "status": "completed",
        "context": {},
        "steps": {},
    }
    (state_dir / "state.json").write_text(json.dumps(state, indent=2))
    before = _persisted_tree_snapshot(state_dir)

    with patch("os.getcwd", return_value=str(temp_workspace)):
        result = resume_workflow(
            run_id=run_id,
            repair=False,
            force_restart=False,
        )

    captured = capsys.readouterr()
    assert result == 2
    assert "workflow_execution_profile_retired" in captured.err
    assert "already completed successfully" not in captured.out
    assert _persisted_tree_snapshot(state_dir) == before
