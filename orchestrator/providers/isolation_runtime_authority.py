"""Pinned descriptor-relative authority for provider runtime state.

The authority deliberately does not resolve candidate or runtime paths through
the ambient pathname namespace after admission.  It holds every candidate
ancestry edge, creates or opens ``.orchestrate`` relative to the held candidate
descriptor, and rejects identity or mount changes before every operation.
"""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import fcntl
import itertools
import os
from pathlib import Path
import stat
from typing import Any, Final
import unicodedata


RUNTIME_AUTHORITY_SCHEMA_VERSION: Final = (
    "provider_isolation_runtime_authority.v1"
)
RUNTIME_AUTHORITY_ERROR_CODE: Final = (
    "provider_isolation_candidate_invalid"
)
MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH: Final = 128
MAX_RUNTIME_AUTHORITY_ENTRY_COUNT: Final = 100_000
MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS: Final = 40
MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH: Final = 128
_RUNTIME_NAME: Final = ".orchestrate"
_AT_SYMLINK_NOFOLLOW: Final = 0x100
_AT_EMPTY_PATH: Final = 0x1000
_STATX_MNT_ID: Final = 0x1000
_DEFAULT_MAX_READ_BYTES: Final = 16_777_216
_TEMP_SEQUENCE = itertools.count()


class ProviderIsolationRuntimeAuthorityError(ValueError):
    """A runtime authority could not be established or revalidated."""

    code = RUNTIME_AUTHORITY_ERROR_CODE

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


class MountIdentityUnavailable(RuntimeError):
    """Descriptor-bound Linux mount identity could not be proved."""


@dataclass(frozen=True, slots=True)
class RuntimeAuthorityObjectIdentity:
    """Stable identity of one held filesystem object."""

    path: str
    device: int
    inode: int
    mount_id: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "device": self.device,
            "inode": self.inode,
            "mount_id": self.mount_id,
        }


@dataclass(frozen=True, slots=True)
class ProviderIsolationRuntimeIdentity:
    """Persistable fresh/resume binding for one candidate runtime authority."""

    schema_version: str
    candidate_root: str
    ancestry: tuple[RuntimeAuthorityObjectIdentity, ...]
    candidate: RuntimeAuthorityObjectIdentity
    runtime: RuntimeAuthorityObjectIdentity

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "candidate_root": self.candidate_root,
            "ancestry": [item.to_dict() for item in self.ancestry],
            "candidate": self.candidate.to_dict(),
            "runtime": self.runtime.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class _HeldEdge:
    parent_fd: int
    child_fd: int
    name: str
    identity: RuntimeAuthorityObjectIdentity


@dataclass(slots=True)
class _TraversalBudget:
    entries: int = 0


@dataclass(slots=True)
class _TraversalFrame:
    fd: int
    prefix: tuple[str, ...]
    depth: int
    names: tuple[str, ...]
    index: int = 0
    owned: bool = True


class _StatxTimestamp(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_int64),
        ("tv_nsec", ctypes.c_uint32),
        ("reserved", ctypes.c_int32),
    ]


class _Statx(ctypes.Structure):
    _fields_ = [
        ("stx_mask", ctypes.c_uint32),
        ("stx_blksize", ctypes.c_uint32),
        ("stx_attributes", ctypes.c_uint64),
        ("stx_nlink", ctypes.c_uint32),
        ("stx_uid", ctypes.c_uint32),
        ("stx_gid", ctypes.c_uint32),
        ("stx_mode", ctypes.c_uint16),
        ("spare0", ctypes.c_uint16),
        ("stx_ino", ctypes.c_uint64),
        ("stx_size", ctypes.c_uint64),
        ("stx_blocks", ctypes.c_uint64),
        ("stx_attributes_mask", ctypes.c_uint64),
        ("stx_atime", _StatxTimestamp),
        ("stx_btime", _StatxTimestamp),
        ("stx_ctime", _StatxTimestamp),
        ("stx_mtime", _StatxTimestamp),
        ("stx_rdev_major", ctypes.c_uint32),
        ("stx_rdev_minor", ctypes.c_uint32),
        ("stx_dev_major", ctypes.c_uint32),
        ("stx_dev_minor", ctypes.c_uint32),
        ("stx_mnt_id", ctypes.c_uint64),
        ("stx_dio_mem_align", ctypes.c_uint32),
        ("stx_dio_offset_align", ctypes.c_uint32),
        ("spare3", ctypes.c_uint64 * 12),
    ]


def _statx_mount_id(directory_fd: int, name: str | None = None) -> int:
    """Return Linux ``STATX_MNT_ID`` for a descriptor-relative object."""

    try:
        statx = ctypes.CDLL(None, use_errno=True).statx
    except AttributeError as exc:
        raise MountIdentityUnavailable("libc statx is unavailable") from exc
    statx.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_uint,
        ctypes.POINTER(_Statx),
    ]
    statx.restype = ctypes.c_int

    result = _Statx()
    if name is None:
        encoded_name = b""
        flags = _AT_EMPTY_PATH | _AT_SYMLINK_NOFOLLOW
    else:
        try:
            encoded_name = name.encode("utf-8", errors="strict")
        except UnicodeEncodeError as exc:
            raise MountIdentityUnavailable(
                "entry name is not strict UTF-8"
            ) from exc
        flags = _AT_SYMLINK_NOFOLLOW

    if statx(
        directory_fd,
        encoded_name,
        flags,
        _STATX_MNT_ID,
        ctypes.byref(result),
    ) != 0:
        error = ctypes.get_errno()
        raise MountIdentityUnavailable(os.strerror(error))
    if result.stx_mask & _STATX_MNT_ID == 0 or result.stx_mnt_id == 0:
        raise MountIdentityUnavailable("STATX_MNT_ID was not returned")
    return int(result.stx_mnt_id)


