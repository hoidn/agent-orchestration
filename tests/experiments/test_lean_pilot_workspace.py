from __future__ import annotations

import importlib
import io
import os
import socket
import stat
import subprocess
import tarfile
from dataclasses import FrozenInstanceError
from pathlib import Path, PurePosixPath
from types import ModuleType

import pytest


PLAIN_BYTES = b"plain\x00bytes\n"
SCRIPT_BYTES = b"#!/bin/sh\nexit 0\n"


@pytest.fixture(scope="module")
def workspace() -> ModuleType:
    return importlib.import_module("orchestrator.experiments.workspace")


def _write_tree(root: Path) -> None:
    (root / "plain.bin").write_bytes(PLAIN_BYTES)
    (root / "plain.bin").chmod(0o664)
    (root / "\u00e9.txt").write_text("accent\n", encoding="utf-8")
    (root / "\u00e9.txt").chmod(0o664)

    nested = root / "nested"
    nested.mkdir()
    (nested / "run.sh").write_bytes(SCRIPT_BYTES)
    (nested / "run.sh").chmod(0o775)
    nested.chmod(0o775)
    (root / "nested-link").symlink_to("nested", target_is_directory=True)


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def _file_member(name: str, data: bytes = b"data") -> tuple[tarfile.TarInfo, bytes]:
    member = tarfile.TarInfo(name)
    member.mode = 0o664
    member.size = len(data)
    return member, data


def _directory_member(name: str) -> tuple[tarfile.TarInfo, None]:
    member = tarfile.TarInfo(name)
    member.type = tarfile.DIRTYPE
    member.mode = 0o775
    return member, None


def _symlink_member(name: str, target: str) -> tuple[tarfile.TarInfo, None]:
    member = tarfile.TarInfo(name)
    member.type = tarfile.SYMTYPE
    member.linkname = target
    return member, None


def _special_member(name: str, kind: bytes) -> tuple[tarfile.TarInfo, None]:
    member = tarfile.TarInfo(name)
    member.type = kind
    return member, None


def _tar_bytes(
    *members: tuple[tarfile.TarInfo, bytes | None],
) -> bytes:
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w:") as output:
        for member, data in members:
            output.addfile(
                member,
                io.BytesIO(data) if data is not None else None,
            )
    return archive.getvalue()


def _stub_git_archive(
    workspace: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    archive: bytes,
) -> None:
    def completed(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess:
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=archive,
            stderr=b"",
        )

    monkeypatch.setattr(workspace.subprocess, "run", completed)


@pytest.fixture
def committed_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _write_tree(repo)
    _git(repo, "add", "--all")
    _git(
        repo,
        "-c",
        "user.name=Lean Pilot Test",
        "-c",
        "user.email=lean-pilot@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-qm",
        "fixture",
    )
    return repo, _git(repo, "rev-parse", "HEAD")


def test_materialize_same_commit_into_three_identical_plain_trees(
    workspace: ModuleType,
    committed_repo: tuple[Path, str],
    tmp_path: Path,
) -> None:
    repo, commit = committed_repo
    destinations = [tmp_path / f"arm-{index}" for index in range(3)]

    assert all(not destination.exists() for destination in destinations)
    manifests = [
        workspace.materialize_git_archive(repo, commit, destination)
        for destination in destinations
    ]

    assert manifests[0] == manifests[1] == manifests[2]
    assert isinstance(manifests[0].entries, tuple)
    with pytest.raises(FrozenInstanceError):
        setattr(manifests[0], "digest", "changed")
    with pytest.raises(FrozenInstanceError):
        setattr(manifests[0].entries[0], "path", "changed")

    entries = {entry.path: entry for entry in manifests[0].entries}
    assert entries["plain.bin"].kind == "file"
    assert entries["plain.bin"].mode == 0o664
    assert entries["nested"].kind == "directory"
    assert entries["nested/run.sh"].kind == "file"
    assert entries["nested/run.sh"].mode == 0o775
    assert entries["nested-link"].kind == "symlink"
    assert entries["nested-link"].link_target == "nested"

    for destination in destinations:
        assert not any(path.name == ".git" for path in destination.rglob(".git"))
        assert (destination / "plain.bin").read_bytes() == PLAIN_BYTES
        assert (destination / "nested" / "run.sh").read_bytes() == SCRIPT_BYTES
        assert stat.S_IMODE((destination / "plain.bin").stat().st_mode) == 0o664
        assert (
            stat.S_IMODE((destination / "nested" / "run.sh").stat().st_mode)
            == 0o775
        )
        assert stat.S_IMODE((destination / "nested").stat().st_mode) == 0o775
        assert os.readlink(destination / "nested-link") == "nested"


def test_verified_git_subtree_materializes_rootless_and_rejects_tree_drift(
    workspace: ModuleType,
    committed_repo: tuple[Path, str],
    tmp_path: Path,
) -> None:
    repo, commit = committed_repo
    tree = _git(repo, "rev-parse", f"{commit}:nested")

    treeish = workspace._verified_git_subtree(
        repo,
        commit,
        PurePosixPath("nested"),
        f"git-tree:{tree}",
    )
    destination = tmp_path / "subtree"
    manifest = workspace.materialize_git_archive(repo, treeish, destination)

    assert treeish == f"{commit}:nested"
    assert [entry.path for entry in manifest.entries] == ["run.sh"]
    assert (destination / "run.sh").read_bytes() == SCRIPT_BYTES
    assert not (destination / "nested").exists()

    with pytest.raises(workspace.WorkspaceError, match="Git tree identity mismatch"):
        workspace._verified_git_subtree(
            repo,
            commit,
            PurePosixPath("nested"),
            f"git-tree:{'0' * 40}",
        )


