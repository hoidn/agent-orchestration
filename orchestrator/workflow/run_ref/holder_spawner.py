"""Profile pieces of the run-ref holder: argv, scope unit, launcher, spawner, leaf script.

Pure builders and checks used by `holder.py` (design D-a, D-b, D-g, D-d, R4,
R5, R7, F3b-1, F3b-2, N8):

- `holder_argv`: the one holder `bwrap` per incarnation (namespaces, the
  sealed rootfs and the sanitized `.git` by descriptor, sized tmpfs mounts,
  `/dev` and `/run` read-only, no `/sys`, `/proc/keys` and `/proc/key-users`
  masked by descriptor, the key-syscall filter by `--seccomp`).
- `unit_name` / `scope_properties`: the `systemd-run --user --scope` unit
  derived from the launch token digest and the policy limits.
- `launcher_source`: the gated launcher. It joins a fresh session keyring with
  the provider shim's `_join_fresh_session_keyring` (its source text, so the
  shim module itself never runs in the launcher), reports its pid, execs
  `bwrap` only after a line whose sha256 equals the token digest on its argv,
  and leaves the spawner only `/dev/null` and the kept descriptors.
- `SPAWNER`: the host-authored loop the image's `/bin/sh` runs as the spawner.
- `leaf_script` / `validate_leaf_request`: one leaf's `/run/runref/<leaf>/leaf.sh`.
- `spawner_attributes` / `attribute_drift`: the F3b-1 comparison.

Dependencies: the provider shim's constants and join function (read-only),
`/proc` of the host, Linux x86_64 syscalls `sched_getattr` and `ioprio_get`.
"""

from __future__ import annotations

import ctypes
import inspect
import math
import os
import posixpath
import re
import shlex
import struct
from collections.abc import Mapping
from pathlib import Path
from typing import cast

# Read-only use of the shim's private constants and join function (Ruling P26):
# the shim and its reviewed identity stay untouched.
from orchestrator.providers import provider_launch_shim as _shim

from .contracts import RUN_REF_CONFINEMENT_CONSTANTS_MIB
from .leaf import LeafRequest
from .runtime import RunRefRuntimeError

UNAVAILABLE = "run_ref_environment_unavailable"
PROFILE_MIB = dict(RUN_REF_CONFINEMENT_CONSTANTS_MIB)
GUEST_SH, GUEST_ENV, GUEST_SETSID = "/bin/sh", "/usr/bin/env", "/usr/bin/setsid"
SPAWNER_PATH = "/usr/local/bin:/usr/bin:/bin"
BWRAP = "/usr/bin/bwrap"
# Descriptor numbers the launcher hands to bwrap, in this order.
FD_CONTROL, FD_GATE, FD_INFO, FD_ROOTFS, FD_KEYS, FD_KEY_USERS, FD_SECCOMP, FD_GIT = range(3, 11)
RESERVED_RESULT_NAMES = frozenset({"stdout", "stderr"})
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_ENV_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")

SPAWNER = f'''echo ready >&3
while IFS= read -r leaf <&3; do
  (
    exec 3>&-
    IFS= read -r go <&4 || exit 125
    exec 4<&-
    [ "$go" = go ] || exit 125
    cd /workspace || exit 126
    exec {GUEST_SETSID} {GUEST_SH} "/run/runref/$leaf/leaf.sh" </dev/null >"/result/$leaf/stdout" 2>"/result/$leaf/stderr"
  ) &
  echo "ack $!" >&3
  wait $!
  echo "status $?" >&3
done
'''


def require_x86_64(machine: str) -> None:
    """The key-syscall filter is x86_64-only, so the profile is too (F3b-2)."""
    if machine != "x86_64":
        raise RunRefRuntimeError(UNAVAILABLE, f"key_syscall_filter_architecture_unsupported:{machine}")


def key_syscall_filter_program() -> bytes:
    """`bwrap --seccomp` bytes of the shim's key-syscall filter, in the shim's instruction order.

    Built here from the shim's constants because the shim's reviewed identity is
    not changed by this profile (P26); a unit test proves byte equality with what
    `_install_key_syscall_filter` passes to prctl.
    """
    f, s = _shim._SockFilter, _shim
    instructions = [f(s._BPF_LD | s._BPF_W | s._BPF_ABS, 0, 0, 4),
                    f(s._BPF_JMP | s._BPF_JEQ | s._BPF_K, 1, 0, s._AUDIT_ARCH_X86_64),
                    f(s._BPF_RET | s._BPF_K, 0, 0, s._SECCOMP_RET_KILL_PROCESS),
                    f(s._BPF_LD | s._BPF_W | s._BPF_ABS, 0, 0, 0)]
    native = (s._X86_64_ADD_KEY, s._X86_64_REQUEST_KEY, s._X86_64_KEYCTL)
    for number in (*native, *(s._X32_SYSCALL_BIT | n for n in native)):
        instructions += [f(s._BPF_JMP | s._BPF_JEQ | s._BPF_K, 0, 1, number),
                         f(s._BPF_RET | s._BPF_K, 0, 0, s._EPERM_RESULT)]
    instructions.append(f(s._BPF_RET | s._BPF_K, 0, 0, s._SECCOMP_RET_ALLOW))
    return b"".join(bytes(instruction) for instruction in instructions)


