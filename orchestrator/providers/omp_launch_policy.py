"""OMP launch policy layer (Task 5 fix round 3, T5-SEC-003/005/006).

The launch filesystem primitives live in ``omp_launch_fs``; this module
carries the code-owned ADMISSION and BINDING policy shared by the adapter,
the parent expectation derivation, and the confinement helper:

- code-owned internal environment carriers for the per-invocation empty cwd
  and the fresh session-dir identity (rejected if authored, stripped before
  the exact positive child env);
- mount-topology admission: a write root on the same superblock as a guarded
  root but under a different mount is a bind-mounted alias view and fails
  closed; genuine separate superblocks stay admissible;
- opened-identity relations (duplicate / ancestor / descendant) that back
  the overlapping-write-root contract;
- the fresh visit directory opened ONCE, identity-compared, and reused
  descriptor-relatively for inventory and primary-journal derivation.

A separate module is required only because ``omp_launch_fs`` and the helper
both hit the 500-line production cap after round-3 hardening.
"""
from __future__ import annotations

import os

from .omp_launch_fs import LaunchFsError, open_dir_no_follow, open_session_dir

# Code-owned internal environment carriers: the parent (workflow prepare)
# carries the per-invocation empty cwd and the fresh session-dir identity to
# the adapter/helper through these names. They win over inputs, are rejected
# if authored at the provider/workflow boundary, and are stripped before the
# child exec (never part of the positive child environment).
EMPTY_CWD_ENV = "_OMP_I1_EMPTY_CWD"
SESSION_DIR_ENV = "_OMP_I1_SESSION_DIR"
SESSION_IDENTITY_ENV = "_OMP_I1_SESSION_DIR_IDENTITY"
CARRIER_ENV_NAMES = (EMPTY_CWD_ENV, SESSION_DIR_ENV, SESSION_IDENTITY_ENV)


def strip_omp_carriers(env: dict[str, str]) -> None:
    """Remove the code-owned carriers from an environment in place."""
    for name in CARRIER_ENV_NAMES:
        env.pop(name, None)


def parse_session_identity(text: str) -> tuple[int, int]:
    """Parse the trusted ``dev:ino`` session-dir identity carrier."""
    dev_text, separator, ino_text = text.partition(":")
    if not separator:
        raise LaunchFsError(f"session identity carrier must be 'dev:ino': {text!r}")
    try:
        return int(dev_text), int(ino_text)
    except ValueError as exc:
        raise LaunchFsError(f"invalid session identity carrier: {text!r}") from exc


def open_session_dir_verified(
    session_dir: str,
    expected_identity: tuple[int, int] | None = None,
) -> int:
    """Open the visit directory ONCE, verifying privacy and expected identity.

    The retained fd backs the identity comparison AND the descriptor-relative
    inventory/primary derivation (T5-SEC-006): a path swap between checks
    cannot redirect attribution.
    """
    fd = open_session_dir(session_dir)
    try:
        if expected_identity is not None:
            st = os.fstat(fd)
            if (st.st_dev, st.st_ino) != expected_identity:
                raise LaunchFsError(
                    "fresh session directory identity does not match the prepared visit"
                )
        return fd
    except BaseException:
        os.close(fd)
        raise


def verify_session_identity(
    rows: list[tuple[str, str, str]],
    fds: list[int],
    env: dict[str, str],
) -> None:
    """Helper-side pre-exec fresh session identity compare (T5-SEC-005).

    When the trusted carrier is present, the session write root (or the
    carrier-named visit dir for coalesced conf lanes) must be the SAME
    directory the parent froze at prepare time; a replacement fails before
    ``add_rule``/exec.
    """
    carrier = env.get(SESSION_IDENTITY_ENV)
    if carrier is None:
        return
    expected = parse_session_identity(carrier)
    for (role, label, _path), fd in zip(rows, fds):
        if role == "write" and label == "session":
            st = os.fstat(fd)
            if (st.st_dev, st.st_ino) != expected:
                raise LaunchFsError(
                    "fresh session directory identity does not match the prepared visit"
                )
            return
    path = env.get(SESSION_DIR_ENV)
    if not path:
        raise LaunchFsError("missing fresh session directory carrier")
    fd = open_dir_no_follow(path)
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    if (st.st_dev, st.st_ino) != expected:
        raise LaunchFsError(
            "fresh session directory identity does not match the prepared visit"
        )


