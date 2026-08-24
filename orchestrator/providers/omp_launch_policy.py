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


def _fd_is_same_superblock(fd_a: int, fd_b: int) -> bool:
    return os.fstat(fd_a).st_dev == os.fstat(fd_b).st_dev


def _fd_mount_id(fd: int) -> int:
    """``stx_mnt_id`` of the RETAINED fd via libc statx(fd, "", AT_EMPTY_PATH).

    No pathname and no /proc lookup: the mount identity is read from the
    already-opened directory object itself, so a mount-capable process that
    swapped the pathname cannot make the check report a covering ordinary
    mount while the fd still names the protected subtree. Kernels without
    STATX_MNT_ID fail closed (the helper already requires Landlock ABI 3,
    i.e. kernel >= 5.13, where the field is guaranteed).
    """
    import ctypes

    class _StatxTimestamp(ctypes.Structure):
        _fields_ = [("tv_sec", ctypes.c_int64), ("tv_nsec", ctypes.c_uint32)]

    class _Statx(ctypes.Structure):
        _fields_ = [
            ("stx_mask", ctypes.c_uint32),
            ("stx_blksize", ctypes.c_uint32),
            ("stx_attributes", ctypes.c_uint64),
            ("stx_nlink", ctypes.c_uint32),
            ("stx_uid", ctypes.c_uint32),
            ("stx_gid", ctypes.c_uint32),
            ("stx_mode", ctypes.c_uint16),
            ("__spare0", ctypes.c_uint16),
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
            ("__spare3", ctypes.c_uint64 * 12),
        ]

    libc = ctypes.CDLL(None, use_errno=True)
    buf = _Statx()
    rc = libc.syscall(
        332,  # SYS_statx (x86_64)
        fd,
        "",
        0x1000,  # AT_EMPTY_PATH
        0x1000,  # STATX_MNT_ID
        ctypes.byref(buf),
    )
    if rc != 0:
        raise LaunchFsError(
            f"statx on the retained root fd failed: {ctypes.get_errno()}"
        )
    if not (buf.stx_mask & 0x1000):
        raise LaunchFsError("kernel cannot report mount ids for the retained root fd")
    return buf.stx_mnt_id


def verify_root_identity_relations(
    rows: list[tuple[str, str, str]],
    fds: list[int],
) -> None:
    """Reject duplicate opened identities, root nesting, and bind aliases.

    Every root was already opened no-follow; this binds the identity
    relations: two roots must not be the same directory, a write root must
    not equal or contain (or be contained in) a protected or read root, and
    two write roots must not be in an ancestor/descendant relation (e.g.
    ``state`` nested below ``data``). EVERY pair involving a write root
    (write x guarded AND write x write, even with equal rights masks) must
    not be a bind-mounted alias view: same superblock but a DIFFERENT mount
    id read from the retained fd via statx fails closed; genuine separate
    superblocks (tmpfs, other partitions) short-circuit admissible.
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
    mount_ids: dict[int, int] = {}

    def _mount_id(fd: int) -> int:
        if fd not in mount_ids:
            mount_ids[fd] = _fd_mount_id(fd)
        return mount_ids[fd]

    for _wrole, wlabel, wpath, wfd in write_pairs:
        for _grole, glabel, gpath, gfd in guarded_pairs:
            if _fd_is_descendant(gfd, wfd) or _fd_is_descendant(wfd, gfd):
                raise LaunchFsError(
                    f"write root {wlabel}={wpath!r} overlaps opened {glabel} root {gpath!r}"
                )
            if _fd_is_same_superblock(wfd, gfd) and _mount_id(wfd) != _mount_id(gfd):
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
            if _fd_is_same_superblock(wfd, ofd) and _mount_id(wfd) != _mount_id(ofd):
                raise LaunchFsError(
                    f"write root {wlabel}={wpath!r} is a bind-mounted alias view "
                    f"of the {olabel} root's filesystem ({opath!r})"
                )