def holder_argv(*, workspace_mib: int, runref_dir: str, git: bool,
                gateway_dir: str | None = None) -> list[str]:
    """The holder `bwrap` argv; descriptors are the `FD_*` numbers the launcher sets up."""
    def tmpfs(mib: int, target: str) -> list[str]:
        return ["--size", str(mib << 20), "--tmpfs", target]

    return [BWRAP, "--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-net", "--unshare-uts",
            "--unshare-cgroup", "--disable-userns", "--die-with-parent", "--new-session", "--cap-drop", "ALL",
            "--clearenv", "--setenv", "PATH", SPAWNER_PATH, "--setenv", "HOME", "/tmp",
            "--ro-bind-fd", str(FD_ROOTFS), "/",
            "--dev", "/dev", *tmpfs(PROFILE_MIB["dev-shm"], "/dev/shm"), "--remount-ro", "/dev",
            "--proc", "/proc",
            "--perms", "0000", "--ro-bind-data", str(FD_KEYS), "/proc/keys",
            "--perms", "0000", "--ro-bind-data", str(FD_KEY_USERS), "/proc/key-users",
            "--seccomp", str(FD_SECCOMP),
            *tmpfs(workspace_mib, "/workspace"),
            *(("--ro-bind-fd", str(FD_GIT), "/workspace/.git") if git else ()),
            *tmpfs(PROFILE_MIB["scratch"], "/tmp"),
            *tmpfs(PROFILE_MIB["result"], "/result"),
            "--tmpfs", "/run", "--ro-bind", runref_dir, "/run/runref",
            *(("--ro-bind", gateway_dir, "/run/runref-gateway", "--symlink", "runref-gateway/gateway.sock",
               "/run/gateway.sock") if gateway_dir is not None else ()),
            "--remount-ro", "/run",
            "--info-fd", str(FD_INFO), "--", GUEST_SH, "-c", SPAWNER]


def unit_name(token_digest_hex: str) -> str:
    return f"run-ref-{token_digest_hex[:16]}.scope"


def scope_properties(limits: Mapping[str, int]) -> list[str]:
    """Unit properties from the policy limits (D-a, R7)."""
    return [f"MemoryMax={limits['memory-mib'] << 20}", "MemorySwapMax=0", f"TasksMax={limits['pids']}",
            f"CPUQuota={limits['cpus'] * 100}%", "OOMPolicy=continue", "Delegate=yes"]


def expected_readback(limits: Mapping[str, int], control_group: str) -> tuple[dict[str, str], dict[str, str]]:
    """What `systemctl show` and the scope's cgroup files must read back before release."""
    unit = {"MemoryMax": str(limits["memory-mib"] << 20), "MemorySwapMax": "0", "TasksMax": str(limits["pids"]),
            "CPUQuotaPerSecUSec": f"{limits['cpus']}s", "OOMPolicy": "continue", "Delegate": "yes",
            "ControlGroup": control_group}
    files = {"memory.max": str(limits["memory-mib"] << 20), "memory.swap.max": "0",
             "pids.max": str(limits["pids"]), "cpu.max": f"{limits['cpus'] * 100000} 100000"}
    return unit, files


def launcher_source() -> str:
    """argv: launch fd, token sha256 hex, kept fds (csv), then the bwrap argv."""
    return "\n".join([
        "import ctypes, fcntl, hashlib, os, sys",
        f"_SYS_KEYCTL = {_shim._SYS_KEYCTL}",
        f"_KEYCTL_JOIN_SESSION_KEYRING = {_shim._KEYCTL_JOIN_SESSION_KEYRING}",
        inspect.getsource(_shim._join_fresh_session_keyring),
        _LAUNCHER_BODY,
    ])


_LAUNCHER_BODY = r'''
launch, digest, kept = int(sys.argv[1]), sys.argv[2], [int(fd) for fd in sys.argv[3].split(",")]
_join_fresh_session_keyring()
os.write(launch, b"%d\n" % os.getpid())
line = b""
while not line.endswith(b"\n") and len(line) < 256:
    chunk = os.read(launch, 1)
    if not chunk:
        os._exit(97)
    line += chunk
if hashlib.sha256(line.rstrip(b"\n")).hexdigest() != digest:
    os._exit(98)
high = [fcntl.fcntl(fd, fcntl.F_DUPFD, 100) for fd in kept]
null = os.open("/dev/null", os.O_RDWR)
for fd in (0, 1, 2):
    os.dup2(null, fd)
os.closerange(3, 100)
for target, fd in enumerate(high, start=3):
    os.dup2(fd, target)
os.closerange(3 + len(high), 65536)
os.execv(sys.argv[4], sys.argv[4:])
'''


