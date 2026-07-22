"""Fail-closed, conditional publication primitives for retirement records."""

from __future__ import annotations

import ctypes
import errno
import os
import stat
from dataclasses import dataclass
from pathlib import Path, PurePosixPath


RENAME_NOREPLACE = 1
RENAME_EXCHANGE = 2


class AtomicPublishError(RuntimeError):
    def __init__(
        self, code: str, detail: str = "", *, preserve_temporary: bool = False
    ) -> None:
        self.code = code
        self.detail = detail
        self.preserve_temporary = preserve_temporary
        super().__init__(f"{code}:{detail}" if detail else code)


@dataclass(frozen=True)
class BoundRegularFile:
    """Bytes and identity observed through one no-follow file descriptor."""

    device: int
    inode: int
    mode: int
    link_count: int
    uid: int
    gid: int
    size: int
    modified_ns: int
    changed_ns: int
    data: bytes


@dataclass(frozen=True)
class BoundLogicalParent:
    """Identity and no-follow route for an opened logical parent directory."""

    repository_root: Path
    relative_parts: tuple[str, ...]
    device: int
    inode: int


@dataclass(frozen=True)
class BoundPathEntry:
    """No-follow identity for a regular, symlink, directory, or special entry."""

    device: int
    inode: int
    mode: int
    link_count: int
    uid: int
    gid: int
    size: int
    modified_ns: int
    changed_ns: int
    payload: bytes | None


def _metadata_identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_mode,
        metadata.st_nlink,
        metadata.st_uid,
        metadata.st_gid,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def capture_regular_file_at(
    parent_fd: int,
    name: str,
    logical_path: str,
    *,
    missing_ok: bool,
) -> BoundRegularFile | None:
    """Capture one directory-relative regular file without following links."""

    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except FileNotFoundError:
        if missing_ok:
            return None
        raise AtomicPublishError("final_slot_missing", logical_path)
    except OSError as exc:
        raise AtomicPublishError("final_slot_not_regular", logical_path) from exc
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise AtomicPublishError("final_slot_not_regular", logical_path)
        with os.fdopen(os.dup(descriptor), "rb") as stream:
            data = stream.read()
        after = os.fstat(descriptor)
        if _metadata_identity(before) != _metadata_identity(after):
            raise AtomicPublishError("unstable_capture", logical_path)
        return BoundRegularFile(
            device=after.st_dev,
            inode=after.st_ino,
            mode=after.st_mode,
            link_count=after.st_nlink,
            uid=after.st_uid,
            gid=after.st_gid,
            size=after.st_size,
            modified_ns=after.st_mtime_ns,
            changed_ns=after.st_ctime_ns,
            data=data,
        )
    finally:
        os.close(descriptor)


def capture_path_entry_at(
    parent_fd: int, name: str, logical_path: str, *, missing_ok: bool
) -> BoundPathEntry | None:
    try:
        before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise AtomicPublishError("final_slot_missing", logical_path)
    payload: bytes | None
    if stat.S_ISREG(before.st_mode):
        regular = capture_regular_file_at(
            parent_fd, name, logical_path, missing_ok=False
        )
        assert regular is not None
        return BoundPathEntry(
            regular.device,
            regular.inode,
            regular.mode,
            regular.link_count,
            regular.uid,
            regular.gid,
            regular.size,
            regular.modified_ns,
            regular.changed_ns,
            regular.data,
        )
    if stat.S_ISLNK(before.st_mode):
        try:
            target = os.readlink(name, dir_fd=parent_fd)
        except OSError as exc:
            raise AtomicPublishError("unstable_capture", logical_path) from exc
        payload = os.fsencode(target)
    else:
        payload = None
    try:
        after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except OSError as exc:
        raise AtomicPublishError("unstable_capture", logical_path) from exc
    if _metadata_identity(before) != _metadata_identity(after):
        raise AtomicPublishError("unstable_capture", logical_path)
    return BoundPathEntry(
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_nlink,
        after.st_uid,
        after.st_gid,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
        payload,
    )


