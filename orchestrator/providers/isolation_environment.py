"""Closed provider-environment manifest identity.

Filesystem admission and snapshot publication build on this manifest owner.
This module deliberately keeps the manifest digest independent from the
complete provider-isolation policy digest.
"""

from __future__ import annotations

import array
import ast
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
import ctypes
from dataclasses import dataclass, field
import errno
import fcntl
from hashlib import sha256
from importlib import resources
import json
import mmap
import os
from pathlib import Path
import posixpath
import re
import shutil
import stat
import struct
from typing import Any
import unicodedata
import uuid

from jsonschema import Draft202012Validator

from .isolation import (
    ProviderIsolationIssue,
    canonical_isolation_json_bytes,
    isolation_schema_validation_issues,
    load_provider_isolation_schema,
)


ENVIRONMENT_SCHEMA_RESOURCE = "provider-environment-manifest-v1.schema.json"
ENVIRONMENT_SCHEMA_VERSION = "provider_environment_manifest.v1"
ENVIRONMENT_INVALID_CODE = "provider_isolation_environment_invalid"
ENVIRONMENT_MISMATCH_CODE = "provider_isolation_environment_mismatch"
ENVIRONMENT_BACKEND_UNAVAILABLE_CODE = "provider_isolation_backend_unavailable"

_DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_JSON_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_COMMON_ENTRY_FIELDS = frozenset(
    {
        "path",
        "kind",
        "mode",
        "uid",
        "gid",
        "atime_ns",
        "mtime_ns",
    }
)
_KIND_FIELDS = {
    "directory": _COMMON_ENTRY_FIELDS,
    "regular_file": _COMMON_ENTRY_FIELDS | {"size", "digest"},
    "symlink": _COMMON_ENTRY_FIELDS | {"link_text"},
}

_AT_SYMLINK_NOFOLLOW = 0x100
_AT_EMPTY_PATH = 0x1000
_STATX_MNT_ID = 0x1000
_FS_IOC_GETFLAGS = 0x80086601
_FS_IOC_SETFLAGS = 0x40086602
_FS_NOATIME_FL = 0x00000080
_SOURCE_FORBIDDEN_WRITE_BITS = 0o022
_SOURCE_IDENTITY_FIELDS = (
    "st_mode",
    "st_ino",
    "st_dev",
    "st_nlink",
    "st_uid",
    "st_gid",
    "st_size",
    "st_mtime_ns",
    "st_ctime_ns",
)
_ELF_MAGIC = b"\x7fELF"
_ELF_CLASS_64 = 2
_ELF_DATA_LITTLE_ENDIAN = 1
_ELF_VERSION_CURRENT = 1
_ELF_TYPE_EXEC = 2
_ELF_TYPE_DYN = 3
_ELF_MACHINE_X86_64 = 62
_MAX_RUNTIME_SYMLINKS = 40
_CONVENTIONAL_X86_64_LOADER = "/lib64/ld-linux-x86-64.so.2"
_GLIBC_CACHE_PATH = "/etc/ld.so.cache"
_GLIBC_CACHE_MAGIC = b"glibc-ld.so.cache"
_GLIBC_CACHE_VERSION = b"1.1"
_GLIBC_CACHE_LITTLE_ENDIAN = 2
_GLIBC_CACHE_X86_64_FLAGS = 0x303
_GLIBC_CACHE_HEADER_FORMAT = "<17s3sIIB3sI3I"
_GLIBC_CACHE_ENTRY_FORMAT = "<iIIIQ"
_GLIBC_CACHE_EXTENSION_MAGIC = 0xEAA42174
_GLIBC_CACHE_EXTENSION_HEADER_FORMAT = "<II"
_GLIBC_CACHE_EXTENSION_SECTION_FORMAT = "<IIII"
_GLIBC_CACHE_COMPARATOR_MAX = (1 << 31) - 1
_DEFAULT_LOADER_DIRECTORIES = (
    "/lib/x86_64-linux-gnu",
    "/usr/lib/x86_64-linux-gnu",
    "/lib",
    "/usr/lib",
)
_WRITABLE_RUNTIME_OVERLAY_ROOTS = (
    "/home",
    "/workspace",
    "/tmp",
    "/run",
    "/candidate",
    "/proc",
    "/dev",
    "/sys",
)
_STRUCTURAL_MOUNTPOINT_RELPATHS = (
    "candidate",
    "dev",
    "home",
    "proc",
    "run",
    "tmp",
    "workspace",
)
BOOTSTRAP_CLOSURE_SCHEMA_VERSION = "provider_bootstrap_closure.v1"
BOOTSTRAP_PROFILE = "cpython312_isolated_no_site.v1"
_BOOTSTRAP_PYTHON_FLAGS = ("-I", "-S")
_BOOTSTRAP_SHIM_RELATIVE_PATH = "libexec/provider-launch-shim-v1.py"
_BOOTSTRAP_PURE_MODULE_RELATIVE_PATHS = (
    "encodings/__init__.py",
    "encodings/aliases.py",
    "encodings/utf_8.py",
    "ctypes/__init__.py",
    "ctypes/_endian.py",
    "types.py",
    "struct.py",
    "os.py",
)
_BOOTSTRAP_MODULE_IMPORTS = (
    "module:from:__future__:annotations",
    "module:import:ctypes",
    "module:import:errno",
    "module:import:os",
    "module:import:struct",
    "module:import:sys",
)
_BOOTSTRAP_ALLOWED_LOCAL_IMPORTS = frozenset(
    {"json", "selectors", "subprocess", "time"}
)
_BOOTSTRAP_LOCAL_IMPORTS = (
    "function:launch_provider_via_shim:import:json",
    "function:launch_provider_via_shim:import:selectors",
    "function:launch_provider_via_shim:import:subprocess",
    "function:launch_provider_via_shim:import:time",
)
_REVIEWED_BOOTSTRAP_SHIM_DIGEST = (
    "sha256:94b6d92bd566a45767544e06cb2daa7f"
    "778246fa6240024ac73aaba3d7ab14c1"
)


@dataclass(frozen=True, slots=True)
class ProviderEnvironmentManifestEntry:
    """One normalized provider-visible rootfs entry."""

    path: str
    kind: str
    mode: int
    uid: int
    gid: int
    atime_ns: int
    mtime_ns: int
    size: int | None = None
    digest: str | None = None
    link_text: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "path": self.path,
            "kind": self.kind,
            "mode": self.mode,
            "uid": self.uid,
            "gid": self.gid,
            "atime_ns": self.atime_ns,
            "mtime_ns": self.mtime_ns,
        }
        if self.kind == "regular_file":
            value["size"] = self.size
            value["digest"] = self.digest
        elif self.kind == "symlink":
            value["link_text"] = self.link_text
        return value


@dataclass(frozen=True, slots=True)
class ProviderEnvironmentManifest:
    """Immutable canonical ``provider_environment_manifest.v1`` identity."""

    schema_version: str
    provider_prefix: str
    entries: tuple[ProviderEnvironmentManifestEntry, ...]
    canonical_json: bytes = field(repr=False)
    digest: str

    @property
    def environment_digest(self) -> str:
        return self.digest

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover - construction invariant
            raise AssertionError("canonical environment manifest is not an object")
        return value


@dataclass(slots=True)
class ProviderEnvironmentSnapshot:
    """One freshly published run-owned environment snapshot with a pinned root."""

    manifest: ProviderEnvironmentManifest
    authority_path: Path
    rootfs_path: Path
    manifest_path: Path
    root_fd: int

    @property
    def digest(self) -> str:
        return self.manifest.digest

    def close(self) -> None:
        if self.root_fd < 0:
            return
        os.close(self.root_fd)
        self.root_fd = -1


class ProviderIsolationEnvironmentError(ValueError):
    """Closed manifest/snapshot rejection with stable safe diagnostics."""

    def __init__(
        self,
        issues: Sequence[ProviderIsolationIssue],
        *,
        code: str | None = None,
    ):
        self.issues = tuple(issues)
        self.code = code or (
            self.issues[0].code if self.issues else ENVIRONMENT_INVALID_CODE
        )
        detail = "; ".join(
            f"{issue.path}: {issue.message}" for issue in self.issues
        )
        super().__init__(f"{self.code}: {detail}")


@dataclass(frozen=True, slots=True)
class ParsedElf:
    """The startup-relevant fields read from one ELF without executing it."""

    elf_class: int
    data_encoding: int
    ident_version: int
    elf_type: int
    machine: int
    header_version: int
    interpreter: str | None
    needed: tuple[str, ...]
    rpath: tuple[str, ...]
    runpath: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _GlibcCacheEntry:
    flags: int
    key: str
    value: str
    osversion: int
    hwcap: int


@dataclass(frozen=True, slots=True)
class ProviderRuntimeClosureEntry:
    """One content-addressed provider-visible runtime-closure member."""

    path: str
    resolved_path: str
    size: int
    digest: str


@dataclass(frozen=True, slots=True)
class ProviderRuntimeClosure:
    """A complete non-executingly discovered provider startup closure."""

    provider_prefix: str
    entrypoint: str
    entries: tuple[ProviderRuntimeClosureEntry, ...]


@dataclass(frozen=True, slots=True)
class ProviderBootstrapClosure:
    """Content-addressed fixed CPython bootstrap admission record."""

    schema_version: str
    environment_digest: str
    provider_prefix: str
    python_path: str
    python_flags: tuple[str, ...]
    python_runtime_closure: ProviderRuntimeClosure
    shim_path: str
    shim_size: int
    shim_digest: str
    shim_mode: int
    shim_materialization: str
    shim_imports: tuple[str, ...]
    profile: str
    prospective_sys_path: tuple[str, ...]
    allowed_import_roots: tuple[str, ...]
    import_projection_root: str
    import_projection_entry_count: int
    import_projection_digest: str
    required_pure_module_paths: tuple[str, ...]
    ctypes_extension_path: str
    ctypes_runtime_closure: ProviderRuntimeClosure
    ctypes_libffi_path: str
    required_absent_startup_paths: tuple[str, ...]
    canonical_json: bytes = field(repr=False)
    digest: str

    def to_dict(self) -> dict[str, Any]:
        value = json.loads(self.canonical_json)
        if not isinstance(value, dict):  # pragma: no cover - construction invariant
            raise AssertionError("canonical bootstrap closure is not an object")
        return value


@dataclass(frozen=True, slots=True)
class _PinnedRuntimeEdge:
    parent_fd: int
    child_fd: int
    name: str
    opened_stat: os.stat_result
    issue_path: str
    link_text: str | None = None


class _RootfsResolutionFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        missing: bool = False,
        observation: _PinnedRuntimeNegativeName | None = None,
    ):
        self.missing = missing
        self.observation = observation
        super().__init__(message)


class MountIdentityUnavailable(RuntimeError):
    """Descriptor-bound Linux mount identity could not be proved."""


@dataclass(frozen=True, slots=True)
class _ScannedEntry:
    entry: ProviderEnvironmentManifestEntry
    source_stat: os.stat_result
    mount_id: int


@dataclass(frozen=True, slots=True)
class _PinnedEdge:
    parent_fd: int
    child_fd: int
    name: str
    opened_stat: os.stat_result
    issue_path: str


