from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        'native_process_unit_test', ROOT / 'scripts/experiments/native_session_cli_process.py'
    )
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = value
    spec.loader.exec_module(value)
    return value


class FakeProcess:
    def __init__(self, pid: int, *, running: bool) -> None:
        self.pid, self.running = pid, running
        self.waits: list[float | None] = []

    def poll(self) -> int | None:
        return None if self.running else 0

    def kill(self) -> None:
        raise OSError('synthetic termination failure')

    def wait(self, timeout: float | None = None) -> int:
        self.waits.append(timeout)
        assert timeout is not None, 'cleanup must never wait without a deadline'
        if self.running:
            raise subprocess.TimeoutExpired('fake-process', timeout)
        return 0


def _tracker(module: ModuleType, invocations: list) -> object:
    tracker = module.ProcessTracker.__new__(module.ProcessTracker)
    tracker.runner_pid, tracker.baseline = 100, {}
    tracker.invocations, tracker.pidfds = invocations, {}
    tracker.ambiguous_adoption = False
    tracker._remember = lambda process: True
    return tracker


def test_reused_leader_pid_cannot_claim_an_unrelated_subtree(module: ModuleType) -> None:
    old = module.Invocation(1, FakeProcess(201, running=False), 0, 10, finalized=True)
    tracker = _tracker(module, [old])
    tracker._capture({201: module.Process(201, 999, 'S', 999), 301: module.Process(301, 201, 'S', 30)})
    assert not old.tracked


def test_adoption_is_ambiguous_when_one_of_two_unfinished_leaders_has_exited(module: ModuleType) -> None:
    first = module.Invocation(3, FakeProcess(201, running=False), 0, 10)
    second = module.Invocation(4, FakeProcess(202, running=True), 0, 20)
    tracker = _tracker(module, [first, second])
    tracker._capture({202: module.Process(202, 100, 'S', 20), 301: module.Process(301, 100, 'S', 30)})
    assert tracker.ambiguous_adoption
    assert not first.tracking_ok and not second.tracking_ok


def test_adopted_child_subtree_remains_owned_after_leader_exit(module: ModuleType) -> None:
    invocation = module.Invocation(1, FakeProcess(201, running=False), 0, 10)
    tracker = _tracker(module, [invocation])
    tracker._capture({301: module.Process(301, 100, 'S', 30), 302: module.Process(302, 301, 'S', 31)})
    assert invocation.tracked == {301: 30, 302: 31}


def test_append_requires_previous_quiescence_even_after_leader_exit(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    invocation = module.Invocation(1, FakeProcess(201, running=False), 0, 10, finalized=True, quiescent=False)
    tracker = _tracker(module, [invocation])
    monkeypatch.setattr(module, '_process_table', lambda: {})
    def forbidden_spawn(*args, **kwargs):
        raise AssertionError('unproven quiescence must stop the next spawn')
    monkeypatch.setattr(module.subprocess, 'Popen', forbidden_spawn)
    with pytest.raises(RuntimeError):
        tracker.launch(2, ['fake'], cwd=tmp_path, env={}, stdout=-3, stderr=-3)


def test_cleanup_scan_failure_never_causes_unbounded_wait(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch
) -> None:
    process = FakeProcess(201, running=True)
    invocation = module.Invocation(1, process, time.monotonic() - 2, 10)
    tracker = _tracker(module, [invocation])
    def unavailable_table():
        raise RuntimeError('synthetic /proc failure')
    monkeypatch.setattr(module, '_process_table', unavailable_table)
    tracker.finish(invocation, .01)
    assert invocation.quiescent is False
    assert process.waits and all(timeout is not None for timeout in process.waits)


def test_failure_after_popen_cleans_registered_leader(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tracker = module.ProcessTracker()
    original_table, original_popen = module._process_table, module.subprocess.Popen
    children: list[subprocess.Popen] = []
    def capture_popen(*args, **kwargs):
        process = original_popen(*args, **kwargs)
        children.append(process)
        return process
    calls = 0
    def failed_scan():
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError('synthetic /proc failure after Popen')
        return original_table()
    monkeypatch.setattr(module.subprocess, 'Popen', capture_popen)
    monkeypatch.setattr(module, '_process_table', failed_scan)
    try:
        with pytest.raises(RuntimeError):
            tracker.launch(1, [sys.executable, '-c', 'import time;time.sleep(30)'],
                           cwd=tmp_path, env=os.environ, stdout=-3, stderr=-3)
        assert len(tracker.invocations) == 1
        assert children[0].poll() is not None
    finally:
        monkeypatch.setattr(module, '_process_table', original_table)
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=2)
        tracker.close()


def test_cleanup_recaptures_child_created_by_termination_handler(module: ModuleType, tmp_path: Path) -> None:
    tracker = module.ProcessTracker()
    ready, marker = tmp_path / 'ready', tmp_path / 'late-child'
    child_pid = None
    code = '''import signal,subprocess,sys,time
from pathlib import Path
marker,ready=sys.argv[1:]
def stop(sig,frame):
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],start_new_session=True)
    Path(marker).write_text(str(child.pid))
    raise SystemExit(0)
signal.signal(signal.SIGTERM,stop)
Path(ready).write_text('ready')
time.sleep(30)
'''
    invocation = tracker.launch(1, [sys.executable, '-c', code, str(marker), str(ready)],
                                cwd=tmp_path, env=os.environ, stdout=-3, stderr=-3)
    try:
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.01)
        assert ready.exists()
        tracker.finish(invocation, .1)
        assert marker.exists()
        child_pid = int(marker.read_text())
        table = module._process_table()
        assert child_pid not in table or table[child_pid].state in {'Z', 'X'}
    finally:
        if child_pid is None and marker.exists():
            child_pid = int(marker.read_text())
        if child_pid is not None:
            try:
                os.kill(child_pid, signal.SIGKILL)
                os.waitpid(child_pid, 0)
            except (ProcessLookupError, ChildProcessError):
                pass
        if invocation.process.poll() is None:
            invocation.process.kill()
        invocation.process.wait(timeout=2)
        tracker.close()


