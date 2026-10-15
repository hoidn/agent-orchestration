"""Deterministic run-reference workspace primitives."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
import sys
from collections.abc import Collection, Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path, PurePosixPath

from ..._common.io_atomic import durable_atomic_write
from ..._common.safe_tree import (
    SafeTreeError,
    _open_child_directory,
    _open_regular_file,
    remove_tree_contents,
)
from ..workspace_files import _write_bytes
from .contracts import canonical_json_bytes, canonical_sha256


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


def _regular_file_stability_fields(identity: os.stat_result) -> tuple[int, ...]:
    return (
        identity.st_dev,
        identity.st_ino,
        identity.st_mode,
        identity.st_size,
        identity.st_mtime_ns,
        identity.st_ctime_ns,
    )


def _hash_regular_file(path: Path, expected: os.stat_result) -> tuple[int, str]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise WorkspaceFreezeError(f"tree entry changed type before hashing: {path}")
        if (opened.st_dev, opened.st_ino) != (expected.st_dev, expected.st_ino):
            raise WorkspaceFreezeError(f"tree entry changed identity before hashing: {path}")
        admitted_fields = _regular_file_stability_fields(expected)
        opened_fields = _regular_file_stability_fields(opened)
        if opened_fields != admitted_fields:
            raise WorkspaceFreezeError(f"tree entry changed before hashing: {path}")
        digest = hashlib.sha256()
        size = 0
        while True:
            chunk = os.read(descriptor, _HASH_CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
            size += len(chunk)
        finished = os.fstat(descriptor)
        finished_fields = _regular_file_stability_fields(finished)
        if (
            finished_fields != admitted_fields
            or finished_fields != opened_fields
            or size != finished.st_size
        ):
            raise WorkspaceFreezeError(f"tree entry changed while hashing: {path}")
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


# Confined workspace copier (design D-c, D-f, D-h, R1, N5, N6).
#
# The copier mirrors one tree onto another through retained root descriptors:
# every component is opened no-follow beneath its root, source entries are
# pinned to the source root's st_dev, and symlink targets are copied as
# strings. Dependencies: the caller owns both root descriptors and guarantees
# guest quiescence; the checkpoint header lives outside the clone.

_RESERVED_ROOTS = (".git", ".orchestrate")
_ESCAPE = "run_ref_environment_escape_rejected"
_CHANGED = "run_ref_environment_changed"
_HEADER_SCHEMA = "run_ref_checkpoint_header.v1"
_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_EXCLUSIVE_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC


class RunRefCheckpointError(ValueError):
    """A copier or checkpoint-header refusal carrying its diagnostic code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class CopyResult:
    manifest: TreeManifest
    skipped_special: int
    bytes_copied: int


@dataclass(frozen=True)
class CheckpointHeader:
    state: str
    effect_identity: str
    ordinal: int
    manifest_digest: str | None
    skipped_special: int = 0


@dataclass
class _Walk:
    source_device: int
    destination_device: int | None
    admit_hardlinks: bool
    remaining_bytes: int
    entries: list[TreeEntry] = field(default_factory=list)
    skipped: int = 0
    copied: int = 0


def _escape(detail: str) -> RunRefCheckpointError:
    return RunRefCheckpointError(_ESCAPE, detail)


def _lstat(directory_fd: int, name: str) -> os.stat_result | None:
    try:
        return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None


def _remove_entry(directory_fd: int, name: str) -> None:
    info = _lstat(directory_fd, name)
    if info is None:
        return
    if not stat.S_ISDIR(info.st_mode):
        os.unlink(name, dir_fd=directory_fd)
        return
    child = os.open(name, _NOFOLLOW_DIRECTORY, dir_fd=directory_fd)
    try:
        remove_tree_contents(child)
    finally:
        os.close(child)
    os.rmdir(name, dir_fd=directory_fd)


def _source_entries(walk: _Walk, source_fd: int, prefix: str) -> dict[str, os.stat_result]:
    entries: dict[str, os.stat_result] = {}
    for name in sorted(os.listdir(source_fd)):
        relative = f"{prefix}/{name}" if prefix else name
        if not prefix and name == ".git":
            continue  # the sanitized .git is bound read-only, never copied
        if not prefix and name in _RESERVED_ROOTS:
            raise _escape(f"entry under a reserved root: {relative!r}")
        _utf8_bytes(relative, label="tree entry path")
        info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        if info.st_dev != walk.source_device:
            raise _escape(f"entry is not on the pinned device: {relative!r}")
        entries[name] = info
    return entries


