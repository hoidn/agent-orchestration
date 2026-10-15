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
import subprocess
import time
from dataclasses import replace
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
                 git_dir_fd: int | None = None, network: str = 'none') -> None:
        """`limits` are the policy's six limits; `control_dir` is private (0700) controller state."""
        self.sandbox = HolderScope(image, limits, control_dir=control_dir, git_dir_fd=git_dir_fd, network=network)
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
        except (HolderDeathError, *CONTAINMENT_ERRORS, OSError) as exc:
            death = self._die(exc)
            return _death_outcome(death, int((wall_seconds() - started) * 1000), progress["timed_out"])

    def run_provider_leaf(self, request: LeafRequest, *, allowance, policy, identity, attempt,
                          installation, deadline_ns, cancelled, prepare_guest) -> LeafOutcome:
        """Private admitted-caller seam; public run_leaf still refuses model-only.

        prepare_guest is trusted host code. It may supply the fixed invocation
        and ephemeral environment only after the durable binding ACK.
        """
        from .confined_budget import boottime_ns
        from .provider_control import ProviderControlRefused
        from .provider_transport import LeafProviderTransport
        profile.validate_leaf_request(request)
        if (request.network != 'model-only' or type(identity) is not str or not identity
                or type(attempt) is not int or attempt <= 0 or type(deadline_ns) is not int
                or deadline_ns > boottime_ns() + int(request.timeout_sec * 1e9)):
            raise RunRefRuntimeError(ESCAPE, 'private_provider_request_invalid')
        if self._death is not None:
            return _death_outcome(self._death, 0, False)
        started, progress = wall_seconds(), {'timed_out': False}
        transport = LeafProviderTransport(self.sandbox, authority=allowance, policy=policy,
            identity=identity, attempt=attempt, installation=installation,
            deadline_ns=deadline_ns, cancelled=cancelled)
        self.sandbox.begin_transport()
        try:
            result = self._run(request, progress, transport=transport, prepare_guest=prepare_guest)
            self.sandbox.end_transport()
            return result
        except (HolderDeathError, *CONTAINMENT_ERRORS, ProviderControlRefused, OSError) as error:
            progress['timed_out'] = boottime_ns() >= deadline_ns
            if not isinstance(error, (HolderDeathError, *CONTAINMENT_ERRORS)):
                error = HolderDeathError(LOST, 'private_provider_transport_refused')
            death = self._die(error)
            return _death_outcome(death, int((wall_seconds()-started)*1000), progress['timed_out'])
        except RunRefRuntimeError:
            # A first exhausted allowance never launched a worker; cleanup has
            # already emptied the host window and must not rename its failure.
            self.sandbox.end_transport()
            raise
        except Exception:
            death = self._die(HolderDeathError(LOST, 'private_provider_transport_refused'))
            return _death_outcome(death, int((wall_seconds()-started)*1000), progress['timed_out'])

    def _die(self, exc: BaseException) -> HolderDeath:
        if isinstance(exc, HolderDeathError):
            death = exc.death
        else:  # the scope vanished under a slot: systemd removes it once bwrap is gone
            process = self.sandbox.process
            exited = process is not None and process.poll() is not None
            death = HolderDeath(LOST, "bwrap exited" if exited else "holder_operation_failed")
        self._death = death
        self.sandbox.kill()
        return death

    def _run(self, request: LeafRequest, progress: dict, *, transport=None, prepare_guest=None) -> LeafOutcome:
        sandbox, leaf = self.sandbox, request.leaf_id
        sandbox.require_quiescent()
        sandbox.check_scripts()
        if os.listdir(sandbox.runref):
            raise HolderDeathError(ESCAPE, 'holder_scripts_not_empty_before_leaf')
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
        leaf_info = leaf_dir.lstat()
        script_identity = leaf_info.st_dev, leaf_info.st_ino
        self._leaves += 1
        assert sandbox.root is not None
        slot = sandbox.root.create_slot(f"leaf:{self._leaves}:{leaf}")
        try:
            if transport is not None:
                capability = transport.start()
                prepared = prepare_guest(capability)
                del capability
                transport.check()
                profile.validate_leaf_request(prepared)
                if replace(request, argv=prepared.argv, env=prepared.env) != prepared:
                    raise HolderDeathError(ESCAPE, 'prepared_provider_request_changed')
                request = prepared
            sandbox.write_leaf_script(leaf,script_identity,profile.leaf_script(request))
            if transport is not None:
                transport.check()
            status, timed_out, lingered, duration_ms = self._execute(
                leaf, slot, request.timeout_sec, progress, transport=transport)
            sandbox.retire_leaf_script(leaf,script_identity)
            reads = self._import(request)
        finally:
            try:
                if transport is not None:
                    try:
                        if not progress.get('leaf_quiesced'):
                            try:
                                slot.kill()
                                slot.wait_empty(timeout_seconds=STATUS_GRACE)
                                progress['leaf_quiesced'] = True
                            except CONTAINMENT_ERRORS as error:
                                transport.observer.revoke()
                                if not (transport.observer.finished.wait(2.25)
                                        and transport.observer.quiesced.is_set()
                                        and sandbox._transport_scope_empty()):
                                    raise HolderDeathError(LOST, 'provider_leaf_close_unconfirmed') from error
                                progress['leaf_quiesced'] = True
                    finally:
                        transport.close()
                    sandbox.end_transport()
            finally:
                try:
                    _remove_slot(slot)
                finally:
                    sandbox.retire_leaf_script(leaf,script_identity)
        exited = not timed_out and not lingered
        return LeafOutcome(exit_code=None if timed_out else status, timed_out=timed_out, stdout=reads.stdout,
                           stderr=reads.stderr, stdout_truncated=reads.stdout_truncated,
                           stderr_truncated=reads.stderr_truncated, result_files=reads.files,
                           duration_ms=duration_ms, quiesced_by_exit=exited, holder_death=None,
                           lingered=lingered)

    def _execute(self, leaf: str, slot: CgroupV2ContainmentSlot, timeout_sec: float,
                 progress: dict, *, transport=None) -> tuple[int, bool, bool, int]:
        """Request, move, release and await one leaf; quiesce and check the spawner afterwards."""
        sandbox = self.sandbox
        if transport is not None:
            transport.check()
        pid = self._request(leaf)
        if transport is not None:
            transport.check()
        slot.add_pid(pid)
        if slot.members() != (pid,) or set(sandbox.slots["holder"].members()) != sandbox.recorded:
            raise HolderDeathError(ESCAPE, f"leaf {leaf} did not stay in its slot")
        started = wall_seconds()
        assert sandbox.gate_socket is not None
        if transport is not None:
            transport.check()
        sandbox.gate_socket.sendall(b"go\n")
        deadline = started + timeout_sec if transport is None else transport.observer.deadline_ns / 1e9
        status, timed_out, lingered = self._await_status(slot, deadline, progress, transport=transport)
        duration_ms = int((wall_seconds() - started) * 1000)
        slot.kill()
        try:
            slot.wait_empty(timeout_seconds=STATUS_GRACE)
        except ProviderIsolationStateError as exc:
            raise HolderDeathError(LOST, f"leaf slot of {leaf} did not quiesce") from exc
        progress['leaf_quiesced'] = True
        slot.remove()
        if transport is not None:
            transport.close()  # before whole-slot quiescence, result import or checkpoint
        sandbox.require_quiescent()
        sandbox.check_spawner()
        if transport is not None:
            sandbox.end_transport()
        return status, timed_out, lingered, duration_ms

    def _import(self, request: LeafRequest) -> LeafReads:
        """Bounded result import, then the post-leaf wipe of the scratch mounts (P27, P28)."""
        roots = self.sandbox.roots
        try:
            reads = read_leaf_results(roots["result"], request.leaf_id, stdout_limit=request.stdout_limit,
                                      stderr_limit=request.stderr_limit,
                                      max_bytes=profile.PROFILE_MIB["result"] << 20)
        except GuestRefusal as exc:
            raise HolderDeathError(ESCAPE, "result_read_refused") from exc
        except OSError as exc:
            raise HolderDeathError(LOST, "result_read_failed") from exc
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
                      progress: dict, *, transport=None) -> tuple[int, bool, bool]:
        """(status, timed out, lingered): the status line within its deadline, or a holder death."""
        grace: float | None = None
        while True:
            if transport is not None:
                transport.poll()
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
