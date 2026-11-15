"""The launch guard (`experiments/seed_set/reaper.py`, `study.launch`, `host.guarded`): the unit's command runs as
the guard's child from its first instant, nothing of its tree outlives the command, its timeout or its root shell,
a kill never reaches a pid that was reused (re-review of fix round 1, minors n1 and n2), and the host-side checks
run under it with a bound, a check past its bound recorded as timed out (major N2). Real processes, no provider."""

import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import pytest

from experiments.seed_set import host, reaper, study, units
from tests.experiments.seed_set_offline_support import hanging_harness


def running(pid):
    """Whether `pid` is a live process (a zombie is not)."""
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except (OSError, IndexError):
        return False


def gone(*pids, within=10):
    deadline = time.time() + within
    while time.time() < deadline and any(map(running, pids)):
        time.sleep(0.1)
    return not any(map(running, pids))


def wait_for(path, within=20):
    deadline = time.time() + within
    while time.time() < deadline and not (path.is_file() and path.read_text().strip()):
        time.sleep(0.05)
    return int(path.read_text())


def launch(tmp_path, script, timeout=60):
    command = tmp_path / "command.sh"
    command.write_text(script)
    return study.launch(command, {**os.environ}, tmp_path / "run.log", timeout)


def test_a_signal_never_reaches_a_pid_whose_start_time_changed():  # n1
    sleeper = subprocess.Popen(["sleep", "60"])
    try:
        _, started = reaper.stat(sleeper.pid)
        reaper.signal_exact(sleeper.pid, started + 1, signal.SIGKILL)
        survived = running(sleeper.pid)
        reaper.signal_exact(sleeper.pid, started, signal.SIGKILL)
        assert (survived, sleeper.wait(timeout=10)) == (True, -signal.SIGKILL)
    finally:
        sleeper.kill()


def test_the_tree_of_a_root_that_is_not_the_recorded_process_is_never_killed():  # n1: a reused root pid
    root = subprocess.Popen(["bash", "-c", "sleep 60 & wait"], start_new_session=True)
    try:
        time.sleep(0.5)
        _, started = reaper.stat(root.pid)
        reaper.kill_tree(root.pid, started=started + 1)
        assert (running(root.pid), sorted(reaper.tree(root.pid)) != [root.pid]) == (True, True)
    finally:
        reaper.kill_tree(root.pid)
        root.wait()


def test_the_command_runs_as_the_guards_child_and_its_session_is_recorded(tmp_path):  # n2: never unguarded
    status = launch(tmp_path, f'cd {tmp_path}\ntr "\\0" " " < /proc/$PPID/cmdline > parent.txt\nexit 3\n')
    pid, started = map(int, (tmp_path / "run.pgid").read_text().split())
    assert (status, reaper.__file__ in (tmp_path / "parent.txt").read_text().split(), started > 0) == (3, True, True)


def test_an_orphan_left_by_a_command_that_ended_is_killed(tmp_path):  # n2: the root's end does not disarm it
    status = launch(tmp_path, f"cd {tmp_path}\nsleep 300 &\necho $! > orphan.pid\nexit 0\n")
    assert (status, gone(int((tmp_path / "orphan.pid").read_text()))) == (0, True)


def test_a_root_shell_killed_while_its_subtree_lives_does_not_disarm_the_guard(tmp_path):  # n2
    script = f"cd {tmp_path}\n(sleep 300; true) &\necho $! > child.pid\necho $$ > root.pid\nwait\n"
    killer = threading.Thread(target=lambda: os.kill(wait_for(tmp_path / "root.pid"), signal.SIGKILL))
    killer.start()
    status = launch(tmp_path, script)
    killer.join()
    assert (status, gone(wait_for(tmp_path / "child.pid"))) == (128 + signal.SIGKILL, True)


def test_a_timeout_kills_the_whole_tree(tmp_path):
    status = launch(tmp_path, f"cd {tmp_path}\nsetsid sleep 300 &\necho $! > other-session.pid\nsleep 300\n",
                    timeout=3)
    assert (status, gone(wait_for(tmp_path / "other-session.pid"))) == ("timeout", True)