_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC_RENAMEAT2 = getattr(_LIBC, "renameat2", None)
if _LIBC_RENAMEAT2 is not None:
    _LIBC_RENAMEAT2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    _LIBC_RENAMEAT2.restype = ctypes.c_int


def _renameat2(parent_fd: int, old_name: str, new_name: str, flags: int) -> None:
    """Invoke Linux renameat2 without providing a weaker fallback."""

    if _LIBC_RENAMEAT2 is None:
        raise AtomicPublishError("atomic_rename_unavailable")
    ctypes.set_errno(0)
    result = _LIBC_RENAMEAT2(
        parent_fd,
        os.fsencode(old_name),
        parent_fd,
        os.fsencode(new_name),
        flags,
    )
    if result == 0:
        return
    error_number = ctypes.get_errno()
    if error_number in {errno.ENOSYS, errno.EINVAL, errno.EOPNOTSUPP}:
        raise AtomicPublishError("atomic_rename_unavailable")
    raise OSError(error_number, os.strerror(error_number))


def _same_bound_file(left: BoundRegularFile, right: BoundRegularFile) -> bool:
    return (
        left.device == right.device
        and left.inode == right.inode
        and left.mode == right.mode
        and left.link_count == right.link_count
        and left.uid == right.uid
        and left.gid == right.gid
        and left.size == right.size
        and left.modified_ns == right.modified_ns
        and left.changed_ns == right.changed_ns
        and left.data == right.data
    )


def _same_file_after_rename(left: BoundRegularFile, right: BoundRegularFile) -> bool:
    """Compare an inode across rename, which advances ctime on Linux."""
    return replace_changed_ns(left, right.changed_ns) == right


def replace_changed_ns(value: BoundRegularFile, changed_ns: int) -> BoundRegularFile:
    return BoundRegularFile(
        device=value.device,
        inode=value.inode,
        mode=value.mode,
        link_count=value.link_count,
        uid=value.uid,
        gid=value.gid,
        size=value.size,
        modified_ns=value.modified_ns,
        changed_ns=changed_ns,
        data=value.data,
    )


def _same_path_entry(left: BoundPathEntry, right: BoundPathEntry) -> bool:
    return left == right


def _same_path_entry_after_rename(
    left: BoundPathEntry, right: BoundPathEntry
) -> bool:
    return (
        left.device == right.device
        and left.inode == right.inode
        and left.mode == right.mode
        and left.link_count == right.link_count
        and left.uid == right.uid
        and left.gid == right.gid
        and left.size == right.size
        and left.modified_ns == right.modified_ns
        and left.payload == right.payload
    )


def bind_logical_parent(
    repository_root: Path, relative_parent: Path, parent_fd: int
) -> BoundLogicalParent:
    text = relative_parent.as_posix()
    parsed = PurePosixPath(text)
    if (
        relative_parent.is_absolute()
        or text not in {"", "."} and any(part in {"", ".", ".."} for part in parsed.parts)
    ):
        raise AtomicPublishError("logical_parent_invalid", text)
    metadata = os.fstat(parent_fd)
    if not stat.S_ISDIR(metadata.st_mode):
        raise AtomicPublishError("logical_parent_invalid", text)
    binding = BoundLogicalParent(
        repository_root=repository_root,
        relative_parts=() if text in {"", "."} else tuple(parsed.parts),
        device=metadata.st_dev,
        inode=metadata.st_ino,
    )
    if not logical_parent_matches(binding):
        raise AtomicPublishError("logical_parent_changed", text)
    return binding


