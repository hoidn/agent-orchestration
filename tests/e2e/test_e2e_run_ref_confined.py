"""F3 substrate facts for the run-ref confinement profile on a real host.

Each case runs a small script inside `systemd-run --user --scope -p
Delegate=yes`, moves the controller into a leaf cgroup, enables
memory/pids/cpu for sibling slots and launches rootless bwrap in a slot.
The full profile (imported image, holder/spawner, escape negatives) is
recorded in docs/reports/run-ref-confinement-feasibility/README.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap

import pytest

from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e

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
    skip_if_no_e2e()
    skip_if_no_cli("bwrap")
    skip_if_no_cli("systemd-run")
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
    facts = _in_delegated_scope('''
        done = sandbox("cat /proc/net/dev | tail -n +3 | cut -d: -f1 | tr -d ' '; "
                       "(exec 3<>/dev/tcp/1.1.1.1/53) 2>/dev/null && echo CONNECTED || echo REFUSED")
        print(json.dumps({"out": done.stdout.split()}))
    ''')

    assert facts == {"out": ["lo", "REFUSED"]}


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
