"""F3 substrate facts for the run-ref confinement profile on a real host.

Each case runs a small script inside `systemd-run --user --scope -p
Delegate=yes`, moves the controller into a leaf cgroup, enables
memory/pids/cpu for sibling slots and launches rootless bwrap in a slot.
The full profile (imported image, holder/spawner, escape negatives) is
recorded in docs/reports/run-ref-confinement-feasibility/README.md.

The F3b-channel tests below drive the throwaway holder in
`tests/e2e/run_ref_holder.py` in the D-a shape (one `systemd-run --user
--scope` unit per launch with the limits and `OOMPolicy` as unit properties,
token-gated launcher, socketpair channels, `setsid` leaves) over the Task 1
digest-pinned image; they skip when that image is absent (see the README for
how a fresh host imports it; `RUN_REF_REQUIRE_IMAGE=1` turns the skip into a
failure) or the user manager is unreachable.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.e2e.run_ref_holder import (IMAGE_RECORD, TREE_DIGEST, Holder, keyed, members, populated,
                                     tree_digest)

pytestmark = pytest.mark.e2e

SCOPE_SETUP = textwrap.dedent('''
    import json, os, subprocess
    from pathlib import Path
    scope = Path("/sys/fs/cgroup") / Path(open("/proc/self/cgroup").read().split("::")[1].strip()).relative_to("/")
    own_scope_error = None
    try:
        (scope / "cgroup.subtree_control").write_text("+memory")
    except OSError as exc:
        own_scope_error = exc.errno
    (scope / "ctl").mkdir()
    (scope / "ctl" / "cgroup.procs").write_text(str(os.getpid()))
    (scope / "cgroup.subtree_control").write_text("+memory +pids +cpu")
    slot = scope / "slot"
    slot.mkdir()
    def limit(name, value):
        (slot / name).write_text(value)
    def stat(name):
        return dict(line.split() for line in (slot / name).read_text().splitlines())
    def sandbox(script, *mounts):
        argv = ["bwrap", "--unshare-all", "--unshare-user", "--disable-userns", "--die-with-parent", "--cap-drop", "ALL",
                "--clearenv", "--setenv", "PATH", "/usr/bin:/bin",
                "--ro-bind", "/usr", "/usr", "--symlink", "usr/bin", "/bin", "--symlink", "usr/lib", "/lib",
                "--symlink", "usr/lib64", "/lib64", "--dev", "/dev", "--proc", "/proc", *mounts,
                "--", "/bin/sh", "-c", script]
        gate = 'echo $$ > "$0/cgroup.procs" && exec "$@"'
        return subprocess.run(["/bin/sh", "-c", gate, str(slot), *argv],
                              capture_output=True, text=True, timeout=60)
''')


def _skip_unless_user_manager() -> None:
    skip_if_no_e2e()
    for command in ("bwrap", "systemd-run", "systemctl"):
        skip_if_no_cli(command)
    if subprocess.run(["systemctl", "--user", "show", "-p", "Version"], capture_output=True,
                      timeout=15).returncode != 0:
        pytest.skip("user systemd manager unreachable")


def _in_delegated_scope(body: str) -> dict:
    _skip_unless_user_manager()
    script = SCOPE_SETUP + textwrap.dedent(body)
    completed = subprocess.run(
        ["systemd-run", "--user", "--scope", "-p", "Delegate=yes", "--quiet", "--",
         sys.executable, "-c", script],
        capture_output=True, text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_controller_scope_needs_a_leaf_before_slots_can_carry_limits():
    facts = _in_delegated_scope('''
        limits = {"cpu.max", "memory.max", "pids.max"}
        print(json.dumps({"own_scope_errno": own_scope_error,
                          "slot_limits": sorted(p.name for p in slot.iterdir() if p.name in limits)}))
    ''')

    assert facts == {"own_scope_errno": 16, "slot_limits": ["cpu.max", "memory.max", "pids.max"]}


def test_unshared_network_sandbox_has_only_loopback_and_no_route():
    # connect_ex returns 0 when a route exists; the unshared namespace yields ENETUNREACH.
    facts = _in_delegated_scope('''
        import errno
        done = sandbox("cat /proc/net/dev | tail -n +3 | cut -d: -f1 | tr -d ' '; "
                       "python3 -c 'import socket; s = socket.socket(); s.settimeout(3); "
                       "print(s.connect_ex((\\"1.1.1.1\\", 53)))'")
        interfaces, code = done.stdout.split()[:-1], int(done.stdout.split()[-1])
        print(json.dumps({"interfaces": interfaces, "connect": errno.errorcode.get(code, code)}))
    ''')

    assert facts == {"interfaces": ["lo"], "connect": "ENETUNREACH"}


def test_slot_pids_max_bounds_a_fork_loop_inside_the_sandbox():
    facts = _in_delegated_scope('''
        limit("pids.max", "16")
        done = sandbox("n=0; while [ $n -lt 64 ]; do sleep 5 & n=$((n+1)); done 2>/dev/null; wait")
        print(json.dumps({"pids_events_max": int(stat("pids.events")["max"]) > 0}))
    ''')

    assert facts == {"pids_events_max": True}


def test_slot_memory_max_kills_an_allocation_beyond_the_limit():
    facts = _in_delegated_scope('''
        limit("memory.max", str(64 << 20)); limit("memory.swap.max", "0")
        done = sandbox("head -c 200000000 /dev/zero | tail > /dev/null")
        print(json.dumps({"oom_kill": int(stat("memory.events")["oom_kill"]) > 0}))
    ''')

    assert facts == {"oom_kill": True}


def test_tmpfs_workspace_is_size_bounded_and_charged_to_the_slot():
    facts = _in_delegated_scope('''
        limit("memory.max", str(256 << 20)); limit("memory.swap.max", "0")
        done = sandbox("dd if=/dev/zero of=/workspace/big bs=1M count=32 2>/dev/null; "
                       "stat -c %s /workspace/big; "
                       "sleep 0.2", "--size", str(16 << 20), "--tmpfs", "/workspace")
        peak = int((slot / "memory.peak").read_text())
        print(json.dumps({"written": int(done.stdout.split()[0]) <= 16 << 20,
                          "charged": peak >= 15 << 20}))
    ''')

    assert facts == {"written": True, "charged": True}


# ---------------------------------------------------------------------------
# F3b-channel: holder topology and channel confinement (Task 5a)
# ---------------------------------------------------------------------------

CHANNEL_PROBE = r"""
import ctypes, errno, json, os, time
libc = ctypes.CDLL(None, use_errno=True)
def fds(pid):
    return {n: os.readlink(f"/proc/{pid}/fd/{n}") for n in os.listdir(f"/proc/{pid}/fd")}