def _copy_file(walk: _Walk, source_fd: int, name: str, info: os.stat_result,
               destination_fd: int | None, mode: int) -> tuple[int, str]:
    descriptor, opened = _open_regular_file(source_fd, name, device=walk.source_device)
    temporary = f".rr-{secrets.token_hex(8)}.tmp"
    output: int | None = None
    try:
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise _escape(f"entry changed identity: {name!r}")
        if opened.st_nlink > 1 and not walk.admit_hardlinks:
            raise _escape(f"unsafe hard link on the host tree: {name!r}")
        if destination_fd is not None:
            existing = _lstat(destination_fd, name)
            if existing is not None and stat.S_ISDIR(existing.st_mode):
                _remove_entry(destination_fd, name)
            output = os.open(temporary, _EXCLUSIVE_WRITE, 0o600, dir_fd=destination_fd)
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(descriptor, _HASH_CHUNK_SIZE):
            size += len(chunk)
            if size > walk.remaining_bytes:
                raise _escape(f"workspace exceeds the byte bound at {name!r}")
            digest.update(chunk)
            if output is not None:
                _write_bytes(output, chunk)
        if output is not None:
            os.fchmod(output, mode)
            os.close(output)
            output = None
            os.replace(temporary, name, src_dir_fd=destination_fd, dst_dir_fd=destination_fd)
        walk.remaining_bytes -= size
        walk.copied += size
        return size, f"sha256:{digest.hexdigest()}"
    except BaseException:
        if output is not None:
            os.close(output)
            os.unlink(temporary, dir_fd=destination_fd)
        raise
    finally:
        os.close(descriptor)


def _copy_symlink(source_fd: int, name: str, destination_fd: int | None) -> str:
    target = os.readlink(name, dir_fd=source_fd)
    if destination_fd is not None:
        existing = _lstat(destination_fd, name)
        if existing is None or not stat.S_ISLNK(existing.st_mode) or (
            os.readlink(name, dir_fd=destination_fd) != target
        ):
            _remove_entry(destination_fd, name)
            os.symlink(target, name, dir_fd=destination_fd)
    return target


def _copy_directory(walk: _Walk, source_fd: int, name: str, info: os.stat_result,
                    destination_fd: int | None, relative: str, mode: int) -> None:
    source_child = _open_child_directory(source_fd, name, info)
    destination_child: int | None = None
    try:
        if destination_fd is not None:
            existing = _lstat(destination_fd, name)
            if existing is not None and not stat.S_ISDIR(existing.st_mode):
                _remove_entry(destination_fd, name)
                existing = None
            if existing is None:
                os.mkdir(name, 0o700, dir_fd=destination_fd)
            destination_child = os.open(name, _NOFOLLOW_DIRECTORY, dir_fd=destination_fd)
            if os.fstat(destination_child).st_dev != walk.destination_device:
                raise _escape(f"destination is not on the pinned device: {relative!r}")
            os.fchmod(destination_child, 0o700)
        _mirror(walk, source_child, destination_child, relative)
        if destination_child is not None:
            os.fchmod(destination_child, mode)
    finally:
        os.close(source_child)
        if destination_child is not None:
            os.close(destination_child)


def _mirror(walk: _Walk, source_fd: int, destination_fd: int | None, prefix: str) -> None:
    entries = _source_entries(walk, source_fd, prefix)
    if destination_fd is not None:
        for name in os.listdir(destination_fd):
            if prefix or name not in _RESERVED_ROOTS:
                info = entries.get(name)
                if info is None or stat.S_IFMT(info.st_mode) not in (stat.S_IFDIR, stat.S_IFREG, stat.S_IFLNK):
                    _remove_entry(destination_fd, name)
    for name, info in entries.items():
        relative = f"{prefix}/{name}" if prefix else name
        mode = stat.S_IMODE(info.st_mode) & 0o777
        if stat.S_ISDIR(info.st_mode):
            walk.entries.append(TreeEntry(relative, "directory", mode, 0, None))
            _copy_directory(walk, source_fd, name, info, destination_fd, relative, mode)
        elif stat.S_ISREG(info.st_mode):
            size, digest = _copy_file(walk, source_fd, name, info, destination_fd, mode)
            walk.entries.append(TreeEntry(relative, "file", mode, size, digest))
        elif stat.S_ISLNK(info.st_mode):
            target = _copy_symlink(source_fd, name, destination_fd)
            target_bytes = _utf8_bytes(target, label=f"symlink target for {relative!r}")
            walk.entries.append(TreeEntry(
                relative, "symlink", stat.S_IMODE(info.st_mode), len(target_bytes),
                f"sha256:{hashlib.sha256(target_bytes).hexdigest()}", target,
            ))
        else:
            walk.skipped += 1  # sockets, FIFOs and devices are skipped and counted