@dataclass(slots=True)
class _PinnedSource:
    root_fd: int
    _owned_fds: list[int]
    _edges: tuple[_PinnedEdge, ...]

    def revalidate_edges(self) -> None:
        for edge in self._edges:
            try:
                opened = os.fstat(edge.child_fd)
                linked = _lstat_at(edge.parent_fd, edge.name)
            except OSError as exc:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{edge.issue_path}.identity",
                            "source authority edge changed during assembly",
                        ),
                    )
                ) from exc
            _require_same_pinned_edge_identity(
                edge.opened_stat,
                opened,
                issue_path=edge.issue_path,
                changed_message="source authority edge changed during assembly",
            )
            _require_same_pinned_edge_identity(
                edge.opened_stat,
                linked,
                issue_path=edge.issue_path,
                changed_message="source authority edge changed during assembly",
            )

    def close(self) -> None:
        for fd in reversed(self._owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._owned_fds.clear()
        self.root_fd = -1


@dataclass(slots=True)
class _PinnedRuntimeFile:
    requested_path: str
    resolved_path: str
    file_fd: int
    stat: os.stat_result
    _owned_fds: list[int]
    _edges: tuple[_PinnedRuntimeEdge, ...]

    def revalidate(self) -> None:
        for edge in self._edges:
            try:
                opened = os.fstat(edge.child_fd)
                linked = _lstat_at(edge.parent_fd, edge.name)
            except OSError as exc:
                raise _runtime_closure_error(
                    edge.issue_path,
                    "runtime closure path changed during capture",
                ) from exc
            _require_same_source_identity(
                edge.opened_stat,
                opened,
                issue_path=edge.issue_path,
            )
            _require_same_source_identity(
                edge.opened_stat,
                linked,
                issue_path=edge.issue_path,
            )
            if edge.link_text is not None:
                try:
                    current_link = os.readlink("", dir_fd=edge.child_fd)
                    linked_text = os.readlink(
                        edge.name,
                        dir_fd=edge.parent_fd,
                    )
                except OSError as exc:
                    raise _runtime_closure_error(
                        edge.issue_path,
                        "runtime closure symlink changed during capture",
                    ) from exc
                if (
                    current_link != edge.link_text
                    or linked_text != edge.link_text
                ):
                    raise _runtime_closure_error(
                        edge.issue_path,
                        "runtime closure symlink changed during capture",
                    )

    def close(self) -> None:
        for fd in reversed(self._owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._owned_fds.clear()
        self.file_fd = -1


@dataclass(slots=True)
class _PinnedRuntimeNegativeName:
    parent_fd: int
    parent_stat: os.stat_result
    name: str | None
    issue_path: str
    authority_edges: tuple[_PinnedRuntimeEdge, ...] = ()
    _owned_fds: list[int] = field(default_factory=list)

    def revalidate(self) -> None:
        try:
            opened_parent = os.fstat(self.parent_fd)
        except OSError as exc:
            raise _runtime_closure_error(
                self.issue_path,
                "runtime negative lookup authority changed during capture",
            ) from exc
        _require_same_source_identity(
            self.parent_stat,
            opened_parent,
            issue_path=self.issue_path,
        )
        for edge in self.authority_edges:
            try:
                opened = os.fstat(edge.child_fd)
                linked_parent = _lstat_at(edge.parent_fd, edge.name)
            except OSError as exc:
                raise _runtime_closure_error(
                    self.issue_path,
                    "runtime negative lookup authority changed during capture",
                ) from exc
            _require_same_source_identity(
                edge.opened_stat,
                opened,
                issue_path=self.issue_path,
            )
            _require_same_source_identity(
                edge.opened_stat,
                linked_parent,
                issue_path=self.issue_path,
            )
            if edge.link_text is not None:
                try:
                    held_link = os.readlink("", dir_fd=edge.child_fd)
                    linked_text = os.readlink(
                        edge.name,
                        dir_fd=edge.parent_fd,
                    )
                except OSError as exc:
                    raise _runtime_closure_error(
                        self.issue_path,
                        "runtime lookup symlink changed during capture",
                    ) from exc
                if (
                    held_link != edge.link_text
                    or linked_text != edge.link_text
                ):
                    raise _runtime_closure_error(
                        self.issue_path,
                        "runtime lookup symlink changed during capture",
                    )
        if self.name is None:
            return
        try:
            _lstat_at(self.parent_fd, self.name)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise _runtime_closure_error(
                self.issue_path,
                "runtime negative lookup could not be revalidated",
            ) from exc
        raise _runtime_closure_error(
            self.issue_path,
            "runtime negative lookup changed during capture",
        )

    def close(self) -> None:
        for fd in reversed(self._owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._owned_fds.clear()
        self.parent_fd = -1


@dataclass(slots=True)
class _PinnedRuntimeClosureCapture:
    source: _PinnedSource
    files: dict[str, _PinnedRuntimeFile]
    negative_names: list[_PinnedRuntimeNegativeName] = field(
        default_factory=list
    )

    def require_file(
        self,
        provider_path: str,
        *,
        require_executable: bool,
    ) -> _PinnedRuntimeFile:
        canonical = _canonical_runtime_path(
            provider_path,
            issue_path="$.runtime_closure.path",
            label="runtime closure path",
        )
        _reject_runtime_writable_overlay_path(
            canonical,
            issue_path=canonical,
        )
        pinned = self.files.get(canonical)
        if pinned is None:
            try:
                pinned = _pin_rootfs_runtime_file(
                    self.source.root_fd,
                    canonical,
                )
            except _RootfsResolutionFailure as exc:
                raise _runtime_closure_error(canonical, str(exc)) from exc
            self.files[canonical] = pinned
        _reject_runtime_writable_overlay_path(
            pinned.resolved_path,
            issue_path=canonical,
        )
        if (
            require_executable
            and not stat.S_IMODE(pinned.stat.st_mode) & 0o111
        ):
            raise _runtime_closure_error(
                canonical,
                "runtime executable has no execute bit",
            )
        return pinned

    def probe_file(self, provider_path: str) -> _PinnedRuntimeFile | None:
        canonical = _canonical_runtime_path(
            provider_path,
            issue_path="$.runtime_closure.path",
            label="runtime closure path",
        )
        _reject_runtime_writable_overlay_path(
            canonical,
            issue_path=canonical,
        )
        pinned = self.files.get(canonical)
        if pinned is not None:
            return pinned
        try:
            pinned = _pin_rootfs_runtime_file(
                self.source.root_fd,
                canonical,
                retain_missing=True,
            )
        except _RootfsResolutionFailure as exc:
            if exc.missing:
                if exc.observation is not None:
                    self.negative_names.append(exc.observation)
                return None
            raise _runtime_closure_error(canonical, str(exc)) from exc
        self.files[canonical] = pinned
        _reject_runtime_writable_overlay_path(
            pinned.resolved_path,
            issue_path=canonical,
        )
        return pinned

    def revalidate(self) -> None:
        self.source.revalidate_edges()
        for observation in self.negative_names:
            observation.revalidate()
        for pinned in self.files.values():
            pinned.revalidate()
        for observation in self.negative_names:
            observation.revalidate()
        self.source.revalidate_edges()

    def close(self) -> None:
        for pinned in reversed(tuple(self.files.values())):
            pinned.close()
        self.files.clear()
        for observation in reversed(self.negative_names):
            observation.close()
        self.negative_names.clear()
        self.source.close()


@dataclass(slots=True)
class _PinnedSnapshot:
    run_root_path: Path
    authority_path: Path
    rootfs_path: Path
    manifest_path: Path
    snapshots_fd: int
    root_fd: int
    manifest_fd: int
    _owned_fds: list[int]
    _edges: tuple[_PinnedEdge, ...]

    def revalidate_edges(self) -> None:
        for edge in self._edges:
            try:
                opened = os.fstat(edge.child_fd)
                linked = _lstat_at(edge.parent_fd, edge.name)
            except OSError as exc:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{edge.issue_path}.identity",
                            "snapshot authority edge changed during verification",
                        ),
                    )
                ) from exc
            _require_same_pinned_edge_identity(
                edge.opened_stat,
                opened,
                issue_path=edge.issue_path,
            )
            _require_same_pinned_edge_identity(
                edge.opened_stat,
                linked,
                issue_path=edge.issue_path,
            )

    def detach_root_fd(self) -> int:
        if self.root_fd < 0:
            raise RuntimeError("snapshot root descriptor is not owned")
        root_fd = self.root_fd
        self._owned_fds.remove(root_fd)
        self.root_fd = -1
        return root_fd

    def close(self) -> None:
        for fd in reversed(self._owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._owned_fds.clear()
        self.snapshots_fd = -1
        self.root_fd = -1
        self.manifest_fd = -1


@dataclass(slots=True)
class _SnapshotAssembly:
    """Pinned destination authority for one private snapshot assembly."""

    run_root_path: Path
    authority_path: Path
    staging_path: Path
    rootfs_path: Path
    run_root_fd: int
    authority_fd: int
    staging_fd: int
    rootfs_fd: int
    staging_name: str
    rootfs_name: str
    _owned_fds: list[int]
    _edges: tuple[_PinnedEdge, ...]
    manifest_fd: int = -1
    rename_attempted: bool = False
    renamed: bool = False
    final_name: str | None = None

    def abort(self) -> None:
        if self.rename_attempted:
            self.close()
            return
        try:
            _remove_held_private_staging(
                self.authority_fd,
                self.staging_fd,
            )
        finally:
            self.close()

    def adopt_manifest_fd(self, fd: int) -> None:
        if self.manifest_fd >= 0:
            raise RuntimeError("snapshot manifest descriptor is already owned")
        self.manifest_fd = fd
        self._owned_fds.append(fd)

    def detach_root_fd(self) -> int:
        if self.rootfs_fd < 0:
            raise RuntimeError("snapshot root descriptor is not owned")
        rootfs_fd = self.rootfs_fd
        self._owned_fds.remove(rootfs_fd)
        self.rootfs_fd = -1
        return rootfs_fd

    def revalidate_before_rename(self) -> None:
        self._revalidate_edges(include_staging_link=True)
        self._require_manifest_link()

    def begin_rename(self, final_name: str) -> None:
        if self.rename_attempted:
            raise RuntimeError("snapshot publication rename was already attempted")
        self.rename_attempted = True
        self.final_name = final_name

    def mark_renamed(self, final_name: str) -> None:
        if not self.rename_attempted or self.final_name != final_name:
            raise RuntimeError("snapshot publication rename was not prepared")
        self.renamed = True

    def revalidate_after_rename(self) -> None:
        if not self.renamed or self.final_name is None:
            raise RuntimeError("snapshot publication has not been marked renamed")
        self._revalidate_edges(include_staging_link=False)
        _require_same_held_directory_identity(
            os.fstat(self.staging_fd),
            _lstat_at(self.authority_fd, self.final_name),
            issue_path="$.snapshot.identity",
            message="published snapshot authority does not name held staging",
        )
        self._require_manifest_link()

    def _revalidate_edges(self, *, include_staging_link: bool) -> None:
        for edge in self._edges:
            if edge.child_fd == self.staging_fd and not include_staging_link:
                continue
            try:
                opened = os.fstat(edge.child_fd)
                linked = _lstat_at(edge.parent_fd, edge.name)
            except OSError as exc:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{edge.issue_path}.identity",
                            "snapshot assembly edge changed during publication",
                        ),
                    )
                ) from exc
            if edge.child_fd in {self.staging_fd, self.rootfs_fd}:
                _require_same_held_directory_identity(
                    edge.opened_stat,
                    opened,
                    issue_path=edge.issue_path,
                    message="held snapshot directory changed during publication",
                )
                _require_same_held_directory_identity(
                    opened,
                    linked,
                    issue_path=edge.issue_path,
                    message="snapshot directory link changed during publication",
                )
            else:
                _require_same_pinned_edge_identity(
                    edge.opened_stat,
                    opened,
                    issue_path=edge.issue_path,
                    changed_message=(
                        "snapshot assembly edge changed during publication"
                    ),
                )
                _require_same_pinned_edge_identity(
                    edge.opened_stat,
                    linked,
                    issue_path=edge.issue_path,
                    changed_message=(
                        "snapshot assembly edge changed during publication"
                    ),
                )

    def _require_manifest_link(self) -> None:
        if self.manifest_fd < 0:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.snapshot_manifest",
                        "snapshot manifest descriptor is unavailable",
                    ),
                )
            )
        opened = os.fstat(self.manifest_fd)
        try:
            linked = _lstat_at(self.staging_fd, "manifest.json")
        except OSError as exc:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.snapshot_manifest.identity",
                        "snapshot manifest link changed during publication",
                    ),
                )
            ) from exc
        _require_same_pinned_edge_identity(
            opened,
            linked,
            issue_path="$.snapshot_manifest",
            changed_message="snapshot manifest link changed during publication",
        )

    def close(self) -> None:
        for fd in reversed(self._owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self._owned_fds.clear()
        self.run_root_fd = -1
        self.authority_fd = -1
        self.staging_fd = -1
        self.rootfs_fd = -1
        self.manifest_fd = -1


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


def discover_provider_runtime_closure(
    rootfs: str | os.PathLike[str],
    executable: str,
    *,
    provider_prefix: str,
) -> ProviderRuntimeClosure:
    """Discover a provider entrypoint's sealed-rootfs closure without execution."""

    root = _require_runtime_rootfs(rootfs)
    prefix_issues = _absolute_prefix_issues(provider_prefix)
    if prefix_issues:
        raise ProviderIsolationEnvironmentError(prefix_issues)
    source = _open_source_binding(root)
    return _discover_provider_runtime_closure_from_owned_source(
        source,
        executable,
        provider_prefix=provider_prefix,
        initial_role="entry",
    )


def _discover_provider_runtime_closure_from_fd(
    root_fd: int,
    executable: str,
    *,
    provider_prefix: str,
    initial_role: str,
) -> ProviderRuntimeClosure:
    """Discover a closure from a duplicated borrowed root descriptor."""

    source = _duplicate_borrowed_runtime_source(root_fd)
    return _discover_provider_runtime_closure_from_owned_source(
        source,
        executable,
        provider_prefix=provider_prefix,
        initial_role=initial_role,
    )


def _duplicate_borrowed_runtime_source(root_fd: int) -> _PinnedSource:
    duplicated_fd = -1
    try:
        duplicated_fd = os.dup(root_fd)
        os.set_inheritable(duplicated_fd, False)
        opened = os.fstat(duplicated_fd)
    except (OSError, TypeError, ValueError) as exc:
        if duplicated_fd >= 0:
            os.close(duplicated_fd)
        raise _runtime_closure_error(
            "$.runtime_closure.rootfs",
            "borrowed runtime root descriptor is unavailable",
        ) from exc
    if not stat.S_ISDIR(opened.st_mode):
        os.close(duplicated_fd)
        raise _runtime_closure_error(
            "$.runtime_closure.rootfs",
            "borrowed runtime root descriptor must name a directory",
        )
    return _PinnedSource(
        root_fd=duplicated_fd,
        _owned_fds=[duplicated_fd],
        _edges=(),
    )


def _discover_provider_runtime_closure_from_owned_source(
    source: _PinnedSource,
    executable: str,
    *,
    provider_prefix: str,
    initial_role: str,
) -> ProviderRuntimeClosure:
    prefix_issues = _absolute_prefix_issues(provider_prefix)
    if prefix_issues:
        source.close()
        raise ProviderIsolationEnvironmentError(prefix_issues)
    if initial_role not in {"entry", "dependency"}:
        source.close()
        raise _runtime_closure_error(
            "$.runtime_closure.role",
            "runtime closure initial role is unsupported",
        )
    try:
        entrypoint = _runtime_entrypoint_path(executable, provider_prefix)
    except BaseException:
        source.close()
        raise
    capture = _PinnedRuntimeClosureCapture(source=source, files={})
    try:
        _retain_runtime_ld_so_preload_absence(capture)
        rows: dict[str, ProviderRuntimeClosureEntry] = {}
        visiting: set[str] = set()
        parsed_members: dict[str, ParsedElf] = {}
        member_kinds: dict[str, str] = {}
        glibc_cache_loaded = False
        glibc_cache_entries: tuple[_GlibcCacheEntry, ...] = ()

        def resolve_glibc_cache_dependency(needed: str) -> str | None:
            nonlocal glibc_cache_loaded, glibc_cache_entries
            if not glibc_cache_loaded:
                glibc_cache_loaded = True
                pinned_cache = capture.probe_file(_GLIBC_CACHE_PATH)
                if pinned_cache is not None:
                    _reject_runtime_writable_overlay_path(
                        pinned_cache.resolved_path,
                        issue_path=_GLIBC_CACHE_PATH,
                    )
                    size, digest = _hash_regular_file(pinned_cache.file_fd)
                    rows[_GLIBC_CACHE_PATH] = ProviderRuntimeClosureEntry(
                        path=pinned_cache.requested_path,
                        resolved_path=pinned_cache.resolved_path,
                        size=size,
                        digest=digest,
                    )
                    glibc_cache_entries = _parse_glibc_cache_fd(
                        pinned_cache.file_fd
                    )
            return _select_glibc_cache_dependency(
                glibc_cache_entries,
                needed=needed,
            )

        def visit(
            provider_path: str,
            *,
            role: str,
            inherited_rpath: tuple[str, ...] = (),
        ) -> None:
            canonical = _canonical_runtime_path(
                provider_path,
                issue_path="$.runtime_closure.path",
                label="runtime closure path",
            )
            if canonical in rows or canonical in visiting:
                member_kind = member_kinds.get(canonical)
                if member_kind is None:
                    raise _runtime_closure_error(
                        canonical,
                        "runtime closure member format is unresolved during "
                        "recursive role validation",
                    )
                if member_kind == "script":
                    _require_script_runtime_role(
                        role=role,
                        provider_path=canonical,
                    )
                    return
                parsed = parsed_members.get(canonical)
                if member_kind != "elf" or parsed is None:
                    raise _runtime_closure_error(
                        canonical,
                        "ELF role metadata is unresolved during recursive "
                        "role validation",
                    )
                _require_elf_runtime_role(
                    parsed,
                    role=role,
                    provider_path=canonical,
                )
                return
            pinned = capture.require_file(
                canonical,
                require_executable=role != "dependency",
            )
            size, digest = _hash_regular_file(pinned.file_fd)
            rows[canonical] = ProviderRuntimeClosureEntry(
                path=pinned.requested_path,
                resolved_path=pinned.resolved_path,
                size=size,
                digest=digest,
            )
            visiting.add(canonical)
            try:
                prefix = _read_runtime_prefix_fd(pinned.file_fd, 4096)
                if prefix.startswith(b"#!"):
                    member_kinds[canonical] = "script"
                    _require_script_runtime_role(
                        role=role,
                        provider_path=canonical,
                    )
                    interpreter, arguments = _parse_shebang(
                        prefix,
                        canonical,
                    )
                    if interpreter == "/usr/bin/env":
                        if len(arguments) != 1 or not _runtime_command_name(
                            arguments[0]
                        ):
                            raise _runtime_closure_error(
                                canonical,
                                "/usr/bin/env shebang must name exactly one "
                                "provider-prefix executable",
                            )
                        visit(interpreter, role="script-executable")
                        visit(
                            posixpath.join(
                                provider_prefix,
                                "bin",
                                arguments[0],
                            ),
                            role="script-executable",
                        )
                    else:
                        visit(interpreter, role="script-executable")
                    return
                if not prefix.startswith(_ELF_MAGIC):
                    raise _runtime_closure_error(
                        canonical,
                        "runtime closure member is neither an ELF nor a script",
                    )
                member_kinds[canonical] = "elf"
                parsed = _parse_elf_fd(pinned.file_fd, canonical)
                parsed_members[canonical] = parsed
                _require_elf_runtime_role(
                    parsed,
                    role=role,
                    provider_path=canonical,
                )
                if parsed.interpreter is not None:
                    visit(
                        _canonical_runtime_path(
                            parsed.interpreter,
                            issue_path="$.runtime_closure.interpreter",
                            label="ELF interpreter",
                        ),
                        role="interpreter",
                    )
                if parsed.runpath:
                    direct_search = _expand_elf_search_directories(
                        parsed.runpath,
                        containing_object=canonical,
                    )
                    child_inherited_rpath = inherited_rpath
                else:
                    own_rpath = _expand_elf_search_directories(
                        parsed.rpath,
                        containing_object=canonical,
                    )
                    direct_search = (*own_rpath, *inherited_rpath)
                    child_inherited_rpath = direct_search
                for needed in parsed.needed:
                    dependency = _resolve_elf_dependency(
                        capture,
                        needed,
                        containing_object=canonical,
                        search_directories=direct_search,
                        cache_resolver=resolve_glibc_cache_dependency,
                    )
                    visit(
                        dependency,
                        role="dependency",
                        inherited_rpath=child_inherited_rpath,
                    )
            finally:
                visiting.discard(canonical)

        visit(entrypoint, role=initial_role)
        capture.revalidate()
        return ProviderRuntimeClosure(
            provider_prefix=provider_prefix,
            entrypoint=entrypoint,
            entries=tuple(rows.values()),
        )
    finally:
        capture.close()


def _require_script_runtime_role(
    *,
    role: str,
    provider_path: str,
) -> None:
    if role in {"interpreter", "dependency"}:
        raise _runtime_closure_error(
            provider_path,
            f"script cannot be used as ELF {role}",
        )


def _require_elf_runtime_role(
    parsed: ParsedElf,
    *,
    role: str,
    provider_path: str,
) -> None:
    if (
        role in {"interpreter", "dependency"}
        and parsed.elf_type != _ELF_TYPE_DYN
    ):
        raise _runtime_closure_error(
            provider_path,
            f"ELF {role} must be ET_DYN",
        )
    if (
        parsed.interpreter is not None
        and parsed.interpreter != _CONVENTIONAL_X86_64_LOADER
    ):
        raise _runtime_closure_error(
            provider_path,
            "dynamic executable selects an unreviewed ELF interpreter",
        )
    if (
        role in {"entry", "script-executable"}
        and (parsed.interpreter is not None or parsed.needed)
        and parsed.interpreter != _CONVENTIONAL_X86_64_LOADER
    ):
        raise _runtime_closure_error(
            provider_path,
            "dynamically-needed executable must select the reviewed "
            "x86_64 glibc loader",
        )


def verify_provider_runtime_closure(
    rootfs: str | os.PathLike[str],
    recorded: ProviderRuntimeClosure,
) -> ProviderRuntimeClosure:
    """Recompute and require exact content equality with a recorded closure."""

    if not isinstance(recorded, ProviderRuntimeClosure):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.runtime_closure",
                    "recorded runtime closure has the wrong type",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
        )
    try:
        current = discover_provider_runtime_closure(
            rootfs,
            recorded.entrypoint,
            provider_prefix=recorded.provider_prefix,
        )
    except ProviderIsolationEnvironmentError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.runtime_closure",
                    "recorded runtime closure is no longer present and valid",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
        ) from exc
    if current != recorded:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.runtime_closure",
                    "recorded runtime closure digest or resolution changed",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
        )
    return current


def validate_fixed_provider_bootstrap_from_fd(
    root_fd: int,
    manifest: ProviderEnvironmentManifest,
    provider_prefix: str,
    *,
    shim_materialization: str = "virtual_injected",
) -> ProviderBootstrapClosure:
    """Admit the fixed sealed CPython 3.12 launch bootstrap from a borrowed FD."""

    if not isinstance(manifest, ProviderEnvironmentManifest):
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            "bootstrap manifest has the wrong type",
        )
    try:
        reloaded_manifest = load_provider_environment_manifest(
            manifest.to_dict(),
            expected_digest=manifest.digest,
        )
    except (ProviderIsolationEnvironmentError, TypeError, ValueError) as exc:
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            "bootstrap manifest is not a valid content-addressed identity",
        ) from exc
    if reloaded_manifest != manifest:
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            "bootstrap manifest fields disagree with its canonical identity",
        )
    prefix_issues = _absolute_prefix_issues(provider_prefix)
    if prefix_issues:
        raise ProviderIsolationEnvironmentError(prefix_issues)
    if provider_prefix != manifest.provider_prefix:
        raise _bootstrap_closure_error(
            "$.bootstrap.provider_prefix",
            "bootstrap prefix does not match the environment manifest",
        )
    if shim_materialization not in {"virtual_injected", "present"}:
        raise _bootstrap_closure_error(
            "$.bootstrap.shim.materialization",
            "bootstrap shim materialization is unsupported",
        )

    entries = {entry.path: entry for entry in manifest.entries}
    source = _duplicate_borrowed_runtime_source(root_fd)
    capture = _PinnedRuntimeClosureCapture(source=source, files={})
    try:
        root_before = os.fstat(source.root_fd)
        _require_bootstrap_tree_matches_manifest(
            source.root_fd,
            manifest,
            shim_materialization=shim_materialization,
        )
        prefix = provider_prefix.rstrip("/")
        python_path = f"{prefix}/bin/python"
        shim_path = f"{prefix}/{_BOOTSTRAP_SHIM_RELATIVE_PATH}"
        stdlib_root = f"{prefix}/lib/python3.12"
        dynload_root = f"{stdlib_root}/lib-dynload"
        prospective_sys_path = (
            f"{prefix}/lib/python312.zip",
            stdlib_root,
            dynload_root,
        )
        allowed_import_roots = (stdlib_root, dynload_root)
        required_pure_module_paths = tuple(
            f"{stdlib_root}/{relative}"
            for relative in _BOOTSTRAP_PURE_MODULE_RELATIVE_PATHS
        )
        required_absent_startup_paths = (
            f"{prefix}/pyvenv.cfg",
            f"{prefix}/bin/pyvenv.cfg",
            f"{prefix}/bin/python._pth",
            f"{prefix}/bin/python3._pth",
            f"{prefix}/bin/python312._pth",
            f"{prefix}/bin/python3.12._pth",
            f"{prefix}/lib/python312.zip",
            f"{stdlib_root}/sitecustomize.py",
            f"{stdlib_root}/usercustomize.py",
            "/etc/python3.12/sitecustomize.py",
        )

        _require_bootstrap_manifest_directory(
            entries,
            stdlib_root,
        )
        _require_bootstrap_manifest_directory(
            entries,
            dynload_root,
        )
        _require_bootstrap_regular_file(
            capture,
            entries,
            python_path,
            require_executable=True,
        )

        packaged_shim = _packaged_launch_shim_bytes()
        shim_entry = _require_bootstrap_manifest_regular_entry(
            entries,
            shim_path,
        )
        if (
            shim_entry.mode != 0o444
            or shim_entry.size != len(packaged_shim)
            or shim_entry.digest != _digest(packaged_shim)
        ):
            raise _bootstrap_closure_error(
                "$.bootstrap.shim",
                "launch shim manifest row differs from the packaged resource",
            )
        if shim_materialization == "virtual_injected":
            if capture.probe_file(shim_path) is not None:
                raise _bootstrap_closure_error(
                    "$.bootstrap.shim",
                    "virtual launch shim collides with a source member",
                )
            shim_bytes = packaged_shim
        else:
            shim_pinned = _require_bootstrap_regular_file(
                capture,
                entries,
                shim_path,
                require_executable=False,
            )
            shim_bytes = _read_regular_file_fd(shim_pinned.file_fd)
            if shim_bytes != packaged_shim:
                raise _bootstrap_closure_error(
                    "$.bootstrap.shim",
                    "materialized launch shim differs from the packaged resource",
                )
        shim_imports = _validate_bootstrap_shim_imports(shim_bytes)

        for path in required_pure_module_paths:
            _require_bootstrap_regular_file(
                capture,
                entries,
                path,
                require_executable=False,
            )

        extension_pattern = re.compile(
            "^"
            + re.escape(
                f"{dynload_root.lstrip('/')}/"
                "_ctypes.cpython-312-"
            )
            + r"[^/]+\.so$"
        )
        extension_entries = tuple(
            entry
            for entry in manifest.entries
            if entry.kind == "regular_file"
            and extension_pattern.fullmatch(entry.path) is not None
        )
        if len(extension_entries) != 1:
            raise _bootstrap_closure_error(
                "$.bootstrap.python_imports._ctypes",
                "bootstrap profile requires exactly one CPython 3.12 _ctypes extension",
            )
        ctypes_extension_path = f"/{extension_entries[0].path}"
        _require_bootstrap_regular_file(
            capture,
            entries,
            ctypes_extension_path,
            require_executable=False,
        )

        for path in required_absent_startup_paths:
            if path.lstrip("/") in entries:
                raise _bootstrap_closure_error(
                    "$.bootstrap.python_imports.startup_configuration",
                    f"startup configuration {path!r} is forbidden",
                )
            if capture.probe_file(path) is not None:
                raise _bootstrap_closure_error(
                    "$.bootstrap.python_imports.startup_configuration",
                    f"startup configuration {path!r} is present",
                )

        python_runtime_closure = (
            _discover_provider_runtime_closure_from_fd(
                source.root_fd,
                python_path,
                provider_prefix=provider_prefix,
                initial_role="entry",
            )
        )
        _require_manifest_backed_runtime_closure(
            entries,
            python_runtime_closure,
            issue_path="$.bootstrap.python.runtime_closure",
        )
        ctypes_runtime_closure = (
            _discover_provider_runtime_closure_from_fd(
                source.root_fd,
                ctypes_extension_path,
                provider_prefix=provider_prefix,
                initial_role="dependency",
            )
        )
        _require_manifest_backed_runtime_closure(
            entries,
            ctypes_runtime_closure,
            issue_path="$.bootstrap.python_imports._ctypes.runtime_closure",
        )
        libffi_rows = tuple(
            row
            for row in ctypes_runtime_closure.entries
            if (
                posixpath.basename(row.path) == "libffi.so"
                or posixpath.basename(row.path).startswith("libffi.so.")
            )
        )
        if len(libffi_rows) != 1:
            raise _bootstrap_closure_error(
                "$.bootstrap.python_imports._ctypes.libffi",
                "the _ctypes closure must contain exactly one manifest-backed libffi",
            )
        ctypes_libffi_path = libffi_rows[0].path

        projection_entries = tuple(
            sorted(
                (
                    entry
                    for entry in manifest.entries
                    if entry.path == stdlib_root.lstrip("/")
                    or entry.path.startswith(
                        f"{stdlib_root.lstrip('/')}/"
                    )
                ),
                key=lambda entry: entry.path.encode("utf-8"),
            )
        )
        if not projection_entries:
            raise _bootstrap_closure_error(
                "$.bootstrap.python_imports.projection",
                "the stdlib manifest projection is empty",
            )
        projection_document = {
            "root": stdlib_root,
            "entries": [entry.to_dict() for entry in projection_entries],
        }
        projection_digest = _digest(
            canonical_isolation_json_bytes(projection_document)
        )

        capture.revalidate()
        _require_bootstrap_tree_matches_manifest(
            source.root_fd,
            manifest,
            shim_materialization=shim_materialization,
        )
        capture.revalidate()
        _require_same_source_identity(
            root_before,
            os.fstat(source.root_fd),
            issue_path="$.bootstrap.rootfs",
        )

        document = {
            "schema_version": BOOTSTRAP_CLOSURE_SCHEMA_VERSION,
            "environment_digest": manifest.digest,
            "provider_prefix": provider_prefix,
            "python": {
                "path": python_path,
                "flags": list(_BOOTSTRAP_PYTHON_FLAGS),
                "runtime_closure": _runtime_closure_document(
                    python_runtime_closure
                ),
            },
            "shim": {
                "path": shim_path,
                "size": len(shim_bytes),
                "digest": _digest(shim_bytes),
                "mode": shim_entry.mode,
                "materialization": shim_materialization,
                "imports": list(shim_imports),
            },
            "python_imports": {
                "profile": BOOTSTRAP_PROFILE,
                "prospective_sys_path": list(prospective_sys_path),
                "allowed_import_roots": list(allowed_import_roots),
                "manifest_projection": {
                    "root": stdlib_root,
                    "entry_count": len(projection_entries),
                    "digest": projection_digest,
                },
                "required_pure_module_paths": list(
                    required_pure_module_paths
                ),
                "_ctypes": {
                    "path": ctypes_extension_path,
                    "runtime_closure": _runtime_closure_document(
                        ctypes_runtime_closure
                    ),
                    "libffi_path": ctypes_libffi_path,
                },
                "required_absent_startup_paths": list(
                    required_absent_startup_paths
                ),
            },
        }
        canonical_json = canonical_isolation_json_bytes(document)
        return ProviderBootstrapClosure(
            schema_version=BOOTSTRAP_CLOSURE_SCHEMA_VERSION,
            environment_digest=manifest.digest,
            provider_prefix=provider_prefix,
            python_path=python_path,
            python_flags=_BOOTSTRAP_PYTHON_FLAGS,
            python_runtime_closure=python_runtime_closure,
            shim_path=shim_path,
            shim_size=len(shim_bytes),
            shim_digest=_digest(shim_bytes),
            shim_mode=shim_entry.mode,
            shim_materialization=shim_materialization,
            shim_imports=shim_imports,
            profile=BOOTSTRAP_PROFILE,
            prospective_sys_path=prospective_sys_path,
            allowed_import_roots=allowed_import_roots,
            import_projection_root=stdlib_root,
            import_projection_entry_count=len(projection_entries),
            import_projection_digest=projection_digest,
            required_pure_module_paths=required_pure_module_paths,
            ctypes_extension_path=ctypes_extension_path,
            ctypes_runtime_closure=ctypes_runtime_closure,
            ctypes_libffi_path=ctypes_libffi_path,
            required_absent_startup_paths=required_absent_startup_paths,
            canonical_json=canonical_json,
            digest=_digest(canonical_json),
        )
    finally:
        capture.close()


