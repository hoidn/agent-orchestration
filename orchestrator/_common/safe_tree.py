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


def walk_regular_files(root_fd: int):
    """Yield RegularFileRow for each regular file beneath root_fd.

    Rows are deterministic: entries are visited in UTF-8 byte order and paths
    are POSIX-relative. Symlinks, devices, FIFOs, sockets, hard-linked
    duplicates, undecodable names, and duplicate canonical (NFC) paths are
    rejected; every descriptor opened here is close-on-exec.
    """
    seen_identities: set[tuple[int, int]] = set()
    seen_canonical: set[str] = set()

    def recurse(directory_fd: int, prefix: str):
        for name in sorted(os.listdir(directory_fd)):
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
                )
            elif stat.S_ISDIR(info.st_mode):
                child = _open_child_directory(directory_fd, name, info)
                try:
                    yield from recurse(child, relative_path)
                finally:
                    os.close(child)
            else:
                raise SafeTreeRejectionError(
                    "tree entry is not a regular file or directory: "
                    f"{relative_path!r}"
                )

    yield from recurse(root_fd, "")


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
    if expected is not None and (kind.st_dev, kind.st_ino) != (
        expected.device,
        expected.inode,
    ):
        raise SafeTreePathChangedError(
            f"tree entry changed identity: {relative_path!r}"
        )


def hash_regular_file(
    root_fd: int,
    relative_path: str,
    *,
    expected: RegularFileRow | None = None,
) -> str:
    """Stream one regular file through SHA-256 and return the hex digest."""
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        digest = sha256()
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                return digest.hexdigest()
            digest.update(chunk)
    finally:
        os.close(descriptor)


def read_regular_file(
    root_fd: int,
    relative_path: str,
    *,
    expected: RegularFileRow | None = None,
) -> bytes:
    """Read one regular file's bytes; callers bound size expectations."""
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(descriptor)


def copy_regular_file(
    root_fd: int,
    relative_path: str,
    destination_fd: int,
    *,
    expected: RegularFileRow | None = None,
) -> int:
    """Stream one regular file into a caller-owned destination descriptor.

    The destination descriptor is never closed or created here; the number of
    bytes written is returned.
    """
    descriptor, kind = _open_regular_file(
        root_fd, relative_path, expected=expected
    )
    try:
        _check_identity(kind, expected, relative_path)
        total = 0
        while True:
            chunk = os.read(descriptor, _CHUNK_SIZE)
            if not chunk:
                return total
            remaining = memoryview(chunk)
            while remaining:
                written = os.write(destination_fd, remaining)
                if written <= 0:
                    raise OSError("safe-tree copy made no progress")
                remaining = remaining[written:]
                total += written
    finally:
        os.close(descriptor)


__all__ = [
    "RegularFileRow",
    "SafeTreeError",
    "SafeTreePathChangedError",
    "SafeTreePathError",
    "SafeTreeRejectionError",
    "copy_regular_file",
    "hash_regular_file",
    "read_regular_file",
    "validate_relative_path",
    "walk_regular_files",
]