class ProviderIsolationRuntimeAuthority:
    """Held candidate and ``.orchestrate`` authority for one isolated run."""

    def __init__(
        self,
        *,
        candidate_root: str,
        ancestry_fds: list[int],
        ancestry_edges: tuple[_HeldEdge, ...],
        runtime_fd: int,
        runtime_edge: _HeldEdge,
        identity: ProviderIsolationRuntimeIdentity,
    ):
        self._candidate_root = candidate_root
        self._ancestry_fds = ancestry_fds
        self._ancestry_edges = ancestry_edges
        self._candidate_fd = ancestry_fds[-1]
        self._runtime_fd = runtime_fd
        self._runtime_edge = runtime_edge
        self._identity = identity
        self._closed = False

    @classmethod
    def create_fresh(
        cls,
        candidate_root: str | os.PathLike[str],
    ) -> ProviderIsolationRuntimeAuthority:
        """Create and pin an absent-only private ``.orchestrate`` directory."""

        ancestry_fds: list[int] = []
        runtime_fd = -1
        created = False
        try:
            candidate_path = _validate_candidate_path(candidate_root)
            ancestry_fds, ancestry_edges, ancestry = _open_candidate_ancestry(
                candidate_path
            )
            candidate_fd = ancestry_fds[-1]
            _require_runtime_absent(candidate_fd)
            _reject_candidate_runtime_aliases(
                candidate_fd,
                candidate_mount_id=ancestry[-1].mount_id,
            )
            os.mkdir(_RUNTIME_NAME, 0o700, dir_fd=candidate_fd)
            created = True
            runtime_fd = _open_directory_at(candidate_fd, _RUNTIME_NAME)
            os.fchmod(runtime_fd, 0o700)
            runtime_identity = _capture_directory_identity(
                runtime_fd,
                f"{candidate_path}/{_RUNTIME_NAME}",
            )
            linked_runtime = _capture_linked_directory_identity(
                candidate_fd,
                _RUNTIME_NAME,
                runtime_identity.path,
            )
            if runtime_identity != linked_runtime:
                raise _invalid("runtime directory changed while it was pinned")
            if runtime_identity.mount_id != ancestry[-1].mount_id:
                raise _invalid("runtime directory crosses the candidate mount")
            _require_private_runtime_directory(runtime_fd)

            identity = ProviderIsolationRuntimeIdentity(
                schema_version=RUNTIME_AUTHORITY_SCHEMA_VERSION,
                candidate_root=candidate_path,
                ancestry=ancestry,
                candidate=ancestry[-1],
                runtime=runtime_identity,
            )
            authority = cls(
                candidate_root=candidate_path,
                ancestry_fds=ancestry_fds,
                ancestry_edges=ancestry_edges,
                runtime_fd=runtime_fd,
                runtime_edge=_HeldEdge(
                    candidate_fd,
                    runtime_fd,
                    _RUNTIME_NAME,
                    runtime_identity,
                ),
                identity=identity,
            )
            authority.revalidate()
            return authority
        except ProviderIsolationRuntimeAuthorityError:
            _close_fds(runtime_fd, ancestry_fds)
            raise
        except (
            MountIdentityUnavailable,
            OSError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            _close_fds(runtime_fd, ancestry_fds)
            qualifier = (
                " after creating the runtime directory" if created else ""
            )
            raise _invalid(
                f"fresh runtime authority failed{qualifier}: {exc}"
            ) from exc

    @classmethod
    def resume(
        cls,
        candidate_root: str | os.PathLike[str],
        recorded_identity: ProviderIsolationRuntimeIdentity,
    ) -> ProviderIsolationRuntimeAuthority:
        """Open only the exact candidate/runtime identity recorded at creation."""

        ancestry_fds: list[int] = []
        runtime_fd = -1
        try:
            candidate_path = _validate_candidate_path(candidate_root)
            if not isinstance(
                recorded_identity,
                ProviderIsolationRuntimeIdentity,
            ):
                raise _invalid("resume requires a typed recorded runtime identity")
            ancestry_fds, ancestry_edges, ancestry = _open_candidate_ancestry(
                candidate_path
            )
            candidate_fd = ancestry_fds[-1]
            runtime_fd = _open_directory_at(candidate_fd, _RUNTIME_NAME)
            runtime_identity = _capture_directory_identity(
                runtime_fd,
                f"{candidate_path}/{_RUNTIME_NAME}",
            )
            linked_runtime = _capture_linked_directory_identity(
                candidate_fd,
                _RUNTIME_NAME,
                runtime_identity.path,
            )
            if runtime_identity != linked_runtime:
                raise _invalid("runtime directory changed while it was pinned")
            if runtime_identity.mount_id != ancestry[-1].mount_id:
                raise _invalid("runtime directory crosses the candidate mount")
            _require_private_runtime_directory(runtime_fd)

            current = ProviderIsolationRuntimeIdentity(
                schema_version=RUNTIME_AUTHORITY_SCHEMA_VERSION,
                candidate_root=candidate_path,
                ancestry=ancestry,
                candidate=ancestry[-1],
                runtime=runtime_identity,
            )
            if current != recorded_identity:
                raise _invalid(
                    "candidate, runtime, or ancestry identity does not match "
                    "the recorded resume authority"
                )
            authority = cls(
                candidate_root=candidate_path,
                ancestry_fds=ancestry_fds,
                ancestry_edges=ancestry_edges,
                runtime_fd=runtime_fd,
                runtime_edge=_HeldEdge(
                    candidate_fd,
                    runtime_fd,
                    _RUNTIME_NAME,
                    runtime_identity,
                ),
                identity=current,
            )
            authority.revalidate()
            return authority
        except ProviderIsolationRuntimeAuthorityError:
            _close_fds(runtime_fd, ancestry_fds)
            raise
        except (
            MountIdentityUnavailable,
            OSError,
            TypeError,
            UnicodeError,
            ValueError,
        ) as exc:
            _close_fds(runtime_fd, ancestry_fds)
            raise _invalid(f"resume runtime authority failed: {exc}") from exc

    @property
    def identity(self) -> ProviderIsolationRuntimeIdentity:
        return self._identity

    def revalidate(self) -> None:
        """Recheck every held ancestry edge and the complete runtime subtree."""

        self._require_open()
        try:
            root_identity = self._identity.ancestry[0]
            if _capture_directory_identity(
                self._ancestry_fds[0],
                root_identity.path,
            ) != root_identity:
                raise _invalid("candidate root ancestry changed")
            for edge in self._ancestry_edges:
                _revalidate_edge(edge)
            _revalidate_edge(self._runtime_edge)
            _require_private_runtime_directory(self._runtime_fd)
            if self._identity.runtime.mount_id != self._identity.candidate.mount_id:
                raise _invalid("runtime directory crosses the candidate mount")
            _validate_runtime_tree(
                self._runtime_fd,
                expected_mount_id=self._identity.runtime.mount_id,
            )
            _reject_candidate_runtime_aliases(
                self._candidate_fd,
                candidate_mount_id=self._identity.candidate.mount_id,
            )
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (
            MountIdentityUnavailable,
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise _invalid(f"runtime authority revalidation failed: {exc}") from exc

    def revalidate_for_broker_after_quiescence(
        self,
        active_scratch_relpath: str,
        scratch_directory_fd: int,
        expected_scratch_identity: RuntimeAuthorityObjectIdentity,
    ) -> None:
        """Revalidate while keeping one exact active scratch subtree opaque."""

        scratch_parts = _parse_runtime_relpath(active_scratch_relpath)
        if type(expected_scratch_identity) is not RuntimeAuthorityObjectIdentity:
            raise _invalid("broker scratch directory identity is not typed")
        expected_path = (
            f"{self._identity.runtime.path}/{active_scratch_relpath}"
        )
        if expected_scratch_identity.path != expected_path:
            raise _invalid("broker scratch directory path identity does not match")

        self._require_open()
        try:
            root_identity = self._identity.ancestry[0]
            if _capture_directory_identity(
                self._ancestry_fds[0],
                root_identity.path,
            ) != root_identity:
                raise _invalid("candidate root ancestry changed")
            for edge in self._ancestry_edges:
                _revalidate_edge(edge)
            _revalidate_edge(self._runtime_edge)
            _require_private_runtime_directory(self._runtime_fd)
            if self._identity.runtime.mount_id != self._identity.candidate.mount_id:
                raise _invalid("runtime directory crosses the candidate mount")

            held_scratch = _capture_directory_identity(
                scratch_directory_fd,
                expected_scratch_identity.path,
            )
            if (
                held_scratch != expected_scratch_identity
                or held_scratch.mount_id != self._identity.runtime.mount_id
            ):
                raise _invalid("broker scratch directory identity changed")
            _require_private_runtime_directory(scratch_directory_fd)

            _validate_runtime_tree(
                self._runtime_fd,
                expected_mount_id=self._identity.runtime.mount_id,
                opaque_directory=(
                    scratch_parts,
                    scratch_directory_fd,
                    expected_scratch_identity,
                ),
            )
            _reject_candidate_runtime_aliases(
                self._candidate_fd,
                candidate_mount_id=self._identity.candidate.mount_id,
            )
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (
            MountIdentityUnavailable,
            OSError,
            UnicodeError,
            ValueError,
        ) as exc:
            raise _invalid(
                f"broker post-quiescence revalidation failed: {exc}"
            ) from exc

    def duplicate_candidate_fd(self) -> int:
        """Return a caller-owned descriptor for the revalidated candidate."""

        try:
            self.revalidate()
            return os.dup(self._candidate_fd)
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"candidate descriptor duplication failed: {exc}"
            ) from exc

    def duplicate_runtime_fd(self) -> int:
        """Return a caller-owned descriptor for the revalidated runtime root."""

        try:
            self.revalidate()
            return os.dup(self._runtime_fd)
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"runtime descriptor duplication failed: {exc}"
            ) from exc

    def duplicate_runtime_fd_for_broker_after_quiescence(
        self,
        active_scratch_relpath: str,
        scratch_directory_fd: int,
        expected_scratch_identity: RuntimeAuthorityObjectIdentity,
        *,
        minimum: int = 16,
    ) -> int:
        """Duplicate the runtime root after exact broker revalidation."""

        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 3
        ):
            raise _invalid(
                "broker runtime descriptor minimum must be an integer >= 3"
            )
        duplicate_fd = -1
        try:
            self.revalidate_for_broker_after_quiescence(
                active_scratch_relpath,
                scratch_directory_fd,
                expected_scratch_identity,
            )
            duplicate_fd = fcntl.fcntl(
                self._runtime_fd,
                fcntl.F_DUPFD_CLOEXEC,
                minimum,
            )
            observed = _capture_directory_identity(
                duplicate_fd,
                self._identity.runtime.path,
            )
            if observed != self._identity.runtime:
                raise _invalid("broker runtime descriptor identity changed")
            _require_private_runtime_directory(duplicate_fd)
            self.revalidate_for_broker_after_quiescence(
                active_scratch_relpath,
                scratch_directory_fd,
                expected_scratch_identity,
            )
            result_fd = duplicate_fd
            duplicate_fd = -1
            return result_fd
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"broker runtime descriptor duplication failed: {exc}"
            ) from exc
        finally:
            _close_fds(duplicate_fd, [])

    def create_fresh_directory(
        self,
        relpath: str,
        *,
        parents: bool = False,
    ) -> tuple[int, RuntimeAuthorityObjectIdentity]:
        """Create and pin one absent-only private runtime directory."""

        parts = _parse_runtime_relpath(relpath)
        parent_fd = -1
        directory_fd = -1
        created = False
        completed = False
        try:
            self.revalidate()
            parent_fd = self._open_directory_parts(
                parts[:-1],
                create=parents,
                parents=parents,
            )
            try:
                os.mkdir(parts[-1], 0o700, dir_fd=parent_fd)
            except FileExistsError as exc:
                raise _invalid("fresh runtime directory already exists") from exc
            created = True
            directory_fd = _open_directory_at(parent_fd, parts[-1])
            os.fchmod(directory_fd, 0o700)
            path = f"{self._identity.runtime.path}/{relpath}"
            identity = _capture_directory_identity(directory_fd, path)
            linked = _capture_linked_directory_identity(
                parent_fd,
                parts[-1],
                path,
            )
            if (
                identity != linked
                or identity.mount_id != self._identity.runtime.mount_id
            ):
                raise _invalid("fresh runtime directory identity changed")
            _require_private_runtime_directory(directory_fd)
            os.fsync(directory_fd)
            os.fsync(parent_fd)
            self.revalidate()
            result_fd = directory_fd
            directory_fd = -1
            completed = True
            return result_fd, identity
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"fresh runtime directory creation failed: {exc}"
            ) from exc
        finally:
            if directory_fd >= 0:
                os.close(directory_fd)
            if created and not completed and parent_fd >= 0:
                try:
                    os.rmdir(parts[-1], dir_fd=parent_fd)
                except OSError:
                    pass
            if parent_fd >= 0:
                os.close(parent_fd)

    def revalidate_directory_binding(
        self,
        relpath: str,
        directory_fd: int,
        expected_identity: RuntimeAuthorityObjectIdentity,
    ) -> None:
        """Verify a held runtime directory and its linked relative name."""

        parts = _parse_runtime_relpath(relpath)
        if type(expected_identity) is not RuntimeAuthorityObjectIdentity:
            raise _invalid("runtime directory identity is not typed")
        linked_fd = -1
        try:
            self.revalidate()
            observed = _capture_directory_identity(
                directory_fd,
                expected_identity.path,
            )
            linked_fd = self._open_directory_parts(parts)
            linked = _capture_directory_identity(
                linked_fd,
                expected_identity.path,
            )
            if (
                observed != expected_identity
                or linked != expected_identity
                or observed.mount_id != self._identity.runtime.mount_id
            ):
                raise _invalid("runtime directory binding identity changed")
            _require_private_runtime_directory(directory_fd)
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"runtime directory binding revalidation failed: {exc}"
            ) from exc
        finally:
            if linked_fd >= 0:
                os.close(linked_fd)

    def remove_empty_directory_binding(
        self,
        relpath: str,
        directory_fd: int,
        expected_identity: RuntimeAuthorityObjectIdentity,
    ) -> None:
        """Remove one exact empty runtime-directory binding."""

        parts = _parse_runtime_relpath(relpath)
        if type(expected_identity) is not RuntimeAuthorityObjectIdentity:
            raise _invalid("runtime directory identity is not typed")
        parent_fd = -1
        try:
            self.revalidate_directory_binding(
                relpath,
                directory_fd,
                expected_identity,
            )
            parent_fd = self._open_directory_parts(parts[:-1])
            observed = _capture_directory_identity(
                directory_fd,
                expected_identity.path,
            )
            linked = _capture_linked_directory_identity(
                parent_fd,
                parts[-1],
                expected_identity.path,
            )
            if (
                observed != expected_identity
                or linked != expected_identity
                or observed.mount_id != self._identity.runtime.mount_id
            ):
                raise _invalid("runtime directory binding identity changed")
            _require_private_runtime_directory(directory_fd)
            if os.listdir(directory_fd):
                raise _invalid("runtime directory binding is not empty")
            os.rmdir(parts[-1], dir_fd=parent_fd)
            os.fsync(parent_fd)
            try:
                os.stat(
                    parts[-1],
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            except FileNotFoundError:
                pass
            else:
                raise _invalid("runtime directory binding remains linked")
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"runtime directory binding removal failed: {exc}"
            ) from exc
        finally:
            if parent_fd >= 0:
                os.close(parent_fd)

    def duplicate_directory_binding(
        self,
        relpath: str,
        directory_fd: int,
        expected_identity: RuntimeAuthorityObjectIdentity,
        *,
        minimum: int = 16,
    ) -> int:
        """Duplicate one exact live runtime-directory binding."""

        if (
            isinstance(minimum, bool)
            or not isinstance(minimum, int)
            or minimum < 3
        ):
            raise _invalid(
                "runtime directory duplicate descriptor minimum is invalid"
            )
        duplicate_fd = -1
        try:
            self.revalidate_directory_binding(
                relpath,
                directory_fd,
                expected_identity,
            )
            duplicate_fd = fcntl.fcntl(
                directory_fd,
                fcntl.F_DUPFD_CLOEXEC,
                minimum,
            )
            self.revalidate_directory_binding(
                relpath,
                duplicate_fd,
                expected_identity,
            )
            self.revalidate_directory_binding(
                relpath,
                directory_fd,
                expected_identity,
            )
            result_fd = duplicate_fd
            duplicate_fd = -1
            return result_fd
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(
                f"runtime directory descriptor duplication failed: {exc}"
            ) from exc
        finally:
            if duplicate_fd >= 0:
                os.close(duplicate_fd)

    def open_directory(
        self,
        relpath: str,
        *,
        create: bool = False,
        parents: bool = False,
    ) -> int:
        """Open one runtime directory without following links or crossing mounts."""

        parts = _parse_runtime_relpath(relpath)
        try:
            self.revalidate()
            return self._open_directory_parts(
                parts,
                create=create,
                parents=parents,
            )
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(f"runtime directory open failed: {exc}") from exc

    def mkdir(self, relpath: str, *, parents: bool = False) -> None:
        """Create one private runtime directory descriptor-relatively."""

        directory_fd = -1
        try:
            directory_fd = self.open_directory(
                relpath,
                create=True,
                parents=parents,
            )
            os.fsync(directory_fd)
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(f"runtime directory creation failed: {exc}") from exc
        finally:
            _close_fds(directory_fd, [])

    def read_bytes(
        self,
        relpath: str,
        *,
        max_bytes: int = _DEFAULT_MAX_READ_BYTES,
    ) -> bytes:
        """Read one exact pinned regular runtime file within a fixed bound."""

        if not isinstance(max_bytes, int) or isinstance(max_bytes, bool):
            raise _invalid("max_bytes must be a positive integer")
        if max_bytes <= 0:
            raise _invalid("max_bytes must be a positive integer")
        parts = _parse_runtime_relpath(relpath)
        parent_fd = -1
        pin_fd = -1
        readable_fd = -1
        try:
            self.revalidate()
            parent_fd = self._open_directory_parts(parts[:-1])
            pin_fd, pinned = self._pin_regular(parent_fd, parts[-1])
            if pinned.size > max_bytes:
                raise _invalid("runtime file exceeds the configured read bound")
            readable_fd = _open_pinned_file(pin_fd, os.O_RDONLY | os.O_NONBLOCK)
            _require_opened_regular(
                readable_fd,
                pinned,
                expected_mount_id=self._identity.runtime.mount_id,
            )
            chunks: list[bytes] = []
            remaining = max_bytes + 1
            while remaining:
                chunk = os.read(readable_fd, min(1_048_576, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            payload = b"".join(chunks)
            if len(payload) > max_bytes:
                raise _invalid("runtime file exceeds the configured read bound")
            _require_opened_regular(
                readable_fd,
                pinned,
                expected_mount_id=self._identity.runtime.mount_id,
            )
            return payload
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(f"runtime read failed: {exc}") from exc
        finally:
            _close_fds(readable_fd, [pin_fd, parent_fd])

    def write_bytes(
        self,
        relpath: str,
        payload: bytes,
        *,
        mode: int = 0o600,
    ) -> None:
        """Create or rewrite one pinned regular runtime file."""

        data = _require_bytes(payload)
        _require_private_file_mode(mode)
        parts = _parse_runtime_relpath(relpath)
        parent_fd = -1
        pin_fd = -1
        writable_fd = -1
        try:
            self.revalidate()
            parent_fd = self._open_directory_parts(parts[:-1])
            try:
                pin_fd, pinned = self._pin_regular(parent_fd, parts[-1])
            except FileNotFoundError:
                pinned = None
            if pinned is None:
                writable_fd = os.open(
                    parts[-1],
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    mode,
                    dir_fd=parent_fd,
                )
                os.fchmod(writable_fd, mode)
                _require_new_regular(
                    writable_fd,
                    expected_mount_id=self._identity.runtime.mount_id,
                )
            else:
                writable_fd = _open_pinned_file(
                    pin_fd,
                    os.O_WRONLY | os.O_NONBLOCK,
                )
                _require_opened_regular(
                    writable_fd,
                    pinned,
                    expected_mount_id=self._identity.runtime.mount_id,
                )
                os.ftruncate(writable_fd, 0)
                os.lseek(writable_fd, 0, os.SEEK_SET)
            _write_all(writable_fd, data)
            os.fsync(writable_fd)
            os.fsync(parent_fd)
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(f"runtime write failed: {exc}") from exc
        finally:
            _close_fds(writable_fd, [pin_fd, parent_fd])

    def atomic_replace(
        self,
        relpath: str,
        payload: bytes,
        *,
        mode: int = 0o600,
    ) -> None:
        """Atomically publish bytes below the held runtime authority."""

        data = _require_bytes(payload)
        _require_private_file_mode(mode)
        parts = _parse_runtime_relpath(relpath)
        parent_fd = -1
        existing_pin_fd = -1
        temp_fd = -1
        published_pin_fd = -1
        temp_name: str | None = None
        try:
            self.revalidate()
            parent_fd = self._open_directory_parts(parts[:-1])
            try:
                existing_pin_fd, _ = self._pin_regular(
                    parent_fd,
                    parts[-1],
                )
            except FileNotFoundError:
                pass
            temp_name, temp_fd = _create_temporary_regular(parent_fd, mode)
            _require_new_regular(
                temp_fd,
                expected_mount_id=self._identity.runtime.mount_id,
            )
            _write_all(temp_fd, data)
            os.fsync(temp_fd)
            temp_stat = os.fstat(temp_fd)
            os.replace(
                temp_name,
                parts[-1],
                src_dir_fd=parent_fd,
                dst_dir_fd=parent_fd,
            )
            temp_name = None
            os.fsync(parent_fd)
            published_pin_fd, published = self._pin_regular(
                parent_fd,
                parts[-1],
            )
            if (
                published.device != temp_stat.st_dev
                or published.inode != temp_stat.st_ino
            ):
                raise _invalid("atomic runtime publication identity changed")
        except ProviderIsolationRuntimeAuthorityError:
            raise
        except (MountIdentityUnavailable, OSError, ValueError) as exc:
            raise _invalid(f"atomic runtime replace failed: {exc}") from exc
        finally:
            if temp_name is not None:
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except (OSError, ValueError):
                    pass
            _close_fds(
                published_pin_fd,
                [temp_fd, existing_pin_fd, parent_fd],
            )

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        _close_fds(self._runtime_fd, self._ancestry_fds)
        self._runtime_fd = -1
        self._candidate_fd = -1
        self._ancestry_fds = []

    def __enter__(self) -> ProviderIsolationRuntimeAuthority:
        self._require_open()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()

    def _require_open(self) -> None:
        if self._closed:
            raise _invalid("runtime authority is closed")

    def _open_directory_parts(
        self,
        parts: tuple[str, ...],
        *,
        create: bool = False,
        parents: bool = False,
    ) -> int:
        current_fd = os.dup(self._runtime_fd)
        try:
            for index, name in enumerate(parts):
                allow_create = create and (parents or index == len(parts) - 1)
                if allow_create:
                    try:
                        os.mkdir(name, 0o700, dir_fd=current_fd)
                        os.fsync(current_fd)
                    except FileExistsError:
                        pass
                next_fd = _open_directory_at(current_fd, name)
                try:
                    identity = _capture_directory_identity(next_fd, name)
                    linked = _capture_linked_directory_identity(
                        current_fd,
                        name,
                        name,
                    )
                    if identity != linked:
                        raise _invalid(
                            "runtime directory edge changed while opening"
                        )
                    if identity.mount_id != self._identity.runtime.mount_id:
                        raise _invalid(
                            "runtime descendant crosses a mount boundary"
                        )
                except Exception:
                    _close_fds(next_fd, [])
                    raise
                previous_fd = current_fd
                current_fd = next_fd
                _close_fds(previous_fd, [])
            return current_fd
        except Exception:
            _close_fds(current_fd, [])
            raise

    def _pin_regular(
        self,
        parent_fd: int,
        name: str,
    ) -> tuple[int, "_PinnedRegularIdentity"]:
        try:
            pin_fd = os.open(
                name,
                os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except FileNotFoundError:
            raise
        except OSError as exc:
            raise _invalid(f"runtime file could not be pinned: {exc}") from exc
        try:
            opened = os.fstat(pin_fd)
            if not stat.S_ISREG(opened.st_mode):
                raise _invalid("runtime file must be a regular file")
            if opened.st_nlink != 1:
                raise _invalid("runtime regular file has an external alias")
            mount_id = _statx_mount_id(pin_fd)
            if mount_id != self._identity.runtime.mount_id:
                raise _invalid("runtime file crosses a mount boundary")
            linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            linked_mount_id = _statx_mount_id(parent_fd, name)
            if (
                linked.st_dev != opened.st_dev
                or linked.st_ino != opened.st_ino
                or linked_mount_id != mount_id
            ):
                raise _invalid("runtime file changed while it was pinned")
            return pin_fd, _PinnedRegularIdentity(
                device=opened.st_dev,
                inode=opened.st_ino,
                mount_id=mount_id,
                size=opened.st_size,
            )
        except Exception:
            os.close(pin_fd)
            raise


@dataclass(frozen=True, slots=True)
class _PinnedRegularIdentity:
    device: int
    inode: int
    mount_id: int
    size: int


def _validate_candidate_path(path: str | os.PathLike[str]) -> str:
    raw = os.fspath(path)
    if not isinstance(raw, str):
        raise _invalid("candidate root must be a text path")
    if "\x00" in raw:
        raise _invalid("candidate root may not contain NUL")
    try:
        raw.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise _invalid("candidate root must be strict UTF-8") from exc
    if unicodedata.normalize("NFC", raw) != raw:
        raise _invalid("candidate root must be NFC-normalized")
    if not raw.startswith("/") or raw == "/" or raw.startswith("//"):
        raise _invalid("candidate root must be a non-root absolute path")
    normalized = os.path.normpath(raw)
    if raw != normalized:
        raise _invalid("candidate root must be a canonical absolute path")
    return raw


def _parse_runtime_relpath(relpath: str) -> tuple[str, ...]:
    if not isinstance(relpath, str):
        raise _invalid("runtime path must be text")
    if "\x00" in relpath:
        raise _invalid("runtime path may not contain NUL")
    try:
        relpath.encode("utf-8", errors="strict")
    except UnicodeEncodeError as exc:
        raise _invalid("runtime path must be strict UTF-8") from exc
    if unicodedata.normalize("NFC", relpath) != relpath:
        raise _invalid("runtime path must be NFC-normalized")
    if (
        not relpath
        or relpath.startswith("/")
        or relpath.endswith("/")
        or "//" in relpath
    ):
        raise _invalid("runtime path must be one canonical relative path")
    parts = tuple(relpath.split("/"))
    if any(part in {"", ".", ".."} for part in parts):
        raise _invalid("runtime path may not contain dot components")
    return parts


def _open_candidate_ancestry(
    candidate_path: str,
) -> tuple[
    list[int],
    tuple[_HeldEdge, ...],
    tuple[RuntimeAuthorityObjectIdentity, ...],
]:
    components = tuple(Path(candidate_path).parts[1:])
    if len(components) > MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH:
        raise _invalid("candidate ancestry exceeds the fixed depth bound")
    root_fd = _open_absolute_root()
    fds = [root_fd]
    edges: list[_HeldEdge] = []
    try:
        identities = [_capture_directory_identity(root_fd, "/")]
        current_path = ""
        for component in components:
            next_fd = _open_directory_at(fds[-1], component)
            parent_fd = fds[-1]
            fds.append(next_fd)
            current_path = f"{current_path}/{component}"
            identity = _capture_directory_identity(next_fd, current_path)
            linked = _capture_linked_directory_identity(
                parent_fd,
                component,
                current_path,
            )
            if identity != linked:
                raise _invalid("candidate ancestry changed while it was pinned")
            edges.append(_HeldEdge(parent_fd, next_fd, component, identity))
            identities.append(identity)
        return fds, tuple(edges), tuple(identities)
    except Exception:
        _close_fds(-1, fds)
        raise


def _open_absolute_root() -> int:
    try:
        return os.open(
            "/",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
    except OSError as exc:
        raise _invalid(f"absolute root could not be pinned: {exc}") from exc


def _open_directory_at(parent_fd: int, name: str) -> int:
    try:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise _invalid(f"real directory {name!r} could not be pinned: {exc}") from exc


def _capture_directory_identity(
    directory_fd: int,
    path: str,
) -> RuntimeAuthorityObjectIdentity:
    opened = os.fstat(directory_fd)
    if not stat.S_ISDIR(opened.st_mode):
        raise _invalid(f"authority object {path!r} is not a real directory")
    return RuntimeAuthorityObjectIdentity(
        path=path,
        device=opened.st_dev,
        inode=opened.st_ino,
        mount_id=_statx_mount_id(directory_fd),
    )


def _capture_linked_directory_identity(
    parent_fd: int,
    name: str,
    path: str,
) -> RuntimeAuthorityObjectIdentity:
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISDIR(linked.st_mode):
        raise _invalid(f"authority edge {path!r} is not a real directory")
    return RuntimeAuthorityObjectIdentity(
        path=path,
        device=linked.st_dev,
        inode=linked.st_ino,
        mount_id=_statx_mount_id(parent_fd, name),
    )


def _revalidate_edge(edge: _HeldEdge) -> None:
    opened = _capture_directory_identity(edge.child_fd, edge.identity.path)
    linked = _capture_linked_directory_identity(
        edge.parent_fd,
        edge.name,
        edge.identity.path,
    )
    if opened != edge.identity or linked != edge.identity:
        raise _invalid(f"authority edge {edge.identity.path!r} changed")


def _require_runtime_absent(candidate_fd: int) -> None:
    try:
        os.stat(_RUNTIME_NAME, dir_fd=candidate_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    except OSError as exc:
        raise _invalid(f"runtime absence could not be proved: {exc}") from exc
    raise _invalid("fresh runtime requires absent .orchestrate")


def _require_private_runtime_directory(runtime_fd: int) -> None:
    opened = os.fstat(runtime_fd)
    if not stat.S_ISDIR(opened.st_mode):
        raise _invalid("runtime authority is not a directory")
    if opened.st_uid != os.geteuid():
        raise _invalid("runtime authority is not controller-owned")
    if stat.S_IMODE(opened.st_mode) != 0o700:
        raise _invalid("runtime authority must have mode 0700")


def _reject_candidate_runtime_aliases(
    candidate_fd: int,
    *,
    candidate_mount_id: int,
) -> None:
    links: dict[tuple[str, ...], str] = {}
    _collect_candidate_links(
        candidate_fd,
        (),
        candidate_mount_id=candidate_mount_id,
        links=links,
    )
    for relpath, link_text in links.items():
        target = _normalize_link_target(relpath[:-1], link_text, ())
        seen: set[tuple[str, ...]] = set()
        for _ in range(MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS):
            if not target or target[0] == _RUNTIME_NAME:
                raise _invalid(
                    "candidate symlink creates an alias to .orchestrate"
                )
            if target in seen:
                raise _invalid("candidate symlink cycle is not admissible")
            seen.add(target)
            match: tuple[int, str] | None = None
            for length in range(1, len(target) + 1):
                prefix = target[:length]
                if prefix in links:
                    match = (length, links[prefix])
                    break
            if match is None:
                break
            length, nested_text = match
            target = _normalize_link_target(
                target[: length - 1],
                nested_text,
                target[length:],
            )
        else:
            raise _invalid("candidate symlink expansion exceeds the fixed bound")


def _collect_candidate_links(
    directory_fd: int,
    prefix: tuple[str, ...],
    *,
    candidate_mount_id: int,
    links: dict[tuple[str, ...], str],
) -> None:
    budget = _TraversalBudget()
    frames = [
        _TraversalFrame(
            fd=directory_fd,
            prefix=prefix,
            depth=0,
            names=_bounded_traversal_names(
                directory_fd,
                budget,
                skip_runtime=not prefix,
            ),
            owned=False,
        )
    ]
    try:
        while frames:
            frame = frames[-1]
            if frame.index >= len(frame.names):
                frames.pop()
                if frame.owned:
                    _close_fds(frame.fd, [])
                continue

            name = frame.names[frame.index]
            frame.index += 1
            observed = os.stat(
                name,
                dir_fd=frame.fd,
                follow_symlinks=False,
            )
            mount_id = _statx_mount_id(frame.fd, name)
            if mount_id != candidate_mount_id:
                raise _invalid("candidate entry crosses a mount boundary")
            relpath = (*frame.prefix, name)

            if stat.S_ISLNK(observed.st_mode):
                link_text = os.readlink(name, dir_fd=frame.fd)
                try:
                    link_text.encode("utf-8", errors="strict")
                except UnicodeEncodeError as exc:
                    raise _invalid(
                        "candidate symlink text is not strict UTF-8"
                    ) from exc
                if unicodedata.normalize("NFC", link_text) != link_text:
                    raise _invalid(
                        "candidate symlink text is not NFC-normalized"
                    )
                links[relpath] = link_text
                continue

            if not stat.S_ISDIR(observed.st_mode):
                continue

            child_depth = frame.depth + 1
            if child_depth > MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH:
                raise _invalid(
                    "candidate directory depth exceeds the fixed bound"
                )
            child_fd = _open_directory_at(frame.fd, name)
            try:
                if _statx_mount_id(child_fd) != candidate_mount_id:
                    raise _invalid(
                        "candidate directory crosses a mount boundary"
                    )
                child_names = _bounded_traversal_names(
                    child_fd,
                    budget,
                    skip_runtime=False,
                )
                frames.append(
                    _TraversalFrame(
                        fd=child_fd,
                        prefix=relpath,
                        depth=child_depth,
                        names=child_names,
                    )
                )
                child_fd = -1
            finally:
                _close_fds(child_fd, [])
    finally:
        for frame in reversed(frames):
            if frame.owned:
                _close_fds(frame.fd, [])


def _bounded_traversal_names(
    directory_fd: int,
    budget: _TraversalBudget,
    *,
    skip_runtime: bool,
) -> tuple[str, ...]:
    names: list[str] = []
    with os.scandir(directory_fd) as iterator:
        for entry in iterator:
            name = entry.name
            if skip_runtime and name == _RUNTIME_NAME:
                continue
            try:
                name.encode("utf-8", errors="strict")
            except UnicodeEncodeError as exc:
                raise _invalid(
                    "runtime authority entry name is not strict UTF-8"
                ) from exc
            if unicodedata.normalize("NFC", name) != name:
                raise _invalid(
                    "runtime authority entry name is not NFC-normalized"
                )
            budget.entries += 1
            if budget.entries > MAX_RUNTIME_AUTHORITY_ENTRY_COUNT:
                raise _invalid(
                    "runtime authority entry count exceeds the fixed bound"
                )
            names.append(name)
    names.sort(key=lambda item: item.encode("utf-8"))
    return tuple(names)


def _normalize_link_target(
    parent: tuple[str, ...],
    link_text: str,
    suffix: tuple[str, ...],
) -> tuple[str, ...]:
    if link_text.startswith("/"):
        raise _invalid("candidate symlink target must remain in the candidate")
    components = list(parent)
    for component in (*link_text.split("/"), *suffix):
        if component in {"", "."}:
            continue
        if component == "..":
            if not components:
                raise _invalid("candidate symlink target escapes the candidate")
            components.pop()
            continue
        components.append(component)
    return tuple(components)


def _validate_runtime_tree(
    directory_fd: int,
    *,
    expected_mount_id: int,
    opaque_directory: (
        tuple[
            tuple[str, ...],
            int,
            RuntimeAuthorityObjectIdentity,
        ]
        | None
    ) = None,
) -> None:
    budget = _TraversalBudget()
    found_opaque_directory = opaque_directory is None
    frames = [
        _TraversalFrame(
            fd=directory_fd,
            prefix=(),
            depth=0,
            names=_bounded_traversal_names(
                directory_fd,
                budget,
                skip_runtime=False,
            ),
            owned=False,
        )
    ]
    try:
        while frames:
            frame = frames[-1]
            if frame.index >= len(frame.names):
                frames.pop()
                if frame.owned:
                    _close_fds(frame.fd, [])
                continue

            name = frame.names[frame.index]
            frame.index += 1
            observed = os.stat(
                name,
                dir_fd=frame.fd,
                follow_symlinks=False,
            )
            mount_id = _statx_mount_id(frame.fd, name)
            if mount_id != expected_mount_id:
                raise _invalid("runtime descendant crosses a mount boundary")
            relpath = (*frame.prefix, name)
            if stat.S_ISLNK(observed.st_mode):
                raise _invalid("runtime descendants may not be symlinks")
            if stat.S_ISREG(observed.st_mode):
                if observed.st_nlink != 1:
                    raise _invalid("runtime regular file has an external alias")
                continue
            if not stat.S_ISDIR(observed.st_mode):
                raise _invalid(
                    "runtime descendants must be directories or regular files"
                )

            child_depth = frame.depth + 1
            if child_depth > MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH:
                raise _invalid(
                    "runtime directory depth exceeds the fixed bound"
                )
            child_fd = _open_directory_at(frame.fd, name)
            try:
                if _statx_mount_id(child_fd) != expected_mount_id:
                    raise _invalid(
                        "runtime descendant crosses a mount boundary"
                    )
                if (
                    opaque_directory is not None
                    and relpath == opaque_directory[0]
                ):
                    expected_opaque_identity = opaque_directory[2]
                    opened = _capture_directory_identity(
                        child_fd,
                        expected_opaque_identity.path,
                    )
                    linked = _capture_linked_directory_identity(
                        frame.fd,
                        name,
                        expected_opaque_identity.path,
                    )
                    held = _capture_directory_identity(
                        opaque_directory[1],
                        expected_opaque_identity.path,
                    )
                    if not (
                        opened
                        == linked
                        == held
                        == expected_opaque_identity
                    ):
                        raise _invalid(
                            "broker scratch directory binding identity changed"
                        )
                    _require_private_runtime_directory(child_fd)
                    _require_private_runtime_directory(opaque_directory[1])
                    found_opaque_directory = True
                    continue

                child_names = _bounded_traversal_names(
                    child_fd,
                    budget,
                    skip_runtime=False,
                )
                frames.append(
                    _TraversalFrame(
                        fd=child_fd,
                        prefix=relpath,
                        depth=child_depth,
                        names=child_names,
                    )
                )
                child_fd = -1
            finally:
                _close_fds(child_fd, [])
    finally:
        for frame in reversed(frames):
            if frame.owned:
                _close_fds(frame.fd, [])

    if not found_opaque_directory:
        raise _invalid("broker scratch directory path is missing")


def _require_bytes(payload: bytes) -> bytes:
    if not isinstance(payload, bytes):
        raise _invalid("runtime payload must be bytes")
    return payload


def _require_private_file_mode(mode: int) -> None:
    if (
        not isinstance(mode, int)
        or isinstance(mode, bool)
        or mode < 0
        or mode > 0o777
        or mode & 0o077
    ):
        raise _invalid("runtime file mode must be a private permission mode")


def _open_pinned_file(pin_fd: int, flags: int) -> int:
    return os.open(
        f"/proc/self/fd/{pin_fd}",
        flags | os.O_CLOEXEC,
    )


def _require_opened_regular(
    opened_fd: int,
    pinned: _PinnedRegularIdentity,
    *,
    expected_mount_id: int,
) -> None:
    observed = os.fstat(opened_fd)
    if (
        not stat.S_ISREG(observed.st_mode)
        or observed.st_dev != pinned.device
        or observed.st_ino != pinned.inode
        or observed.st_nlink != 1
    ):
        raise _invalid("opened runtime file does not match its pinned identity")
    mount_id = _statx_mount_id(opened_fd)
    if mount_id != pinned.mount_id or mount_id != expected_mount_id:
        raise _invalid("opened runtime file crosses a mount boundary")


def _require_new_regular(opened_fd: int, *, expected_mount_id: int) -> None:
    observed = os.fstat(opened_fd)
    if not stat.S_ISREG(observed.st_mode) or observed.st_nlink != 1:
        raise _invalid("new runtime output is not a single-link regular file")
    if _statx_mount_id(opened_fd) != expected_mount_id:
        raise _invalid("new runtime output crosses a mount boundary")


def _create_temporary_regular(parent_fd: int, mode: int) -> tuple[str, int]:
    for _ in range(128):
        name = (
            f".provider-runtime-replace-{os.getpid()}-"
            f"{next(_TEMP_SEQUENCE)}"
        )
        try:
            fd = os.open(
                name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                mode,
                dir_fd=parent_fd,
            )
        except FileExistsError:
            continue
        try:
            os.fchmod(fd, mode)
        except Exception:
            _close_fds(fd, [])
            try:
                os.unlink(name, dir_fd=parent_fd)
            except (OSError, ValueError):
                pass
            raise
        return name, fd
    raise _invalid("could not allocate a unique runtime replacement file")


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short runtime write")
        view = view[written:]


def _close_fds(primary: int, others: list[int]) -> None:
    seen: set[int] = set()
    for fd in [primary, *reversed(others)]:
        if fd < 0 or fd in seen:
            continue
        seen.add(fd)
        try:
            os.close(fd)
        except (OSError, ValueError):
            pass


def _invalid(message: str) -> ProviderIsolationRuntimeAuthorityError:
    return ProviderIsolationRuntimeAuthorityError(message)


__all__ = [
    "MAX_RUNTIME_AUTHORITY_ANCESTRY_DEPTH",
    "MAX_RUNTIME_AUTHORITY_DIRECTORY_DEPTH",
    "MAX_RUNTIME_AUTHORITY_ENTRY_COUNT",
    "MAX_RUNTIME_AUTHORITY_SYMLINK_EXPANSIONS",
    "MountIdentityUnavailable",
    "ProviderIsolationRuntimeAuthority",
    "ProviderIsolationRuntimeAuthorityError",
    "ProviderIsolationRuntimeIdentity",
    "RUNTIME_AUTHORITY_ERROR_CODE",
    "RUNTIME_AUTHORITY_SCHEMA_VERSION",
    "RuntimeAuthorityObjectIdentity",
]