def _require_bootstrap_tree_matches_manifest(
    root_fd: int,
    manifest: ProviderEnvironmentManifest,
    *,
    shim_materialization: str,
) -> None:
    rebuilt = _build_provider_environment_manifest_from_fd(
        root_fd,
        manifest.provider_prefix,
        inject_launch_shim=shim_materialization == "virtual_injected",
        finalized_snapshot=False,
    )
    if rebuilt.canonical_json != manifest.canonical_json:
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            "bootstrap rootfs differs from the bound environment manifest",
        )


def _require_bootstrap_manifest_directory(
    entries: Mapping[str, ProviderEnvironmentManifestEntry],
    provider_path: str,
) -> ProviderEnvironmentManifestEntry:
    entry = entries.get(provider_path.lstrip("/"))
    if entry is None or entry.kind != "directory":
        raise _bootstrap_closure_error(
            "$.bootstrap.python_imports",
            f"required import directory {provider_path!r} is not manifest-backed",
        )
    return entry


def _require_bootstrap_manifest_regular_entry(
    entries: Mapping[str, ProviderEnvironmentManifestEntry],
    provider_path: str,
) -> ProviderEnvironmentManifestEntry:
    entry = entries.get(provider_path.lstrip("/"))
    if entry is None or entry.kind != "regular_file":
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            f"required regular file {provider_path!r} is not manifest-backed",
        )
    return entry


def _require_bootstrap_regular_file(
    capture: _PinnedRuntimeClosureCapture,
    entries: Mapping[str, ProviderEnvironmentManifestEntry],
    provider_path: str,
    *,
    require_executable: bool,
) -> _PinnedRuntimeFile:
    entry = _require_bootstrap_manifest_regular_entry(
        entries,
        provider_path,
    )
    pinned = capture.require_file(
        provider_path,
        require_executable=require_executable,
    )
    if pinned.resolved_path != provider_path:
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            f"fixed bootstrap member {provider_path!r} must not be a symlink",
        )
    size, digest = _hash_regular_file(pinned.file_fd)
    if entry.size != size or entry.digest != digest:
        raise _bootstrap_closure_error(
            "$.bootstrap.manifest",
            f"bootstrap member {provider_path!r} differs from its manifest row",
        )
    return pinned


def _require_manifest_backed_runtime_closure(
    entries: Mapping[str, ProviderEnvironmentManifestEntry],
    closure: ProviderRuntimeClosure,
    *,
    issue_path: str,
) -> None:
    for row in closure.entries:
        requested = entries.get(row.path.lstrip("/"))
        resolved = entries.get(row.resolved_path.lstrip("/"))
        if (
            requested is None
            or resolved is None
            or resolved.kind != "regular_file"
            or resolved.size != row.size
            or resolved.digest != row.digest
        ):
            raise _bootstrap_closure_error(
                issue_path,
                f"runtime closure member {row.path!r} is not manifest-backed",
            )


def _runtime_closure_document(
    closure: ProviderRuntimeClosure,
) -> dict[str, Any]:
    return {
        "provider_prefix": closure.provider_prefix,
        "entrypoint": closure.entrypoint,
        "entries": [
            {
                "path": row.path,
                "resolved_path": row.resolved_path,
                "size": row.size,
                "digest": row.digest,
            }
            for row in sorted(
                closure.entries,
                key=lambda item: (
                    item.path.encode("utf-8"),
                    item.resolved_path.encode("utf-8"),
                ),
            )
        ],
    }


def _read_regular_file_fd(fd: int) -> bytes:
    size = os.fstat(fd).st_size
    offset = 0
    chunks: list[bytes] = []
    while offset < size:
        block = os.pread(fd, min(1024 * 1024, size - offset), offset)
        if not block:
            raise _bootstrap_closure_error(
                "$.bootstrap.shim",
                "launch shim read ended before its recorded size",
            )
        chunks.append(block)
        offset += len(block)
    return b"".join(chunks)


def _validate_bootstrap_shim_imports(source: bytes) -> tuple[str, ...]:
    if _digest(source) != _REVIEWED_BOOTSTRAP_SHIM_DIGEST:
        raise _bootstrap_closure_error(
            "$.bootstrap.shim.identity",
            "launch shim differs from its independently reviewed source identity",
        )
    try:
        text = source.decode("utf-8", "strict")
        tree = ast.parse(text, filename="provider-launch-shim-v1.py")
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise _bootstrap_closure_error(
            "$.bootstrap.shim.imports",
            "launch shim is not canonical UTF-8 Python source",
        ) from exc

    # The source digest above is authority for the complete shim.  These rows
    # describe its closed ordinary import declarations; they are not a claim
    # that Python's dynamic call semantics can be exhaustively inferred here.
    parents = {
        child: parent
        for parent in ast.walk(tree)
        for child in ast.iter_child_nodes(parent)
    }
    imports = sorted(
        (
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
        ),
        key=lambda node: (node.lineno, node.col_offset),
    )
    module_imports: list[str] = []
    local_imports: list[str] = []
    for node in imports:
        parent = parents.get(node)
        if isinstance(parent, ast.Module):
            if isinstance(node, ast.ImportFrom):
                if (
                    node.module != "__future__"
                    or node.level != 0
                    or len(node.names) != 1
                    or node.names[0].name != "annotations"
                    or node.names[0].asname is not None
                ):
                    raise _bootstrap_closure_error(
                        "$.bootstrap.shim.imports",
                        "launch shim has an unreviewed module import",
                    )
                module_imports.append(
                    "module:from:__future__:annotations"
                )
                continue
            if (
                len(node.names) != 1
                or node.names[0].asname is not None
            ):
                raise _bootstrap_closure_error(
                    "$.bootstrap.shim.imports",
                    "launch shim has an unreviewed module import",
                )
            module_imports.append(
                f"module:import:{node.names[0].name}"
            )
            continue

        enclosing: ast.AST | None = parent
        while enclosing is not None and not isinstance(
            enclosing,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            enclosing = parents.get(enclosing)
        if (
            not isinstance(enclosing, ast.FunctionDef)
            or enclosing.name != "launch_provider_via_shim"
            or not isinstance(node, ast.Import)
            or len(node.names) != 1
            or node.names[0].asname is not None
            or node.names[0].name not in _BOOTSTRAP_ALLOWED_LOCAL_IMPORTS
        ):
            raise _bootstrap_closure_error(
                "$.bootstrap.shim.imports",
                "launch shim has a misplaced or unreviewed local import",
            )
        local_imports.append(
            "function:launch_provider_via_shim:import:"
            f"{node.names[0].name}"
        )

    if tuple(module_imports) != _BOOTSTRAP_MODULE_IMPORTS:
        raise _bootstrap_closure_error(
            "$.bootstrap.shim.imports",
            "launch shim module imports differ from the reviewed closure",
        )
    if tuple(local_imports) != _BOOTSTRAP_LOCAL_IMPORTS:
        raise _bootstrap_closure_error(
            "$.bootstrap.shim.imports",
            "launch shim local imports differ from the reviewed closure",
        )
    dynamic_names = {"__import__", "compile", "eval", "exec"}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in dynamic_names
        ) or (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and node.value in dynamic_names
        ):
            raise _bootstrap_closure_error(
                "$.bootstrap.shim.imports",
                "launch shim uses dynamic import or code construction",
            )
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if (
            isinstance(node.func, ast.Name)
            and node.func.id in {"__import__", "compile", "eval", "exec"}
        ) or (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == "import_module"
        ):
            raise _bootstrap_closure_error(
                "$.bootstrap.shim.imports",
                "launch shim uses dynamic import",
            )
    return (*module_imports, *local_imports)


def _bootstrap_closure_error(
    path: str,
    message: str,
) -> ProviderIsolationEnvironmentError:
    return ProviderIsolationEnvironmentError(
        (_issue(path, message, code=ENVIRONMENT_INVALID_CODE),)
    )


def expand_loader_search_path(
    value: str,
    *,
    containing_object: str,
    allowed_root: str = "/",
) -> tuple[str, ...]:
    """Expand one closed RPATH/RUNPATH value using only the ORIGIN token."""

    containing = _canonical_runtime_path(
        containing_object,
        issue_path="$.runtime_closure.loader_path",
        label="containing ELF path",
    )
    allowed = _canonical_runtime_path(
        allowed_root,
        issue_path="$.runtime_closure.loader_path",
        label="loader containment root",
        allow_root=True,
    )
    if not isinstance(value, str) or not value:
        raise _runtime_closure_error(
            containing,
            "loader search path must be non-empty text",
        )
    origin = posixpath.dirname(containing)
    expanded_rows: list[str] = []
    token_pattern = re.compile(
        r"\$(?:\{(?P<braced>[A-Za-z_][A-Za-z0-9_]*)\}|"
        r"(?P<plain>[A-Za-z_][A-Za-z0-9_]*))"
    )
    for raw in value.split(":"):
        if not raw:
            raise _runtime_closure_error(
                containing,
                "loader search path must not contain an empty entry",
            )
        for match in token_pattern.finditer(raw):
            token = match.group("braced") or match.group("plain")
            if token != "ORIGIN":
                raise _runtime_closure_error(
                    containing,
                    f"loader token {token!r} is not supported",
                )
        expanded = re.sub(r"\$(?:ORIGIN|\{ORIGIN\})", origin, raw)
        if "$" in expanded:
            raise _runtime_closure_error(
                containing,
                "loader search path contains an unknown token",
            )
        if not expanded.startswith("/") or expanded.startswith("//"):
            raise _runtime_closure_error(
                containing,
                "loader search path must resolve to an absolute path",
            )
        if "\x00" in expanded or unicodedata.normalize("NFC", expanded) != expanded:
            raise _runtime_closure_error(
                containing,
                "loader search path is not canonical Unicode text",
            )
        normalized = posixpath.normpath(expanded)
        if not _runtime_path_contains(allowed, normalized):
            raise _runtime_closure_error(
                containing,
                "loader search path escapes its permitted root",
            )
        if normalized in expanded_rows:
            raise _runtime_closure_error(
                containing,
                "loader search path contains a duplicate resolution",
            )
        expanded_rows.append(normalized)
    return tuple(expanded_rows)


def _runtime_entrypoint_path(executable: str, provider_prefix: str) -> str:
    if not isinstance(executable, str) or not executable:
        raise _runtime_closure_error(
            "$.runtime_closure.entrypoint",
            "provider executable must be non-empty text",
        )
    if _runtime_command_name(executable):
        return posixpath.join(provider_prefix, "bin", executable)
    canonical = _canonical_runtime_path(
        executable,
        issue_path="$.runtime_closure.entrypoint",
        label="provider executable",
    )
    if not _runtime_path_contains(provider_prefix, canonical):
        raise _runtime_closure_error(
            canonical,
            "provider executable must resolve below the declared provider prefix",
        )
    return canonical


def _runtime_command_name(value: str) -> bool:
    return (
        bool(value)
        and "/" not in value
        and value not in {".", ".."}
        and "\x00" not in value
        and unicodedata.normalize("NFC", value) == value
    )


def _require_runtime_rootfs(rootfs: str | os.PathLike[str]) -> Path:
    try:
        raw = os.fspath(rootfs)
    except TypeError as exc:
        raise _runtime_closure_error(
            "$.runtime_closure.rootfs",
            "runtime rootfs must be an absolute text path",
        ) from exc
    if (
        not isinstance(raw, str)
        or not raw.startswith("/")
        or raw.startswith("//")
        or "\x00" in raw
        or unicodedata.normalize("NFC", raw) != raw
        or posixpath.normpath(raw) != raw
    ):
        raise _runtime_closure_error(
            "$.runtime_closure.rootfs",
            "runtime rootfs must be a canonical absolute text path",
        )
    return Path(raw)


def _retain_runtime_ld_so_preload_absence(
    capture: _PinnedRuntimeClosureCapture,
) -> None:
    root_fd = capture.source.root_fd
    etc_fd = -1
    try:
        etc_stat = _lstat_at(root_fd, "etc")
    except FileNotFoundError:
        capture.negative_names.append(
            _PinnedRuntimeNegativeName(
                parent_fd=root_fd,
                parent_stat=os.fstat(root_fd),
                name="etc",
                issue_path="/etc/ld.so.preload",
            )
        )
        return
    except OSError as exc:
        raise _runtime_closure_error(
            "/etc",
            "loader startup configuration could not be inspected",
        ) from exc
    if not stat.S_ISDIR(etc_stat.st_mode):
        raise _runtime_closure_error(
            "/etc",
            "loader startup configuration directory must be a real directory",
        )
    try:
        etc_fd = _open_directory_at(root_fd, "etc")
        opened_etc = os.fstat(etc_fd)
        _require_same_source_identity(
            etc_stat,
            opened_etc,
            issue_path="$.runtime_closure.preload",
        )
        try:
            _lstat_at(etc_fd, "ld.so.preload")
        except FileNotFoundError:
            capture.negative_names.append(
                _PinnedRuntimeNegativeName(
                    parent_fd=etc_fd,
                    parent_stat=opened_etc,
                    name="ld.so.preload",
                    issue_path="/etc/ld.so.preload",
                    authority_edges=(
                        _PinnedRuntimeEdge(
                            parent_fd=root_fd,
                            child_fd=etc_fd,
                            name="etc",
                            opened_stat=opened_etc,
                            issue_path="$.runtime_closure.preload",
                        ),
                    ),
                    _owned_fds=[etc_fd],
                )
            )
            etc_fd = -1
            return
        except OSError as exc:
            raise _runtime_closure_error(
                "/etc/ld.so.preload",
                "loader preload configuration could not be inspected",
            ) from exc
        raise _runtime_closure_error(
            "/etc/ld.so.preload",
            "/etc/ld.so.preload is forbidden in a sealed provider rootfs",
        )
    finally:
        if etc_fd >= 0:
            os.close(etc_fd)


def _canonical_runtime_path(
    value: str,
    *,
    issue_path: str,
    label: str,
    allow_root: bool = False,
) -> str:
    if (
        not isinstance(value, str)
        or not value.startswith("/")
        or value.startswith("//")
        or "\x00" in value
        or unicodedata.normalize("NFC", value) != value
        or posixpath.normpath(value) != value
        or (value == "/" and not allow_root)
    ):
        raise _runtime_closure_error(
            issue_path,
            f"{label} must be a canonical absolute provider-visible path",
        )
    return value


def _runtime_path_contains(root: str, candidate: str) -> bool:
    if root == "/":
        return candidate.startswith("/")
    return candidate == root or candidate.startswith(f"{root.rstrip('/')}/")


def _pin_rootfs_runtime_file(
    root_fd: int,
    provider_path: str,
    *,
    retain_missing: bool = False,
) -> _PinnedRuntimeFile:
    requested = _canonical_runtime_path(
        provider_path,
        issue_path="$.runtime_closure.path",
        label="runtime closure path",
    )
    pending = requested.lstrip("/").split("/")
    resolved: list[str] = []
    directory_stack = [root_fd]
    owned_fds: list[int] = []
    edges: list[_PinnedRuntimeEdge] = []
    expansions = 0
    try:
        while pending:
            component = pending.pop(0)
            if component in {"", "."}:
                continue
            if component == "..":
                if not resolved:
                    raise _RootfsResolutionFailure(
                        f"{requested!r} escapes the sealed rootfs"
                    )
                resolved.pop()
                directory_stack.pop()
                continue
            parent_fd = directory_stack[-1]
            issue_path = (
                "$.runtime_closure.paths["
                f"{requested!r}].components[{len(edges)}]"
            )
            try:
                before = _lstat_at(parent_fd, component)
            except FileNotFoundError as exc:
                observation = None
                if retain_missing:
                    observation = _PinnedRuntimeNegativeName(
                        parent_fd=parent_fd,
                        parent_stat=os.fstat(parent_fd),
                        name=component,
                        issue_path=issue_path,
                        authority_edges=tuple(edges),
                        _owned_fds=owned_fds,
                    )
                    owned_fds = []
                raise _RootfsResolutionFailure(
                    f"{requested!r} is not packaged in the sealed rootfs",
                    missing=True,
                    observation=observation,
                ) from exc
            except NotADirectoryError as exc:
                raise _RootfsResolutionFailure(
                    f"{requested!r} is not packaged in the sealed rootfs",
                    missing=True,
                ) from exc
            except OSError as exc:
                raise _RootfsResolutionFailure(
                    f"{requested!r} could not be inspected"
                ) from exc

            if stat.S_ISLNK(before.st_mode):
                expansions += 1
                if expansions > _MAX_RUNTIME_SYMLINKS:
                    raise _RootfsResolutionFailure(
                        f"{requested!r} has a cyclic or overlong symlink chain"
                    )
                try:
                    symlink_fd = _open_runtime_symlink_at(
                        parent_fd,
                        component,
                    )
                    owned_fds.append(symlink_fd)
                    opened = os.fstat(symlink_fd)
                    _require_same_source_identity(
                        before,
                        opened,
                        issue_path=issue_path,
                    )
                    target = os.readlink("", dir_fd=symlink_fd)
                except ProviderIsolationEnvironmentError:
                    raise
                except OSError as exc:
                    raise _RootfsResolutionFailure(
                        f"{requested!r} symlink could not be read"
                    ) from exc
                if (
                    not isinstance(target, str)
                    or not target
                    or "\x00" in target
                    or unicodedata.normalize("NFC", target) != target
                ):
                    raise _RootfsResolutionFailure(
                        f"{requested!r} has an invalid symlink target"
                    )
                edges.append(
                    _PinnedRuntimeEdge(
                        parent_fd=parent_fd,
                        child_fd=symlink_fd,
                        name=component,
                        opened_stat=opened,
                        issue_path=issue_path,
                        link_text=target,
                    )
                )
                target_parts = target.split("/")
                if target.startswith("/"):
                    resolved.clear()
                    directory_stack = [root_fd]
                    target_parts = target.lstrip("/").split("/")
                pending = target_parts + pending
                continue

            if pending:
                if not stat.S_ISDIR(before.st_mode):
                    observation = None
                    if retain_missing:
                        blocker_fd = _open_runtime_node_at(
                            parent_fd,
                            component,
                        )
                        owned_fds.append(blocker_fd)
                        opened = os.fstat(blocker_fd)
                        _require_same_source_identity(
                            before,
                            opened,
                            issue_path=issue_path,
                        )
                        edges.append(
                            _PinnedRuntimeEdge(
                                parent_fd=parent_fd,
                                child_fd=blocker_fd,
                                name=component,
                                opened_stat=opened,
                                issue_path=issue_path,
                            )
                        )
                        observation = _PinnedRuntimeNegativeName(
                            parent_fd=parent_fd,
                            parent_stat=os.fstat(parent_fd),
                            name=None,
                            issue_path=issue_path,
                            authority_edges=tuple(edges),
                            _owned_fds=owned_fds,
                        )
                        owned_fds = []
                    raise _RootfsResolutionFailure(
                        f"{requested!r} crosses a non-directory rootfs member",
                        missing=True,
                        observation=observation,
                    )
                try:
                    child_fd = _open_directory_at(parent_fd, component)
                    owned_fds.append(child_fd)
                    opened = os.fstat(child_fd)
                    _require_same_source_identity(
                        before,
                        opened,
                        issue_path=issue_path,
                    )
                except ProviderIsolationEnvironmentError:
                    raise
                except (FileNotFoundError, NotADirectoryError) as exc:
                    raise _RootfsResolutionFailure(
                        f"{requested!r} changed during resolution"
                    ) from exc
                except OSError as exc:
                    raise _RootfsResolutionFailure(
                        f"{requested!r} could not be opened"
                    ) from exc
                edges.append(
                    _PinnedRuntimeEdge(
                        parent_fd=parent_fd,
                        child_fd=child_fd,
                        name=component,
                        opened_stat=opened,
                        issue_path=issue_path,
                    )
                )
                resolved.append(component)
                directory_stack.append(child_fd)
                continue

            if not stat.S_ISREG(before.st_mode):
                raise _RootfsResolutionFailure(
                    f"{requested!r} does not resolve to a regular file"
                )
            try:
                file_fd = _open_regular_at(parent_fd, component)
                owned_fds.append(file_fd)
                opened = os.fstat(file_fd)
                _require_same_source_identity(
                    before,
                    opened,
                    issue_path=issue_path,
                )
            except ProviderIsolationEnvironmentError:
                raise
            except OSError as exc:
                raise _RootfsResolutionFailure(
                    f"{requested!r} could not be opened"
                ) from exc
            edges.append(
                _PinnedRuntimeEdge(
                    parent_fd=parent_fd,
                    child_fd=file_fd,
                    name=component,
                    opened_stat=opened,
                    issue_path=issue_path,
                )
            )
            resolved.append(component)
            return _PinnedRuntimeFile(
                requested_path=requested,
                resolved_path="/" + "/".join(resolved),
                file_fd=file_fd,
                stat=opened,
                _owned_fds=owned_fds,
                _edges=tuple(edges),
            )
        raise _RootfsResolutionFailure(
            f"{requested!r} does not resolve to a regular file"
        )
    except BaseException:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _open_runtime_symlink_at(directory_fd: int, name: str) -> int:
    return _open_runtime_node_at(directory_fd, name)


