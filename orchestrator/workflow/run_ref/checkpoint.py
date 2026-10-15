"""Confined run-ref workspace copier and two-phase checkpoint header.

Design D-c, D-f, D-h, R1, N5, N6. The copier mirrors one tree onto another
through retained root descriptors: every component is opened no-follow
beneath its root, source entries are pinned to the source root's st_dev, and
symlink targets are copied as strings. Dependencies: the caller owns both
root descriptors and guarantees guest quiescence; the checkpoint header lives
in the control root outside the clone.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..._common.io_atomic import durable_atomic_write
from ..._common.safe_tree import (
    SafeTreeError,
    open_child_directory,
    open_regular_file,
    remove_tree_contents,
)
from .contracts import canonical_json_bytes
from .workspace import TreeEntry, TreeManifest, WorkspaceFreezeError, manifest_from_entries

_HASH_CHUNK_SIZE = 1024 * 1024

_RESERVED_ROOTS = (".git", ".orchestrate")
_ESCAPE = "run_ref_environment_escape_rejected"
_CHANGED = "run_ref_environment_changed"
_HEADER_SCHEMA = "run_ref_checkpoint_header.v1"
_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_EXCLUSIVE_WRITE = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC
# Copier temporaries; a source entry with this shape refuses, so intent repair
# can remove every such name from the clone without touching guest data.
_TEMPORARY = re.compile(r"\.rr-[0-9a-f]{16}\.tmp")
# Profile constants of `run_ref_confinement.v1` (workspace trees). The depth
# bound keeps recursion and open descriptors (two per level) finite: the copy
# refuses before creating a directory deeper than it, so the clone never
# exceeds it and repair's walk under the same bound cannot wedge. The entry
# bound applies to every checkpoint of the guest tmpfs, to seeding and to the
# provisioned clone (`confinement.provision_confined_child`); repair stays
# unbounded because the clone holds at most the previous checkpoint plus one
# bounded partial copy. A refusal of the guest tmpfs is guest-caused
# (`run_ref_environment_escape_rejected`); the same refusal of the clone, which
# only the host writes, is host-side corruption (`run_ref_environment_changed`).
MAX_TREE_DEPTH = 128
MAX_CHECKPOINT_ENTRIES = 262_144


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
    remaining_entries: int
    repair: bool
    source_code: str = _ESCAPE  # code of a refused source tree: escape (guest tmpfs) or changed (clone)
    entries: list[TreeEntry] = field(default_factory=list)
    skipped: int = 0
    copied: int = 0


def _escape(detail: str) -> RunRefCheckpointError:
    return RunRefCheckpointError(_ESCAPE, detail)


def _write_all(descriptor: int, chunk: bytes) -> None:
    view = memoryview(chunk)
    while view:
        view = view[os.write(descriptor, view):]


def _utf8(text: str, label: str) -> bytes:
    try:
        return text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise _escape(f"{label} is not valid UTF-8: {text!r}") from exc


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
        walk.remaining_entries -= 1
        if walk.remaining_entries < 0:
            raise RunRefCheckpointError(walk.source_code, f"workspace exceeds the entry bound at {relative!r}")
        _utf8(relative, "tree entry path")
        info = os.stat(name, dir_fd=source_fd, follow_symlinks=False)
        if _TEMPORARY.fullmatch(name):
            if not walk.repair or stat.S_ISDIR(info.st_mode):
                raise RunRefCheckpointError(walk.source_code, f"entry uses the copier's temporary name: {relative!r}")
            os.unlink(name, dir_fd=source_fd)  # an interrupted copy's temporary
            continue
        if info.st_dev != walk.source_device:
            raise _escape(f"entry is not on the pinned device: {relative!r}")
        entries[name] = info
    return entries


def _copy_file(walk: _Walk, source_fd: int, name: str, info: os.stat_result,
               destination_fd: int | None, mode: int) -> tuple[int, str]:
    descriptor, opened = open_regular_file(source_fd, name, device=walk.source_device)
    temporary = f".rr-{secrets.token_hex(8)}.tmp"
    output: int | None = None
    created = False
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
            created = True
        digest, size = hashlib.sha256(), 0
        while chunk := os.read(descriptor, _HASH_CHUNK_SIZE):
            size += len(chunk)
            if size > walk.remaining_bytes:
                raise _escape(f"workspace exceeds the byte bound at {name!r}")
            digest.update(chunk)
            if output is not None:
                _write_all(output, chunk)
        if output is not None:
            os.fchmod(output, mode)
            os.close(output)
            output = None
            os.replace(temporary, name, src_dir_fd=destination_fd, dst_dir_fd=destination_fd)
            created = False
        walk.remaining_bytes -= size
        walk.copied += size
        return size, f"sha256:{digest.hexdigest()}"
    except BaseException:
        if output is not None:
            os.close(output)
        if created:
            try:
                os.unlink(temporary, dir_fd=destination_fd)
            except FileNotFoundError:
                pass
        raise
    finally:
        os.close(descriptor)


def _copy_symlink(source_fd: int, name: str, destination_fd: int | None, relative: str) -> tuple[str, bytes]:
    target = os.readlink(name, dir_fd=source_fd)
    target_bytes = _utf8(target, f"symlink target for {relative!r}")  # before any write
    if destination_fd is not None:
        existing = _lstat(destination_fd, name)
        if existing is None or not stat.S_ISLNK(existing.st_mode) or (
            os.readlink(name, dir_fd=destination_fd) != target
        ):
            _remove_entry(destination_fd, name)
            os.symlink(target, name, dir_fd=destination_fd)
    return target, target_bytes


def _copy_directory(walk: _Walk, source_fd: int, name: str, info: os.stat_result,
                    destination_fd: int | None, relative: str, mode: int, depth: int) -> None:
    source_child = open_child_directory(source_fd, name, info)
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
        _mirror(walk, source_child, destination_child, relative, depth)
        if destination_child is not None:
            os.fchmod(destination_child, mode)
    finally:
        os.close(source_child)
        if destination_child is not None:
            os.close(destination_child)


def _mirror(walk: _Walk, source_fd: int, destination_fd: int | None, prefix: str, depth: int) -> None:
    entries = _source_entries(walk, source_fd, prefix)
    if destination_fd is not None:
        for name in os.listdir(destination_fd):
            if prefix or name not in _RESERVED_ROOTS:
                info = entries.get(name)
                if info is None or stat.S_IFMT(info.st_mode) not in (stat.S_IFDIR, stat.S_IFREG, stat.S_IFLNK):
                    _remove_entry(destination_fd, name)
    for name, info in entries.items():
        relative = f"{prefix}/{name}" if prefix else name
        # A copy masks modes; a pure manifest records what freeze_tree records.
        mode = stat.S_IMODE(info.st_mode) & (0o7777 if destination_fd is None else 0o777)
        if stat.S_ISDIR(info.st_mode):
            if depth >= MAX_TREE_DEPTH:
                raise _escape(f"workspace exceeds the depth bound at {relative!r}")
            walk.entries.append(TreeEntry(relative, "directory", mode, 0, None))
            _copy_directory(walk, source_fd, name, info, destination_fd, relative, mode, depth + 1)
        elif stat.S_ISREG(info.st_mode):
            size, digest = _copy_file(walk, source_fd, name, info, destination_fd, mode)
            walk.entries.append(TreeEntry(relative, "file", mode, size, digest))
        elif stat.S_ISLNK(info.st_mode):
            target, target_bytes = _copy_symlink(source_fd, name, destination_fd, relative)
            walk.entries.append(TreeEntry(
                relative, "symlink", stat.S_IMODE(info.st_mode), len(target_bytes),
                f"sha256:{hashlib.sha256(target_bytes).hexdigest()}", target,
            ))
        else:
            walk.skipped += 1  # sockets, FIFOs and devices are skipped and counted


def _copy_tree(source_fd: int, destination_fd: int | None, *, admit_hardlinks: bool,
               max_bytes: int | None, max_entries: int | None = None,
               repair: bool = False, source_code: str = _ESCAPE) -> CopyResult:
    walk = _Walk(
        source_device=os.fstat(source_fd).st_dev,
        destination_device=None if destination_fd is None else os.fstat(destination_fd).st_dev,
        admit_hardlinks=admit_hardlinks,
        remaining_bytes=sys.maxsize if max_bytes is None else max_bytes,
        remaining_entries=sys.maxsize if max_entries is None else max_entries,
        repair=repair,
        source_code=source_code,
    )
    try:
        _mirror(walk, source_fd, destination_fd, "", 0)
    except (SafeTreeError, WorkspaceFreezeError) as exc:
        raise _escape(str(exc)) from exc
    return CopyResult(manifest_from_entries(walk.entries), walk.skipped, walk.copied)


def workspace_manifest(root_fd: int, *, clone: bool = False) -> TreeManifest:
    """Freeze a tree beneath a retained descriptor, ``.git``/``.orchestrate`` excluded.

    ``clone`` codes a refused tree as host-side corruption rather than guest-caused.
    """
    return _copy_tree(root_fd, None, admit_hardlinks=True, max_bytes=None,
                      source_code=_CHANGED if clone else _ESCAPE).manifest


def seed_workspace(disk_root_fd: int, tmpfs_root_fd: int, *, max_bytes: int,
                   max_entries: int = MAX_CHECKPOINT_ENTRIES) -> CopyResult:
    """Seed the holder tmpfs from the host clone; host-disk hard links refuse."""
    return _copy_tree(disk_root_fd, tmpfs_root_fd, admit_hardlinks=False, max_bytes=max_bytes,
                      max_entries=max_entries, source_code=_CHANGED)


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
                         effect_identity: str, ordinal: int, max_bytes: int,
                         max_entries: int = MAX_CHECKPOINT_ENTRIES) -> CheckpointHeader:
    """Copy the quiesced tmpfs onto the clone under the two-phase header (R1, N6).

    ``intent`` is durable before the first clone write; the clone's bytes are
    synced before ``committed`` carries the manifest digest. A failure or a
    kill leaves ``intent`` for :func:`preflight_checkpoint` to repair.
    """
    _publish(header_path, CheckpointHeader("intent", effect_identity, ordinal, None))
    result = _copy_tree(tmpfs_root_fd, disk_root_fd, admit_hardlinks=True,
                        max_bytes=max_bytes, max_entries=max_entries)
    os.sync()  # ponytail: global sync; syncfs(disk_root_fd) via ctypes if it costs
    return _publish(header_path, CheckpointHeader(
        "committed", effect_identity, ordinal, result.manifest.digest, result.skipped_special,
    ))


def preflight_checkpoint(header_path: Path, disk_root_fd: int) -> CheckpointHeader:
    """Repair an ``intent`` header by re-freezing; verify a ``committed`` one.

    Repair removes the copier's temporaries before freezing. Run only after
    the recorded scope is killed and empty (N4). Choosing which committed
    attempt a header may name is the resume owner's rule.
    """
    header = read_checkpoint_header(header_path)
    if header.state == "intent":
        result = _copy_tree(disk_root_fd, None, admit_hardlinks=True, max_bytes=None, repair=True)
        os.sync()
        return _publish(header_path, CheckpointHeader(
            "committed", header.effect_identity, header.ordinal,
            result.manifest.digest, result.skipped_special,
        ))
    if workspace_manifest(disk_root_fd, clone=True).digest != header.manifest_digest:
        raise RunRefCheckpointError(_CHANGED, "clone no longer matches its committed checkpoint header")
    return header


__all__ = [
    "CheckpointHeader",
    "CopyResult",
    "RunRefCheckpointError",
    "checkpoint_workspace",
    "preflight_checkpoint",
    "publish_initial_header",
    "read_checkpoint_header",
    "seed_workspace",
    "workspace_manifest",
]
