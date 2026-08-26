"""OMP launch filesystem primitives.

No-follow directory authority, private staging, and bounded journal hashes.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import stat
from .._common.safe_tree import SafeTreeError, open_directory
from .omp_pin import OmpBinaryPin

# Cap for hashing a primary session journal (streamed, never fully buffered).
PRIMARY_HASH_LIMIT = 512 * 1024 * 1024


class LaunchFsError(Exception):
    """Fatal launch filesystem violation."""


def source_owner_admitted(uid: int, *, euid: int | None = None) -> bool:
    return uid == (os.geteuid() if euid is None else euid) or uid == 0


def open_dir_no_follow(path: str) -> int:
    try:
        return open_directory(path)
    except SafeTreeError as exc:
        raise LaunchFsError(str(exc)) from exc


def directory_identity(path: str) -> tuple[int, int]:
    descriptor = open_dir_no_follow(path)
    try:
        kind = os.fstat(descriptor)
        return kind.st_dev, kind.st_ino
    finally:
        os.close(descriptor)


def _require_private_dir(kind: os.stat_result, label: str) -> None:
    if (
        not stat.S_ISDIR(kind.st_mode)
        or kind.st_uid != os.geteuid()
        or kind.st_mode & 0o077
    ):
        raise LaunchFsError(f"{label} is not a private current-user directory")


def _open_private_cache(cache_home: str, digest: str) -> int:
    descriptor = open_dir_no_follow(cache_home)
    try:
        for component in ("omp-i1", "private", digest):
            try:
                os.mkdir(component, 0o700, dir_fd=descriptor)
            except FileExistsError:
                pass
            child = os.open(
                component,
                os.O_RDONLY
                | os.O_DIRECTORY
                | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                dir_fd=descriptor,
            )
            try:
                _require_private_dir(os.fstat(child), "private copy directory")
            except BaseException:
                os.close(child)
                raise
            os.close(descriptor)
            descriptor = child
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def _new_attempt_root(digest_fd: int) -> tuple[str, int]:
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    for _ in range(10):
        name = f"attempt-{secrets.token_hex(16)}"
        try:
            os.mkdir(name, 0o700, dir_fd=digest_fd)
        except FileExistsError:
            continue
        descriptor = os.open(name, flags, dir_fd=digest_fd)
        _require_private_dir(os.fstat(descriptor), "launch attempt")
        return name, descriptor
    raise LaunchFsError("could not reserve a private OMP launch attempt")


def sha256_fd(fd: int) -> str:
    offset = os.lseek(fd, 0, os.SEEK_CUR)
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    try:
        while chunk := os.read(fd, 1 << 16):
            digest.update(chunk)
        return digest.hexdigest()
    finally:
        os.lseek(fd, offset, os.SEEK_SET)


def open_private_exec_fd(target: list[str]) -> int:
    if not target or not os.path.isabs(target[0]):
        raise LaunchFsError("missing or non-absolute private OMP target")
    binary = target[0]
    attempt_dir = os.path.dirname(binary)
    digest = os.path.basename(os.path.dirname(attempt_dir))
    attempt = os.path.basename(attempt_dir)
    if (
        len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or len(attempt) != 40
        or not attempt.startswith("attempt-")
        or any(char not in "0123456789abcdef" for char in attempt[8:])
    ):
        raise LaunchFsError(
            "private OMP target is not under a digest-named launch attempt"
        )
    parent_fd = open_dir_no_follow(attempt_dir)
    try:
        _require_private_dir(os.fstat(parent_fd), "private copy directory")
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
        kind = os.fstat(exec_fd)
        if (
            not stat.S_ISREG(kind.st_mode)
            or kind.st_uid != os.geteuid()
            or kind.st_mode & 0o222
            or kind.st_mode & 0o077
            or kind.st_nlink != 1
        ):
            raise LaunchFsError(
                "private OMP target must be current-user-owned, non-writable, "
                "single-linked, and private"
            )
        if sha256_fd(exec_fd) != digest:
            raise LaunchFsError("private OMP target digest mismatch")
        return exec_fd
    except BaseException:
        os.close(exec_fd)
        raise


def stage_private_copy(
    source_path: str, pin: OmpBinaryPin, cache_home: str
) -> str:
    """Stage the admitted executable in a fresh exclusive attempt root."""
    if not os.path.isabs(source_path):
        raise LaunchFsError("binary resolver returned a non-absolute path")
    source_fd = digest_fd = attempt_fd = -1
    attempt_name: str | None = None
    created = False
    try:
        source_fd = os.open(
            source_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC
        )
        admitted = os.fstat(source_fd)
        if not stat.S_ISREG(admitted.st_mode):
            raise LaunchFsError("source is not a regular file")
        if not source_owner_admitted(admitted.st_uid):
            raise LaunchFsError("source is not owned by root or the effective user")
        if admitted.st_mode & 0o222:
            raise LaunchFsError("source is writable")
        if admitted.st_nlink != 1:
            raise LaunchFsError("source must have exactly one link")
        if sha256_fd(source_fd) != pin.executable_sha256:
            raise LaunchFsError("source digest does not match the pin")
        after = os.fstat(source_fd)
        stable = ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        if any(getattr(after, name) != getattr(admitted, name) for name in stable):
            raise LaunchFsError("source changed during admission")

        digest_fd = _open_private_cache(cache_home, pin.executable_sha256)
        attempt_name, attempt_fd = _new_attempt_root(digest_fd)
        output_fd = os.open(
            "omp",
            os.O_WRONLY
            | os.O_CREAT
            | os.O_EXCL
            | os.O_CLOEXEC
            | os.O_NOFOLLOW,
            0o500,
            dir_fd=attempt_fd,
        )
        created = True
        try:
            os.lseek(source_fd, 0, os.SEEK_SET)
            while chunk := os.read(source_fd, 1 << 20):
                remaining = memoryview(chunk)
                while remaining:
                    written = os.write(output_fd, remaining)
                    if written <= 0:
                        raise LaunchFsError("private OMP copy made no progress")
                    remaining = remaining[written:]
            os.fchmod(output_fd, 0o500)
            os.fsync(output_fd)
        finally:
            os.close(output_fd)
        target = os.path.join(
            cache_home,
            "omp-i1",
            "private",
            pin.executable_sha256,
            attempt_name,
            "omp",
        )
        verify_fd = open_private_exec_fd([target])
        os.close(verify_fd)
        return target
    except BaseException as exc:
        if created and attempt_fd >= 0:
            try:
                os.unlink("omp", dir_fd=attempt_fd)
            except OSError:
                pass
        if attempt_name is not None and digest_fd >= 0:
            try:
                os.rmdir(attempt_name, dir_fd=digest_fd)
            except OSError:
                pass
        if isinstance(exc, OSError):
            raise LaunchFsError(
                f"cannot stage private OMP copy no-follow: {exc}"
            ) from exc
        raise
    finally:
        for descriptor in (attempt_fd, digest_fd, source_fd):
            if descriptor >= 0:
                os.close(descriptor)


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
    digest = profile_attempt_key(
        lane=lane, workspace=workspace, session_dir=session_dir,
        conf_root=conf_root, env_roots=env_roots,
    )
    if nonce:
        return os.path.join(home, f"omp-empty-{digest}-{nonce}")
    return os.path.join(home, "omp-empty-" + digest)


def profile_attempt_key(
    *,
    lane: str,
    workspace: str,
    session_dir: str | None,
    conf_root: str | None,
    env_roots: dict[str, str],
) -> str:
    """16-hex attempt key shared by the empty cwd and attempt roots."""
    canonical = json.dumps(
        {"lane": lane, "workspace": workspace, "session_dir": session_dir,
         "conf_root": conf_root, "env_roots": env_roots},
        separators=(",", ":"), sort_keys=True,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


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


def open_empty_omp_cwd(path: str) -> int:
    """Open and retain the prepared empty cwd no-follow."""
    try:
        descriptor = open_dir_no_follow(path)
    except (OSError, LaunchFsError) as exc:
        raise LaunchFsError(f"cannot open the empty OMP cwd: {exc}") from exc
    try:
        _verify_empty_dir(descriptor, "empty OMP cwd")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


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
    the current user; symlinks and exotic types fail so the child cannot
    plant a misattributed journal.
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

    Opened descriptor-relatively with O_NOFOLLOW; must be a regular
    current-user one-link file within the hash bound, hashed by streaming
    (never fully buffered), identity rechecked after hashing so a
    hard-linked alias cannot misattribute it.
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