def _open_runtime_node_at(directory_fd: int, name: str) -> int:
    flags = os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC
    return os.open(name, flags, dir_fd=directory_fd)


def _read_runtime_prefix_fd(fd: int, size: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    return os.read(fd, size)


def _parse_shebang(prefix: bytes, provider_path: str) -> tuple[str, tuple[str, ...]]:
    first_line = prefix[2:].split(b"\n", 1)[0].rstrip(b"\r")
    try:
        decoded = first_line.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _runtime_closure_error(
            provider_path,
            "script shebang is not strict UTF-8",
        ) from exc
    if unicodedata.normalize("NFC", decoded) != decoded:
        raise _runtime_closure_error(
            provider_path,
            "script shebang is not NFC",
        )
    parts = decoded.strip().split()
    if not parts:
        raise _runtime_closure_error(
            provider_path,
            "script shebang is empty",
        )
    interpreter = _canonical_runtime_path(
        parts[0],
        issue_path="$.runtime_closure.shebang",
        label="script interpreter",
    )
    return interpreter, tuple(parts[1:])


def _expand_elf_search_directories(
    values: Sequence[str],
    *,
    containing_object: str,
) -> tuple[str, ...]:
    directories: list[str] = []
    for value in values:
        expanded = expand_loader_search_path(
            value,
            containing_object=containing_object,
            allowed_root="/",
        )
        for directory in expanded:
            _reject_runtime_writable_overlay_path(
                directory,
                issue_path=containing_object,
            )
            directories.append(directory)
    return tuple(directories)


def _reject_runtime_writable_overlay_path(
    provider_path: str,
    *,
    issue_path: str,
) -> None:
    for overlay_root in _WRITABLE_RUNTIME_OVERLAY_ROOTS:
        if _runtime_path_contains(overlay_root, provider_path):
            raise _runtime_closure_error(
                issue_path,
                f"runtime path {provider_path!r} is below a writable overlay",
            )


def _parse_glibc_cache_fd(fd: int) -> tuple[_GlibcCacheEntry, ...]:
    """Parse the bounded glibc 1.1 cache profile without executing helpers."""

    cache_path = Path(_GLIBC_CACHE_PATH)
    header_size = struct.calcsize(_GLIBC_CACHE_HEADER_FORMAT)
    entry_size = struct.calcsize(_GLIBC_CACHE_ENTRY_FORMAT)
    extension_header_size = struct.calcsize(
        _GLIBC_CACHE_EXTENSION_HEADER_FORMAT
    )
    extension_section_size = struct.calcsize(
        _GLIBC_CACHE_EXTENSION_SECTION_FORMAT
    )
    if header_size != 48 or entry_size != 24:
        raise AssertionError("glibc cache layout constants are inconsistent")
    file_size = os.fstat(fd).st_size
    if file_size < header_size:
        raise _runtime_closure_error(
            _GLIBC_CACHE_PATH,
            "glibc cache header is truncated",
        )
    with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as image:
        (
            magic,
            version,
            entry_count,
            string_size,
            endian_flag,
            padding,
            extension_offset,
            reserved_0,
            reserved_1,
            reserved_2,
        ) = struct.unpack_from(_GLIBC_CACHE_HEADER_FORMAT, image, 0)
        if magic != _GLIBC_CACHE_MAGIC:
            raise _runtime_closure_error(
                _GLIBC_CACHE_PATH,
                "glibc cache magic is invalid",
            )
        if version != _GLIBC_CACHE_VERSION:
            raise _runtime_closure_error(
                _GLIBC_CACHE_PATH,
                "glibc cache version is unsupported",
            )
        if endian_flag != _GLIBC_CACHE_LITTLE_ENDIAN:
            raise _runtime_closure_error(
                _GLIBC_CACHE_PATH,
                "glibc cache endian flag is unsupported",
            )
        if padding != b"\0\0\0" or any(
            (reserved_0, reserved_1, reserved_2)
        ):
            raise _runtime_closure_error(
                _GLIBC_CACHE_PATH,
                "glibc cache reserved header fields are unsupported",
            )

        entries_start = header_size
        entries_end = entries_start + entry_count * entry_size
        _require_glibc_cache_region(
            image,
            entries_start,
            entry_count * entry_size,
            "entry table",
        )
        strings_start = entries_end
        strings_end = strings_start + string_size
        _require_glibc_cache_region(
            image,
            strings_start,
            string_size,
            "string table",
        )

        if extension_offset == 0:
            if strings_end != file_size:
                raise _runtime_closure_error(
                    _GLIBC_CACHE_PATH,
                    "glibc cache has unbounded trailing data",
                )
        else:
            if (
                extension_offset < strings_end
                or extension_offset % 4
                or extension_offset - strings_end >= 4
                or any(image[strings_end:extension_offset])
            ):
                raise _runtime_closure_error(
                    _GLIBC_CACHE_PATH,
                    "glibc cache extension offset is invalid",
                )
            _require_glibc_cache_region(
                image,
                extension_offset,
                extension_header_size,
                "extension header",
            )
            extension_magic, extension_count = struct.unpack_from(
                _GLIBC_CACHE_EXTENSION_HEADER_FORMAT,
                image,
                extension_offset,
            )
            if extension_magic != _GLIBC_CACHE_EXTENSION_MAGIC:
                raise _runtime_closure_error(
                    _GLIBC_CACHE_PATH,
                    "glibc cache extension magic is invalid",
                )
            sections_start = extension_offset + extension_header_size
            sections_size = extension_count * extension_section_size
            _require_glibc_cache_region(
                image,
                sections_start,
                sections_size,
                "extension section table",
            )
            for index in range(extension_count):
                section_offset = (
                    sections_start + index * extension_section_size
                )
                _, _, data_offset, data_size = struct.unpack_from(
                    _GLIBC_CACHE_EXTENSION_SECTION_FORMAT,
                    image,
                    section_offset,
                )
                _require_glibc_cache_region(
                    image,
                    data_offset,
                    data_size,
                    f"extension section {index}",
                )

        entries: list[_GlibcCacheEntry] = []
        for index in range(entry_count):
            offset = entries_start + index * entry_size
            flags, key_offset, value_offset, osversion, hwcap = (
                struct.unpack_from(_GLIBC_CACHE_ENTRY_FORMAT, image, offset)
            )
            key = _glibc_cache_string(
                image,
                absolute_offset=int(key_offset),
                strings_start=strings_start,
                strings_end=strings_end,
                cache_path=cache_path,
            )
            _require_glibc_cache_comparator_domain(key)
            entries.append(
                _GlibcCacheEntry(
                    flags=int(flags),
                    key=key,
                    value=_glibc_cache_string(
                        image,
                        absolute_offset=int(value_offset),
                        strings_start=strings_start,
                        strings_end=strings_end,
                        cache_path=cache_path,
                    ),
                    osversion=int(osversion),
                    hwcap=int(hwcap),
                )
            )
        for previous, current in zip(entries, entries[1:]):
            if _glibc_cache_libcmp(previous.key, current.key) < 0:
                raise _runtime_closure_error(
                    _GLIBC_CACHE_PATH,
                    "glibc cache entries violate loader sort order",
                )
        return tuple(entries)


def _require_glibc_cache_region(
    image: mmap.mmap,
    offset: int,
    size: int,
    label: str,
) -> None:
    if (
        offset < 0
        or size < 0
        or offset > len(image)
        or size > len(image) - offset
    ):
        raise _runtime_closure_error(
            _GLIBC_CACHE_PATH,
            f"glibc cache {label} is out of bounds",
        )


def _glibc_cache_string(
    image: mmap.mmap,
    *,
    absolute_offset: int,
    strings_start: int,
    strings_end: int,
    cache_path: Path,
) -> str:
    if absolute_offset < strings_start or absolute_offset >= strings_end:
        raise _runtime_closure_error(
            _GLIBC_CACHE_PATH,
            "glibc cache string offset is out of bounds",
        )
    end = image.find(b"\0", absolute_offset, strings_end)
    if end < 0:
        raise _runtime_closure_error(
            _GLIBC_CACHE_PATH,
            "glibc cache string is not terminated",
        )
    return _decode_elf_text(
        bytes(image[absolute_offset:end]),
        cache_path,
        "glibc cache string",
    )


def _require_glibc_cache_comparator_domain(value: str) -> None:
    encoded = value.encode("utf-8")
    index = 0
    while index < len(encoded):
        if not 48 <= encoded[index] <= 57:
            index += 1
            continue
        numeric_value = 0
        while index < len(encoded) and 48 <= encoded[index] <= 57:
            numeric_value = numeric_value * 10 + encoded[index] - 48
            if numeric_value > _GLIBC_CACHE_COMPARATOR_MAX:
                raise _runtime_closure_error(
                    _GLIBC_CACHE_PATH,
                    "glibc cache numeric run exceeds the loader comparator "
                    "domain",
                )
            index += 1


def _glibc_cache_libcmp(left: str, right: str) -> int:
    """Match glibc's numeric-run cache comparator on admitted strings."""

    _require_glibc_cache_comparator_domain(left)
    _require_glibc_cache_comparator_domain(right)
    left_bytes = left.encode("utf-8")
    right_bytes = right.encode("utf-8")
    left_index = 0
    right_index = 0

    def raw_char(value: bytes, index: int) -> int:
        return value[index] if index < len(value) else 0

    def signed_char(value: bytes, index: int) -> int:
        current = raw_char(value, index)
        return current if current < 128 else current - 256

    while raw_char(left_bytes, left_index) != 0:
        left_char = raw_char(left_bytes, left_index)
        right_char = raw_char(right_bytes, right_index)
        if 48 <= left_char <= 57:
            if 48 <= right_char <= 57:
                left_value = left_char - 48
                right_value = right_char - 48
                left_index += 1
                right_index += 1
                while 48 <= raw_char(left_bytes, left_index) <= 57:
                    left_value = (
                        left_value * 10
                        + raw_char(left_bytes, left_index)
                        - 48
                    )
                    left_index += 1
                while 48 <= raw_char(right_bytes, right_index) <= 57:
                    right_value = (
                        right_value * 10
                        + raw_char(right_bytes, right_index)
                        - 48
                    )
                    right_index += 1
                if left_value != right_value:
                    return left_value - right_value
            else:
                return 1
        elif 48 <= right_char <= 57:
            return -1
        elif left_char != right_char:
            return (
                signed_char(left_bytes, left_index)
                - signed_char(right_bytes, right_index)
            )
        else:
            left_index += 1
            right_index += 1
    return -signed_char(right_bytes, right_index)


def _select_glibc_cache_dependency(
    entries: Sequence[_GlibcCacheEntry],
    *,
    needed: str,
) -> str | None:
    if not entries:
        return None
    _require_glibc_cache_comparator_domain(needed)
    for entry in entries:
        if _glibc_cache_libcmp(needed, entry.key) != 0:
            continue
        if (
            entry.flags != _GLIBC_CACHE_X86_64_FLAGS
            or entry.hwcap != 0
        ):
            raise _runtime_closure_error(
                _GLIBC_CACHE_PATH,
                f"unsupported-priority glibc cache match for {needed!r}",
            )
        selected = _canonical_runtime_path(
            entry.value,
            issue_path=_GLIBC_CACHE_PATH,
            label="glibc cache dependency",
        )
        _reject_runtime_writable_overlay_path(
            selected,
            issue_path=_GLIBC_CACHE_PATH,
        )
        return selected
    return None


def _resolve_elf_dependency(
    capture: _PinnedRuntimeClosureCapture,
    needed: str,
    *,
    containing_object: str,
    search_directories: Sequence[str],
    cache_resolver: Callable[[str], str | None],
) -> str:
    if (
        not needed
        or "\x00" in needed
        or unicodedata.normalize("NFC", needed) != needed
    ):
        raise _runtime_closure_error(
            containing_object,
            "ELF dependency name is invalid",
        )
    if "/" in needed:
        if not needed.startswith("/"):
            raise _runtime_closure_error(
                containing_object,
                f"ELF dependency {needed!r} uses a relative path",
            )
        candidate = _canonical_runtime_path(
            needed,
            issue_path="$.runtime_closure.needed",
            label="ELF dependency",
        )
        _reject_runtime_writable_overlay_path(
            candidate,
            issue_path=containing_object,
        )
        capture.require_file(candidate, require_executable=False)
        return candidate

    seen_directories: set[str] = set()
    for directory in search_directories:
        if directory in seen_directories:
            continue
        seen_directories.add(directory)
        candidate = posixpath.join(directory, needed)
        if capture.probe_file(candidate) is not None:
            if not _runtime_path_contains("/", candidate):
                raise AssertionError(
                    "resolved library path is not provider-visible"
                )
            return candidate
    cached = cache_resolver(needed)
    if cached is not None:
        pinned_cached = capture.require_file(
            cached,
            require_executable=False,
        )
        _reject_runtime_writable_overlay_path(
            pinned_cached.resolved_path,
            issue_path=_GLIBC_CACHE_PATH,
        )
        return cached
    for directory in _DEFAULT_LOADER_DIRECTORIES:
        if directory in seen_directories:
            continue
        seen_directories.add(directory)
        candidate = posixpath.join(directory, needed)
        if capture.probe_file(candidate) is not None:
            if not _runtime_path_contains("/", candidate):
                raise AssertionError(
                    "resolved library path is not provider-visible"
                )
            return candidate
    raise _runtime_closure_error(
        containing_object,
        f"ELF dependency {needed!r} is not packaged in the sealed rootfs",
    )


def _parse_elf(
    path: Path | int,
    *,
    display_path: str | os.PathLike[str] | None = None,
) -> ParsedElf:
    """Parse startup-relevant ELF program/dynamic tables with checked bounds."""

    close_fd = False
    if isinstance(path, int):
        fd = path
        label = Path(
            os.fspath(display_path)
            if display_path is not None
            else f"<fd:{fd}>"
        )
    else:
        label = path
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            fd = _open_noatime(path, flags)
        except OSError as exc:
            raise _runtime_closure_error(
                str(path),
                "ELF could not be opened",
            ) from exc
        close_fd = True
    path = label
    try:
        file_size = os.fstat(fd).st_size
        if file_size < 16:
            raise _runtime_closure_error(str(path), "ELF header is truncated")
        with mmap.mmap(fd, 0, access=mmap.ACCESS_READ) as image:
            if image[:4] != _ELF_MAGIC:
                raise _runtime_closure_error(str(path), "ELF magic is invalid")
            elf_class = image[4]
            data_encoding = image[5]
            ident_version = image[6]
            if (
                elf_class != _ELF_CLASS_64
                or data_encoding != _ELF_DATA_LITTLE_ENDIAN
            ):
                raise _runtime_closure_error(
                    str(path),
                    "ELF must use the reviewed 64-bit little-endian profile",
                )
            if ident_version != _ELF_VERSION_CURRENT:
                raise _runtime_closure_error(
                    str(path),
                    "ELF ident version is invalid",
                )
            header_format = "<16sHHIQQQIHHHHHH"
            program_format = "<IIQQQQQQ"
            dynamic_format = "<qQ"
            header_size = struct.calcsize(header_format)
            program_size = struct.calcsize(program_format)
            dynamic_size = struct.calcsize(dynamic_format)
            _require_elf_region(image, 0, header_size, "ELF header", path)
            header = struct.unpack_from(header_format, image, 0)
            elf_type = int(header[1])
            machine = int(header[2])
            header_version = int(header[3])
            if header_version != _ELF_VERSION_CURRENT:
                raise _runtime_closure_error(
                    str(path),
                    "ELF header version is invalid",
                )
            if elf_type not in {_ELF_TYPE_EXEC, _ELF_TYPE_DYN}:
                raise _runtime_closure_error(
                    str(path),
                    "ELF type must be ET_EXEC or ET_DYN",
                )
            if machine != _ELF_MACHINE_X86_64:
                raise _runtime_closure_error(
                    str(path),
                    "ELF machine must be EM_X86_64",
                )
            program_offset = int(header[5])
            declared_header_size = int(header[8])
            program_entry_size = int(header[9])
            program_count = int(header[10])
            if (
                declared_header_size < header_size
                or program_entry_size < program_size
                or program_count == 0xFFFF
            ):
                raise _runtime_closure_error(
                    str(path),
                    "ELF program-header layout is unsupported",
                )
            _require_elf_region(
                image,
                program_offset,
                program_entry_size * program_count,
                "ELF program-header table",
                path,
            )

            loads: list[tuple[int, int, int, int]] = []
            interpreter_regions: list[tuple[int, int]] = []
            dynamic_regions: list[tuple[int, int]] = []
            for index in range(program_count):
                offset = program_offset + index * program_entry_size
                row = struct.unpack_from(program_format, image, offset)
                kind, _, file_offset, virtual_address, _, file_bytes, _, _ = row
                file_offset = int(file_offset)
                virtual_address = int(virtual_address)
                file_bytes = int(file_bytes)
                if kind in {1, 2, 3}:
                    _require_elf_region(
                        image,
                        file_offset,
                        file_bytes,
                        f"ELF program segment {index}",
                        path,
                    )
                if kind == 1:  # PT_LOAD
                    loads.append(
                        (file_offset, virtual_address, file_bytes, index)
                    )
                elif kind == 2:  # PT_DYNAMIC
                    dynamic_regions.append((file_offset, file_bytes))
                elif kind == 3:  # PT_INTERP
                    interpreter_regions.append((file_offset, file_bytes))
            if len(interpreter_regions) > 1 or len(dynamic_regions) > 1:
                raise _runtime_closure_error(
                    str(path),
                    "ELF has ambiguous interpreter or dynamic tables",
                )

            interpreter: str | None = None
            if interpreter_regions:
                offset, length = interpreter_regions[0]
                payload = bytes(image[offset : offset + length])
                if (
                    len(payload) < 2
                    or payload[-1:] != b"\0"
                    or b"\0" in payload[:-1]
                ):
                    raise _runtime_closure_error(
                        str(path),
                        "ELF PT_INTERP is not a single terminated path",
                    )
                interpreter = _decode_elf_text(
                    payload[:-1],
                    path,
                    "ELF interpreter",
                )

            if not dynamic_regions:
                return ParsedElf(
                    elf_class=elf_class,
                    data_encoding=data_encoding,
                    ident_version=ident_version,
                    elf_type=elf_type,
                    machine=machine,
                    header_version=header_version,
                    interpreter=interpreter,
                    needed=(),
                    rpath=(),
                    runpath=(),
                )
            dynamic_offset, dynamic_bytes = dynamic_regions[0]
            if dynamic_bytes % dynamic_size:
                raise _runtime_closure_error(
                    str(path),
                    "ELF dynamic table has a truncated entry",
                )
            dynamic_rows: list[tuple[int, int]] = []
            terminated = False
            for offset in range(
                dynamic_offset,
                dynamic_offset + dynamic_bytes,
                dynamic_size,
            ):
                tag, value = struct.unpack_from(dynamic_format, image, offset)
                if tag == 0:
                    terminated = True
                    break
                dynamic_rows.append((int(tag), int(value)))
            if not terminated:
                raise _runtime_closure_error(
                    str(path),
                    "ELF dynamic table is not terminated",
                )
            string_offsets = [
                value for tag, value in dynamic_rows if tag == 5
            ]
            string_sizes = [
                value for tag, value in dynamic_rows if tag == 10
            ]
            string_tags = [
                (tag, value)
                for tag, value in dynamic_rows
                if tag in {1, 15, 29}
            ]
            if not string_tags:
                return ParsedElf(
                    elf_class=elf_class,
                    data_encoding=data_encoding,
                    ident_version=ident_version,
                    elf_type=elf_type,
                    machine=machine,
                    header_version=header_version,
                    interpreter=interpreter,
                    needed=(),
                    rpath=(),
                    runpath=(),
                )
            if len(string_offsets) != 1 or len(string_sizes) != 1:
                raise _runtime_closure_error(
                    str(path),
                    "ELF dynamic string table is missing or ambiguous",
                )
            string_size = string_sizes[0]
            string_offset = _elf_virtual_file_offset(
                loads,
                string_offsets[0],
                string_size,
                path,
            )
            _require_elf_region(
                image,
                string_offset,
                string_size,
                "ELF dynamic string table",
                path,
            )

            needed: list[str] = []
            rpath_values: list[str] = []
            runpath_values: list[str] = []
            for tag, value in string_tags:
                text = _elf_string(
                    image,
                    table_offset=string_offset,
                    table_size=string_size,
                    string_offset=value,
                    path=path,
                )
                if tag == 1:
                    needed.append(text)
                elif tag == 15:
                    rpath_values.append(text)
                else:
                    runpath_values.append(text)
            if len(rpath_values) > 1 or len(runpath_values) > 1:
                raise _runtime_closure_error(
                    str(path),
                    "ELF has ambiguous RPATH or RUNPATH entries",
                )
            return ParsedElf(
                elf_class=elf_class,
                data_encoding=data_encoding,
                ident_version=ident_version,
                elf_type=elf_type,
                machine=machine,
                header_version=header_version,
                interpreter=interpreter,
                needed=tuple(needed),
                rpath=(
                    tuple(rpath_values[0].split(":"))
                    if rpath_values
                    else ()
                ),
                runpath=(
                    tuple(runpath_values[0].split(":"))
                    if runpath_values
                    else ()
                ),
            )
    finally:
        if close_fd:
            os.close(fd)


def _parse_elf_fd(fd: int, provider_path: str) -> ParsedElf:
    return _parse_elf(fd, display_path=provider_path)


def _require_elf_region(
    image: mmap.mmap,
    offset: int,
    size: int,
    label: str,
    path: Path,
) -> None:
    if offset < 0 or size < 0 or offset > len(image) or size > len(image) - offset:
        raise _runtime_closure_error(str(path), f"{label} is out of bounds")


def _elf_virtual_file_offset(
    loads: Sequence[tuple[int, int, int, int]],
    address: int,
    size: int,
    path: Path,
) -> int:
    candidates = [
        file_offset + address - virtual_address
        for file_offset, virtual_address, file_size, _ in loads
        if address >= virtual_address
        and address - virtual_address <= file_size
        and size <= file_size - (address - virtual_address)
    ]
    if len(candidates) != 1:
        raise _runtime_closure_error(
            str(path),
            "ELF dynamic string table address is missing or ambiguous",
        )
    return candidates[0]


def _elf_string(
    image: mmap.mmap,
    *,
    table_offset: int,
    table_size: int,
    string_offset: int,
    path: Path,
) -> str:
    if string_offset < 0 or string_offset >= table_size:
        raise _runtime_closure_error(
            str(path),
            "ELF dynamic string offset is out of bounds",
        )
    start = table_offset + string_offset
    end = image.find(b"\0", start, table_offset + table_size)
    if end < 0:
        raise _runtime_closure_error(
            str(path),
            "ELF dynamic string is not terminated",
        )
    return _decode_elf_text(bytes(image[start:end]), path, "ELF dynamic string")


def _decode_elf_text(value: bytes, path: Path, label: str) -> str:
    try:
        decoded = value.decode("utf-8", "strict")
    except UnicodeDecodeError as exc:
        raise _runtime_closure_error(
            str(path),
            f"{label} is not strict UTF-8",
        ) from exc
    if (
        not decoded
        or "\x00" in decoded
        or unicodedata.normalize("NFC", decoded) != decoded
    ):
        raise _runtime_closure_error(
            str(path),
            f"{label} is empty or non-canonical",
        )
    return decoded


def _runtime_closure_error(
    path: str,
    message: str,
) -> ProviderIsolationEnvironmentError:
    return ProviderIsolationEnvironmentError(
        (_issue(path, message, code=ENVIRONMENT_INVALID_CODE),)
    )


def validate_provider_environment_manifest(
    document: object,
    *,
    expected_digest: str | None = None,
) -> tuple[ProviderIsolationIssue, ...]:
    """Return every deterministic structural, semantic, and identity issue."""

    schema = load_provider_isolation_schema(ENVIRONMENT_SCHEMA_RESOURCE)
    validator = Draft202012Validator(schema)
    issues = list(
        isolation_schema_validation_issues(
            validator.iter_errors(document),
            error_code=ENVIRONMENT_INVALID_CODE,
        )
    )
    issues.extend(_float_issues(document, "$"))
    if isinstance(document, Mapping):
        issues.extend(_closed_field_issues(document))
        issues.extend(_semantic_manifest_issues(document))

    invalid = _deduplicate_issues(issues)
    if invalid:
        return invalid

    if expected_digest is not None:
        if (
            not isinstance(expected_digest, str)
            or _DIGEST_PATTERN.fullmatch(expected_digest) is None
        ):
            return (
                _issue(
                    "$.digest",
                    "expected environment identity must be canonical sha256",
                ),
            )
        actual = _digest(canonical_isolation_json_bytes(deepcopy(document)))
        if actual != expected_digest:
            return (
                _issue(
                    "$.digest",
                    "provider environment identity does not match expected digest",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
    return ()


def load_provider_environment_manifest(
    document: Mapping[str, Any],
    *,
    expected_digest: str | None = None,
) -> ProviderEnvironmentManifest:
    """Validate and load one canonical provider-environment manifest."""

    issues = validate_provider_environment_manifest(
        document,
        expected_digest=expected_digest,
    )
    if issues:
        raise ProviderIsolationEnvironmentError(issues)

    canonical_json = canonical_isolation_json_bytes(document)
    normalized = json.loads(canonical_json)
    entries = tuple(
        ProviderEnvironmentManifestEntry(
            path=row["path"],
            kind=row["kind"],
            mode=row["mode"],
            uid=row["uid"],
            gid=row["gid"],
            atime_ns=row["atime_ns"],
            mtime_ns=row["mtime_ns"],
            size=row.get("size"),
            digest=row.get("digest"),
            link_text=row.get("link_text"),
        )
        for row in normalized["entries"]
    )
    return ProviderEnvironmentManifest(
        schema_version=normalized["schema_version"],
        provider_prefix=normalized["provider_prefix"],
        entries=entries,
        canonical_json=canonical_json,
        digest=_digest(canonical_json),
    )


def build_provider_environment_manifest(
    root: str | os.PathLike[str],
    provider_prefix: str,
) -> ProviderEnvironmentManifest:
    """Prospectively assemble one closed manifest without mutating the source."""

    return _build_provider_environment_manifest(
        root,
        provider_prefix,
        inject_launch_shim=True,
        finalized_snapshot=False,
    )


def _build_provider_environment_manifest(
    root: str | os.PathLike[str],
    provider_prefix: str,
    *,
    inject_launch_shim: bool,
    finalized_snapshot: bool,
) -> ProviderEnvironmentManifest:
    prefix_issues = _absolute_prefix_issues(provider_prefix)
    if prefix_issues:
        raise ProviderIsolationEnvironmentError(prefix_issues)

    source_root = Path(root)
    if not source_root.is_absolute():
        raise ProviderIsolationEnvironmentError(
            (_issue("$.root", "environment source root must be absolute"),)
        )
    root_before = _lstat_root(source_root)
    _require_source_entry(
        root_before,
        path=".",
        issue_path="$.entries[0]",
        required_kind="directory",
    )

    root_fd = _open_directory(source_root)
    try:
        root_opened = os.fstat(root_fd)
        _require_same_source_identity(
            root_before,
            root_opened,
            issue_path="$.entries[0]",
        )
        manifest = _build_provider_environment_manifest_from_fd(
            root_fd,
            provider_prefix,
            inject_launch_shim=inject_launch_shim,
            finalized_snapshot=finalized_snapshot,
        )

        root_after_fd = os.fstat(root_fd)
        root_after_path = _lstat_root(source_root)
        if root_after_path.st_uid != root_before.st_uid:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.entries[0].owner",
                        "source root owner changed during admission",
                    ),
                )
            )
        _require_same_source_identity(
            root_before,
            root_after_fd,
            issue_path="$.entries[0]",
        )
        _require_same_source_identity(
            root_before,
            root_after_path,
            issue_path="$.entries[0]",
        )
    finally:
        os.close(root_fd)
    return manifest


