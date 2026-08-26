from __future__ import annotations

import errno
import hashlib
import os
from pathlib import Path
import socket
import stat
import unicodedata

import pytest

import orchestrator._common.safe_tree as safe_tree
from orchestrator._common.safe_tree import (
    SafeTreePathChangedError,
    SafeTreePathError,
    SafeTreeRejectionError,
    copy_regular_file,
    hash_regular_file,
    read_regular_file,
    walk_regular_files,
)

_CHUNK_SIZE = 64 * 1024


def _tree_descriptor(root: Path) -> int:
    return os.open(root, os.O_RDONLY | os.O_DIRECTORY)


def _run_walk(root: Path) -> list[safe_tree.RegularFileRow]:
    fd = _tree_descriptor(root)
    try:
        return list(walk_regular_files(fd))
    finally:
        os.close(fd)


def _make_entries(root: Path, names: list[bytes | str]) -> None:
    fd = _tree_descriptor(root)
    try:
        for name in names:
            os.open(
                name if isinstance(name, bytes) else os.fsencode(name),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
                dir_fd=fd,
            )
    finally:
        os.close(fd)


def test_walk_yields_deterministic_sorted_utf8_rows(tmp_path: Path) -> None:
    (tmp_path / "b").mkdir()
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "z.txt").write_bytes(b"zzz")
    (tmp_path / "a" / "m.bin").write_bytes(b"mmm")
    (tmp_path / "b" / "q.txt").write_bytes(b"q")
    (tmp_path / "top").write_bytes(b"t")
    (tmp_path / ".hidden").write_bytes(b"h")
    fd = _tree_descriptor(tmp_path)
    try:
        first = list(walk_regular_files(fd))
        second = list(walk_regular_files(fd))
    finally:
        os.close(fd)

    assert [(row.relative_path, row.size_bytes) for row in first] == [
        (".hidden", 1),
        ("a/m.bin", 3),
        ("a/z.txt", 3),
        ("b/q.txt", 1),
        ("top", 1),
    ]
    assert first == second
    observed = os.stat(tmp_path / "top")
    assert (first[4].device, first[4].inode) == (observed.st_dev, observed.st_ino)


def test_walk_of_empty_tree_yields_no_rows(tmp_path: Path) -> None:
    assert _run_walk(tmp_path) == []


def test_walk_rejects_entry_budget_before_yielding_unbounded_tree(tmp_path: Path) -> None:
    for name in ("a", "b", "c"):
        (tmp_path / name).write_bytes(b"x")
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError, match="entry bound"):
            list(walk_regular_files(fd, max_entries=2))
    finally:
        os.close(fd)


def test_walk_rejects_depth_budget(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    (nested / "x").write_bytes(b"x")
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError, match="depth bound"):
            list(walk_regular_files(fd, max_depth=1))
    finally:
        os.close(fd)


def test_remove_tree_contents_handles_deep_tree_iteratively(tmp_path: Path) -> None:
    nested = tmp_path
    for index in range(80):
        nested = nested / f"d{index}"
        nested.mkdir()
    (nested / "leaf").write_bytes(b"x")
    fd = _tree_descriptor(tmp_path)
    try:
        safe_tree.remove_tree_contents(fd)
    finally:
        os.close(fd)
    assert list(tmp_path.iterdir()) == []


def test_remove_tree_contents_restores_child_changed_directory_modes(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "locked"
    nested.mkdir()
    (nested / "leaf").write_bytes(b"x")
    fd = _tree_descriptor(tmp_path)
    nested.chmod(0)
    tmp_path.chmod(0)
    try:
        safe_tree.remove_tree_contents(fd)
    finally:
        os.close(fd)
        tmp_path.chmod(0o700)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "make_entry",
    [
        lambda p: os.symlink("real.txt", p / "link.txt"),
        lambda p: os.symlink("missing", p / "dangling"),
        lambda p: os.symlink(".", p / "dir-link"),
        lambda p: os.mkfifo(p / "pipe"),
        lambda p: socket.socket(socket.AF_UNIX).bind(str(p / "sock")) or None,
        lambda p: os.mknod(p / "device", stat.S_IFCHR | 0o600)
        if os.geteuid() == 0
        else pytest.skip("device nodes require privileges"),
    ],
    ids=["symlink", "dangling-symlink", "dir-symlink", "fifo", "socket", "device"],
)
def test_walk_rejects_non_regular_entries(tmp_path: Path, make_entry) -> None:
    (tmp_path / "real.txt").write_bytes(b"x")
    make_entry(tmp_path)
    with pytest.raises(SafeTreeRejectionError):
        _run_walk(tmp_path)


