"""Bubblewrap holder runtime of `run_ref_confinement.v1`: one `Holder` per controller incarnation.

`Holder` implements `LeafRunner` over one `HolderScope` (`holder_scope.py`:
scope, launch, quiescence, teardown). Per leaf (design D-g, R5, R6, F3b-1,
P28): whole-slot quiescence and empty `/tmp`, `/dev/shm` and `/result`,
exclusive `/result/<leaf>` with the host-written inputs, request and
acknowledgement with deadlines, the leaf pid taken from holder-slot membership
and moved into its own slot, gate release, status line or wall deadline, slot
kill, quiescence again (including a stopped spawner), the spawner attribute
comparison, the bounded result import (`holder_broker.py`) and a wipe of the
three scratch mounts, so an unwipeable tree fails the culprit's own attempt.
Holder deaths come back as `LeafOutcome.holder_death`; nothing here writes
ledgers or memos. Dependencies: those of `HolderScope`.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from orchestrator.providers.isolation_backend import CgroupV2ContainmentSlot, ProviderIsolationStateError

from . import holder_spawner as profile
from .holder_broker import GuestRefusal, LeafReads, read_leaf_results, wipe_mount, write_inputs
from .holder_scope import CGROUP_MOUNT, CONTAINMENT_ERRORS, ESCAPE, LOST, HolderDeathError, HolderScope, wall_seconds
from .image_store import SealedImage
from .leaf import HolderDeath, LeafOutcome, LeafRequest
from .runtime import RunRefRuntimeError

__all__ = ["CGROUP_MOUNT", "Holder"]

ACK_SECONDS = 2.0       # spawner acknowledgement and leaf-member deadline
STATUS_GRACE = 2.0      # status line deadline once the leaf slot is empty or killed
LINGER_SECONDS = 0.25   # a reaped leaf's slot must empty within this, else descendants linger
SCRATCH = ("tmp", "dev/shm", "result")


class Holder:
    """One holder incarnation of a child attempt; implements `LeafRunner`."""

    def __init__(self, image: SealedImage, limits: Mapping[str, int], *, control_dir: Path,
                 git_dir_fd: int | None = None) -> None:
        """`limits` are the policy's six limits; `control_dir` is private (0700) controller state."""
        self.sandbox = HolderScope(image, limits, control_dir=control_dir, git_dir_fd=git_dir_fd)
        self._leaves = 0
        self._death: HolderDeath | None = None

    def launch(self) -> "Holder":
        """Raises `RunRefRuntimeError` (unavailable before release, lost or escape_rejected after)."""
        self.sandbox.launch()
        return self

    def stop(self) -> None:
        self.sandbox.stop()

    @property
    def unit(self) -> str:
        return self.sandbox.unit

    @property
    def scope(self) -> Path | None:
        return self.sandbox.path

    @property
    def slots(self) -> dict[str, CgroupV2ContainmentSlot]:
        return self.sandbox.slots

    @property
    def readback(self) -> dict[str, dict[str, str]]:
        return self.sandbox.readback

    @property
    def dead(self) -> HolderDeath | None:
        return self._death

    def root_fd(self, mount: str) -> int:
        """Retained root descriptor of a holder tmpfs mount (`workspace`, `tmp`, `dev/shm`, `result`)."""
        return self.sandbox.roots[mount]

    def run_host_helper(self, argv: Sequence[str], *, pass_fds: Sequence[int] = (),
                        timeout_sec: float) -> subprocess.CompletedProcess:
        """Run a trusted host helper (absolute argv[0]) in the `host` slot under a parent-death SIGKILL (N4).

        It enters the slot before it executes (its pages charge the scope), inherits
        only `pass_fds`, and the slot is killed and emptied afterwards. A dead or
        non-quiescent holder, a helper past `timeout_sec` or a containment fault is
        a holder death raised as `RunRefRuntimeError` with its code.
        """
        if self._death is not None:
            raise RunRefRuntimeError(self._death.code, self._death.detail)
        try:
            return self.sandbox.run_host_helper(argv, pass_fds=pass_fds, timeout_sec=timeout_sec)
        except (HolderDeathError, *CONTAINMENT_ERRORS, OSError, subprocess.SubprocessError) as exc:
            death = self._die(exc)
            raise RunRefRuntimeError(death.code, f"host helper: {death.detail}") from exc

    # -- leaves -------------------------------------------------------------------------------------
    def run_leaf(self, request: LeafRequest) -> LeafOutcome:
        if request.network == "model-only":
            raise RunRefRuntimeError("run_ref_provider_transport_unavailable", "model_only_relay_unavailable")
        profile.validate_leaf_request(request)
        if self._death is not None:
            return _death_outcome(self._death, 0, False)
        started = wall_seconds()
        progress = {"timed_out": False}
        try:
            return self._run(request, progress)
        except (HolderDeathError, *CONTAINMENT_ERRORS) as exc:
            death = self._die(exc)
            return _death_outcome(death, int((wall_seconds() - started) * 1000), progress["timed_out"])

    def _die(self, exc: BaseException) -> HolderDeath:
        if isinstance(exc, HolderDeathError):
            death = exc.death
        else:  # the scope vanished under a slot: systemd removes it once bwrap is gone
            process = self.sandbox.process
            exited = process is not None and process.poll() is not None
            death = HolderDeath(LOST, "bwrap exited" if exited else f"{type(exc).__name__}: {exc}")
        self._death = death
        self.sandbox.kill()
        return death

    def _run(self, request: LeafRequest, progress: dict) -> LeafOutcome:
        sandbox, leaf = self.sandbox, request.leaf_id
        sandbox.require_quiescent()
        for mount in SCRATCH:
            if os.listdir(sandbox.roots[mount]):
                raise HolderDeathError(ESCAPE, f"/{mount} is not empty before leaf {leaf}")
        try:
            os.mkdir(leaf, 0o755, dir_fd=sandbox.roots["result"])  # exclusive (R6)
        except FileExistsError as exc:
            raise HolderDeathError(ESCAPE, f"/result/{leaf} exists before its leaf") from exc
        write_inputs(sandbox.roots["result"], leaf, request.input_files)
        leaf_dir = sandbox.runref / leaf
        leaf_dir.mkdir(mode=0o700)
        self._leaves += 1
        assert sandbox.root is not None
        slot = sandbox.root.create_slot(f"leaf:{self._leaves}:{leaf}")
        try:
            (leaf_dir / "leaf.sh").write_text(profile.leaf_script(request))
            status, timed_out, lingered, duration_ms = self._execute(leaf, slot, request.timeout_sec, progress)
            reads = self._import(request)
        finally:
            shutil.rmtree(leaf_dir, ignore_errors=True)
            _remove_slot(slot)
        exited = not timed_out and not lingered
        return LeafOutcome(exit_code=None if timed_out else status, timed_out=timed_out, stdout=reads.stdout,
                           stderr=reads.stderr, stdout_truncated=reads.stdout_truncated,
                           stderr_truncated=reads.stderr_truncated, result_files=reads.files,
                           duration_ms=duration_ms, quiesced_by_exit=exited, holder_death=None,
                           lingered=lingered)

    def _execute(self, leaf: str, slot: CgroupV2ContainmentSlot, timeout_sec: float,
                 progress: dict) -> tuple[int, bool, bool, int]:
        """Request, move, release and await one leaf; quiesce and check the spawner afterwards."""
        sandbox = self.sandbox
        pid = self._request(leaf)
        slot.add_pid(pid)
        if slot.members() != (pid,) or set(sandbox.slots["holder"].members()) != sandbox.recorded:
            raise HolderDeathError(ESCAPE, f"leaf {leaf} did not stay in its slot")
        started = wall_seconds()
        assert sandbox.gate_socket is not None
        sandbox.gate_socket.sendall(b"go\n")
        status, timed_out, lingered = self._await_status(slot, started + timeout_sec, progress)
        duration_ms = int((wall_seconds() - started) * 1000)
        slot.kill()
        try:
            slot.wait_empty(timeout_seconds=STATUS_GRACE)
        except ProviderIsolationStateError as exc:
            raise HolderDeathError(LOST, f"leaf slot of {leaf} did not quiesce") from exc
        slot.remove()
        sandbox.require_quiescent()
        sandbox.check_spawner()
        return status, timed_out, lingered, duration_ms

    def _import(self, request: LeafRequest) -> LeafReads:
        """Bounded result import, then the post-leaf wipe of the scratch mounts (P27, P28)."""
        roots = self.sandbox.roots
        try:
            reads = read_leaf_results(roots["result"], request.leaf_id, stdout_limit=request.stdout_limit,
                                      stderr_limit=request.stderr_limit,
                                      max_bytes=profile.PROFILE_MIB["result"] << 20)
        except GuestRefusal as exc:
            raise HolderDeathError(ESCAPE, f"result read refused: {exc}") from exc
        for mount in SCRATCH:
            if not wipe_mount(roots[mount]):
                raise HolderDeathError(ESCAPE, f"/{mount} could not be emptied after leaf {request.leaf_id}")
        return reads

    def _request(self, leaf: str) -> int:
        """Send the request; return the leaf pid derived from holder-slot membership (D-g)."""
        sandbox = self.sandbox
        assert sandbox.ctrl is not None
        sandbox.ctrl.sendall(leaf.encode() + b"\n")
        deadline = wall_seconds() + ACK_SECONDS
        try:
            ack = sandbox.line(deadline)
        except TimeoutError as exc:
            raise HolderDeathError(LOST, "no acknowledgement within the deadline") from exc
        if ack is None:
            raise HolderDeathError(LOST, "control socket EOF")
        kind, _, value = ack.partition(" ")
        if kind != "ack" or not value.isdecimal():
            raise HolderDeathError(LOST, "malformed acknowledgement")
        while True:
            extra = set(sandbox.slots["holder"].members()) - sandbox.recorded
            if len(extra) > 1:
                raise HolderDeathError(ESCAPE, "foreign holder-slot member")
            if extra:
                pid = extra.pop()
                if _nspid(pid) != int(value):
                    raise HolderDeathError(ESCAPE, "holder-slot member is not the acknowledged leaf")
                return pid
            if wall_seconds() > deadline:
                raise HolderDeathError(ESCAPE, "no leaf member within the deadline")
            time.sleep(0.005)

    def _await_status(self, slot: CgroupV2ContainmentSlot, wall_deadline: float,
                      progress: dict) -> tuple[int, bool, bool]:
        """(status, timed out, lingered): the status line within its deadline, or a holder death."""
        grace: float | None = None
        while True:
            now = wall_seconds()
            if grace is None and not slot.populated:
                grace = now + STATUS_GRACE
            if grace is None and now > wall_deadline:
                progress["timed_out"] = True
                slot.kill()
                grace = now + STATUS_GRACE
            if grace is not None and now > grace:
                raise HolderDeathError(LOST, "no status line within the deadline")
            try:
                line = self.sandbox.line(min(now + 0.05, grace or wall_deadline))
            except TimeoutError:
                continue
            if line is None:
                raise HolderDeathError(LOST, "control socket EOF")
            kind, _, value = line.partition(" ")
            if kind != "status" or not value.isdecimal():
                raise HolderDeathError(LOST, "malformed status line")
            linger_deadline = wall_seconds() + LINGER_SECONDS
            while slot.populated and wall_seconds() < linger_deadline:
                time.sleep(0.01)
            timed_out = progress["timed_out"]
            return int(value), timed_out, not timed_out and slot.populated


def _death_outcome(death: HolderDeath, duration_ms: int, timed_out: bool) -> LeafOutcome:
    return LeafOutcome(exit_code=None, timed_out=timed_out, stdout=b"", stderr=b"", stdout_truncated=False,
                       stderr_truncated=False, result_files={}, duration_ms=duration_ms, quiesced_by_exit=False,
                       holder_death=death)


def _nspid(pid: int) -> int:
    rows = [line for line in Path(f"/proc/{pid}/status").read_text().splitlines() if line.startswith("NSpid:")]
    return int(rows[0].split()[-1])


def _remove_slot(slot: CgroupV2ContainmentSlot) -> None:
    try:
        if slot.populated:
            slot.kill()
            slot.wait_empty(timeout_seconds=STATUS_GRACE)
        slot.remove()
    except CONTAINMENT_ERRORS:
        pass  # gone with the scope after a holder death, or already removed