def _build_provider_environment_manifest_from_fd(
    root_fd: int,
    provider_prefix: str,
    *,
    inject_launch_shim: bool,
    finalized_snapshot: bool,
) -> ProviderEnvironmentManifest:
    """Build one manifest by borrowing an already-open root directory."""

    prefix_issues = _absolute_prefix_issues(provider_prefix)
    if prefix_issues:
        raise ProviderIsolationEnvironmentError(prefix_issues)

    root_before = os.fstat(root_fd)
    _require_source_entry(
        root_before,
        path=".",
        issue_path="$.entries[0]",
        required_kind="directory",
    )
    if finalized_snapshot:
        _require_finalized_snapshot_metadata(
            root_before,
            issue_path="$.entries[0]",
        )
        _require_snapshot_noatime_flag(
            root_fd,
            issue_path="$.entries[0]",
        )
    _require_no_xattrs_fd(root_fd, issue_path="$.entries[0].xattrs")
    try:
        root_mount_id = _statx_mount_id(root_fd)
    except MountIdentityUnavailable as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.entries[0].mount_id",
                    "descriptor-bound mount identity is unavailable",
                ),
            )
        ) from exc

    root_entry = ProviderEnvironmentManifestEntry(
        path=".",
        kind="directory",
        mode=_normalized_mode(root_before.st_mode),
        uid=0,
        gid=0,
        atime_ns=0,
        mtime_ns=0,
    )
    scanned: dict[str, _ScannedEntry] = {
        ".": _ScannedEntry(root_entry, root_before, root_mount_id)
    }
    _scan_directory(
        root_fd,
        parent_path=".",
        root_mount_id=root_mount_id,
        scanned=scanned,
        finalized_snapshot=finalized_snapshot,
    )
    _require_same_source_identity(
        root_before,
        os.fstat(root_fd),
        issue_path="$.entries[0]",
    )

    _require_complete_hardlink_accounting(scanned)
    _require_safe_symlink_graph(scanned)
    if inject_launch_shim:
        _inject_launch_shim(scanned, provider_prefix)
        _inject_structural_mountpoints(scanned)

    document = {
        "schema_version": ENVIRONMENT_SCHEMA_VERSION,
        "provider_prefix": provider_prefix,
        "entries": [item.entry.to_dict() for item in scanned.values()],
    }
    return load_provider_environment_manifest(document)


def assemble_provider_environment_snapshot(
    source_root: str | os.PathLike[str],
    provider_prefix: str,
    run_root: str | os.PathLike[str],
    *,
    expected_digest: str,
    fault_hook: Callable[[str, Path], None] | None = None,
) -> ProviderEnvironmentSnapshot:
    """Create and atomically publish one fresh run-owned sealed snapshot."""

    _require_expected_snapshot_digest(expected_digest)
    source = _open_source_binding(source_root)
    try:
        return _assemble_provider_environment_snapshot_from_source(
            source,
            provider_prefix,
            run_root,
            expected_digest=expected_digest,
            fault_hook=fault_hook,
        )
    finally:
        source.close()


def _assemble_provider_environment_snapshot_from_source(
    source: _PinnedSource,
    provider_prefix: str,
    run_root: str | os.PathLike[str],
    *,
    expected_digest: str,
    fault_hook: Callable[[str, Path], None] | None,
) -> ProviderEnvironmentSnapshot:
    _require_expected_snapshot_digest(expected_digest)
    manifest = _build_provider_environment_manifest_from_fd(
        source.root_fd,
        provider_prefix,
        inject_launch_shim=True,
        finalized_snapshot=False,
    )
    if manifest.digest != expected_digest:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.digest",
                    "provider environment identity does not match expected digest",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
        )

    assembly = _open_snapshot_assembly(run_root)
    authority = assembly.authority_path
    authority_fd = assembly.authority_fd
    staging_name = assembly.staging_name
    staging = assembly.staging_path
    rootfs = assembly.rootfs_path
    try:
        final_name = manifest.digest
        try:
            os.stat(final_name, dir_fd=authority_fd, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.snapshot_authority",
                        "snapshot digest authority already exists",
                    ),
                )
            )

        _copy_manifest_tree_to_staging(
            source.root_fd,
            assembly.rootfs_fd,
            manifest,
            provider_prefix=provider_prefix,
        )
        if fault_hook is not None:
            fault_hook("population", rootfs)

        # Re-admit the mutable source after population so no later source
        # identity can silently replace the bytes copied into staging.
        repeated = _build_provider_environment_manifest_from_fd(
            source.root_fd,
            provider_prefix,
            inject_launch_shim=True,
            finalized_snapshot=False,
        )
        if repeated.canonical_json != manifest.canonical_json:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.source",
                        "environment source changed during snapshot population",
                    ),
                )
            )

        if fault_hook is not None:
            fault_hook("normalization", rootfs)
        _finalize_snapshot_rootfs(
            assembly.rootfs_fd,
            rootfs,
            manifest,
            fault_hook=fault_hook,
        )
        if fault_hook is not None:
            fault_hook("final_chmod", rootfs)
            fault_hook("manifest_verification", rootfs)
        rebuilt = _build_provider_environment_manifest_from_fd(
            assembly.rootfs_fd,
            provider_prefix,
            inject_launch_shim=False,
            finalized_snapshot=True,
        )
        if rebuilt.canonical_json != manifest.canonical_json:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.snapshot",
                        "finalized snapshot manifest differs from prospective identity",
                    ),
                )
            )
        _restore_verified_symlink_timestamps(
            assembly.rootfs_fd,
            manifest,
        )

        manifest_fd = _write_snapshot_manifest(
            assembly.staging_fd,
            manifest.canonical_json,
        )
        assembly.adopt_manifest_fd(manifest_fd)
        os.fsync(assembly.staging_fd)
        if fault_hook is not None:
            fault_hook("before_rename", staging)
        source.revalidate_edges()
        assembly.revalidate_before_rename()
        assembly.begin_rename(final_name)
        _rename_noreplace(
            authority_fd,
            staging_name,
            final_name,
        )
        assembly.mark_renamed(final_name)
        assembly.revalidate_after_rename()
        os.fsync(authority_fd)
        assembly.revalidate_after_rename()

        final_authority = authority / final_name
        published_rootfs = final_authority / "rootfs"
        root_fd = assembly.detach_root_fd()
        return ProviderEnvironmentSnapshot(
            manifest=manifest,
            authority_path=final_authority,
            rootfs_path=published_rootfs,
            manifest_path=final_authority / "manifest.json",
            root_fd=root_fd,
        )
    finally:
        if assembly.renamed:
            assembly.close()
        else:
            assembly.abort()


def verify_provider_environment_snapshot(
    rootfs_path: str | os.PathLike[str],
    *,
    expected_digest: str,
    expected_run_root: str | os.PathLike[str] | None = None,
) -> ProviderEnvironmentManifest:
    """Verify one published snapshot without consulting its mutable source."""

    run_root = (
        _derive_published_snapshot_run_root(
            rootfs_path,
            expected_digest=expected_digest,
        )
        if expected_run_root is None
        else _require_canonical_absolute_authority_spelling(
            expected_run_root,
            issue_path="$.run_root",
            label="expected run root",
        )
    )
    pinned = _open_published_snapshot(
        run_root,
        expected_digest,
        supplied_rootfs_path=rootfs_path,
    )
    try:
        return _verify_pinned_snapshot(
            pinned,
            expected_digest=expected_digest,
        )
    finally:
        pinned.close()


def load_provider_environment_snapshot(
    run_root: str | os.PathLike[str],
    *,
    expected_digest: str,
) -> ProviderEnvironmentSnapshot:
    """Load and pin the exact previously published snapshot for resume."""

    return _load_provider_environment_snapshot(
        run_root,
        expected_digest=expected_digest,
        require_symlink_free=False,
    )


def load_provider_environment_snapshot_for_launch(
    run_root: str | os.PathLike[str],
    *,
    expected_digest: str,
) -> ProviderEnvironmentSnapshot:
    """Load a verified snapshot admitted for a timestamp-stable launch."""

    return _load_provider_environment_snapshot(
        run_root,
        expected_digest=expected_digest,
        require_symlink_free=True,
    )


def _load_provider_environment_snapshot(
    run_root: str | os.PathLike[str],
    *,
    expected_digest: str,
    require_symlink_free: bool,
) -> ProviderEnvironmentSnapshot:
    run_path = _require_canonical_absolute_authority_spelling(
        run_root,
        issue_path="$.run_root",
        label="expected run root",
    )
    rootfs = (
        run_path
        / "provider_environment_snapshots"
        / expected_digest
        / "rootfs"
    )
    pinned: _PinnedSnapshot | None = None
    try:
        pinned = _open_published_snapshot(
            run_path,
            expected_digest,
            supplied_rootfs_path=rootfs,
        )
        manifest = _verify_pinned_snapshot(
            pinned,
            expected_digest=expected_digest,
            require_symlink_free=require_symlink_free,
        )
        try:
            os.fsync(pinned.snapshots_fd)
        except OSError as exc:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        "$.snapshot_authority.durability",
                        "verified snapshot authority could not be durably accepted",
                    ),
                )
            ) from exc
        pinned.revalidate_edges()
        root_fd = pinned.detach_root_fd()
        return ProviderEnvironmentSnapshot(
            manifest=manifest,
            authority_path=pinned.authority_path,
            rootfs_path=pinned.rootfs_path,
            manifest_path=pinned.manifest_path,
            root_fd=root_fd,
        )
    finally:
        if pinned is not None:
            pinned.close()


def _derive_published_snapshot_run_root(
    rootfs_path: str | os.PathLike[str],
    *,
    expected_digest: str,
) -> Path:
    _require_expected_snapshot_digest(expected_digest)

    rootfs = _require_canonical_absolute_authority_spelling(
        rootfs_path,
        issue_path="$.snapshot",
        label="snapshot rootfs path",
    )

    authority = rootfs.parent
    snapshots = authority.parent
    run_root = snapshots.parent
    if (
        rootfs.name != "rootfs"
        or _DIGEST_PATTERN.fullmatch(authority.name) is None
        or snapshots.name != "provider_environment_snapshots"
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot",
                    "snapshot must use the exact run-owned digest authority",
                ),
            )
        )
    if authority.name != expected_digest:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.digest",
                    "provider environment identity does not match expected digest",
                    code=ENVIRONMENT_MISMATCH_CODE,
                ),
            )
        )
    return run_root


def _open_absolute_directory_chain(
    path: str | os.PathLike[str],
    *,
    issue_path: str,
) -> tuple[list[int], list[_PinnedEdge]]:
    value = Path(path)
    if not value.is_absolute():
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority must be absolute"),)
        )
    if ".." in value.parts:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority must be a real canonical path"),)
        )

    owned_fds: list[int] = []
    edges: list[_PinnedEdge] = []
    try:
        parent_fd = _open_directory("/")
        owned_fds.append(parent_fd)
        for index, name in enumerate(value.parts[1:]):
            before = _lstat_at(parent_fd, name)
            child_fd = _open_directory_at(parent_fd, name)
            owned_fds.append(child_fd)
            opened = os.fstat(child_fd)
            edge_path = f"{issue_path}.components[{index}]"
            _require_same_source_identity(
                before,
                opened,
                issue_path=edge_path,
            )
            edges.append(
                _PinnedEdge(
                    parent_fd=parent_fd,
                    child_fd=child_fd,
                    name=name,
                    opened_stat=opened,
                    issue_path=edge_path,
                )
            )
            parent_fd = child_fd
        return owned_fds, edges
    except BaseException:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _open_source_binding(
    source_root: str | os.PathLike[str],
) -> _PinnedSource:
    owned_fds: list[int] = []
    try:
        owned_fds, edges = _open_absolute_directory_chain(
            source_root,
            issue_path="$.source",
        )
        root_fd = owned_fds[-1]
        _require_source_entry(
            os.fstat(root_fd),
            path=".",
            issue_path="$.entries[0]",
            required_kind="directory",
        )
        return _PinnedSource(
            root_fd=root_fd,
            _owned_fds=owned_fds,
            _edges=tuple(edges),
        )
    except ProviderIsolationEnvironmentError:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise ProviderIsolationEnvironmentError(
            (_issue("$.source", "environment source root is unavailable"),)
        ) from exc


