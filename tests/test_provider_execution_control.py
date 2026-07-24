"""Contract tests for generic cancellable provider execution."""

from __future__ import annotations

import io
import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import FrozenInstanceError
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, get_args

import pytest

from orchestrator.providers import (
    InputMode,
    ProviderExecutionClassification,
    ProviderExecutionControl,
    ProviderExecutor,
    ProviderInvocation,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
    SessionIdentitySnapshot,
)


class _CaptureWorkerAbort(BaseException):
    """Non-Exception capture-worker termination used by contract tests."""


def _wait_until(
    predicate: Callable[[], bool],
    *,
    timeout: float = 5.0,
    message: str,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    pytest.fail(message)


def _pid_is_running(pid: int) -> bool:
    """Treat a reaped-or-waiting-to-be-reaped zombie as no longer running."""
    state = _pid_state(pid)
    if state == "Z":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _pid_state(pid: int) -> str | None:
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except OSError:
        return None
    return fields[2] if len(fields) >= 3 else None


_requires_proc_stat = pytest.mark.skipif(
    not Path("/proc/self/stat").is_file(),
    reason="requires Linux /proc process-state inspection",
)


def test_pid_liveness_falls_back_to_signal_probe_without_proc_stat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing_stat(
        _path: Path,
        *,
        encoding: str,
    ) -> str:
        raise FileNotFoundError

    monkeypatch.setattr(Path, "read_text", _missing_stat)

    assert _pid_is_running(os.getpid()) is True


def _start_execution(
    executor: ProviderExecutor,
    invocation: ProviderInvocation,
    control: ProviderExecutionControl,
    *,
    session_runtime: dict[str, Any] | None = None,
    stream_output: bool = False,
) -> tuple[threading.Thread, dict[str, Any]]:
    result_box: dict[str, Any] = {}
    completion: Future[Any] = Future()
    assert completion.set_running_or_notify_cancel() is True
    control.attach_execution_future(completion)

    def _run() -> None:
        try:
            result = executor.execute(
                invocation,
                control=control,
                session_runtime=session_runtime,
                stream_output=stream_output,
            )
            result_box["result"] = result
            completion.set_result(result)
        except BaseException as exc:  # pragma: no cover - surfaced by assertions
            result_box["exception"] = exc
            completion.set_exception(exc)

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread, result_box


def _join_execution(
    thread: threading.Thread,
    result_box: dict[str, Any],
    *,
    timeout: float = 5.0,
) -> Any:
    thread.join(timeout=timeout)
    assert not thread.is_alive(), "provider execution did not terminate"
    assert "exception" not in result_box
    assert "result" in result_box
    return result_box["result"]


@pytest.fixture
def executor(tmp_path: Path) -> ProviderExecutor:
    return ProviderExecutor(tmp_path, ProviderRegistry())


@pytest.mark.parametrize("resume_boundary_seen", (False, True))
def test_resume_boundary_snapshot_is_preserved_at_control_copy_boundaries(
    resume_boundary_seen: bool,
) -> None:
    control = ProviderExecutionControl()
    source = SessionIdentitySnapshot(
        status="unique",
        session_ids=("session-copy",),
        terminal_seen=False,
        resume_boundary_seen=resume_boundary_seen,
    )

    control.publish_session_snapshot(source)
    published = control.session_snapshot
    terminal = control.spawn_failed("test terminal boundary")

    assert published is not None
    assert published is not source
    assert published.resume_boundary_seen is resume_boundary_seen
    assert terminal.final_session_snapshot is not None
    assert (
        terminal.final_session_snapshot.resume_boundary_seen
        is resume_boundary_seen
    )


def test_cancellation_before_bind_latches_and_runs_immediately_after_spawn(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    spawn_entered = threading.Event()
    allow_spawn = threading.Event()

    def _delayed_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        spawn_entered.set()
        assert allow_spawn.wait(timeout=5)
        return real_popen(*args, **kwargs)

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _delayed_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    completion: Future[Any] = Future()
    execution_box: dict[str, Any] = {}

    def _run() -> None:
        result = executor.execute(invocation, control=control)
        execution_box["result"] = result
        completion.set_result(result)

    execution_thread = threading.Thread(target=_run, daemon=True)
    execution_thread.start()
    assert spawn_entered.wait(timeout=5)
    assert control.state == "NEW"

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="pre-bind cancellation was not latched",
    )
    assert control.state == "NEW"

    control.attach_execution_future(completion)
    allow_spawn.set()
    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)

    assert not cancellation_thread.is_alive()
    cancellation_result = cancellation_box["result"]
    assert cancellation_result.disposition == "cancelled"
    assert cancellation_result.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.stdout == b""
    assert execution_result.provider_session is None
    assert control.state == "TERMINAL"


@_requires_proc_stat
def test_prebind_cancellation_cannot_promote_an_already_exited_provider(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    spawn_entered = threading.Event()
    allow_spawn = threading.Event()

    def _exit_before_bind_popen(
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.Popen:
        spawn_entered.set()
        assert allow_spawn.wait(timeout=5)
        process = real_popen(*args, **kwargs)
        _wait_until(
            lambda: _pid_state(process.pid) == "Z",
            message="provider did not exit before bind",
        )
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _exit_before_bind_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
        timeout_sec=None,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert spawn_entered.wait(timeout=5)

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="pre-bind cancellation did not latch",
    )
    allow_spawn.set()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]

    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_return_code == 0
    assert terminal.proof_complete is False
    assert terminal.term_sent is False
    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert (
        execution_result.error["type"]
        == "provider_cancellation_boundary_failed"
    )


@pytest.mark.parametrize("cancel_timing", ["bound", "prebind"])
def test_large_unread_controlled_stdin_cannot_block_cancellation(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cancel_timing: str,
) -> None:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []
    wait_thread_ids: list[int] = []
    writer_threads: list[threading.Thread] = []
    spawn_entered = threading.Event()
    allow_spawn = threading.Event()
    stdin_write_entered = threading.Event()
    ready_path = tmp_path / f"stdin-{cancel_timing}.ready"

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        spawn_entered.set()
        assert allow_spawn.wait(timeout=5)
        process = real_popen(*args, **kwargs)
        processes.append(process)
        _wait_until(
            ready_path.exists,
            message="stdin-resistant provider did not become ready",
        )
        real_wait = process.wait
        real_stdin = process.stdin
        assert real_stdin is not None

        class _RecordingStdin:
            @property
            def closed(self) -> bool:
                return real_stdin.closed

            def write(self, data: Any) -> int:
                if not writer_threads:
                    writer_threads.append(threading.current_thread())
                stdin_write_entered.set()
                return real_stdin.write(data)

            def close(self) -> None:
                real_stdin.close()

            def __getattr__(self, name: str) -> Any:
                return getattr(real_stdin, name)

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_thread_ids.append(threading.get_ident())
            return real_wait(*wait_args, **wait_kwargs)

        process.stdin = _RecordingStdin()  # type: ignore[assignment]
        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    script = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sys.stdout.buffer.write(b'partial-stdout'); sys.stdout.flush(); "
        "sys.stderr.buffer.write(b'partial-stderr'); sys.stderr.flush(); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 0.5
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        prompt="x" * (6 * 1024 * 1024),
        timeout_sec=None,
    )
    if cancel_timing == "bound":
        allow_spawn.set()
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert spawn_entered.wait(timeout=5)

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    if cancel_timing == "prebind":
        cancellation_thread.start()
        _wait_until(
            lambda: control.cancellation_requested,
            message="pre-bind stdin cancellation did not latch",
        )
        allow_spawn.set()
    else:
        assert stdin_write_entered.wait(timeout=5)
        cancellation_thread.start()

    cancellation_thread.join(timeout=2)
    automatic_cleanup = (
        not cancellation_thread.is_alive()
        and not execution_thread.is_alive()
    )
    if not automatic_cleanup:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    cancellation_thread.join(timeout=5)
    execution_result = _join_execution(execution_thread, execution_box)

    assert automatic_cleanup is True
    assert not cancellation_thread.is_alive()
    assert stdin_write_entered.is_set()
    terminal = cancellation_box["result"]
    assert terminal.disposition == "cancelled"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.capture_threads_joined is True
    assert terminal.execution_joined is True
    assert terminal.proof_complete is True
    assert terminal.term_sent is True
    assert terminal.kill_sent is True
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.raw_stdout == b"partial-stdout"
    assert execution_result.stderr == b"partial-stderr"
    assert wait_thread_ids
    assert set(wait_thread_ids) == {execution_thread.ident}
    assert len(writer_threads) == 1
    assert writer_threads[0] is not execution_thread
    assert writer_threads[0].is_alive() is False
    assert processes[0].stdin is not None
    assert processes[0].stdin.closed is True
    with pytest.raises(ProcessLookupError):
        os.killpg(processes[0].pid, 0)
    assert control.cancel_and_reap(grace=0.01) is terminal