def logical_parent_matches(binding: BoundLogicalParent) -> bool:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    descriptor = -1
    try:
        descriptor = os.open(binding.repository_root, flags)
        for component in binding.relative_parts:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        metadata = os.fstat(descriptor)
        return (
            stat.S_ISDIR(metadata.st_mode)
            and metadata.st_dev == binding.device
            and metadata.st_ino == binding.inode
        )
    except OSError:
        return False
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _conditional_publish_boundary(
    _stage: str, _parent_fd: int, _temporary_name: str, _destination_name: str
) -> None:
    """No-op deterministic concurrency boundary for adversarial tests."""


def _conditional_quarantine_boundary(
    _stage: str, _parent_fd: int, _destination_name: str, _quarantine_name: str
) -> None:
    """No-op deterministic concurrency boundary for quarantine tests."""


def _quarantine_entry(
    parent_fd: int,
    temporary_name: str,
    destination_name: str,
    logical_path: str,
) -> str | None:
    try:
        captured = capture_path_entry_at(
            parent_fd, temporary_name, logical_path, missing_ok=True
        )
    except AtomicPublishError:
        captured = None
    if captured is None:
        return None
    base = (
        f".{destination_name}.recovery-"
        f"{captured.device:x}-{captured.inode:x}-{captured.changed_ns:x}"
    )
    for suffix in range(128):
        quarantine = base if suffix == 0 else f"{base}-{suffix}"
        try:
            _renameat2(
                parent_fd, temporary_name, quarantine, RENAME_NOREPLACE
            )
            os.fsync(parent_fd)
            return quarantine
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                continue
            break
        except AtomicPublishError:
            break
    raise AtomicPublishError(
        "atomic_recovery_failed", logical_path, preserve_temporary=True
    )


def conditional_quarantine_file_at(
    parent_fd: int,
    destination_name: str,
    expected: BoundRegularFile,
    logical_path: str,
    *,
    logical_parent: BoundLogicalParent | None = None,
) -> str:
    """Move an exact owned regular entry aside without deleting raced bytes."""
    if logical_parent is not None and not logical_parent_matches(logical_parent):
        raise AtomicPublishError("logical_parent_changed", logical_path)
    base = (
        f".{destination_name}.recovery-"
        f"{expected.device:x}-{expected.inode:x}-{expected.changed_ns:x}"
    )
    quarantine = ""
    for suffix in range(128):
        candidate = base if suffix == 0 else f"{base}-{suffix}"
        try:
            _renameat2(
                parent_fd, destination_name, candidate, RENAME_NOREPLACE
            )
            quarantine = candidate
            break
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                continue
            raise AtomicPublishError("atomic_recovery_failed", logical_path) from exc
    if not quarantine:
        raise AtomicPublishError("atomic_recovery_failed", logical_path)
    _conditional_quarantine_boundary(
        "after_quarantine_move", parent_fd, destination_name, quarantine
    )
    if logical_parent is not None and not logical_parent_matches(logical_parent):
        raise AtomicPublishError(
            "logical_parent_changed", logical_path, preserve_temporary=True
        )
    try:
        moved = capture_regular_file_at(
            parent_fd, quarantine, logical_path, missing_ok=False
        )
    except AtomicPublishError as exc:
        raise AtomicPublishError("atomic_recovery_failed", logical_path) from exc
    assert moved is not None
    if _same_file_after_rename(expected, moved):
        destination = capture_path_entry_at(
            parent_fd, destination_name, logical_path, missing_ok=True
        )
        if destination is not None:
            os.fsync(parent_fd)
            raise AtomicPublishError(
                "concurrent_mutation", logical_path, preserve_temporary=True
            )
        if logical_parent is not None and not logical_parent_matches(logical_parent):
            raise AtomicPublishError(
                "logical_parent_changed", logical_path, preserve_temporary=True
            )
        os.fsync(parent_fd)
        return quarantine
    try:
        _renameat2(
            parent_fd, quarantine, destination_name, RENAME_NOREPLACE
        )
    except BaseException as exc:
        raise AtomicPublishError("atomic_recovery_failed", logical_path) from exc
    raise AtomicPublishError("concurrent_mutation", logical_path)