def _open_snapshot_assembly(
    run_root: str | os.PathLike[str],
) -> _SnapshotAssembly:
    run_path = _require_canonical_absolute_authority_spelling(
        run_root,
        issue_path="$.run_root",
        label="run root",
    )
    owned_fds: list[int] = []
    edges: list[_PinnedEdge] = []
    authority_fd: int | None = None
    staging_fd: int | None = None
    try:
        owned_fds, edges = _open_absolute_directory_chain(
            run_path,
            issue_path="$.run_root",
        )
        run_root_fd = owned_fds[-1]
        _require_private_directory_fd(
            run_root_fd,
            issue_path="$.run_root",
            exact_mode=0o700,
        )

        authority_name = "provider_environment_snapshots"
        try:
            os.mkdir(authority_name, 0o700, dir_fd=run_root_fd)
        except FileExistsError:
            pass
        authority_fd = _open_pinned_directory_at(
            run_root_fd,
            authority_name,
            issue_path="$.snapshot_authority",
            owned_fds=owned_fds,
            edges=edges,
        )
        _require_private_directory_fd(
            authority_fd,
            issue_path="$.snapshot_authority",
            exact_mode=0o700,
        )
        authority_path = run_path / authority_name

        staging_name = f".staging-{uuid.uuid4().hex}"
        os.mkdir(staging_name, 0o700, dir_fd=authority_fd)
        staging_path = authority_path / staging_name
        staging_fd = _open_pinned_directory_at(
            authority_fd,
            staging_name,
            issue_path="$.snapshot_staging",
            owned_fds=owned_fds,
            edges=edges,
        )
        _require_private_directory_fd(
            staging_fd,
            issue_path="$.snapshot_staging",
            exact_mode=0o700,
        )

        rootfs_name = "rootfs"
        os.mkdir(rootfs_name, 0o700, dir_fd=staging_fd)
        rootfs_path = staging_path / rootfs_name
        rootfs_fd = _open_pinned_directory_at(
            staging_fd,
            rootfs_name,
            issue_path="$.snapshot_staging.rootfs",
            owned_fds=owned_fds,
            edges=edges,
        )
        _require_private_directory_fd(
            rootfs_fd,
            issue_path="$.snapshot_staging.rootfs",
            exact_mode=0o700,
        )
        return _SnapshotAssembly(
            run_root_path=run_path,
            authority_path=authority_path,
            staging_path=staging_path,
            rootfs_path=rootfs_path,
            run_root_fd=run_root_fd,
            authority_fd=authority_fd,
            staging_fd=staging_fd,
            rootfs_fd=rootfs_fd,
            staging_name=staging_name,
            rootfs_name=rootfs_name,
            _owned_fds=owned_fds,
            _edges=tuple(edges),
        )
    except ProviderIsolationEnvironmentError:
        try:
            if authority_fd is not None and staging_fd is not None:
                _remove_held_private_staging(authority_fd, staging_fd)
        finally:
            for fd in reversed(owned_fds):
                try:
                    os.close(fd)
                except OSError:
                    pass
        raise
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        try:
            if authority_fd is not None and staging_fd is not None:
                _remove_held_private_staging(authority_fd, staging_fd)
        finally:
            for fd in reversed(owned_fds):
                try:
                    os.close(fd)
                except OSError:
                    pass
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_authority",
                    "snapshot assembly authority is unavailable",
                ),
            )
        ) from exc


def _open_published_snapshot(
    expected_run_root: str | os.PathLike[str],
    expected_digest: str,
    *,
    supplied_rootfs_path: str | os.PathLike[str],
) -> _PinnedSnapshot:
    _require_expected_snapshot_digest(expected_digest)
    run_root = _require_canonical_absolute_authority_spelling(
        expected_run_root,
        issue_path="$.run_root",
        label="expected run root",
    )
    rootfs = _require_canonical_absolute_authority_spelling(
        supplied_rootfs_path,
        issue_path="$.snapshot",
        label="snapshot rootfs path",
    )
    derived_run_root = _derive_published_snapshot_run_root(
        rootfs,
        expected_digest=expected_digest,
    )
    if derived_run_root != run_root:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.run_root",
                    "snapshot does not belong to the expected run root",
                ),
            )
        )
    expected_rootfs = (
        run_root
        / "provider_environment_snapshots"
        / expected_digest
        / "rootfs"
    )
    if rootfs != expected_rootfs:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot",
                    "snapshot must use the exact run-owned digest authority",
                ),
            )
        )

    owned_fds: list[int] = []
    edges: list[_PinnedEdge] = []
    try:
        owned_fds, edges = _open_absolute_directory_chain(
            run_root,
            issue_path="$.run_root",
        )
        run_root_fd = owned_fds[-1]
        _require_private_directory_fd(
            run_root_fd,
            issue_path="$.run_root",
            exact_mode=0o700,
        )
        snapshots_fd = _open_pinned_directory_at(
            run_root_fd,
            "provider_environment_snapshots",
            issue_path="$.snapshot_authority",
            owned_fds=owned_fds,
            edges=edges,
        )
        _require_private_directory_fd(
            snapshots_fd,
            issue_path="$.snapshot_authority",
            exact_mode=0o700,
        )
        authority_fd = _open_pinned_directory_at(
            snapshots_fd,
            expected_digest,
            issue_path="$.snapshot",
            owned_fds=owned_fds,
            edges=edges,
        )
        _require_private_directory_fd(
            authority_fd,
            issue_path="$.snapshot",
            exact_mode=0o700,
        )
        root_fd = _open_pinned_directory_at(
            authority_fd,
            "rootfs",
            issue_path="$.snapshot",
            owned_fds=owned_fds,
            edges=edges,
        )
        manifest_fd = _open_pinned_regular_at(
            authority_fd,
            "manifest.json",
            issue_path="$.snapshot_manifest",
            owned_fds=owned_fds,
            edges=edges,
        )
        authority = rootfs.parent
        return _PinnedSnapshot(
            run_root_path=run_root,
            authority_path=authority,
            rootfs_path=rootfs,
            manifest_path=authority / "manifest.json",
            snapshots_fd=snapshots_fd,
            root_fd=root_fd,
            manifest_fd=manifest_fd,
            _owned_fds=owned_fds,
            _edges=tuple(edges),
        )
    except ProviderIsolationEnvironmentError:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise
    except (FileNotFoundError, NotADirectoryError, OSError) as exc:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise ProviderIsolationEnvironmentError(
            (_issue("$.snapshot", "required published snapshot is unavailable"),)
        ) from exc


def _require_canonical_absolute_authority_spelling(
    path: str | os.PathLike[str],
    *,
    issue_path: str,
    label: str,
) -> Path:
    try:
        raw = os.fspath(path)
    except TypeError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must be a text filesystem path"),)
        ) from exc
    if not isinstance(raw, str):
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must be a text filesystem path"),)
        )
    text_issues = _strict_nfc_text_issues(raw, issue_path, label=label)
    if text_issues:
        raise ProviderIsolationEnvironmentError(text_issues)
    if "\x00" in raw:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must not contain NUL"),)
        )
    if not raw.startswith("/"):
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must be absolute"),)
        )
    if raw != "/" and any(
        component in {"", ".", ".."} for component in raw.split("/")[1:]
    ):
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must use canonical lexical spelling"),)
        )
    value = Path(raw)
    if not value.is_absolute() or os.fspath(value) != raw:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, f"{label} must use canonical lexical spelling"),)
        )
    return value


def _open_pinned_directory_at(
    parent_fd: int,
    name: str,
    *,
    issue_path: str,
    owned_fds: list[int],
    edges: list[_PinnedEdge],
) -> int:
    before = _lstat_at(parent_fd, name)
    child_fd = _open_directory_at(parent_fd, name)
    owned_fds.append(child_fd)
    opened = os.fstat(child_fd)
    _require_same_source_identity(before, opened, issue_path=issue_path)
    edges.append(
        _PinnedEdge(
            parent_fd=parent_fd,
            child_fd=child_fd,
            name=name,
            opened_stat=opened,
            issue_path=issue_path,
        )
    )
    return child_fd


def _open_pinned_regular_at(
    parent_fd: int,
    name: str,
    *,
    issue_path: str,
    owned_fds: list[int],
    edges: list[_PinnedEdge],
) -> int:
    before = _lstat_at(parent_fd, name)
    child_fd = _open_regular_at(parent_fd, name)
    owned_fds.append(child_fd)
    opened = os.fstat(child_fd)
    _require_same_source_identity(before, opened, issue_path=issue_path)
    edges.append(
        _PinnedEdge(
            parent_fd=parent_fd,
            child_fd=child_fd,
            name=name,
            opened_stat=opened,
            issue_path=issue_path,
        )
    )
    return child_fd


def _require_private_directory_fd(
    fd: int,
    *,
    issue_path: str,
    exact_mode: int,
) -> None:
    observed = os.fstat(fd)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != exact_mode
    ):
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority is not private and trusted"),)
        )
    _require_no_xattrs_fd(fd, issue_path=f"{issue_path}.xattrs")


def _verify_pinned_snapshot(
    pinned: _PinnedSnapshot,
    *,
    expected_digest: str,
    require_symlink_free: bool = False,
    verification_hook: Callable[[str, _PinnedSnapshot], None] | None = None,
) -> ProviderEnvironmentManifest:
    if verification_hook is not None:
        verification_hook("after_pinned_open", pinned)
    manifest = _load_published_snapshot_manifest_from_fd(
        pinned.manifest_fd,
        expected_digest=expected_digest,
        after_read=(
            None
            if verification_hook is None
            else lambda: verification_hook("after_manifest_read", pinned)
        ),
    )
    if require_symlink_free:
        symlink = next(
            (
                entry
                for entry in manifest.entries
                if entry.kind == "symlink"
            ),
            None,
        )
        if symlink is not None:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        f"$.entries[{symlink.path}].kind",
                        "strict launch snapshots must not contain symlinks",
                    ),
                )
            )
    rebuilt = _build_provider_environment_manifest_from_fd(
        pinned.root_fd,
        manifest.provider_prefix,
        inject_launch_shim=False,
        finalized_snapshot=True,
    )
    if rebuilt.canonical_json != manifest.canonical_json:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot",
                    "published snapshot differs from its bound manifest",
                ),
            )
        )
    _restore_verified_symlink_timestamps(
        pinned.root_fd,
        manifest,
    )
    if verification_hook is not None:
        verification_hook("after_tree_scan", pinned)
    if verification_hook is not None:
        verification_hook("before_edge_revalidation", pinned)
    pinned.revalidate_edges()
    return manifest


def _require_expected_snapshot_digest(expected_digest: object) -> None:
    if (
        not isinstance(expected_digest, str)
        or _DIGEST_PATTERN.fullmatch(expected_digest) is None
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.digest",
                    "expected environment identity must be canonical sha256",
                ),
            )
        )


def _load_published_snapshot_manifest_from_fd(
    fd: int,
    *,
    expected_digest: str,
    after_read: Callable[[], None] | None = None,
) -> ProviderEnvironmentManifest:
    """Read one canonical snapshot manifest from a borrowed pinned descriptor."""

    before = os.fstat(fd)
    _require_canonical_snapshot_manifest_metadata(before)
    _require_snapshot_noatime_flag(
        fd,
        issue_path="$.snapshot_manifest",
    )
    _require_no_xattrs_fd(fd, issue_path="$.snapshot_manifest.xattrs")
    content = _read_all(fd)
    after = os.fstat(fd)
    _require_snapshot_noatime_flag(
        fd,
        issue_path="$.snapshot_manifest",
    )
    _require_canonical_snapshot_manifest_metadata(after)
    _require_same_source_identity(
        before,
        after,
        issue_path="$.snapshot_manifest",
    )
    if after_read is not None:
        after_read()

    try:
        document = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue("$.snapshot_manifest", "snapshot manifest is not canonical JSON"),)
        ) from exc
    if not isinstance(document, Mapping):
        raise ProviderIsolationEnvironmentError(
            (_issue("$.snapshot_manifest", "snapshot manifest must be an object"),)
        )
    manifest = load_provider_environment_manifest(
        document,
        expected_digest=expected_digest,
    )
    if content != manifest.canonical_json:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_manifest",
                    "snapshot manifest bytes are not canonical",
                ),
            )
        )
    return manifest


def _require_canonical_snapshot_manifest_metadata(
    value: os.stat_result,
) -> None:
    if (
        not stat.S_ISREG(value.st_mode)
        or value.st_uid != os.geteuid()
        or value.st_gid != os.getegid()
        or stat.S_IMODE(value.st_mode) != 0o400
        or value.st_nlink != 1
        or value.st_atime_ns != 0
        or value.st_mtime_ns != 0
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_manifest",
                    "snapshot manifest metadata is not canonical",
                ),
            )
        )


def _require_real_private_directory(
    path: str | os.PathLike[str],
    *,
    issue_path: str,
    exact_mode: int,
) -> Path:
    value = _require_private_directory(
        path,
        issue_path=issue_path,
        exact_mode=exact_mode,
    )
    try:
        resolved = value.resolve(strict=True)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority cannot be resolved safely"),)
        ) from exc
    if resolved != value:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority must be a real canonical path"),)
        )
    return value


def _copy_manifest_tree_to_staging(
    source_root_fd: int,
    destination_root_fd: int,
    manifest: ProviderEnvironmentManifest,
    *,
    provider_prefix: str,
) -> None:
    source_dirs: dict[str, int] = {".": source_root_fd}
    destination_dirs: dict[str, int] = {".": destination_root_fd}
    source_records: list[tuple[int, str, str, os.stat_result]] = []
    root_before = os.fstat(source_root_fd)
    try:
        root_mount_id = _statx_mount_id(source_root_fd)
    except MountIdentityUnavailable as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.entries[0].mount_id",
                    "descriptor-bound mount identity is unavailable during snapshot population",
                ),
            )
        ) from exc
    shim_relpath = (
        f"{provider_prefix.lstrip('/')}/libexec/provider-launch-shim-v1.py"
    )
    libexec_relpath = posixpath.dirname(shim_relpath)
    shim_bytes = _packaged_launch_shim_bytes()
    try:
        entries = sorted(
            (entry for entry in manifest.entries if entry.path != "."),
            key=lambda entry: (
                entry.path.count("/"),
                entry.path.encode("utf-8"),
            ),
        )
        for entry in entries:
            parent = posixpath.dirname(entry.path) or "."
            name = posixpath.basename(entry.path)
            destination_parent_fd = destination_dirs[parent]
            source_parent_fd = source_dirs.get(parent)

            source_stat: os.stat_result | None = None
            if source_parent_fd is not None:
                try:
                    source_stat = _lstat_at(source_parent_fd, name)
                except FileNotFoundError:
                    source_stat = None

            if entry.path == shim_relpath:
                if source_stat is not None:
                    raise ProviderIsolationEnvironmentError(
                        (
                            _issue(
                                f"$.entries[{entry.path}]",
                                "source collides with the reserved launch shim",
                            ),
                        )
                    )
                _write_new_regular_at(
                    destination_parent_fd,
                    name,
                    shim_bytes,
                )
                if entry.size != len(shim_bytes) or entry.digest != _digest(shim_bytes):
                    raise ProviderIsolationEnvironmentError(
                        (
                            _issue(
                                f"$.entries[{entry.path}]",
                                "packaged launch shim identity changed",
                            ),
                        )
                    )
                continue

            if source_stat is None:
                if entry.kind == "directory" and (
                    entry.path == libexec_relpath
                    or entry.path in _STRUCTURAL_MOUNTPOINT_RELPATHS
                ):
                    os.mkdir(name, 0o700, dir_fd=destination_parent_fd)
                    destination_dirs[entry.path] = _open_directory_at(
                        destination_parent_fd,
                        name,
                    )
                    continue
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"$.entries[{entry.path}].identity",
                            "source entry disappeared during snapshot population",
                        ),
                    )
                )

            assert source_parent_fd is not None
            issue_base = f"$.entries[{entry.path}]"
            _require_source_entry(
                source_stat,
                path=entry.path,
                issue_path=issue_base,
            )
            observed_mode = (
                0o777
                if stat.S_ISLNK(source_stat.st_mode)
                else _normalized_mode(source_stat.st_mode)
            )
            if observed_mode != entry.mode:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_base}.mode",
                            "source mode changed after manifest admission",
                        ),
                    )
                )
            try:
                entry_mount_id = _statx_mount_id(source_parent_fd, name)
            except MountIdentityUnavailable as exc:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_base}.mount_id",
                            "descriptor-bound mount identity is unavailable during snapshot population",
                        ),
                    )
                ) from exc
            if entry_mount_id != root_mount_id:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_base}.mount_id",
                            "source mount identity changed during snapshot population",
                        ),
                    )
                )

            if entry.kind == "directory":
                if not stat.S_ISDIR(source_stat.st_mode):
                    raise ProviderIsolationEnvironmentError(
                        (_issue(f"{issue_base}.kind", "source type changed"),)
                    )
                source_child_fd = _open_directory_at(source_parent_fd, name)
                source_dirs[entry.path] = source_child_fd
                _require_same_source_identity(
                    source_stat,
                    os.fstat(source_child_fd),
                    issue_path=issue_base,
                )
                _require_opened_source_mount_identity(
                    source_child_fd,
                    entry_mount_id=entry_mount_id,
                    root_mount_id=root_mount_id,
                    issue_path=issue_base,
                    phase="snapshot population",
                )
                _require_no_xattrs_fd(
                    source_child_fd,
                    issue_path=f"{issue_base}.xattrs",
                )
                os.mkdir(name, 0o700, dir_fd=destination_parent_fd)
                destination_child_fd = _open_directory_at(
                    destination_parent_fd,
                    name,
                )
                destination_dirs[entry.path] = destination_child_fd
                source_records.append(
                    (source_parent_fd, name, issue_base, source_stat)
                )
                continue

            if entry.kind == "regular_file":
                if not stat.S_ISREG(source_stat.st_mode):
                    raise ProviderIsolationEnvironmentError(
                        (_issue(f"{issue_base}.kind", "source type changed"),)
                    )
                source_fd = _open_regular_at(source_parent_fd, name)
                try:
                    _require_same_source_identity(
                        source_stat,
                        os.fstat(source_fd),
                        issue_path=issue_base,
                    )
                    _require_opened_source_mount_identity(
                        source_fd,
                        entry_mount_id=entry_mount_id,
                        root_mount_id=root_mount_id,
                        issue_path=issue_base,
                        phase="snapshot population",
                    )
                    _require_no_xattrs_fd(
                        source_fd,
                        issue_path=f"{issue_base}.xattrs",
                    )
                    observed_size, observed_digest = _copy_regular_to_new_at(
                        source_fd,
                        destination_parent_fd,
                        name,
                    )
                    after_fd = os.fstat(source_fd)
                finally:
                    os.close(source_fd)
                after_path = _lstat_at(source_parent_fd, name)
                _require_same_source_identity(
                    source_stat,
                    after_fd,
                    issue_path=issue_base,
                )
                _require_same_source_identity(
                    source_stat,
                    after_path,
                    issue_path=issue_base,
                )
                if (
                    observed_size != entry.size
                    or observed_digest != entry.digest
                ):
                    raise ProviderIsolationEnvironmentError(
                        (
                            _issue(
                                f"{issue_base}.digest",
                                "copied source bytes differ from admitted manifest",
                            ),
                        )
                    )
                source_records.append(
                    (source_parent_fd, name, issue_base, source_stat)
                )
                continue

            if entry.kind == "symlink":
                if not stat.S_ISLNK(source_stat.st_mode):
                    raise ProviderIsolationEnvironmentError(
                        (_issue(f"{issue_base}.kind", "source type changed"),)
                    )
                _require_no_xattrs_at(
                    source_parent_fd,
                    name,
                    issue_path=f"{issue_base}.xattrs",
                )
                link_text = os.readlink(name, dir_fd=source_parent_fd)
                if link_text != entry.link_text:
                    raise ProviderIsolationEnvironmentError(
                        (
                            _issue(
                                f"{issue_base}.link_text",
                                "source symlink changed after manifest admission",
                            ),
                        )
                    )
                os.symlink(link_text, name, dir_fd=destination_parent_fd)
                after_path = _lstat_at(source_parent_fd, name)
                _require_same_source_identity(
                    source_stat,
                    after_path,
                    issue_path=issue_base,
                )
                source_records.append(
                    (source_parent_fd, name, issue_base, source_stat)
                )
                continue

            raise AssertionError(f"unexpected manifest entry kind {entry.kind!r}")

        for parent_fd, name, issue_base, before in source_records:
            _require_same_source_identity(
                before,
                _lstat_at(parent_fd, name),
                issue_path=issue_base,
            )
        _require_same_source_identity(
            root_before,
            os.fstat(source_root_fd),
            issue_path="$.entries[0]",
        )
    finally:
        for path, fd in sorted(
            destination_dirs.items(),
            key=lambda item: item[0].count("/"),
            reverse=True,
        ):
            if path == ".":
                continue
            try:
                os.close(fd)
            except OSError:
                pass
        for path, fd in sorted(
            source_dirs.items(),
            key=lambda item: item[0].count("/"),
            reverse=True,
        ):
            if path == ".":
                continue
            try:
                os.close(fd)
            except OSError:
                pass


