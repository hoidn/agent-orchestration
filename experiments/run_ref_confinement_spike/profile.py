"""Throwaway spike of the `run_ref_confinement.v1` launch shape.

One delegated cgroup slot per child attempt with memory/pids/cpu limits; a
holder sandbox owns the namespaces and the tmpfs workspace; each leaf joins the
holder namespaces from the host through a release gate and its own leaf cgroup.
Must run inside `systemd-run --user --scope -p Delegate=yes` (see `ensure_delegated`).
"""
from __future__ import annotations

import io, json, os, signal, subprocess, sys, tarfile, time
from pathlib import Path

CGROUP_MOUNT = Path("/sys/fs/cgroup")
GUEST_PATH = "/usr/local/bin:/usr/bin:/bin"


def ensure_delegated(argv: list[str]) -> None:
    """Re-exec under a delegated transient scope unless already there."""
    if os.environ.get("RUNREF_SPIKE_SCOPE") == "1":
        return
    env = {**os.environ, "RUNREF_SPIKE_SCOPE": "1"}
    os.execvpe("systemd-run", ["systemd-run", "--user", "--scope", "-p", "Delegate=yes", "--quiet",
                               "--", sys.executable, *argv], env)


def _own_cgroup() -> Path:
    [row] = [line[3:] for line in Path("/proc/self/cgroup").read_text().splitlines() if line.startswith("0::")]
    return CGROUP_MOUNT / row.lstrip("/")


class Slot:
    """Delegated per-attempt slot: limits on the slot, leaves below it."""

    def __init__(self, name: str, *, memory_mib: int, pids: int, cpus: int) -> None:
        scope = _own_cgroup()
        if scope.name == "ctl":
            scope = scope.parent
        else:
            (scope / "ctl").mkdir()
            (scope / "ctl" / "cgroup.procs").write_text(str(os.getpid()))
            (scope / "cgroup.subtree_control").write_text("+memory +pids +cpu")
        self.path = scope / name
        self.path.mkdir()
        (self.path / "memory.max").write_text(str(memory_mib * 1024 * 1024))
        (self.path / "memory.swap.max").write_text("0")
        (self.path / "pids.max").write_text(str(pids))
        (self.path / "cpu.max").write_text(f"{cpus * 100000} 100000")
        self.limits = {k: (self.path / k).read_text().strip()
                       for k in ("memory.max", "memory.swap.max", "pids.max", "cpu.max")}

    def leaf(self, name: str) -> Path:
        path = self.path / name
        path.mkdir()
        return path

    def stat(self, name: str) -> str:
        return (self.path / name).read_text()

    @staticmethod
    def populated(cg: Path) -> bool:
        return "populated 1" in (cg / "cgroup.events").read_text()

    @staticmethod
    def kill_and_wait(cg: Path, timeout: float = 10) -> None:
        if Slot.populated(cg):
            (cg / "cgroup.kill").write_text("1")
        deadline = time.monotonic() + timeout
        while Slot.populated(cg):
            if time.monotonic() > deadline:
                raise RuntimeError(f"{cg} did not quiesce")
            time.sleep(0.01)

    def remove(self) -> None:
        for child in self.path.iterdir():
            if child.is_dir():
                self.kill_and_wait(child)
                child.rmdir()
        self.kill_and_wait(self.path)
        self.path.rmdir()


def _gated(argv: list[str], cgroup: Path, **popen) -> subprocess.Popen:
    """Start argv only after its PID is a member of `cgroup` (release gate)."""
    read_fd, write_fd = os.pipe()
    process = subprocess.Popen(["/bin/sh", "-c", f'read _ <&{read_fd}; exec {read_fd}<&-; exec "$@"', "gate", *argv],
                               pass_fds=(read_fd,), **popen)
    os.close(read_fd)
    (cgroup / "cgroup.procs").write_text(str(process.pid))
    if str(process.pid) not in (cgroup / "cgroup.procs").read_text().split():
        raise RuntimeError("process is absent from its leaf cgroup")
    os.write(write_fd, b"go\n")
    os.close(write_fd)
    return process


AGENT = r"""cd /
while :; do
  IFS= read -r id < /run/runref/req || exit 0
  d=/run/runref/$id
  ( read _ < "$d/gate"; mkdir -p "/tmp/.runref/$id"; cd /workspace &&
    /bin/sh "$d/leaf.sh" < "$d/stdin" > "/tmp/.runref/$id/out" 2> "/tmp/.runref/$id/err";
    echo $? > "/tmp/.runref/$id/status" ) &
  echo "$!" > "$d/pid"
done
"""


