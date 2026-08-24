"""Landlock ABI-3 write confinement exec helper (Task 5, OMP-I1).

Dependency-free Linux helper for one private OMP launch. Grammar::

    python -m orchestrator.providers.omp_write_confinement \
        --abi N --digest H \
        --protected <label>=<path> ... \
        --write <role>=<path> ... \
        [--read <role>=<path> ...] \
        -- <private-argv...>

    python -m orchestrator.providers.omp_write_confinement \
        --exec-only -- <private-argv...>

The first mode requires Landlock ABI 3 or newer (queried directly), sets
``no_new_privs``, admits only no-follow-opened existing directory roots,
rejects any write root overlapping protected/read roots or another write
root, installs the role-labelled write allowlist from the same still-open
root fds, verifies the private target is a digest-named copy rehashed from
the inherited no-follow private target fd, compares the code-owned fresh
session identity carrier against the retained session-root fd, strips the
internal carriers from the environment, and then ``execve``-replaces itself
with the private OMP argv. The ``--exec-only`` mode skips Landlock entirely
(ambient lanes stay unconfined) but still opens the private target no-follow
and rehashes it on the same fd before ``execve``.
Every root and the target fd are reopened/recomputed: a digest, root, fd,
identity, or target mismatch fails before restriction/exec.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import sys

from .omp_launch_fs import (
    LaunchFsError,
    directory_identity,
    open_dir_no_follow,
    open_private_exec_fd,
)
from .omp_launch_policy import (
    strip_omp_carriers,
    verify_root_identity_relations,
    verify_session_identity,
)

SCHEMA_VERSION = "omp_write_confinement.v1"
MIN_LANDLOCK_ABI = 3

# Mutation-only ABI-3 filesystem set (this kernel family's UAPI layout):
# WRITE_FILE|REMOVE_DIR|REMOVE_FILE|MAKE_CHAR|MAKE_DIR|MAKE_REG|MAKE_SOCK|
# MAKE_FIFO|MAKE_BLOCK|MAKE_SYM|REFER|TRUNCATE. Reads and execution stay
# unhandled (permitted everywhere), so the allowlist is a pure write
# confinement.
MUTATION_FS_RIGHTS = 0x7FF2


def role_rights(role: str, label: str) -> int:
    """Deterministic per-root rights; shared by adapter, parent, and helper."""
    if role == "write":
        return MUTATION_FS_RIGHTS
    if role in ("protected", "read"):
        return 0
    raise ConfinementError(f"unknown root role {role!r}")

# Fixed protected runtime roots for the dynamically linked pinned binary and
# the python interpreter that launches it. Usrmerge symlinks (/bin -> /usr/bin)
# are resolved ONCE at import to their real targets, so the component-wise
# no-follow walk below never encounters a symlink component.
SYSTEM_RUNTIME_ROOTS = tuple(
    dict.fromkeys(
        os.path.realpath(root)
        for root in (
            "/bin",
            "/usr/bin",
            "/lib64",
            "/lib/x86_64-linux-gnu",
            "/usr/lib/x86_64-linux-gnu",
            "/usr/lib",
        )
    )
)

_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_ADD_RULE = 445
_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_RULE_PATH_BENEATH = 1
_LANDLOCK_CREATE_RULESET_VERSION = 1
_PR_SET_NO_NEW_PRIVS = 38


class ConfinementError(Exception):
    """Fatal confinement setup failure; the child must never run."""


class _RulesetAttr(ctypes.Structure):
    _fields_ = [
        ("handled_access_fs", ctypes.c_uint64),
        ("scoped", ctypes.c_uint64),
    ]


class _PathBeneath(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int),
    ]


def landlock_abi() -> int:
    """Return the running kernel's Landlock ABI via the direct VERSION query."""
    libc = ctypes.CDLL(None, use_errno=True)
    version = libc.syscall(
        _LANDLOCK_CREATE_RULESET,
        None,
        0,
        _LANDLOCK_CREATE_RULESET_VERSION,
    )
    return int(version) if version >= 0 else 0


