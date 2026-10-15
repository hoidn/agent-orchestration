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
digest-pinned image (fixtures in `tests/e2e/run_ref_fixtures.py`); they skip
when that image is absent (see the README for how a fresh host imports it;
`RUN_REF_REQUIRE_IMAGE=1` turns the skip into a failure) or the user manager
is unreachable. The F3b-keyring witnesses live in `test_e2e_run_ref_keyring.py`.
"""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from tests.e2e.run_ref_fixtures import (
    IMAGE_RECORD, TREE_DIGEST, launch, sealed_rootfs, skip_unless_user_manager,
)  # noqa: F401 (fixtures)
from tests.e2e.run_ref_holder import Holder, keyed, members, populated
from tests.e2e.test_e2e_run_ref_confined_child import (
    PARENT, READ, REPOSITORY, _candidate, _child_memo, _git, _retained_checkpoint,
    _scope_units, _settled, refs,
)
from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.run_ref.holder_scope import recover_holder_scopes
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger

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


def _in_delegated_scope(body: str) -> dict:
    skip_unless_user_manager()
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
                   if Path(f"/proc/{pid}/cmdline").read_bytes() == b"sleep\x00300\x00"]

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

    class HostReadBlocked(BaseException):
        """Not an OSError, so the harness cannot class a blocked host open as a guest refusal."""

    def _hung(signum, frame):
        raise HostReadBlocked("host result read blocked")

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


TASK9_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule run_ref_confined) (export main)
  (defpath Artifact :kind relpath :under "out" :must-exist true)
  (defworkflow candidate-body ((seed Int)) -> Artifact
    (let* ((produced (command-result produce :argv ("python3" "produce.py") :returns Artifact))
           (verified (command-result verify :argv ("python3" "verify.py") :returns Artifact)))
      verified))
  (defworkflow main ((seed Int) (revision String)) -> String
    (let* ((child (run-ref :source (:repo "REPO" :commit revision)
                    :program (:workflow candidate-body) :inputs (:seed seed)
                    :policy (:environment :confined :image "IMAGE" :network :none
                             :limits (:wall-seconds 300 :memory-mib 1024 :cpus 1 :pids 64
                                      :workspace-mib 32 :output-mib 8)))))
      (match child
        ((COMPLETED c)
          (command-result consume :argv ("python3" "consume.py" c.result.value) :returns String))
        ((FAILED f) f.code)))))'''
TASK9_PRODUCE = '''import json, os
from pathlib import Path
path = Path("out/result.txt")
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("hello from the confined child\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("out/result.txt"))
'''
TASK9_VERIFY = '''import json, os
from pathlib import Path
path = Path("out/result.txt")
assert path.read_text() == "hello from the confined child\\n"
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("out/result.txt"))
'''
TASK9_CONSUME = '''import json, os, sys
from pathlib import Path
payload = Path(sys.argv[1]).read_text()
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps("parent consumed: " + payload))
'''

TASK9_OBSERVER = r'''
import json, os, time
from pathlib import Path
from orchestrator.workflow.run_ref import holder
from orchestrator.workflow.evaluated import runtime
control = Path(os.environ["TASK9_CONTROL"])
def log(name, row):
    with (control / name).open("ab", buffering=0) as stream:
        stream.write(json.dumps(row, sort_keys=True).encode() + b"\n")
def pause():
    (control / "committed.json").write_text(json.dumps({"pid": os.getpid()}))
    while True: time.sleep(1)
real_launch = holder.Holder.launch
def launch(self):
    log("holders.jsonl", {"unit": self.unit})
    return real_launch(self)
holder.Holder.launch = launch
real_leaf = holder.Holder.run_leaf
def run_leaf(self, request):
    log("dispatches.jsonl", {"unit": self.unit, "leaf": request.leaf_id})
    return real_leaf(self, request)
holder.Holder.run_leaf = run_leaf
real_append = runtime.append_record
paused = False
def append(path, row, **kwargs):
    global paused
    result = real_append(path, row, **kwargs)
    authority = kwargs.get("checked_authority")
    if (not paused and authority is not None and authority.confined
            and row.get("record") == "committed" and row.get("effect_class") == "command"):
        paused = True
        log("boundary.jsonl", {"identity": row["identity"], "record": row["record"], "effect_class": row["effect_class"]})
        if os.environ.get("TASK9_PAUSE_AFTER_COMMIT") == "1": pause()
    return result
runtime.append_record = append
'''


def _task9_cli(parent: Path, *arguments: str, control: Path | None = None,
               pause_after_commit: bool = False) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPOSITORY)}
    command = [sys.executable, "-m", "orchestrator", *arguments]
    if control is not None:
        (control / "sitecustomize.py").write_text(TASK9_OBSERVER)
        env.update(TASK9_CONTROL=str(control), TASK9_PAUSE_AFTER_COMMIT=str(int(pause_after_commit)))
        env["PYTHONPATH"] = os.pathsep.join((str(control), str(REPOSITORY)))
    return subprocess.run(command, cwd=parent, env=env, capture_output=True, text=True, timeout=600)


def _task9_start(parent: Path, control: Path, arguments: list[str], *, pause_after_commit: bool):
    number = len(list(control.glob("run-*.stdout.log")))
    stdout_path, stderr_path = control / f"run-{number}.stdout.log", control / f"run-{number}.stderr.log"
    stdout, stderr = stdout_path.open("wb"), stderr_path.open("wb")
    env = {**os.environ, "PYTHONPATH": str(REPOSITORY), "TASK9_CONTROL": str(control),
           "TASK9_PAUSE_AFTER_COMMIT": str(int(pause_after_commit))}
    (control / "sitecustomize.py").write_text(TASK9_OBSERVER)
    env["PYTHONPATH"] = os.pathsep.join((str(control), str(REPOSITORY)))
    command = [sys.executable, "-m", "orchestrator", *arguments]
    process = subprocess.Popen(command, cwd=parent, env=env, stdout=stdout, stderr=stderr,
                               start_new_session=True)
    return process, stdout, stderr, stdout_path, stderr_path, command


def _task9_wait_for_commit(process, control: Path, stderr_path: Path) -> None:
    deadline = time.monotonic() + 180
    marker = control / "committed.json"
    while not marker.exists():
        if process.poll() is not None:
            pytest.fail(f"CLI exited {process.returncode} before a child commit: {stderr_path.read_text()}")
        if time.monotonic() > deadline:
            pytest.fail(f"CLI did not reach a child commit: {stderr_path.read_text()}")
        time.sleep(0.02)


def _task9_run_tree(root: Path, *, exclude_image_store: bool = False) -> dict[str, tuple[int, int, int, bytes | None]]:
    rows = {}
    for path in sorted(root.rglob("*")):
        if exclude_image_store and path.relative_to(root).parts[0] == "images":
            continue
        stat = path.lstat()
        rows[path.relative_to(root).as_posix()] = (
            stat.st_mode, stat.st_size, stat.st_mtime_ns, path.read_bytes() if path.is_file() else None)
    return rows


def test_increment_a_public_lifecycle_with_commands(tmp_path, refs, request):
    root, image = refs
    repository = tmp_path / "candidate"
    repository.mkdir()
    _git(repository, "init", "--quiet")
    _git(repository, "config", "user.name", "Run Ref Task 9")
    _git(repository, "config", "user.email", "run-ref-task9@example.invalid")
    (repository / "produce.py").write_text(TASK9_PRODUCE)
    (repository / "verify.py").write_text(TASK9_VERIFY)
    _git(repository, "add", ".")
    _git(repository, "commit", "--quiet", "-m", "candidate")
    commit = _git(repository, "rev-parse", "HEAD")

    parent = tmp_path / "parent"
    parent.mkdir()
    source = parent / "run_ref_confined.orc"
    source.write_text(TASK9_SOURCE.replace("REPO", repository.as_uri()).replace("IMAGE", image))
    commands = parent / "commands.json"
    commands.write_text(json.dumps({
        "produce": {"stable_command": ["python3", "produce.py"], "closure": []},
        "verify": {"stable_command": ["python3", "verify.py"], "closure": []},
        "consume": {"stable_command": ["python3", "consume.py"], "closure": []},
    }))
    providers = parent / "providers.json"
    providers.write_text("{}")
    inputs = parent / "inputs.json"
    inputs.write_text(json.dumps({"revision": commit, "seed": 1}))
    (parent / "consume.py").write_text(TASK9_CONSUME)
    runs = parent / ".orchestrate" / "runs"
    runs.mkdir(parents=True)
    run_roots_before = set(runs.iterdir())

    def recover_only_this_tests_scopes():
        for owned_run in set(runs.iterdir()) - run_roots_before:
            for child in (owned_run / "run-ref-children").glob("*"):
                recover_holder_scopes(child / "holder")

    request.addfinalizer(recover_only_this_tests_scopes)
    control = tmp_path / "control"
    control.mkdir()
    evidence_dir = Path(os.environ.get("TASK9_EVIDENCE_DIR", tmp_path / "evidence"))
    evidence_dir.mkdir(parents=True, exist_ok=True)

    frontend = ["--entry-workflow", "run_ref_confined::main", "--source-root", str(parent),
                "--command-boundaries-file", str(commands), "--provider-externs-file", str(providers)]
    compile_argv = ["compile", str(source), *frontend]
    compiled = _task9_cli(parent, *compile_argv)
    assert compiled.returncode == 0, compiled.stderr
    summary = json.loads(compiled.stdout)
    artifact_path = Path(summary["artifact_paths"]["closed_program"])
    artifact = ClosedProgram.from_artifact(artifact_path.read_text())
    assert summary["program_digest"] == artifact.digest

    run_argv = ["run", str(source), *frontend, "--input-file", str(inputs), "--state-dir", str(runs),
                "--run-ref-root", str(root)]
    process, stdout, stderr, stdout_path, stderr_path, observed_run_argv = _task9_start(
        parent, control, run_argv, pause_after_commit=True)
    run_root = None
    controller_killed = False
    try:
        _task9_wait_for_commit(process, control, stderr_path)
        (run_root,) = tuple(runs.iterdir())
        initial_ledger = load_attempt_ledger(run_root / "run-ref-attempts.jsonl")
        initial_attempt = initial_ledger.rows[-1]
        (initial_child_root,) = (run_root / "run-ref-children").iterdir()
        initial_child_authority = load_run_authority(initial_child_root)
        initial_child_memo = _child_memo(initial_child_root)
        initial_commits = [entry.data for entry in initial_child_memo.active_commits.values()]
        initial_dispatches = [json.loads(line) for line in (control / "dispatches.jsonl").read_text().splitlines()]
        assert len(initial_commits) == len(initial_dispatches) == 1
        assert initial_commits[0]["effect_class"] == "command"
        assert initial_child_authority.run_root == initial_child_root
        paused_authority = load_run_authority(run_root)
        child_commit_boundary = json.loads((control / "boundary.jsonl").read_text().splitlines()[0])
        assert child_commit_boundary["effect_class"] == "command"
        os.kill(process.pid, signal.SIGKILL)
        assert process.wait(timeout=30) == -signal.SIGKILL
        controller_killed = True
    finally:
        if process.poll() is None:
            os.kill(process.pid, signal.SIGKILL)
            process.wait(timeout=30)
        stdout.close()
        stderr.close()
        if not controller_killed:
            for owned_run in set(runs.iterdir()) - run_roots_before:
                for child in (owned_run / "run-ref-children").glob("*"):
                    recover_holder_scopes(child / "holder")

    run_id = run_root.name
    resume_argv = ["resume", run_id, "--state-dir", str(runs), "--run-ref-root", str(root)]
    resumed = _task9_cli(parent, *resume_argv, control=control)
    if resumed.returncode != 0:
        for child in (run_root / "run-ref-children").glob("*"):
            recover_holder_scopes(child / "holder")
    assert resumed.returncode == 0, resumed.stderr
    authority, memo, site, workspace, child_root = _settled(parent)
    header, final = _retained_checkpoint(workspace, child_root)
    child_authority = load_run_authority(child_root)
    child_memo = _child_memo(child_root)
    ledger = load_attempt_ledger(run_root / "run-ref-attempts.jsonl")
    child_commits = [entry.data for entry in child_memo.active_commits.values()]
    dispatches_after_resume = [json.loads(line) for line in (control / "dispatches.jsonl").read_text().splitlines()]
    report_argv = ["report", "--run-id", run_id, "--runs-root", str(runs), "--format", "json"]
    report = _task9_cli(parent, *report_argv)
    assert report.returncode == 0, report.stderr
    rendered = json.loads(report.stdout)

    exported = site["value"]["result"]["value"]
    assert Path(parent / exported).read_text() == "hello from the confined child\n"
    assert memo.terminal.data["value"] == "parent consumed: hello from the confined child\n"
    assert authority.header["program_digest"] == artifact.digest == paused_authority.program.digest
    assert child_authority.header["program_digest"] == child_authority.program.digest
    assert child_memo.terminal.data["outcome"] == "completed"
    assert [row["effect_class"] for row in child_commits] == ["command", "command"]
    assert len(dispatches_after_resume) == 2
    assert dispatches_after_resume[0] == initial_dispatches[0]
    assert dispatches_after_resume[1]["leaf"] != initial_dispatches[0]["leaf"]
    assert all(row.attempt_ordinal == initial_attempt.attempt_ordinal == 1
               and row.bindings.child_run_id == initial_attempt.bindings.child_run_id
               for row in ledger.rows)
    assert ledger.rows[-1].bindings.child_run_id == initial_child_root.name
    assert final.digest == header.manifest_digest and not workspace.exists()
    assert not (child_root / "checkpoint.json").exists()
    assert ledger.rows[-1].event_kind == "cleanup_complete"
    assert site["value"]["result"]["workspace_delta"]
    assert rendered["run"]["workflow_outputs"] == memo.terminal.data["value"]

    before = _task9_run_tree(run_root)
    run_ref_before = _task9_run_tree(root, exclude_image_store=True)
    exported_bytes_before = Path(parent / exported).read_bytes()
    holders_before = (control / "holders.jsonl").read_bytes()
    dispatches_before = (control / "dispatches.jsonl").read_bytes()
    scopes_before = _scope_units()
    repeated = [_task9_cli(parent, *resume_argv, control=control) for _ in range(2)]
    assert [item.returncode for item in repeated] == [0, 0]
    assert _task9_run_tree(run_root) == before
    assert _task9_run_tree(root, exclude_image_store=True) == run_ref_before
    assert (control / "holders.jsonl").read_bytes() == holders_before
    assert (control / "dispatches.jsonl").read_bytes() == dispatches_before
    assert _scope_units() == scopes_before
    assert Path(parent / exported).read_bytes() == exported_bytes_before

    report_again = _task9_cli(parent, *report_argv)
    assert report_again.returncode == 0, report_again.stderr
    assert json.loads(report_again.stdout) == rendered
    assert _task9_run_tree(run_root) == before
    assert _task9_run_tree(root, exclude_image_store=True) == run_ref_before
    assert Path(parent / exported).read_bytes() == exported_bytes_before

    (evidence_dir / "compile.stdout.log").write_text(compiled.stdout)
    (evidence_dir / "compile.stderr.log").write_text(compiled.stderr)
    (evidence_dir / "run-interrupted.stdout.log").write_bytes(stdout_path.read_bytes())
    (evidence_dir / "run-interrupted.stderr.log").write_bytes(stderr_path.read_bytes())
    (evidence_dir / "resume.stdout.log").write_text(resumed.stdout)
    (evidence_dir / "resume.stderr.log").write_text(resumed.stderr)
    for number, item in enumerate(repeated, start=1):
        (evidence_dir / f"completed-resume-{number}.stdout.log").write_text(item.stdout)
        (evidence_dir / f"completed-resume-{number}.stderr.log").write_text(item.stderr)
    (evidence_dir / "report.stdout.json").write_text(report.stdout)
    (evidence_dir / "report.stderr.log").write_text(report.stderr)
    (evidence_dir / "report-again.stdout.json").write_text(report_again.stdout)
    (evidence_dir / "report-again.stderr.log").write_text(report_again.stderr)
    image_record = json.loads(IMAGE_RECORD.read_text())
    binary_pins = {}
    for binary in ("bwrap", "systemd-run", "systemctl", sys.executable):
        path = shutil.which(binary) if not Path(binary).is_absolute() else binary
        binary_pins[binary] = {"path": path, "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}
    (evidence_dir / "task9-evidence.json").write_text(json.dumps({
        "compile": {"argv": [sys.executable, "-m", "orchestrator", *compile_argv],
                    "returncode": compiled.returncode, "build_key": summary["build_key"],
                    "closed_artifact": str(artifact_path), "program_digest": artifact.digest},
        "run_interrupted": {"argv": observed_run_argv, "returncode": -signal.SIGKILL,
                            "run_id": run_id, "committed_child_effect": child_commit_boundary,
                            "stdout_log": str(stdout_path), "stderr_log": str(stderr_path)},
        "resume": {"argv": [sys.executable, "-m", "orchestrator", *resume_argv],
                   "returncode": resumed.returncode},
        "completed_resumes": [{"argv": [sys.executable, "-m", "orchestrator", *resume_argv],
                                "returncode": item.returncode} for item in repeated],
        "report": {"argv": [sys.executable, "-m", "orchestrator", *report_argv],
                   "returncode": report.returncode},
        "memo_terminal": memo.terminal.data["value"], "exported_path": exported,
        "ledger_events": [row.event_kind for row in ledger.rows],
        "attempt_ordinal": initial_attempt.attempt_ordinal,
        "child_run_id": initial_attempt.bindings.child_run_id,
        "initial_committed_effects": initial_commits,
        "final_committed_effects": child_commits,
        "holders": [json.loads(line) for line in (control / "holders.jsonl").read_text().splitlines()],
        "dispatches": [json.loads(line) for line in (control / "dispatches.jsonl").read_text().splitlines()],
        "image": image, "image_record": image_record, "image_record_sha256": hashlib.sha256(
            IMAGE_RECORD.read_bytes()).hexdigest(), "tree_digest": TREE_DIGEST,
        "binary_pins": binary_pins, "scope_units_after": _scope_units(),
    }, indent=2, sort_keys=True))


def test_provider_effects_refuse_before_holder_launch(tmp_path, refs):
    root, image = refs
    repository, commit = _candidate(tmp_path, READ)
    parent = tmp_path / "parent"
    parent.mkdir()
    control = tmp_path / "control"
    control.mkdir()
    source = PARENT.replace("REPO", repository.as_uri()).replace("IMAGE", image).replace("WALL", "60")
    source = source.replace('(command-result first :argv ("python3" "write.py") :returns Int)',
        "(provider-result providers.review :prompt prompts.base :inputs (seed) :returns Int)")
    source = source.replace(":network :none", ":network :model-only")
    (parent / "controller.orc").write_text(source)
    (parent / "boundaries.json").write_text(json.dumps({
        "second": {"stable_command": ["python3", "read.py"], "closure": []}}))
    (parent / "providers.json").write_text(json.dumps({"providers.review": "probe-provider"}))
    (parent / "prompts.json").write_text(json.dumps({"prompts.base": "prompt.md"}))
    (parent / "prompt.md").write_text("review\n")
    inputs = parent / "inputs.json"
    inputs.write_text(json.dumps({"revision": commit, "seed": 1}))
    units_before = _scope_units()

    refused_argv = ["run", str(parent / "controller.orc"), "--entry-workflow", "controller::run",
        "--source-root", str(parent), "--command-boundaries-file", str(parent / "boundaries.json"),
        "--provider-externs-file", str(parent / "providers.json"),
        "--prompt-externs-file", str(parent / "prompts.json"), "--input-file", str(inputs),
        "--state-dir", str(parent / ".orchestrate" / "runs"), "--run-ref-root", str(root)]
    refused = _task9_cli(parent, *refused_argv, control=control)
    units_after = _scope_units()

    assert refused.returncode == 2 and "run_ref_provider_transport_unavailable" in refused.stderr
    assert not (parent / ".orchestrate" / "runs").exists()
    assert units_after == units_before
    assert not (control / "holders.jsonl").exists()
    assert not (control / "dispatches.jsonl").exists()
    evidence_dir = Path(os.environ.get("TASK9_EVIDENCE_DIR", tmp_path / "evidence"))
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "provider-refusal.stdout.log").write_text(refused.stdout)
    (evidence_dir / "provider-refusal.stderr.log").write_text(refused.stderr)
    (evidence_dir / "provider-refusal.json").write_text(json.dumps({
        "argv": [sys.executable, "-m", "orchestrator", *refused_argv],
        "returncode": refused.returncode, "diagnostic": "run_ref_provider_transport_unavailable",
        "run_state_created": False, "scope_units_before": units_before, "scope_units_after": units_after,
    }, indent=2, sort_keys=True))