@pytest.mark.parametrize(
    "failure_kind",
    ["runtime", "preapply_broken_pipe"],
)
def test_unexpected_controlled_stdin_writer_failure_fails_boundary(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    wait_thread_ids: list[int] = []
    writer_threads: list[threading.Thread] = []
    spawn_entered = threading.Event()
    allow_spawn = threading.Event()
    broken_pipe_classified = threading.Event()
    allow_broken_pipe_classification_return = threading.Event()
    kill_seen = threading.Event()
    close_saw_kill: list[bool] = []
    stdin_closed = threading.Event()
    ready_path = tmp_path / f"stdin-writer-{failure_kind}.ready"

    def _failing_stdin_popen(
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.Popen:
        spawn_entered.set()
        assert allow_spawn.wait(timeout=5)
        process = real_popen(*args, **kwargs)
        processes.append(process)
        _wait_until(
            ready_path.exists,
            message="stdin-failure provider did not become ready",
        )
        real_wait = process.wait
        real_stdin = process.stdin
        assert real_stdin is not None

        class _FailingStdin:
            @property
            def closed(self) -> bool:
                return real_stdin.closed

            def write(self, data: bytes) -> int:
                writer_threads.append(threading.current_thread())
                if failure_kind == "preapply_broken_pipe":
                    raise BrokenPipeError(
                        "stdin broke before cancellation signal"
                    )
                raise RuntimeError("stdin writer exploded")

            def close(self) -> None:
                stdin_closed.set()
                if failure_kind == "runtime":
                    close_saw_kill.append(
                        kill_seen.wait(timeout=0.5)
                    )
                real_stdin.close()

            def __getattr__(self, name: str) -> Any:
                return getattr(real_stdin, name)

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_thread_ids.append(threading.get_ident())
            if (
                failure_kind == "preapply_broken_pipe"
                and wait_kwargs.get("timeout") == 0
            ):
                assert broken_pipe_classified.wait(timeout=5)
            return real_wait(*wait_args, **wait_kwargs)

        process.stdin = _FailingStdin()  # type: ignore[assignment]
        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _failing_stdin_popen,
    )

    def _recording_killpg(pgid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            kill_seen.set()
        real_killpg(pgid, sig)

    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _recording_killpg,
    )
    script = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "sys.stdout.buffer.write(b'partial-stdout'); sys.stdout.flush(); "
        "sys.stderr.buffer.write(b'partial-stderr'); sys.stderr.flush(); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    classify_stdin_broken_pipe = (
        control.classify_stdin_broken_pipe
    )

    def _observed_broken_pipe_classification(
        *,
        failure_grace: float,
    ) -> bool:
        expected = classify_stdin_broken_pipe(
            failure_grace=failure_grace,
        )
        broken_pipe_classified.set()
        if failure_kind == "preapply_broken_pipe":
            assert allow_broken_pipe_classification_return.wait(timeout=5)
        return expected

    monkeypatch.setattr(
        control,
        "classify_stdin_broken_pipe",
        _observed_broken_pipe_classification,
    )
    apply_pending_cancellation = (
        control.apply_pending_cancellation_after_incomplete_probe
    )

    def _apply_pending_cancellation_and_release_writer() -> None:
        apply_pending_cancellation()
        allow_broken_pipe_classification_return.set()

    monkeypatch.setattr(
        control,
        "apply_pending_cancellation_after_incomplete_probe",
        _apply_pending_cancellation_and_release_writer,
    )
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        prompt="prompt",
        timeout_sec=None,
    )
    if failure_kind == "runtime":
        allow_spawn.set()
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert spawn_entered.wait(timeout=5)
    if failure_kind == "preapply_broken_pipe":
        assert control.state == "NEW"
        control.request_cancel(reason="external", grace=0.1)
        allow_spawn.set()
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.capture_threads_joined is True
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert terminal.term_sent is True
    assert terminal.kill_sent is True
    expected_failure = (
        "stdin broke before cancellation signal"
        if failure_kind == "preapply_broken_pipe"
        else "stdin writer exploded"
    )
    assert expected_failure in (terminal.error or "")
    assert execution_result.classification == "failed"
    assert execution_result.raw_stdout == b"partial-stdout"
    assert execution_result.stderr == b"partial-stderr"
    assert stdin_closed.is_set()
    if failure_kind == "runtime":
        assert close_saw_kill == [True]
    else:
        assert broken_pipe_classified.is_set()
    assert wait_thread_ids
    assert set(wait_thread_ids) == {execution_thread.ident}
    assert len(writer_threads) == 1
    assert writer_threads[0] is not execution_thread
    assert writer_threads[0].is_alive() is False
    with pytest.raises(ProcessLookupError):
        os.killpg(processes[0].pid, 0)
    assert control.cancel_and_reap(grace=0.01) is terminal


def test_spawn_failure_terminalizes_an_unbound_control(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[str(tmp_path / "missing-provider-command")],
        input_mode=InputMode.ARGV,
    )

    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert execution_result.error["type"] == "execution_error"
    assert control.state == "TERMINAL"
    assert terminal is not None
    assert terminal.disposition == "spawn_failed"
    assert terminal.pgid is None
    assert terminal.leader_reaped is False
    assert terminal.proof_complete is False
    assert control.cancel_and_reap(grace=0.01) is terminal


@pytest.mark.parametrize(
    "completion_kind",
    ["done", "exceptional", "cancelled"],
)
@pytest.mark.parametrize(
    "ordering",
    ["attach-then-cancel", "cancel-then-attach"],
)
def test_execution_future_ending_in_new_terminalizes_and_wakes_waiter(
    completion_kind: str,
    ordering: str,
) -> None:
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()

    if ordering == "attach-then-cancel":
        if completion_kind != "cancelled":
            assert completion.set_running_or_notify_cancel() is True
        control.attach_execution_future(completion)

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="pre-bind cancellation was not latched",
    )

    if completion_kind == "done":
        completion.set_result(object())
    elif completion_kind == "exceptional":
        completion.set_exception(RuntimeError("launch future failed"))
    else:
        if not completion.cancelled():
            assert completion.cancel() is True

    if ordering == "cancel-then-attach":
        control.attach_execution_future(completion)

    cancellation_thread.join(timeout=1)

    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]
    assert terminal is control.terminal_result
    assert terminal.disposition == "spawn_failed"
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert terminal.error is not None
    if completion_kind == "done":
        assert "completed before process binding" in terminal.error
    elif completion_kind == "exceptional":
        assert "launch future failed" in terminal.error
    else:
        assert "cancelled before process binding" in terminal.error


def test_cancelled_queued_execution_terminalizes_as_spawn_failure() -> None:
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    control.attach_execution_future(completion)
    cancellation_box: dict[str, Any] = {}

    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    cancellation_thread.join(timeout=0.5)
    returned_without_external_release = not cancellation_thread.is_alive()
    if not returned_without_external_release:
        completion.cancel()
        cancellation_thread.join(timeout=1)

    assert returned_without_external_release is True
    assert not cancellation_thread.is_alive()
    assert completion.cancelled() is True
    frozen = cancellation_box["result"]
    assert frozen.disposition == "spawn_failed"
    assert frozen.execution_joined is True
    assert frozen.proof_complete is False
    assert control.cancel_and_reap(grace=0.01) is frozen


def test_attaching_queued_execution_after_cancel_latch_cancels_it() -> None:
    control = ProviderExecutionControl()
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    completion: Future[Any] = Future()

    try:
        _wait_until(
            lambda: control.cancellation_requested,
            message="pre-bind cancellation was not latched",
        )
        control.attach_execution_future(completion)
        cancellation_thread.join(timeout=0.5)
    finally:
        if not completion.done():
            completion.cancel()
        cancellation_thread.join(timeout=1)

    assert completion.cancelled() is True
    assert not cancellation_thread.is_alive()
    frozen = cancellation_box["result"]
    assert frozen.disposition == "spawn_failed"
    assert frozen.execution_joined is True
    assert control.cancel_and_reap(grace=0.01) is frozen


def test_new_cancellation_does_not_reject_a_running_launch() -> None:
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    assert completion.set_running_or_notify_cancel() is True
    control.attach_execution_future(completion)
    cancellation_box: dict[str, Any] = {}

    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="pre-bind cancellation was not latched",
    )
    cancellation_thread.join(timeout=0.05)
    returned_before_launch_finished = not cancellation_thread.is_alive()
    claim_error: BaseException | None = None
    launch_error = RuntimeError("process creation failed")

    try:
        control.claim_spawn()
        control.spawn_failed(launch_error)
    except BaseException as exc:
        claim_error = exc
    finally:
        if not completion.done():
            completion.set_exception(launch_error)
        cancellation_thread.join(timeout=1)

    assert returned_before_launch_finished is False
    assert claim_error is None
    assert completion.cancelled() is False
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]
    assert terminal is control.terminal_result
    assert terminal.disposition == "spawn_failed"
    assert terminal.pgid is None
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False


def test_claimed_spawn_race_applies_latched_cancellation_after_bind(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    spawn_entered = threading.Event()
    allow_spawn_return = threading.Event()
    processes: list[subprocess.Popen] = []

    def _late_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        spawn_entered.set()
        assert allow_spawn_return.wait(timeout=5)
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _late_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )

    try:
        assert spawn_entered.wait(timeout=5)
        cancellation_thread.start()
        _wait_until(
            lambda: control.cancellation_requested,
            message="pre-bind cancellation was not latched",
        )
        cancellation_thread.join(timeout=0.3)
        returned_before_bind = not cancellation_thread.is_alive()

        allow_spawn_return.set()
        execution_result = _join_execution(
            execution_thread,
            execution_box,
        )
        cancellation_thread.join(timeout=5)
    finally:
        allow_spawn_return.set()
        for process in processes:
            if process.returncode is None:
                try:
                    real_killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert returned_before_bind is False
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]
    assert terminal is control.terminal_result
    assert terminal.disposition == "cancelled"
    assert terminal.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.exit_code != 0
    assert processes[0].returncode is not None
    with pytest.raises(ProcessLookupError):
        real_killpg(processes[0].pid, 0)


def test_control_absence_keeps_the_legacy_result_unclassified(
    executor: ProviderExecutor,
) -> None:
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "print('legacy')"],
        input_mode=InputMode.ARGV,
    )

    execution_result = executor.execute(invocation)

    assert execution_result.exit_code == 0
    assert execution_result.stdout == b"legacy\n"
    assert execution_result.classification is None
    assert execution_result.is_promotable is True


def test_provider_execution_classification_is_a_closed_contract() -> None:
    assert set(get_args(ProviderExecutionClassification)) == {
        "normal",
        "cancelled_provisional",
        "failed",
    }


def test_natural_exit_freezes_a_complete_terminal_proof(
    executor: ProviderExecutor,
) -> None:
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import os, sys; "
            "sys.stdout.write(f'{os.getpid()}:{os.getpgrp()}'); sys.stdout.flush()",
        ],
        input_mode=InputMode.ARGV,
    )

    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert execution_result.classification == "normal"
    assert execution_result.exit_code == 0
    assert execution_result.is_promotable is True
    pid_text, pgid_text = execution_result.stdout.decode("utf-8").split(":")
    assert pid_text == pgid_text
    assert int(pgid_text) != os.getpgrp()
    assert terminal is not None
    assert terminal.disposition == "natural_exit"
    assert terminal.leader_return_code == 0
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.capture_threads_joined is True
    assert terminal.execution_joined is True
    assert terminal.final_identity_valid is True
    assert terminal.proof_complete is True