def _write_new_regular_at(
    directory_fd: int,
    name: str,
    content: bytes,
) -> None:
    fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=directory_fd,
    )
    try:
        _write_all(fd, content)
        os.fsync(fd)
    finally:
        os.close(fd)


def _copy_regular_to_new_at(
    source_fd: int,
    destination_directory_fd: int,
    name: str,
) -> tuple[int, str]:
    destination_fd = os.open(
        name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
        dir_fd=destination_directory_fd,
    )
    digest = sha256()
    size = 0
    try:
        os.lseek(source_fd, 0, os.SEEK_SET)
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            _write_all(destination_fd, block)
            size += len(block)
            digest.update(block)
        os.fsync(destination_fd)
    finally:
        os.close(destination_fd)
    return size, f"sha256:{digest.hexdigest()}"


def _write_all(fd: int, value: bytes) -> None:
    offset = 0
    while offset < len(value):
        written = os.write(fd, value[offset:])
        if written <= 0:  # pragma: no cover - defensive kernel invariant
            raise OSError(errno.EIO, "short write while assembling snapshot")
        offset += written


def _finalize_snapshot_rootfs(
    rootfs_fd: int,
    display_rootfs: Path,
    manifest: ProviderEnvironmentManifest,
    *,
    fault_hook: Callable[[str, Path], None] | None = None,
) -> None:
    files_and_links = sorted(
        (entry for entry in manifest.entries if entry.kind != "directory"),
        key=lambda entry: entry.path.encode("utf-8"),
    )
    directories = sorted(
        (entry for entry in manifest.entries if entry.kind == "directory"),
        key=lambda entry: (
            entry.path.count("/"),
            entry.path.encode("utf-8"),
        ),
        reverse=True,
    )
    directory_fds, owned_directory_fds = _open_snapshot_manifest_directories(
        rootfs_fd,
        manifest,
    )
    try:
        for entry in files_and_links:
            parent = posixpath.dirname(entry.path) or "."
            name = posixpath.basename(entry.path)
            parent_fd = directory_fds[parent]
            issue_path = f"$.entries[{entry.path}]"
            observed = _lstat_at(parent_fd, name)
            if entry.kind == "regular_file":
                if not stat.S_ISREG(observed.st_mode):
                    raise ProviderIsolationEnvironmentError(
                        (_issue(f"{issue_path}.kind", "snapshot type changed"),)
                    )
                fd = _open_regular_at(parent_fd, name)
                try:
                    _require_same_source_identity(
                        observed,
                        os.fstat(fd),
                        issue_path=issue_path,
                    )
                    if (
                        observed.st_uid != os.geteuid()
                        or observed.st_gid != os.getegid()
                    ):
                        os.fchown(fd, os.geteuid(), os.getegid())
                    os.fchmod(fd, entry.mode)
                    expected_inode_flags = _apply_snapshot_noatime_flag(
                        fd,
                        issue_path=issue_path,
                    )
                    os.utime(fd, ns=(0, 0))
                    _require_snapshot_inode_flags(
                        fd,
                        issue_path=issue_path,
                        expected_flags=expected_inode_flags,
                    )
                    finalized = os.fstat(fd)
                    _require_finalized_snapshot_metadata(
                        finalized,
                        issue_path=issue_path,
                    )
                    if stat.S_IMODE(finalized.st_mode) != entry.mode:
                        raise ProviderIsolationEnvironmentError(
                            (
                                _issue(
                                    f"{issue_path}.mode",
                                    "snapshot mode differs from its manifest",
                                ),
                            )
                        )
                    os.fsync(fd)
                finally:
                    os.close(fd)
                if fault_hook is not None:
                    fault_hook(
                        "descendant_finalization",
                        display_rootfs / entry.path,
                    )
                continue

            if entry.kind != "symlink" or not stat.S_ISLNK(observed.st_mode):
                raise ProviderIsolationEnvironmentError(
                    (_issue(f"{issue_path}.kind", "snapshot type changed"),)
                )
            if (
                observed.st_uid != os.geteuid()
                or observed.st_gid != os.getegid()
            ):
                os.chown(
                    name,
                    os.geteuid(),
                    os.getegid(),
                    dir_fd=parent_fd,
                    follow_symlinks=False,
                )
            os.utime(
                name,
                ns=(0, 0),
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            finalized = _lstat_at(parent_fd, name)
            if not os.path.samestat(observed, finalized):
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_path}.identity",
                            "snapshot symlink changed during finalization",
                        ),
                    )
                )
            _require_finalized_snapshot_metadata(
                finalized,
                issue_path=issue_path,
            )

        for entry in directories:
            fd = directory_fds[entry.path]
            issue_path = f"$.entries[{entry.path}]"
            observed = os.fstat(fd)
            if (
                observed.st_uid != os.geteuid()
                or observed.st_gid != os.getegid()
            ):
                os.fchown(fd, os.geteuid(), os.getegid())
            os.fchmod(fd, entry.mode)
            expected_inode_flags = _apply_snapshot_noatime_flag(
                fd,
                issue_path=issue_path,
            )
            os.utime(fd, ns=(0, 0))
            _require_snapshot_inode_flags(
                fd,
                issue_path=issue_path,
                expected_flags=expected_inode_flags,
            )
            finalized = os.fstat(fd)
            _require_finalized_snapshot_metadata(
                finalized,
                issue_path=issue_path,
            )
            if stat.S_IMODE(finalized.st_mode) != entry.mode:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_path}.mode",
                            "snapshot mode differs from its manifest",
                        ),
                    )
                )
            os.fsync(fd)
            if fault_hook is not None:
                fault_hook(
                    (
                        "root_finalization"
                        if entry.path == "."
                        else "descendant_finalization"
                    ),
                    (
                        display_rootfs
                        if entry.path == "."
                        else display_rootfs / entry.path
                    ),
                )
    finally:
        for fd in reversed(owned_directory_fds):
            os.close(fd)


def _open_snapshot_manifest_directories(
    rootfs_fd: int,
    manifest: ProviderEnvironmentManifest,
) -> tuple[dict[str, int], list[int]]:
    directories = sorted(
        (
            entry
            for entry in manifest.entries
            if entry.kind == "directory" and entry.path != "."
        ),
        key=lambda entry: (
            entry.path.count("/"),
            entry.path.encode("utf-8"),
        ),
    )
    result = {".": rootfs_fd}
    owned: list[int] = []
    try:
        for entry in directories:
            parent = posixpath.dirname(entry.path) or "."
            name = posixpath.basename(entry.path)
            parent_fd = result[parent]
            observed = _lstat_at(parent_fd, name)
            child_fd = _open_directory_at(parent_fd, name)
            owned.append(child_fd)
            _require_same_source_identity(
                observed,
                os.fstat(child_fd),
                issue_path=f"$.entries[{entry.path}]",
            )
            result[entry.path] = child_fd
        return result, owned
    except BaseException:
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _write_snapshot_manifest(staging_fd: int, content: bytes) -> int:
    try:
        fd = os.open(
            "manifest.json",
            os.O_RDWR
            | os.O_CREAT
            | os.O_EXCL
            | os.O_NONBLOCK
            | os.O_NOFOLLOW
            | os.O_CLOEXEC,
            0o600,
            dir_fd=staging_fd,
        )
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_manifest",
                    "snapshot manifest destination already exists or is unsafe",
                ),
            )
        ) from exc
    try:
        _write_all(fd, content)
        os.fchmod(fd, 0o400)
        expected_inode_flags = _apply_snapshot_noatime_flag(
            fd,
            issue_path="$.snapshot_manifest",
        )
        os.utime(fd, ns=(0, 0))
        _require_snapshot_inode_flags(
            fd,
            issue_path="$.snapshot_manifest",
            expected_flags=expected_inode_flags,
        )
        value = os.fstat(fd)
        _require_canonical_snapshot_manifest_metadata(value)
        os.fsync(fd)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _restore_verified_symlink_timestamps(
    rootfs_fd: int,
    manifest: ProviderEnvironmentManifest,
) -> None:
    directory_fds, owned_directory_fds = _open_snapshot_manifest_directories(
        rootfs_fd,
        manifest,
    )
    parent_paths: set[str] = set()
    try:
        for entry in manifest.entries:
            if entry.kind != "symlink":
                continue
            parent = posixpath.dirname(entry.path) or "."
            name = posixpath.basename(entry.path)
            parent_fd = directory_fds[parent]
            before = _lstat_at(parent_fd, name)
            if not stat.S_ISLNK(before.st_mode):
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"$.entries[{entry.path}].kind",
                            "snapshot symlink type changed",
                        ),
                    )
                )
            os.utime(
                name,
                ns=(0, 0),
                dir_fd=parent_fd,
                follow_symlinks=False,
            )
            observed = _lstat_at(parent_fd, name)
            if (
                not os.path.samestat(before, observed)
                or observed.st_atime_ns != 0
                or observed.st_mtime_ns != 0
            ):
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"$.entries[{entry.path}].timestamps",
                            "snapshot symlink timestamps could not be fixed",
                        ),
                    )
                )
            parent_paths.add(parent)
        for parent in sorted(
            parent_paths,
            key=lambda value: value.count("/"),
            reverse=True,
        ):
            os.fsync(directory_fds[parent])
    finally:
        for fd in reversed(owned_directory_fds):
            os.close(fd)


def _rename_noreplace(
    parent_fd: int,
    source_name: str,
    destination_name: str,
) -> None:
    try:
        renameat2 = ctypes.CDLL(None, use_errno=True).renameat2
    except AttributeError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_authority",
                    "atomic no-replace rename is unavailable",
                ),
            )
        ) from exc
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    if (
        renameat2(
            parent_fd,
            source_name.encode("utf-8"),
            parent_fd,
            destination_name.encode("utf-8"),
            1,
        )
        == 0
    ):
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_authority",
                    "snapshot digest authority already exists",
                ),
            )
        )
    raise ProviderIsolationEnvironmentError(
        (
            _issue(
                "$.snapshot_authority",
                "atomic no-replace snapshot publication failed",
            ),
        )
    )


def _require_private_directory(
    path: str | os.PathLike[str],
    *,
    issue_path: str,
    exact_mode: int,
) -> Path:
    value = Path(path)
    if not value.is_absolute():
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority must be absolute"),)
        )
    observed = os.stat(value, follow_symlinks=False)
    if (
        not stat.S_ISDIR(observed.st_mode)
        or observed.st_uid != os.geteuid()
        or stat.S_IMODE(observed.st_mode) != exact_mode
    ):
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority is not private and trusted"),)
        )
    try:
        if os.listxattr(value, follow_symlinks=False):
            raise ProviderIsolationEnvironmentError(
                (_issue(issue_path, "directory authority xattrs are forbidden"),)
            )
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "directory authority cannot be inspected"),)
        ) from exc
    return value


def _remove_held_private_staging(
    authority_fd: int,
    staging_fd: int,
) -> None:
    """Remove only the staging directory identified by the borrowed descriptors."""

    held = os.fstat(staging_fd)
    if (
        not stat.S_ISDIR(held.st_mode)
        or held.st_uid != os.geteuid()
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_staging",
                    "held snapshot staging authority is not trusted",
                ),
            )
        )
    _remove_directory_contents_at(staging_fd)

    current = os.fstat(staging_fd)
    matching_names: list[str] = []
    for name in os.listdir(authority_fd):
        try:
            candidate = _lstat_at(authority_fd, name)
        except FileNotFoundError:
            continue
        if stat.S_ISDIR(candidate.st_mode) and os.path.samestat(candidate, current):
            matching_names.append(name)
    if len(matching_names) != 1:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_staging.identity",
                    "held snapshot staging authority cannot be removed exactly",
                ),
            )
        )

    name = matching_names[0]
    before_remove = _lstat_at(authority_fd, name)
    if not os.path.samestat(before_remove, current):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_staging.identity",
                    "held snapshot staging authority changed before cleanup",
                ),
            )
        )
    os.rmdir(name, dir_fd=authority_fd)
    if any(
        os.path.samestat(_lstat_at(authority_fd, candidate_name), current)
        for candidate_name in os.listdir(authority_fd)
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.snapshot_staging.identity",
                    "held snapshot staging authority remains linked after cleanup",
                ),
            )
        )
    os.fsync(authority_fd)


def _remove_directory_contents_at(directory_fd: int) -> None:
    os.fchmod(directory_fd, 0o700)
    for name in os.listdir(directory_fd):
        observed = _lstat_at(directory_fd, name)
        if stat.S_ISDIR(observed.st_mode):
            child_fd = _open_directory_at(directory_fd, name)
            try:
                opened = os.fstat(child_fd)
                if not os.path.samestat(observed, opened):
                    raise ProviderIsolationEnvironmentError(
                        (
                            _issue(
                                "$.snapshot_staging.identity",
                                "snapshot staging descendant changed during cleanup",
                            ),
                        )
                    )
                _remove_directory_contents_at(child_fd)
            finally:
                os.close(child_fd)
            linked = _lstat_at(directory_fd, name)
            if not os.path.samestat(observed, linked):
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            "$.snapshot_staging.identity",
                            "snapshot staging descendant changed before cleanup",
                        ),
                    )
                )
            os.rmdir(name, dir_fd=directory_fd)
            continue
        os.unlink(name, dir_fd=directory_fd)


def _remove_private_staging(path: Path) -> None:
    for root, directories, files in os.walk(path, topdown=False, followlinks=False):
        root_path = Path(root)
        for name in files:
            candidate = root_path / name
            if not candidate.is_symlink():
                try:
                    candidate.chmod(0o600)
                except OSError:
                    pass
        for name in directories:
            candidate = root_path / name
            if not candidate.is_symlink():
                try:
                    candidate.chmod(0o700)
                except OSError:
                    pass
        try:
            root_path.chmod(0o700)
        except OSError:
            pass
    shutil.rmtree(path)


def require_disjoint_environment_authorities(
    source_root: str | os.PathLike[str],
    other_authorities: Sequence[str | os.PathLike[str]],
) -> None:
    """Reject canonical containment in either direction for every authority."""

    source = _canonical_authority_path(source_root)
    for index, other_root in enumerate(other_authorities):
        other = _canonical_authority_path(other_root)
        if _path_contains(source, other) or _path_contains(other, source):
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        f"$.authorities[{index}]",
                        "environment source and denied authority overlap",
                    ),
                )
            )


def _require_opened_source_mount_identity(
    fd: int,
    *,
    entry_mount_id: int,
    root_mount_id: int,
    issue_path: str,
    phase: str,
) -> None:
    try:
        opened_mount_id = _statx_mount_id(fd)
    except MountIdentityUnavailable as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.mount_id",
                    f"descriptor-bound mount identity is unavailable during {phase}",
                ),
            )
        ) from exc
    if (
        opened_mount_id != entry_mount_id
        or opened_mount_id != root_mount_id
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.mount_id",
                    f"source mount identity changed during {phase}",
                ),
            )
        )


def _scan_directory(
    directory_fd: int,
    *,
    parent_path: str,
    root_mount_id: int,
    scanned: dict[str, _ScannedEntry],
    finalized_snapshot: bool,
) -> None:
    names = os.listdir(directory_fd)
    for name in names:
        _require_source_name(name)
    names.sort(key=lambda value: value.encode("utf-8"))

    for name in names:
        relpath = name if parent_path == "." else f"{parent_path}/{name}"
        issue_base = f"$.entries[{relpath}]"
        before = _lstat_at(directory_fd, name)
        _require_source_entry(before, path=relpath, issue_path=issue_base)
        if finalized_snapshot:
            _require_finalized_snapshot_metadata(
                before,
                issue_path=issue_base,
            )
        try:
            mount_id = _statx_mount_id(directory_fd, name)
        except MountIdentityUnavailable as exc:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        f"{issue_base}.mount_id",
                        "descriptor-bound mount identity is unavailable",
                    ),
                )
            ) from exc
        if mount_id != root_mount_id:
            raise ProviderIsolationEnvironmentError(
                (
                    _issue(
                        f"{issue_base}.mount_id",
                        "nested mount identity differs from environment root",
                    ),
                )
            )

        mode = before.st_mode
        if stat.S_ISDIR(mode):
            child_fd = _open_directory_at(directory_fd, name)
            try:
                opened = os.fstat(child_fd)
                _require_same_source_identity(before, opened, issue_path=issue_base)
                if finalized_snapshot:
                    _require_snapshot_noatime_flag(
                        child_fd,
                        issue_path=issue_base,
                    )
                _require_opened_source_mount_identity(
                    child_fd,
                    entry_mount_id=mount_id,
                    root_mount_id=root_mount_id,
                    issue_path=issue_base,
                    phase="admission",
                )
                _require_no_xattrs_fd(
                    child_fd,
                    issue_path=f"{issue_base}.xattrs",
                )
                entry = ProviderEnvironmentManifestEntry(
                    path=relpath,
                    kind="directory",
                    mode=_normalized_mode(mode),
                    uid=0,
                    gid=0,
                    atime_ns=0,
                    mtime_ns=0,
                )
                scanned[relpath] = _ScannedEntry(entry, before, mount_id)
                _scan_directory(
                    child_fd,
                    parent_path=relpath,
                    root_mount_id=root_mount_id,
                    scanned=scanned,
                    finalized_snapshot=finalized_snapshot,
                )
                after_fd = os.fstat(child_fd)
            finally:
                os.close(child_fd)
            after_path = _lstat_at(directory_fd, name)
            _require_same_source_identity(before, after_fd, issue_path=issue_base)
            _require_same_source_identity(before, after_path, issue_path=issue_base)
            continue

        if stat.S_ISREG(mode):
            file_fd = _open_regular_at(directory_fd, name)
            try:
                opened = os.fstat(file_fd)
                _require_same_source_identity(before, opened, issue_path=issue_base)
                if finalized_snapshot:
                    _require_snapshot_noatime_flag(
                        file_fd,
                        issue_path=issue_base,
                    )
                _require_opened_source_mount_identity(
                    file_fd,
                    entry_mount_id=mount_id,
                    root_mount_id=root_mount_id,
                    issue_path=issue_base,
                    phase="admission",
                )
                _require_no_xattrs_fd(
                    file_fd,
                    issue_path=f"{issue_base}.xattrs",
                )
                size, content_digest = _hash_regular_file(file_fd)
                after_fd = os.fstat(file_fd)
            finally:
                os.close(file_fd)
            after_path = _lstat_at(directory_fd, name)
            _require_same_source_identity(before, after_fd, issue_path=issue_base)
            _require_same_source_identity(before, after_path, issue_path=issue_base)
            if size != before.st_size:
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"{issue_base}.size",
                            "source file size changed during admission",
                        ),
                    )
                )
            entry = ProviderEnvironmentManifestEntry(
                path=relpath,
                kind="regular_file",
                mode=_normalized_mode(mode),
                uid=0,
                gid=0,
                atime_ns=0,
                mtime_ns=0,
                size=size,
                digest=content_digest,
            )
            scanned[relpath] = _ScannedEntry(entry, before, mount_id)
            continue

        if stat.S_ISLNK(mode):
            _require_no_xattrs_at(
                directory_fd,
                name,
                issue_path=f"{issue_base}.xattrs",
            )
            link_text = os.readlink(name, dir_fd=directory_fd)
            link_issues = _strict_nfc_text_issues(
                link_text,
                f"{issue_base}.link_text",
                label="symlink text",
            )
            if link_issues:
                raise ProviderIsolationEnvironmentError(link_issues)
            after_path = _lstat_at(directory_fd, name)
            _require_same_source_identity(before, after_path, issue_path=issue_base)
            entry = ProviderEnvironmentManifestEntry(
                path=relpath,
                kind="symlink",
                mode=0o777,
                uid=0,
                gid=0,
                atime_ns=0,
                mtime_ns=0,
                link_text=link_text,
            )
            scanned[relpath] = _ScannedEntry(entry, before, mount_id)
            continue

        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_base}.kind",
                    "source entry type is forbidden",
                ),
            )
        )


def _packaged_launch_shim_bytes() -> bytes:
    return (
        resources.files("orchestrator.providers")
        .joinpath("provider_launch_shim.py")
        .read_bytes()
    )


def _inject_structural_mountpoints(
    scanned: dict[str, _ScannedEntry],
) -> None:
    root = scanned["."]
    for relpath in _STRUCTURAL_MOUNTPOINT_RELPATHS:
        existing = scanned.get(relpath)
        if existing is not None:
            if existing.entry.kind != "directory":
                raise ProviderIsolationEnvironmentError(
                    (
                        _issue(
                            f"$.entries[{relpath}].kind",
                            "reserved structural mountpoint must be a directory",
                        ),
                    )
                )
            continue
        scanned[relpath] = _ScannedEntry(
            ProviderEnvironmentManifestEntry(
                path=relpath,
                kind="directory",
                mode=0o555,
                uid=0,
                gid=0,
                atime_ns=0,
                mtime_ns=0,
            ),
            root.source_stat,
            root.mount_id,
        )


