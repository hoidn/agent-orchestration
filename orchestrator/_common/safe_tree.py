"""Descriptor-relative no-follow reads of regular-file trees.

Operations here are low-level and shared by OMP consumers (conf admission,
scaffold generation, session links): a deterministic walk of regular files
beneath a caller-opened directory descriptor, and streaming hash/read/copy of
one regular file. Domain allowlists and schemas never belong in this module.
"""

from __future__ import annotations

from dataclasses import dataclass
import errno
from hashlib import sha256
import os
import stat
from pathlib import Path
import unicodedata

_CHUNK_SIZE = 64 * 1024
_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_NOFOLLOW_REGULAR = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


class SafeTreeError(Exception):
    """Base class for descriptor-safe tree failures."""


class SafeTreePathError(SafeTreeError, ValueError):
    """A caller-supplied relative path is not a safe POSIX relative path."""


class SafeTreeRejectionError(SafeTreeError):
    """A tree entry violates the regular-file-only no-follow contract."""


class SafeTreePathChangedError(SafeTreeError):
    """A tree entry changed identity between enumeration and use."""


@dataclass(frozen=True, slots=True)
class RegularFileRow:
    """One deterministic regular-file row beneath a directory descriptor."""

    relative_path: str
    size_bytes: int
    device: int
    inode: int
    mode: int
    uid: int
    link_count: int
    mtime_ns: int
    ctime_ns: int


def resolve_path_preserving_fd(path: Path | str) -> Path:
    """Resolve ordinary paths while retaining caller-owned ``/proc/self/fd`` roots."""
    candidate = Path(path)
    parts = candidate.parts
    if (
        len(parts) >= 5
        and parts[:4] == ("/", "proc", "self", "fd")
        and parts[4].isdecimal()
    ):
        info = os.fstat(int(parts[4]))
        if ".." in parts[5:]:
            raise SafeTreePathError("retained descriptor path must not contain '..'")
        if not stat.S_ISDIR(info.st_mode):
            raise SafeTreePathError("retained path root fd is not a directory")
        return candidate
    try:
        return candidate.resolve()
    except RuntimeError as exc:
        raise OSError(errno.ELOOP, str(exc), str(candidate)) from exc


def open_directory(path: str) -> int:
    """Open an absolute directory component-by-component without symlinks."""
    if not os.path.isabs(path):
        raise SafeTreePathError(f"directory root must be absolute: {path!r}")
    components = [part for part in path.split(os.sep) if part not in ("", ".")]
    if any(part == ".." for part in components):
        raise SafeTreePathError(
            f"directory root must not contain '..': {path!r}"
        )
    descriptor = os.open(
        "/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC
    )
    try:
        for component in components:
            try:
                child = os.open(
                    component, _NOFOLLOW_DIRECTORY, dir_fd=descriptor
                )
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise SafeTreeRejectionError(
                        f"cannot open directory root component {component!r}: "
                        "symlink or non-directory"
                    ) from exc
                raise SafeTreeRejectionError(
                    f"cannot open directory root component {component!r}"
                ) from exc
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _canonical_name(name: str) -> str:
    try:
        name.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise SafeTreeRejectionError(
            f"tree entry name is not valid UTF-8: {name!r}"
        ) from exc
    return unicodedata.normalize("NFC", name)


def _lstat_entry(directory_fd: int, name: str) -> os.stat_result:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except OSError as exc:
        raise SafeTreeRejectionError(
            f"tree entry cannot be enumerated safely: {name!r}"
        ) from exc


