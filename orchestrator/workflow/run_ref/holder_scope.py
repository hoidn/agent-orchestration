"""Scope, launch, quiescence and teardown of one run-ref holder incarnation.

`HolderScope.launch()` (design D-a, D-e, F3b-2, R10): rehash the sealed rootfs
through its retained descriptor, start the gated launcher in a fresh
`systemd-run --user --scope` unit named from the launch token digest with the
policy limits and `OOMPolicy=continue` as unit properties, resolve the scope
from the launcher pid and validate it with the containment identity rules,
read the limits back, bind one `DurableLaunchReleaseGate` to the scope
identity, move the launcher into the `holder` slot, verify the scope root is
empty and only then send the exact release token; then wait for the spawner,
record the holder-slot members, open the tmpfs root descriptors and record the
F3b-1 spawner attributes. Every launch failure is a `RunRefRuntimeError`:
`run_ref_environment_unavailable` before release and until the spawner
reports ready (no guest code has run), `run_ref_environment_lost` or
`run_ref_environment_escape_rejected` after; the original error wins over a
teardown failure, which is attached as a note.

`require_quiescent()` and `check_spawner()` raise `HolderDeathError`;
`run_host_helper()` runs 6c's helper in the `host` slot through an exec
trampoline under a parent-death signal (N4). `stop()` kills and empties the
scope. Dependencies: user systemd manager with cpu/memory/pids delegation,
`/usr/bin/bwrap`, `systemctl`, x86_64, an admitted `SealedImage`, a private
control directory (release record and host-written leaf scripts).
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import platform
import secrets
import select
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from orchestrator.providers.isolation_backend import (
    CgroupV2ContainmentRoot,
    CgroupV2ContainmentSlot,
    DurableLaunchReleaseGate,
    ProviderIsolationBackendUnavailable,
    ProviderIsolationStateError,
)

from . import holder_spawner as profile
from .image_store import ImageStoreError, SealedImage
from .leaf import HolderDeath
from .runtime import RunRefRuntimeError

LOST = "run_ref_environment_lost"
ESCAPE = "run_ref_environment_escape_rejected"
UNAVAILABLE = profile.UNAVAILABLE
LAUNCH_SECONDS = 15.0
SLOT_EMPTY_SECONDS = 2.0
CGROUP_MOUNT = Path("/sys/fs/cgroup")
MOUNTS = ("workspace", "tmp", "dev/shm", "result")
CONTAINMENT_ERRORS = (ProviderIsolationStateError, ProviderIsolationBackendUnavailable)
_VANISHED = (errno.ENOENT, errno.ENODEV)  # a cgroup being removed fails its file ops with ENODEV

# Enter the host slot, then exec; the parent-death signal is re-checked against the parent pid
# so a controller that died between fork and prctl is not missed (N4, m5). PR_SET_PDEATHSIG fires
# when the *thread* that forked the helper exits, not the controller process: call
# `run_host_helper` from a thread that outlives the helper (the evaluated runtime's own thread).
HELPER_TRAMPOLINE = r'''
import ctypes, os, signal, sys
procs, parent = int(sys.argv[1]), int(sys.argv[2])
if ctypes.CDLL(None).prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
    os._exit(125)
os.write(procs, b"0\n")
os.close(procs)
os.execv(sys.argv[3], sys.argv[3:])
'''


class HolderDeathError(Exception):
    """The holder can no longer serve leaves; carries the `HolderDeath` the attempt fails with."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.death = HolderDeath(code, detail)


def memfd(data: bytes) -> int:
    fd = os.memfd_create("run-ref-holder")
    os.write(fd, data)
    os.lseek(fd, 0, os.SEEK_SET)
    return fd


def procs(cgroup: Path) -> set[int]:
    return {int(pid) for pid in (cgroup / "cgroup.procs").read_text().split()}


def populated(cgroup: Path) -> bool:
    try:
        return "populated 1" in (cgroup / "cgroup.events").read_text()
    except OSError as exc:
        if exc.errno in _VANISHED:
            return False
        raise


def kill_cgroup(cgroup: Path, timeout: float = 10.0) -> bool:
    """`cgroup.kill` and wait until unpopulated; a vanished cgroup is empty."""
    try:
        if populated(cgroup):
            (cgroup / "cgroup.kill").write_text("1")
    except OSError as exc:
        if exc.errno not in _VANISHED:
            raise
    deadline = time.monotonic() + timeout
    while populated(cgroup):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def process_state(pid: int) -> str:
    """The one-letter state from `/proc/<pid>/stat` (after the parenthesised command)."""
    return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[0]