def _inject_launch_shim(
    scanned: dict[str, _ScannedEntry],
    provider_prefix: str,
) -> None:
    prefix_relpath = provider_prefix.lstrip("/")
    prefix = scanned.get(prefix_relpath)
    if prefix is None or prefix.entry.kind != "directory":
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    "$.provider_prefix",
                    "provider prefix is not a source directory",
                ),
            )
        )
    libexec_path = f"{prefix_relpath}/libexec"
    shim_path = f"{libexec_path}/provider-launch-shim-v1.py"
    if shim_path in scanned:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"$.entries[{shim_path}]",
                    "source collides with the reserved launch shim",
                ),
            )
        )

    if libexec_path not in scanned:
        scanned[libexec_path] = _ScannedEntry(
            ProviderEnvironmentManifestEntry(
                path=libexec_path,
                kind="directory",
                mode=0o555,
                uid=0,
                gid=0,
                atime_ns=0,
                mtime_ns=0,
            ),
            prefix.source_stat,
            prefix.mount_id,
        )
    elif scanned[libexec_path].entry.kind != "directory":
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"$.entries[{libexec_path}].kind",
                    "reserved launch-shim parent must be a directory",
                ),
            )
        )

    shim_bytes = _packaged_launch_shim_bytes()
    scanned[shim_path] = _ScannedEntry(
        ProviderEnvironmentManifestEntry(
            path=shim_path,
            kind="regular_file",
            mode=0o444,
            uid=0,
            gid=0,
            atime_ns=0,
            mtime_ns=0,
            size=len(shim_bytes),
            digest=_digest(shim_bytes),
        ),
        prefix.source_stat,
        prefix.mount_id,
    )


def _require_complete_hardlink_accounting(
    scanned: Mapping[str, _ScannedEntry],
) -> None:
    groups: dict[tuple[int, int], list[_ScannedEntry]] = {}
    for item in scanned.values():
        if item.entry.kind != "regular_file":
            continue
        key = (item.source_stat.st_dev, item.source_stat.st_ino)
        groups.setdefault(key, []).append(item)
    for items in groups.values():
        expected = items[0].source_stat.st_nlink
        if expected == len(items):
            continue
        first = min(items, key=lambda item: item.entry.path.encode("utf-8"))
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"$.entries[{first.entry.path}].hardlinks",
                    "source inode link count is not fully accounted within the rootfs",
                ),
            )
        )


def _require_safe_symlink_graph(
    scanned: Mapping[str, _ScannedEntry],
) -> None:
    for path, item in scanned.items():
        if item.entry.kind != "symlink":
            continue
        _resolve_symlink(path, scanned, origin_path=path, seen=set())


def _resolve_symlink(
    path: str,
    scanned: Mapping[str, _ScannedEntry],
    *,
    origin_path: str,
    seen: set[str],
) -> str:
    if path in seen:
        raise _unsafe_symlink(origin_path, "symlink graph is cyclic")
    item = scanned.get(path)
    if item is None:
        raise _unsafe_symlink(origin_path, "symlink target is broken")
    if item.entry.kind != "symlink":
        return path
    seen.add(path)
    target = item.entry.link_text
    assert target is not None
    if target.startswith("/"):
        raise _unsafe_symlink(origin_path, "absolute symlink targets are forbidden")
    parent = posixpath.dirname(path)
    resolved = posixpath.normpath(posixpath.join(parent, target))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        raise _unsafe_symlink(origin_path, "symlink target escapes the rootfs")
    return _resolve_symlink(
        resolved,
        scanned,
        origin_path=origin_path,
        seen=seen,
    )


def _unsafe_symlink(path: str, message: str) -> ProviderIsolationEnvironmentError:
    return ProviderIsolationEnvironmentError(
        (_issue(f"$.entries[{path}].link_text", message),)
    )


def _require_source_name(name: str) -> None:
    issues = _strict_nfc_text_issues(name, "$.entries", label="entry name")
    if issues:
        raise ProviderIsolationEnvironmentError(issues)
    if not name or name in {".", ".."} or "/" in name or "\x00" in name:
        raise ProviderIsolationEnvironmentError(
            (_issue("$.entries", "source entry name is invalid"),)
        )


def _require_source_entry(
    value: os.stat_result,
    *,
    path: str,
    issue_path: str,
    required_kind: str | None = None,
) -> None:
    if value.st_uid != os.geteuid():
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.owner",
                    "source entry must be controller-owned",
                ),
            )
        )
    if (
        not stat.S_ISLNK(value.st_mode)
        and stat.S_IMODE(value.st_mode) & _SOURCE_FORBIDDEN_WRITE_BITS
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.mode",
                    "source entry must not be group/world writable",
                ),
            )
        )
    if required_kind == "directory" and not stat.S_ISDIR(value.st_mode):
        raise ProviderIsolationEnvironmentError(
            (_issue(f"{issue_path}.kind", "source root must be a real directory"),)
        )
    if required_kind is None and not (
        stat.S_ISDIR(value.st_mode)
        or stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
    ):
        raise ProviderIsolationEnvironmentError(
            (_issue(f"{issue_path}.kind", "source entry type is forbidden"),)
        )


def _require_finalized_snapshot_metadata(
    value: os.stat_result,
    *,
    issue_path: str,
) -> None:
    if value.st_uid != os.geteuid() or value.st_gid != os.getegid():
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.owner",
                    "snapshot entry is not controller-owned",
                ),
            )
        )
    if value.st_atime_ns != 0 or value.st_mtime_ns != 0:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.timestamps",
                    "snapshot entry timestamps are not fixed at zero",
                ),
            )
        )
    mode = stat.S_IMODE(value.st_mode)
    if stat.S_ISLNK(value.st_mode):
        if mode != 0o777:
            raise ProviderIsolationEnvironmentError(
                (_issue(f"{issue_path}.mode", "snapshot symlink mode is not 0777"),)
            )
    elif mode & 0o222:
        raise ProviderIsolationEnvironmentError(
            (_issue(f"{issue_path}.mode", "snapshot entry remains writable"),)
        )
    if stat.S_ISREG(value.st_mode) and value.st_nlink != 1:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.hardlinks",
                    "snapshot regular file link count must equal one",
                ),
            )
        )


def _get_inode_flags(fd: int) -> int:
    value = array.array("L", [0])
    fcntl.ioctl(fd, _FS_IOC_GETFLAGS, value, True)
    return int(value[0])


def _set_inode_flags(fd: int, flags: int) -> None:
    value = array.array("L", [flags])
    fcntl.ioctl(fd, _FS_IOC_SETFLAGS, value, True)


def _apply_snapshot_noatime_flag(fd: int, *, issue_path: str) -> int:
    try:
        current = _get_inode_flags(fd)
        expected = current | _FS_NOATIME_FL
        _set_inode_flags(fd, expected)
        observed = _get_inode_flags(fd)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "fixed no-atime enforcement is unavailable",
                    code=ENVIRONMENT_BACKEND_UNAVAILABLE_CODE,
                ),
            )
        ) from exc
    if observed != expected:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "fixed no-atime enforcement did not preserve inode flags",
                    code=ENVIRONMENT_BACKEND_UNAVAILABLE_CODE,
                ),
            )
        )
    return expected


def _require_snapshot_inode_flags(
    fd: int,
    *,
    issue_path: str,
    expected_flags: int,
) -> None:
    try:
        observed = _get_inode_flags(fd)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "fixed inode flags cannot be verified after timestamp normalization",
                    code=ENVIRONMENT_BACKEND_UNAVAILABLE_CODE,
                ),
            )
        ) from exc
    if observed != expected_flags:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "timestamp normalization did not preserve fixed inode flags",
                    code=ENVIRONMENT_BACKEND_UNAVAILABLE_CODE,
                ),
            )
        )


def _require_snapshot_noatime_flag(
    fd: int,
    *,
    issue_path: str,
) -> None:
    try:
        observed = _get_inode_flags(fd)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "fixed no-atime enforcement cannot be verified",
                    code=ENVIRONMENT_BACKEND_UNAVAILABLE_CODE,
                ),
            )
        ) from exc
    if not observed & _FS_NOATIME_FL:
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.inode_flags",
                    "snapshot entry is missing fixed no-atime enforcement",
                ),
            )
        )


def _require_same_source_identity(
    before: os.stat_result,
    after: os.stat_result,
    *,
    issue_path: str,
) -> None:
    if any(
        getattr(before, field) != getattr(after, field)
        for field in _SOURCE_IDENTITY_FIELDS
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.identity",
                    "source entry changed during admission",
                ),
            )
        )


def _require_same_pinned_edge_identity(
    before: os.stat_result,
    after: os.stat_result,
    *,
    issue_path: str,
    changed_message: str = "snapshot authority edge changed during verification",
) -> None:
    if any(
        getattr(before, field) != getattr(after, field)
        for field in ("st_mode", "st_ino", "st_dev", "st_uid", "st_gid")
    ):
        raise ProviderIsolationEnvironmentError(
            (
                _issue(
                    f"{issue_path}.identity",
                    changed_message,
                ),
            )
        )


def _require_same_held_directory_identity(
    before: os.stat_result,
    after: os.stat_result,
    *,
    issue_path: str,
    message: str,
) -> None:
    if (
        not stat.S_ISDIR(before.st_mode)
        or not stat.S_ISDIR(after.st_mode)
        or any(
            getattr(before, field) != getattr(after, field)
            for field in ("st_ino", "st_dev", "st_uid", "st_gid")
        )
    ):
        raise ProviderIsolationEnvironmentError(
            (_issue(f"{issue_path}.identity", message),)
        )


def _normalized_mode(mode: int) -> int:
    return stat.S_IMODE(mode) & ~0o222


def _lstat_root(path: str | os.PathLike[str]) -> os.stat_result:
    return os.stat(path, follow_symlinks=False)


def _lstat_at(directory_fd: int, name: str) -> os.stat_result:
    return os.stat(name, dir_fd=directory_fd, follow_symlinks=False)


def _open_directory(path: str | os.PathLike[str]) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    return _open_noatime(path, flags)


def _open_directory_at(directory_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    return _open_noatime(name, flags, dir_fd=directory_fd)


def _open_regular_at(directory_fd: int, name: str) -> int:
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
    return _open_noatime(name, flags, dir_fd=directory_fd)


def _open_noatime(
    path: str | os.PathLike[str],
    flags: int,
    *,
    dir_fd: int | None = None,
) -> int:
    noatime = getattr(os, "O_NOATIME", 0)
    try:
        return os.open(path, flags | noatime, dir_fd=dir_fd)
    except OSError as exc:
        if not noatime or exc.errno not in {errno.EPERM, errno.EACCES, errno.EINVAL}:
            raise
        return os.open(path, flags, dir_fd=dir_fd)


def _hash_regular_file(fd: int) -> tuple[int, str]:
    os.lseek(fd, 0, os.SEEK_SET)
    digest = sha256()
    size = 0
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        size += len(block)
        digest.update(block)
    return size, f"sha256:{digest.hexdigest()}"


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            return b"".join(chunks)
        chunks.append(block)


def _require_no_xattrs_fd(fd: int, *, issue_path: str) -> None:
    try:
        names = os.listxattr(fd)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "source xattrs could not be inspected"),)
        ) from exc
    if names:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "source entries with xattrs are forbidden"),)
        )


def _require_no_xattrs_at(
    directory_fd: int,
    name: str,
    *,
    issue_path: str,
) -> None:
    proc_path = f"/proc/self/fd/{directory_fd}/{name}"
    try:
        names = os.listxattr(proc_path, follow_symlinks=False)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "source xattrs could not be inspected"),)
        ) from exc
    if names:
        raise ProviderIsolationEnvironmentError(
            (_issue(issue_path, "source entries with xattrs are forbidden"),)
        )


def _statx_mount_id(directory_fd: int, name: str | None = None) -> int:
    """Return Linux ``STATX_MNT_ID`` for a pinned descriptor-relative entry."""

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
            raise MountIdentityUnavailable("entry name is not strict UTF-8") from exc
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


def _canonical_authority_path(path: str | os.PathLike[str]) -> Path:
    value = Path(path)
    if not value.is_absolute():
        raise ProviderIsolationEnvironmentError(
            (_issue("$.authorities", "authority paths must be absolute"),)
        )
    try:
        return value.resolve(strict=True)
    except OSError as exc:
        raise ProviderIsolationEnvironmentError(
            (_issue("$.authorities", "authority path cannot be resolved safely"),)
        ) from exc


def _path_contains(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents


def _closed_field_issues(
    document: Mapping[str, Any],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    top_fields = {"schema_version", "provider_prefix", "entries"}
    for name in sorted(set(document) - top_fields):
        issues.append(
            _issue(_append_json_path("$", str(name)), "unknown field is not allowed")
        )
    entries = document.get("entries")
    if not isinstance(entries, list):
        return issues
    for index, row in enumerate(entries):
        if not isinstance(row, Mapping):
            continue
        kind = row.get("kind")
        allowed = _KIND_FIELDS.get(kind, _COMMON_ENTRY_FIELDS)
        for name in sorted(set(row) - allowed):
            issues.append(
                _issue(
                    _append_json_path(f"$.entries[{index}]", str(name)),
                    "unknown field is not allowed",
                )
            )
    return issues


def _semantic_manifest_issues(
    document: Mapping[str, Any],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    prefix = document.get("provider_prefix")
    if isinstance(prefix, str):
        issues.extend(_absolute_prefix_issues(prefix))

    entries = document.get("entries")
    if not isinstance(entries, list):
        return issues

    rows_by_path: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for index, value in enumerate(entries):
        if not isinstance(value, Mapping):
            continue
        path = value.get("path")
        if isinstance(path, str):
            path_issues = _manifest_path_issues(path, f"$.entries[{index}].path")
            issues.extend(path_issues)
            if not path_issues:
                if path in rows_by_path:
                    issues.append(
                        _issue(
                            f"$.entries[{index}].path",
                            "manifest entry path must be unique",
                        )
                    )
                else:
                    rows_by_path[path] = (index, value)

        kind = value.get("kind")
        mode = value.get("mode")
        if isinstance(mode, int) and not isinstance(mode, bool):
            if kind == "symlink":
                if mode != 0o777:
                    issues.append(
                        _issue(
                            f"$.entries[{index}].mode",
                            "symlink mode must equal Linux 0777",
                        )
                    )
            elif kind in {"directory", "regular_file"} and (
                mode < 0 or mode > 0o777 or mode & 0o222
            ):
                issues.append(
                    _issue(
                        f"$.entries[{index}].mode",
                        "destination mode must contain no write or special bits",
                    )
                )

        link_text = value.get("link_text")
        if kind == "symlink" and isinstance(link_text, str):
            issues.extend(
                _strict_nfc_text_issues(
                    link_text,
                    f"$.entries[{index}].link_text",
                    label="symlink text",
                )
            )

    root = rows_by_path.get(".")
    if root is None:
        issues.append(_issue("$.entries", "manifest must contain the root '.' row"))
    elif root[1].get("kind") != "directory":
        issues.append(
            _issue(
                f"$.entries[{root[0]}].kind",
                "manifest root row must be a directory",
            )
        )

    for path, (index, _row) in rows_by_path.items():
        if path == ".":
            continue
        parent = posixpath.dirname(path) or "."
        while True:
            parent_row = rows_by_path.get(parent)
            if parent_row is None:
                issues.append(
                    _issue(
                        f"$.entries[{index}].path",
                        f"manifest ancestor {parent!r} is missing",
                    )
                )
                break
            if parent_row[1].get("kind") != "directory":
                issues.append(
                    _issue(
                        f"$.entries[{index}].path",
                        f"manifest ancestor {parent!r} is not a directory",
                    )
                )
                break
            if parent == ".":
                break
            parent = posixpath.dirname(parent) or "."
    issues.extend(_manifest_symlink_graph_issues(rows_by_path))
    return issues


def _manifest_symlink_graph_issues(
    rows_by_path: Mapping[str, tuple[int, Mapping[str, Any]]],
) -> list[ProviderIsolationIssue]:
    issues: list[ProviderIsolationIssue] = []
    for path, (index, row) in sorted(
        rows_by_path.items(),
        key=lambda item: item[0].encode("utf-8"),
    ):
        if row.get("kind") != "symlink":
            continue
        message = _manifest_symlink_resolution_issue(
            path,
            rows_by_path,
            seen=set(),
        )
        if message is not None:
            issues.append(_issue(f"$.entries[{index}].link_text", message))
    return issues


def _manifest_symlink_resolution_issue(
    path: str,
    rows_by_path: Mapping[str, tuple[int, Mapping[str, Any]]],
    *,
    seen: set[str],
) -> str | None:
    if path in seen:
        return "symlink graph is cyclic"
    item = rows_by_path.get(path)
    if item is None:
        return "symlink target is broken"
    row = item[1]
    if row.get("kind") != "symlink":
        return None
    target = row.get("link_text")
    if not isinstance(target, str):
        return None
    if target.startswith("/"):
        return "absolute symlink targets are forbidden"
    parent = posixpath.dirname(path)
    resolved = posixpath.normpath(posixpath.join(parent, target))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        return "symlink target escapes the rootfs"
    return _manifest_symlink_resolution_issue(
        resolved,
        rows_by_path,
        seen=seen | {path},
    )


def _absolute_prefix_issues(value: str) -> list[ProviderIsolationIssue]:
    path = "$.provider_prefix"
    issues = _strict_nfc_text_issues(value, path, label="provider prefix")
    if issues:
        return issues
    if (
        not value.startswith("/")
        or value == "/"
        or value.startswith("//")
        or "\x00" in value
        or posixpath.normpath(value) != value
    ):
        return [_issue(path, "provider prefix must be canonical and absolute")]
    return []


def _manifest_path_issues(
    value: str,
    path: str,
) -> list[ProviderIsolationIssue]:
    issues = _strict_nfc_text_issues(value, path, label="manifest path")
    if issues:
        return issues
    if "\x00" in value:
        return [_issue(path, "manifest path must not contain NUL")]
    if value == ".":
        return []
    if (
        not value
        or value.startswith("/")
        or value == ".."
        or value.startswith("../")
        or value.startswith("./")
        or posixpath.normpath(value) != value
    ):
        return [_issue(path, "manifest path must be a normalized POSIX relative path")]
    return []


def _strict_nfc_text_issues(
    value: str,
    path: str,
    *,
    label: str,
) -> list[ProviderIsolationIssue]:
    try:
        value.encode("utf-8", errors="strict")
    except UnicodeEncodeError:
        return [_issue(path, f"{label} must be strict UTF-8")]
    if unicodedata.normalize("NFC", value) != value:
        return [_issue(path, f"{label} must already be Unicode NFC")]
    return []


def _float_issues(value: object, path: str) -> list[ProviderIsolationIssue]:
    if isinstance(value, float):
        return [_issue(path, "environment manifest JSON forbids floating-point values")]
    if isinstance(value, Mapping):
        issues: list[ProviderIsolationIssue] = []
        for key, item in value.items():
            issues.extend(_float_issues(item, _append_json_path(path, str(key))))
        return issues
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        issues = []
        for index, item in enumerate(value):
            issues.extend(_float_issues(item, f"{path}[{index}]"))
        return issues
    return []


def _deduplicate_issues(
    issues: Sequence[ProviderIsolationIssue],
) -> tuple[ProviderIsolationIssue, ...]:
    grouped: dict[tuple[str, str], set[str]] = {}
    for issue in issues:
        grouped.setdefault((issue.code, issue.path), set()).add(issue.message)
    return tuple(
        sorted(
            (
                ProviderIsolationIssue(
                    code=code,
                    path=path,
                    message="; ".join(sorted(messages)),
                )
                for (code, path), messages in grouped.items()
            ),
            key=lambda issue: (issue.path, issue.message, issue.code),
        )
    )


def _issue(
    path: str,
    message: str,
    *,
    code: str = ENVIRONMENT_INVALID_CODE,
) -> ProviderIsolationIssue:
    return ProviderIsolationIssue(code=code, path=path, message=message)


def _append_json_path(parent: str, name: str) -> str:
    if _JSON_NAME_PATTERN.fullmatch(name):
        return f"{parent}.{name}"
    return f"{parent}[{json.dumps(name, ensure_ascii=True)}]"


def _digest(value: bytes) -> str:
    return f"sha256:{sha256(value).hexdigest()}"


__all__ = [
    "BOOTSTRAP_CLOSURE_SCHEMA_VERSION",
    "BOOTSTRAP_PROFILE",
    "ENVIRONMENT_BACKEND_UNAVAILABLE_CODE",
    "ENVIRONMENT_INVALID_CODE",
    "ENVIRONMENT_MISMATCH_CODE",
    "ENVIRONMENT_SCHEMA_RESOURCE",
    "ENVIRONMENT_SCHEMA_VERSION",
    "MountIdentityUnavailable",
    "ParsedElf",
    "ProviderBootstrapClosure",
    "ProviderEnvironmentManifest",
    "ProviderEnvironmentManifestEntry",
    "ProviderEnvironmentSnapshot",
    "ProviderIsolationEnvironmentError",
    "ProviderRuntimeClosure",
    "ProviderRuntimeClosureEntry",
    "assemble_provider_environment_snapshot",
    "build_provider_environment_manifest",
    "discover_provider_runtime_closure",
    "expand_loader_search_path",
    "load_provider_environment_snapshot",
    "load_provider_environment_snapshot_for_launch",
    "load_provider_environment_manifest",
    "require_disjoint_environment_authorities",
    "validate_fixed_provider_bootstrap_from_fd",
    "validate_provider_environment_manifest",
    "verify_provider_runtime_closure",
    "verify_provider_environment_snapshot",
]