def _open_child_directory(
    directory_fd: int,
    name: str,
    expected: os.stat_result,
) -> int:
    try:
        child = os.open(name, _NOFOLLOW_DIRECTORY, dir_fd=directory_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise SafeTreeRejectionError(
                f"tree entry is not a directory: {name!r}"
            ) from exc
        if exc.errno == errno.ENOENT:
            raise SafeTreePathChangedError(
                f"tree entry changed identity: {name!r}"
            ) from exc
        raise SafeTreeRejectionError(
            f"tree entry cannot be opened: {name!r}"
        ) from exc
    try:
        opened = os.fstat(child)
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise SafeTreePathChangedError(
                f"tree entry changed identity: {name!r}"
            )
    except OSError as exc:
        os.close(child)
        raise SafeTreeRejectionError(
            f"tree entry cannot be inspected: {name!r}"
        ) from exc
    except BaseException:
        os.close(child)
        raise
    return child


def walk_regular_files(root_fd: int, *, directories: list[str] | None = None,
                       max_depth: int | None = None, max_entries: int | None = None):
    """Yield deterministic no-follow rows, optionally under depth/entry bounds."""
    for label, value in (("depth", max_depth), ("entry", max_entries)):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError(f"tree {label} bound must be a non-negative integer")
    seen_identities: set[tuple[int, int]] = set()
    seen_canonical: set[str] = set()
    entry_count = 0

    def recurse(directory_fd: int, prefix: str, depth: int):
        nonlocal entry_count
        if max_depth is not None and depth > max_depth:
            raise SafeTreeRejectionError("tree exceeds the depth bound")
        if directories is not None:
            directories.append(prefix)
        if max_entries is None:
            names = os.listdir(directory_fd)
        else:
            names = []
            with os.scandir(directory_fd) as entries:
                for entry in entries:
                    entry_count += 1
                    if entry_count > max_entries:
                        raise SafeTreeRejectionError("tree exceeds the entry bound")
                    names.append(entry.name)
        for name in sorted(names):
            canonical = _canonical_name(name)
            if canonical in (".", ".."):
                raise SafeTreeRejectionError(
                    f"tree entry name is not a POSIX relative name: {name!r}"
                )
            relative_path = f"{prefix}/{name}" if prefix else name
            info = _lstat_entry(directory_fd, name)
            if stat.S_ISREG(info.st_mode):
                identity = (info.st_dev, info.st_ino)
                if identity in seen_identities:
                    raise SafeTreeRejectionError(
                        f"duplicate hard link: {relative_path!r}"
                    )
                seen_identities.add(identity)
                canonical_path = unicodedata.normalize("NFC", relative_path)
                if canonical_path in seen_canonical:
                    raise SafeTreeRejectionError(
                        f"duplicate canonical path: {relative_path!r}"
                    )
                seen_canonical.add(canonical_path)
                yield RegularFileRow(
                    relative_path,
                    info.st_size,
                    info.st_dev,
                    info.st_ino,
                    info.st_mode,
                    info.st_uid,
                    info.st_nlink,
                    info.st_mtime_ns,
                    info.st_ctime_ns,
                )
            elif stat.S_ISDIR(info.st_mode):
                child = _open_child_directory(directory_fd, name, info)
                try:
                    yield from recurse(child, relative_path, depth + 1)
                finally:
                    os.close(child)
            else:
                raise SafeTreeRejectionError(
                    "tree entry is not a regular file or directory: "
                    f"{relative_path!r}"
                )

    yield from recurse(root_fd, "", 0)


def validate_relative_path(relative_path: str) -> None:
    if not isinstance(relative_path, str) or not relative_path:
        raise SafeTreePathError(f"unsafe relative path: {relative_path!r}")
    if relative_path.startswith("/"):
        raise SafeTreePathError(f"unsafe relative path: {relative_path!r}")
    for component in relative_path.split("/"):
        if component in ("", ".", "..") or "\x00" in component:
            raise SafeTreePathError(f"unsafe relative path: {relative_path!r}")
        try:
            component.encode("utf-8")
        except UnicodeEncodeError as exc:
            raise SafeTreePathError(
                f"unsafe relative path: {relative_path!r}"
            ) from exc


def _open_regular_file(
    root_fd: int,
    relative_path: str,
    *,
    expected: RegularFileRow | None = None,
) -> tuple[int, os.stat_result]:
    """Open one regular file beneath root_fd without following any symlink.

    Every intermediate component is opened as a no-follow directory and every
    descriptor is close-on-exec; only the returned descriptor stays open.
    Open-window failures raise SafeTreeError: a vanished entry becomes
    SafeTreePathChangedError when an expected row binds identity, and
    SafeTreeRejectionError otherwise.
    """
    validate_relative_path(relative_path)
    components = relative_path.split("/")
    parent_fd = root_fd
    owned: list[int] = []
    try:
        for component in components[:-1]:
            try:
                child = os.open(component, _NOFOLLOW_DIRECTORY, dir_fd=parent_fd)
            except OSError as exc:
                if exc.errno == errno.ENOENT:
                    if expected is not None:
                        raise SafeTreePathChangedError(
                            f"tree entry changed identity: {relative_path!r}"
                        ) from exc
                    raise SafeTreeRejectionError(
                        f"path is missing: {relative_path!r}"
                    ) from exc
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise SafeTreeRejectionError(
                        f"path is not a directory: {relative_path!r}"
                    ) from exc
                raise SafeTreeRejectionError(
                    f"path cannot be opened: {relative_path!r}"
                ) from exc
            owned.append(child)
            parent_fd = child
        try:
            descriptor = os.open(
                components[-1], _NOFOLLOW_REGULAR, dir_fd=parent_fd
            )
        except OSError as exc:
            if exc.errno == errno.ENOENT:
                if expected is not None:
                    raise SafeTreePathChangedError(
                        f"tree entry changed identity: {relative_path!r}"
                    ) from exc
                raise SafeTreeRejectionError(
                    f"path is missing: {relative_path!r}"
                ) from exc
            if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                raise SafeTreeRejectionError(
                    f"not a regular file: {relative_path!r}"
                ) from exc
            raise SafeTreeRejectionError(
                f"path cannot be opened: {relative_path!r}"
            ) from exc
        try:
            kind = os.fstat(descriptor)
        except OSError as exc:
            os.close(descriptor)
            raise SafeTreeRejectionError(
                f"regular file cannot be inspected: {relative_path!r}"
            ) from exc
        if not stat.S_ISREG(kind.st_mode):
            os.close(descriptor)
            raise SafeTreeRejectionError(
                f"not a regular file: {relative_path!r}"
            )
        return descriptor, kind
    finally:
        for owned_fd in reversed(owned):
            os.close(owned_fd)


def _check_identity(
    kind: os.stat_result,
    expected: RegularFileRow | None,
    relative_path: str,
) -> None:
    if expected is None:
        return
    observed = (
        kind.st_dev,
        kind.st_ino,
        kind.st_size,
        kind.st_mode,
        kind.st_uid,
        kind.st_nlink,
        kind.st_mtime_ns,
        kind.st_ctime_ns,
    )
    admitted = (
        expected.device,
        expected.inode,
        expected.size_bytes,
        expected.mode,
        expected.uid,
        expected.link_count,
        expected.mtime_ns,
        expected.ctime_ns,
    )
    if observed != admitted:
        raise SafeTreePathChangedError(
            f"tree entry changed identity: {relative_path!r}"
        )


def hash_regular_file(
    root_fd: int,
    relative_path: str,
    *,
    expected: RegularFileRow | None = None,
) -> str:
    """Stream one stable regular file through SHA-256."""
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        digest = sha256()
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
        _check_identity(os.fstat(descriptor), expected, relative_path)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


def read_regular_file(
    root_fd: int,
    relative_path: str,
    *,
    expected: RegularFileRow | None = None,
    max_bytes: int | None = None,
) -> bytes:
    """Read one stable regular file, optionally under a hard byte bound."""
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        if max_bytes is not None and kind.st_size > max_bytes:
            raise SafeTreeRejectionError(
                f"tree entry exceeds the byte bound: {relative_path!r}"
            )
        chunks: list[bytes] = []
        total = 0
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise SafeTreeRejectionError(
                    f"tree entry exceeds the byte bound: {relative_path!r}"
                )
            chunks.append(chunk)
        _check_identity(os.fstat(descriptor), expected, relative_path)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def copy_regular_file(
    root_fd: int,
    relative_path: str,
    destination_fd: int,
    *,
    expected: RegularFileRow | None = None,
    max_bytes: int | None = None,
) -> int:
    """Stream one stable regular file under an optional hard byte bound."""
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        if max_bytes is not None and kind.st_size > max_bytes:
            raise SafeTreeRejectionError(
                f"tree entry exceeds the byte bound: {relative_path!r}"
            )
        total = 0
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                break
            if max_bytes is not None and total + len(chunk) > max_bytes:
                raise SafeTreeRejectionError(
                    f"tree entry exceeds the byte bound: {relative_path!r}"
                )
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(destination_fd, remaining)
                if written <= 0:
                    raise OSError("safe-tree copy made no progress")
                remaining = remaining[written:]
                total += written
        _check_identity(os.fstat(descriptor), expected, relative_path)
        return total
    finally:
        os.close(descriptor)


def remove_tree_contents(directory_fd: int) -> None:
    """Best-effort descriptor-relative removal without following symlinks."""
    from .safe_tree_cleanup import remove_tree_contents as remove

    remove(directory_fd)


__all__ = [
    "RegularFileRow",
    "SafeTreeError",
    "SafeTreePathChangedError",
    "SafeTreePathError",
    "SafeTreeRejectionError",
    "copy_regular_file",
    "open_directory",
    "hash_regular_file",
    "remove_tree_contents",
    "read_regular_file",
    "validate_relative_path",
    "walk_regular_files",
]