def test_walk_rejects_hard_linked_duplicates(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"same")
    os.link(tmp_path / "a", tmp_path / "b")
    with pytest.raises(SafeTreeRejectionError, match="hard link"):
        _run_walk(tmp_path)


def test_walk_rejects_undecodable_names(tmp_path: Path) -> None:
    _make_entries(tmp_path, [b"bad\xffname"])
    with pytest.raises(SafeTreeRejectionError, match="UTF-8"):
        _run_walk(tmp_path)


def test_walk_rejects_duplicate_canonical_paths(tmp_path: Path) -> None:
    _make_entries(
        tmp_path,
        [
            os.fsencode(unicodedata.normalize("NFD", "café")),
            os.fsencode(unicodedata.normalize("NFC", "café")),
        ],
    )
    with pytest.raises(SafeTreeRejectionError, match="canonical"):
        _run_walk(tmp_path)


def test_walk_defensively_rejects_dot_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a.txt").write_bytes(b"x")
    monkeypatch.setattr(safe_tree.os, "listdir", lambda _fd: ["..", "a.txt"])
    with pytest.raises(SafeTreeRejectionError):
        _run_walk(tmp_path)


def test_walk_rejects_entries_that_vanish_between_list_and_stat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a.txt").write_bytes(b"x")
    real_stat = safe_tree.os.stat

    def vanishing_stat(path, *, dir_fd=None, follow_symlinks=True):
        if os.fsdecode(path) == "a.txt":
            raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT))
        return real_stat(path, dir_fd=dir_fd, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(safe_tree.os, "stat", vanishing_stat)
    with pytest.raises(SafeTreeRejectionError):
        _run_walk(tmp_path)


@pytest.mark.parametrize(
    ("open_error", "error_type"),
    [
        (
            FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT)),
            SafeTreePathChangedError,
        ),
        (
            PermissionError(errno.EACCES, os.strerror(errno.EACCES)),
            SafeTreeRejectionError,
        ),
    ],
    ids=["vanished-directory", "open-denied-directory"],
)
def test_walk_directory_open_failures_are_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    open_error: OSError,
    error_type: type[SafeTreeError],
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_bytes(b"x")
    real_open = safe_tree.os.open

    def failing_open(path, flags, mode=0o777, *, dir_fd=None):
        if os.fsdecode(path) == "a" and flags & os.O_DIRECTORY:
            raise open_error
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safe_tree.os, "open", failing_open)
    with pytest.raises(error_type):
        _run_walk(tmp_path)


def test_walk_detects_directory_swap_between_stat_and_open(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    (tmp_path / "b" / "f.txt").write_bytes(b"x")
    real_open = safe_tree.os.open

    def swapped_open(path, flags, mode=0o777, *, dir_fd=None):
        if os.fsdecode(path) == "a" and flags & os.O_DIRECTORY:
            return real_open("b", flags, mode, dir_fd=dir_fd)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safe_tree.os, "open", swapped_open)
    with pytest.raises(SafeTreePathChangedError):
        _run_walk(tmp_path)


def test_hash_regular_file_matches_sha256_of_contents(tmp_path: Path) -> None:
    payload = bytes(range(256)) * 4096
    (tmp_path / "blob.bin").write_bytes(payload)
    fd = _tree_descriptor(tmp_path)
    try:
        digest = hash_regular_file(fd, "blob.bin")
    finally:
        os.close(fd)

    assert digest == hashlib.sha256(payload).hexdigest()