def test_cancellation_escalates_from_term_to_kill(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "ready"
    term_path = tmp_path / "term-observed"
    script = (
        "import pathlib, signal, time; "
        f"ready = pathlib.Path({str(ready_path)!r}); "
        f"term = pathlib.Path({str(term_path)!r}); "
        "signal.signal(signal.SIGTERM, lambda *_: term.write_text('TERM')); "
        "ready.write_text('ready'); "
        "\nwhile True: time.sleep(0.05)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")

    cancellation_result = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)

    assert term_path.read_text(encoding="utf-8") == "TERM"
    assert cancellation_result.disposition == "cancelled"
    assert cancellation_result.term_sent is True
    assert cancellation_result.kill_sent is True
    assert cancellation_result.leader_return_code == -signal.SIGKILL
    assert cancellation_result.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"


def test_cancellation_escalates_after_a_failed_term_delivery(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_killpg = os.killpg
    term_attempted = threading.Event()
    kill_attempted = threading.Event()
    ready_path = tmp_path / "failed-term-escalation.ready"

    def _fail_term_only(pgid: int, sig: int) -> None:
        if sig == signal.SIGTERM:
            term_attempted.set()
            raise PermissionError("injected TERM delivery failure")
        if sig == signal.SIGKILL:
            kill_attempted.set()
        real_killpg(pgid, sig)

    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _fail_term_only,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.05),
        ),
        daemon=True,
    )

    try:
        _wait_until(ready_path.exists, message="provider did not become ready")
        cancellation_thread.start()
        cancellation_thread.join(timeout=1)
        escalated_without_external_cleanup = (
            not cancellation_thread.is_alive()
            and not execution_thread.is_alive()
        )
        if not escalated_without_external_cleanup:
            real_killpg(control._pgid, signal.SIGKILL)
        cancellation_thread.join(timeout=5)
        execution_result = _join_execution(execution_thread, execution_box)
    finally:
        pgid = control._pgid
        if isinstance(pgid, int):
            try:
                real_killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    assert escalated_without_external_cleanup is True
    assert term_attempted.is_set()
    assert kill_attempted.is_set()
    terminal = cancellation_box["result"]
    assert terminal.disposition == "boundary_failed"
    assert terminal.term_sent is False
    assert terminal.kill_sent is True
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert "TERM delivery failure" in (terminal.error or "")
    assert execution_result.classification == "failed"


def test_persistent_group_signal_failure_uses_bounded_leader_fallback(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    signal_attempts: list[int] = []

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _fail_group_signals(pgid: int, sig: int) -> None:
        if sig == 0:
            real_killpg(pgid, sig)
            return
        signal_attempts.append(sig)
        raise PermissionError(f"injected group signal failure {sig}")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _fail_group_signals,
    )
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 0.05
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}

    def _cancel() -> None:
        try:
            cancellation_box["result"] = control.cancel_and_reap(grace=0.01)
        except BaseException as exc:
            cancellation_box["exception"] = exc

    cancellation_thread = threading.Thread(target=_cancel, daemon=True)

    try:
        _wait_until(
            lambda: control.state == "BOUND",
            message="provider control did not bind",
        )
        cancellation_thread.start()
        cancellation_thread.join(timeout=1)
        cancellation_returned_before_cleanup = not cancellation_thread.is_alive()
        returned_while_execution_live = execution_thread.is_alive()
        if not cancellation_returned_before_cleanup or returned_while_execution_live:
            real_killpg(processes[0].pid, signal.SIGKILL)
        cancellation_thread.join(timeout=5)
        execution_result = _join_execution(execution_thread, execution_box)
    finally:
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert cancellation_returned_before_cleanup is True
    assert "exception" not in cancellation_box
    assert returned_while_execution_live is False
    assert signal_attempts.count(signal.SIGTERM) == 1
    assert signal_attempts.count(signal.SIGKILL) <= 1
    terminal = cancellation_box["result"]
    assert terminal is control.terminal_result
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert execution_result.classification == "failed"


def test_group_signal_failure_with_inherited_pipes_has_bounded_workers(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    signal_attempts: list[int] = []
    finalize_thread_ids: list[int] = []
    ready_path = tmp_path / "bound-live-group.ready"
    child_pid_path = tmp_path / "bound-live-group-child.pid"

    class _RecordingAccumulator:
        def snapshot(self) -> SessionIdentitySnapshot:
            return SessionIdentitySnapshot(
                status="missing",
                session_ids=(),
                terminal_seen=False,
            )

        def feed(self, _chunk: bytes) -> None:
            return

        def finalize(
            self,
            *,
            expected_session_id: str | None,
            require_terminal: bool,
        ) -> tuple[None, dict[str, Any]]:
            finalize_thread_ids.append(threading.get_ident())
            return None, {"type": "incomplete test transport"}

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _fail_group_signals(pgid: int, sig: int) -> None:
        if sig == 0:
            real_killpg(pgid, sig)
            return
        signal_attempts.append(sig)
        raise PermissionError(f"injected group signal failure {sig}")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _fail_group_signals,
    )
    monkeypatch.setattr(
        "orchestrator.providers.executor."
        "create_session_transport_accumulator",
        lambda *_args, **_kwargs: _RecordingAccumulator(),
    )
    child_script = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"child = subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 2.0
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", parent_script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}

    def _cancel() -> None:
        try:
            cancellation_box["result"] = control.cancel_and_reap(grace=0.01)
        except BaseException as exc:
            cancellation_box["exception"] = exc

    cancellation_thread = threading.Thread(target=_cancel, daemon=True)

    try:
        _wait_until(ready_path.exists, message="provider child did not start")
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        cancellation_thread.start()
        execution_thread.join(timeout=1.5)
        execution_returned_before_cleanup = not execution_thread.is_alive()
        if not execution_returned_before_cleanup:
            real_killpg(processes[0].pid, signal.SIGKILL)
        execution_result = _join_execution(execution_thread, execution_box)
        finalize_calls_before_cleanup = tuple(finalize_thread_ids)
        cancellation_thread.join(timeout=5)
    finally:
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        if "child_pid" in locals():
            _wait_until(
                lambda: not _pid_is_running(child_pid),
                message="provider child remained live after test cleanup",
            )

    assert execution_returned_before_cleanup is True
    assert not cancellation_thread.is_alive()
    assert "exception" not in cancellation_box
    assert signal_attempts.count(signal.SIGTERM) == 1
    assert signal_attempts.count(signal.SIGKILL) == 1
    assert execution_thread.ident not in finalize_calls_before_cleanup
    terminal = cancellation_box["result"]
    assert terminal is control.terminal_result
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is False
    assert terminal.capture_threads_joined is False
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert execution_result.classification == "failed"


def test_unjoined_failure_preserves_signal_error_and_future_done_fact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 0.01
    control.claim_spawn()
    control.bind(SimpleNamespace(pid=987654), 987654)
    completion: Future[Any] = Future()
    completion.set_result(object())
    control.attach_execution_future(completion)

    def _fail_signal(_pgid: int, sig: int) -> None:
        if sig == 0:
            raise ProcessLookupError
        raise PermissionError("primary signal failure")

    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _fail_signal,
    )
    control.request_cancel(grace=0.01)
    control.apply_pending_cancellation_after_incomplete_probe()

    frozen = control.cancel_and_reap(grace=0.01)

    assert frozen.disposition == "boundary_failed"
    assert frozen.execution_joined is True
    assert frozen.term_sent is False
    assert frozen.kill_sent is False
    assert "primary signal failure" in (frozen.error or "")
    assert "complete boundary" in (frozen.error or "")


def test_boundary_failure_preserves_both_capture_and_signal_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = ProviderExecutionControl()
    control.claim_spawn()
    control.bind(SimpleNamespace(pid=987654), 987654)

    def _fail_term_then_report_empty(_pgid: int, sig: int) -> None:
        if sig == signal.SIGTERM:
            raise PermissionError("primary signal failure")
        if sig == 0:
            raise ProcessLookupError

    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _fail_term_then_report_empty,
    )
    control.request_cancel(grace=0.01)
    control.apply_pending_cancellation_after_incomplete_probe()
    control.record_leader_reaped(1)

    boundary = control.record_execution_boundary(
        capture_threads_joined=True,
        final_identity_valid=True,
        boundary_error="capture worker exploded",
    )

    assert boundary.disposition == "boundary_failed"
    assert "capture worker exploded" in (boundary.error or "")
    assert "primary signal failure" in (boundary.error or "")


def test_cancellation_honors_grace_for_a_lingering_child(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_killpg = os.killpg
    signal_times: dict[int, float] = {}
    child_ready_path = tmp_path / "grace-child-ready"
    parent_ready_path = tmp_path / "grace-parent-ready"

    def _recording_killpg(pgid: int, sig: int) -> None:
        signal_times.setdefault(sig, time.monotonic())
        real_killpg(pgid, sig)

    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _recording_killpg,
    )
    child_script = (
        "import pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(child_ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, signal, subprocess, sys, time; "
        f"subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(parent_ready_path)!r}).write_text('ready'); "
        "\nwhile True: time.sleep(0.05)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", parent_script],
        input_mode=InputMode.ARGV,
        timeout_sec=None,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(parent_ready_path.exists, message="parent did not become ready")
    _wait_until(child_ready_path.exists, message="child did not become ready")

    terminal = control.cancel_and_reap(grace=0.35)
    execution_result = _join_execution(execution_thread, execution_box)

    assert terminal.disposition == "cancelled"
    assert terminal.term_sent is True
    assert terminal.kill_sent is True
    assert signal.SIGTERM in signal_times
    assert signal.SIGKILL in signal_times
    assert (
        signal_times[signal.SIGKILL] - signal_times[signal.SIGTERM]
        >= 0.30
    )
    assert execution_result.classification == "cancelled_provisional"


