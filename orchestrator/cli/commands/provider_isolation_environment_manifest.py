"""Publish a prospective provider-isolation environment manifest."""

from __future__ import annotations

import ctypes
from dataclasses import dataclass
import errno
import os
import stat
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from orchestrator.providers.isolation_environment import (
    ProviderIsolationEnvironmentError,
    _build_provider_environment_manifest_from_fd,
    _open_source_binding,
    validate_fixed_provider_bootstrap_from_fd,
)


_INVALID_DIAGNOSTIC = "provider_isolation_environment_invalid"
_AT_EMPTY_PATH = 0x1000


class _ManifestPublicationError(Exception):
    """Internal fail-closed publication rejection."""


@dataclass(frozen=True, slots=True)
class _OutputAuthorityEdge:
    parent_fd: int
    child_fd: int
    name: str
    opened_stat: os.stat_result


@dataclass(slots=True)
class _PinnedOutputAuthority:
    requested_parent: Path
    parent_fd: int
    parent_stat: os.stat_result
    root_fd: int
    root_stat: os.stat_result
    owned_fds: list[int]
    edges: tuple[_OutputAuthorityEdge, ...]

    def revalidate(self) -> None:
        root_opened = os.fstat(self.root_fd)
        if not _same_identity(self.root_stat, root_opened, root_opened):
            raise _ManifestPublicationError
        _require_trusted_output_ancestor(root_opened)

        for edge in self.edges:
            opened = os.fstat(edge.child_fd)
            linked = os.stat(
                edge.name,
                dir_fd=edge.parent_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(linked.st_mode) or not _same_identity(
                edge.opened_stat,
                opened,
                linked,
            ):
                raise _ManifestPublicationError
            if edge.child_fd != self.parent_fd:
                _require_trusted_output_ancestor(opened)

        _require_output_parent_binding(
            self.requested_parent,
            self.parent_fd,
            self.parent_stat,
        )

    def close(self) -> None:
        for fd in reversed(self.owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        self.owned_fds.clear()
        self.parent_fd = -1
        self.root_fd = -1


def provider_isolation_environment_manifest_workflow(args: Any) -> int:
    """Build and atomically publish one prospective manifest."""

    try:
        digest = _publish_manifest(
            root=args.root,
            provider_prefix=args.provider_prefix,
            output=args.output,
        )
    except (
        ProviderIsolationEnvironmentError,
        _ManifestPublicationError,
        OSError,
        TypeError,
        ValueError,
    ):
        print(_INVALID_DIAGNOSTIC, file=sys.stderr)
        return 2

    print(digest)
    return 0


def _publish_manifest(*, root: str, provider_prefix: str, output: str) -> str:
    if not all(
        isinstance(value, str) and os.path.isabs(value)
        for value in (root, provider_prefix, output)
    ):
        raise _ManifestPublicationError

    output_path = Path(output)
    output_name = output_path.name
    output_parent = output_path.parent
    if not output_name or output_name in {".", ".."}:
        raise _ManifestPublicationError

    source = _open_source_binding(root)
    output_authority: _PinnedOutputAuthority | None = None
    try:
        source_path = Path(f"/proc/self/fd/{source.root_fd}").resolve(strict=True)
        if source_path != Path(root):
            raise _ManifestPublicationError

        output_authority = _open_output_authority(output_parent)
        parent_fd = output_authority.parent_fd
        canonical_parent = Path(f"/proc/self/fd/{parent_fd}").resolve(strict=True)
        _require_absent(parent_fd, output_name)

        manifest = _build_manifest_from_pinned_source(
            source.root_fd,
            provider_prefix,
        )
        validate_fixed_provider_bootstrap_from_fd(
            source.root_fd,
            manifest,
            provider_prefix,
            shim_materialization="virtual_injected",
        )

        def revalidate_authorities() -> None:
            source.revalidate_edges()
            if (
                Path(f"/proc/self/fd/{source.root_fd}").resolve(strict=True)
                != source_path
            ):
                raise _ManifestPublicationError
            output_authority.revalidate()

        revalidate_authorities()
        if _paths_overlap(source_path, canonical_parent):
            raise _ManifestPublicationError
        if any(
            PurePosixPath(entry.path).name == output_name
            for entry in manifest.entries
        ):
            raise _ManifestPublicationError

        _publish_bytes(
            parent_fd,
            output_name,
            manifest.canonical_json,
            authority_check=revalidate_authorities,
        )
        return manifest.digest
    finally:
        if output_authority is not None:
            output_authority.close()
        source.close()


def _build_manifest_from_pinned_source(
    source_root_fd: int,
    provider_prefix: str,
):
    return _build_provider_environment_manifest_from_fd(
        source_root_fd,
        provider_prefix,
        inject_launch_shim=True,
        finalized_snapshot=False,
    )


def _same_identity(
    before: os.stat_result,
    opened: os.stat_result,
    after: os.stat_result,
) -> bool:
    expected = (before.st_dev, before.st_ino, before.st_mode, before.st_uid)
    return expected == (
        opened.st_dev,
        opened.st_ino,
        opened.st_mode,
        opened.st_uid,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_mode,
        after.st_uid,
    )


def _open_output_authority(requested_parent: Path) -> _PinnedOutputAuthority:
    owned_fds: list[int] = []
    edges: list[_OutputAuthorityEdge] = []
    try:
        root_fd = os.open(
            "/",
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
        )
        owned_fds.append(root_fd)
        root_stat = os.fstat(root_fd)
        _require_trusted_output_ancestor(root_stat)

        current_fd = root_fd
        for name in requested_parent.parts[1:]:
            before = os.stat(
                name,
                dir_fd=current_fd,
                follow_symlinks=False,
            )
            if not stat.S_ISDIR(before.st_mode):
                raise _ManifestPublicationError
            child_fd = os.open(
                name,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=current_fd,
            )
            owned_fds.append(child_fd)
            opened = os.fstat(child_fd)
            if not _same_identity(before, opened, before):
                raise _ManifestPublicationError
            edges.append(
                _OutputAuthorityEdge(
                    parent_fd=current_fd,
                    child_fd=child_fd,
                    name=name,
                    opened_stat=opened,
                )
            )
            current_fd = child_fd

        parent_stat = os.fstat(current_fd)
        authority = _PinnedOutputAuthority(
            requested_parent=requested_parent,
            parent_fd=current_fd,
            parent_stat=parent_stat,
            root_fd=root_fd,
            root_stat=root_stat,
            owned_fds=owned_fds,
            edges=tuple(edges),
        )
        for edge in authority.edges:
            if edge.child_fd != authority.parent_fd:
                _require_trusted_output_ancestor(edge.opened_stat)
        authority.revalidate()
        return authority
    except BaseException:
        for fd in reversed(owned_fds):
            try:
                os.close(fd)
            except OSError:
                pass
        raise


def _require_trusted_output_ancestor(value: os.stat_result) -> None:
    if not stat.S_ISDIR(value.st_mode):
        raise _ManifestPublicationError
    if value.st_uid not in {0, os.geteuid()}:
        raise _ManifestPublicationError
    writable_by_other = stat.S_IMODE(value.st_mode) & 0o022
    root_owned_sticky = value.st_uid == 0 and value.st_mode & stat.S_ISVTX
    if writable_by_other and not root_owned_sticky:
        raise _ManifestPublicationError


def _require_output_parent_binding(
    requested_path: Path,
    parent_fd: int,
    expected: os.stat_result,
) -> None:
    opened = os.fstat(parent_fd)
    linked = os.lstat(requested_path)
    if not _same_identity(expected, opened, linked):
        raise _ManifestPublicationError
    if opened.st_uid != os.geteuid():
        raise _ManifestPublicationError
    if stat.S_IMODE(opened.st_mode) != 0o700:
        raise _ManifestPublicationError
    if os.listxattr(parent_fd):
        raise _ManifestPublicationError
    if Path(f"/proc/self/fd/{parent_fd}").resolve(strict=True) != requested_path:
        raise _ManifestPublicationError


def _paths_overlap(first: Path, second: Path) -> bool:
    return (
        first == second
        or first in second.parents
        or second in first.parents
    )


def _require_absent(parent_fd: int, name: str) -> None:
    try:
        os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    raise _ManifestPublicationError


def _publish_bytes(
    parent_fd: int,
    output_name: str,
    payload: bytes,
    *,
    authority_check: Callable[[], None],
) -> None:
    manifest_fd: int | None = None
    try:
        authority_check()
        if not hasattr(os, "O_TMPFILE"):
            raise _ManifestPublicationError
        manifest_fd = os.open(
            ".",
            os.O_RDWR | os.O_TMPFILE | os.O_CLOEXEC,
            0o600,
            dir_fd=parent_fd,
        )
        os.fchmod(manifest_fd, 0o600)
        _require_private_manifest_fd(
            manifest_fd,
            expected_payload=b"",
            expected_nlink=0,
        )
        _write_all(manifest_fd, payload)
        os.fsync(manifest_fd)
        _require_private_manifest_fd(
            manifest_fd,
            expected_payload=payload,
            expected_nlink=0,
        )

        authority_check()
        _link_unnamed_noreplace(manifest_fd, parent_fd, output_name)
        _require_manifest_name_binding(parent_fd, output_name, manifest_fd)
        _require_private_manifest_fd(
            manifest_fd,
            expected_payload=payload,
            expected_nlink=1,
        )
        os.fsync(parent_fd)
        _require_manifest_name_binding(parent_fd, output_name, manifest_fd)
        _require_private_manifest_fd(
            manifest_fd,
            expected_payload=payload,
            expected_nlink=1,
        )
        authority_check()
        _require_private_manifest_fd(
            manifest_fd,
            expected_payload=payload,
            expected_nlink=1,
        )
        _require_manifest_name_binding(parent_fd, output_name, manifest_fd)
    finally:
        if manifest_fd is not None:
            os.close(manifest_fd)


def _require_private_manifest_fd(
    fd: int,
    *,
    expected_payload: bytes,
    expected_nlink: int,
) -> None:
    before = os.fstat(fd)
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_uid != os.geteuid()
        or before.st_nlink != expected_nlink
        or stat.S_IMODE(before.st_mode) != 0o600
        or before.st_size != len(expected_payload)
        or os.listxattr(fd)
    ):
        raise _ManifestPublicationError
    if _read_all(fd) != expected_payload:
        raise _ManifestPublicationError
    after = os.fstat(fd)
    if (
        not os.path.samestat(before, after)
        or before.st_mode != after.st_mode
        or before.st_uid != after.st_uid
        or before.st_nlink != after.st_nlink
        or before.st_size != after.st_size
        or os.listxattr(fd)
    ):
        raise _ManifestPublicationError


def _require_manifest_name_binding(
    parent_fd: int,
    name: str,
    manifest_fd: int,
) -> None:
    held = os.fstat(manifest_fd)
    linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    if not stat.S_ISREG(linked.st_mode) or not os.path.samestat(held, linked):
        raise _ManifestPublicationError


def _write_all(fd: int, payload: bytes) -> None:
    remaining = memoryview(payload)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise _ManifestPublicationError
        remaining = remaining[written:]


def _read_all(fd: int) -> bytes:
    os.lseek(fd, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    while True:
        block = os.read(fd, 64 * 1024)
        if not block:
            return b"".join(chunks)
        chunks.append(block)


def _link_unnamed_noreplace(
    manifest_fd: int,
    parent_fd: int,
    destination_name: str,
) -> None:
    try:
        linkat = ctypes.CDLL(None, use_errno=True).linkat
    except AttributeError as exc:
        raise _ManifestPublicationError from exc
    linkat.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    linkat.restype = ctypes.c_int
    if (
        linkat(
            manifest_fd,
            b"",
            parent_fd,
            os.fsencode(destination_name),
            _AT_EMPTY_PATH,
        )
        == 0
    ):
        return
    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise _ManifestPublicationError
    raise OSError(error, os.strerror(error))


# The command validates the fixed bootstrap closure from the same pinned source
# descriptor before it publishes the prospective manifest.