def test_a_killed_guard_leaves_the_launcher_to_kill_the_unit(tmp_path):
    script = f"cd {tmp_path}\nsleep 300 &\necho $! > child.pid\necho $PPID > guard.pid\nsleep 300\n"
    def kill_the_guard():  # only a guard: before the guard was the command's parent, the parent was this test
        guard = wait_for(tmp_path / "guard.pid")
        if reaper.__file__ in Path(f"/proc/{guard}/cmdline").read_text().split("\0"):
            os.kill(guard, signal.SIGKILL)
    killer = threading.Thread(target=kill_the_guard)
    killer.start()
    status = launch(tmp_path, script)
    killer.join()
    root = int((tmp_path / "run.pgid").read_text().split()[0])
    assert (status, gone(wait_for(tmp_path / "child.pid"), root)) == ("guard killed by signal 9", True)


def test_a_guard_killed_before_it_recorded_the_session_gives_a_status_saying_so(tmp_path):  # final scoped check
    """The guard dies between opening the session file and writing it: an empty file, no TypeError."""
    pgid = tmp_path / "run.pgid"
    pgid.write_text("")
    status = reaper.run(["true"], pgid, 30, preexec_fn=lambda: os.kill(os.getpid(), signal.SIGKILL))
    assert status == "guard killed by signal 9 before it recorded the command's session"


def test_an_empty_session_file_reads_as_no_session(tmp_path):  # a guard killed before it wrote the file
    (tmp_path / "run.pgid").write_text("")
    assert units.session_alive(tmp_path / "run.pgid") is False


@pytest.mark.parametrize("offset, alive", [(0, True), (1, False)])
def test_a_session_reads_alive_only_while_its_leader_is_the_recorded_process(tmp_path, offset, alive):  # n9
    """A stale session file (a reboot, a reused pid) names a live group leader that started at another time."""
    leader = subprocess.Popen(["sleep", "60"], start_new_session=True)
    try:
        (tmp_path / "run.pgid").write_text(f"{leader.pid} {reaper.stat(leader.pid)[1] + offset}\n")
        assert units.session_alive(tmp_path / "run.pgid") is alive
    finally:
        leader.kill()
        leader.wait()


REAL = Path(__file__).resolve().parents[2] / "experiments" / "seed_set" / "tasks" / "1f424cc9ae"  # a T3 package
ROOT = Path(__file__).resolve().parents[2]


def test_a_host_side_check_past_its_bound_is_killed_with_its_whole_tree(tmp_path):  # re-review N2
    code = (f"import subprocess, time\np = subprocess.Popen(['sleep', '300'], start_new_session=True)\n"
            f"open({str(tmp_path / 'grandchild.pid')!r}, 'w').write(str(p.pid))\ntime.sleep(300)\n")
    done, attempts = host.guarded([sys.executable, "-c", code], timeout=3)
    assert (done.returncode, attempts, gone(wait_for(tmp_path / "grandchild.pid"))) == ("timeout", [], True)


def test_a_visible_check_past_its_bound_is_recorded_as_timed_out_never_as_a_result(tmp_path, monkeypatch):  # N2
    monkeypatch.setattr(host, "VISIBLE_SEC", 0.5)
    (tmp_path / "empty.diff").write_text("")
    result = host.visible_check(REAL, tmp_path / "empty.diff", ROOT)
    assert (result["passed"], result["timed_out"]) == (None, "the visible check ran past 0.5 s")


def test_a_hidden_check_past_its_bound_is_recorded_as_timed_out_never_as_a_result(tmp_path, monkeypatch):  # N2
    monkeypatch.setattr(host, "CHECK_SEC", 0.5)
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 0)  # the backstop is CHECK_SEC alone
    (tmp_path / "empty.diff").write_text("")
    result = host.hidden_check(REAL, tmp_path / "empty.diff", ROOT)
    assert (result["passed"], result["timed_out"]) == (None, "the hidden tests ran past 0.5 s")


