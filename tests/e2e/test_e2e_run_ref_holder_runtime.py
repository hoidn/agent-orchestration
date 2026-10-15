"""Real launches through the run-ref holder runtime (`orchestrator/workflow/run_ref/holder.py`).

Task 6a witnesses, driven through `Holder.run_leaf` (not the throwaway F3b
harness): the profile shape seen from a leaf, timeout and output bounds, one
F3b-1 witness per spawner attribute (holder death naming it at the culprit's
own post-leaf quiescence), a FIFO stdout that cannot hang the broker, a
pre-created later `/result` entry that never reaches its leaf, stopped and
signalled spawners and a `setsid` daemon as in F3b-channel, unit-property
limits, and the `host` slot helper (N4). The image comes from
`tests/e2e/run_ref_image_fixture.py` (an OCI layout imported by the image
store); cases skip without ORCHESTRATE_E2E, the CLIs or a user manager.
"""

from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.holder import CGROUP_MOUNT, Holder
from orchestrator.workflow.run_ref.holder_broker import populated
from orchestrator.workflow.run_ref.leaf import HolderDeath, LeafRequest
from tests.e2e.run_ref_image_fixture import sealed_image  # noqa: F401 (fixture)

pytestmark = pytest.mark.e2e

PATH = {"PATH": "/usr/local/bin:/usr/bin:/bin"}
PYTHON = "/usr/local/bin/python3"
WORKSPACE_MIB = 32
LIMITS = {"wall-seconds": 600, "memory-mib": WORKSPACE_MIB + 960, "cpus": 1, "pids": 64,
          "workspace-mib": WORKSPACE_MIB, "output-mib": 1}
LOST = "run_ref_environment_lost"
ESCAPE = "run_ref_environment_escape_rejected"


def leaf(name: str, script: str | None = None, *, argv: tuple[str, ...] | None = None, timeout: float = 10,
         files: dict[str, bytes] | None = None, limit: int = 1 << 16) -> LeafRequest:
    return LeafRequest(leaf_id=name, argv=argv or ("/bin/sh", "-c", script or "true"), env=PATH,
                       cwd="/workspace", timeout_sec=timeout, stdout_limit=limit, stderr_limit=limit,
                       input_files=files or {}, network="none")


@pytest.fixture
def launch(sealed_image, tmp_path):
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    started: list[Holder] = []

    def _launch(**kwargs) -> Holder:
        holder = Holder(sealed_image, kwargs.pop("limits", LIMITS), control_dir=control, **kwargs)
        started.append(holder)
        return holder.launch()

    yield _launch
    for holder in started:
        holder.stop()
    assert [h.unit for h in started if h.scope is not None and populated(h.scope)] == []


PROFILE_PROBE = r"""
import ctypes, errno, json, os, sys
libc = ctypes.CDLL(None, use_errno=True)
def attempt(action):
    try:
        action()
        return "ok"
    except OSError as exc:
        return errno.errorcode[exc.errno]
def keyctl():
    if libc.syscall(250, 0, -3, 0) < 0:  # KEYCTL_GET_KEYRING_ID of the session keyring
        raise OSError(ctypes.get_errno(), "keyctl")
def fds(pid):
    return sorted(os.readlink(f"/proc/{pid}/fd/{n}") for n in os.listdir(f"/proc/{pid}/fd"))
spawner = os.getppid()
json.dump({
    "env": dict(row.split("=", 1) for row in open("/proc/self/environ").read().split("\0") if row),
    "cwd": os.getcwd(), "own_session": os.getsid(0) == os.getpid(),
    "spawner_session": os.getsid(spawner) != os.getpid(),
    "processes": sorted(int(p) for p in os.listdir("/proc") if p.isdigit()) == sorted({1, spawner, os.getpid()}),
    "in_namespace_fds": sorted(set(fds(1) + fds(spawner)) - {"/dev/null"}),
    "keyctl": attempt(keyctl),
    "proc_keys": [attempt(lambda: open(p).read()) for p in ("/proc/keys", "/proc/key-users")],
    "creates": {p: attempt(lambda: open(p, "x").close())
                for p in ("/dev/x", "/run/x", "/run/runref/x", "/workspace/.git/x")},
    "no_sysfs": os.listdir("/sys") if os.path.isdir("/sys") else None,
    "git_head": open("/workspace/.git/HEAD").read(),
    "interfaces": [line.split(":")[0].strip() for line in open("/proc/net/dev").read().splitlines()[2:]],
    "inputs": sorted(os.listdir("/result/probe")),
}, sys.stdout)
open("/result/probe/value.json", "w").write("[42]")
"""


