"""Contract tests for generic cancellable provider execution."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import Future
from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any, Callable

import pytest

from orchestrator.providers import (
    InputMode,
    ProviderExecutionControl,
    ProviderExecutor,
    ProviderInvocation,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
)


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
    stat_path = Path(f"/proc/{pid}/stat")
    try:
        fields = stat_path.read_text(encoding="utf-8").split()
    except FileNotFoundError:
        return False
    if len(fields) >= 3 and fields[2] == "Z":
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def _start_execution(
    executor: ProviderExecutor,
    invocation: ProviderInvocation,
    control: ProviderExecutionControl,
    *,
    session_runtime: dict[str, Any] | None = None,
) -> tuple[threading.Thread, dict[str, Any]]:
    result_box: dict[str, Any] = {}
    completion: Future[Any] = Future()
    control.attach_execution_future(completion)

    def _run() -> None:
        try:
            result = executor.execute(
                invocation,
                control=control,
                session_runtime=session_runtime,
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
        execution_thread.join(timeout=5)

    assert terminal.final_identity_valid is True
    assert not execution_thread.is_alive()