def validate_leaf_request(request: LeafRequest) -> None:
    """Shape checks of a dispatch-built request; a violation is a caller bug (ValueError)."""
    if not isinstance(request.leaf_id, str) or not _NAME.match(request.leaf_id):
        raise ValueError("leaf_id must be a plain name")
    _validate_command(request.argv, request.env, request.cwd)
    _validate_bounds(request)
    for name, data in request.input_files.items():
        if not _NAME.match(name) or name in RESERVED_RESULT_NAMES or not isinstance(data, bytes):
            raise ValueError("input file name or content is invalid")
    if request.network not in ("none", "model-only"):
        raise ValueError("network must be none or model-only")


def _validate_command(argv: tuple[str, ...], env: Mapping[str, str], cwd: str) -> None:
    if not argv or any(not isinstance(arg, str) or "\0" in arg for arg in argv):
        raise ValueError("argv must be non-empty text without NUL")
    if not argv[0].startswith("/") or "=" in argv[0]:
        raise ValueError("argv[0] must be an absolute guest path without '='")
    for name, value in env.items():
        if not _ENV_NAME.match(name) or not isinstance(value, str) or "\0" in value:
            raise ValueError("environment entry is invalid")
    if posixpath.normpath(cwd) != cwd or not (cwd == "/workspace" or cwd.startswith("/workspace/")):
        raise ValueError("cwd must be a normalized path under /workspace")


def _validate_bounds(request: LeafRequest) -> None:
    timeout = request.timeout_sec
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout < math.inf:
        raise ValueError("timeout_sec must be positive and finite")
    for limit in (request.stdout_limit, request.stderr_limit):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("output limits must be non-negative integers")


def leaf_script(request: LeafRequest) -> str:
    """`cd` into the guest cwd, then exec argv under exactly `request.env` through the pinned env."""
    assignments = [shlex.quote(f"{name}={value}") for name, value in sorted(request.env.items())]
    command = " ".join([GUEST_ENV, "-i", "--", *assignments, *map(shlex.quote, request.argv)])
    return f"cd -- {shlex.quote(request.cwd)} || exit 126\nexec {command}\n"


# -- F3b-1 spawner attributes -------------------------------------------------
_SYS_SCHED_GETATTR, _SYS_IOPRIO_GET, _IOPRIO_WHO_PROCESS = 315, 252, 1
_SCHED_ATTR = struct.Struct("=IIQiIQQQII")
_libc = ctypes.CDLL(None, use_errno=True)


def _syscall(*args: int) -> int:
    result = _libc.syscall(*(ctypes.c_long(arg) for arg in args))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    return result


def _sched_getattr(pid: int) -> tuple[int, ...]:
    buffer = ctypes.create_string_buffer(_SCHED_ATTR.size)
    result = _libc.syscall(ctypes.c_long(_SYS_SCHED_GETATTR), ctypes.c_long(pid), buffer,
                           ctypes.c_long(_SCHED_ATTR.size), ctypes.c_long(0))
    if result < 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))
    _size, policy, flags, _nice, priority, *_deadline, util_min, util_max = _SCHED_ATTR.unpack(buffer.raw)
    return policy, priority, flags, util_min, util_max


def parse_cpu_list(text: str) -> frozenset[int]:
    cpus: set[int] = set()
    for part in filter(None, text.strip().split(",")):
        low, _, high = part.partition("-")
        cpus.update(range(int(low), int(high or low) + 1))
    return frozenset(cpus)


def spawner_attributes(pid: int) -> dict[str, object]:
    """The F3b-1 attributes a same-uid leaf can change on the spawner and later leaves inherit."""
    proc = Path(f"/proc/{pid}")
    status = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line)
    return {"limits": (proc / "limits").read_text(),
            "nice": os.getpriority(os.PRIO_PROCESS, pid),
            "oom_score_adj": (proc / "oom_score_adj").read_text().strip(),
            "cpus_allowed": parse_cpu_list(status["Cpus_allowed_list"]),
            "sched_getattr": _sched_getattr(pid),
            "ioprio": _syscall(_SYS_IOPRIO_GET, _IOPRIO_WHO_PROCESS, pid),
            "coredump_filter": (proc / "coredump_filter").read_text().strip()}


def attribute_drift(ready: Mapping[str, object], now: Mapping[str, object],
                    effective_cpus: frozenset[int] | None) -> str | None:
    """Name of the first attribute changed since ready, or None.

    Affinity is relative to the scope's effective cpuset (Task 6 note N1): only a
    mask narrower than the ready mask within the current effective cpuset is
    drift; a shrinking effective cpuset alone is not.
    """
    for name in ready:
        if name == "cpus_allowed":
            ready_cpus, now_cpus = cast(frozenset[int], ready[name]), cast(frozenset[int], now[name])
            if not (ready_cpus if effective_cpus is None else ready_cpus & effective_cpus) <= now_cpus:
                return name
        elif ready[name] != now[name]:
            return name
    return None