def test_leaf_sees_the_profile_shape_through_the_runtime(launch, tmp_path):
    git = tmp_path / "git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n")
    git_fd = os.open(git, os.O_RDONLY | os.O_DIRECTORY)
    try:
        holder = launch(git_dir_fd=git_fd)
        outcome = holder.run_leaf(leaf("probe", argv=(PYTHON, "/result/probe/probe.py"),
                                       files={"probe.py": PROFILE_PROBE.encode()}))
    finally:
        os.close(git_fd)
    facts = json.loads(outcome.stdout)
    sockets = [target for target in facts.pop("in_namespace_fds") if target.startswith("socket:")]

    assert {
        "outcome": (outcome.exit_code, outcome.quiesced_by_exit, outcome.holder_death, outcome.stderr),
        "result_files": outcome.result_files,
        "read_back": (holder.readback["cgroup"], holder.readback["unit"]["OOMPolicy"]),
        "scope_root_empty": (holder.scope / "cgroup.procs").read_text(),
        "spawner_sockets": len(sockets),
        **facts,
    } == {
        "outcome": (0, True, None, b""),
        "result_files": {"probe.py": PROFILE_PROBE.encode(), "value.json": b"[42]"},
        "read_back": ({"memory.max": str(992 << 20), "memory.swap.max": "0", "pids.max": "64",
                       "cpu.max": "100000 100000"}, "continue"),
        "scope_root_empty": "",
        "spawner_sockets": 2,
        "env": PATH,  # exactly the request environment, nothing inherited
        "cwd": "/workspace",
        "own_session": True,
        "spawner_session": True,
        "processes": True,
        "keyctl": "EPERM",
        "proc_keys": ["EACCES", "EACCES"],
        "creates": {"/dev/x": "EROFS", "/run/x": "EROFS", "/run/runref/x": "EROFS",
                    "/workspace/.git/x": "EROFS"},
        "no_sysfs": [],  # at most the image's empty /sys directory, never sysfs
        "git_head": "ref: refs/heads/main\n",
        "interfaces": ["lo"],
        "inputs": ["probe.py", "stderr", "stdout"],
    }, outcome.stderr


def test_timeout_kills_the_leaf_tree_and_the_holder_serves_the_next_leaf(launch):
    holder = launch()
    slow = holder.run_leaf(leaf("slow", "sleep 300 & sleep 300", timeout=1))
    flood = holder.run_leaf(leaf("flood", "head -c 100000 /dev/zero; echo e >&2", limit=1000))

    assert {
        "slow": (slow.exit_code, slow.timed_out, slow.quiesced_by_exit, slow.holder_death, slow.duration_ms < 3000),
        "flood": (flood.exit_code, len(flood.stdout), flood.stdout_truncated, flood.stderr, flood.stderr_truncated),
    } == {
        "slow": (None, True, False, None, True),
        "flood": (0, 1000, True, b"e\n", False),
    }


SET_ON_SPAWNER = {
    "limits": (PYTHON, "-c", "import os, resource; resource.prlimit(os.getppid(), resource.RLIMIT_NOFILE, (64, 64))"),
    "oom_score_adj": ("/bin/sh", "-c", "echo 700 > /proc/$PPID/oom_score_adj"),
    "nice": (PYTHON, "-c", "import os; os.setpriority(os.PRIO_PROCESS, os.getppid(), 5)"),
    "cpus_allowed": (PYTHON, "-c", "import os; p = os.getppid(); os.sched_setaffinity(p, {min(os.sched_getaffinity(p))})"),
    "sched_getattr": (PYTHON, "-c", "import os; os.sched_setscheduler(os.getppid(), os.SCHED_IDLE, os.sched_param(0))"),
    "ioprio": (PYTHON, "-c", "import ctypes, os; assert ctypes.CDLL(None).syscall(251, 1, os.getppid(), 3 << 13) == 0"),
    "coredump_filter": ("/bin/sh", "-c", "echo 0 > /proc/$PPID/coredump_filter"),
}