def _validate_exact_mask() -> None:
    """Fail closed unless the kernel accepts the exact ABI-3 mutation mask."""
    libc = ctypes.CDLL(None, use_errno=True)
    probe = _RulesetAttr(MUTATION_FS_RIGHTS, 0)
    fd = libc.syscall(
        _LANDLOCK_CREATE_RULESET,
        ctypes.byref(probe),
        ctypes.sizeof(probe),
        0,
    )
    if fd < 0:
        raise ConfinementError("kernel rejects the exact ABI-3 mutation mask")
    os.close(fd)


def _path_is_within(path: str, root: str) -> bool:
    """Lexical containment of ``path`` at/under ``root`` (both absolute).

    Used only to decide the deterministic write-role set shared by the
    adapter and the parent expectation (fresh conf coalescing); the actual
    overlap rejection runs on no-follow-opened identities.
    """
    try:
        return os.path.commonpath([path, root]) == os.path.normpath(root)
    except ValueError:
        return False


def profile_root_sets(
    *,
    lane: str,
    home_omp: str,
    session_dir: str | None,
    conf_root: str | None,
    workspace: str,
    empty_cwd: str,
    env_roots: dict[str, str],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]], list[tuple[str, str]]]:
    """Return the deterministic (protected, write, read) role-labelled roots.

    Both the adapter and the parent expectation derive the policy digest from
    this same function so the helper's recomputation can never drift.
    """
    protected = [("omp-home", home_omp)]
    protected += [("system-runtime", root) for root in SYSTEM_RUNTIME_ROOTS]
    write: list[tuple[str, str]] = []
    for role in ("data", "state", "cache", "temp"):
        value = env_roots.get(role)
        if not value:
            raise ConfinementError(f"missing {role} write root")
        write.append((role, value))
    # Fresh conf: the canonical live-session dir commonly lives beneath the
    # admitted conf-workspace write root (runs/<id>/provider_sessions). A
    # separate Landlock `session` rule would overlap that root; the workspace
    # authority already permits the journal writes, so coalesce: omit the
    # redundant session rule (identity/path/visit/journal binding still
    # happens in the parent expectation and adapter frame). Fresh lanes
    # without workspace authority keep the explicit session role.
    if session_dir is not None and not (
        lane == "conf"
        and workspace
        and _path_is_within(session_dir, workspace)
    ):
        write.append(("session", session_dir))
    if lane == "conf":
        write.append(("conf-workspace", workspace))
    read: list[tuple[str, str]] = []
    if conf_root is not None:
        read.append(("conf", conf_root))
    read.append(("cwd", empty_cwd))
    return protected, write, read


def canonical_policy_digest(
    *,
    lane: str,
    home_omp: str,
    session_dir: str | None,
    conf_root: str | None,
    workspace: str,
    empty_cwd: str,
    env_roots: dict[str, str],
) -> str:
    """Return the canonical policy digest binding rights, roles, and identities."""
    protected, write, read = profile_root_sets(
        lane=lane,
        home_omp=home_omp,
        session_dir=session_dir,
        conf_root=conf_root,
        workspace=workspace,
        empty_cwd=empty_cwd,
        env_roots=env_roots,
    )
    root_rows = []
    for role, label, path in _role_path_rows(protected, write, read):
        try:
            dev, ino = directory_identity(path)
        except LaunchFsError as exc:
            raise ConfinementError(str(exc)) from exc
        root_rows.append(
            {
                "label": label,
                "path": path,
                "dev": dev,
                "ino": ino,
                "rights": role_rights(role, label),
            }
        )
    root_rows.sort(key=lambda row: (row["label"], row["path"]))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "abi": MIN_LANDLOCK_ABI,
        "handled_access_fs": MUTATION_FS_RIGHTS,
        "roots": root_rows,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_args(argv: list[str]) -> dict:
    expected = {
        "abi": None,
        "digest": None,
        "protected": [],
        "write": [],
        "read": [],
        "target": None,
    }
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg in ("--abi", "--digest") and index + 1 < len(argv):
            expected[arg[2:]] = argv[index + 1]
            index += 2
        elif arg in ("--protected", "--write", "--read") and index + 1 < len(argv):
            expected[arg[2:]].append(argv[index + 1])
            index += 2
        elif arg == "--":
            expected["target"] = argv[index + 1:]
            break
        else:
            raise ConfinementError(f"unexpected helper argument: {arg!r}")
    return expected