def drain(fd: int, deadline: float) -> bytes:
    data = b""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError("holder info pipe did not close")
            chunk = os.read(fd, 4096)
            if not chunk:
                return data
            data += chunk
    finally:
        os.close(fd)


class HolderScope:
    """The delegated scope, its slots, the launcher process and the spawner channels of one holder."""

    def __init__(self, image: SealedImage, limits: Mapping[str, int], *, control_dir: Path,
                 git_dir_fd: int | None = None) -> None:
        self.image, self.limits, self.control_dir, self.git_dir_fd = image, dict(limits), control_dir, git_dir_fd
        self._token = secrets.token_hex(32)
        self.token_digest = hashlib.sha256(self._token.encode()).hexdigest()
        self.unit = profile.unit_name(self.token_digest)
        self.runref = control_dir / f"runref-{self.token_digest[:16]}"
        self.process: subprocess.Popen | None = None
        self.path: Path | None = None
        self.root: CgroupV2ContainmentRoot | None = None
        self.gate: DurableLaunchReleaseGate | None = None
        self.slots: dict[str, CgroupV2ContainmentSlot] = {}
        self.spawner_pid = 0
        self.readback: dict[str, dict[str, str]] = {}
        self.roots: dict[str, int] = {}
        self.recorded: set[int] = set()
        self.ctrl: socket.socket | None = None
        self.gate_socket: socket.socket | None = None
        self._ready_attributes: dict[str, object] = {}
        self._oom_kills = 0
        self._buffer = b""
        self._released = False
        self._stopped = False

    # -- launch -------------------------------------------------------------------------------
    def launch(self) -> None:
        try:
            self._launch()
        except BaseException as exc:
            error: BaseException = exc
            if isinstance(exc, Exception) and not isinstance(exc, RunRefRuntimeError):
                code = LOST if self._released else UNAVAILABLE
                error = RunRefRuntimeError(code, f"holder_launch_failed:{type(exc).__name__}:{exc}")
            try:
                self.stop()
            except Exception as teardown:  # the launch failure is the error to report
                error.add_note(f"teardown after the failed launch also failed: {teardown!r}")
            if error is exc:
                raise
            raise error from exc

    def _launch(self) -> None:
        profile.require_x86_64(platform.machine())
        try:
            self.image.rehash()
        except ImageStoreError as exc:
            raise RunRefRuntimeError(UNAVAILABLE, f"image_rehash_refused:{exc.detail}") from exc
        self.runref.mkdir(mode=0o700)
        launch_host, launch_guest = socket.socketpair()
        self.ctrl, ctrl_guest = socket.socketpair()
        self.gate_socket, gate_guest = socket.socketpair()
        info_read, info_write = os.pipe()
        owned = [memfd(b""), memfd(b""), memfd(profile.key_syscall_filter_program())]
        kept = [ctrl_guest.fileno(), gate_guest.fileno(), info_write, self.image.root_fd, *owned,
                *(() if self.git_dir_fd is None else (self.git_dir_fd,))]
        bwrap = profile.holder_argv(workspace_mib=self.limits["workspace-mib"], runref_dir=str(self.runref),
                                    git=self.git_dir_fd is not None)
        argv = ["systemd-run", "--user", "--scope", "--quiet", "--unit", self.unit,
                *(arg for prop in profile.scope_properties(self.limits) for arg in ("-p", prop)), "--",
                sys.executable, "-I", "-S", "-c", profile.launcher_source(), str(launch_guest.fileno()),
                self.token_digest, ",".join(map(str, kept)), *bwrap]
        try:
            try:
                self.process = subprocess.Popen(argv, pass_fds=(launch_guest.fileno(), *kept),
                                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                                stderr=subprocess.PIPE)
            finally:
                for fd in (launch_guest.detach(), ctrl_guest.detach(), gate_guest.detach(), info_write, *owned):
                    os.close(fd)
            with launch_host:  # closing it is EOF: an unreleased launcher exits without starting bwrap
                self._release(launch_host)
        except BaseException:
            os.close(info_read)
            raise
        self._await_ready(info_read)

    def _release(self, launch_host: socket.socket) -> None:
        """Everything before the token; a refusal here is `run_ref_environment_unavailable`."""
        assert self.process is not None
        launch_host.settimeout(LAUNCH_SECONDS)
        try:
            reported = int(launch_host.recv(64).split(b"\n")[0])
        except (OSError, ValueError) as exc:
            raise RunRefRuntimeError(UNAVAILABLE, f"launcher_did_not_report:{self._stderr()}") from exc
        if reported != self.process.pid:
            raise RunRefRuntimeError(UNAVAILABLE, "launcher_pid_differs")
        row = Path(f"/proc/{reported}/cgroup").read_text().strip().split("::", 1)[1]
        path = self.path = CGROUP_MOUNT / row.lstrip("/")
        if path.name != self.unit:
            raise RunRefRuntimeError(UNAVAILABLE, "launcher_not_in_its_scope")
        try:
            root = self.root = CgroupV2ContainmentRoot.from_scope_path(path, slot_prefix="run-ref-")
        except ProviderIsolationBackendUnavailable as exc:
            raise RunRefRuntimeError(UNAVAILABLE, f"scope_not_delegated:{exc}") from exc
        controllers = set((path / "cgroup.controllers").read_text().split())
        if not {"cpu", "memory", "pids"} <= controllers:
            raise RunRefRuntimeError(UNAVAILABLE, f"scope_controllers_missing:{sorted(controllers)}")
        self._read_back(path)
        gate = self.gate = DurableLaunchReleaseGate.create(
            self.control_dir / f"holder-release-{self.token_digest[:16]}.json",
            launch_token="sha256:" + self.token_digest, containment_identity=root.identity_digest)
        gate.record_intent()
        holder = self.slots["holder"] = root.create_slot("holder")
        holder.add_pid(reported)
        self.slots["host"] = root.create_slot("host")
        if procs(path) or set(holder.members()) != {reported}:
            raise RunRefRuntimeError(UNAVAILABLE, "scope_root_not_empty")
        (path / "cgroup.subtree_control").write_text("+memory +pids")
        gate.consume_release(gate.record_commit())
        self._released = True
        launch_host.sendall(self._token.encode() + b"\n")

    def _read_back(self, path: Path) -> None:
        names = ["MemoryMax", "MemorySwapMax", "TasksMax", "CPUQuotaPerSecUSec", "OOMPolicy", "Delegate",
                 "ControlGroup"]
        shown = subprocess.run(["systemctl", "--user", "show", self.unit, "-p", ",".join(names)],
                               capture_output=True, text=True, timeout=LAUNCH_SECONDS, check=True).stdout
        unit = dict(line.split("=", 1) for line in shown.splitlines() if "=" in line)
        files = {name: (path / name).read_text().strip()
                 for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}
        if (unit, files) != profile.expected_readback(self.limits, "/" + str(path.relative_to(CGROUP_MOUNT))):
            raise RunRefRuntimeError(UNAVAILABLE, f"scope_read_back_differs:{unit}:{files}")
        self.readback = {"unit": unit, "cgroup": files}

    def _await_ready(self, info_read: int) -> None:
        assert self.process is not None
        try:
            info = drain(info_read, time.monotonic() + LAUNCH_SECONDS)
        except TimeoutError as exc:
            raise RunRefRuntimeError(UNAVAILABLE, f"holder_info_pipe_not_ready:{exc}") from exc
        if not info:  # released, but bwrap never reported its sandbox
            self.process.wait(timeout=10)
            raise RunRefRuntimeError(UNAVAILABLE, f"holder_exited_{self.process.returncode}_before_ready:"
                                                  f"{self._stderr()}")
        child_pid = json.loads(info)["child-pid"]
        try:
            ready = self.line(time.monotonic() + LAUNCH_SECONDS)
        except TimeoutError:
            ready = None  # silence is refused like EOF: no guest code has run yet
        if ready != "ready":
            raise RunRefRuntimeError(UNAVAILABLE, f"spawner_not_ready:{self._stderr()}")
        holder = self.slots["holder"]
        self.recorded = set(holder.members())
        children = Path(f"/proc/{child_pid}/task/{child_pid}/children").read_text().split()
        if len(children) != 1 or int(children[0]) not in self.recorded:
            raise RunRefRuntimeError(ESCAPE, "spawner_not_identified")
        self.spawner_pid = int(children[0])
        for mount in MOUNTS:
            self.roots[mount] = os.open(f"/proc/{child_pid}/root/{mount}",
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if set(holder.members()) != self.recorded:
            raise RunRefRuntimeError(ESCAPE, "holder_membership_changed_while_opening_roots")
        self._ready_attributes = profile.spawner_attributes(self.spawner_pid)
        self._oom_kills = self._holder_oom_kills()

    def _stderr(self) -> str:
        if self.process is None or self.process.stderr is None or self.process.poll() is None:
            return ""
        return self.process.stderr.read(4096).decode(errors="replace")[-2000:]

    # -- spawner channel and quiescence -------------------------------------------------------------
    def line(self, deadline: float) -> str | None:
        """One control-socket line; None on EOF; TimeoutError past `deadline`."""
        assert self.ctrl is not None
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self.ctrl.settimeout(remaining)
            try:
                chunk = self.ctrl.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError from exc
            if not chunk:
                return None
            self._buffer += chunk
            if len(self._buffer) > 4096:
                raise HolderDeathError(LOST, "control line exceeds its bound")
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line.decode(errors="replace")

    def require_quiescent(self) -> None:
        """Whole-slot quiescence (D-g): holder members as at ready and running, every other slot empty."""
        assert self.path is not None and self.process is not None
        if self.process.poll() is not None:
            raise HolderDeathError(LOST, "bwrap exited")
        holder = self.slots["holder"]
        members = set(holder.members())
        if members - self.recorded:
            raise HolderDeathError(ESCAPE, "foreign holder-slot member")
        if members != self.recorded:
            raise HolderDeathError(LOST, "holder-slot process ended")
        for pid in sorted(members):
            try:
                state = process_state(pid)
            except OSError as exc:
                raise HolderDeathError(LOST, "holder-slot process ended") from exc
            if state in ("T", "t"):
                raise HolderDeathError(LOST, "spawner stopped" if pid == self.spawner_pid
                                       else "holder-slot process stopped")
        if self._holder_oom_kills() != self._oom_kills:
            raise HolderDeathError(LOST, "holder-slot OOM kill")
        for child in self.path.iterdir():
            if child.is_dir() and child != holder.path and populated(child):
                raise HolderDeathError(ESCAPE, f"populated slot {child.name} outside a leaf window")

    def _holder_oom_kills(self) -> int:
        events = (self.slots["holder"].path / "memory.events").read_text().split()
        return int(dict(zip(events[::2], events[1::2])).get("oom_kill", 0))

    def check_spawner(self) -> None:
        """F3b-1 at post-leaf quiescence, before any host read."""
        assert self.path is not None
        try:
            now = profile.spawner_attributes(self.spawner_pid)
        except OSError as exc:
            raise HolderDeathError(LOST, f"spawner attributes unreadable: {exc}") from exc
        cpuset = self.path / "cpuset.cpus.effective"
        effective = profile.parse_cpu_list(cpuset.read_text()) if cpuset.exists() else None
        drifted = profile.attribute_drift(self._ready_attributes, now, effective)
        if drifted is not None:
            raise HolderDeathError(LOST, f"spawner attribute changed since ready: {drifted}")

    # -- host helper (N4) ---------------------------------------------------------------------------
    def run_host_helper(self, argv: Sequence[str], *, pass_fds: Sequence[int],
                        timeout_sec: float) -> subprocess.CompletedProcess:
        if not argv or not argv[0].startswith("/"):
            raise ValueError("host helper argv[0] must be an absolute path")
        self.require_quiescent()
        host = self.slots["host"]
        procs_fd = os.open(host.path / "cgroup.procs", os.O_WRONLY | os.O_CLOEXEC)
        try:
            process = subprocess.Popen([sys.executable, "-I", "-S", "-c", HELPER_TRAMPOLINE, str(procs_fd),
                                        str(os.getpid()), *argv], pass_fds=(procs_fd, *pass_fds),
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(procs_fd)
        try:
            stdout, stderr = process.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired as exc:
            host.kill()
            process.communicate()
            raise HolderDeathError(LOST, f"host helper exceeded {timeout_sec} s") from exc
        finally:
            host.kill()
            host.wait_empty(timeout_seconds=SLOT_EMPTY_SECONDS)
        return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)

    # -- teardown -------------------------------------------------------------------------------------
    def kill(self) -> None:
        if self.path is not None:
            kill_cgroup(self.path)

    def stop(self) -> None:
        """Kill and empty the scope, reap the launcher, close every descriptor (idempotent)."""
        if self._stopped:
            return
        self._stopped = True
        for fd in self.roots.values():
            os.close(fd)
        self.roots = {}
        emptied = self.path is None or kill_cgroup(self.path)
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            if self.process.stderr is not None:
                self.process.stderr.close()
        for sock in (self.ctrl, self.gate_socket):
            if sock is not None:
                sock.close()
        try:  # a unit stopped by systemd stays listed as failed; non-zero when already gone
            subprocess.run(["systemctl", "--user", "reset-failed", self.unit], capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass  # cosmetic unit listing only; the scope itself was proven empty above
        shutil.rmtree(self.runref, ignore_errors=True)
        if not emptied:
            raise RunRefRuntimeError(LOST, f"holder scope {self.unit} did not empty")