@pytest.mark.parametrize("attribute", sorted(SET_ON_SPAWNER))
def test_a_leaf_changing_a_spawner_attribute_is_a_holder_death_naming_it(launch, attribute):
    if attribute == "cpus_allowed" and len(os.sched_getaffinity(0)) < 2:
        pytest.skip("affinity narrowing needs two CPUs")
    holder = launch()
    innocent = holder.run_leaf(leaf("innocent", "echo before"))
    culprit = holder.run_leaf(leaf("culprit", argv=SET_ON_SPAWNER[attribute]))
    later = holder.run_leaf(leaf("later", "echo after"))
    death = HolderDeath(LOST, f"spawner attribute changed since ready: {attribute}")

    assert {
        "innocent": (innocent.exit_code, innocent.holder_death),
        "culprit": (culprit.exit_code, culprit.quiesced_by_exit, culprit.holder_death),
        "later": later.holder_death,
        "scope_populated": populated(holder.scope),
    } == {"innocent": (0, None), "culprit": (None, False, death), "later": death, "scope_populated": False}


def test_a_fifo_stdout_is_refused_promptly_without_hanging_the_broker(launch):
    holder = launch()

    class HostReadBlocked(BaseException):
        """Not an OSError, so a blocked host open cannot pass as a guest refusal."""

    def _hung(signum, frame):
        raise HostReadBlocked("host result read blocked")

    previous = signal.signal(signal.SIGALRM, _hung)
    signal.alarm(10)
    started = time.monotonic()
    try:
        outcome = holder.run_leaf(leaf("fifo", "rm /result/fifo/stdout && mkfifo /result/fifo/stdout"))
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)

    assert (outcome.holder_death, time.monotonic() - started < 2, populated(holder.scope)) == (
        HolderDeath(ESCAPE, "result read refused: /result/fifo/stdout is not a regular file"), True, False)


def test_a_pre_created_later_result_entry_never_reaches_its_leaf(launch):
    holder = launch()
    forger = holder.run_leaf(leaf("forger", "mkdir -p /result/later/sub && echo forged > /result/later/forged; "
                                            "chmod 0 /result/later; touch /tmp/left /dev/shm/left"))
    later = holder.run_leaf(leaf("later", "ls -A /result /result/later /tmp /dev/shm"))

    assert ((forger.exit_code, forger.holder_death), (later.exit_code, later.stdout, later.result_files)) == (
        (0, None), (0, b"/dev/shm:\n\n/result:\nlater\n\n/result/later:\nstderr\nstdout\n\n/tmp:\n", {}))


def test_stopped_and_signalled_spawners_and_a_setsid_daemon(launch):
    stopped, signalled, daemon = launch(), launch(), launch()
    outcomes = {
        "stopped": stopped.run_leaf(leaf("stop", "kill -STOP $PPID", timeout=5)),
        "signalled": signalled.run_leaf(leaf("signal", "kill -KILL $PPID", timeout=5)),
        "daemon": daemon.run_leaf(leaf("daemon", "setsid sleep 300 >/dev/null 2>&1 &\necho started", timeout=5)),
    }
    after_daemon = daemon.run_leaf(leaf("after", "ps -eo args 2>/dev/null || ls /proc | grep -c '^[0-9]'"))
    survivors = [pid for cgroup in daemon.scope.rglob("cgroup.procs") for pid in cgroup.read_text().split()
                 if Path(f"/proc/{pid}/cmdline").read_bytes() == b"sleep\x00300\x00"]

    assert {
        "stopped": outcomes["stopped"].holder_death,
        # pid 1 follows its killed child out, so the scope may vanish before the EOF is read
        "signalled": (outcomes["signalled"].holder_death.code,
                      outcomes["signalled"].holder_death.detail in ("control socket EOF", "bwrap exited")),
        "daemon": (outcomes["daemon"].exit_code, outcomes["daemon"].quiesced_by_exit, outcomes["daemon"].stdout,
                   outcomes["daemon"].holder_death),
        "dead_scopes_populated": [populated(h.scope) for h in (stopped, signalled)],
        "after_daemon": (after_daemon.exit_code, after_daemon.holder_death),
        "daemon_survivors": survivors,
    } == {
        "stopped": HolderDeath(LOST, "no status line within the deadline"),
        "signalled": (LOST, True),
        "daemon": (None, False, b"started\n", None),
        "dead_scopes_populated": [False, False],
        "after_daemon": (0, None),
        "daemon_survivors": [],
    }


