"""No-follow launch filesystem primitives (Task 5 fix round).

Shared by the pinned launch adapter, its parent expectation derivation, and
the confinement helper: fd-safe private-binary opens, exclusive empty-cwd
creation, and descriptor-relative no-follow session inventory with bounded
journal hashing. Every pathname is opened no-follow exactly once and rechecked
by identity so a same-UID step can never redirect attribution or cleanup.
"""
from __future__ import annotations

import hashlib
import json
import os
import stat

# Cap for hashing a primary session journal (streamed, never fully buffered).
PRIMARY_HASH_LIMIT = 512 * 1024 * 1024


class LaunchFsError(Exception):
    """Fatal launch filesystem violation; the launch must fail closed."""


def sha256_fd(fd: int) -> str:
    """Hex sha256 of the bytes readable from ``fd`` (position preserved)."""
    digest = hashlib.sha256()
    while True:
        chunk = os.read(fd, 1 << 16)
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def empty_omp_cwd_path(
    *,
    home: str,
    lane: str,
    workspace: str,
    session_dir: str | None,
    conf_root: str | None,
    env_roots: dict[str, str],
) -> str:
    """Deterministic profile-isolated empty cwd path under ``$HOME`` (never
    inside a write root, so the helper's overlap rejection cannot fire)."""
    canonical = json.dumps(
        {"lane": lane, "workspace": workspace, "session_dir": session_dir,
         "conf_root": conf_root, "env_roots": env_roots},
        separators=(",", ":"), sort_keys=True,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
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
        # The parent (normally $HOME) may be group/other-readable (0750/0755),
        # but no other user may be able to preplant the exclusive child.
        raise LaunchFsError("empty cwd parent is not a private current-user directory")
    try:
        os.mkdir(path, 0o700)
    except FileExistsError as exc:
        raise LaunchFsError(f"empty OMP cwd already exists: {path}") from exc
    try:
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
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
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise LaunchFsError(f"cannot open the empty OMP cwd: {exc}") from exc
    try:
        _verify_empty_dir(fd, "empty OMP cwd")
    finally:
        os.close(fd)


def session_inventory(session_dir: str) -> tuple[str, ...]:
    """Scan one session dir descriptor-relatively with no-follow entries.

    Every entry must open no-follow as a regular file or directory owned by
    the current user; symlinks and exotic types fail the launch so the child
    cannot plant a misattributed journal.
    """
    try:
        dir_fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise LaunchFsError(f"cannot open session directory: {exc}") from exc
    try:
        names = sorted(os.listdir(dir_fd))
        for name in names:
            try:
                entry = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dir_fd)
            except OSError as exc:
                raise LaunchFsError(f"cannot open session entry {name!r}: {exc}") from exc
            try:
                st = os.fstat(entry)
                if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                    raise LaunchFsError(
                        f"session entry {name!r} is not a regular file or directory"
                    )
                if st.st_uid != os.getuid():
                    raise LaunchFsError(
                        f"session entry {name!r} is not owned by the current user"
                    )
            finally:
                os.close(entry)
        return tuple(names)
    finally:
        os.close(dir_fd)


def primary_journal_identity(session_dir: str, session_id: str) -> tuple[str, str]:
    """Return (name, sha256) of the primary journal for ``session_id``.

    The journal is opened descriptor-relatively with O_NOFOLLOW, must be a
    regular current-user file within the hash bound, is hashed by streaming
    (never fully buffered), and its identity is rechecked after hashing.
    """
    try:
        dir_fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise LaunchFsError(f"cannot open session directory: {exc}") from exc
    try:
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
    finally:
        os.close(dir_fd)