def _rollback_exchange(
    parent_fd: int,
    temporary_name: str,
    destination_name: str,
    published: BoundRegularFile,
    displaced: BoundPathEntry,
    logical_path: str,
) -> None:
    _conditional_publish_boundary(
        "before_rollback", parent_fd, temporary_name, destination_name
    )
    try:
        current_destination = capture_path_entry_at(
            parent_fd, destination_name, logical_path, missing_ok=False
        )
        current_temporary = capture_path_entry_at(
            parent_fd, temporary_name, logical_path, missing_ok=False
        )
    except AtomicPublishError:
        _quarantine_entry(
            parent_fd, temporary_name, destination_name, logical_path
        )
        raise AtomicPublishError("concurrent_mutation", logical_path)
    assert current_destination is not None and current_temporary is not None
    if not (
        _same_path_entry(
            BoundPathEntry(
                published.device,
                published.inode,
                published.mode,
                published.link_count,
                published.uid,
                published.gid,
                published.size,
                published.modified_ns,
                published.changed_ns,
                published.data,
            ),
            current_destination,
        )
        and _same_path_entry(displaced, current_temporary)
    ):
        _quarantine_entry(
            parent_fd, temporary_name, destination_name, logical_path
        )
        raise AtomicPublishError("concurrent_mutation", logical_path)

    displaced_before_link = displaced
    recovery_base = (
        f".{destination_name}.displaced-recovery-"
        f"{displaced.device:x}-{displaced.inode:x}"
    )
    recovery_name = ""
    for suffix in range(128):
        candidate = recovery_base if suffix == 0 else f"{recovery_base}-{suffix}"
        try:
            os.link(
                temporary_name,
                candidate,
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
                follow_symlinks=False,
            )
            recovery_name = candidate
            break
        except FileExistsError:
            continue
        except OSError as exc:
            raise AtomicPublishError(
                "atomic_recovery_failed",
                logical_path,
                preserve_temporary=True,
            ) from exc
    if not recovery_name:
        raise AtomicPublishError(
            "atomic_recovery_failed", logical_path, preserve_temporary=True
        )
    try:
        displaced_after_link = capture_path_entry_at(
            parent_fd, temporary_name, logical_path, missing_ok=False
        )
        recovery_entry = capture_path_entry_at(
            parent_fd, recovery_name, logical_path, missing_ok=False
        )
    except AtomicPublishError as exc:
        raise AtomicPublishError(
            "atomic_recovery_failed", logical_path, preserve_temporary=True
        ) from exc
    assert displaced_after_link is not None and recovery_entry is not None
    if not _same_path_entry(displaced_after_link, recovery_entry):
        raise AtomicPublishError(
            "atomic_recovery_failed", logical_path, preserve_temporary=True
        )
    displaced = displaced_after_link

    _renameat2(
        parent_fd, temporary_name, destination_name, RENAME_EXCHANGE
    )
    _conditional_publish_boundary(
        "after_rollback_exchange", parent_fd, temporary_name, destination_name
    )
    try:
        restored_destination = capture_path_entry_at(
            parent_fd, destination_name, logical_path, missing_ok=False
        )
        restored_temporary = capture_path_entry_at(
            parent_fd, temporary_name, logical_path, missing_ok=False
        )
    except AtomicPublishError as exc:
        raise AtomicPublishError(
            "atomic_recovery_failed", logical_path, preserve_temporary=True
        ) from exc
    assert restored_destination is not None and restored_temporary is not None
    published_entry = BoundPathEntry(
        published.device,
        published.inode,
        published.mode,
        published.link_count,
        published.uid,
        published.gid,
        published.size,
        published.modified_ns,
        published.changed_ns,
        published.data,
    )
    if _same_path_entry_after_rename(
        displaced, restored_destination
    ) and _same_path_entry_after_rename(published_entry, restored_temporary):
        _conditional_publish_boundary(
            "before_recovery_anchor_cleanup",
            parent_fd,
            temporary_name,
            destination_name,
        )
        try:
            cleanup_destination = capture_path_entry_at(
                parent_fd, destination_name, logical_path, missing_ok=False
            )
            cleanup_temporary = capture_path_entry_at(
                parent_fd, temporary_name, logical_path, missing_ok=False
            )
        except AtomicPublishError as exc:
            raise AtomicPublishError(
                "atomic_recovery_failed", logical_path, preserve_temporary=True
            ) from exc
        assert cleanup_destination is not None and cleanup_temporary is not None
        if not (
            _same_path_entry_after_rename(displaced, cleanup_destination)
            and _same_path_entry_after_rename(published_entry, cleanup_temporary)
        ):
            if _same_path_entry_after_rename(published_entry, cleanup_temporary):
                _quarantine_entry(
                    parent_fd, temporary_name, destination_name, logical_path
                )
                raise AtomicPublishError("concurrent_mutation", logical_path)
            raise AtomicPublishError(
                "atomic_recovery_failed", logical_path, preserve_temporary=True
            )
        try:
            os.unlink(recovery_name, dir_fd=parent_fd)
            cleaned_destination = capture_path_entry_at(
                parent_fd, destination_name, logical_path, missing_ok=False
            )
            cleaned_temporary = capture_path_entry_at(
                parent_fd, temporary_name, logical_path, missing_ok=False
            )
        except (AtomicPublishError, OSError) as exc:
            raise AtomicPublishError(
                "atomic_recovery_failed", logical_path, preserve_temporary=True
            ) from exc
        assert cleaned_destination is not None and cleaned_temporary is not None
        if not (
            _same_path_entry_after_rename(
                displaced_before_link, cleaned_destination
            )
            and _same_path_entry_after_rename(
                published_entry, cleaned_temporary
            )
        ):
            raise AtomicPublishError(
                "atomic_recovery_failed", logical_path, preserve_temporary=True
            )
        os.fsync(parent_fd)
        return

    # If temp is still our publisher, a second owner arrived after rollback;
    # leave that owner at the destination and quarantine only our publisher.
    if _same_path_entry_after_rename(published_entry, restored_temporary):
        _quarantine_entry(
            parent_fd, temporary_name, destination_name, logical_path
        )
        raise AtomicPublishError("concurrent_mutation", logical_path)

    # Otherwise the second owner arrived immediately before the rollback
    # exchange and is now in temp. Exchange once to put it back, while the
    # hard-linked recovery anchor retains the displaced prior entry.
    try:
        _renameat2(
            parent_fd, temporary_name, destination_name, RENAME_EXCHANGE
        )
        _quarantine_entry(
            parent_fd, temporary_name, destination_name, logical_path
        )
    except BaseException as exc:
        raise AtomicPublishError(
            "atomic_recovery_failed", logical_path, preserve_temporary=True
        ) from exc
    raise AtomicPublishError("concurrent_mutation", logical_path)


