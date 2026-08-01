"""Deterministic run-reference workspace primitives."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .contracts import canonical_sha256


_HASH_CHUNK_SIZE = 1024 * 1024


class WorkspaceFreezeError(ValueError):
    """A workspace cannot be represented by the deterministic tree contract."""


@dataclass(frozen=True)
class TreeEntry:
    path: str
    kind: str
    mode: int
    size: int
    sha256: str | None
    link_target: str | None = None


@dataclass(frozen=True)
class TreeManifest:
    schema_version: int
    entries: tuple[TreeEntry, ...]
    digest: str


def _utf8_bytes(value: str, *, label: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceFreezeError(f"{label} is not valid UTF-8 text") from exc


def _entry_row(entry: TreeEntry) -> dict[str, object]:
    return {
        "path": entry.path,
        "kind": entry.kind,
        "mode": entry.mode,
        "size": entry.size,
        "sha256": entry.sha256,
        "link_target": entry.link_target,
    }


def manifest_from_entries(entries: Iterable[TreeEntry]) -> TreeManifest:
    ordered = tuple(
        sorted(entries, key=lambda entry: _utf8_bytes(entry.path, label="tree entry path"))
    )
    payload = {
        "schema_version": 1,
        "entries": [_entry_row(entry) for entry in ordered],
    }
    return TreeManifest(
        schema_version=1,
        entries=ordered,
        digest=canonical_sha256(payload),
    )


def _normalize_excluded_roots(
    excluded_roots: Collection[str | PurePosixPath],
) -> tuple[PurePosixPath, ...]:
    normalized: set[PurePosixPath] = set()
    for value in excluded_roots:
        try:
            path = PurePosixPath(value)
        except TypeError as exc:
            raise WorkspaceFreezeError(f"invalid excluded root: {value!r}") from exc
        if (
            path.is_absolute()
            or not path.parts
            or any(part in {".", ".."} for part in path.parts)
        ):
            raise WorkspaceFreezeError(
                f"excluded root is not canonical relative text: {value!r}"
            )
        _utf8_bytes(path.as_posix(), label="excluded root")
        normalized.add(path)
    return tuple(
        sorted(
            normalized,
            key=lambda path: _utf8_bytes(
                path.as_posix(),
                label="excluded root",
            ),
        )
    )


def _is_excluded(path: PurePosixPath, excluded_roots: tuple[PurePosixPath, ...]) -> bool:
    return any(path.parts[: len(excluded.parts)] == excluded.parts for excluded in excluded_roots)


def _hash_regular_file(path: Path, expected: os.stat_result) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise WorkspaceFreezeError(f"tree entry changed type before hashing: {path}")
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise WorkspaceFreezeError(f"tree entry changed identity before hashing: {path}")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, _HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        return size, f"sha256:{digest.hexdigest()}"
    finally:
        os.close(descriptor)


def freeze_tree(
    root: Path,
    excluded_roots: Collection[str | PurePosixPath] = (),
) -> TreeManifest:
    """Freeze every file, directory, and symlink without following symlinks."""

    root = Path(root)
    try:
        root_identity = root.lstat()
    except OSError as exc:
        raise WorkspaceFreezeError(f"cannot inspect tree root: {root}") from exc
    if not stat.S_ISDIR(root_identity.st_mode):
        raise WorkspaceFreezeError(f"tree root is not a directory: {root}")

    exclusions = _normalize_excluded_roots(excluded_roots)
    entries: list[TreeEntry] = []

    def walk(directory: Path, relative_directory: PurePosixPath) -> None:
        try:
            with os.scandir(directory) as scan:
                children = list(scan)
            children.sort(key=lambda child: _utf8_bytes(child.name, label="tree entry name"))
        except OSError as exc:
            raise WorkspaceFreezeError(f"cannot enumerate tree directory: {directory}") from exc

        for child in children:
            relative = relative_directory / child.name
            if _is_excluded(relative, exclusions):
                continue
            path_text = relative.as_posix()
            _utf8_bytes(path_text, label="tree entry path")
            try:
                identity = child.stat(follow_symlinks=False)
            except OSError as exc:
                raise WorkspaceFreezeError(f"cannot inspect tree entry: {path_text!r}") from exc
            mode = stat.S_IMODE(identity.st_mode)
            child_path = Path(child.path)
            if stat.S_ISDIR(identity.st_mode):
                entries.append(TreeEntry(path_text, "directory", mode, 0, None))
                walk(child_path, relative)
            elif stat.S_ISREG(identity.st_mode):
                size, digest = _hash_regular_file(child_path, identity)
                entries.append(TreeEntry(path_text, "file", mode, size, digest))
            elif stat.S_ISLNK(identity.st_mode):
                try:
                    link_target = os.readlink(child_path)
                except OSError as exc:
                    raise WorkspaceFreezeError(f"cannot read tree symlink: {path_text!r}") from exc
                target_bytes = _utf8_bytes(link_target, label=f"symlink target for {path_text!r}")
                entries.append(
                    TreeEntry(
                        path_text,
                        "symlink",
                        mode,
                        len(target_bytes),
                        f"sha256:{hashlib.sha256(target_bytes).hexdigest()}",
                        link_target,
                    )
                )
            else:
                raise WorkspaceFreezeError(f"unsupported tree entry type: {path_text!r}")

    walk(root, PurePosixPath())
    return manifest_from_entries(entries)


__all__ = [
    "TreeEntry",
    "TreeManifest",
    "WorkspaceFreezeError",
    "freeze_tree",
    "manifest_from_entries",
]
