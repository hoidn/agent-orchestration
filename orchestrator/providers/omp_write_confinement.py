"""Landlock ABI-3 write confinement exec helper (Task 5, OMP-I1).

Dependency-free Linux helper that confines one private OMP launch. Grammar::

    python -m orchestrator.providers.omp_write_confinement \
        --abi N --digest H \
        --protected <label>=<path> ... \
        --write <role>=<path> ... \
        [--read <role>=<path> ...] \
        -- <private-argv...>

It requires Landlock ABI 3 or newer, sets ``no_new_privs``, admits only
no-follow-opened existing directory roots, rejects any write root containing
the runtime conf/snapshot/empty cwd, installs the role-labelled write
allowlist, verifies the target is a private digest-named copy, and then
``execve``-replaces itself with the private OMP argv. Every root is reopened
and every value recomputed: a digest, root, or target mismatch fails before
restriction/exec.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import os
import stat
import sys

SCHEMA_VERSION = "omp_write_confinement.v1"
MIN_LANDLOCK_ABI = 3

# Mutation-only ABI-3 filesystem set (kernel 6.2+ UAPI layout):
# WRITE_FILE|REMOVE_DIR|REMOVE_FILE|MAKE_CHAR|MAKE_DIR|MAKE_REG|MAKE_SOCK|
# MAKE_FIFO|MAKE_BLOCK|MAKE_SYM|REFER|TRUNCATE. This is the full set of
# mutation bits handled by the ruleset; reads and execution stay unhandled
# (permitted everywhere), so the allowlist is a pure write confinement.
MUTATION_FS_RIGHTS = 0x77F2


def role_rights(role: str, label: str) -> int:
    """Derive the deterministic per-root rights for a role-labelled root.

    Shared by the adapter (policy digest), the parent expectation, and the
    helper's recomputation so the digest binds exactly the rights installed.
    Only write roots carry the full mutation allowlist; protected/read roots
    are bound by identity but grant nothing (their reads and execs are
    unhandled and therefore permitted).
    """
    if role == "write":
        return MUTATION_FS_RIGHTS
    if role in ("protected", "read"):
        return 0
    raise ConfinementError(f"unknown root role {role!r}")

# Fixed protected runtime roots for the dynamically linked pinned binary and
# the python interpreter that launches it.
SYSTEM_RUNTIME_ROOTS = (
    "/bin",
    "/usr/bin",
    "/lib64",
    "/lib/x86_64-linux-gnu",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib",
)

_LANDLOCK_CREATE_RULESET = 444
_LANDLOCK_ADD_RULE = 445
_LANDLOCK_RESTRICT_SELF = 446
_LANDLOCK_RULE_PATH_BENEATH = 1
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
    """Return the running kernel's Landlock ABI (0 when unavailable)."""
    libc = ctypes.CDLL(None, use_errno=True)
    # Supported handled bits grow by ABI (kernel 6.2+ UAPI layout): ABI-1
    # (0x1FFF = EXECUTE..MAKE_SYM), ABI-2 adds REFER|TRUNCATE (0x7FFF), ABI-4
    # adds IOCTL_DEV (0xFFFF). ABI-3 adds no new mask bits, so an ABI-3 kernel
    # is conservatively reported as ABI-2; the helper then fails closed for
    # --abi 3 on those 2023-era kernels.
    abi = 0
    for candidate, bits in (
        (1, 0x1FFF),
        (2, 0x7FFF),
        (4, 0xFFFF),
    ):
        probe = _RulesetAttr(bits, 0)
        probe_fd = libc.syscall(
            _LANDLOCK_CREATE_RULESET,
            ctypes.byref(probe),
            ctypes.sizeof(probe),
            0,
        )
        if probe_fd < 0:
            break
        os.close(probe_fd)
        abi = candidate
    return abi