def test_runtime_cancellation_handler_exit_seven_is_still_cancelled(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "exit-seven-ready"
    script = (
        "import pathlib, signal, sys, time; "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(7)); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "\nwhile True: time.sleep(0.05)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
        timeout_sec=None,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")

    terminal = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)

    assert terminal.disposition == "cancelled"
    assert terminal.leader_return_code == 7
    assert terminal.term_sent is True
    assert terminal.pgid_empty is True
    assert terminal.proof_complete is True
    assert execution_result.exit_code == 7
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.is_promotable is False


def test_exit_zero_cancellation_is_nonzero_and_not_promotable(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "cancel-exit-zero.ready"
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, signal, sys, time; "
            "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")

    terminal = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)

    assert terminal.disposition == "cancelled"
    assert terminal.leader_return_code == 0
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.exit_code != 0
    assert execution_result.is_promotable is False


def test_cancellation_cleans_same_pgid_children(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "child.pid"
    ready_path = tmp_path / "ready"
    script = (
        "import pathlib, subprocess, sys, time; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "\nwhile True: time.sleep(0.05)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider child was not created")
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    cancellation_result = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)
    _wait_until(
        lambda: not _pid_is_running(child_pid),
        message="same-PGID child survived cancellation",
    )

    assert cancellation_result.pgid_empty is True
    assert cancellation_result.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"


def test_natural_leader_exit_with_lingering_child_is_cleaned_but_rejected(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    child_pid_path = tmp_path / "lingering-child.pid"
    script = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )

    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    terminal = control.terminal_result
    _wait_until(
        lambda: not _pid_is_running(child_pid),
        message="lingering same-PGID child was not cleaned",
    )

    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert execution_result.error["type"] == "provider_cancellation_boundary_failed"
    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.natural_exit_with_lingering_group is True
    assert terminal.pgid_empty is True
    assert terminal.proof_complete is False


def test_repeated_cancellation_returns_the_same_frozen_disposition(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "ready"
    script = (
        "import pathlib, time; "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")

    first = control.cancel_and_reap(grace=0.1)
    second = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)

    assert second is first
    assert control.terminal_result is first
    assert execution_result.classification == "cancelled_provisional"
    with pytest.raises(FrozenInstanceError):
        first.pgid_empty = False  # type: ignore[misc]


def test_concurrent_natural_exit_and_cancel_freeze_exactly_one_outcome(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "ready"
    exit_path = tmp_path / "exit"
    script = (
        "import pathlib, time; "
        f"ready = pathlib.Path({str(ready_path)!r}); "
        f"exit_path = pathlib.Path({str(exit_path)!r}); "
        "ready.write_text('ready'); "
        "\nwhile not exit_path.exists(): time.sleep(0.005)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")
    race = threading.Barrier(3)
    cancellation_box: dict[str, Any] = {}

    def _cancel() -> None:
        race.wait()
        cancellation_box["result"] = control.cancel_and_reap(grace=0.1)

    def _exit_naturally() -> None:
        race.wait()
        exit_path.write_text("exit", encoding="utf-8")

    cancellation_thread = threading.Thread(target=_cancel, daemon=True)
    exit_thread = threading.Thread(target=_exit_naturally, daemon=True)
    cancellation_thread.start()
    exit_thread.start()
    race.wait()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    exit_thread.join(timeout=5)
    frozen = control.terminal_result

    assert frozen is not None
    assert cancellation_box["result"] is frozen
    assert control.cancel_and_reap(grace=0.1) is frozen
    assert frozen.disposition in {"natural_exit", "cancelled"}
    assert frozen.proof_complete is True
    expected_classification = (
        "normal"
        if frozen.disposition == "natural_exit"
        else "cancelled_provisional"
    )
    assert execution_result.classification == expected_classification


def test_cancel_and_reap_waits_for_capture_threads_to_join(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ready_path = tmp_path / "ready"
    readers_at_eof = threading.Event()
    release_readers = threading.Event()
    original_capture_pipe = executor._capture_pipe

    def _delayed_capture(*args: Any, **kwargs: Any) -> None:
        original_capture_pipe(*args, **kwargs)
        readers_at_eof.set()
        assert release_readers.wait(timeout=5)

    monkeypatch.setattr(executor, "_capture_pipe", _delayed_capture)
    script = (
        "import pathlib, sys, time; "
        "sys.stdout.write('partial'); sys.stdout.flush(); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    assert readers_at_eof.wait(timeout=5)
    time.sleep(0.05)
    assert cancellation_thread.is_alive()

    release_readers.set()
    cancellation_thread.join(timeout=5)
    execution_result = _join_execution(execution_thread, execution_box)

    assert cancellation_box["result"].capture_threads_joined is True
    assert cancellation_box["result"].execution_joined is True
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.raw_stdout == b"partial"


def test_late_capture_finalization_keeps_frozen_failure_and_partial_buffers(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ProviderExecutionControl,
        "_FINALIZATION_TIMEOUT_SEC",
        0.05,
    )
    original_capture_pipe = executor._capture_pipe
    capture_lock = threading.Lock()
    capture_count = 0
    captures_at_eof = threading.Event()
    release_captures = threading.Event()

    def _delayed_capture(*args: Any, **kwargs: Any) -> None:
        nonlocal capture_count
        original_capture_pipe(*args, **kwargs)
        with capture_lock:
            capture_count += 1
            if capture_count == 2:
                captures_at_eof.set()
        assert release_captures.wait(timeout=5)

    monkeypatch.setattr(executor, "_capture_pipe", _delayed_capture)
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import sys; "
            "sys.stdout.write('partial'); sys.stdout.flush(); "
            "sys.stderr.write('diagnostic'); sys.stderr.flush()",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert captures_at_eof.wait(timeout=5)

    frozen = control.cancel_and_reap(grace=0.01)
    assert frozen.disposition == "boundary_failed"
    assert frozen.capture_threads_joined is False
    assert frozen.execution_joined is False
    assert frozen.proof_complete is False

    release_captures.set()
    execution_result = _join_execution(execution_thread, execution_box)

    assert control.terminal_result is frozen
    assert control.cancel_and_reap(grace=0.01) is frozen
    assert execution_result.classification == "failed"
    assert execution_result.exit_code != 0
    assert execution_result.is_promotable is False
    assert execution_result.stdout == b""
    assert execution_result.raw_stdout == b"partial"
    assert execution_result.stderr == b"diagnostic"
    assert execution_result.normalized_stdout is None
    assert execution_result.provider_session is None


def test_frozen_failure_does_not_revoke_bound_process_cleanup(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    wait_blocked = threading.Event()
    release_wait = threading.Event()
    ready_path = tmp_path / "frozen-proof-cleanup.ready"

    def _blocked_wait_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        try:
            _wait_until(
                ready_path.exists,
                message="TERM-resistant provider did not become ready",
            )
        except BaseException:
            real_killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
        real_wait = process.wait
        first_probe = True

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            nonlocal first_probe
            if first_probe and wait_kwargs.get("timeout") == 0:
                first_probe = False
                wait_blocked.set()
                assert release_wait.wait(timeout=5)
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _blocked_wait_popen,
    )
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 0.05
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )

    try:
        assert wait_blocked.wait(timeout=5)
        frozen = control.cancel_and_reap(grace=0.01)
        assert frozen.disposition == "boundary_failed"
        assert frozen.leader_reaped is False
        assert frozen.execution_joined is False

        release_wait.set()
        execution_thread.join(timeout=1)
        cleanup_finished_automatically = not execution_thread.is_alive()
        if not cleanup_finished_automatically:
            real_killpg(processes[0].pid, signal.SIGKILL)
        execution_result = _join_execution(execution_thread, execution_box)
    finally:
        release_wait.set()
        for process in processes:
            if process.returncode is None:
                try:
                    real_killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert cleanup_finished_automatically is True
    assert control.terminal_result is frozen
    assert control.cancel_and_reap(grace=0.01) is frozen
    assert frozen.leader_reaped is False
    assert frozen.execution_joined is False
    assert execution_result.classification == "failed"
    assert execution_result.exit_code != 0
    with pytest.raises(ProcessLookupError):
        real_killpg(processes[0].pid, 0)


@pytest.mark.parametrize("failed_stream", ["stdout", "stderr"])
def test_capture_worker_exception_fails_the_controlled_boundary(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
    failed_stream: str,
) -> None:
    original_capture_pipe = executor._capture_pipe

    def _failing_capture(
        pipe: Any,
        buffer: bytearray,
        **kwargs: Any,
    ) -> None:
        stream_name = "stdout" if "read_mode" in kwargs else "stderr"
        if stream_name == failed_stream:
            try:
                buffer.extend(f"partial-{stream_name}".encode("utf-8"))
                raise RuntimeError(f"{stream_name} capture exploded")
            finally:
                pipe.close()
        original_capture_pipe(pipe, buffer, **kwargs)

    monkeypatch.setattr(executor, "_capture_pipe", _failing_capture)
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
    )

    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.capture_threads_joined is True
    assert terminal.proof_complete is False
    assert f"{failed_stream} capture exploded" in (terminal.error or "")
    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert (
        execution_result.error["type"]
        == "provider_cancellation_boundary_failed"
    )
    assert "execution_joined" not in execution_result.error["context"]
    if failed_stream == "stdout":
        assert execution_result.raw_stdout == b"partial-stdout"
    else:
        assert execution_result.stderr == b"partial-stderr"


@pytest.mark.parametrize("hook_kind", ["callback", "display"])
def test_legacy_capture_hook_baseexception_propagates(
    executor: ProviderExecutor,
    hook_kind: str,
) -> None:
    class _AbortingDisplay:
        def write(self, chunk: bytes) -> None:
            raise _CaptureWorkerAbort("display aborted")

        def flush(self) -> None:
            raise AssertionError("flush must not follow a failed write")

    def _aborting_callback(chunk: bytes) -> None:
        raise _CaptureWorkerAbort("callback aborted")

    pipe = io.BytesIO(b"captured-payload")
    buffer = bytearray()
    with pytest.raises(_CaptureWorkerAbort):
        executor._capture_pipe(
            pipe,
            buffer,
            out_stream=_AbortingDisplay() if hook_kind == "display" else None,
            chunk_callback=(
                _aborting_callback
                if hook_kind == "callback"
                else None
            ),
        )

    assert bytes(buffer) == b"captured-payload"
    assert pipe.closed is True


def test_legacy_capture_buffer_lookup_baseexception_propagates() -> None:
    executor = ProviderExecutor(Path.cwd(), ProviderRegistry())
    abort = _CaptureWorkerAbort("buffer lookup aborted")

    class _AbortingBufferLookup:
        @property
        def buffer(self) -> Any:
            raise abort

    pipe = io.BytesIO(b"payload")
    try:
        with pytest.raises(_CaptureWorkerAbort) as caught:
            executor._capture_pipe(
                pipe,
                bytearray(),
                out_stream=_AbortingBufferLookup(),
            )
    finally:
        pipe.close()

    assert caught.value is abort


@pytest.mark.parametrize("hook_kind", ["callback", "display"])
def test_controlled_optional_hook_baseexception_is_best_effort_via_execute(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
    hook_kind: str,
) -> None:
    abort = _CaptureWorkerAbort(f"{hook_kind} aborted")
    raw_stdout = (
        '{"type":"session.started","session_id":"sess-controlled"}\n'
        '{"type":"assistant.message","role":"assistant","text":"hello"}\n'
        '{"type":"response.completed","session_id":"sess-controlled"}\n'
    )

    if hook_kind == "callback":
        original_build_callback = executor._build_session_stdout_callback

        def _build_aborting_callback(**kwargs: Any) -> Callable[[bytes], None]:
            callback = original_build_callback(**kwargs)

            def _callback(chunk: bytes) -> None:
                callback(chunk)
                raise abort

            return _callback

        monkeypatch.setattr(
            executor,
            "_build_session_stdout_callback",
            _build_aborting_callback,
        )
        invocation = ProviderInvocation(
            command=[
                sys.executable,
                "-c",
                f"import sys; sys.stdout.write({raw_stdout!r})",
            ],
            input_mode=InputMode.ARGV,
            command_variant="fresh_command",
            metadata_mode=(
                ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
            ),
            session_request=ProviderSessionRequest(
                mode=ProviderSessionMode.FRESH,
            ),
        )
        stream_output = False
    else:
        class _AbortingDisplay:
            def write(self, _chunk: bytes) -> None:
                raise abort

            def flush(self) -> None:
                raise AssertionError("flush must not follow failed write")

        monkeypatch.setattr(
            "orchestrator.providers.executor.sys.stdout",
            _AbortingDisplay(),
        )
        invocation = ProviderInvocation(
            command=[
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('display-payload')",
            ],
            input_mode=InputMode.ARGV,
        )
        stream_output = True

    control = ProviderExecutionControl()
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
        stream_output=stream_output,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert execution_result.classification == "normal"
    assert terminal is not None
    assert terminal.disposition == "natural_exit"
    assert terminal.proof_complete is True
    if hook_kind == "callback":
        assert execution_result.raw_stdout == raw_stdout.encode("utf-8")
        assert execution_result.stdout == b"hello"
    else:
        assert execution_result.raw_stdout == b"display-payload"


@pytest.mark.parametrize(
    "failure_kind",
    ["exception", "baseexception"],
)
def test_live_no_timeout_capture_failure_forces_bounded_group_cleanup(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
) -> None:
    real_popen = subprocess.Popen
    original_capture_pipe = executor._capture_pipe
    processes: list[subprocess.Popen] = []
    wait_thread_ids: list[int] = []
    ready_path = tmp_path / f"capture-{failure_kind}.ready"

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_thread_ids.append(threading.get_ident())
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    def _failing_capture(
        pipe: Any,
        buffer: bytearray,
        **kwargs: Any,
    ) -> None:
        if "read_mode" not in kwargs:
            original_capture_pipe(pipe, buffer, **kwargs)
            return
        _wait_until(
            ready_path.exists,
            message="TERM-resistant provider did not become ready",
        )
        try:
            buffer.extend(b"partial-live-capture")
            if failure_kind == "exception":
                raise RuntimeError("live stdout capture exploded")
            raise _CaptureWorkerAbort("live stdout capture aborted")
        finally:
            pipe.close()

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(executor, "_capture_pipe", _failing_capture)
    script = (
        "import pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
        timeout_sec=None,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )

    execution_thread.join(timeout=2)
    automatic_cleanup = not execution_thread.is_alive()
    if not automatic_cleanup:
        for process in processes:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    execution_result = _join_execution(execution_thread, execution_box)

    assert automatic_cleanup is True
    terminal = control.terminal_result
    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.capture_threads_joined is True
    assert terminal.execution_joined is True
    assert terminal.term_sent is True
    assert terminal.kill_sent is True
    assert terminal.proof_complete is False
    assert execution_result.classification == "failed"
    assert execution_result.raw_stdout == b"partial-live-capture"
    assert execution_result.error is not None
    assert (
        execution_result.error["type"]
        == "provider_cancellation_boundary_failed"
    )
    expected_failure = (
        "live stdout capture exploded"
        if failure_kind == "exception"
        else "live stdout capture aborted"
    )
    assert expected_failure in (terminal.error or "")
    assert wait_thread_ids
    assert set(wait_thread_ids) == {execution_thread.ident}
    with pytest.raises(ProcessLookupError):
        os.killpg(processes[0].pid, 0)
    assert control.cancel_and_reap(grace=0.01) is terminal


def test_invalid_final_session_identity_rejects_the_cancellation_boundary(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "ready"
    identity_line = (
        '{"type":"thread.started","thread_id":"session-123"}\n'
    )
    script = (
        "import pathlib, sys, time; "
        f"sys.stdout.buffer.write({identity_line.encode('utf-8')!r}); "
        "sys.stdout.buffer.write(b'{'); sys.stdout.flush(); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=(
            ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        ),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="session provider did not become ready")
    _wait_until(
        lambda: control.session_snapshot is not None
        and control.session_snapshot.status == "unique",
        message="preterminal session identity did not become unique",
    )
    provisional_snapshot = control.session_snapshot
    assert provisional_snapshot is not None

    cancellation_result = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, execution_box)

    assert provisional_snapshot.status == "unique"
    assert provisional_snapshot.session_ids == ("session-123",)
    assert cancellation_result.disposition == "boundary_failed"
    assert cancellation_result.final_session_snapshot is not None
    assert cancellation_result.final_session_snapshot.status == "invalid"
    assert cancellation_result.final_identity_valid is False
    assert cancellation_result.proof_complete is False
    assert execution_result.classification == "failed"
    assert execution_result.stdout == b""
    assert execution_result.raw_stdout == identity_line.encode("utf-8") + b"{"
    assert execution_result.normalized_stdout is None
    assert execution_result.provider_session is None
    assert execution_result.error is not None
    assert execution_result.error["type"] == "provider_cancellation_boundary_failed"


def test_timeout_does_not_mask_a_failed_final_identity_proof(
    executor: ProviderExecutor,
) -> None:
    script = (
        "import sys, time; "
        "sys.stdout.buffer.write(b'{'); sys.stdout.flush(); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        timeout_sec=0.1,
        command_variant="fresh_command",
        metadata_mode=(
            ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        ),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
    )

    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    execution_result = _join_execution(execution_thread, execution_box)
    terminal = control.terminal_result

    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.final_identity_valid is False
    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert execution_result.error["type"] == "provider_cancellation_boundary_failed"


def test_post_bind_capture_setup_failure_cleans_and_reaps_owned_group(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _fail_thread_start(_thread: threading.Thread) -> None:
        raise RuntimeError("capture thread start failed")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.executor.threading.Thread.start",
        _fail_thread_start,
    )
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    control.attach_execution_future(completion)
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )

    try:
        execution_result = executor.execute(invocation, control=control)
        completion.set_result(execution_result)
        terminal = control.terminal_result

        assert execution_result.classification == "failed"
        assert control.state == "TERMINAL"
        assert terminal is not None
        assert terminal.disposition == "boundary_failed"
        assert terminal.leader_reaped is True
        assert terminal.pgid_empty is True
        assert terminal.proof_complete is False
        assert processes[0].returncode is not None
    finally:
        for process in processes:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)