@pytest.mark.parametrize(
    "bad_name",
    ["/absolute.txt", "nested/../parent.txt"],
    ids=["absolute", "parent-component"],
)
def test_materialize_rejects_unsafe_member_names_before_mutation(
    workspace: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    bad_name: str,
) -> None:
    _stub_git_archive(
        workspace,
        monkeypatch,
        _tar_bytes(_file_member("safe.txt"), _file_member(bad_name)),
    )
    destination = tmp_path / "destination"

    with pytest.raises(ValueError):
        workspace.materialize_git_archive(tmp_path / "repo", "commit", destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    "layout",
    ["duplicate", "file-ancestor"],
)
def test_materialize_rejects_duplicate_and_colliding_members_before_mutation(
    workspace: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    layout: str,
) -> None:
    if layout == "duplicate":
        members = (_file_member("same.txt"), _file_member("same.txt", b"other"))
    else:
        members = (_file_member("node"), _directory_member("node/child"))
    _stub_git_archive(workspace, monkeypatch, _tar_bytes(*members))
    destination = tmp_path / "destination"

    with pytest.raises(ValueError):
        workspace.materialize_git_archive(tmp_path / "repo", "commit", destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    ("name", "target"),
    [("link", "/outside"), ("nested/link", "../../outside")],
    ids=["absolute", "escaping"],
)
def test_materialize_rejects_unsafe_symlink_targets_before_mutation(
    workspace: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str,
    target: str,
) -> None:
    _stub_git_archive(
        workspace,
        monkeypatch,
        _tar_bytes(_file_member("safe.txt"), _symlink_member(name, target)),
    )
    destination = tmp_path / "destination"

    with pytest.raises(ValueError):
        workspace.materialize_git_archive(tmp_path / "repo", "commit", destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    "kind",
    [tarfile.FIFOTYPE, tarfile.CHRTYPE, tarfile.BLKTYPE],
    ids=["fifo", "character-device", "block-device"],
)
def test_materialize_rejects_unsupported_tar_members_before_mutation(
    workspace: ModuleType,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    kind: bytes,
) -> None:
    _stub_git_archive(
        workspace,
        monkeypatch,
        _tar_bytes(_file_member("safe.txt"), _special_member("special", kind)),
    )
    destination = tmp_path / "destination"

    with pytest.raises(ValueError):
        workspace.materialize_git_archive(tmp_path / "repo", "commit", destination)

    assert not destination.exists()


def test_freeze_is_ordered_non_following_and_uses_exact_excluded_roots(
    workspace: ModuleType,
    tmp_path: Path,
) -> None:
    root = tmp_path / "product"
    root.mkdir()
    _write_tree(root)
    excluded = root / "runtime"
    excluded.mkdir()
    (excluded / "ignored.txt").write_bytes(b"ignored-v1")
    sibling = root / "runtime-copy"
    sibling.mkdir()
    (sibling / "included.txt").write_bytes(b"included-v1")

    excluded_roots = {PurePosixPath("runtime")}
    baseline = workspace.freeze_product(root, excluded_roots)
    paths = [entry.path for entry in baseline.entries]

    assert paths == sorted(paths, key=lambda path: path.encode("utf-8"))
    assert "runtime" not in paths
    assert not any(path.startswith("runtime/") for path in paths)
    assert "runtime-copy/included.txt" in paths
    assert "nested-link" in paths
    assert not any(path.startswith("nested-link/") for path in paths)

    (root / "plain.bin").write_bytes(b"included-change")
    included_change = workspace.freeze_product(root, excluded_roots)
    assert included_change.digest != baseline.digest

    (root / "plain.bin").write_bytes(PLAIN_BYTES)
    restored = workspace.freeze_product(root, excluded_roots)
    assert restored == baseline

    (excluded / "ignored.txt").write_bytes(b"ignored-v2")
    excluded_change = workspace.freeze_product(root, excluded_roots)
    assert excluded_change.digest == baseline.digest

    (sibling / "included.txt").write_bytes(b"included-v2")
    sibling_change = workspace.freeze_product(root, excluded_roots)
    assert sibling_change.digest != excluded_change.digest


@pytest.mark.parametrize("kind", ["fifo", "socket"])
def test_freeze_rejects_special_files_without_reading_them(
    workspace: ModuleType,
    tmp_path: Path,
    kind: str,
) -> None:
    root = tmp_path / "product"
    root.mkdir()
    special = root / "special"
    bound_socket: socket.socket | None = None
    try:
        if kind == "fifo":
            os.mkfifo(special, 0o600)
        else:
            bound_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            bound_socket.bind(str(special))

        with pytest.raises(ValueError):
            workspace.freeze_product(root, set())
    finally:
        if bound_socket is not None:
            bound_socket.close()