def test_a_summary_whose_harness_hangs_past_its_backstop_refuses_and_the_harness_is_killed(tmp_path, monkeypatch):
    """N2, fix round 3: the per-clone bound is the backstop for a summary harness that itself hangs."""
    pool, pids = tmp_path / "pool", tmp_path / "pids"
    (pool / "records").mkdir(parents=True)
    pids.mkdir()
    (pool / "records" / "mapping.json").write_text(json.dumps({"clones": {"a": {}, "b": {}}}))
    monkeypatch.setattr(host, "ROOT", hanging_harness(tmp_path / "checkout", pids))
    monkeypatch.setattr(host, "CHECK_SEC", 1)
    with pytest.raises(SystemExit, match="summarize of .* ran past its backstop of 2 s"):
        host.summarize(pool, tmp_path / "criterion.json")
    assert (len(os.listdir(pids)), gone(*map(int, os.listdir(pids)))) == (1, True)


def test_a_summarys_backstop_adds_each_hidden_test_bound_for_every_clone_whose_hidden_tests_run(tmp_path,
                                                                                               monkeypatch):
    """Final scoped check M2: CHECK_SEC per clone plus HIDDEN_TEST_SEC per hidden test of each clone that runs them
    (the reference clone does not): here 2 x 1 s + 3 tests x 0.5 s x 1 clone."""
    pool, pids, task = tmp_path / "pool", tmp_path / "pids", tmp_path / "task"
    (pool / "records").mkdir(parents=True)
    pids.mkdir()
    task.mkdir()
    (task / "hidden_tests.txt").write_text("t.py::a\nt.py::b\nt.py::c\n")
    (pool / "records" / "mapping.json").write_text(json.dumps({"task": str(task), "clones": {
        "a": {"arm": "direct"}, "b": {"arm": "reference"}}}))
    monkeypatch.setattr(host, "ROOT", hanging_harness(tmp_path / "checkout", pids))
    monkeypatch.setattr(host, "CHECK_SEC", 1)
    monkeypatch.setattr(host, "HIDDEN_TEST_SEC", 0.5)
    with pytest.raises(SystemExit, match="ran past its backstop of 3.5 s"):
        host.summarize(pool, tmp_path / "criterion.json")


def made_by(directory, pid, started):
    return json.dumps({"path": str(directory), "pid": pid, "started": started}) + "\n"


def test_the_sweep_removes_a_recorded_directory_whose_maker_is_gone_and_keeps_a_live_makers(tmp_path):  # round 3
    me, started = os.getpid(), reaper.stat(os.getpid())[1]
    dead, live = (Path(tempfile.mkdtemp(prefix=prefix)) for prefix in ("seed-set-host-", "seed-set-view-"))
    record = tmp_path / "host-temp.jsonl"
    record.write_text(made_by(dead, me, started + 1) + made_by(live, me, started))  # start time: not this process
    try:
        removed = host.sweep(record)
        assert (removed, dead.exists(), live.exists(), record.read_text()) == (
            [str(dead)], False, True, made_by(live, me, started))
    finally:
        shutil.rmtree(live)


FOREIGN_RECORDS = {  # what a record line names, as (the kit's temp directory, a tree that is not the kit's)
    "a name without the kit's prefix": lambda base, other: base / "not-the-kits",
    "a symlink with the prefix": lambda base, other: base / "seed-set-host-link",
    "a path through ..": lambda base, other: base / "seed-set-view-x" / ".." / ".." / "other" / "seed-set-view-mine",
    "a symlinked parent": lambda base, other: base / "linkparent" / "seed-set-host-mine",
    "a directory outside the temp directory": lambda base, other: other / "seed-set-host-mine",
    "a directory below a child of the temp directory": lambda base, other: base / "sub" / "seed-set-host-deep",
}


