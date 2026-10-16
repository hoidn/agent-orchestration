"""Linux process-tree cleanup for the native session probe."""

from __future__ import annotations

import ctypes
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence


@dataclass(frozen=True)
class Process:
    pid: int
    parent: int
    state: str
    start_time: int


@dataclass
class Invocation:
    ordinal: int
    process: subprocess.Popen[bytes]
    started: float
    leader_start_time: int | None
    tracked: dict[int, int] = field(default_factory=dict)
    tracking_ok: bool = True
    timed_out: bool = False
    quiescent: bool = False
    unexpected_descendants: bool = False
    finalized: bool = False
    returncode: int | None = None
    stop_requested: float | None = None
    provider_stopped: float | None = None
    cleanup_completed: float | None = None


def _enable_subreaper() -> None:
    if not Path("/proc/self/stat").exists():
        raise RuntimeError("process-tree quiescence requires Linux /proc")
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))


def _process_table() -> dict[int, Process]:
    table: dict[int, Process] = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            raw = (entry / "stat").read_text(encoding="ascii")
        except FileNotFoundError:
            continue
        except PermissionError as error:
            raise RuntimeError("cannot establish child process quiescence") from error
        end = raw.rfind(")")
        fields = raw[end + 2 :].split()
        if end < 0 or len(fields) < 20:
            raise RuntimeError("cannot parse Linux process state")
        pid = int(entry.name)
        table[pid] = Process(pid, int(fields[1]), fields[0], int(fields[19]))
    return table


def _descendants(root_pid: int, table: Mapping[int, Process]) -> set[int]:
    children: dict[int, list[int]] = {}
    for process in table.values():
        children.setdefault(process.parent, []).append(process.pid)
    found: set[int] = set()
    pending = [root_pid]
    while pending:
        parent = pending.pop()
        for child in children.get(parent, []):
            if child not in found:
                found.add(child)
                pending.append(child)
    return found


def _alive(pid: int, start_time: int, table: Mapping[int, Process]) -> bool:
    process = table.get(pid)
    return process is not None and process.start_time == start_time and process.state not in {"Z", "X"}


def _pidfd_open(pid: int) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    # Linux assigns pidfd_open syscall 434 on the supported 64-bit ABIs.
    descriptor = libc.syscall(434, pid, 0)
    if descriptor < 0:
        error_number = ctypes.get_errno()
        raise OSError(error_number, os.strerror(error_number))
    return int(descriptor)


def _reap(pids: set[int]) -> None:
    for pid in pids:
        try:
            os.waitpid(pid, os.WNOHANG)
        except (ChildProcessError, ProcessLookupError):
            pass