def _parse_labeled(values: list[str], kind: str) -> list[tuple[str, str]]:
    rows = []
    for value in values:
        label, separator, path = value.partition("=")
        if not separator or not label or not path:
            raise ConfinementError(f"invalid {kind} root: {value!r}")
        rows.append((label, path))
    return rows


def _role_path_rows(
    protected: list[tuple[str, str]],
    write: list[tuple[str, str]],
    read: list[tuple[str, str]],
) -> list[tuple[str, str, str]]:
    """Flatten role-labelled groups into (role, label, path) triples."""
    rows: list[tuple[str, str, str]] = []
    rows += [("protected", label, path) for label, path in protected]
    rows += [("write", label, path) for label, path in write]
    rows += [("read", label, path) for label, path in read]
    return rows


def _restrict_and_exec(
    *,
    rows: list[tuple[str, str, str]],
    fds: list[int],
    target: list[str],
    exec_fd: int,
) -> int:
    """Install the Landlock ruleset from the still-open root fds and exec the
    verified private target fd (internal carriers stripped first)."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0:
        raise ConfinementError("prctl(PR_SET_NO_NEW_PRIVS) failed")
    attr = _RulesetAttr(MUTATION_FS_RIGHTS, 0)
    ruleset = libc.syscall(
        _LANDLOCK_CREATE_RULESET,
        ctypes.byref(attr),
        ctypes.sizeof(attr),
        0,
    )
    if ruleset < 0:
        raise ConfinementError("landlock_create_ruleset failed")
    for (role, label, _), fd in zip(rows, fds):
        rights = role_rights(role, label)
        if not rights:
            continue
        beneath = _PathBeneath(rights, fd)
        rc = libc.syscall(
            _LANDLOCK_ADD_RULE,
            ruleset,
            _LANDLOCK_RULE_PATH_BENEATH,
            ctypes.byref(beneath),
            0,
        )
        if rc != 0:
            raise ConfinementError(f"landlock_add_rule failed for {label}: {ctypes.get_errno()}")
    rc = libc.syscall(_LANDLOCK_RESTRICT_SELF, ruleset, 0)
    if rc != 0:
        raise ConfinementError(f"landlock_restrict_self failed: {ctypes.get_errno()}")
    strip_omp_carriers(os.environ)
    try:
        os.execve(exec_fd, target, os.environ)
    except OSError as exc:
        raise ConfinementError(f"exec of the private target failed: {exc}") from exc
    return 1  # pragma: no cover


def _exec_only_main(argv: list[str]) -> int:
    """Ambient fd-exec route: verify the private target on the opened fd and
    exec it without any Landlock confinement (ambient lanes stay unconfined).
    The same no-follow private-parent verification, same-fd hash, and same-fd
    execve apply, so a swapped copy fails closed exactly like the confined
    path; internal carriers are stripped before exec."""
    if argv[:1] != ["--"]:
        raise ConfinementError("--exec-only requires a '-- <private-argv>' separator")
    target = argv[1:]
    try:
        exec_fd = open_private_exec_fd(target)
    except LaunchFsError as exc:
        raise ConfinementError(str(exc)) from exc
    strip_omp_carriers(os.environ)
    try:
        os.execve(exec_fd, target, os.environ)
    except OSError as exc:
        raise ConfinementError(f"exec of the private target failed: {exc}") from exc
    return 1  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    """Run the confinement helper; returns an exit code (never execs on error)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        if argv[:1] == ["--exec-only"]:
            return _exec_only_main(argv[1:])
        parsed = _parse_args(argv)
        abi_text = parsed["abi"]
        digest = parsed["digest"]
        if not isinstance(abi_text, str) or not abi_text.isdigit():
            raise ConfinementError("expected --abi N")
        required_abi = int(abi_text)
        if required_abi != MIN_LANDLOCK_ABI:
            raise ConfinementError(
                f"requires exactly Landlock ABI {MIN_LANDLOCK_ABI}"
            )
        available = landlock_abi()
        if available < required_abi:
            raise ConfinementError(
                f"Landlock ABI {required_abi} required, kernel has {available}"
            )
        _validate_exact_mask()
        if not isinstance(digest, str) or len(digest) != 64:
            raise ConfinementError("expected a 64-hex --digest")
        protected = _parse_labeled(parsed["protected"], "protected")
        write = _parse_labeled(parsed["write"], "write")
        read = _parse_labeled(parsed["read"], "read")
        target = parsed["target"]
        if target is None:
            raise ConfinementError("missing -- separator before the private OMP argv")
        if not protected:
            raise ConfinementError("missing fixed protected roots")
        roles = [role for role, _ in write]
        if roles.count("data") != 1 or roles.count("state") != 1 or roles.count("cache") != 1 or roles.count("temp") != 1:
            raise ConfinementError("write roles require exactly one each of data/state/cache/temp")
        if len(roles) != len(set(roles)):
            raise ConfinementError("duplicate write role")
        if any(role not in ("data", "state", "cache", "temp", "session", "conf-workspace") for role in roles):
            raise ConfinementError("unknown write role")
        read_roles = [role for role, _ in read]
        if any(role not in ("conf", "cwd") for role in read_roles):
            raise ConfinementError("unknown read role")
        try:
            exec_fd = open_private_exec_fd(target)
        except LaunchFsError as exc:
            raise ConfinementError(str(exc)) from exc
        rows = _role_path_rows(protected, write, read)
        try:
            root_fds = [open_dir_no_follow(path) for _, _, path in rows]
        except LaunchFsError as exc:
            raise ConfinementError(str(exc)) from exc
        try:
            # Identity relations bind the no-follow-opened roots: duplicate
            # (dev, ino) identities, write/protected-read nesting, and
            # bind-mounted alias views fail; the fresh session identity
            # carrier must match the retained session-root fd (or the
            # carrier-named visit dir for coalesced conf lanes).
            verify_root_identity_relations(rows, root_fds)
            verify_session_identity(rows, root_fds, os.environ)
            computed = _recompute_digest(protected, write, read, required_abi, root_fds)
            if computed != digest:
                raise ConfinementError("canonical policy digest does not match --digest")
            return _restrict_and_exec(rows=rows, fds=root_fds, target=target, exec_fd=exec_fd)
        except LaunchFsError as exc:
            raise ConfinementError(str(exc)) from exc
        finally:
            for fd in root_fds:
                os.close(fd)
    except ConfinementError as exc:
        sys.stderr.write(f"omp_write_confinement: {exc}\n")
        return 2


def _recompute_digest(
    protected: list[tuple[str, str]],
    write: list[tuple[str, str]],
    read: list[tuple[str, str]],
    abi: int,
    fds: list[int],
) -> str:
    root_rows = []
    for fd, (role, label, path) in zip(fds, _role_path_rows(protected, write, read)):
        st = os.fstat(fd)
        root_rows.append(
            {
                "label": label,
                "path": path,
                "dev": st.st_dev,
                "ino": st.st_ino,
                "rights": role_rights(role, label),
            }
        )
    root_rows.sort(key=lambda row: (row["label"], row["path"]))
    payload = {
        "schema_version": SCHEMA_VERSION,
        "abi": abi,
        "handled_access_fs": MUTATION_FS_RIGHTS,
        "roots": root_rows,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