@pytest.mark.parametrize("case", FOREIGN_RECORDS)
def test_the_sweep_skips_and_names_a_record_line_that_is_not_a_direct_child_of_the_temp_directory(
        tmp_path, monkeypatch, capsys, case):  # final scoped check B1
    """Only a direct child of the kit's temp directory whose real path is the recorded one is touched; any other
    line is named and skipped (no chmod, no removal, no crash), and the sweep goes on with the other lines."""
    base, other = tmp_path / "tmp", tmp_path / "other"
    for directory in (base / "not-the-kits", base / "sub" / "seed-set-host-deep", other / "seed-set-view-mine",
                      other / "seed-set-host-mine", base / "seed-set-view-x"):
        directory.mkdir(parents=True)
        (directory / "MARKER").write_text("not the kit's")
    (base / "seed-set-host-link").symlink_to(other / "seed-set-host-mine", target_is_directory=True)
    (base / "linkparent").symlink_to(other, target_is_directory=True)
    (other / "seed-set-host-mine").chmod(0o500)  # a chmod that followed the link would show as 0o700
    monkeypatch.setattr(tempfile, "tempdir", str(base))
    dead = Path(tempfile.mkdtemp(prefix="seed-set-host-"))
    named = FOREIGN_RECORDS[case](base, other)
    record = tmp_path / "host-temp.jsonl"
    record.write_text(made_by(named, 1, 1) + made_by(dead, os.getpid(), reaper.stat(os.getpid())[1] + 1))
    removed = host.sweep(record)
    markers = sorted(str(p.relative_to(tmp_path)) for p in tmp_path.glob("*/**/MARKER"))
    assert (removed, markers, oct((other / "seed-set-host-mine").stat().st_mode & 0o777),
            str(named) in capsys.readouterr().err) == (
        [str(dead)], ["other/seed-set-host-mine/MARKER", "other/seed-set-view-mine/MARKER",
                      "tmp/not-the-kits/MARKER", "tmp/seed-set-view-x/MARKER", "tmp/sub/seed-set-host-deep/MARKER"],
        "0o500", True)


def test_the_sweep_skips_a_prefix_named_regular_file_without_changing_its_mode(tmp_path, monkeypatch, capsys):
    """Review 4 B1a: a line naming a regular file, not a directory, is named, skipped and kept; no chmod."""
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    plain = tmp_path / "seed-set-host-file"
    plain.write_text("not the kit's")
    plain.chmod(0o400)
    dead = Path(tempfile.mkdtemp(prefix="seed-set-host-"))
    record = tmp_path / "host-temp.jsonl"
    record.write_text(made_by(plain, 1, 1) + made_by(dead, os.getpid(), reaper.stat(os.getpid())[1] + 1))
    removed = host.sweep(record)
    assert (removed, oct(plain.stat().st_mode & 0o777), str(plain) in capsys.readouterr().err,
            record.read_text()) == ([str(dead)], "0o400", True, made_by(plain, 1, 1))


@pytest.mark.parametrize("line", ['{"path": "/tmp/seed-set-ho', "", '{"pid": 1, "started": 1}', "[]",
                                  '{"path": 5, "pid": 1, "started": 1}', '{"path": "/tmp/seed-set-host-x"}'])
def test_the_sweep_skips_and_keeps_a_record_line_it_cannot_read(tmp_path, monkeypatch, capsys, line):  # review 4 m1
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    dead = Path(tempfile.mkdtemp(prefix="seed-set-host-"))
    record = tmp_path / "host-temp.jsonl"
    record.write_text(line + "\n" + made_by(dead, os.getpid(), reaper.stat(os.getpid())[1] + 1))
    removed = host.sweep(record)
    assert (removed, repr(line) in capsys.readouterr().err, record.read_text()) == ([str(dead)], True, line + "\n")


def test_the_sweep_removes_a_dead_kit_directory_whose_mode_is_000(tmp_path, monkeypatch):  # review 4 m1
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    dead = Path(tempfile.mkdtemp(prefix="seed-set-host-"))
    (dead / "check.pgid").write_text("1 1\n")
    dead.chmod(0)
    record = tmp_path / "host-temp.jsonl"
    record.write_text(made_by(dead, os.getpid(), reaper.stat(os.getpid())[1] + 1))
    assert (host.sweep(record), dead.exists()) == ([str(dead)], False)


def test_a_host_check_records_its_temporary_directories_and_its_child_makes_its_own_inside(tmp_path):  # round 3
    record = tmp_path / "host-temp.jsonl"
    done, _ = host.guarded([sys.executable, "-c", "import tempfile; print(tempfile.mkdtemp())"], record=record)
    (made,) = [Path(json.loads(line)["path"]) for line in record.read_text().splitlines()]
    assert (made.name.startswith("seed-set-host-"), Path(done.stdout.strip()).is_relative_to(made),
            made.exists()) == (True, True, False)