class ProcessTracker:
    """Track direct children and escaped descendants of this isolated runner."""

    def __init__(self) -> None:
        _enable_subreaper()
        if not hasattr(signal, "pidfd_send_signal"):
            raise RuntimeError("safe process termination requires Linux pidfd signaling")
        probe_fd = _pidfd_open(os.getpid())
        os.close(probe_fd)
        table = _process_table()
        self.runner_pid = os.getpid()
        self.baseline = {pid: table[pid].start_time for pid in _descendants(self.runner_pid, table)}
        self.invocations: list[Invocation] = []
        self.ambiguous_adoption = False
        self.pidfds: dict[tuple[int, int], int] = {}
        self.tracking_failures: list[dict[str, object]] = []

    def _remember_failure(self, process: Process, reason: str) -> bool:
        self.tracking_failures.append({"pid": process.pid, "start_time": process.start_time, "reason": reason})
        return False

    def _remember(self, process: Process) -> bool:
        identity = (process.pid, process.start_time)
        if identity in self.pidfds:
            return True
        descriptor: int | None = None
        stage = "pidfd_open"
        try:
            descriptor = _pidfd_open(process.pid)
            stage = "process identity recheck"
            current = _process_table().get(process.pid)
            if current is None or current.start_time != process.start_time:
                os.close(descriptor)
                return True
        except (OSError, RuntimeError) as error:
            if descriptor is not None:
                os.close(descriptor)
            if descriptor is None and isinstance(error, ProcessLookupError):
                try:
                    if not _alive(process.pid, process.start_time, _process_table()):
                        return True
                    return self._remember_failure(process, "pidfd_open failed while the original process remained alive")
                except (OSError, RuntimeError) as recheck_error:
                    return self._remember_failure(process, f"process identity recheck failed: {recheck_error}")
            return self._remember_failure(process, f"{stage} failed: {error}")
        self.pidfds[identity] = descriptor
        return True

    def _signal(self, identity: tuple[int, int], sig: signal.Signals) -> bool:
        descriptor = self.pidfds.get(identity)
        if descriptor is None:
            return False
        try:
            signal.pidfd_send_signal(descriptor, sig)
            return True
        except ProcessLookupError:
            return True
        except OSError:
            return False

    def _poll(self, invocation: Invocation) -> int | None:
        returncode = invocation.process.poll()
        if returncode is not None and invocation.provider_stopped is None:
            invocation.provider_stopped = time.monotonic()
        return returncode

    def launch(
        self, ordinal: int, argv: Sequence[str], *, cwd: Path,
        env: Mapping[str, str], stdout: int, stderr: int, allow_overlap: bool = False,
        stdin: int = subprocess.DEVNULL,
    ) -> Invocation:
        live = self._owned_live()
        if (
            self.ambiguous_adoption
            or any(not item.tracking_ok or (item.finalized and not item.quiescent) for item in self.invocations)
            or (not allow_overlap and (live or any(not item.finalized for item in self.invocations)))
        ):
            raise RuntimeError("cannot append a turn before earlier child quiescence is proven")
        started = time.monotonic()
        process = subprocess.Popen(
            list(argv), cwd=cwd, env=dict(env), stdin=stdin,
            stdout=stdout, stderr=stderr, start_new_session=True,
        )
        invocation = Invocation(ordinal, process, started, None)
        self.invocations.append(invocation)
        try:
            self.pidfds[(process.pid, -1)] = _pidfd_open(process.pid)
            table = _process_table()
            leader = table.get(process.pid)
            if leader is None:
                invocation.tracking_ok = False
            else:
                invocation.leader_start_time = leader.start_time
                self.pidfds[(process.pid, leader.start_time)] = self.pidfds.pop((process.pid, -1))
            self._capture(table)
        except (OSError, RuntimeError):
            invocation.tracking_ok = False
            self._stop_owned()
            raise
        return invocation

    def _capture_tree(self, invocation: Invocation, root: Process, table: Mapping[int, Process]) -> None:
        for pid in _descendants(root.pid, table):
            process = table[pid]
            invocation.tracked[pid] = process.start_time
            if not self._remember(process):
                invocation.tracking_ok = False

    def _capture(self, table: Mapping[int, Process]) -> None:
        known_leaders = {(item.process.pid, item.leader_start_time) for item in self.invocations}
        for invocation in self.invocations:
            roots = list(invocation.tracked.items())
            if invocation.leader_start_time is not None:
                roots.append((invocation.process.pid, invocation.leader_start_time))
            for pid, started in roots:
                root = table.get(pid)
                if root is not None and root.start_time == started:
                    self._capture_tree(invocation, root, table)
        adopted = [
            process for pid, process in table.items()
            if process.parent == self.runner_pid
            and (pid, process.start_time) not in known_leaders
            and self.baseline.get(pid) != process.start_time
            and not any(item.tracked.get(pid) == process.start_time for item in self.invocations)
        ]
        if not adopted:
            return
        candidates = [item for item in self.invocations if not item.finalized]
        if len(candidates) != 1:
            self.ambiguous_adoption = True
            for invocation in self.invocations:
                invocation.tracking_ok = False
                invocation.quiescent = False
        owner = candidates[0] if candidates else (self.invocations[-1] if self.invocations else None)
        for process in adopted:
            if not self._remember(process):
                for invocation in self.invocations:
                    invocation.tracking_ok = False
            if owner is not None:
                owner.tracked[process.pid] = process.start_time
                owner.unexpected_descendants = True
                self._capture_tree(owner, process, table)

    def _owned_live(self) -> set[tuple[int, int]]:
        try:
            table = _process_table()
            self._capture(table)
        except (OSError, RuntimeError):
            for item in self.invocations:
                item.tracking_ok = False
            return {(item.process.pid, item.leader_start_time or -1) for item in self.invocations}
        return self._live_identities(table)

    def _live_identities(self, table: Mapping[int, Process]) -> set[tuple[int, int]]:
        found = {identity for identity in self.pidfds if _alive(*identity, table)}
        for invocation in self.invocations:
            if self._poll(invocation) is None:
                found.add((invocation.process.pid, invocation.leader_start_time or -1))
            found.update((pid, started) for pid, started in invocation.tracked.items() if _alive(pid, started, table))
        return found

    def finish(self, invocation: Invocation, timeout: float) -> None:
        expired = False
        while self._poll(invocation) is None:
            now = time.monotonic()
            for active in self.invocations:
                if not active.finalized and self._poll(active) is None and now >= active.started + timeout:
                    active.timed_out = True
                    expired = True
            if expired:
                break
            self.refresh()
            time.sleep(0.02)
        if expired and invocation.timed_out:
            child_live = False
        else:
            try:
                table = _process_table()
                self._capture(table)
                child_live = any(_alive(pid, started, table) for pid, started in invocation.tracked.items())
            except (OSError, RuntimeError):
                invocation.tracking_ok = False
                child_live = bool(invocation.tracked)
        if expired or child_live or not invocation.tracking_ok:
            self._stop_owned()
        if child_live and not invocation.timed_out:
            invocation.unexpected_descendants = True
        self._finalize(invocation, reject_unexpected=True)

    def _finalize(self, invocation: Invocation, *, reject_unexpected: bool) -> None:
        try:
            invocation.returncode = invocation.process.wait(timeout=0.2)
        except subprocess.TimeoutExpired:
            invocation.tracking_ok = False
        _reap(set(invocation.tracked))
        try:
            table = _process_table()
            self._capture(table)
            still_live = self._poll(invocation) is None or any(
                _alive(pid, started, table) for pid, started in invocation.tracked.items()
            )
            invocation.quiescent = (
                invocation.tracking_ok and not self.ambiguous_adoption and not still_live
                and not (reject_unexpected and invocation.unexpected_descendants)
            )
        except (OSError, RuntimeError):
            invocation.tracking_ok = False
            invocation.quiescent = False
        invocation.finalized = True
        invocation.cleanup_completed = time.monotonic()

    def cancel(self, invocation: Invocation) -> None:
        self._stop_owned()
        self._finalize(invocation, reject_unexpected=False)

    def refresh(self) -> None:
        try:
            self._capture(_process_table())
        except (OSError, RuntimeError):
            for invocation in self.invocations:
                if not invocation.finalized:
                    invocation.tracking_ok = False

    def _stop_owned(self) -> None:
        deadline = time.monotonic() + 0.6
        clean_scans = 0
        sig = signal.SIGTERM
        self._signal_owned(sig)
        while time.monotonic() < deadline:
            table: dict[int, Process] | None = None
            try:
                table = _process_table()
                self._capture(table)
            except (OSError, RuntimeError):
                for invocation in self.invocations:
                    invocation.tracking_ok = False
            self._signal_owned(sig)
            clean_scans = clean_scans + 1 if table is not None and not self._live_identities(table) else 0
            if clean_scans >= 2:
                break
            sig = signal.SIGKILL
            time.sleep(0.02)
        for invocation in self.invocations:
            try:
                invocation.process.wait(timeout=max(0, deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                invocation.tracking_ok = False
        _reap({pid for pid, _ in self.pidfds})

    def _signal_owned(self, sig: signal.Signals) -> None:
        for invocation in self.invocations:
            if self._poll(invocation) is None and invocation.stop_requested is None:
                invocation.stop_requested = time.monotonic()
        for identity in list(self.pidfds):
            if not self._signal(identity, sig):
                for invocation in self.invocations:
                    invocation.tracking_ok = False
        for invocation in self.invocations:
            identity = (invocation.process.pid, invocation.leader_start_time if invocation.leader_start_time is not None else -1)
            if identity not in self.pidfds and invocation.process.poll() is None:
                # An unreaped direct child cannot have its PID reused.
                try:
                    invocation.process.kill()
                except ProcessLookupError:
                    pass
                except OSError:
                    invocation.tracking_ok = False

    def close(self) -> None:
        self._stop_owned()
        for descriptor in self.pidfds.values():
            try:
                os.close(descriptor)
            except OSError:
                for invocation in self.invocations:
                    invocation.tracking_ok = False
        self.pidfds.clear()