def reopen(pid, n):
    try:
        os.close(os.open(f"/proc/{pid}/fd/{n}", os.O_RDWR | os.O_NONBLOCK))
        return "opened"
    except OSError as exc:
        return errno.errorcode[exc.errno]
def getfd(pid, n):
    pidfd = os.pidfd_open(pid)
    got = libc.syscall(438, pidfd, int(n), 0)  # pidfd_getfd
    os.close(pidfd)
    if got < 0:
        return errno.errorcode[ctypes.get_errno()]
    os.close(got)
    return "obtained"
spawner = os.getppid()
visible = sorted(int(p) for p in os.listdir("/proc") if p.isdigit())
pids = {"pid1" if pid == 1 else "spawner" if pid == spawner else str(pid): pid
        for pid in visible if pid != os.getpid()}
tables = {name: fds(pid) for name, pid in pids.items()}
probes = [{"process": name, "target": target, "open": reopen(pids[name], n), "pidfd_getfd": getfd(pids[name], n)}
          for name, table in tables.items() for n, target in table.items() if target != "/dev/null"]
r, w = os.pipe()
child = os.fork()
if child == 0:
    time.sleep(5)
    os._exit(0)
own_child = getfd(child, r)
os.kill(child, 9)
os.waitpid(child, 0)
print(json.dumps({"pid": os.getpid(), "visible": visible, "spawner": spawner, "sid": os.getsid(0), "pgid": os.getpgid(0),
                  "spawner_pgid": os.getpgid(spawner), "tables": tables, "probes": probes,
                  "own_child_pidfd_getfd": own_child}))
"""

SCRATCH_PROBE = r"""
import errno, json, os, sys
def create(path):
    try:
        open(path, "x").close()
        return "created"
    except OSError as exc:
        return errno.errorcode[exc.errno]