def _root_identity(path: str) -> tuple[int, int]:
    """Return the no-follow-opened directory (dev, ino) identity."""
    resolved = os.path.realpath(path)  # usrmerge: /bin -> /usr/bin, /lib64 -> /usr/lib64
    fd = os.open(resolved, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        st = os.fstat(fd)
    finally:
        os.close(fd)
    if not stat.S_ISDIR(st.st_mode):
        raise ConfinementError(f"root is not a directory: {path!r}")
    return st.st_dev, st.st_ino


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
    if session_dir is not None:
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
        dev, ino = _root_identity(path)
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
        if arg == "--abi" and index + 1 < len(argv):
            expected["abi"] = argv[index + 1]
            index += 2
        elif arg == "--digest" and index + 1 < len(argv):
            expected["digest"] = argv[index + 1]
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


def _reject_container_roots(write: list[tuple[str, str]], excluded: list[str]) -> None:
    """Reject any write root containing the runtime conf/snapshot/empty cwd."""
    for role, root in write:
        normalized_root = os.path.normpath(root)
        for candidate in excluded:
            normalized = os.path.normpath(candidate)
            try:
                inside = os.path.commonpath([normalized_root, normalized]) == normalized_root
            except ValueError:
                inside = False
            if inside:
                raise ConfinementError(
                    f"write root {role}={root!r} contains runtime path {candidate!r}"
                )


def _verify_private_target(target: list[str]) -> None:
    """Reject any non-private target: the copy must sit in a 64-hex digest-named
    directory whose name equals the whole-file SHA-256 of the target itself."""
    if not target:
        raise ConfinementError("missing private OMP target after --")
    binary = target[0]
    if not os.path.isabs(binary):
        raise ConfinementError("private OMP target must be absolute")
    digest_dir = os.path.basename(os.path.dirname(binary))
    if len(digest_dir) != 64 or any(char not in "0123456789abcdef" for char in digest_dir):
        raise ConfinementError("private OMP target is not under a digest-named copy directory")
    try:
        with open(binary, "rb") as handle:
            actual = hashlib.sha256(handle.read()).hexdigest()
    except OSError as exc:
        raise ConfinementError(f"private OMP target is unreadable: {exc}") from exc
    if actual != digest_dir:
        raise ConfinementError("private OMP target digest does not match its digest directory")


def _restrict_and_exec(
    *,
    abi: int,
    protected: list[tuple[str, str]],
    write: list[tuple[str, str]],
    read: list[tuple[str, str]],
    target: list[str],
) -> int:
    """Install the Landlock ruleset and execve the private target."""
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

    def add(root: str, rights: int) -> None:
        fd = os.open(
            os.path.realpath(root),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        try:
            beneath = _PathBeneath(rights, fd)
            rc = libc.syscall(
                _LANDLOCK_ADD_RULE,
                ruleset,
                _LANDLOCK_RULE_PATH_BENEATH,
                ctypes.byref(beneath),
                0,
            )
        finally:
            os.close(fd)
        if rc != 0:
            raise ConfinementError(
                f"landlock_add_rule failed for {root!r}: {ctypes.get_errno()}"
            )

    for role, label, root in _role_path_rows(protected, write, read):
        rights = role_rights(role, label)
        if rights:
            add(root, rights)

    rc = libc.syscall(_LANDLOCK_RESTRICT_SELF, ruleset, 0)
    if rc != 0:
        raise ConfinementError(
            f"landlock_restrict_self failed: {ctypes.get_errno()}"
        )
    try:
        os.execve(target[0], target, os.environ)
    except OSError as exc:
        raise ConfinementError(f"execve failed: {exc}") from exc
    return 1  # pragma: no cover


def main(argv: list[str] | None = None) -> int:
    """Run the confinement helper; returns an exit code (never execs on error)."""
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
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
        excluded = [path for _, path in read] + [os.getcwd()]
        _reject_container_roots(write, excluded)
        _verify_private_target(target)

        # Recompute the canonical digest over reopened identities.
        computed = _recompute_digest(protected, write, read, required_abi)
        if computed != digest:
            raise ConfinementError("canonical policy digest does not match --digest")
        return _restrict_and_exec(
            abi=required_abi,
            protected=protected,
            write=write,
            read=read,
            target=target,
        )
    except ConfinementError as exc:
        sys.stderr.write(f"omp_write_confinement: {exc}\n")
        return 2


def _recompute_digest(
    protected: list[tuple[str, str]],
    write: list[tuple[str, str]],
    read: list[tuple[str, str]],
    abi: int,
) -> str:
    root_rows = []
    for role, label, path in _role_path_rows(protected, write, read):
        dev, ino = _root_identity(path)
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
        "abi": abi,
        "handled_access_fs": MUTATION_FS_RIGHTS,
        "roots": root_rows,
    }
    canonical = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    sys.exit(main())
