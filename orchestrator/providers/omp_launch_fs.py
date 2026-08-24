"""No-follow launch filesystem primitives (Task 5 fix rounds).

Shared by the pinned launch adapter, its parent expectation derivation, and
the confinement helper: fd-safe private-binary opens, exclusive empty-cwd
creation, and descriptor-relative no-follow session inventory with bounded
journal hashing. Every pathname is opened no-follow exactly once and rechecked
by identity so a same-UID step can never redirect attribution or cleanup.
The admission/binding policy (carriers, mount topology, identity relations,
fresh-session identity compare) lives in ``omp_launch_policy``.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import secrets
import shutil
import stat
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.providers.omp_pin import OmpBinaryPin

# Cap for hashing a primary session journal (streamed, never fully buffered).
PRIMARY_HASH_LIMIT = 512 * 1024 * 1024

_NOFOLLOW_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class LaunchFsError(Exception):
    """Fatal launch filesystem violation; the launch must fail closed."""


def open_dir_no_follow(path: str) -> int:
    """Open an absolute directory path component-by-component from ``/``.

    Every component is opened with ``O_NOFOLLOW|O_DIRECTORY|O_CLOEXEC``
    relative to the parent dirfd, so a symlink at ANY position fails the
    open: no resolve-then-open TOCTOU, no lexical canonicalization. The
    returned fd is caller-owned and backs the bound identity.
    """
    if not os.path.isabs(path):
        raise LaunchFsError(f"directory root must be absolute: {path!r}")
    components = [part for part in path.split(os.sep) if part not in ("", ".")]
    if any(part == ".." for part in components):
        raise LaunchFsError(f"directory root must not contain '..': {path!r}")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in components:
            try:
                child = os.open(component, _NOFOLLOW_DIRECTORY, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise LaunchFsError(
                        f"cannot open directory root {path!r}: component {component!r} is a symlink or non-directory"
                    ) from exc
                raise LaunchFsError(f"cannot open directory root {path!r} component {component!r}: {exc}") from exc
            os.close(fd)
            fd = child
        st = os.fstat(fd)
        if not stat.S_ISDIR(st.st_mode):
            raise LaunchFsError(f"directory root is not a directory: {path!r}")
        return fd
    except BaseException:
        os.close(fd)
        raise


def directory_identity(path: str) -> tuple[int, int]:
    """Return the no-follow component-walked (dev, ino) of a directory path."""
    fd = open_dir_no_follow(path)
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    return st.st_dev, st.st_ino


def open_private_exec_fd(target: list[str]) -> int:
    """Open the private target no-follow via its verified private parent.

    The digest-named copy directory is opened first (no-follow, owner/mode
    verified); the basename is then opened against that dirfd with O_NOFOLLOW
    and rehashed on the same fd: a pre-open replacement mismatches the hash,
    a post-open replacement cannot change the executed inode.
    """
    if not target:
        raise LaunchFsError("missing private OMP target after --")
    binary = target[0]
    if not os.path.isabs(binary):
        raise LaunchFsError("private OMP target must be absolute")
    digest_dir = os.path.basename(os.path.dirname(binary))
    if len(digest_dir) != 64 or any(char not in "0123456789abcdef" for char in digest_dir):
        raise LaunchFsError("private OMP target is not under a digest-named copy directory")
    try:
        parent_fd = os.open(os.path.dirname(binary), _NOFOLLOW_DIRECTORY)
    except OSError as exc:
        raise LaunchFsError(f"cannot open the private copy directory: {exc}") from exc
    try:
        st = os.fstat(parent_fd)
        if st.st_uid != os.getuid() or st.st_mode & 0o077:
            raise LaunchFsError("private copy directory is not a private current-user directory")
        try:
            exec_fd = os.open(
                os.path.basename(binary),
                os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
        except OSError as exc:
            raise LaunchFsError(f"cannot open the private OMP target: {exc}") from exc
    finally:
        os.close(parent_fd)
    try:
        st = os.fstat(exec_fd)
        if not stat.S_ISREG(st.st_mode):
            raise LaunchFsError("private OMP target is not a regular file")
        if st.st_uid != os.getuid():
            raise LaunchFsError("private OMP target is not owned by the current user")
        if st.st_mode & 0o022:
            raise LaunchFsError("private OMP target is group/other-writable")
        if sha256_fd(exec_fd) != digest_dir:
            raise LaunchFsError("private OMP target digest does not match its digest directory")
    except BaseException:
        os.close(exec_fd)
        raise
    return exec_fd


def sha256_fd(fd: int) -> str:
    """Hex sha256 of the bytes readable from ``fd`` (position preserved)."""
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1 << 16)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def stage_private_copy(source_path: str, pin: OmpBinaryPin, cache_home: str) -> str:
    """Verify the source no-follow/owner/mode/type/digest and stage a private copy.

    Raises ``LaunchFsError`` on any violation; the caller translates to its
    launch-facing error type.
    """
    if not os.path.isabs(source_path):
        raise LaunchFsError("binary resolver must return an absolute source path")
    try:
        fd = os.open(source_path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError as exc:
        raise LaunchFsError(f"cannot open source no-follow: {exc}") from exc
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode):
            raise LaunchFsError("source is not a regular file")
        if st.st_uid != os.getuid():
            raise LaunchFsError("source is not owned by the current user")
        if st.st_mode & 0o022:
            raise LaunchFsError("source is group/other-writable")
        if sha256_fd(fd) != pin.executable_sha256:
            raise LaunchFsError("source digest does not match the pinned executable")
        os.lseek(fd, 0, os.SEEK_SET)
        base_dir = os.path.join(cache_home, "omp-i1", "private")
        for directory in (base_dir, os.path.join(base_dir, pin.executable_sha256)):
            try:
                os.makedirs(directory, mode=0o700, exist_ok=True)
                st = os.stat(directory)
            except OSError as exc:
                raise LaunchFsError(f"cannot prepare the private copy directory: {exc}") from exc
            if st.st_uid != os.getuid() or st.st_mode & 0o077:
                raise LaunchFsError("private copy directory is not a private current-user directory")
        target = os.path.join(base_dir, pin.executable_sha256, os.path.basename(source_path))
        try:
            verify_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        except OSError:
            staging = os.path.join(
                base_dir, pin.executable_sha256, ".staging-" + secrets.token_hex(8)
            )
            stage_fd = os.open(staging, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o500)
            try:
                shutil.copyfileobj(
                    os.fdopen(os.dup(fd), "rb"),
                    os.fdopen(stage_fd, "wb", closefd=False),
                )
                os.fsync(stage_fd)
            except BaseException:
                os.close(stage_fd)
                try:
                    os.unlink(staging)
                except OSError:
                    pass
                raise
            os.close(stage_fd)
            try:
                os.link(staging, target)  # atomic no-replace publish
            except FileExistsError:
                pass
            finally:
                os.unlink(staging)
            verify_fd = os.open(target, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            if sha256_fd(verify_fd) != pin.executable_sha256:
                raise LaunchFsError("private copy digest mismatch")
        finally:
            os.close(verify_fd)
    finally:
        os.close(fd)
    return target


def empty_omp_cwd_path(
    *,
    home: str,
    lane: str,
    workspace: str,
    session_dir: str | None,
    conf_root: str | None,
    env_roots: dict[str, str],
    nonce: str | None = None,
) -> str:
    """Deterministic profile-isolated empty cwd path under ``$HOME`` (never
    inside a write root, so the helper's overlap rejection cannot fire); the
    optional per-invocation nonce yields a fresh exclusive path so a
    crashed-run leftover can never poison a later launch.
    """
    canonical = json.dumps(
        {"lane": lane, "workspace": workspace, "session_dir": session_dir,
         "conf_root": conf_root, "env_roots": env_roots},
        separators=(",", ":"), sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    if nonce:
        return os.path.join(home, f"omp-empty-{digest}-{nonce}")
    return os.path.join(home, "omp-empty-" + digest)


def _verify_empty_dir(fd: int, what: str) -> None:
    st = os.fstat(fd)
    if not stat.S_ISDIR(st.st_mode):
        raise LaunchFsError(f"{what} is not a directory")
    if st.st_uid != os.getuid():
        raise LaunchFsError(f"{what} is not owned by the current user")
    if st.st_mode & 0o077:
        raise LaunchFsError(f"{what} is group/other-accessible")
    if os.listdir(fd):
        raise LaunchFsError(f"{what} is not empty")


def create_empty_omp_cwd(path: str) -> None:
    """Create the empty cwd EXCLUSIVELY beneath a verified current-user parent."""
    parent = os.path.dirname(path)
    if not os.path.isabs(path):
        raise LaunchFsError("empty OMP cwd must be an absolute path")
    try:
        st = os.stat(parent)
    except OSError as exc:
        raise LaunchFsError(f"cannot verify the empty cwd parent: {exc}") from exc
    if st.st_uid != os.getuid() or st.st_mode & 0o022:
        raise LaunchFsError("empty cwd parent is not a private current-user directory")
    try:
        os.mkdir(path, 0o700)
    except FileExistsError as exc:
        raise LaunchFsError(f"empty OMP cwd already exists: {path}") from exc
    try:
        fd = open_dir_no_follow(path)
    except OSError as exc:
        raise LaunchFsError(f"cannot open the empty OMP cwd: {exc}") from exc
    try:
        _verify_empty_dir(fd, "empty OMP cwd")
    finally:
        os.close(fd)


def open_empty_omp_cwd(path: str) -> None:
    """Open the prepared empty cwd no-follow and verify owner/mode/emptiness.

    The parent (workflow prepare) creates it exclusively; the adapter opens
    the same directory object so a preplanted symlink or non-empty entry
    fails the launch.
    """
    try:
        fd = open_dir_no_follow(path)
    except (OSError, LaunchFsError) as exc:
        raise LaunchFsError(f"cannot open the empty OMP cwd: {exc}") from exc
    try:
        _verify_empty_dir(fd, "empty OMP cwd")
    finally:
        os.close(fd)


def open_session_dir(session_dir: str) -> int:
    """Open the fresh session dir no-follow and verify it is private.

    The directory must be a current-user directory with no group/other
    access; the returned fd is owned by the caller.
    """
    fd = open_dir_no_follow(session_dir)
    try:
        st = os.fstat(fd)
        if st.st_uid != os.getuid():
            raise LaunchFsError(
                f"session directory is not owned by the current user: {session_dir!r}"
            )
        if st.st_mode & 0o077:
            raise LaunchFsError(
                f"session directory is group/other-accessible: {session_dir!r}"
            )
        return fd
    except BaseException:
        os.close(fd)
        raise


def session_dir_identity(session_dir: str) -> tuple[int, int]:
    """Return the (dev, ino) of a verified private fresh session directory."""
    fd = open_session_dir(session_dir)
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    return st.st_dev, st.st_ino


def session_inventory_fd(dir_fd: int) -> tuple[str, ...]:
    """Scan one session dir descriptor-relatively with no-follow entries.

    Every entry must open no-follow as a regular file or directory owned by
    the current user; symlinks and exotic types fail the launch so the child
    cannot plant a misattributed journal.
    """
    names = sorted(os.listdir(dir_fd))
    for name in names:
        try:
            entry = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
        except OSError as exc:
            raise LaunchFsError(f"cannot open session entry {name!r}: {exc}") from exc
        try:
            st = os.fstat(entry)
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                raise LaunchFsError(f"session entry {name!r} is not a regular file or directory")
            if st.st_uid != os.getuid():
                raise LaunchFsError(f"session entry {name!r} is not owned by the current user")
        finally:
            os.close(entry)
    return tuple(names)


def session_inventory(session_dir: str) -> tuple[str, ...]:
    """Open one session dir and scan it descriptor-relatively (see fd variant)."""
    dir_fd = open_session_dir(session_dir)
    try:
        return session_inventory_fd(dir_fd)
    finally:
        os.close(dir_fd)


def primary_journal_identity_fd(dir_fd: int, session_id: str) -> tuple[str, str]:
    """Return (name, sha256) of the primary journal for ``session_id``.

    The journal is opened descriptor-relatively with O_NOFOLLOW, must be a
    regular current-user file within the hash bound, is hashed by streaming
    (never fully buffered), and its identity is rechecked after hashing. The
    journal must also be a one-link file so a hard-linked alias cannot
    misattribute it.
    """
    for name in sorted(os.listdir(dir_fd)):
        if not name.endswith(".jsonl"):
            continue
        if name[: -len(".jsonl")].rsplit("_", 1)[-1] != session_id:
            continue
        try:
            entry = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
        except OSError as exc:
            raise LaunchFsError(f"cannot open primary journal {name!r}: {exc}") from exc
        try:
            st = os.fstat(entry)
            if not stat.S_ISREG(st.st_mode):
                raise LaunchFsError(f"primary journal {name!r} is not a regular file")
            if st.st_uid != os.getuid():
                raise LaunchFsError(f"primary journal {name!r} is not owned by the current user")
            if st.st_nlink != 1:
                raise LaunchFsError(f"primary journal {name!r} is hard-linked")
            if st.st_size > PRIMARY_HASH_LIMIT:
                raise LaunchFsError(f"primary journal {name!r} exceeds the hash bound")
            digest = hashlib.sha256()
            while True:
                chunk = os.read(entry, 1 << 16)
                if not chunk:
                    break
                digest.update(chunk)
            st2 = os.fstat(entry)
            if (st2.st_dev, st2.st_ino, st2.st_size) != (st.st_dev, st.st_ino, st.st_size):
                raise LaunchFsError(f"primary journal {name!r} changed during hashing")
            return name, digest.hexdigest()
        finally:
            os.close(entry)
    raise LaunchFsError("no primary session journal matches the header session id")


def primary_journal_identity(session_dir: str, session_id: str) -> tuple[str, str]:
    """Open one session dir and derive the primary descriptor-relatively."""
    dir_fd = open_session_dir(session_dir)
    try:
        return primary_journal_identity_fd(dir_fd, session_id)
    finally:
        os.close(dir_fd)


def accept_fresh_session_fd(
    dir_fd: int,
    session_id: str,
    expected_observed: tuple[str, ...],
    expected_relpath: str,
    expected_sha256: str,
) -> None:
    """FINAL one-fd parent acceptance (T5-SEC-006).

    On one retained, identity-checked visit fd at one instant, derives the
    inventory, requires it to equal the adapter frame's observed relpaths,
    then derives the one-link primary journal and requires relpath + bounded
    sha256 to agree with the framed values. A racer that changes a NON-primary
    entry between the observation scan and finalization fails here even when
    the primary journal still matches.
    """
    observed = session_inventory_fd(dir_fd)
    if tuple(observed) != tuple(expected_observed):
        raise LaunchFsError("fresh session inventory drifted from the adapter frame")
    revalidate_primary_journal_fd(dir_fd, session_id, expected_relpath, expected_sha256)


def revalidate_primary_journal_fd(
    dir_fd: int,
    session_id: str,
    relpath: str,
    sha256: str,
) -> None:
    """Re-derive the primary from one retained fd and require framed agreement."""
    observed_relpath, observed_sha256 = primary_journal_identity_fd(dir_fd, session_id)
    if observed_relpath != relpath:
        raise LaunchFsError(
            f"primary journal relpath drifted: framed {relpath!r}, observed {observed_relpath!r}"
        )
    if observed_sha256 != sha256:
        raise LaunchFsError(
            f"primary journal sha256 drifted: framed {sha256!r}, observed {observed_sha256!r}"
        )


def revalidate_primary_journal(
    session_dir: str,
    session_id: str,
    relpath: str,
    sha256: str,
    expected_identity: tuple[int, int] | None = None,
) -> None:
    """Parent post-run re-validation on ONE opened visit fd (T5-SEC-006).

    Re-opens the verified private session dir no-follow, compares the
    expected identity (when known), re-derives the primary journal identity
    descriptor-relatively, and requires the relpath and bounded sha256 to
    agree with the adapter's framed values. Any drift fails the launch
    closed.
    """
    dir_fd = open_session_dir(session_dir)
    try:
        if expected_identity is not None:
            st = os.fstat(dir_fd)
            if (st.st_dev, st.st_ino) != expected_identity:
                raise LaunchFsError(
                    "fresh session directory identity does not match the prepared visit"
                )
        revalidate_primary_journal_fd(dir_fd, session_id, relpath, sha256)
    finally:
        os.close(dir_fd)
