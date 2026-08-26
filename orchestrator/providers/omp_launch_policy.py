"""Code-owned OMP launch admission and binding policy."""
from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import json
import os
import re

from .._common.safe_tree import remove_tree_contents
from .omp_launch_fs import (
    LaunchFsError,
    open_dir_no_follow,
    open_session_dir,
    profile_attempt_key,
)

EMPTY_CWD_ENV = "_OMP_I1_EMPTY_CWD"
SESSION_DIR_ENV = "_OMP_I1_SESSION_DIR"
SESSION_IDENTITY_ENV = "_OMP_I1_SESSION_DIR_IDENTITY"
SESSION_PATH_FD_ENV = "_OMP_I1_SESSION_PATH_FD"
ATTEMPT_FDS_ENV = "_OMP_I1_ATTEMPT_FDS"
CARRIER_ENV_NAMES = (
    EMPTY_CWD_ENV, SESSION_DIR_ENV, SESSION_IDENTITY_ENV,
    SESSION_PATH_FD_ENV, ATTEMPT_FDS_ENV,
)


def strip_omp_carriers(env: MutableMapping[str, str]) -> None:
    """Remove the code-owned carriers from an environment in place."""
    for name in CARRIER_ENV_NAMES:
        env.pop(name, None)


_EMPTY_CWD_CARRIER = re.compile(r"omp-empty-([0-9a-f]{16})(?:-([0-9a-f]+))?\Z")


def empty_omp_cwd_nonce(path: str, *, expected_key: str) -> str | None:
    """Return the validated nonce carried in an empty-cwd basename."""
    match = _EMPTY_CWD_CARRIER.fullmatch(os.path.basename(path))
    if match is None or match.group(1) != expected_key:
        raise LaunchFsError(
            f"empty OMP cwd carrier does not match the derived key: {path!r}"
        )
    return match.group(2)

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
    """Open the visit directory once and verify its prepared identity."""
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
    env: Mapping[str, str],
) -> None:
    """Match a fresh session root or retained path fd to its prepared identity."""
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
    value = env.get(SESSION_PATH_FD_ENV)
    try:
        st = os.fstat(int(value)) if value is not None else None
    except (OSError, TypeError, ValueError) as exc:
        raise LaunchFsError("invalid retained session path descriptor") from exc
    if st is None or (st.st_dev, st.st_ino) != expected:
        raise LaunchFsError(
            "fresh session directory identity does not match the prepared visit"
        )


def _fd_is_descendant(ancestor_fd: int, descendant_fd: int) -> bool:
    """Return whether one retained directory fd is at/beneath another."""
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
    """Read ``stx_mnt_id`` from one retained fd via ``AT_EMPTY_PATH``."""
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



def profile_attempt_roots(
    *,
    env_roots: dict[str, str],
    lane: str,
    workspace: str,
    session_dir: str | None,
    conf_root: str | None,
    nonce: str | None,
) -> dict[str, str]:
    """Return the deterministic path projection for one profile attempt."""
    key = profile_attempt_key(
        lane=lane, workspace=workspace, session_dir=session_dir,
        conf_root=conf_root, env_roots=env_roots,
    )
    base = os.path.join(
        env_roots["cache"], "omp-i1", "attempts",
        "omp-attempt-" + key + (f"-{nonce}" if nonce else ""),
    )
    return {
        "HOME": os.path.join(base, "home"),
        "XDG_CONFIG_HOME": os.path.join(base, "config"),
        "XDG_DATA_HOME": os.path.join(base, "data"),
        "XDG_STATE_HOME": os.path.join(base, "state"),
        "XDG_CACHE_HOME": os.path.join(base, "cache"),
        "TMPDIR": os.path.join(base, "tmp"),
    }


def attempt_env_roots(attempt: dict[str, str]) -> dict[str, str]:
    """The 4-key env_roots shape (data/state/cache/temp) of an attempt."""
    return {"data": attempt["XDG_DATA_HOME"], "state": attempt["XDG_STATE_HOME"],
            "cache": attempt["XDG_CACHE_HOME"], "temp": attempt["TMPDIR"]}


class ProfileAttemptAuthority:
    """Retained descriptor authority for one exclusive profile attempt."""

    def __init__(
        self,
        paths: dict[str, str],
        parent_fd: int,
        base_fd: int,
        root_fds: dict[str, int],
        omp_fd: int,
        agent_fd: int,
    ) -> None:
        self.paths = paths
        self.parent_fd = parent_fd
        self.base_fd = base_fd
        self.root_fds = root_fds
        self.omp_fd = omp_fd
        self.agent_fd = agent_fd
        self.base_name = os.path.basename(os.path.dirname(paths["HOME"]))
        self.path_fds = {
            **{paths[name]: fd for name, fd in root_fds.items() if name in paths},
            os.path.join(paths["HOME"], ".omp"): omp_fd}

    @property
    def descriptors(self) -> tuple[int, ...]:
        return (self.parent_fd, self.base_fd, *self.root_fds.values(),
                self.omp_fd, self.agent_fd)

    def carrier(self) -> str:
        return json.dumps(
            {"parent": self.parent_fd, "base": self.base_fd,
             "roots": self.root_fds, "omp": self.omp_fd,
             "agent": self.agent_fd},
            separators=(",", ":"), sort_keys=True)

    def _release(self, *, cleanup: bool) -> None:
        if self.base_fd < 0:
            return
        if cleanup:
            base_kind = os.fstat(self.base_fd)
            remove_tree_contents(self.base_fd)
            try:
                current = os.stat(
                    self.base_name,
                    dir_fd=self.parent_fd,
                    follow_symlinks=False,
                )
                if (current.st_dev, current.st_ino) == (
                    base_kind.st_dev,
                    base_kind.st_ino,
                ):
                    os.rmdir(self.base_name, dir_fd=self.parent_fd)
            except OSError:
                pass
        for descriptor in self.descriptors:
            os.close(descriptor)
        self.base_fd = -1

    def close(self) -> None:
        self._release(cleanup=True)

    def detach(self) -> None:
        self._release(cleanup=False)


