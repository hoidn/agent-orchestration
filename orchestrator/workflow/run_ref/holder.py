"""Bubblewrap holder runtime of `run_ref_confinement.v1`: one `Holder` per child attempt.

`Holder.launch()` (design D-a, D-e, F3b-2, R10): rehash the sealed rootfs
through its retained descriptor, start the gated launcher in a fresh
`systemd-run --user --scope` unit named from the launch token digest with the
policy limits and `OOMPolicy=continue` as unit properties, resolve the scope
from the launcher pid and validate it with the containment identity rules,
read the limits back, bind one `DurableLaunchReleaseGate` to the scope
identity, move the launcher into the `holder` slot, verify the scope root is
empty and only then send the exact release token. Refusals before release are
`run_ref_environment_unavailable`.

`Holder.run_leaf()` implements `LeafRunner` (D-g, R5, R6, F3b-1): whole-slot
quiescence, chmod-then-wipe of `/tmp`, `/dev/shm` and `/result`, exclusive
`/result/<leaf>`, request and acknowledgement with deadlines, the leaf pid
taken from holder-slot membership and moved into its own slot, gate release,
status line or wall deadline, slot kill, quiescence again, the spawner
attribute comparison, then the bounded result import (`holder_broker.py`).
Holder deaths come back as `LeafOutcome.holder_death`; nothing here writes
ledgers or memos. `run_host_helper()` runs 6c's seeding/checkpoint helper in
the `host` slot under a parent-death signal (N4).

Dependencies: a user systemd manager with cpu/memory/pids delegation,
`/usr/bin/bwrap`, `systemd-run`, `systemctl`, x86_64, an admitted
`SealedImage`, and a private control directory for the release record and
the host-written leaf scripts.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import os
import platform
import secrets
import shutil
import signal
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
from .holder_broker import (
    GuestRefusal, drain, kill_cgroup, memfd, nspid, populated, procs, read_leaf_results, wipe_mount,
    write_inputs,
)
from .image_store import ImageStoreError, SealedImage
from .leaf import HolderDeath, LeafOutcome, LeafRequest
from .runtime import RunRefRuntimeError

LOST = "run_ref_environment_lost"
ESCAPE = "run_ref_environment_escape_rejected"
ACK_SECONDS = 2.0       # spawner acknowledgement and leaf-member deadline
STATUS_GRACE = 2.0      # status line deadline once the leaf slot is empty or killed
LINGER_SECONDS = 0.25   # a reaped leaf's slot must empty within this, else descendants linger
LAUNCH_SECONDS = 15.0
CGROUP_MOUNT = Path("/sys/fs/cgroup")
MOUNTS = ("workspace", "tmp", "dev/shm", "result")
_PR_SET_PDEATHSIG = 1


class _Death(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.death = HolderDeath(code, detail)


def _unavailable(detail: str) -> RunRefRuntimeError:
    return RunRefRuntimeError(profile.UNAVAILABLE, detail)


class Holder:
    """One holder incarnation of a child attempt; implements `LeafRunner`."""

    def __init__(self, image: SealedImage, limits: Mapping[str, int], *, control_dir: Path,
                 git_dir_fd: int | None = None) -> None:
        """`limits` are the policy's six limits; `control_dir` is private (0700) controller state."""
        self.image, self.limits, self.control_dir, self.git_dir_fd = image, dict(limits), control_dir, git_dir_fd
        token = secrets.token_hex(32)
        self._token = token
        self.token_digest = hashlib.sha256(token.encode()).hexdigest()
        self.unit = profile.unit_name(self.token_digest)
        self.runref = control_dir / f"runref-{self.token_digest[:16]}"
        self.process: subprocess.Popen | None = None
        self.scope: Path | None = None
        self.root: CgroupV2ContainmentRoot | None = None
        self.gate: DurableLaunchReleaseGate | None = None
        self.slots: dict[str, CgroupV2ContainmentSlot] = {}
        self.spawner_pid: int | None = None
        self.readback: dict[str, dict[str, str]] = {}
        self._roots: dict[str, int] = {}
        self._recorded: set[int] = set()
        self._ready_attributes: dict[str, object] = {}
        self._oom_kills = 0
        self._ctrl: socket.socket | None = None
        self._gate_socket: socket.socket | None = None
        self._buffer = b""
        self._leaves = 0
        self._death: HolderDeath | None = None
        self._stopped = False

    # -- launch -------------------------------------------------------------------------------
    def launch(self) -> "Holder":
        profile.require_x86_64(platform.machine())
        try:
            self.image.rehash()
        except ImageStoreError as exc:
            raise _unavailable(f"image_rehash_refused:{exc.detail}") from exc
        self.runref.mkdir(mode=0o700)
        launch_host, launch_guest = socket.socketpair()
        self._ctrl, ctrl_guest = socket.socketpair()
        self._gate_socket, gate_guest = socket.socketpair()
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
            self.process = subprocess.Popen(argv, pass_fds=(launch_guest.fileno(), *kept),
                                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                            stderr=subprocess.PIPE)
        finally:
            for fd in (launch_guest.detach(), ctrl_guest.detach(), gate_guest.detach(), info_write, *owned):
                os.close(fd)
        try:
            self._release(launch_host)
        except BaseException as exc:
            launch_host.close()  # EOF: an unreleased launcher exits without starting bwrap
            os.close(info_read)
            self.stop()
            if isinstance(exc, (ProviderIsolationBackendUnavailable, ProviderIsolationStateError,
                                subprocess.SubprocessError, OSError)):
                raise _unavailable(f"holder_release_refused:{exc}") from exc
            raise
        launch_host.close()
        try:
            self._await_ready(info_read)
        except BaseException:
            self.stop()
            raise
        return self

    def _release(self, launch_host: socket.socket) -> None:
        """Everything before the token; any refusal here is `run_ref_environment_unavailable`."""
        assert self.process is not None
        launch_host.settimeout(LAUNCH_SECONDS)
        try:
            reported = int(launch_host.recv(64).split(b"\n")[0])
        except (OSError, ValueError) as exc:
            raise _unavailable(f"launcher_did_not_report:{self._launcher_stderr()}") from exc
        if reported != self.process.pid:
            raise _unavailable("launcher_pid_differs")
        row = Path(f"/proc/{reported}/cgroup").read_text().strip().split("::", 1)[1]
        self.scope = CGROUP_MOUNT / row.lstrip("/")
        if self.scope.name != self.unit:
            raise _unavailable("launcher_not_in_its_scope")
        try:
            self.root = CgroupV2ContainmentRoot.from_scope_path(self.scope, slot_prefix="run-ref-")
        except ProviderIsolationBackendUnavailable as exc:
            raise _unavailable(f"scope_not_delegated:{exc}") from exc
        controllers = set((self.scope / "cgroup.controllers").read_text().split())
        if not {"cpu", "memory", "pids"} <= controllers:
            raise _unavailable(f"scope_controllers_missing:{sorted(controllers)}")
        self._read_back()
        self.gate = DurableLaunchReleaseGate.create(
            self.control_dir / f"holder-release-{self.token_digest[:16]}.json",
            launch_token="sha256:" + self.token_digest, containment_identity=self.root.identity_digest)
        self.gate.record_intent()
        holder = self.root.create_slot("holder")
        self.slots["holder"] = holder
        holder.add_pid(reported)
        self.slots["host"] = self.root.create_slot("host")
        if procs(self.scope) or set(holder.members()) != {reported}:
            raise _unavailable("scope_root_not_empty")
        (self.scope / "cgroup.subtree_control").write_text("+memory +pids")
        permit = self.gate.record_commit()
        self.gate.consume_release(permit)
        launch_host.sendall(self._token.encode() + b"\n")

    def _read_back(self) -> None:
        assert self.scope is not None
        names = ["MemoryMax", "MemorySwapMax", "TasksMax", "CPUQuotaPerSecUSec", "OOMPolicy", "Delegate",
                 "ControlGroup"]
        shown = subprocess.run(["systemctl", "--user", "show", self.unit, "-p", ",".join(names)],
                               capture_output=True, text=True, timeout=LAUNCH_SECONDS, check=True).stdout
        unit = dict(line.split("=", 1) for line in shown.splitlines() if "=" in line)
        files = {name: (self.scope / name).read_text().strip()
                 for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}
        expected = profile.expected_readback(self.limits, "/" + str(self.scope.relative_to(CGROUP_MOUNT)))
        if (unit, files) != expected:
            raise _unavailable(f"scope_read_back_differs:{unit}:{files}")
        self.readback = {"unit": unit, "cgroup": files}

    def _await_ready(self, info_read: int) -> None:
        assert self.process is not None and self.scope is not None
        info = drain(info_read, time.monotonic() + LAUNCH_SECONDS)
        if not info:  # released, but the launcher never started bwrap
            self.process.wait(timeout=10)
            raise _unavailable(f"launcher_exited_{self.process.returncode}_before_bwrap:{self._launcher_stderr()}")
        child_pid = json.loads(info)["child-pid"]
        if self._line(time.monotonic() + LAUNCH_SECONDS) != "ready":
            raise RunRefRuntimeError(LOST, "spawner_not_ready")
        self._recorded = set(self.slots["holder"].members())
        children = Path(f"/proc/{child_pid}/task/{child_pid}/children").read_text().split()
        if len(children) != 1 or int(children[0]) not in self._recorded:
            raise RunRefRuntimeError(ESCAPE, "spawner_not_identified")
        self.spawner_pid = int(children[0])
        for mount in MOUNTS:
            self._roots[mount] = os.open(f"/proc/{child_pid}/root/{mount}",
                                         os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        if set(self.slots["holder"].members()) != self._recorded:
            raise RunRefRuntimeError(ESCAPE, "holder_membership_changed_while_opening_roots")
        self._ready_attributes = profile.spawner_attributes(self.spawner_pid)
        self._oom_kills = self._holder_oom_kills()

    def _launcher_stderr(self) -> str:
        if self.process is None or self.process.stderr is None or self.process.poll() is None:
            return ""
        return self.process.stderr.read(4096).decode(errors="replace")[-2000:]

    # -- accessors for the integration (6c) --------------------------------------------------------
    @property
    def dead(self) -> HolderDeath | None:
        return self._death

    def root_fd(self, mount: str) -> int:
        """Retained root descriptor of a holder tmpfs mount (`workspace`, `tmp`, `dev/shm`, `result`)."""
        return self._roots[mount]

    def run_host_helper(self, argv: Sequence[str], *, pass_fds: Sequence[int] = (),
                        timeout_sec: float) -> subprocess.CompletedProcess:
        """Run a trusted host helper in the `host` slot under a parent-death SIGKILL (N4): it enters the
        slot before it executes (its pages charge the scope), inherits only `pass_fds`, and the slot is
        killed and emptied afterwards."""
        self._require_quiescent()
        host = self.slots["host"]
        procs_fd = os.open(host.path / "cgroup.procs", os.O_WRONLY | os.O_CLOEXEC)
        libc = ctypes.CDLL(None, use_errno=True)

        def enter_slot() -> None:
            if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
                os._exit(125)
            os.write(procs_fd, b"0\n")

        try:
            process = subprocess.Popen(list(argv), pass_fds=tuple(pass_fds), preexec_fn=enter_slot,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        finally:
            os.close(procs_fd)
        try:
            stdout, stderr = process.communicate(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            host.kill()
            stdout, stderr = process.communicate()
        host.kill()
        host.wait_empty(timeout_seconds=STATUS_GRACE)
        return subprocess.CompletedProcess(list(argv), process.returncode, stdout, stderr)

    # -- leaves -------------------------------------------------------------------------------------
    def run_leaf(self, request: LeafRequest) -> LeafOutcome:
        if request.network == "model-only":
            raise RunRefRuntimeError("run_ref_provider_transport_unavailable", "model_only_relay_unavailable")
        profile.validate_leaf_request(request)
        if self._death is not None:
            return self._death_outcome(self._death, 0, False)
        started = time.monotonic()
        progress = {"timed_out": False}
        try:
            return self._run(request, progress)
        except (_Death, ProviderIsolationStateError, ProviderIsolationBackendUnavailable) as exc:
            if isinstance(exc, _Death):
                death = exc.death
            else:  # the scope vanished under the slot: systemd removes it once bwrap is gone
                exited = self.process is not None and self.process.poll() is not None
                death = HolderDeath(LOST, "bwrap exited" if exited else f"containment: {exc}")
            self._death = death
            if self.scope is not None:
                kill_cgroup(self.scope)
            return self._death_outcome(death, int((time.monotonic() - started) * 1000), progress["timed_out"])

    @staticmethod
    def _death_outcome(death: HolderDeath, duration_ms: int, timed_out: bool) -> LeafOutcome:
        return LeafOutcome(exit_code=None, timed_out=timed_out, stdout=b"", stderr=b"", stdout_truncated=False,
                           stderr_truncated=False, result_files={}, duration_ms=duration_ms,
                           quiesced_by_exit=False, holder_death=death)

    def _run(self, request: LeafRequest, progress: dict) -> LeafOutcome:
        assert self.root is not None and self._ctrl is not None and self._gate_socket is not None
        leaf = request.leaf_id
        self._require_quiescent()
        for mount in ("tmp", "dev/shm", "result"):
            if not wipe_mount(self._roots[mount]):
                raise _Death(ESCAPE, f"/{mount} could not be emptied before leaf {leaf}")
        try:
            os.mkdir(leaf, 0o755, dir_fd=self._roots["result"])  # exclusive (R6)
        except FileExistsError as exc:
            raise _Death(ESCAPE, f"/result/{leaf} exists before its leaf") from exc
        write_inputs(self._roots["result"], leaf, request.input_files)
        leaf_dir = self.runref / leaf
        leaf_dir.mkdir(mode=0o700)
        self._leaves += 1
        slot = self.root.create_slot(f"leaf:{self._leaves}:{leaf}")
        try:
            (leaf_dir / "leaf.sh").write_text(profile.leaf_script(request))
            pid = self._request(leaf)
            slot.add_pid(pid)
            if slot.members() != (pid,) or set(self.slots["holder"].members()) != self._recorded:
                raise _Death(ESCAPE, f"leaf {leaf} did not stay in its slot")
            started = time.monotonic()
            self._gate_socket.sendall(b"go\n")
            status, timed_out, lingering = self._await_status(slot, started + request.timeout_sec, progress)
            duration_ms = int((time.monotonic() - started) * 1000)
            slot.kill()
            try:
                slot.wait_empty(timeout_seconds=STATUS_GRACE)
            except ProviderIsolationStateError as exc:
                raise _Death(LOST, f"leaf slot of {leaf} did not quiesce") from exc
            slot.remove()
            self._require_quiescent()
            self._compare_attributes()
            try:
                reads = read_leaf_results(self._roots["result"], leaf, stdout_limit=request.stdout_limit,
                                          stderr_limit=request.stderr_limit,
                                          max_bytes=profile.PROFILE_MIB["result"] << 20)
            except GuestRefusal as exc:
                raise _Death(ESCAPE, f"result read refused: {exc}") from exc
        finally:
            shutil.rmtree(leaf_dir, ignore_errors=True)
            self._remove_slot(slot)
        exited = not timed_out and not lingering
        return LeafOutcome(exit_code=status if exited else None, timed_out=timed_out, stdout=reads.stdout,
                           stderr=reads.stderr, stdout_truncated=reads.stdout_truncated,
                           stderr_truncated=reads.stderr_truncated, result_files=reads.files,
                           duration_ms=duration_ms, quiesced_by_exit=exited, holder_death=None)

    def _request(self, leaf: str) -> int:
        """Send the request; return the leaf pid derived from holder-slot membership (D-g)."""
        assert self._ctrl is not None
        self._ctrl.sendall(leaf.encode() + b"\n")
        deadline = time.monotonic() + ACK_SECONDS
        try:
            ack = self._line(deadline)
        except TimeoutError as exc:
            raise _Death(LOST, "no acknowledgement within the deadline") from exc
        if ack is None:
            raise _Death(LOST, "control socket EOF")
        kind, _, value = ack.partition(" ")
        if kind != "ack" or not value.isdecimal():
            raise _Death(LOST, "malformed acknowledgement")
        while True:
            extra = set(self.slots["holder"].members()) - self._recorded
            if len(extra) > 1:
                raise _Death(ESCAPE, "foreign holder-slot member")
            if extra:
                pid = extra.pop()
                if nspid(pid) != int(value):
                    raise _Death(ESCAPE, "holder-slot member is not the acknowledged leaf")
                return pid
            if time.monotonic() > deadline:
                raise _Death(ESCAPE, "no leaf member within the deadline")
            time.sleep(0.005)

    def _await_status(self, slot: CgroupV2ContainmentSlot, wall_deadline: float,
                      progress: dict) -> tuple[int, bool, bool]:
        grace: float | None = None
        while True:
            now = time.monotonic()
            if grace is None and not slot.populated:
                grace = now + STATUS_GRACE
            if grace is None and now > wall_deadline:
                progress["timed_out"] = True
                slot.kill()
                grace = now + STATUS_GRACE
            if grace is not None and now > grace:
                raise _Death(LOST, "no status line within the deadline")
            try:
                line = self._line(min(now + 0.05, grace or wall_deadline))
            except TimeoutError:
                continue
            if line is None:
                raise _Death(LOST, "control socket EOF")
            kind, _, value = line.partition(" ")
            if kind != "status" or not value.isdecimal():
                raise _Death(LOST, "malformed status line")
            linger_deadline = time.monotonic() + LINGER_SECONDS
            while slot.populated and time.monotonic() < linger_deadline:
                time.sleep(0.01)
            return int(value), progress["timed_out"], slot.populated

    def _line(self, deadline: float) -> str | None:
        """One control-socket line; None on EOF; TimeoutError past `deadline`."""
        assert self._ctrl is not None
        while b"\n" not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self._ctrl.settimeout(remaining)
            try:
                chunk = self._ctrl.recv(4096)
            except socket.timeout as exc:
                raise TimeoutError from exc
            if not chunk:
                return None
            self._buffer += chunk
            if len(self._buffer) > 4096:
                raise _Death(LOST, "control line exceeds its bound")
        line, _, self._buffer = self._buffer.partition(b"\n")
        return line.decode(errors="replace")

    def _require_quiescent(self) -> None:
        """Whole-slot quiescence (D-g): holder members as at ready, every other slot empty."""
        assert self.root is not None and self.scope is not None and self.process is not None
        if self._death is not None:
            raise _Death(self._death.code, self._death.detail)
        if self.process.poll() is not None:
            raise _Death(LOST, "bwrap exited")
        members = set(self.slots["holder"].members())
        if members - self._recorded:
            raise _Death(ESCAPE, "foreign holder-slot member")
        if members != self._recorded:
            raise _Death(LOST, "holder-slot process ended")
        if self._holder_oom_kills() != self._oom_kills:
            raise _Death(LOST, "holder-slot OOM kill")
        for child in self.scope.iterdir():
            if child.is_dir() and child != self.slots["holder"].path and populated(child):
                raise _Death(ESCAPE, f"populated slot {child.name} outside a leaf window")

    def _holder_oom_kills(self) -> int:
        events = (self.slots["holder"].path / "memory.events").read_text().split()
        return int(dict(zip(events[::2], events[1::2])).get("oom_kill", 0))

    def _compare_attributes(self) -> None:
        """F3b-1 at post-leaf quiescence, before any host read."""
        assert self.spawner_pid is not None and self.scope is not None
        try:
            now = profile.spawner_attributes(self.spawner_pid)
        except OSError as exc:
            raise _Death(LOST, f"spawner attributes unreadable: {exc}") from exc
        cpuset = self.scope / "cpuset.cpus.effective"
        effective = profile.parse_cpu_list(cpuset.read_text()) if cpuset.exists() else None
        drifted = profile.attribute_drift(self._ready_attributes, now, effective)
        if drifted is not None:
            raise _Death(LOST, f"spawner attribute changed since ready: {drifted}")

    def _remove_slot(self, slot: CgroupV2ContainmentSlot) -> None:
        try:
            if slot.populated:
                slot.kill()
                slot.wait_empty(timeout_seconds=STATUS_GRACE)
            slot.remove()
        except ProviderIsolationStateError:
            pass  # gone with the scope after a holder death, or already removed

    # -- teardown -------------------------------------------------------------------------------------
    def stop(self) -> None:
        """Kill and empty the scope, reap the launcher, close every descriptor (idempotent)."""
        if self._stopped:
            return
        self._stopped = True
        for fd in self._roots.values():
            os.close(fd)
        self._roots = {}
        emptied = self.scope is None or kill_cgroup(self.scope)
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            if self.process.stderr is not None:
                self.process.stderr.close()
        for sock in (self._ctrl, self._gate_socket):
            if sock is not None:
                sock.close()
        try:  # a unit stopped by systemd stays listed as failed; non-zero when already gone
            subprocess.run(["systemctl", "--user", "reset-failed", self.unit], capture_output=True, timeout=15)
        except subprocess.TimeoutExpired:
            pass  # cosmetic unit listing only; the scope itself was proven empty above
        shutil.rmtree(self.runref, ignore_errors=True)
        if not emptied:
            raise RunRefRuntimeError(LOST, f"holder scope {self.unit} did not empty")