@pytest.mark.parametrize(
    "interruption",
    [
        pytest.param(KeyboardInterrupt("injected interrupt"), id="keyboard"),
        pytest.param(
            _CaptureWorkerAbort("injected base abort"),
            id="custom-baseexception",
        ),
    ],
)
def test_post_bind_baseexception_cleans_boundary_then_reraises(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interruption: BaseException,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    ready_path = tmp_path / f"post-bind-{type(interruption).__name__}.ready"

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _interrupt_after_bind(**_kwargs: Any) -> Any:
        _wait_until(
            ready_path.exists,
            message="post-bind provider did not become ready",
        )
        raise interruption

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        executor,
        "_run_bound_controlled_invocation",
        _interrupt_after_bind,
    )
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    control.attach_execution_future(completion)
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    caught: BaseException | None = None

    try:
        try:
            executor.execute(invocation, control=control)
        except BaseException as exc:
            caught = exc
            completion.set_exception(exc)
        assert processes
        process = processes[0]
        group_cleaned_before_teardown = False
        try:
            real_killpg(process.pid, 0)
        except ProcessLookupError:
            group_cleaned_before_teardown = True
        pipes_closed_before_teardown = all(
            pipe is None or pipe.closed
            for pipe in (process.stdin, process.stdout, process.stderr)
        )
    finally:
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert caught is interruption
    assert completion.exception() is interruption
    assert group_cleaned_before_teardown is True
    assert pipes_closed_before_teardown is True
    terminal = control.terminal_result
    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.capture_threads_joined is True
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert str(interruption) in (terminal.error or "")


