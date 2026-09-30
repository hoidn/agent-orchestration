"""Descriptor-rooted operations on workflow result files."""

from __future__ import annotations

import errno
import io
import os
import secrets
import shutil
import stat
import weakref
from pathlib import Path

from .._common.safe_tree import open_directory, remove_tree_contents

_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_NOFOLLOW_READ = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
_NOFOLLOW_WRITE = os.O_WRONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


def _write_bytes(descriptor: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("result file write made no progress")
        remaining = remaining[written:]


class WorkspaceFiles:
    """Own or borrow one open workspace root for result-file operations."""

    def __init__(
        self,
        workspace: Path,
        *,
        root_fd: int | None = None,
        owns_root: bool = False,
    ) -> None:
        self.workspace = Path(os.path.abspath(os.fspath(workspace)))
        self._owns_root = root_fd is None or owns_root
        self._root_fd = (
            open_directory(os.fspath(self.workspace))
            if root_fd is None
            else root_fd
        )
        self._closed = False
        # An owner nobody closed releases its root when it is collected.
        self._release_root = (
            weakref.finalize(self, os.close, self._root_fd) if self._owns_root else None
        )

    def subroot(self, workspace: str | Path) -> "WorkspaceFiles":
        """Open one descendant workspace without resolving its path again."""
        relative = self.relative(workspace)
        parent_fd, leaf = self._parent(relative, create=False)
        descriptor: int | None = None
        try:
            descriptor = os.open(
                leaf,
                _NOFOLLOW_DIRECTORY,
                dir_fd=parent_fd,
            )
        except BaseException:
            os.close(parent_fd)
            raise
        try:
            os.close(parent_fd)
        except BaseException:
            os.close(descriptor)
            raise
        return WorkspaceFiles(
            self.workspace / relative,
            root_fd=descriptor,
            owns_root=True,
        )

    def duplicate(self) -> "WorkspaceFiles":
        """Return an independent owner for this exact pinned root."""
        return WorkspaceFiles(
            self.workspace,
            root_fd=os.dup(self.root_fd),
            owns_root=True,
        )

    @property
    def root_fd(self) -> int:
        if self._closed:
            raise OSError("workspace file owner is closed")
        return self._root_fd

    @property
    def closed(self) -> bool:
        return self._closed

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._release_root is not None:
            self._release_root()

    def relative(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_absolute():
            try:
                candidate = candidate.relative_to(self.workspace)
            except ValueError as exc:
                raise ValueError("result path escapes workspace") from exc
        if not candidate.parts or any(part in {"", ".", ".."} for part in candidate.parts):
            raise ValueError("result path must be a non-empty workspace-relative path")
        return candidate

    def _parent(self, path: str | Path, *, create: bool) -> tuple[int, str]:
        relative = self.relative(path)
        directory_fd = os.dup(self.root_fd)
        try:
            for component in relative.parts[:-1]:
                if create:
                    try:
                        os.mkdir(component, dir_fd=directory_fd)
                    except FileExistsError:
                        pass
                try:
                    child_fd = os.open(
                        component,
                        _NOFOLLOW_DIRECTORY,
                        dir_fd=directory_fd,
                    )
                except OSError as exc:
                    if exc.errno not in (errno.ELOOP, errno.ENOTDIR):
                        raise
                    raise OSError(
                        exc.errno,
                        f"result path component {component!r} is a symbolic link or not a directory",
                    ) from exc
                parent_fd, directory_fd = directory_fd, child_fd
                os.close(parent_fd)
            return directory_fd, relative.name
        except BaseException:
            os.close(directory_fd)
            raise

    def ensure_parent(self, path: str | Path) -> None:
        parent_fd, _leaf = self._parent(path, create=True)
        os.close(parent_fd)

    def exists(self, path: str | Path) -> bool:
        candidate = Path(path)
        if candidate == Path(".") or candidate == self.workspace:
            return True
        try:
            parent_fd, leaf = self._parent(path, create=False)
        except FileNotFoundError:
            return False
        try:
            try:
                info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return False
            if stat.S_ISLNK(info.st_mode):
                raise OSError(errno.ELOOP, "result path is a symbolic link")
            return True
        finally:
            os.close(parent_fd)

    def stat(self, path: str | Path) -> os.stat_result:
        parent_fd, leaf = self._parent(path, create=False)
        try:
            info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(info.st_mode):
                raise OSError(errno.ELOOP, "result path is a symbolic link")
            return info
        finally:
            os.close(parent_fd)

    def read(self, path: str | Path) -> bytes:
        with self.open_read(path) as source:
            return source.read()

    def open_read(self, path: str | Path):
        """Return a buffered stream for a descriptor-rooted regular file."""
        parent_fd, leaf = self._parent(path, create=False)
        descriptor: int | None = None
        source = None
        try:
            descriptor = os.open(leaf, _NOFOLLOW_READ, dir_fd=parent_fd)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError(errno.EINVAL, "result path is not a regular file")
            source = os.fdopen(descriptor, "rb")
            descriptor = None
            return source
        finally:
            try:
                if descriptor is not None:
                    closing_fd = descriptor
                    descriptor = None
                    os.close(closing_fd)
            finally:
                try:
                    os.close(parent_fd)
                except BaseException:
                    if source is not None:
                        source.close()
                    raise

    def write_from_fileobj(
        self,
        path: str | Path,
        source,
        *,
        mode: int | None = None,
        times_ns: tuple[int, int] | None = None,
    ) -> None:
        """Atomically write a binary stream beneath this workspace descriptor."""
        parent_fd, leaf = self._parent(path, create=True)
        temporary = f".{leaf}.{secrets.token_hex(8)}.tmp"
        descriptor: int | None = None
        try:
            descriptor = os.open(
                temporary,
                _NOFOLLOW_WRITE | os.O_CREAT | os.O_EXCL,
                0o666 if mode is None else mode,
                dir_fd=parent_fd,
            )
            if mode is not None:
                os.fchmod(descriptor, mode)
            with os.fdopen(os.dup(descriptor), "wb") as destination:
                shutil.copyfileobj(source, destination, length=64 * 1024)
                destination.flush()
            if times_ns is not None:
                os.utime(descriptor, ns=times_ns)
            os.fsync(descriptor)
            closing_fd = descriptor
            descriptor = None
            os.close(closing_fd)
            os.replace(temporary, leaf, src_dir_fd=parent_fd, dst_dir_fd=parent_fd)
            os.fsync(parent_fd)
        except BaseException:
            try:
                os.unlink(temporary, dir_fd=parent_fd)
            except OSError:
                pass
            raise
        finally:
            try:
                if descriptor is not None:
                    closing_fd = descriptor
                    descriptor = None
                    os.close(closing_fd)
            finally:
                os.close(parent_fd)

    def sha256(self, path: str | Path) -> str:
        from hashlib import sha256

        digest = sha256()
        with self.open_read(path) as source:
            while chunk := source.read(64 * 1024):
                digest.update(chunk)
        return "sha256:" + digest.hexdigest()

    def copy_to(
        self,
        source: str | Path,
        destination_owner: "WorkspaceFiles",
        destination: str | Path,
    ) -> None:
        """Copy a regular result file atomically without buffering its contents."""
        with self.open_read(source) as source_file:
            source_info = os.fstat(source_file.fileno())
            destination_owner.write_from_fileobj(
                destination,
                source_file,
                mode=source_info.st_mode & 0o777,
                times_ns=(source_info.st_atime_ns, source_info.st_mtime_ns),
            )

    def create(
        self,
        path: str | Path,
        content: bytes,
        *,
        exclusive: bool = False,
        mode: int = 0o600,
    ) -> None:
        parent_fd, leaf = self._parent(path, create=True)
        descriptor: int | None = None
        try:
            flags = _NOFOLLOW_WRITE | os.O_CREAT
            flags |= os.O_EXCL if exclusive else os.O_TRUNC
            descriptor = os.open(leaf, flags, mode, dir_fd=parent_fd)
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise OSError(errno.EINVAL, "result path is not a regular file")
            _write_bytes(descriptor, content)
            if exclusive:
                os.fsync(descriptor)
        except BaseException:
            if exclusive and descriptor is not None:
                try:
                    os.unlink(leaf, dir_fd=parent_fd)
                except OSError:
                    pass
            raise
        finally:
            try:
                if descriptor is not None:
                    closing_fd = descriptor
                    descriptor = None
                    os.close(closing_fd)
            finally:
                os.close(parent_fd)

    def write_atomic(
        self,
        path: str | Path,
        content: bytes,
        *,
        mode: int | None = 0o600,
    ) -> None:
        self.write_from_fileobj(path, io.BytesIO(content), mode=mode)

    def ensure_directory(self, path: str | Path) -> None:
        parent_fd, leaf = self._parent(path, create=True)
        try:
            try:
                os.mkdir(leaf, dir_fd=parent_fd)
            except FileExistsError:
                pass
            child_fd = os.open(leaf, _NOFOLLOW_DIRECTORY, dir_fd=parent_fd)
            os.close(child_fd)
        finally:
            os.close(parent_fd)

    def rmdir(self, path: str | Path) -> None:
        parent_fd, leaf = self._parent(path, create=False)
        try:
            os.rmdir(leaf, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def remove_tree(self, path: str | Path) -> None:
        parent_fd, leaf = self._parent(path, create=False)
        try:
            try:
                info = os.stat(leaf, dir_fd=parent_fd, follow_symlinks=False)
            except FileNotFoundError:
                return
            if not stat.S_ISDIR(info.st_mode):
                os.unlink(leaf, dir_fd=parent_fd)
                return
            child_fd = os.open(leaf, _NOFOLLOW_DIRECTORY, dir_fd=parent_fd)
            try:
                remove_tree_contents(child_fd)
            finally:
                os.close(child_fd)
            os.rmdir(leaf, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def clear(self, path: str | Path) -> None:
        parent_fd, leaf = self._parent(path, create=True)
        try:
            try:
                os.unlink(leaf, dir_fd=parent_fd)
            except FileNotFoundError:
                pass
        finally:
            os.close(parent_fd)

    def unlink(self, path: str | Path) -> None:
        parent_fd, leaf = self._parent(path, create=False)
        try:
            os.unlink(leaf, dir_fd=parent_fd)
        finally:
            os.close(parent_fd)

    def replace(self, source: str | Path, destination: str | Path) -> None:
        source_fd, source_leaf = self._parent(source, create=False)
        try:
            destination_fd, destination_leaf = self._parent(destination, create=True)
            try:
                os.replace(
                    source_leaf,
                    destination_leaf,
                    src_dir_fd=source_fd,
                    dst_dir_fd=destination_fd,
                )
            finally:
                os.close(destination_fd)
        finally:
            os.close(source_fd)