def test_scope_limits_and_workspace_quota_are_enforced_and_oom_keeps_the_holder(launch):
    holder = launch()
    memory = holder.run_leaf(leaf("memory", argv=(PYTHON, "-c", "b = [bytearray(64 << 20) for _ in range(32)]"),
                                  timeout=30))
    quota = holder.run_leaf(leaf("quota", "head -c 64000000 /dev/zero > /workspace/big; echo $?; "
                                          "stat -c %s /workspace/big"))
    pids = holder.run_leaf(leaf("pids", argv=(PYTHON, "-c", "\n".join([
        "import os, time", "kids = []", "try:", "    for _ in range(200):", "        pid = os.fork()",
        "        if pid == 0:", "            time.sleep(30); os._exit(0)", "        kids.append(pid)",
        "except OSError:", "    print(len(kids))", "for kid in kids:", "    os.kill(kid, 9)"]))))
    events = dict(line.split() for line in (holder.scope / "memory.events").read_text().splitlines())
    written = int(quota.stdout.split()[1])

    assert {
        "memory": (memory.exit_code, memory.holder_death, int(events["oom_kill"]) >= 1),
        "quota": (quota.stdout.split()[0], written <= WORKSPACE_MIB << 20, b"No space left" in quota.stderr),
        "pids": (pids.exit_code, int(pids.stdout) < 64),
    } == {"memory": (137, None, True), "quota": (b"1", True, True), "pids": (0, True)}


HELPER_PROBE = r"""
import ctypes, json, os, sys
libc = ctypes.CDLL(None)
signal_number = ctypes.c_int()
libc.prctl(2, ctypes.byref(signal_number), 0, 0, 0)  # PR_GET_PDEATHSIG
workspace = int(sys.argv[1])
print(json.dumps({"cgroup": open("/proc/self/cgroup").read().strip().split("::")[1],
                  "pdeathsig": signal_number.value, "workspace": sorted(os.listdir(workspace)),
                  "fds": sorted(int(n) for n in os.listdir("/proc/self/fd"))}))
"""


def test_host_helper_runs_in_the_host_slot_under_a_parent_death_signal(launch):
    holder = launch()
    made = holder.run_leaf(leaf("make", "echo data > /workspace/made-by-leaf"))
    workspace = holder.root_fd("workspace")
    done = holder.run_host_helper([sys.executable, "-I", "-c", HELPER_PROBE, str(workspace)],
                                  pass_fds=(workspace,), timeout_sec=30)
    facts = json.loads(done.stdout)

    assert {
        "leaf": made.exit_code,
        "helper": (done.returncode, facts["pdeathsig"], facts["workspace"]),
        "in_host_slot": facts["cgroup"] == "/" + str(holder.slots["host"].path.relative_to(CGROUP_MOUNT)),
        "other_descriptors": len(set(facts["fds"]) - {0, 1, 2, workspace}) <= 1,  # os.listdir's own
        "host_slot_empty_after": holder.slots["host"].populated,
    } == {
        "leaf": 0,
        "helper": (0, signal.SIGKILL, ["made-by-leaf"]),
        "in_host_slot": True,
        "other_descriptors": True,
        "host_slot_empty_after": False,
    }, done.stderr