def _copy_tree(source_fd: int, destination_fd: int | None, *, admit_hardlinks: bool,
               max_bytes: int | None) -> CopyResult:
    walk = _Walk(
        source_device=os.fstat(source_fd).st_dev,
        destination_device=None if destination_fd is None else os.fstat(destination_fd).st_dev,
        admit_hardlinks=admit_hardlinks,
        remaining_bytes=sys.maxsize if max_bytes is None else max_bytes,
    )
    try:
        _mirror(walk, source_fd, destination_fd, "")
    except (SafeTreeError, WorkspaceFreezeError) as exc:
        raise _escape(str(exc)) from exc
    return CopyResult(manifest_from_entries(walk.entries), walk.skipped, walk.copied)


def workspace_manifest(root_fd: int) -> TreeManifest:
    """Freeze a tree beneath a retained descriptor, ``.git``/``.orchestrate`` excluded."""
    return _copy_tree(root_fd, None, admit_hardlinks=True, max_bytes=None).manifest


def seed_workspace(disk_root_fd: int, tmpfs_root_fd: int, *, max_bytes: int) -> CopyResult:
    """Seed the holder tmpfs from the host clone; host-disk hard links refuse."""
    return _copy_tree(disk_root_fd, tmpfs_root_fd, admit_hardlinks=False, max_bytes=max_bytes)


def _publish(header_path: Path, header: CheckpointHeader) -> CheckpointHeader:
    durable_atomic_write(Path(header_path), canonical_json_bytes({"schema": _HEADER_SCHEMA, **asdict(header)}))
    return header


def publish_initial_header(header_path: Path, baseline_digest: str) -> CheckpointHeader:
    """Publish the post-provisioning header: committed, effect ``none``, ordinal 0."""
    return _publish(header_path, CheckpointHeader("committed", "none", 0, baseline_digest))


def read_checkpoint_header(header_path: Path) -> CheckpointHeader:
    try:
        payload = json.loads(Path(header_path).read_bytes())
        if payload.pop("schema") != _HEADER_SCHEMA:
            raise ValueError("unknown checkpoint header schema")
        header = CheckpointHeader(**payload)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise RunRefCheckpointError(_CHANGED, f"checkpoint header is unreadable: {exc}") from exc
    digest_ok = (header.manifest_digest is None) == (header.state == "intent")
    if not (
        header.state in ("intent", "committed") and digest_ok
        and isinstance(header.effect_identity, str) and header.effect_identity
        and all(type(value) is int and value >= 0 for value in (header.ordinal, header.skipped_special))
        and (header.manifest_digest is None or isinstance(header.manifest_digest, str))
    ):
        raise RunRefCheckpointError(_CHANGED, f"checkpoint header is malformed: {header!r}")
    return header


def checkpoint_workspace(tmpfs_root_fd: int, disk_root_fd: int, header_path: Path, *,
                         effect_identity: str, ordinal: int, max_bytes: int) -> CheckpointHeader:
    """Copy the quiesced tmpfs onto the clone under the two-phase header (R1, N6).

    ``intent`` is durable before the first clone write; the clone's bytes are
    synced before ``committed`` carries the manifest digest. A failure leaves
    ``intent`` for :func:`preflight_checkpoint` to repair.
    """
    _publish(header_path, CheckpointHeader("intent", effect_identity, ordinal, None))
    result = _copy_tree(tmpfs_root_fd, disk_root_fd, admit_hardlinks=True, max_bytes=max_bytes)
    os.sync()  # ponytail: global sync; syncfs(disk_root_fd) via ctypes if it costs
    return _publish(header_path, CheckpointHeader(
        "committed", effect_identity, ordinal, result.manifest.digest, result.skipped_special,
    ))


def preflight_checkpoint(header_path: Path, disk_root_fd: int) -> CheckpointHeader:
    """Repair an ``intent`` header by re-freezing; verify a ``committed`` one.

    Run only after the recorded scope is killed and empty (N4). Choosing
    which committed attempt a header may name is the resume owner's rule.
    """
    header = read_checkpoint_header(header_path)
    manifest = workspace_manifest(disk_root_fd)
    if header.state == "intent":
        os.sync()
        return _publish(header_path, CheckpointHeader(
            "committed", header.effect_identity, header.ordinal, manifest.digest,
        ))
    if manifest.digest != header.manifest_digest:
        raise RunRefCheckpointError(_CHANGED, "clone no longer matches its committed checkpoint header")
    return header


__all__ = [
    "CheckpointHeader",
    "CopyResult",
    "RunRefCheckpointError",
    "TreeEntry",
    "TreeManifest",
    "WorkspaceFreezeError",
    "checkpoint_workspace",
    "freeze_tree",
    "manifest_from_entries",
    "preflight_checkpoint",
    "publish_initial_header",
    "read_checkpoint_header",
    "seed_workspace",
    "workspace_manifest",
]