def test_close_cleans_an_active_invocation(module: ModuleType, tmp_path: Path) -> None:
    tracker = module.ProcessTracker()
    invocation = tracker.launch(1, [sys.executable, '-c', 'import time;time.sleep(30)'],
                                cwd=tmp_path, env=os.environ, stdout=-3, stderr=-3)
    try:
        tracker.close()
        assert invocation.process.poll() is not None
    finally:
        if invocation.process.poll() is None:
            invocation.process.kill()
        invocation.process.wait(timeout=2)


def test_reaped_child_between_snapshot_and_pidfd_does_not_block_quiescence(module: ModuleType, tmp_path: Path) -> None:
    tracker = module.ProcessTracker()
    spawn, ready, release = (tmp_path / name for name in ('spawn', 'ready', 'release'))
    tool = "import os,sys,time;from pathlib import Path;Path(sys.argv[1]).write_text(str(os.getpid()));\nwhile not Path(sys.argv[2]).exists():time.sleep(.001)"
    leader = "import subprocess,sys,time;from pathlib import Path;\nwhile not Path(sys.argv[1]).exists():time.sleep(.001)\nchild=subprocess.Popen([sys.executable,'-c',sys.argv[2],sys.argv[3],sys.argv[4]]);child.wait();time.sleep(.05)"
    invocation = tracker.launch(1, [sys.executable, '-c', leader, str(spawn), tool, str(ready), str(release)],
                                cwd=tmp_path, env=os.environ, stdout=-3, stderr=-3)
    spawn.touch()
    try:
        deadline = time.monotonic() + 2
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(.005)
        assert ready.exists()
        child_pid = int(ready.read_text())
        table = module._process_table()
        assert table[child_pid].state not in {'Z', 'X'}
        original_remember = tracker._remember
        def child_exits_before_open(process):
            if process.pid == child_pid:
                release.touch()
                deadline = time.monotonic() + 2
                while (Path('/proc') / str(child_pid)).exists() and time.monotonic() < deadline:
                    time.sleep(.001)
                assert not (Path('/proc') / str(child_pid)).exists()
            return original_remember(process)
        tracker._remember = child_exits_before_open
        tracker._capture(table)
        tracker.finish(invocation, 5)
        assert invocation.returncode == 0
        assert invocation.tracking_ok and invocation.quiescent
    finally:
        release.touch()
        tracker.close()


@pytest.mark.parametrize('failure', ['permission', 'state-read', 'original-alive'])
def test_failed_identity_capture_keeps_live_or_unverifiable_process_inconclusive(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    tracker = module.ProcessTracker()
    sampled = module.Process(201, 100, 'S', 10)
    def failed_open(pid):
        if failure == 'permission':
            raise PermissionError('synthetic permission failure')
        raise ProcessLookupError('synthetic process disappeared')
    def state_table():
        if failure == 'state-read':
            raise RuntimeError('synthetic state read failure')
        return {201: sampled}
    monkeypatch.setattr(module, '_pidfd_open', failed_open)
    monkeypatch.setattr(module, '_process_table', state_table)
    assert tracker._remember(sampled) is False
    assert tracker.tracking_failures[-1]['pid'] == sampled.pid
    assert tracker.tracking_failures[-1]['start_time'] == sampled.start_time
    assert tracker.tracking_failures[-1]['reason']


@pytest.mark.parametrize('current', [None, (201, 100, 'S', 20)])
def test_identity_recheck_confirms_original_death_and_closes_pidfd(
    module: ModuleType, monkeypatch: pytest.MonkeyPatch, current
) -> None:
    tracker = module.ProcessTracker()
    descriptor = module._pidfd_open(os.getpid())
    monkeypatch.setattr(module, '_pidfd_open', lambda pid: descriptor)
    monkeypatch.setattr(module, '_process_table', lambda: {} if current is None else {201: module.Process(*current)})
    assert tracker._remember(module.Process(201, 100, 'S', 10)) is True
    with pytest.raises(OSError):
        os.fstat(descriptor)
    assert not tracker.pidfds