def test_bind_rejection_after_popen_is_reaped_by_the_executor_thread(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []
    wait_thread_ids: list[int] = []

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_thread_ids.append(threading.get_ident())
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    control.attach_execution_future(completion)

    def _reject_bind(_process: subprocess.Popen, _pgid: int) -> None:
        raise RuntimeError("injected bind rejection")

    monkeypatch.setattr(control, "bind", _reject_bind)
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    execution_result: Any = None
    execution_error: BaseException | None = None

    try:
        try:
            execution_result = executor.execute(invocation, control=control)
        except BaseException as exc:
            execution_error = exc
            completion.set_exception(exc)
        else:
            completion.set_result(execution_result)

        assert execution_error is None
        assert execution_result.classification == "failed"
        terminal = control.terminal_result
        assert terminal is not None
        assert terminal.disposition == "boundary_failed"
        assert terminal.pgid == processes[0].pid
        assert terminal.leader_reaped is True
        assert terminal.pgid_empty is True
        assert terminal.proof_complete is False
        assert "bind rejection" in (terminal.error or "")
        assert processes[0].returncode is not None
        with pytest.raises(ProcessLookupError):
            os.killpg(processes[0].pid, 0)
        assert wait_thread_ids
        assert set(wait_thread_ids) == {threading.get_ident()}
    finally:
        for process in processes:
            if process.returncode is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)


def test_bind_baseexception_cleans_spawned_process_then_reraises(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    interruption = _CaptureWorkerAbort("bind interrupted")

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _interrupt_bind(_process: subprocess.Popen, _pgid: int) -> None:
        raise interruption

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    control = ProviderExecutionControl()
    monkeypatch.setattr(control, "bind", _interrupt_bind)
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    caught: BaseException | None = None

    try:
        try:
            executor.execute(invocation, control=control)
        except BaseException as exc:
            caught = exc
        assert processes
        process = processes[0]
        process_cleaned_before_teardown = process.returncode is not None
        group_cleaned_before_teardown = False
        try:
            real_killpg(process.pid, 0)
        except ProcessLookupError:
            group_cleaned_before_teardown = True
    finally:
        for process in processes:
            if process.returncode is None:
                try:
                    real_killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert caught is interruption
    assert process_cleaned_before_teardown is True
    assert group_cleaned_before_teardown is True


def test_bind_rejection_cleanup_is_bounded_when_group_signals_fail(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    wait_timeouts: list[float | None] = []
    direct_terminate_seen = threading.Event()
    direct_kill_seen = threading.Event()
    ready_path = tmp_path / "bind-rejection-resistant.ready"

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        try:
            _wait_until(
                ready_path.exists,
                message="bind-rejection provider did not become ready",
            )
        except BaseException:
            real_killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
        real_wait = process.wait
        real_terminate = process.terminate
        real_kill = process.kill

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_timeouts.append(wait_kwargs.get("timeout"))
            return real_wait(*wait_args, **wait_kwargs)

        def _terminate() -> None:
            direct_terminate_seen.set()
            real_terminate()

        def _kill() -> None:
            direct_kill_seen.set()
            real_kill()

        process.wait = _wait  # type: ignore[method-assign]
        process.terminate = _terminate  # type: ignore[method-assign]
        process.kill = _kill  # type: ignore[method-assign]
        return process

    def _reject_bind(_process: subprocess.Popen, _pgid: int) -> None:
        raise RuntimeError("injected bounded bind rejection")

    def _fail_group_signals(pgid: int, sig: int) -> None:
        if sig == 0:
            real_killpg(pgid, sig)
            return
        raise PermissionError(f"injected group signal failure {sig}")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.executor.os.killpg",
        _fail_group_signals,
    )
    control = ProviderExecutionControl()
    monkeypatch.setattr(control, "bind", _reject_bind)
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, signal, time; "
            "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )

    try:
        execution_thread.join(timeout=1)
        cleanup_finished_automatically = not execution_thread.is_alive()
        if not cleanup_finished_automatically and processes:
            real_killpg(processes[0].pid, signal.SIGKILL)
        execution_result = _join_execution(execution_thread, execution_box)
    finally:
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert cleanup_finished_automatically is True
    assert direct_terminate_seen.is_set()
    assert direct_kill_seen.is_set()
    assert wait_timeouts
    assert all(timeout is not None for timeout in wait_timeouts)
    terminal = control.terminal_result
    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.term_sent is False
    assert terminal.kill_sent is False
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is True
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert "failed to terminate process group" in (terminal.error or "")
    assert "failed to kill process group" in (terminal.error or "")
    assert execution_result.classification == "failed"
    assert execution_result.exit_code != 0


def test_bind_failure_is_bound_before_pending_future_completion(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    bind_failure_recorded = threading.Event()
    release_execution = threading.Event()

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        return process

    def _reject_bind(_process: subprocess.Popen, _pgid: int) -> None:
        raise RuntimeError("injected bind rejection")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    control = ProviderExecutionControl()
    control._FINALIZATION_TIMEOUT_SEC = 0.05
    monkeypatch.setattr(control, "bind", _reject_bind)
    original_record_bind_failure = control.record_bind_failure

    def _pause_after_recording(**kwargs: Any) -> Any:
        result = original_record_bind_failure(**kwargs)
        bind_failure_recorded.set()
        assert release_execution.wait(timeout=5)
        return result

    monkeypatch.setattr(
        control,
        "record_bind_failure",
        _pause_after_recording,
    )
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "import time; time.sleep(30)"],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}

    def _cancel() -> None:
        try:
            cancellation_box["result"] = control.cancel_and_reap(grace=0.01)
        except BaseException as exc:
            cancellation_box["exception"] = exc

    cancellation_thread = threading.Thread(target=_cancel, daemon=True)

    try:
        assert bind_failure_recorded.wait(timeout=5)
        state_before_future_completion = control.state
        cancellation_thread.start()
        cancellation_thread.join(timeout=1)
        cancellation_returned_before_future = not cancellation_thread.is_alive()
        frozen_before_future = control.terminal_result

        release_execution.set()
        execution_result = _join_execution(execution_thread, execution_box)
        cancellation_thread.join(timeout=5)
    finally:
        release_execution.set()
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        if cancellation_thread.ident is not None:
            cancellation_thread.join(timeout=5)

    assert state_before_future_completion == "BOUND"
    assert cancellation_returned_before_future is True
    assert "exception" not in cancellation_box
    frozen = cancellation_box["result"]
    assert frozen is frozen_before_future
    assert frozen is control.terminal_result
    assert frozen.disposition == "boundary_failed"
    assert frozen.pgid == processes[0].pid
    assert frozen.leader_reaped is True
    assert frozen.pgid_empty is True
    assert frozen.execution_joined is False
    assert frozen.proof_complete is False
    assert execution_result.classification == "failed"
    assert control.cancel_and_reap(grace=0.01) is frozen


def test_bind_cleanup_does_not_read_pipes_while_group_remains_live(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    signal_attempts: list[int] = []
    direct_kill_seen = threading.Event()
    ready_path = tmp_path / "bind-live-group.ready"
    child_pid_path = tmp_path / "bind-live-group-child.pid"

    def _recording_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        try:
            _wait_until(
                ready_path.exists,
                message="bind cleanup provider did not become ready",
            )
        except BaseException:
            real_killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            raise
        real_kill = process.kill

        def _kill() -> None:
            direct_kill_seen.set()
            real_kill()

        process.kill = _kill  # type: ignore[method-assign]
        return process

    def _reject_bind(_process: subprocess.Popen, _pgid: int) -> None:
        raise RuntimeError("injected bind rejection with live group")

    def _fail_group_signals(pgid: int, sig: int) -> None:
        if sig == 0:
            real_killpg(pgid, sig)
            return
        signal_attempts.append(sig)
        raise PermissionError(f"injected group signal failure {sig}")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.executor.os.killpg",
        _fail_group_signals,
    )
    control = ProviderExecutionControl()
    monkeypatch.setattr(control, "bind", _reject_bind)
    child_script = (
        "import signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, signal, subprocess, sys, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"child = subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", parent_script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )

    try:
        execution_thread.join(timeout=5)
        returned_before_external_cleanup = not execution_thread.is_alive()
        if not returned_before_external_cleanup and processes:
            real_killpg(processes[0].pid, signal.SIGKILL)
        execution_result = _join_execution(execution_thread, execution_box)
    finally:
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert returned_before_external_cleanup is True
    assert direct_kill_seen.is_set()
    assert signal_attempts.count(signal.SIGTERM) == 1
    assert signal_attempts.count(signal.SIGKILL) == 1
    terminal = control.terminal_result
    assert terminal is not None
    assert terminal.disposition == "boundary_failed"
    assert terminal.leader_reaped is True
    assert terminal.pgid_empty is False
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert execution_result.classification == "failed"
    assert execution_result.exit_code != 0


def test_terminal_control_reuse_is_rejected_before_popen(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    control = ProviderExecutionControl()
    original_terminal = control.spawn_failed("first launch failed")
    popen_called = False

    def _unexpected_popen(*_args: Any, **_kwargs: Any) -> None:
        nonlocal popen_called
        popen_called = True
        raise RuntimeError("Popen must not run for a reused control")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _unexpected_popen,
    )
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
    )

    execution_result = executor.execute(invocation, control=control)

    assert popen_called is False
    assert execution_result.classification == "failed"
    assert execution_result.error is not None
    assert execution_result.error["type"] == "execution_error"
    assert control.terminal_result is original_terminal


@pytest.mark.parametrize(
    "failure_target",
    [
        (
            "orchestrator.providers.executor."
            "ProviderExecutor._expected_session_id"
        ),
        (
            "orchestrator.providers.executor."
            "create_session_transport_accumulator"
        ),
    ],
    ids=["expected-session", "session-codec"],
)
def test_pre_bind_setup_failure_terminalizes_without_waiting_for_bind(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
    failure_target: str,
) -> None:
    def _fail_codec_setup(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("codec setup failed")

    monkeypatch.setattr(failure_target, _fail_codec_setup)
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=(
            ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        ),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
    )

    execution_result = executor.execute(invocation, control=control)
    terminal = control.terminal_result

    assert execution_result.classification == "failed"
    assert control.state == "TERMINAL"
    assert terminal is not None
    assert terminal.disposition == "spawn_failed"
    assert terminal.pgid is None
    assert terminal.proof_complete is False
    assert control.cancel_and_reap(grace=0.01) is terminal


