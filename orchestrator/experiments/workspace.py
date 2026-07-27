"""Safe source materialization and deterministic product manifests."""

from __future__ import annotations

import hashlib
import io
import os
import stat
import subprocess
import tarfile
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .contracts import canonical_sha256


_HASH_CHUNK_SIZE = 1024 * 1024


class WorkspaceError(ValueError):
    """A source archive or product tree violates the workspace contract."""


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
    entries: tuple[TreeEntry, ...]
    digest: str


@dataclass(frozen=True)
class _ArchiveEntry:
    path: PurePosixPath
    kind: str
    mode: int
    data: bytes | None = None
    link_target: str | None = None


def _utf8_bytes(value: str, *, label: str) -> bytes:
    try:
        return value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise WorkspaceError(f"{label} is not valid UTF-8 text") from exc


def _sha256_bytes(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _entry_row(entry: TreeEntry) -> dict[str, object]:
    return {
        "path": entry.path,
        "kind": entry.kind,
        "mode": entry.mode,
        "size": entry.size,
        "sha256": entry.sha256,
        "link_target": entry.link_target,
    }


def _tree_manifest(entries: Iterable[TreeEntry]) -> TreeManifest:
    ordered = tuple(
        sorted(entries, key=lambda entry: _utf8_bytes(entry.path, label="path"))
    )
    return TreeManifest(
        entries=ordered,
        digest=canonical_sha256([_entry_row(entry) for entry in ordered]),
    )


def _normalized_member_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute():
        raise WorkspaceError(f"archive member path is absolute: {name!r}")
    if not path.parts:
        raise WorkspaceError(f"archive member path is empty or dot: {name!r}")
    if any(part == ".." for part in path.parts):
        raise WorkspaceError(f"archive member path contains '..': {name!r}")
    normalized = PurePosixPath(*path.parts)
    _utf8_bytes(normalized.as_posix(), label="archive member path")
    return normalized


def _validate_symlink_target(path: PurePosixPath, target: str) -> None:
    if "\x00" in target:
        raise WorkspaceError(f"symlink {path.as_posix()!r} has a NUL target")
    _utf8_bytes(target, label=f"symlink target for {path.as_posix()!r}")
    target_path = PurePosixPath(target)
    if target_path.is_absolute():
        raise WorkspaceError(
            f"symlink {path.as_posix()!r} has an absolute target"
        )
    if not target_path.parts:
        raise WorkspaceError(f"symlink {path.as_posix()!r} has an empty target")

    resolved_parts = list(path.parent.parts)
    for part in target_path.parts:
        if part == "..":
            if not resolved_parts:
                raise WorkspaceError(
                    f"symlink {path.as_posix()!r} escapes the archive root"
                )
            resolved_parts.pop()
        else:
            resolved_parts.append(part)


def _member_kind(member: tarfile.TarInfo) -> str:
    if member.isdir():
        return "directory"
    if member.isreg():
        return "file"
    if member.issym():
        return "symlink"
    raise WorkspaceError(
        f"unsupported archive member type for {member.name!r}: {member.type!r}"
    )


def _read_regular_member(
    archive: tarfile.TarFile,
    member: tarfile.TarInfo,
) -> bytes:
    source = archive.extractfile(member)
    if source is None:
        raise WorkspaceError(f"archive file has no data: {member.name!r}")
    with source:
        data = source.read()
    if len(data) != member.size:
        raise WorkspaceError(f"archive file has the wrong size: {member.name!r}")
    return data


def _validated_archive_entries(
    archive: tarfile.TarFile,
) -> tuple[_ArchiveEntry, ...]:
    entries: list[_ArchiveEntry] = []
    kinds_by_path: dict[PurePosixPath, str] = {}

    for member in archive.getmembers():
        path = _normalized_member_path(member.name)
        if path in kinds_by_path:
            raise WorkspaceError(f"duplicate archive member: {path.as_posix()!r}")
        kind = _member_kind(member)
        kinds_by_path[path] = kind

        if kind == "file":
            entries.append(
                _ArchiveEntry(
                    path=path,
                    kind=kind,
                    mode=stat.S_IMODE(member.mode),
                    data=_read_regular_member(archive, member),
                )
            )
        elif kind == "symlink":
            _validate_symlink_target(path, member.linkname)
            entries.append(
                _ArchiveEntry(
                    path=path,
                    kind=kind,
                    mode=stat.S_IMODE(member.mode),
                    link_target=member.linkname,
                )
            )
        else:
            entries.append(
                _ArchiveEntry(
                    path=path,
                    kind=kind,
                    mode=stat.S_IMODE(member.mode),
                )
            )

    for path in kinds_by_path:
        for ancestor in path.parents:
            if not ancestor.parts:
                break
            ancestor_kind = kinds_by_path.get(ancestor)
            if ancestor_kind is not None and ancestor_kind != "directory":
                raise WorkspaceError(
                    f"non-directory archive member {ancestor.as_posix()!r} "
                    f"is an ancestor of {path.as_posix()!r}"
                )

    return tuple(entries)


def _destination_path(root: Path, relative: PurePosixPath) -> Path:
    return root.joinpath(*relative.parts)


def _extract_archive_entries(
    entries: tuple[_ArchiveEntry, ...],
    destination: Path,
) -> None:
    destination.mkdir(mode=0o755)
    destination.chmod(0o755)

    required_directories: set[PurePosixPath] = set()
    explicit_directory_modes: dict[PurePosixPath, int] = {}
    for entry in entries:
        if entry.kind == "directory":
            required_directories.add(entry.path)
            explicit_directory_modes[entry.path] = entry.mode
        for parent in entry.path.parents:
            if not parent.parts:
                break
            required_directories.add(parent)

    for relative in sorted(
        required_directories,
        key=lambda path: (len(path.parts), _utf8_bytes(path.as_posix(), label="path")),
    ):
        output = _destination_path(destination, relative)
        output.mkdir(mode=0o755, exist_ok=True)
        output.chmod(0o755)

    for entry in sorted(
        entries,
        key=lambda item: _utf8_bytes(item.path.as_posix(), label="path"),
    ):
        output = _destination_path(destination, entry.path)
        if entry.kind == "file":
            if entry.data is None:
                raise AssertionError("validated archive file has no data")
            with output.open("xb") as handle:
                handle.write(entry.data)
            output.chmod(entry.mode)
        elif entry.kind == "symlink":
            if entry.link_target is None:
                raise AssertionError("validated archive symlink has no target")
            os.symlink(entry.link_target, output)

    for relative in sorted(
        required_directories,
        key=lambda path: (
            -len(path.parts),
            _utf8_bytes(path.as_posix(), label="path"),
        ),
    ):
        output = _destination_path(destination, relative)
        output.chmod(explicit_directory_modes.get(relative, 0o755))


def materialize_git_archive(
    repo: Path,
    commit: str,
    destination: Path,
) -> TreeManifest:
    """Materialize one Git commit into a fresh plain-tree destination."""

    if os.path.lexists(destination):
        raise WorkspaceError(f"destination already exists: {destination}")

    archive_bytes = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", commit],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    ).stdout
    with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:") as archive:
        entries = _validated_archive_entries(archive)

    if os.path.lexists(destination):
        raise WorkspaceError(f"destination already exists: {destination}")
    _extract_archive_entries(entries, destination)
    return freeze_product(destination, ())


def _normalize_excluded_roots(
    excluded_roots: Collection[PurePosixPath],
) -> tuple[PurePosixPath, ...]:
    normalized: set[PurePosixPath] = set()
    for value in excluded_roots:
        try:
            path = PurePosixPath(value)
        except TypeError as exc:
            raise WorkspaceError(f"invalid excluded root: {value!r}") from exc
        if path.is_absolute():
            raise WorkspaceError(f"excluded root is absolute: {value!r}")
        if not path.parts:
            raise WorkspaceError(f"excluded root is empty or dot: {value!r}")
        if any(part == ".." for part in path.parts):
            raise WorkspaceError(f"excluded root contains '..': {value!r}")
        path = PurePosixPath(*path.parts)
        _utf8_bytes(path.as_posix(), label="excluded root")
        normalized.add(path)
    return tuple(
        sorted(
            normalized,
            key=lambda path: _utf8_bytes(path.as_posix(), label="excluded root"),
        )
    )


def _is_excluded(
    path: PurePosixPath,
    excluded_roots: tuple[PurePosixPath, ...],
) -> bool:
    return any(
        path.parts[: len(excluded.parts)] == excluded.parts
        for excluded in excluded_roots
    )


def _hash_regular_file(path: Path, identity: os.stat_result) -> tuple[int, str]:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise WorkspaceError(f"product entry changed type before hashing: {path}")
        if (opened.st_dev, opened.st_ino) != (identity.st_dev, identity.st_ino):
            raise WorkspaceError(f"product entry changed identity before hashing: {path}")

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


def freeze_product(
    root: Path,
    excluded_roots: Collection[PurePosixPath],
) -> TreeManifest:
    """Freeze a product tree without following symlinks."""

    try:
        root_identity = root.lstat()
    except OSError as exc:
        raise WorkspaceError(f"cannot inspect product root: {root}") from exc
    if not stat.S_ISDIR(root_identity.st_mode):
        raise WorkspaceError(f"product root is not a directory: {root}")

    exclusions = _normalize_excluded_roots(excluded_roots)
    entries: list[TreeEntry] = []

    def walk(directory: Path, relative_directory: PurePosixPath) -> None:
        with os.scandir(directory) as scan:
            children = list(scan)
        children.sort(
            key=lambda child: _utf8_bytes(child.name, label="product entry name")
        )

        for child in children:
            relative = relative_directory / child.name
            if _is_excluded(relative, exclusions):
                continue
            path_text = relative.as_posix()
            _utf8_bytes(path_text, label="product entry path")
            identity = child.stat(follow_symlinks=False)
            mode = stat.S_IMODE(identity.st_mode)
            child_path = Path(child.path)

            if stat.S_ISDIR(identity.st_mode):
                entries.append(
                    TreeEntry(
                        path=path_text,
                        kind="directory",
                        mode=mode,
                        size=0,
                        sha256=None,
                    )
                )
                walk(child_path, relative)
            elif stat.S_ISREG(identity.st_mode):
                size, digest = _hash_regular_file(child_path, identity)
                entries.append(
                    TreeEntry(
                        path=path_text,
                        kind="file",
                        mode=mode,
                        size=size,
                        sha256=digest,
                    )
                )
            elif stat.S_ISLNK(identity.st_mode):
                link_target = os.readlink(child_path)
                target_bytes = _utf8_bytes(
                    link_target,
                    label=f"symlink target for {path_text!r}",
                )
                entries.append(
                    TreeEntry(
                        path=path_text,
                        kind="symlink",
                        mode=mode,
                        size=len(target_bytes),
                        sha256=_sha256_bytes(target_bytes),
                        link_target=link_target,
                    )
                )
            else:
                raise WorkspaceError(f"unsupported product entry type: {path_text!r}")

    walk(root, PurePosixPath())
    return _tree_manifest(entries)


__all__ = [
    "TreeEntry",
    "TreeManifest",
    "WorkspaceError",
    "freeze_product",
    "materialize_git_archive",
]