def _private_child(parent_fd: int, name: str, *, exclusive: bool) -> int:
    try:
        os.mkdir(name, 0o700, dir_fd=parent_fd)
    except FileExistsError:
        if exclusive:
            raise LaunchFsError(f"attempt root already exists: {name!r}")
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
    except OSError as exc:
        raise LaunchFsError(f"attempt directory cannot be opened: {name!r}") from exc
    kind = os.fstat(descriptor)
    if kind.st_uid != os.geteuid() or kind.st_mode & 0o077:
        os.close(descriptor)
        raise LaunchFsError(
            f"attempt directory is not private current-user authority: {name!r}"
        )
    return descriptor


def create_profile_attempt_authority(attempt: dict[str, str]) -> ProfileAttemptAuthority:
    """Create the attempt exclusively and retain every writable root fd."""
    base = os.path.dirname(attempt["HOME"])
    attempts = os.path.dirname(base)
    cache_home = os.path.dirname(os.path.dirname(attempts))
    if attempts != os.path.join(cache_home, "omp-i1", "attempts"):
        raise LaunchFsError("attempt paths are outside the pinned cache shape")
    current = open_dir_no_follow(cache_home)
    base_fd = -1
    roots: dict[str, int] = {}
    omp_fd = agent_fd = -1
    try:
        for component in ("omp-i1", "attempts"):
            child = _private_child(current, component, exclusive=False)
            os.close(current)
            current = child
        base_fd = _private_child(
            current, os.path.basename(base), exclusive=True
        )
        for env_name, path in attempt.items():
            name = os.path.basename(path)
            if path != os.path.join(base, name):
                raise LaunchFsError("attempt child escaped its exclusive base")
            roots[env_name] = _private_child(base_fd, name, exclusive=True)
        for env_name in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            os.close(_private_child(roots[env_name], "omp", exclusive=True))
        omp_fd = _private_child(roots["HOME"], ".omp", exclusive=True)
        agent_fd = _private_child(omp_fd, "agent", exclusive=True)
        return ProfileAttemptAuthority(
            attempt, current, base_fd, roots, omp_fd, agent_fd
        )
    except BaseException:
        if base_fd >= 0:
            remove_tree_contents(base_fd)
            try:
                os.rmdir(os.path.basename(base), dir_fd=current)
            except OSError:
                pass
        for fd in (agent_fd, omp_fd, *roots.values(), base_fd, current):
            if fd >= 0:
                os.close(fd)
        raise


def inherited_profile_conf_fd(carrier: str) -> int | None:
    """Return the optional code-owned conf fd from an attempt carrier."""
    try:
        roots = json.loads(carrier)["roots"]
        descriptor = roots.get("__conf__")
        if descriptor is None:
            return None
        if not isinstance(descriptor, int) or descriptor < 3:
            raise ValueError
        os.fstat(descriptor)
        return descriptor
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as exc:
        raise LaunchFsError("invalid inherited profile conf descriptor") from exc

def adopt_profile_attempt_authority(
    attempt: dict[str, str], carrier: str
) -> ProfileAttemptAuthority:
    """Adopt the parent-prepared descriptor set inherited by this process."""
    try:
        payload = json.loads(carrier)
        if set(payload) != {"parent", "base", "roots", "omp", "agent"}:
            raise ValueError
        roots = payload["roots"]
        if set(roots) not in (set(attempt), set(attempt) | {"__conf__"}):
            raise ValueError
        descriptors = [
            payload["parent"],
            payload["base"],
            *roots.values(),
            payload["omp"],
            payload["agent"],
        ]
        if (
            not all(isinstance(fd, int) and fd >= 3 for fd in descriptors)
            or len(descriptors) != len(set(descriptors))
        ):
            raise ValueError
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise LaunchFsError("invalid profile attempt descriptor carrier") from exc
    authority = ProfileAttemptAuthority(
        attempt,
        payload["parent"],
        payload["base"],
        roots,
        payload["omp"],
        payload["agent"],
    )
    base = os.path.dirname(attempt["HOME"])
    links = [
        (authority.parent_fd, os.path.basename(base), authority.base_fd),
        *[
            (authority.base_fd, os.path.basename(path), roots[name])
            for name, path in attempt.items()
        ],
        (roots["HOME"], ".omp", authority.omp_fd),
        (authority.omp_fd, "agent", authority.agent_fd),
    ]
    try:
        for parent_fd, name, descriptor in links:
            kind = os.fstat(descriptor)
            current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                kind.st_uid != os.geteuid()
                or kind.st_mode & 0o077
                or (kind.st_dev, kind.st_ino)
                != (current.st_dev, current.st_ino)
            ):
                raise LaunchFsError("profile attempt descriptor identity mismatch")
        return authority
    except BaseException:
        authority.close()
        raise