def conditional_publish_file_at(
    parent_fd: int,
    temporary_name: str,
    destination_name: str,
    expected: BoundRegularFile | None,
    logical_path: str,
    *,
    logical_parent: BoundLogicalParent | None = None,
) -> BoundRegularFile:
    """Publish only if the destination still has its captured identity.

    An existing destination is exchanged with the temporary file.  The
    displaced entry is then checked against the no-follow capture; on any
    mismatch the exchange is reversed before a typed failure is returned.
    """

    _conditional_publish_boundary(
        "before_parent_validation",
        parent_fd,
        temporary_name,
        destination_name,
    )
    if logical_parent is not None and not logical_parent_matches(logical_parent):
        raise AtomicPublishError("logical_parent_changed", logical_path)

    published_before = capture_regular_file_at(
        parent_fd, temporary_name, logical_path, missing_ok=False
    )
    assert published_before is not None

    if expected is None:
        try:
            _renameat2(
                parent_fd,
                temporary_name,
                destination_name,
                RENAME_NOREPLACE,
            )
        except FileExistsError as exc:
            raise AtomicPublishError("concurrent_mutation", logical_path) from exc
        except OSError as exc:
            if exc.errno == errno.EEXIST:
                raise AtomicPublishError("concurrent_mutation", logical_path) from exc
            raise AtomicPublishError("atomic_publish_failed", logical_path) from exc
        published_after = capture_regular_file_at(
            parent_fd, destination_name, logical_path, missing_ok=False
        )
        assert published_after is not None
        parent_changed = logical_parent is not None and not logical_parent_matches(
            logical_parent
        )
        if parent_changed:
            try:
                _renameat2(
                    parent_fd,
                    destination_name,
                    temporary_name,
                    RENAME_NOREPLACE,
                )
                retracted = capture_regular_file_at(
                    parent_fd, temporary_name, logical_path, missing_ok=False
                )
                if retracted is None or not _same_file_after_rename(
                    published_after, retracted
                ):
                    raise AtomicPublishError(
                        "atomic_recovery_failed",
                        logical_path,
                        preserve_temporary=True,
                    )
            except AtomicPublishError:
                raise
            except OSError as exc:
                raise AtomicPublishError(
                    "atomic_recovery_failed",
                    logical_path,
                    preserve_temporary=True,
                ) from exc
            raise AtomicPublishError("logical_parent_changed", logical_path)
        os.fsync(parent_fd)
        return published_after

    _conditional_publish_boundary(
        "before_destination_capture",
        parent_fd,
        temporary_name,
        destination_name,
    )
    live = capture_regular_file_at(
        parent_fd, destination_name, logical_path, missing_ok=False
    )
    if live is None or not _same_bound_file(expected, live):
        raise AtomicPublishError("concurrent_mutation", logical_path)

    try:
        _renameat2(
            parent_fd,
            temporary_name,
            destination_name,
            RENAME_EXCHANGE,
        )
    except AtomicPublishError:
        raise
    except OSError as exc:
        if exc.errno in {errno.ENOENT, errno.EEXIST}:
            raise AtomicPublishError("concurrent_mutation", logical_path) from exc
        raise AtomicPublishError("atomic_publish_failed", logical_path) from exc

    displaced: BoundPathEntry | None
    try:
        displaced = capture_path_entry_at(
            parent_fd,
            temporary_name,
            logical_path,
            missing_ok=False,
        )
    except AtomicPublishError:
        displaced = None
    try:
        published_after = capture_regular_file_at(
            parent_fd, destination_name, logical_path, missing_ok=False
        )
    except AtomicPublishError:
        published_after = None
    live_entry = BoundPathEntry(
        live.device,
        live.inode,
        live.mode,
        live.link_count,
        live.uid,
        live.gid,
        live.size,
        live.modified_ns,
        live.changed_ns,
        live.data,
    )
    displaced_matches = displaced is not None and _same_path_entry_after_rename(
        live_entry, displaced
    )
    published_matches = (
        published_after is not None
        and _same_file_after_rename(published_before, published_after)
    )
    parent_matches = logical_parent is None or logical_parent_matches(logical_parent)
    if displaced_matches and published_matches and parent_matches:
        os.fsync(parent_fd)
        assert published_after is not None
        return published_after

    if displaced is None or published_after is None:
        _quarantine_entry(
            parent_fd, temporary_name, destination_name, logical_path
        )
        raise AtomicPublishError("concurrent_mutation", logical_path)
    _rollback_exchange(
        parent_fd,
        temporary_name,
        destination_name,
        published_after,
        displaced,
        logical_path,
    )
    raise AtomicPublishError("concurrent_mutation", logical_path)
