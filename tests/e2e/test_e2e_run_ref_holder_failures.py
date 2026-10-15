"""Holder deaths, refusals and launch failures through the run-ref holder runtime (Task 6a fix round 1).

Real launches over the image from `tests/e2e/run_ref_image_fixture.py`: a
spawner stopped by a leaf's delayed daemon is the culprit's own holder death;
guest-caused result entries (an unreadable directory, a non-UTF-8 name) are
`run_ref_environment_escape_rejected`, never a host exception; an unwipeable
scratch tree fails the culprit; a foreign holder-slot member refuses the next
request; launch and host-helper failures are coded `RunRefRuntimeError`s and
leave no scope behind. Skips without ORCHESTRATE_E2E, the CLIs or a user manager.
"""

from __future__ import annotations

import socket
import subprocess
import sys

import pytest

from orchestrator.workflow.run_ref.holder import Holder
from orchestrator.workflow.run_ref.holder_scope import populated
from orchestrator.workflow.run_ref.leaf import HolderDeath
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError
from tests.e2e.run_ref_image_fixture import (  # noqa: F401 (fixtures)
    ESCAPE, LIMITS, LOST, PYTHON, launch, leaf, sealed_image,
)

pytestmark = pytest.mark.e2e
UNAVAILABLE = "run_ref_environment_unavailable"


def test_a_daemon_stopping_the_spawner_after_its_leaf_exits_fails_that_leaf(launch):
    holder = launch()
    culprit = holder.run_leaf(leaf("culprit", 'setsid sh -c "sleep 0.1; kill -STOP $PPID" & exit 0'))
    later = holder.run_leaf(leaf("later", "echo after"))
    death = HolderDeath(LOST, "spawner stopped")

    assert ((culprit.exit_code, culprit.holder_death), later.holder_death, populated(holder.scope)) == (
        (None, death), death, False)


@pytest.mark.parametrize("signal_name", ["TSTP", "TTIN", "TTOU"])
def test_terminal_stop_signals_from_a_daemon_never_stop_the_spawner(launch, signal_name):
    """The spawner's process group is orphaned, so the kernel discards these (only SIGSTOP stops it)."""
    holder = launch()
    culprit = holder.run_leaf(leaf("culprit", f'setsid sh -c "sleep 0.1; kill -{signal_name} $PPID" & exit 0'))
    later = holder.run_leaf(leaf("later", "echo after"))

    assert ((culprit.exit_code, culprit.holder_death), (later.exit_code, later.holder_death)) == (
        (0, None), (0, None))


GUEST_ENTRIES = {
    "unreadable_directory": "mkdir /result/p/sub && touch /result/p/sub/f && chmod 0400 /result/p/sub",
    "non_utf8_name": f"{PYTHON} -c \"open(b'/result/p/\\\\xff', 'w').close()\"",
}


@pytest.mark.parametrize("entry", sorted(GUEST_ENTRIES))
def test_guest_caused_result_entries_are_escape_rejected_not_host_errors(launch, entry):
    holder = launch()
    outcome = holder.run_leaf(leaf("p", GUEST_ENTRIES[entry]))

    assert (outcome.holder_death.code, outcome.holder_death.detail == "result_read_refused",
            populated(holder.scope)) == (ESCAPE, True, False), outcome


def test_a_scratch_tree_deeper_than_the_wipe_bound_fails_the_culprit(launch):
    holder = launch()
    culprit = holder.run_leaf(leaf("deep", argv=(PYTHON, "-c", "import os\nos.chdir('/tmp')\n"
                                                 "for _ in range(3000):\n    os.mkdir('d'); os.chdir('d')")))

    assert culprit.holder_death == HolderDeath(ESCAPE, "/tmp could not be emptied after leaf deep")


def test_a_foreign_holder_slot_member_refuses_the_next_request(launch):
    holder = launch()
    intruder = subprocess.Popen(["sleep", "60"])
    try:
        holder.slots["holder"].add_pid(intruder.pid)
        outcome = holder.run_leaf(leaf("next", "echo hi"))
        intruder.wait(timeout=10)  # killed with the scope
    finally:
        if intruder.poll() is None:
            intruder.kill()
            intruder.wait()

    assert (outcome.holder_death, populated(holder.scope)) == (HolderDeath(ESCAPE, "foreign holder-slot member"),
                                                               False)


def test_a_launch_refused_before_release_is_unavailable_and_leaves_no_scope(sealed_image, tmp_path):
    shared = tmp_path / "shared"
    shared.mkdir(mode=0o755)  # the release record needs a private parent
    holder = Holder(sealed_image, LIMITS, control_dir=shared)

    with pytest.raises(RunRefRuntimeError) as refused:
        holder.launch()
    assert (refused.value.code, holder.scope is not None and populated(holder.scope)) == (UNAVAILABLE, False)


def test_a_holder_exiting_after_release_before_ready_is_lost_and_leaves_no_scope(sealed_image, tmp_path):
    control = tmp_path / "control"
    control.mkdir(mode=0o700)
    left, right = socket.socketpair()  # bwrap cannot bind a socket at /workspace/.git, after release
    try:
        holder = Holder(sealed_image, LIMITS, control_dir=control, git_dir_fd=left.fileno())
        with pytest.raises(RunRefRuntimeError) as refused:
            holder.launch()
    finally:
        left.close()
        right.close()

    left_behind = holder.scope is not None and populated(holder.scope)

    assert holder.sandbox._released and holder.sandbox.gate.release_consumed
    assert (refused.value.code, "ready" in refused.value.detail, left_behind) == (LOST, True, False)


def test_host_helper_failures_are_coded_holder_deaths(launch):
    holder = launch()
    with pytest.raises(RunRefRuntimeError) as slow:
        holder.run_host_helper([sys.executable, "-c", "import time; time.sleep(30)"], timeout_sec=0.5)
    with pytest.raises(RunRefRuntimeError) as after:
        holder.run_host_helper([sys.executable, "-c", "pass"], timeout_sec=5)
    outcome = holder.run_leaf(leaf("after", "true"))

    assert ((slow.value.code, after.value.code), outcome.holder_death.code, populated(holder.scope)) == (
        (LOST, LOST), LOST, False)