@pytest.mark.parametrize(
    "failure_target",
    [
        (
            "orchestrator.providers.executor."
            "ProviderExecutor._expected_session_id"
        ),
        (
            "orchestrator.providers.executor."
            "create_session_transport_accumulator"
        ),
    ],
    ids=["expected-session", "session-codec"],
)
def test_pre_spawn_baseexception_terminalizes_then_reraises(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
    failure_target: str,
) -> None:
    class Abort(BaseException):
        pass

    abort = Abort("setup aborted")

    def _abort_setup(*_args: Any, **_kwargs: Any) -> None:
        raise abort

    monkeypatch.setattr(failure_target, _abort_setup)
    popen_called = False

    def _unexpected_popen(*_args: Any, **_kwargs: Any) -> None:
        nonlocal popen_called
        popen_called = True
        raise AssertionError("setup failure reached process creation")

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _unexpected_popen,
    )
    control = ProviderExecutionControl()
    completion: Future[Any] = Future()
    assert completion.set_running_or_notify_cancel() is True
    control.attach_execution_future(completion)
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
    )

    with pytest.raises(Abort) as caught:
        try:
            executor.execute(invocation, control=control)
        except BaseException as exc:
            completion.set_exception(exc)
            raise

    terminal = control.terminal_result
    assert caught.value is abort
    assert completion.exception() is abort
    assert popen_called is False
    assert terminal is not None
    assert terminal.disposition == "spawn_failed"
    assert terminal.execution_joined is True
    assert terminal.proof_complete is False
    assert control.cancel_and_reap(grace=0.01) is terminal


def test_cancel_waits_until_the_attached_execution_future_is_done(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    ready_path = tmp_path / "ready"
    completion: Future[Any] = Future()
    control = ProviderExecutionControl()
    control.attach_execution_future(completion)
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, time; "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_returned = threading.Event()
    release_future = threading.Event()
    execution_box: dict[str, Any] = {}

    def _run() -> None:
        result = executor.execute(invocation, control=control)
        execution_box["result"] = result
        execution_returned.set()
        assert release_future.wait(timeout=5)
        completion.set_result(result)

    execution_thread = threading.Thread(target=_run, daemon=True)
    execution_thread.start()
    _wait_until(ready_path.exists, message="provider did not become ready")
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    cancellation_thread.start()

    assert execution_returned.wait(timeout=5)
    time.sleep(0.05)
    assert cancellation_thread.is_alive()
    assert control.terminal_result is None

    release_future.set()
    cancellation_thread.join(timeout=5)
    execution_thread.join(timeout=5)

    assert not cancellation_thread.is_alive()
    assert not execution_thread.is_alive()
    terminal = cancellation_box["result"]
    assert terminal.execution_joined is True
    assert terminal.proof_complete is True


def test_only_the_executor_thread_calls_controlled_popen_wait(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    wait_thread_ids: list[int] = []
    ready_path = tmp_path / "ready"

    def _recording_wait_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_thread_ids.append(threading.get_ident())
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _recording_wait_popen,
    )
    completion: Future[Any] = Future()
    control = ProviderExecutionControl()
    control.attach_execution_future(completion)
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, time; "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            "time.sleep(30)",
        ],
        input_mode=InputMode.ARGV,
    )
    result_box: dict[str, Any] = {}

    def _run() -> None:
        result = executor.execute(invocation, control=control)
        result_box["result"] = result
        completion.set_result(result)

    execution_thread = threading.Thread(target=_run, daemon=True)
    execution_thread.start()
    _wait_until(ready_path.exists, message="provider did not become ready")

    terminal = control.cancel_and_reap(grace=0.1)
    execution_thread.join(timeout=5)

    assert terminal.proof_complete is True
    assert not execution_thread.is_alive()
    assert wait_thread_ids
    assert set(wait_thread_ids) == {execution_thread.ident}
    assert threading.get_ident() not in wait_thread_ids


def test_execution_future_attachment_is_one_shot() -> None:
    control = ProviderExecutionControl()
    first: Future[Any] = Future()
    second: Future[Any] = Future()

    control.attach_execution_future(first)

    with pytest.raises(RuntimeError, match="already attached"):
        control.attach_execution_future(second)


def test_missing_execution_future_fails_the_terminal_proof(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ProviderExecutionControl,
        "_FINALIZATION_TIMEOUT_SEC",
        0.05,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "pass"],
        input_mode=InputMode.ARGV,
    )

    execution_result = executor.execute(invocation, control=control)
    terminal = control.cancel_and_reap(grace=0.01)

    assert execution_result.classification == "normal"
    assert terminal.disposition == "boundary_failed"
    assert terminal.execution_joined is False
    assert terminal.proof_complete is False
    assert terminal.error is not None
    assert "future" in terminal.error


def test_cancel_after_wait_return_cannot_rehabilitate_a_lingering_child(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    wait_returned = threading.Event()
    release_wait = threading.Event()
    child_pid_path = tmp_path / "racing-child.pid"

    def _delayed_wait_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            return_code = real_wait(*wait_args, **wait_kwargs)
            wait_returned.set()
            assert release_wait.wait(timeout=5)
            return return_code

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _delayed_wait_popen,
    )
    script = (
        "import pathlib, subprocess, sys; "
        "child = subprocess.Popen([sys.executable, '-c', "
        "'import time; time.sleep(30)']); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid))"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert wait_returned.wait(timeout=5)
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="cancellation did not latch after leader wait",
    )
    release_wait.set()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    terminal = cancellation_box["result"]
    _wait_until(
        lambda: not _pid_is_running(child_pid),
        message="racing lingering child was not cleaned",
    )

    assert terminal.disposition == "boundary_failed"
    assert terminal.natural_exit_with_lingering_group is True
    assert terminal.proof_complete is False
    assert execution_result.classification == "failed"