@pytest.mark.parametrize("operation", ["hash", "copy"], ids=["hash", "copy"])
def test_streaming_uses_bounded_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    payload = os.urandom(2 * 1024 * 1024)
    (tmp_path / "blob.bin").write_bytes(payload)
    destination = tmp_path / "copy.bin"
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    real_read = safe_tree.os.read
    read_sizes: list[int] = []

    def recording_read(fd, count):
        read_sizes.append(count)
        return real_read(fd, count)

    monkeypatch.setattr(safe_tree.os, "read", recording_read)
    fd = _tree_descriptor(tmp_path)
    try:
        if operation == "hash":
            result = hash_regular_file(fd, "blob.bin")
        else:
            result = copy_regular_file(fd, "blob.bin", destination_fd)
    finally:
        os.close(fd)
        os.close(destination_fd)

    assert read_sizes
    assert max(read_sizes) <= _CHUNK_SIZE
    assert len(read_sizes) >= 32
    if operation == "hash":
        assert result == hashlib.sha256(payload).hexdigest()
    else:
        assert result == len(payload)
        assert destination.read_bytes() == payload


def test_read_regular_file_returns_exact_bytes(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.txt").write_bytes("café\n".encode("utf-8"))
    fd = _tree_descriptor(tmp_path)
    try:
        assert read_regular_file(fd, "a/b.txt") == "café\n".encode("utf-8")
    finally:
        os.close(fd)


def test_empty_regular_file_round_trips(tmp_path: Path) -> None:
    (tmp_path / "empty").write_bytes(b"")
    fd = _tree_descriptor(tmp_path)
    destination = tmp_path / "copy.bin"
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        assert hash_regular_file(fd, "empty") == hashlib.sha256(b"").hexdigest()
        assert read_regular_file(fd, "empty") == b""
        assert copy_regular_file(fd, "empty", destination_fd) == 0
    finally:
        os.close(destination_fd)
        os.close(fd)
    assert destination.read_bytes() == b""


@pytest.mark.parametrize(
    "bad_path",
    ["/abs", "a/../b", "../b", "a/./b", "a//b", "a/", "", "a/\udcff", "a/b\x00c"],
)
def test_read_rejects_invalid_relative_paths(
    tmp_path: Path,
    bad_path: str,
) -> None:
    (tmp_path / "a").mkdir()
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreePathError):
            read_regular_file(fd, bad_path)
    finally:
        os.close(fd)


def test_read_rejects_symlink_components(tmp_path: Path) -> None:
    (tmp_path / "real").mkdir()
    (tmp_path / "real" / "f.txt").write_bytes(b"x")
    os.symlink("real", tmp_path / "link")
    os.symlink("real/f.txt", tmp_path / "file-link")
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError):
            read_regular_file(fd, "link/f.txt")
        with pytest.raises(SafeTreeRejectionError):
            read_regular_file(fd, "file-link")
    finally:
        os.close(fd)


def test_read_rejects_non_regular_final_entries(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe")
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError):
            read_regular_file(fd, "pipe")
    finally:
        os.close(fd)


def test_copy_never_closes_the_destination_descriptor(tmp_path: Path) -> None:
    (tmp_path / "src.bin").write_bytes(b"payload")
    destination = tmp_path / "out.bin"
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    fd = _tree_descriptor(tmp_path)
    try:
        copy_regular_file(fd, "src.bin", destination_fd)
        os.write(destination_fd, b"tail")
    finally:
        os.close(fd)
        os.close(destination_fd)

    assert destination.read_bytes() == b"payloadtail"