seen = {d: sorted(os.listdir(d)) for d in ("/result", f"/result/{sys.argv[1]}", "/tmp", "/dev/shm")}
creates = {path: create(path) for path in ("/dev/x", "/run/x", "/run/runref/x")}
fd = os.open("/dev/shm/fill", os.O_WRONLY | os.O_CREAT)
written, error = 0, None
try:
    while True:
        written += os.write(fd, bytes(1 << 16))
except OSError as exc:
    error = errno.errorcode[exc.errno]
os.close(fd)
os.makedirs("/result/scratch-b", exist_ok=True)  # pre-create a later leaf's result directory
for path in ("/result/scratch-b/forged", f"/result/{sys.argv[1]}/extra", "/tmp/left", "/dev/shm/left"):
    open(path, "w").close()
host = open("/workspace/from-host").read() if os.path.exists("/workspace/from-host") else None
print(json.dumps({"seen": seen, "creates": creates, "shm_written": written, "shm_error": error, "host_file": host}))
"""


@pytest.fixture(scope="module")
def sealed_rootfs() -> Path:
    _skip_unless_user_manager()
    if not IMAGE_RECORD.exists():
        message = f"Task 1 image record {IMAGE_RECORD} absent; import it as the feasibility README describes"
        if os.getenv("RUN_REF_REQUIRE_IMAGE") == "1":
            pytest.fail(message)
        pytest.skip(message)
    rootfs = Path(json.loads(IMAGE_RECORD.read_text())["rootfs"])
    assert tree_digest(rootfs) == TREE_DIGEST, "sealed rootfs does not match the pinned tree digest"
    return rootfs


@pytest.fixture
def launch(sealed_rootfs, tmp_path):
    started: list[Holder] = []

    def _launch(release: str | None = "token", **limits) -> Holder:
        holder = Holder(sealed_rootfs, tmp_path, **limits)
        started.append(holder)
        return holder.launch(release=release)

    yield _launch
    reports, errors = [], []
    for holder in started:  # stop every holder even when one stop raises
        try:
            reports.append((holder.unit, holder.stop()))
        except Exception as exc:  # re-raised below after the remaining holders are stopped
            errors.append(exc)
    if errors:
        raise errors[0]
    assert [unit for unit, report in reports if report.get("scope_populated")] == []


def _scope_active(holder: Holder) -> str:
    return subprocess.run(["systemctl", "--user", "is-active", holder.unit], capture_output=True,
                          text=True, timeout=15).stdout.strip()


def test_holder_channels_descriptors_and_scope_shape(launch):
    holder = launch()
    scope_root_procs = members(holder.cg)
    channels = holder.run("channels", "exec python3 /run/runref/channels/probe.py\n",
                          files={"probe.py": CHANNEL_PROBE})
    facts = json.loads(channels["stdout"])
    kill_zero = holder.run("killzero", "echo $$; trap 'kill 0' EXIT; exit 0\n")
    scratch_a = holder.run("scratch-a", "exec python3 /run/runref/scratch-a/probe.py scratch-a\n",
                           files={"probe.py": SCRATCH_PROBE})
    holder.write_workspace("from-host", b"written through /proc/<holder>/root\n")
    scratch_b = holder.run("scratch-b", "exec python3 /run/runref/scratch-b/probe.py scratch-b\n",
                           files={"probe.py": SCRATCH_PROBE})
    after = json.loads(scratch_b["stdout"])
    targets = {target for table in facts["tables"].values() for target in table.values()}
    spawner_sockets = {t for t in facts["tables"]["spawner"].values() if t.startswith("socket:")}

    assert {
        "read_back": holder.readback["unit"] | holder.readback["cgroup"],
        "launcher_in_holder_scope_root_empty": (holder.process.pid in holder.recorded, scope_root_procs),
        "outcomes": [r["outcome"] for r in (channels, kill_zero, scratch_a, scratch_b)],
        "visible_processes": facts["visible"] == [1, facts["spawner"], facts["pid"]],
        "in_namespace_descriptors": targets - {"/dev/null"} - holder.channels,
        "spawner_sockets_are_the_channels": spawner_sockets == holder.channels,
        "reachable": [p for p in facts["probes"] if p["open"] == "opened" or p["pidfd_getfd"] == "obtained"],
        "socket_errors": sorted({(p["open"], p["pidfd_getfd"]) for p in facts["probes"]
                                 if p["target"] in holder.channels}),
        "own_child_pidfd_getfd": facts["own_child_pidfd_getfd"],
        "leaf_pid_is_ack": (facts["pid"], channels["leaf_nspid"]) == (channels["ack"], channels["ack"]),
        "leaf_own_session": facts["sid"] == facts["pid"] != facts["spawner_pgid"],
        "kill_zero_spawner_survives": (kill_zero["stdout"].strip() == str(kill_zero["ack"]),
                                       scratch_a["ack"] > kill_zero["ack"]),
        "dev_run_creates": after["creates"],
        "shm_fill": (after["shm_error"], (8 << 20) - (1 << 20) <= after["shm_written"] <= 8 << 20),
        "earlier_scratch_gone": after["seen"],
        "host_write_visible": after["host_file"],
        "holder_slot_equals_recorded": members(holder.cg / "holder") == holder.recorded,
    } == {
        "read_back": {"MemoryMax": str(256 << 20), "MemorySwapMax": "0", "TasksMax": "64",
                      "CPUQuotaPerSecUSec": "1s", "OOMPolicy": "continue", "Delegate": "yes",
                      "ControlGroup": "/" + str(holder.cg.relative_to("/sys/fs/cgroup")),
                      "memory.max": str(256 << 20), "memory.swap.max": "0", "pids.max": "64",
                      "cpu.max": "100000 100000"},
        "launcher_in_holder_scope_root_empty": (True, set()),
        "outcomes": ["exited"] * 4,
        "visible_processes": True,
        "in_namespace_descriptors": {"anon_inode:[eventfd]"},  # bwrap's own pid-1 eventfd, unreachable
        "spawner_sockets_are_the_channels": True,
        "reachable": [],
        "socket_errors": [("ENXIO", "EPERM")],
        "own_child_pidfd_getfd": "obtained",
        "leaf_pid_is_ack": True,
        "leaf_own_session": True,
        "kill_zero_spawner_survives": (True, True),
        "dev_run_creates": {"/dev/x": "EROFS", "/run/x": "EROFS", "/run/runref/x": "EROFS"},
        "shm_fill": ("ENOSPC", True),
        "earlier_scratch_gone": {"/result": ["scratch-b"], "/result/scratch-b": ["stderr", "stdout"],
                                 "/tmp": [], "/dev/shm": []},
        "host_write_visible": "written through /proc/<holder>/root\n",
        "holder_slot_equals_recorded": True,
    }


def test_fifo_and_pipe_placed_like_the_channels_reopen_from_a_leaf(launch, tmp_path):
    read_end, write_end = os.pipe()
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    fifo_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)
    try:
        holder = launch(extra_fds=(read_end, fifo_fd))
        facts = json.loads(holder.run("controls", "exec python3 /run/runref/controls/probe.py\n",
                                      files={"probe.py": CHANNEL_PROBE})["stdout"])
    finally:
        for fd in (read_end, write_end, fifo_fd):
            os.close(fd)
    kinds = {("pipe" if p["target"].startswith("pipe:") else "fifo" if p["target"] == str(fifo)
              else "socket" if p["target"] in holder.channels else p["target"]): p["open"]
             for p in facts["probes"] if p["process"] == "spawner"}

    assert kinds == {"pipe": "opened", "fifo": "opened", "socket": "ENXIO"}


def test_launcher_without_the_exact_release_token_never_starts_bwrap(launch):
    refused = {repr(release): launch(release=release) for release in (None, "not-the-launch-token")}

    assert {name: (h.child_pid, h.process.returncode, populated(h.cg)) for name, h in refused.items()} == {
        "None": (None, 97, False), "'not-the-launch-token'": (None, 98, False)}


def test_unit_property_limits_are_enforced_and_oom_keeps_the_scope(launch):
    holder = launch(memory_mib=128, tasks=32)
    oom_before = int(keyed(holder.cg / "memory.events")["oom_kill"])
    memory = holder.run("memory", "exec python3 -c 'b = [bytearray(16 << 20) for _ in range(32)]'\n", wall=30)
    oom_kills = int(keyed(holder.cg / "memory.events")["oom_kill"]) - oom_before
    pids = holder.run("pids", "exec python3 -c '" + "\n".join([
        "import os, time", "kids = []", "try:", "    for _ in range(100):", "        pid = os.fork()",
        "        if pid == 0:", "            time.sleep(30); os._exit(0)", "        kids.append(pid)",
        "except OSError as exc:", "    print(len(kids), exc.strerror)",
        "for kid in kids:", "    os.kill(kid, 9); os.waitpid(kid, 0)"]) + "'\n")
    cpu_before = int(keyed(holder.cg / "cpu.stat")["usage_usec"])
    wall = time.monotonic()
    cpu = holder.run("cpu", "for i in 1 2 3 4; do timeout 2 sh -c 'while :; do :; done' & done; wait\n")
    cpu_seconds = (int(keyed(holder.cg / "cpu.stat")["usage_usec"]) - cpu_before) / 1e6
    wall = time.monotonic() - wall
    forked = int(pids["stdout"].split()[0])

    assert {
        "memory": (memory["outcome"], memory["status"], oom_kills >= 1),
        "pids": (pids["outcome"], forked < 32, int(keyed(holder.cg / "pids.events")["max"]) >= 1),
        "cpu_one_core": (cpu["outcome"], len(os.sched_getaffinity(0)) > 1, cpu_seconds < 1.5 * wall),
        "scope_survives_oom": (_scope_active(holder), holder.quiescent()),
    } == {
        "memory": ("exited", 137, True),
        "pids": ("exited", True, True),
        "cpu_one_core": ("exited", True, True),  # four busy loops on a multi-CPU host
        "scope_survives_oom": ("active", True),
    }, (cpu_seconds, wall, forked)


def test_stopped_or_signalled_spawner_and_setsid_daemon_fail_the_attempt_with_an_empty_scope(launch):
    stopped, signalled, daemon = launch(), launch(), launch()
    outcomes = {
        "stopped": stopped.run("stop", "kill -STOP $PPID\n", wall=5),
        "signalled": signalled.run("signal", "kill -KILL $PPID\n", wall=5),
        "daemon": daemon.run("daemon", "setsid sleep 300 >/dev/null 2>&1 &\necho started\n", wall=5),
    }
    daemon_holder_slot = members(daemon.cg / "holder") == daemon.recorded
    daemon_left = [pid for cgroup in daemon.cg.rglob("cgroup.procs") for pid in cgroup.read_text().split()
                   if b"300" in Path(f"/proc/{pid}/cmdline").read_bytes()]

    assert {
        "outcomes": {name: (r["outcome"], r.get("reason")) for name, r in outcomes.items()},
        "dead_scopes_populated": [populated(h.cg) for h in (stopped, signalled)],
        "daemon_holder_quiescent": daemon.quiescent(),  # its scope empties at stop (fixture teardown asserts)
        "daemon_outside_holder_slot": daemon_holder_slot,
        "daemon_left_in_scope": daemon_left,
    } == {
        "outcomes": {"stopped": ("holder_death", "no status line within the deadline"),
                     "signalled": ("holder_death", "control socket EOF"),
                     "daemon": ("lingering", None)},
        "dead_scopes_populated": [False, False],
        "daemon_holder_quiescent": True,
        "daemon_outside_holder_slot": True,
        "daemon_left_in_scope": [],
    }


def test_host_refuses_a_fifo_result_file_promptly_as_escape_rejected(launch):
    holder = launch()

    def _hung(signum, frame):
        raise TimeoutError("host result read blocked")

    previous = signal.signal(signal.SIGALRM, _hung)
    signal.alarm(10)  # a blocking host open on the FIFO fails the test instead of hanging the suite
    started = time.monotonic()
    try:
        result = holder.run("fifo", "rm /result/fifo/stdout && mkfifo /result/fifo/stdout\n", wall=5)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    elapsed = time.monotonic() - started

    assert {
        "outcome": (result["outcome"], result.get("status"), result["reason"]),
        "prompt": elapsed < 2,
        "scope_populated": populated(holder.cg),
    } == {
        "outcome": ("escape_rejected", 0, "result read refused: /result/fifo/stdout is not a regular file"),
        "prompt": True,
        "scope_populated": False,
    }, elapsed