def test_repeated_cancel_preserves_cancel_before_clean_exit_with_child(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    wait_returned = threading.Event()
    release_wait = threading.Event()
    kill_seen = threading.Event()
    child_pid_path = tmp_path / "cancelled-child.pid"
    child_ready_path = tmp_path / "cancelled-child.ready"
    parent_ready_path = tmp_path / "cancelled-parent.ready"

    def _delayed_wait_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            return_code = real_wait(*wait_args, **wait_kwargs)
            wait_returned.set()
            assert release_wait.wait(timeout=5)
            return return_code

        process.wait = _wait  # type: ignore[method-assign]
        return process

    def _recording_killpg(pgid: int, sig: int) -> None:
        if sig == signal.SIGKILL:
            kill_seen.set()
        real_killpg(pgid, sig)

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _delayed_wait_popen,
    )
    monkeypatch.setattr(
        "orchestrator.providers.control.os.killpg",
        _recording_killpg,
    )
    child_script = (
        "import pathlib, signal, time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        f"pathlib.Path({str(child_ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    parent_script = (
        "import pathlib, signal, subprocess, sys, time; "
        f"child = subprocess.Popen([sys.executable, '-c', {child_script!r}]); "
        f"pathlib.Path({str(child_pid_path)!r}).write_text(str(child.pid)); "
        "signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)); "
        f"pathlib.Path({str(parent_ready_path)!r}).write_text('ready'); "
        "\nwhile True: time.sleep(0.05)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", parent_script],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(parent_ready_path.exists, message="parent did not become ready")
    _wait_until(child_ready_path.exists, message="child did not become ready")
    child_pid = int(child_pid_path.read_text(encoding="utf-8"))

    cancellation_results: list[Any] = []

    def _cancel() -> None:
        cancellation_results.append(control.cancel_and_reap(grace=0.05))

    first_cancel = threading.Thread(target=_cancel, daemon=True)
    first_cancel.start()
    assert wait_returned.wait(timeout=5)
    second_cancel = threading.Thread(target=_cancel, daemon=True)
    second_cancel.start()
    release_wait.set()
    assert kill_seen.wait(timeout=5)

    execution_result = _join_execution(execution_thread, execution_box)
    first_cancel.join(timeout=5)
    second_cancel.join(timeout=5)
    assert not first_cancel.is_alive()
    assert not second_cancel.is_alive()
    _wait_until(
        lambda: not _pid_is_running(child_pid),
        message="cancelled same-PGID child survived cleanup",
    )

    assert len(cancellation_results) == 2
    assert cancellation_results[1] is cancellation_results[0]
    terminal = cancellation_results[0]
    assert terminal.disposition == "cancelled"
    assert terminal.leader_return_code == 0
    assert terminal.natural_exit_with_lingering_group is False
    assert terminal.pgid_empty is True
    assert terminal.term_sent is True
    assert terminal.kill_sent is True
    assert terminal.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"


def test_cancel_after_natural_nonzero_wait_preserves_failure_disposition(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    wait_returned = threading.Event()
    release_wait = threading.Event()

    def _delayed_wait_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            return_code = real_wait(*wait_args, **wait_kwargs)
            wait_returned.set()
            assert release_wait.wait(timeout=5)
            return return_code

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _delayed_wait_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", "raise SystemExit(7)"],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert wait_returned.wait(timeout=5)

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.1),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="cancellation did not latch after natural nonzero wait",
    )
    release_wait.set()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]

    assert terminal.disposition == "natural_exit"
    assert terminal.leader_return_code == 7
    assert terminal.proof_complete is True
    assert execution_result.exit_code == 7
    assert execution_result.classification == "failed"


@_requires_proc_stat
def test_unreaped_natural_nonzero_exit_cannot_become_cancellation(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    incomplete_probe = threading.Event()
    release_probe = threading.Event()
    ready_path = tmp_path / "natural-nonzero-ready"
    exit_path = tmp_path / "natural-nonzero-exit"

    def _blocked_before_wait_popen(
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait
        first_zero_probe = True

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            nonlocal first_zero_probe
            if first_zero_probe and wait_kwargs.get("timeout") == 0:
                first_zero_probe = False
                try:
                    return real_wait(*wait_args, **wait_kwargs)
                except subprocess.TimeoutExpired:
                    incomplete_probe.set()
                    assert release_probe.wait(timeout=5)
                    raise
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _blocked_before_wait_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, time; "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            f"exit_path = pathlib.Path({str(exit_path)!r}); "
            "\nwhile not exit_path.exists(): time.sleep(0.005); "
            "\nraise SystemExit(7)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )

    try:
        _wait_until(ready_path.exists, message="provider did not become ready")
        assert incomplete_probe.wait(timeout=5)
        exit_path.write_text("exit", encoding="utf-8")
        process = processes[0]
        _wait_until(
            lambda: _pid_state(process.pid) == "Z",
            message="provider leader did not become an unreaped zombie",
        )
        assert process.returncode is None
        assert control.cancellation_requested is False

        cancellation_thread.start()
        _wait_until(
            lambda: control.cancellation_requested,
            message="cancellation did not latch for unreaped leader",
        )
        release_probe.set()

        execution_result = _join_execution(execution_thread, execution_box)
        cancellation_thread.join(timeout=5)
    finally:
        release_probe.set()
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()

    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]

    assert terminal.disposition == "natural_exit"
    assert terminal.leader_return_code == 7
    assert terminal.proof_complete is True
    assert execution_result.exit_code == 7
    assert execution_result.classification == "failed"


@_requires_proc_stat
def test_cancellation_after_live_probe_rechecks_before_bounded_wait(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    real_killpg = os.killpg
    processes: list[subprocess.Popen] = []
    first_probe_completed = threading.Event()
    release_first_probe = threading.Event()
    post_cancel_probe_completed = threading.Event()
    bounded_wait_entered = threading.Event()
    release_after_exit = threading.Event()
    ready_path = tmp_path / "inverse-causal-ready"
    exit_path = tmp_path / "inverse-causal-exit"

    def _held_completed_probe_popen(
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait
        zero_probe_count = 0

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            nonlocal zero_probe_count
            if wait_kwargs.get("timeout") == 0:
                zero_probe_count += 1
                try:
                    return real_wait(*wait_args, **wait_kwargs)
                except subprocess.TimeoutExpired:
                    if zero_probe_count == 1:
                        first_probe_completed.set()
                        assert release_first_probe.wait(timeout=5)
                    else:
                        post_cancel_probe_completed.set()
                        assert release_after_exit.wait(timeout=5)
                    raise

            bounded_wait_entered.set()
            assert release_after_exit.wait(timeout=5)
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _held_completed_probe_popen,
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            "import pathlib, time; "
            f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
            f"exit_path = pathlib.Path({str(exit_path)!r}); "
            "\nwhile not exit_path.exists(): time.sleep(0.005); "
            "\nraise SystemExit(7)",
        ],
        input_mode=InputMode.ARGV,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )

    try:
        _wait_until(ready_path.exists, message="provider did not become ready")
        assert first_probe_completed.wait(timeout=5)
        cancellation_thread.start()
        _wait_until(
            lambda: control.cancellation_requested,
            message="cancellation did not latch after the live probe",
        )
        release_first_probe.set()
        _wait_until(
            lambda: (
                post_cancel_probe_completed.is_set()
                or bounded_wait_entered.is_set()
            ),
            message="executor selected neither causal wait path",
        )

        exit_path.write_text("exit", encoding="utf-8")
        process = processes[0]
        _wait_until(
            lambda: _pid_state(process.pid) == "Z",
            message="provider leader did not become an unreaped zombie",
        )
        release_after_exit.set()

        execution_result = _join_execution(execution_thread, execution_box)
        cancellation_thread.join(timeout=5)
    finally:
        release_first_probe.set()
        release_after_exit.set()
        for process in processes:
            try:
                real_killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            if process.returncode is None:
                process.wait(timeout=5)
            for pipe in (process.stdin, process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
        if cancellation_thread.ident is not None:
            cancellation_thread.join(timeout=5)

    assert post_cancel_probe_completed.is_set()
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]
    assert terminal.disposition == "cancelled"
    assert terminal.leader_return_code == 7
    assert terminal.proof_complete is True
    assert execution_result.exit_code == 7
    assert execution_result.classification == "cancelled_provisional"


@_requires_proc_stat
def test_natural_sigusr1_before_delayed_reap_beats_later_cancellation(
    executor: ProviderExecutor,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []
    bounded_wait_entered = threading.Event()
    allow_reap = threading.Event()
    ready_path = tmp_path / "sigusr1-ready"
    exit_path = tmp_path / "sigusr1-exit"

    def _delayed_reap_popen(*args: Any, **kwargs: Any) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            timeout = wait_kwargs.get("timeout")
            if timeout == 0:
                return real_wait(*wait_args, **wait_kwargs)
            bounded_wait_entered.set()
            assert allow_reap.wait(timeout=5)
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _delayed_reap_popen,
    )
    script = (
        "import os, pathlib, signal, time; "
        f"ready = pathlib.Path({str(ready_path)!r}); "
        f"exit_path = pathlib.Path({str(exit_path)!r}); "
        "ready.write_text('ready'); "
        "\nwhile not exit_path.exists(): time.sleep(0.005); "
        "\nos.kill(os.getpid(), signal.SIGUSR1)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.ARGV,
        timeout_sec=None,
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    _wait_until(ready_path.exists, message="provider did not become ready")
    assert bounded_wait_entered.wait(timeout=5)
    exit_path.write_text("exit", encoding="utf-8")
    process = processes[0]
    _wait_until(
        lambda: _pid_state(process.pid) == "Z",
        message="SIGUSR1 provider did not become an unreaped zombie",
    )
    assert process.returncode is None

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="cancellation did not latch after SIGUSR1 exit",
    )
    allow_reap.set()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]

    assert terminal.disposition == "natural_exit"
    assert terminal.leader_return_code == -signal.SIGUSR1
    assert terminal.proof_complete is True
    assert execution_result.exit_code == -signal.SIGUSR1
    assert execution_result.classification == "failed"


@_requires_proc_stat
def test_completed_transport_failure_before_unreaped_wait_beats_cancellation(
    executor: ProviderExecutor,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_popen = subprocess.Popen
    processes: list[subprocess.Popen] = []
    wait_entered = threading.Event()
    allow_wait = threading.Event()
    stdout_captured = threading.Event()

    def _blocked_before_wait_popen(
        *args: Any,
        **kwargs: Any,
    ) -> subprocess.Popen:
        process = real_popen(*args, **kwargs)
        processes.append(process)
        real_wait = process.wait

        def _wait(*wait_args: Any, **wait_kwargs: Any) -> int:
            wait_entered.set()
            assert allow_wait.wait(timeout=5)
            return real_wait(*wait_args, **wait_kwargs)

        process.wait = _wait  # type: ignore[method-assign]
        return process

    monkeypatch.setattr(
        "orchestrator.providers.executor.subprocess.Popen",
        _blocked_before_wait_popen,
    )
    identity_line = (
        '{"type":"thread.started","thread_id":"session-natural"}\n'
    )
    control = ProviderExecutionControl()
    record_missing_terminal = (
        control.record_missing_terminal_at_session_stdout_eof
    )

    def _observed_missing_terminal(
        snapshot: Any,
    ) -> None:
        record_missing_terminal(snapshot)
        stdout_captured.set()

    monkeypatch.setattr(
        control,
        "record_missing_terminal_at_session_stdout_eof",
        _observed_missing_terminal,
    )
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            f"import sys; sys.stdout.write({identity_line!r}); sys.stdout.flush()",
        ],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=(
            ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        ),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
    )
    execution_thread, execution_box = _start_execution(
        executor,
        invocation,
        control,
    )
    assert wait_entered.wait(timeout=5)
    process = processes[0]
    _wait_until(
        lambda: _pid_state(process.pid) == "Z",
        message="provider leader did not become an unreaped zombie",
    )
    assert stdout_captured.wait(timeout=5)
    assert process.returncode is None

    cancellation_box: dict[str, Any] = {}
    cancellation_thread = threading.Thread(
        target=lambda: cancellation_box.setdefault(
            "result",
            control.cancel_and_reap(grace=0.01),
        ),
        daemon=True,
    )
    cancellation_thread.start()
    _wait_until(
        lambda: control.cancellation_requested,
        message="cancellation did not latch after completed transport",
    )
    allow_wait.set()

    execution_result = _join_execution(execution_thread, execution_box)
    cancellation_thread.join(timeout=5)
    assert not cancellation_thread.is_alive()
    terminal = cancellation_box["result"]

    assert terminal.disposition == "natural_exit"
    assert terminal.proof_complete is True
    assert execution_result.classification == "failed"
    assert execution_result.raw_stdout == identity_line.encode("utf-8")
    assert execution_result.error is not None
    assert execution_result.error["type"] == "provider_session_transport_error"


def test_spool_failure_cannot_suppress_preterminal_identity_publication(
    executor: ProviderExecutor,
    tmp_path: Path,
) -> None:
    invalid_parent = tmp_path / "not-a-directory"
    invalid_parent.write_text("file", encoding="utf-8")
    spool_path = invalid_parent / "transport.log"
    ready_path = tmp_path / "ready"
    identity_line = (
        '{"type":"thread.started","thread_id":"session-123"}\n'
    )
    script = (
        "import pathlib, sys, time; "
        f"sys.stdout.write({identity_line!r}); sys.stdout.flush(); "
        f"pathlib.Path({str(ready_path)!r}).write_text('ready'); "
        "time.sleep(30)"
    )
    control = ProviderExecutionControl()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=(
            ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value
        ),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.FRESH,
        ),
    )
    execution_thread, result_box = _start_execution(
        executor,
        invocation,
        control,
        session_runtime={"transport_spool_path": spool_path},
    )
    _wait_until(ready_path.exists, message="session provider did not become ready")

    try:
        _wait_until(
            lambda: control.session_snapshot is not None
            and control.session_snapshot.status == "unique",
            timeout=0.5,
            message="spool failure suppressed preterminal identity",
        )
    finally:
        terminal = control.cancel_and_reap(grace=0.1)
    execution_result = _join_execution(execution_thread, result_box)

    assert terminal.final_identity_valid is True
    assert terminal.proof_complete is True
    assert execution_result.classification == "cancelled_provisional"
    assert execution_result.raw_stdout == identity_line.encode("utf-8")
    assert execution_result.normalized_stdout is None
    assert execution_result.provider_session is None
