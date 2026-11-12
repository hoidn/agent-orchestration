"""`WorkspaceFiles.publish_new`: durable publication that never replaces a name."""

from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from orchestrator._common.io_atomic import (
    RenameNoreplaceError,
    RenameNoreplaceUnavailableError,
)
from orchestrator.workflow import workspace_files
from orchestrator.workflow.workspace_files import WorkspaceFiles


def _publish(root: Path, name: str, content: bytes) -> None:
    files = WorkspaceFiles(root)
    try:
        files.publish_new(name, content)
    finally:
        files.close()


def test_publish_new_writes_durable_bytes(tmp_path: Path) -> None:
    _publish(tmp_path, "closed_program.x.json", b"edited program")

    published = tmp_path / "closed_program.x.json"
    assert (published.read_bytes(), stat.S_IMODE(published.stat().st_mode)) == (
        b"edited program",
        0o600,
    )


def test_publish_new_refuses_an_existing_name_and_leaves_its_bytes(tmp_path: Path) -> None:
    _publish(tmp_path, "closed_program.x.json", b"first")

    with pytest.raises(FileExistsError):
        _publish(tmp_path, "closed_program.x.json", b"second")
    assert (tmp_path / "closed_program.x.json").read_bytes() == b"first"


def test_publish_new_leaves_no_temporary_file_on_failure(tmp_path: Path) -> None:
    _publish(tmp_path, "closed_program.x.json", b"first")

    with pytest.raises(FileExistsError):
        _publish(tmp_path, "closed_program.x.json", b"second")
    assert sorted(os.listdir(tmp_path)) == ["closed_program.x.json"]


@pytest.mark.parametrize("kind", ["directory", "dangling symlink"])
def test_publish_new_refuses_a_name_taken_by_a_non_file_and_leaves_it(
    tmp_path: Path, kind: str
) -> None:
    taken = tmp_path / "closed_program.x.json"
    if kind == "directory":
        taken.mkdir()
    else:
        taken.symlink_to(tmp_path / "absent")

    with pytest.raises(FileExistsError):
        _publish(tmp_path, taken.name, b"second")
    assert (sorted(os.listdir(tmp_path)), taken.is_dir(), os.path.lexists(tmp_path / "absent")) == (
        [taken.name],
        kind == "directory",
        False,
    )


@pytest.mark.parametrize(
    "failure",
    [
        RenameNoreplaceUnavailableError("Linux renameat2 is unavailable"),
        RenameNoreplaceError(errno.EINVAL, os.strerror(errno.EINVAL)),
    ],
    ids=["no syscall", "file system refuses the flag"],
)
def test_publish_new_without_rename_noreplace_fails_and_publishes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def unsupported(*_arguments: object) -> None:
        raise failure

    monkeypatch.setattr(workspace_files, "rename_noreplace_at", unsupported)

    with pytest.raises(type(failure)):
        _publish(tmp_path, "closed_program.x.json", b"edited program")
    assert os.listdir(tmp_path) == []


def test_publish_new_does_not_follow_a_symlinked_parent_out_of_the_workspace(
    tmp_path: Path,
) -> None:
    workspace, outside = tmp_path / "workspace", tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "runs").symlink_to(outside)

    with pytest.raises(OSError):
        _publish(workspace, "runs/closed_program.x.json", b"edited program")
    assert os.listdir(outside) == []
