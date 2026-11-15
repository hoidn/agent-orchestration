"""The pure parts of the long-horizon oracle check (`experiments/long_horizon_tasks/oracle_check.sh`).

Each test sources the script (its run only starts when executed) and calls one function on constructed input.
"""

import hashlib
import json
import subprocess
import time
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


def _schedule(tmp_path, repeats, concurrency, free=30 * 10**9, gate_open=1, stand_ins=STAND_INS):
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "JOBS": str(tmp_path), "REPEATS": str(repeats), "CONCURRENCY": str(concurrency),
           "LAUNCH_GAP_S": "0", "FREE": str(free), "OPEN": str(gate_open)}
    done = subprocess.run(["bash", "-c", 'source "$1" && eval "$2" && check_task t1', "lh-test", str(SCRIPT), stand_ins],
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


def test_a_stop_request_ends_the_task_with_exit_5_before_any_trial(tmp_path):
    (tmp_path / ".stop").touch()
    assert _schedule(tmp_path, repeats=2, concurrency=2)[:2] == (5, [])


def test_a_stop_request_during_a_run_ends_the_task_with_exit_5_and_launches_no_more_trials(tmp_path):
    stop_in_first = STAND_INS.replace('trial() { echo "start $2 $3" >> "$JOBS/log";',
                                      'trial() { echo "start $2 $3" >> "$JOBS/log"; touch "$JOBS/.stop";')
    assert _schedule(tmp_path, repeats=3, concurrency=1, stand_ins=stop_in_first)[:2] == (5, ["start oracle 1"])


# ---- stops, the gate's clock, the store: a stand-in podman keeps its containers, networks and images as files ---

PODMAN = r'''#!/bin/bash
S=$PODSTATE
echo "$*" >> "$S/calls"
prefix() { local a; for a; do case $a in name=^*) echo "${a#name=^}" ;; esac; done; }
case "$1" in
  ps) ls "$S/containers" | grep "^$(prefix "$@")" ;;
  rm) rm "$S/containers/${@: -1}" ;;
  network) case "$2" in ls) ls "$S/networks" | grep "^$(prefix "$@")" ;; rm) rm "$S/networks/$3" ;; esac ;;
  rmi) ! grep -qsxF "$2" "$S/inuse" && echo "$2" >> "$S/removed" ;;
  image) case "$2" in
    exists) awk -v r="$3" '$1 == r || $2 == r { f = 1 } END { exit !f }' "$S/images" ;;
    inspect) awk -v r="${@: -1}" '$1 == r { print $2; f = 1 } END { exit !f }' "$S/images" ;;
    esac ;;
  tag) echo "$3 $2" >> "$S/images" ;;
  pull) echo "$2" >> "$S/pulls" ;;
  *) exit 1 ;;
esac
'''
# A harness that builds its trial, a container and a network (named as Harbor names them, <trial>__env_…),
# starts a child and then hangs, deaf to SIGTERM.
HARNESS = r'''#!/bin/bash
S=$1
while [ "$1" != -o ]; do shift; done
mkdir -p "$2/job/t1__abc1234"
touch "$S/containers/t1__abc1234__env_main_1" "$S/networks/t1__abc1234__env_default"
trap '' TERM
sleep 300 &
echo $! > "$2/child.pid"
sleep 300
'''


def _host(tmp_path):
    """A stand-in podman first on PATH, its state directory, and the environment of a sourced script."""
    state, bin_ = tmp_path / "pod", tmp_path / "bin"
    for d in (state / "containers", state / "networks", bin_):
        d.mkdir(parents=True)
    (state / "images").touch()
    for name, text in (("podman", PODMAN), ("harness", HARNESS)):
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    jobs = tmp_path / "jobs"
    jobs.mkdir()
    return state, {"PATH": f"{bin_}:/usr/bin:/bin", "HOME": str(tmp_path), "PODSTATE": str(state), "JOBS": str(jobs),
                   "LH": str(tmp_path), "CPUS": "0", "LAUNCH_GAP_S": "0"}


def _sourced(env, code, *args):
    return subprocess.run(["bash", "-c", 'source "$1" && eval "$2"', "lh-test", str(SCRIPT), code, *args],
                          capture_output=True, text=True, env=env)


def _gone(pid):
    stat = Path(f"/proc/{pid}/stat")
    return not stat.exists() or stat.read_text().rsplit(")", 1)[1].split()[0] in ("Z", "X")


def test_a_disk_stop_ends_a_hung_harness_its_child_and_its_containers_within_seconds(tmp_path):
    state, env = _host(tmp_path)
    env |= {"HARNESS": f"{tmp_path / 'bin' / 'harness'} {state}", "STOP_GRACE_S": "1", "WALL_BOUND_S": "3600"}
    low_once_running = f'free_bytes() {{ [ -e {state}/containers/t1__abc1234__env_main_1 ] && echo "1 1" || echo "{10**12} {10**12}"; }}'
    start = time.monotonic()
    _sourced(env, low_once_running + '; OVERLAY=x IMAGES=; trial t1 oracle 1 --agent oracle')
    out = Path(env["JOBS"]) / "oracle" / "t1" / "1"
    assert (time.monotonic() - start < 30, _gone((out / "child.pid").read_text().strip()),
            sorted(p.name for p in state.glob("*/t1__*")),
            [line for line in (out / "meta.txt").read_text().splitlines() if line.startswith(("stop=", "removed="))]) == (
        True, True, [], ["stop=disk free 1 1", "removed=container t1__abc1234__env_main_1",
                         "removed=network t1__abc1234__env_default"])


@pytest.mark.parametrize(("free", "elapsed", "flag", "why"), [
    ("1 1", 0, False, "disk free 1 1"), (f"{10**12} {10**12}", 60, False, "wall bound 60s"),
    (f"{10**12} {10**12}", 0, True, "signal"), (f"{10**12} {10**12}", 59, False, "")])
def test_a_trial_stops_on_low_disk_at_its_wall_bound_or_on_a_stop_request(tmp_path, free, elapsed, flag, why):
    _, env = _host(tmp_path)
    if flag:
        (Path(env["JOBS"]) / ".stop").touch()
    done = _sourced(env | {"WALL_BOUND_S": "60"}, 'stop_reason "$3" "$4"', free, str(elapsed))
    assert done.stdout.strip() == why


def test_the_wall_bound_is_the_tasks_agent_verifier_and_build_limits_plus_the_margin(tmp_path):
    pkg = _package(tmp_path / "pkg", TOML + "\n[verifier.environment]\nbuild_timeout_sec = 1200\n"
                   "[environment]\nbuild_timeout_sec = 300\n")
    done = _call("wall_bound", pkg)
    assert done.stdout.strip() == str(28800 + 900 + 1200 + 300 + 1800)


def test_the_gates_two_hour_clock_runs_only_while_no_trial_is_in_flight(tmp_path):
    _, env = _host(tmp_path)
    start = time.monotonic()
    _sourced(env | {"GATE": "-1", "GATE_WAIT_S": "2", "GATE_POLL_S": "1"}, "sleep 6 & wait_gate")
    assert time.monotonic() - start >= 5  # a clock running from the start would end near 2 s


def test_a_run_refuses_a_jobs_directory_that_holds_earlier_runs(tmp_path):
    state, env = _host(tmp_path)
    (Path(env["JOBS"]) / "oracle").mkdir()
    done = subprocess.run(["bash", str(SCRIPT), "t1"], capture_output=True, text=True, env=env)
    assert (done.returncode, (state / "calls").exists(), sorted(p.name for p in Path(env["JOBS"]).iterdir())) == (
        2, False, ["oracle"])


def test_release_keeps_listed_an_image_it_could_not_delete(tmp_path):
    state, env = _host(tmp_path)
    (Path(env["JOBS"]) / "pulled.txt").write_text("a/one@sha256:1\na/two@sha256:2\n")
    (state / "inuse").write_text("a/one@sha256:1\n")
    _sourced(env, "release")
    assert ((Path(env["JOBS"]) / "pulled.txt").read_text(), (state / "removed").read_text()) == (
        "a/one@sha256:1\n", "a/two@sha256:2\n")


def test_a_pull_that_would_leave_under_25_gb_is_refused_before_it_starts(tmp_path):
    state, env = _host(tmp_path)
    done = _sourced(env, f'free_bytes() {{ echo "{30 * 10**9} {90 * 10**9}"; }}; ensure_image a/one@sha256:1 {6 * 10**9}')
    assert (done.returncode, (state / "pulls").exists()) == (3, False)


def _variant_tasks(tmp_path):
    tasks = tmp_path / "tasks.json"
    tasks.write_text(json.dumps({"tasks": [{"name": "terminal-bench/vba-userform-port", "variant": {
        "image": "lh-oracle/v:verifier", "keeper": "lh-keep/v:verifier", "image_id": "abc123"}}]}))
    return tasks


def test_the_variants_name_comes_back_from_its_keeper_name_after_a_teardown_removed_it(tmp_path):
    state, env = _host(tmp_path)
    (state / "images").write_text("lh-keep/v:verifier abc123\n")
    done = _sourced(env | {"TASKS": str(_variant_tasks(tmp_path))}, "variant_image")
    assert (done.stdout.strip(), "lh-oracle/v:verifier abc123" in (state / "images").read_text()) == (
        "lh-oracle/v:verifier abc123", True)


def test_a_variant_image_with_another_id_is_refused(tmp_path):
    state, env = _host(tmp_path)
    (state / "images").write_text("lh-oracle/v:verifier fff999\nlh-keep/v:verifier fff999\n")
    done = _sourced(env | {"TASKS": str(_variant_tasks(tmp_path))}, "variant_image")
    assert (done.returncode, done.stdout) == (2, "")
