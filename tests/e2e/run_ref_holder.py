"""Throwaway F3b-channel holder in the D-a shape (Task 5a evidence, not runtime code).

One holder launch = one transient `systemd-run --user --scope` unit
(`run-ref-<token prefix>.scope`, `Delegate=yes`, memory/swap/tasks/cpu limits
and `OOMPolicy` as unit properties) around a token-gated launcher. The
launcher reports its pid on a launch socket; the host resolves the scope
cgroup from that pid, reads the unit properties and cgroup limits back, moves
the launcher into `<scope>/holder`, verifies the scope root holds no process
and only then sends the exact launch token. EOF or any other line makes the
launcher exit (97/98) without starting `bwrap`. Before `exec bwrap` the
launcher points 0-2 at `/dev/null` and keeps only the control socket (3), the
gate socket (4), the `--info-fd` pipe (5) and the sealed rootfs descriptor (6).

Inside `bwrap` the image `/bin/sh` runs `SPAWNER`: per request line on the
control socket it forks a leaf subshell, acknowledges `ack <pid>`, waits and
reports `status <code>`. The subshell drops the control socket, blocks on one
`go` line from the gate socket, drops it and execs the image `setsid` over the
host-written `/run/runref/<leaf>/leaf.sh`. The host derives the leaf from the
holder slot's membership (exactly one member beyond the set recorded at
`ready`), moves it into its own leaf slot, then releases the gate.

Dependencies: a reachable user systemd manager with cpu/memory/pids
delegation, `bwrap` (0.9.0 flags), `systemctl`, a sealed rootfs containing
`/bin/sh`, `setsid`, `python3` and the empty mount points `/workspace` and
`/result` (see `IMAGE_RECORD`). Stateful effects: one transient scope and its
cgroup subtree per launch, killed by `stop()`; files only under `workdir`.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import secrets
import select
import shutil
import socket
import stat
import subprocess
import sys
import time
from pathlib import Path

# Task 1 image (docs/reports/run-ref-confinement-feasibility/README.md, F3).
IMAGE_RECORD = Path.home() / ".cache/run-ref-spike-images/records" / (
    "sha256-2b4f19dae3a777dfc3b76730bda1e82e1f66ab2a2686fa93ca78edbfb4f04ffe.json")
GUEST_PATH = "/usr/local/bin:/usr/bin:/bin"
ACK_SECONDS = 2.0       # spawner acknowledgement deadline
STATUS_GRACE = 2.0      # status line deadline once the leaf slot is empty or killed
CGROUP_MOUNT = Path("/sys/fs/cgroup")

LAUNCHER = r'''
import fcntl, os, sys
token = sys.argv[1].encode() + b"\n"
launch = int(sys.argv[2])
kept = [int(fd) for fd in sys.argv[3].split(",")]
os.write(launch, b"%d\n" % os.getpid())
line = b""
while not line.endswith(b"\n"):
    chunk = os.read(launch, 1)
    if not chunk:
        os._exit(97)
    line += chunk
if line != token:
    os._exit(98)
high = [fcntl.fcntl(fd, fcntl.F_DUPFD, 100) for fd in kept]
null = os.open("/dev/null", os.O_RDWR)
for fd in (0, 1, 2):
    os.dup2(null, fd)
os.closerange(3, 100)
for target, fd in enumerate(high, start=3):
    os.dup2(fd, target)
os.closerange(3 + len(high), 4096)
os.execvp(sys.argv[4], sys.argv[4:])
'''

SPAWNER = r'''echo ready >&3
while IFS= read -r leaf <&3; do
  (
    exec 3>&-
    IFS= read -r go <&4 || exit 125
    exec 4<&-
    [ "$go" = go ] || exit 125
    cd /workspace || exit 126
    exec setsid /bin/sh "/run/runref/$leaf/leaf.sh" <"/run/runref/$leaf/stdin" >"/result/$leaf/stdout" 2>"/result/$leaf/stderr"
  ) &
  echo "ack $!" >&3
  wait $!
  echo "status $?" >&3
done
'''


def tree_digest(rootfs: Path) -> str:
    """Canonical digest of the sealed tree, as recorded by the Task 1 importer."""
    rows = []
    for directory, dirs, files in os.walk(rootfs):
        dirs.sort()
        for name in sorted(dirs + files):
            path = Path(directory, name)
            rel = path.relative_to(rootfs).as_posix()
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                rows.append([rel, "symlink", os.readlink(path)])
            elif stat.S_ISDIR(info.st_mode):
                rows.append([rel, "dir", stat.S_IMODE(info.st_mode)])
            else:
                rows.append([rel, "file", stat.S_IMODE(info.st_mode), info.st_size,
                             hashlib.sha256(path.read_bytes()).hexdigest()])
    return "sha256:" + hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def members(cgroup: Path) -> set[int]:
    return {int(pid) for pid in (cgroup / "cgroup.procs").read_text().split()}


def populated(cgroup: Path) -> bool:
    return cgroup.exists() and "populated 1" in (cgroup / "cgroup.events").read_text()


def kill_and_wait(cgroup: Path, timeout: float = 10) -> bool:
    """`cgroup.kill` then wait until unpopulated; False when it stays populated."""
    if populated(cgroup):
        (cgroup / "cgroup.kill").write_text("1")
    deadline = time.monotonic() + timeout
    while populated(cgroup):
        if time.monotonic() > deadline:
            return False
        time.sleep(0.01)
    return True


def keyed(path: Path) -> dict[str, str]:
    return dict(line.split(maxsplit=1) for line in path.read_text().splitlines())


def nspid(pid: int) -> int:
    [row] = [line for line in Path(f"/proc/{pid}/status").read_text().splitlines() if line.startswith("NSpid:")]
    return int(row.split()[-1])


def _empty(dir_fd: int) -> None:
    for name in os.listdir(dir_fd):
        if stat.S_ISDIR(os.stat(name, dir_fd=dir_fd, follow_symlinks=False).st_mode):
            shutil.rmtree(name, dir_fd=dir_fd)
        else:
            os.unlink(name, dir_fd=dir_fd)


def _read(dir_fd: int, leaf: str, name: str, limit: int = 1 << 20) -> str:
    sub = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=dir_fd)
    try:
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=sub)
    finally:
        os.close(sub)
    with os.fdopen(fd, "rb") as handle:
        return handle.read(limit).decode(errors="replace")


class Holder:
    """One holder incarnation. `launch()` returns before release when the token is refused."""

    def __init__(self, rootfs: Path, workdir: Path, *, memory_mib: int = 256, tasks: int = 64,
                 cpu_percent: int = 100, oom_policy: str = "continue", shm_mib: int = 8,
                 extra_fds: tuple[int, ...] = ()) -> None:
        """`extra_fds` are inherited by the spawner from fd 7 on (positive controls only)."""
        self.token = secrets.token_hex(16)
        self.unit = f"run-ref-{self.token[:16]}.scope"
        self.limits = {"MemoryMax": memory_mib << 20, "MemorySwapMax": 0, "TasksMax": tasks,
                       "CPUQuota": cpu_percent, "OOMPolicy": oom_policy}
        self.runref = workdir / f"runref-{self.token[:8]}"
        self.runref.mkdir(mode=0o700)
        self.argv = ["bwrap", "--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-net",
                     "--unshare-uts", "--unshare-cgroup", "--disable-userns", "--die-with-parent",
                     "--new-session", "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", GUEST_PATH,
                     "--setenv", "HOME", "/tmp", "--ro-bind-fd", "6", "/",
                     "--dev", "/dev", "--size", str(shm_mib << 20), "--tmpfs", "/dev/shm",
                     "--remount-ro", "/dev", "--proc", "/proc",
                     "--size", str(32 << 20), "--tmpfs", "/workspace",
                     "--size", str(16 << 20), "--tmpfs", "/tmp",
                     "--size", str(16 << 20), "--tmpfs", "/result",
                     "--tmpfs", "/run", "--ro-bind", str(self.runref), "/run/runref", "--remount-ro", "/run",
                     "--info-fd", "5", "--", "/bin/sh", "-c", SPAWNER]
        self.rootfs, self.extra_fds = rootfs, extra_fds
        self.process: subprocess.Popen | None = None
        self.scope: Path | None = None
        self.child_pid: int | None = None
        self.recorded: set[int] = set()
        self.readback: dict = {}
        self.roots: dict[str, int] = {}
        self.dead = self.stopped = False
        self._buf = b""

    # -- launch -----------------------------------------------------------------
    def launch(self, release: str | None = "token") -> "Holder":
        """Start the gated launcher in a fresh scope; `release` = "token", None (EOF) or a wrong line."""
        launch_host, launch_guest = socket.socketpair()
        self.ctrl, ctrl_guest = socket.socketpair()
        self.gate, gate_guest = socket.socketpair()
        info_read, info_write = os.pipe()
        root = os.open(self.rootfs, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        self.channels = {f"socket:[{os.fstat(end.fileno()).st_ino}]" for end in (ctrl_guest, gate_guest)}
        kept = [ctrl_guest.fileno(), gate_guest.fileno(), info_write, root, *self.extra_fds]  # -> 3, 4, 5, 6, 7...
        properties = [f"MemoryMax={self.limits['MemoryMax']}", "MemorySwapMax=0",
                      f"TasksMax={self.limits['TasksMax']}", f"CPUQuota={self.limits['CPUQuota']}%",
                      f"OOMPolicy={self.limits['OOMPolicy']}", "Delegate=yes"]
        argv = ["systemd-run", "--user", "--scope", "--quiet", "--unit", self.unit,
                *(arg for prop in properties for arg in ("-p", prop)), "--",
                sys.executable, "-I", "-c", LAUNCHER, self.token, str(launch_guest.fileno()),
                ",".join(map(str, kept)), *self.argv]
        self.process = subprocess.Popen(argv, pass_fds=(launch_guest.fileno(), *kept), stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        for obj in (launch_guest, ctrl_guest, gate_guest):
            obj.close()
        os.close(info_write)
        os.close(root)
        try:
            launch_host.settimeout(15)
            reported = int(launch_host.recv(64).split(b"\n")[0])
            if reported != self.process.pid:
                raise RuntimeError(f"launcher reported {reported}, spawned {self.process.pid}")
            row = Path(f"/proc/{reported}/cgroup").read_text().strip().split("::", 1)[1]
            self.scope = CGROUP_MOUNT / row.lstrip("/")
            if self.scope.name != self.unit:
                raise RuntimeError(f"launcher is in {self.scope}, not {self.unit}")
            self.readback = self._read_back()
            holder = self.scope / "holder"
            holder.mkdir()
            (holder / "cgroup.procs").write_text(str(reported))
            if members(self.scope) or members(holder) != {reported}:
                raise RuntimeError("scope root not empty or launcher not in holder")
            (self.scope / "cgroup.subtree_control").write_text("+memory +pids")
            if release == "token":
                launch_host.sendall(self.token.encode() + b"\n")
            elif release is not None:
                launch_host.sendall(release.encode() + b"\n")
        except BaseException:
            os.close(info_read)
            raise
        finally:
            launch_host.close()  # EOF: an unreleased launcher exits 97 without starting bwrap
        info = _drain(info_read, deadline=time.monotonic() + 15)
        if not info:
            self.process.wait(timeout=10)
            return self
        self.child_pid = json.loads(info)["child-pid"]
        if self._line(time.monotonic() + 15) != "ready":
            raise RuntimeError("spawner did not report ready")
        self.recorded = members(self.scope / "holder")
        for mount in ("workspace", "tmp", "dev/shm", "result"):
            self.roots[mount] = os.open(f"/proc/{self.child_pid}/root/{mount}",
                                        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        if members(self.scope / "holder") != self.recorded:
            raise RuntimeError("holder membership changed while opening root descriptors")
        return self

    def _read_back(self) -> dict:
        names = ["MemoryMax", "MemorySwapMax", "TasksMax", "CPUQuotaPerSecUSec", "OOMPolicy", "Delegate",
                 "ControlGroup"]
        shown = subprocess.run(["systemctl", "--user", "show", self.unit, "-p", ",".join(names)],
                               capture_output=True, text=True, timeout=15, check=True).stdout
        unit = dict(line.split("=", 1) for line in shown.splitlines())
        files = {name: (self.scope / name).read_text().strip()
                 for name in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}
        expected_unit = {"MemoryMax": str(self.limits["MemoryMax"]), "MemorySwapMax": "0",
                         "TasksMax": str(self.limits["TasksMax"]),
                         "CPUQuotaPerSecUSec": f"{self.limits['CPUQuota'] // 100}s",  # multiples of 100 only
                         "OOMPolicy": self.limits["OOMPolicy"], "Delegate": "yes",
                         "ControlGroup": "/" + str(self.scope.relative_to(CGROUP_MOUNT))}
        expected_files = {"memory.max": str(self.limits["MemoryMax"]), "memory.swap.max": "0",
                          "pids.max": str(self.limits["TasksMax"]),
                          "cpu.max": f"{self.limits['CPUQuota'] * 1000} 100000"}
        if unit != expected_unit or files != expected_files:
            raise RuntimeError(f"run_ref_environment_unavailable: read-back {unit} {files}")
        return {"unit": unit, "cgroup": files}

    # -- leaves -----------------------------------------------------------------
    def _line(self, deadline: float) -> str | None:
        """One control-socket line; None on EOF; TimeoutError past `deadline`."""
        while b"\n" not in self._buf:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            self.ctrl.settimeout(remaining)
            chunk = self.ctrl.recv(4096)
            if not chunk:
                return None
            self._buf += chunk
        line, _, self._buf = self._buf.partition(b"\n")
        return line.decode()

    def quiescent(self) -> bool:
        slots = [p for p in self.scope.iterdir() if p.is_dir() and p.name != "holder"]
        return members(self.scope / "holder") == self.recorded and not any(map(populated, slots))

    def write_workspace(self, name: str, data: bytes) -> None:
        """Host write into the holder's tmpfs through `/proc/<holder>/root` (retained descriptor)."""
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644,
                     dir_fd=self.roots["workspace"])
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    def run(self, name: str, script: str, *, files: dict[str, str] | None = None, wall: float = 10,
            wipe: bool = True) -> dict:
        """One gated leaf; outcome is exited, lingering, timeout, holder_death or escape_rejected."""
        if self.dead or not self.quiescent():
            raise RuntimeError("holder not quiescent before a leaf")
        if wipe:
            for mount in ("tmp", "dev/shm", "result"):
                _empty(self.roots[mount])
        os.mkdir(name, 0o755, dir_fd=self.roots["result"])  # exclusive: EEXIST if pre-created
        leaf_dir = self.runref / name
        leaf_dir.mkdir()
        (leaf_dir / "leaf.sh").write_text(script)
        (leaf_dir / "stdin").write_bytes(b"")
        for file_name, text in (files or {}).items():
            (leaf_dir / file_name).write_text(text)
        slot = self.scope / f"leaf-{name}"
        slot.mkdir()
        result: dict = {"name": name}
        try:
            self.ctrl.sendall(name.encode() + b"\n")
            ack = self._line(time.monotonic() + ACK_SECONDS)
            if not ack or not ack.startswith("ack "):
                return self._holder_death(result, f"acknowledgement {ack!r}")
            result["ack"] = int(ack.split()[1])
            pid = self._new_member(time.monotonic() + ACK_SECONDS)
            if pid is None:
                return self._holder_death(result, "no leaf member", code="escape_rejected")
            (slot / "cgroup.procs").write_text(str(pid))
            if members(slot) != {pid} or members(self.scope / "holder") != self.recorded:
                return self._holder_death(result, "leaf move", code="escape_rejected")
            result["leaf_nspid"] = nspid(pid)
            started = time.monotonic()
            self.gate.sendall(b"go\n")
            result.update(self._await_status(slot, started + wall))
            result["seconds"] = round(time.monotonic() - started, 3)
            if result["outcome"] == "holder_death":
                return self._holder_death(result, result.pop("reason"))
            if not kill_and_wait(slot, timeout=STATUS_GRACE):
                return self._holder_death(result, "leaf slot did not quiesce")
            if not self.quiescent():
                return self._holder_death(result, "holder membership changed", code="escape_rejected")
            result["stdout"] = _read(self.roots["result"], name, "stdout")
            result["stderr"] = _read(self.roots["result"], name, "stderr")[-2000:]
            return result
        finally:
            if slot.exists():
                kill_and_wait(slot)
                slot.rmdir()
            shutil.rmtree(leaf_dir)

    def _new_member(self, deadline: float) -> int | None:
        while time.monotonic() < deadline:
            extra = members(self.scope / "holder") - self.recorded
            if len(extra) == 1:
                return extra.pop()
            if len(extra) > 1:
                return None
            time.sleep(0.005)
        return None

    def _await_status(self, slot: Path, wall_deadline: float) -> dict:
        grace: float | None = None
        timed_out = False
        while True:
            now = time.monotonic()
            if grace is None and not populated(slot):
                grace = now + STATUS_GRACE
            if grace is None and now > wall_deadline:
                timed_out = True
                kill_and_wait(slot, timeout=STATUS_GRACE)
                grace = time.monotonic() + STATUS_GRACE
            if grace is not None and now > grace:
                return {"outcome": "holder_death", "reason": "no status line within the deadline"}
            try:
                line = self._line(min(now + 0.05, grace or wall_deadline))
            except TimeoutError:
                continue
            if line is None:
                return {"outcome": "holder_death", "reason": "control socket EOF"}
            status = int(line.split()[1])
            time.sleep(0.05)  # the spawner reaped the leaf; descendants would still be members
            lingering = populated(slot)
            outcome = "timeout" if timed_out else "lingering" if lingering else "exited"
            return {"outcome": outcome, "status": status}

    def _holder_death(self, result: dict, reason: str, code: str = "lost") -> dict:
        """Kill and empty the whole scope; the pending attempt fails."""
        self.dead = True
        emptied = kill_and_wait(self.scope)
        result.update(outcome="holder_death" if code == "lost" else code, reason=reason,
                      scope_populated_after_kill=not emptied)
        return result

    # -- teardown ---------------------------------------------------------------
    def stop(self) -> dict:
        """Kill the scope, reap the launcher, close descriptors; report the scope state (idempotent)."""
        report = {}
        if self.stopped:
            return report
        self.stopped = True
        for fd in self.roots.values():
            os.close(fd)
        self.roots = {}
        if self.scope is not None and self.scope.exists():
            report["scope_emptied"] = kill_and_wait(self.scope)
            try:  # systemd removes the scope (and our slots) once it is empty
                for child in [p for p in self.scope.iterdir() if p.is_dir()]:
                    child.rmdir()
            except FileNotFoundError:
                pass
        if self.process is not None:
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=10)
            report["launcher_exit"] = self.process.returncode
            report["launcher_stderr"] = self.process.stderr.read().decode(errors="replace")[-2000:]
            self.process.stderr.close()
        for sock in (getattr(self, "ctrl", None), getattr(self, "gate", None)):
            if sock is not None:
                sock.close()
        deadline = time.monotonic() + 10
        while self.scope is not None and populated(self.scope) and time.monotonic() < deadline:
            time.sleep(0.01)
        report["scope_populated"] = self.scope is not None and populated(self.scope)
        # A unit stopped by systemd (e.g. OOMPolicy=stop) stays listed as failed; non-zero when already gone.
        subprocess.run(["systemctl", "--user", "reset-failed", self.unit], capture_output=True, timeout=15)
        shutil.rmtree(self.runref, ignore_errors=True)
        return report


def _drain(fd: int, deadline: float) -> bytes:
    """Read a pipe to EOF within `deadline`; closes `fd`."""
    data = b""
    try:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
                raise TimeoutError("info pipe did not close")
            chunk = os.read(fd, 4096)
            if not chunk:
                return data
            data += chunk
    finally:
        os.close(fd)