def _fd_is_descendant(ancestor_fd: int, descendant_fd: int) -> bool:
    """Whether ``descendant_fd`` equals ``ancestor_fd`` or is beneath it.

    Walks ``..`` through duplicated fds (never closing a caller fd), stopping
    at the FS root via a seen-identity set; rejects write-root nesting by
    opened identity, never by lexical path.
    """
    target = os.fstat(ancestor_fd)
    if target.st_dev == 0:
        return False
    current = os.dup(descendant_fd)
    seen: set[tuple[int, int]] = set()
    try:
        while True:
            st = os.fstat(current)
            identity = (st.st_dev, st.st_ino)
            if identity == (target.st_dev, target.st_ino):
                return True
            if identity in seen:
                return False  # reached the FS root without a match
            seen.add(identity)
            try:
                parent = os.open("..", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=current)
            except OSError as exc:
                raise LaunchFsError(f"cannot walk root parent: {exc}") from exc
            os.close(current)
            current = parent
    finally:
        os.close(current)


_MOUNTINFO: tuple[tuple[str, int], ...] | None = None


def _unmountescape(value: str) -> str:
    return (
        value.replace("\\040", " ")
        .replace("\\011", "\t")
        .replace("\\012", "\n")
        .replace("\\134", "\\")
    )


def _mountinfo_entries() -> tuple[tuple[str, int], ...]:
    """``(mount_point, mount_id)`` pairs parsed once from /proc/self/mountinfo."""
    global _MOUNTINFO
    if _MOUNTINFO is None:
        entries = []
        with open("/proc/self/mountinfo", encoding="utf-8") as handle:
            for line in handle:
                head, separator, _tail = line.partition(" - ")
                if not separator:
                    continue
                fields = head.split()
                if len(fields) < 6:
                    continue
                entries.append((_unmountescape(fields[4]), int(fields[0])))
        _MOUNTINFO = tuple(entries)
    return _MOUNTINFO


def _mount_id_for_path(path: str) -> int:
    """Mount id covering ``path`` (the longest mount-point prefix)."""
    best_point = ""
    best_id: int | None = None
    for point, mount_id in _mountinfo_entries():
        if path == point or path.startswith(point.rstrip("/") + "/"):
            if len(point) > len(best_point):
                best_point, best_id = point, mount_id
    if best_id is None:
        raise LaunchFsError(f"cannot resolve the mount for root {path!r}")
    return best_id


def _fd_is_same_superblock(fd_a: int, fd_b: int) -> bool:
    return os.fstat(fd_a).st_dev == os.fstat(fd_b).st_dev


def verify_root_identity_relations(
    rows: list[tuple[str, str, str]],
    fds: list[int],
) -> None:
    """Reject duplicate opened identities, write-root nesting, and bind aliases.

    Every root was already opened no-follow; this binds the identity
    relations: two roots must not be the same directory, a write root must
    not equal or contain (or be contained in) a protected or read root, and
    two write roots must not be in an ancestor/descendant relation (e.g.
    ``state`` nested below ``data``). A write root on the same superblock as
    a guarded root but under a DIFFERENT mount is a bind-mounted alias view
    of that filesystem and fails closed (T5-SEC-003); genuine separate
    superblocks (tmpfs, other partitions) stay admissible.
    """
    identities: dict[tuple[int, int], str] = {}
    for (role, label, path), fd in zip(rows, fds):
        st = os.fstat(fd)
        identity = (st.st_dev, st.st_ino)
        if identity in identities:
            raise LaunchFsError(
                f"duplicate opened root identity for {label!r}: {path!r} "
                f"and {identities[identity]!r}"
            )
        identities[identity] = path
    write_pairs = [
        (role, label, path, fd)
        for (role, label, path), fd in zip(rows, fds)
        if role == "write"
    ]
    guarded_pairs = [
        (role, label, path, fd)
        for (role, label, path), fd in zip(rows, fds)
        if role in ("protected", "read")
    ]
    for _wrole, wlabel, wpath, wfd in write_pairs:
        for _grole, glabel, gpath, gfd in guarded_pairs:
            if _fd_is_descendant(gfd, wfd) or _fd_is_descendant(wfd, gfd):
                raise LaunchFsError(
                    f"write root {wlabel}={wpath!r} overlaps opened {glabel} root {gpath!r}"
                )
            if _fd_is_same_superblock(wfd, gfd) and (
                _mount_id_for_path(wpath) != _mount_id_for_path(gpath)
            ):
                raise LaunchFsError(
                    f"write root {wlabel}={wpath!r} is a bind-mounted alias view "
                    f"of the {glabel} root's filesystem ({gpath!r})"
                )
    for index, (_wrole, wlabel, wpath, wfd) in enumerate(write_pairs):
        for _orole, olabel, opath, ofd in write_pairs[index + 1:]:
            if _fd_is_descendant(ofd, wfd) or _fd_is_descendant(wfd, ofd):
                raise LaunchFsError(
                    f"write root {wlabel}={wpath!r} overlaps opened write root "
                    f"{olabel}={opath!r}"
                )