def test_every_opened_descriptor_is_close_on_exec(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f.txt").write_bytes(b"x" * 70000)
    (tmp_path / "g.txt").write_bytes(b"y")
    destination = tmp_path / "out.bin"
    destination_fd = os.open(
        destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    fd = _tree_descriptor(tmp_path)
    real_open = safe_tree.os.open
    opened_flags: list[int] = []

    def recording_open(path, flags, mode=0o777, *, dir_fd=None):
        opened_flags.append(flags)
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(safe_tree.os, "open", recording_open)
    try:
        list(walk_regular_files(fd))
        hash_regular_file(fd, "a/f.txt")
        read_regular_file(fd, "g.txt")
        copy_regular_file(fd, "a/f.txt", destination_fd)
    finally:
        os.close(fd)
        os.close(destination_fd)

    assert opened_flags
    assert all(bool(flags & os.O_CLOEXEC) for flags in opened_flags)


def test_expected_identity_accepts_unchanged_file(tmp_path: Path) -> None:
    (tmp_path / "a").write_bytes(b"payload")
    row = _run_walk(tmp_path)[0]
    fd = _tree_descriptor(tmp_path)
    try:
        digest = hash_regular_file(fd, "a", expected=row)
    finally:
        os.close(fd)

    assert digest == hashlib.sha256(b"payload").hexdigest()


@pytest.mark.parametrize(
    ("prepare", "mutate", "row_path", "operations"),
    [
        (lambda p: ((p / "a").write_bytes(b"original"),
                    (p / "other").write_bytes(b"replacement")),
         lambda p: os.replace(p / "other", p / "a"), "a",
         ("hash", "read", "copy")),
        (lambda p: (p / "a").write_bytes(b"original"),
         lambda p: (p / "a").unlink(), "a",
         ("hash", "read", "copy")),
        (lambda p: ((p / "a").mkdir(), (p / "a" / "b.txt").write_bytes(b"x")),
         lambda p: ((p / "a" / "b.txt").unlink(), (p / "a").rmdir()),
         "a/b.txt", ("read",)),
    ],
    ids=["path-swap", "deleted-final", "deleted-intermediate"],
)
def test_expected_identity_rejects_changed_paths(
    tmp_path: Path,
    prepare,
    mutate,
    row_path: str,
    operations: tuple[str, ...],
) -> None:
    prepare(tmp_path)
    row = next(item for item in _run_walk(tmp_path) if item.relative_path == row_path)
    mutate(tmp_path)
    fd = _tree_descriptor(tmp_path)
    destination_fd = os.open(
        tmp_path / "out.bin", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
    )
    try:
        if "hash" in operations:
            with pytest.raises(SafeTreePathChangedError):
                hash_regular_file(fd, row_path, expected=row)
        if "read" in operations:
            with pytest.raises(SafeTreePathChangedError):
                read_regular_file(fd, row_path, expected=row)
        if "copy" in operations:
            with pytest.raises(SafeTreePathChangedError):
                copy_regular_file(fd, row_path, destination_fd, expected=row)
    finally:
        os.close(destination_fd)
        os.close(fd)


def test_read_without_expected_rejects_missing_path(tmp_path: Path) -> None:
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError):
            read_regular_file(fd, "missing.txt")
    finally:
        os.close(fd)


@pytest.mark.parametrize(
    ("tree_setup", "operation"),
    [
        (lambda p: (p / "a.txt").write_bytes(b"x" * 100), "hash"),
        (lambda p: ((p / "a").mkdir(), (p / "a" / "f.txt").write_bytes(b"x")), "walk"),
    ],
    ids=["final-file", "child-dir"],
)
def test_fstat_failure_closes_every_opened_descriptor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    tree_setup,
    operation: str,
) -> None:
    tree_setup(tmp_path)
    real_open = safe_tree.os.open
    opened: list[int] = []

    def recording_open(path, flags, mode=0o777, *, dir_fd=None):
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(safe_tree.os, "open", recording_open)
    monkeypatch.setattr(
        safe_tree.os,
        "fstat",
        lambda _fd: (_ for _ in ()).throw(
            OSError(errno.EIO, "injected fstat failure")
        ),
    )
    fd = _tree_descriptor(tmp_path)
    try:
        with pytest.raises(SafeTreeRejectionError):
            if operation == "hash":
                hash_regular_file(fd, "a.txt")
            else:
                _run_walk(tmp_path)
    finally:
        os.close(fd)

    assert opened
    for opened_fd in opened:
        with pytest.raises(OSError) as caught:
            os.read(opened_fd, 1)
        assert caught.value.errno == errno.EBADF