class Holder:
    """Owns namespaces, the sealed rootfs view, the tmpfs workspace and scratch.

    AppArmor on the reference host lets only bwrap gain capabilities in a user
    namespace, so leaves cannot join the holder from the host (nsenter/setns
    and bwrap --bind-fd from /proc/<pid>/root both fail). Leaves are forked by
    an image `/bin/sh` spawner inside the holder, gated until the host has
    moved them into their own leaf cgroup. The spawner is guest code: the host
    trusts only cgroup membership/quiescence and bounded post-quiescence reads.
    """

    def __init__(self, slot: Slot, rootfs: Path, result_dir: Path, control: Path, *,
                 workspace_mib: int, scratch_mib: int, extra: tuple[str, ...] = ()) -> None:
        self.slot = slot
        self.control = control
        control.mkdir(mode=0o700)
        os.mkfifo(control / "req", 0o600)
        self.cgroup = slot.leaf("holder")
        info_read, info_write = os.pipe()
        argv = ["bwrap", "--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-net",
                "--unshare-uts", "--unshare-cgroup", "--disable-userns", "--die-with-parent",
                "--new-session", "--cap-drop", "ALL", "--clearenv", "--setenv", "PATH", GUEST_PATH,
                "--setenv", "HOME", "/tmp",
                "--ro-bind", str(rootfs), "/", "--dev", "/dev", "--proc", "/proc",
                "--size", str(workspace_mib << 20), "--tmpfs", "/workspace",
                "--size", str(scratch_mib << 20), "--tmpfs", "/tmp",
                "--tmpfs", "/run", "--ro-bind", str(control), "/run/runref",
                "--bind", str(result_dir), "/result", *extra,
                "--info-fd", str(info_write), "--", "/bin/sh", "-c", AGENT]
        read_fd, write_fd = os.pipe()
        self.process = subprocess.Popen(
            ["/bin/sh", "-c", f'read _ <&{read_fd}; exec {read_fd}<&-; exec "$@"', "gate", *argv],
            pass_fds=(read_fd, info_write), stdin=subprocess.DEVNULL)
        os.close(read_fd)
        os.close(info_write)
        (self.cgroup / "cgroup.procs").write_text(str(self.process.pid))
        os.write(write_fd, b"go\n")
        os.close(write_fd)
        with os.fdopen(info_read) as info:
            self.child_pid = json.loads(info.read() or "{}")["child-pid"]
        self.argv = argv

    def host_view(self, guest_path: str = "/workspace") -> Path:
        """Host path of a guest directory, valid while the holder lives."""
        return Path(f"/proc/{self.child_pid}/root") / guest_path.lstrip("/")

    def _host_pid(self, ns_pid: int) -> int:
        for host_pid in (self.cgroup / "cgroup.procs").read_text().split():
            status = Path(f"/proc/{host_pid}/status").read_text()
            nspid = [line for line in status.splitlines() if line.startswith("NSpid:")][0].split()
            if int(nspid[-1]) == ns_pid:
                return int(host_pid)
        raise RuntimeError("spawned leaf is not a holder member")

    def leaf(self, name: str, argv: list[str], *, stdin: bytes = b"", timeout: float = 30,
             env: dict[str, str] | None = None, output_limit: int = 1 << 20) -> dict:
        import shlex
        d = self.control / name
        d.mkdir(mode=0o700)
        os.mkfifo(d / "gate", 0o600)
        os.mkfifo(d / "pid", 0o600)
        (d / "stdin").write_bytes(stdin)
        guest_env = ["PATH=" + GUEST_PATH, "HOME=/tmp", *(f"{k}={v}" for k, v in (env or {}).items())]
        (d / "leaf.sh").write_text("exec /usr/bin/env -i " + shlex.join([*guest_env, *argv]) + "\n")
        for path in d.iterdir():
            os.chmod(path, 0o644 if path.name in ("stdin", "leaf.sh") else 0o666)
        os.chmod(d, 0o755)
        cgroup = self.slot.leaf(name)
        with open(self.control / "req", "w") as req:
            req.write(name + "\n")
        with open(d / "pid") as pid_pipe:
            ns_pid = int(pid_pipe.read().strip())
        (cgroup / "cgroup.procs").write_text(str(self._host_pid(ns_pid)))
        started = time.monotonic()
        with open(d / "gate", "w") as gate:
            gate.write("go\n")
        timed_out = False
        status_path = self.host_view(f"/tmp/.runref/{name}/status")
        while Slot.populated(cgroup) and not status_path.exists():
            if time.monotonic() - started > timeout:
                timed_out = True
                break
            time.sleep(0.01)
        settle = time.monotonic() + 0.5
        while not timed_out and Slot.populated(cgroup) and time.monotonic() < settle:
            time.sleep(0.01)
        lingering = Slot.populated(cgroup) and not timed_out
        Slot.kill_and_wait(cgroup)
        cgroup.rmdir()
        out_dir = self.host_view(f"/tmp/.runref/{name}")
        read = lambda n: (out_dir / n).read_bytes()[:output_limit].decode(errors="replace") if (out_dir / n).exists() else ""
        status = read("status").strip()
        return {"returncode": int(status) if status.isdigit() else None, "stdout": read("out"),
                "stderr": read("err")[-2000:], "timed_out": timed_out,
                "lingering_descendants_killed": lingering,
                "seconds": round(time.monotonic() - started, 3)}

    def seed(self, clone: Path) -> dict:
        """Copy the clone into the tmpfs workspace from inside the slot (charged to it)."""
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as archive:
            archive.add(clone, arcname=".", filter=lambda info: None if info.issym() or info.islnk() or info.isdev() else info)
        return self.leaf("seed", ["/usr/bin/tar", "-x", "--no-same-owner", "-C", "/workspace", "-f", "-"],
                         stdin=buffer.getvalue())

    def stop(self) -> None:
        Slot.kill_and_wait(self.cgroup)
        self.process.wait(timeout=10)
