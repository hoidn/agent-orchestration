"""The pure parts of the long-horizon oracle check (`experiments/long_horizon_tasks/oracle_check.sh`).

Each test sources the script (its run only starts when executed) and calls one function on constructed input.
"""

import hashlib
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks" / "oracle_check.sh"
TOML = '[task]\nname = "t"\n\n[agent]\ntimeout_sec = 28800.0\n\n[verifier]\ntimeout_sec = 900\n'


def _call(*args):
    return subprocess.run(["bash", "-c", 'source "$1" && shift && "$@"', "lh-test", str(SCRIPT), *map(str, args)],
                          capture_output=True, text=True)


def _package(root, toml=TOML):
    (root / "tests").mkdir(parents=True)
    (root / "task.toml").write_text(toml)
    (root / "tests" / "test.sh").write_text("#!/bin/bash\n")
    return root


def test_the_overlay_adds_the_two_agent_keys_after_the_agent_table(tmp_path):
    done = _call("overlay_task", _package(tmp_path / "pkg"), tmp_path / "copy", "relay", "pypi.org")
    keys = 'network_mode = "allowlist"\nallowed_hosts = ["relay", "pypi.org"]\n'
    assert (done.returncode, (tmp_path / "copy" / "task.toml").read_text()) == (
        0, TOML.replace("[agent]\n", "[agent]\n" + keys))


def test_the_overlay_digest_is_the_sha256_of_the_two_lines(tmp_path):
    done = _call("overlay_task", _package(tmp_path / "pkg"), tmp_path / "copy", "relay")
    keys = b'network_mode = "allowlist"\nallowed_hosts = ["relay"]\n'
    assert done.stdout.strip() == hashlib.sha256(keys).hexdigest()


def test_the_overlay_copies_every_other_file_unchanged(tmp_path):
    _call("overlay_task", _package(tmp_path / "pkg"), tmp_path / "copy", "relay")
    assert (tmp_path / "copy" / "tests" / "test.sh").read_text() == "#!/bin/bash\n"


@pytest.mark.parametrize("toml", [TOML.replace("[agent]\n", "[agent]\nnetwork_mode = \"public\"\n"),
                                  TOML.replace("[agent]\n", ""), TOML + "[agent]\n"])
def test_the_overlay_refuses_a_task_that_sets_a_network_key_or_has_not_one_agent_table(tmp_path, toml):
    done = _call("overlay_task", _package(tmp_path / "pkg", toml), tmp_path / "copy", "relay")
    assert (done.returncode, done.stdout) == (2, "")


@pytest.mark.parametrize(("loadavg", "gate", "open_"), [
    ("24.00 23.10 40.00 3/900 1", "24", True), ("24.01 10.00 1.00 3/900 1", "24", False),
    ("10.00 24.50 1.00 3/900 1", "24", False), ("80.00 80.00 80.00 3/900 1", "none", True)])
def test_the_load_gate_is_open_only_when_the_one_and_five_minute_load_are_at_or_below_it(tmp_path, loadavg, gate,
                                                                                         open_):
    (tmp_path / "loadavg").write_text(loadavg + "\n")
    assert (_call("gate_open", gate, tmp_path / "loadavg").returncode == 0) is open_


@pytest.mark.parametrize(("free", "ok"), [((25 * 10**9, 70 * 10**9), True), ((70 * 10**9, 25 * 10**9 - 1), False)])
def test_the_disk_stops_under_25_gb_on_either_mount(free, ok):
    assert (_call("room_ok", *free).returncode == 0) is ok


def test_the_uidfix_changes_exactly_the_one_bound_line(tmp_path):
    worker = tmp_path / "app_worker.py"
    worker.write_text("import secrets\n        uid = 10000 + secrets.randbelow(1000000000)\nx = 1\n")
    done = _call("uidfix", worker)
    assert (done.returncode, worker.read_text()) == (
        0, "import secrets\n        uid = 10000 + secrets.randbelow(55000)\nx = 1\n")


@pytest.mark.parametrize("text", ["uid = 1\n", "secrets.randbelow(1000000000)\nsecrets.randbelow(1000000000)\n"])
def test_the_uidfix_refuses_a_file_without_exactly_one_bound_line(tmp_path, text):
    worker = tmp_path / "app_worker.py"
    worker.write_text(text)
    assert (_call("uidfix", worker).returncode, worker.read_text()) == (2, text)


# ---- the schedule of one task, with the harness and the host replaced by stand-ins ---------------

STAND_INS = '''
prepare() { :; }
free_bytes() { echo "$FREE $FREE"; }
wait_gate() { [ "$OPEN" = 1 ]; }
trial() { echo "start $2 $3" >> "$JOBS/log"; sleep 1; echo "end $2 $3" >> "$JOBS/log"; }
'''


def _schedule(tmp_path, repeats, concurrency, free=30 * 10**9, gate_open=1):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "JOBS": str(tmp_path), "REPEATS": str(repeats), "CONCURRENCY": str(concurrency),
           "LAUNCH_GAP_S": "0", "FREE": str(free), "OPEN": str(gate_open)}
    done = subprocess.run(["bash", "-c", 'source "$1" && eval "$2" && check_task t1', "lh-test", str(SCRIPT), STAND_INS],
                          capture_output=True, text=True, env=env)
    log = (tmp_path / "log").read_text().split("\n") if (tmp_path / "log").exists() else []
    running = peak = 0
    for line in filter(None, log):
        running += 1 if line.startswith("start") else -1
        peak = max(peak, running)
    return done.returncode, sorted(line for line in log if line.startswith("start")), peak


def test_every_round_runs_the_reference_and_the_untouched_trial_at_most_concurrency_at_once(tmp_path):
    rc, starts, peak = _schedule(tmp_path, repeats=3, concurrency=2)
    assert (rc, len(starts), peak) == (0, 6, 2)


def test_a_gate_that_stays_closed_ends_the_task_with_exit_4_before_any_trial(tmp_path):
    assert _schedule(tmp_path, repeats=2, concurrency=2, gate_open=0)[:2] == (4, [])


def test_low_free_space_ends_the_task_with_exit_3_before_any_trial(tmp_path):
    assert _schedule(tmp_path, repeats=2, concurrency=2, free=24 * 10**9)[:2] == (3, [])
