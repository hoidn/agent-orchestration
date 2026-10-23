"""Provider-execution parity tests for observation-only display mirroring."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers import (
    InputMode,
    ProviderExecutionControl,
    ProviderExecutor,
    ProviderInvocation,
    ProviderObservationError,
    ProviderRegistry,
    ProviderSessionMetadataMode,
    ProviderSessionMode,
    ProviderSessionRequest,
)


class _BinaryRecorder:
    def __init__(self) -> None:
        self.buffer = self
        self._chunks: list[bytes] = []
        self._lock = threading.Lock()

    def write(self, data: bytes | str) -> int:
        encoded = data.encode("utf-8") if isinstance(data, str) else bytes(data)
        with self._lock:
            self._chunks.append(encoded)
        return len(encoded)

    def flush(self) -> None:
        return None

    def getvalue(self) -> bytes:
        with self._lock:
            return b"".join(self._chunks)


class _RecordingHandle:
    def __init__(
        self,
        *,
        append_failure: BaseException | None = None,
        health_failure: BaseException | None = None,
        finalize_failure: BaseException | None = None,
    ) -> None:
        self.append_failure = append_failure
        self.health_failure = health_failure
        self.finalize_failure = finalize_failure
        self.display_chunks: list[bytes] = []
        self.health_calls = 0
        self.finalize_calls = 0
        self.first_append = threading.Event()

    def append_display(self, data: bytes) -> None:
        self.display_chunks.append(bytes(data))
        self.first_append.set()
        if self.append_failure is not None:
            raise self.append_failure

    def check_health(self) -> bool:
        self.health_calls += 1
        if self.health_failure is not None:
            raise self.health_failure
        return True

    def finalize(self) -> dict[str, object]:
        self.finalize_calls += 1
        if self.finalize_failure is not None:
            raise self.finalize_failure
        return {"status": "finalized"}


class _RecordingManager:
    def __init__(
        self,
        handle: _RecordingHandle | None = None,
        *,
        open_failure: BaseException | None = None,
    ) -> None:
        self.handle = handle or _RecordingHandle()
        self.open_failure = open_failure
        self.open_calls: list[dict[str, str]] = []
        self.invocation_index = 0

    def next_invocation_id(self) -> str:
        self.invocation_index += 1
        return f"provider-invocation-{self.invocation_index:06d}"

    def open_observation(self, **identity: str) -> _RecordingHandle:
        self.open_calls.append(dict(identity))
        if self.open_failure is not None:
            raise self.open_failure
        return self.handle


def _executor(
    tmp_path: Path,
    *,
    enabled: bool,
    manager: _RecordingManager,
) -> ProviderExecutor:
    return ProviderExecutor(
        tmp_path,
        ProviderRegistry(),
        None,
        provider_observation_enabled=enabled,
        observation_manager=manager,
    )


def _ordinary_invocation(
    *,
    stdout: str = "ordinary-out",
    stderr: str = "ordinary-err",
    timeout_sec: float | None = None,
    sleep_sec: float | None = None,
) -> ProviderInvocation:
    sleep = f"time.sleep({sleep_sec}); " if sleep_sec is not None else ""
    script = (
        "import sys, time; "
        f"sys.stdout.write({stdout!r}); sys.stdout.flush(); "
        f"sys.stderr.write({stderr!r}); sys.stderr.flush(); "
        f"{sleep}"
    )
    return ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        timeout_sec=timeout_sec,
    )


def _session_invocation() -> tuple[ProviderInvocation, bytes]:
    raw = (
        '{"type":"thread.started","thread_id":"thread-observed"}\n'
        '{"type":"turn.started"}\n'
        '{"type":"item.completed","item":{"type":"agent_message","text":"hello"}}\n'
        '{"type":"turn.completed"}\n'
    ).encode("utf-8")
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            f"import sys; sys.stdout.buffer.write({raw!r}); sys.stdout.flush()",
        ],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )
    return invocation, raw


def _tool_invocation(
    raw: bytes,
    *,
    session_request=None,
    metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
) -> ProviderInvocation:
    return ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            f"import sys; sys.stdout.buffer.write({raw!r}); sys.stdout.flush()",
        ],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=metadata_mode,
        session_request=session_request
        or ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )


def _codex_tool_events(*, thread_id="tool-thread", command="PRIVATE COMMAND") -> bytes:
    rows = (
        {"type": "thread.started", "thread_id": thread_id},
        {"type": "turn.started"},
        {"type": "item.started", "item": {"type": "command_execution", "id": "tool-1", "command": command}},
        {"type": "item.completed", "item": {"type": "command_execution", "id": "tool-1", "exit_code": 0, "aggregated_output": "PRIVATE RESULT"}},
        {"type": "turn.completed"},
    )
    return b"".join(json.dumps(row).encode() + b"\n" for row in rows)


def test_provider_executor_enables_ordinary_observation_by_default(
    tmp_path: Path,
) -> None:
    manager = _RecordingManager()
    executor = ProviderExecutor(
        tmp_path,
        ProviderRegistry(),
        None,
        observation_manager=manager,
    )

    result = executor.execute(_ordinary_invocation())

    assert executor.provider_observation_enabled is True
    assert result.exit_code == 0
    assert len(manager.open_calls) == 1


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_preserves_ordinary_nonstream_result(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()
    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        _ordinary_invocation()
    )

    assert result.exit_code == 0
    assert result.stdout == b"ordinary-out"
    assert result.stderr == b"ordinary-err"
    assert result.error is None
    assert not any("observation" in key for key in vars(result))
    if enabled:
        assert manager.handle.display_chunks == [b"ordinary-out"]
        assert manager.handle.health_calls >= 1
        assert manager.handle.finalize_calls == 1
    else:
        assert manager.open_calls == []
        assert manager.handle.display_chunks == []
        assert manager.handle.health_calls == 0
        assert manager.handle.finalize_calls == 0


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_preserves_ordinary_stream_result(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()
    stdout = _BinaryRecorder()
    stderr = _BinaryRecorder()

    with patch("sys.stdout", stdout), patch("sys.stderr", stderr):
        result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
            _ordinary_invocation(),
            stream_output=True,
        )

    assert result.exit_code == 0
    assert result.stdout == b"ordinary-out"
    assert result.stderr == b"ordinary-err"
    assert stdout.getvalue() == b"ordinary-out"
    assert stderr.getvalue() == b"ordinary-err"
    assert manager.handle.display_chunks == (
        [b"ordinary-out"] if enabled else []
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_preserves_session_result_and_displays_only_normalized_text(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()
    invocation, raw = _session_invocation()

    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        invocation
    )

    assert result.exit_code == 0
    assert result.stdout == b"hello"
    assert result.raw_stdout == raw
    assert result.normalized_stdout == b"hello"
    assert result.provider_session == {
        "session_id": "thread-observed",
        "normalized_stdout": "hello",
        "event_count": 4,
        "turns_completed": 1,
    }
    assert manager.handle.display_chunks == ([b"hello"] if enabled else [])
    assert raw not in manager.handle.display_chunks


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_preserves_controlled_session_transport_and_normalization(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()
    invocation, raw = _session_invocation()

    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        invocation,
        control=ProviderExecutionControl(),
    )

    assert result.exit_code == 0
    assert result.stdout == b"hello"
    assert result.raw_stdout == raw
    assert result.normalized_stdout == b"hello"
    assert result.classification == "normal"
    assert manager.handle.display_chunks == ([b"hello"] if enabled else [])
    assert raw not in manager.handle.display_chunks


def test_tool_activity_reaches_observation_before_the_child_exits(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "activity-seen"
    exited = tmp_path / "child-exited"
    prefix = b"\n".join(
        (
            json.dumps({"type": "thread.started", "thread_id": "tool-thread"}).encode(),
            json.dumps({"type": "turn.started"}).encode(),
            json.dumps({"type": "item.started", "item": {"type": "command_execution", "id": "tool-1", "command": "PRIVATE COMMAND"}}).encode(),
            b"",
        )
    )
    suffix = b"\n".join(
        (
            json.dumps({"type": "item.completed", "item": {"type": "command_execution", "id": "tool-1", "exit_code": 0, "aggregated_output": "PRIVATE RESULT"}}).encode(),
            json.dumps({"type": "turn.completed"}).encode(),
            b"",
        )
    )

    class _SignalHandle(_RecordingHandle):
        def append_display(self, data: bytes) -> None:
            super().append_display(data)
            if data.startswith(b"Tool started:"):
                marker.write_text("seen", encoding="utf-8")

    script = (
        "from pathlib import Path\nimport sys, time\n"
        f"marker = Path({str(marker)!r})\n"
        f"sys.stdout.buffer.write({prefix!r}); sys.stdout.buffer.flush()\n"
        "deadline = time.monotonic() + 2\n"
        "while time.monotonic() < deadline and not marker.exists(): time.sleep(0.01)\n"
        f"Path({str(exited)!r}).write_text('before-exit' if marker.exists() else 'missing', encoding='utf-8')\n"
        "if not marker.exists(): sys.exit(23)\n"
        f"sys.stdout.buffer.write({suffix!r}); sys.stdout.buffer.flush()\n"
    )
    manager = _RecordingManager(handle=_SignalHandle())
    stdout = _BinaryRecorder()
    invocation = ProviderInvocation(
        command=[sys.executable, "-c", script],
        input_mode=InputMode.STDIN,
        command_variant="fresh_command",
        metadata_mode=ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value,
        session_request=ProviderSessionRequest(mode=ProviderSessionMode.FRESH),
    )

    with patch("sys.stdout", stdout):
        result = _executor(tmp_path, enabled=True, manager=manager).execute(
            invocation, stream_output=True
        )

    assert result.exit_code == 0
    assert exited.read_text(encoding="utf-8") == "before-exit"
    assert b"Tool started: command execution\n" in manager.handle.display_chunks[0]
    assert b"Tool completed: command execution\n" in manager.handle.display_chunks[-1]
    assert b"PRIVATE" not in b"".join(manager.handle.display_chunks)
    assert b"Tool started: command execution\n" in stdout.getvalue()
    assert result.normalized_stdout == b""


@pytest.mark.parametrize("failed_sink", ["console", "observation"])
def test_tool_activity_sinks_fail_independently(
    tmp_path: Path, failed_sink: str
) -> None:
    manager = _RecordingManager(
        handle=_RecordingHandle(
            append_failure=RuntimeError("observation failed")
            if failed_sink == "observation"
            else None
        )
    )

    class _FailingConsole:
        buffer = None

        def __init__(self) -> None:
            self.buffer = self

        def write(self, _data):
            raise RuntimeError("console failed")

        def flush(self):
            return None

    stdout = _BinaryRecorder() if failed_sink == "observation" else _FailingConsole()
    with patch("sys.stdout", stdout):
        result = _executor(tmp_path, enabled=True, manager=manager).execute(
            _tool_invocation(_codex_tool_events()), stream_output=True
        )

    assert result.exit_code == 0
    if failed_sink == "console":
        assert b"Tool started: command execution" in b"".join(manager.handle.display_chunks)
    else:
        assert b"Tool started: command execution" in stdout.getvalue()


def test_identity_mismatch_blocks_tool_activity_from_both_sinks(tmp_path: Path) -> None:
    manager = _RecordingManager()
    stdout = _BinaryRecorder()
    invocation = _tool_invocation(
        _codex_tool_events(thread_id="actual-thread"),
        session_request=ProviderSessionRequest(
            mode=ProviderSessionMode.RESUME, session_id="expected-thread"
        ),
    )

    with patch("sys.stdout", stdout):
        _executor(tmp_path, enabled=True, manager=manager).execute(
            invocation, stream_output=True
        )

    assert manager.handle.display_chunks == []
    assert stdout.getvalue() == b""


def test_claude_activity_is_single_line_bounded_and_terminal_safe(tmp_path: Path) -> None:
    manager = _RecordingManager()
    stdout = _BinaryRecorder()
    sid = "1930ae6b-5267-4eec-b1e1-b430dad86844"
    name = "\x1b[31mBash\nINJECTED" + "\ud800" + "x" * 300
    raw = b"".join(
        json.dumps(row, ensure_ascii=True).encode() + b"\n"
        for row in (
            {"type": "system", "subtype": "init", "session_id": sid},
            {"type": "assistant", "session_id": sid, "message": {"content": [{"type": "tool_use", "id": "t1", "name": name, "input": {"command": "PRIVATE ARGUMENT"}}]}},
            {"type": "user", "session_id": sid, "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": "PRIVATE RESULT"}]}},
            {"type": "result", "session_id": sid, "subtype": "success", "is_error": False},
        )
    )

    with patch("sys.stdout", stdout):
        result = _executor(tmp_path, enabled=True, manager=manager).execute(
            _tool_invocation(
                raw,
                metadata_mode=ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value,
            ),
            stream_output=True,
        )

    display = b"".join(manager.handle.display_chunks)
    assert result.exit_code == 0 and result.normalized_stdout == b""
    assert b"\x1b" not in display and display.count(b"\n") == 2
    assert b"\\nINJECTED" in display and b"\\ud800" in display
    assert len(max(display.splitlines(), key=len)) < 200
    assert b"PRIVATE" not in display and display == stdout.getvalue()


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_preserves_timeout_result(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()

    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        _ordinary_invocation(
            stdout="partial",
            stderr="timeout-err",
            timeout_sec=0.1,
            sleep_sec=2.0,
        )
    )

    assert result.exit_code == 124
    assert result.stdout == b"partial"
    assert result.stderr == b"timeout-err"
    assert result.error is not None
    assert result.error["type"] == "timeout"
    assert manager.handle.display_chunks == ([b"partial"] if enabled else [])


@pytest.mark.parametrize("enabled", [False, True])
def test_observed_nonstream_timeout_is_not_blocked_by_unread_large_stdin(
    tmp_path: Path,
    enabled: bool,
) -> None:
    manager = _RecordingManager()
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            (
                "import sys, time; "
                "sys.stdout.write('partial'); sys.stdout.flush(); "
                "time.sleep(1)"
            ),
        ],
        input_mode=InputMode.STDIN,
        prompt="x" * (2 * 1024 * 1024),
        timeout_sec=0.1,
    )

    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        invocation
    )

    assert result.exit_code == 124
    assert result.stdout == b"partial"
    assert result.stderr == b""
    assert result.error is not None
    assert result.error["type"] == "timeout"
    assert manager.handle.display_chunks == ([b"partial"] if enabled else [])


def test_automatic_observation_uses_deterministic_generic_identities(
    tmp_path: Path,
) -> None:
    manager = _RecordingManager()
    executor = _executor(tmp_path, enabled=True, manager=manager)

    executor.execute(_ordinary_invocation(stdout="one", stderr=""))
    executor.execute(_ordinary_invocation(stdout="two", stderr=""))

    assert manager.open_calls == [
        {
            "invocation_id": "provider-invocation-000001",
            "member_id": "ordinary",
            "turn_id": "turn-1",
        },
        {
            "invocation_id": "provider-invocation-000002",
            "member_id": "ordinary",
            "turn_id": "turn-1",
        },
    ]


def test_shared_manager_allocates_unique_identities_across_executors(
    tmp_path: Path,
) -> None:
    manager = _RecordingManager()
    first = _executor(tmp_path, enabled=True, manager=manager)
    second = _executor(tmp_path, enabled=True, manager=manager)

    first.execute(_ordinary_invocation(stdout="one", stderr=""))
    second.execute(_ordinary_invocation(stdout="two", stderr=""))

    assert [
        call["invocation_id"]
        for call in manager.open_calls
    ] == [
        "provider-invocation-000001",
        "provider-invocation-000002",
    ]


def test_enabled_nonstream_observation_appends_before_provider_exit(
    tmp_path: Path,
) -> None:
    manager = _RecordingManager()
    executor = _executor(tmp_path, enabled=True, manager=manager)
    release_path = tmp_path / "release-provider"
    invocation = ProviderInvocation(
        command=[
            sys.executable,
            "-c",
            (
                "import pathlib, sys, time\n"
                "sys.stdout.write('first')\n"
                "sys.stdout.flush()\n"
                f"release = pathlib.Path({str(release_path)!r})\n"
                "while not release.exists():\n"
                "    time.sleep(0.01)\n"
            ),
        ],
        input_mode=InputMode.STDIN,
    )
    result_box: dict[str, object] = {}
    worker = threading.Thread(
        target=lambda: result_box.setdefault(
            "result",
            executor.execute(invocation),
        ),
        daemon=True,
    )

    worker.start()

    try:
        assert manager.handle.first_append.wait(timeout=3)
        assert worker.is_alive()
    finally:
        release_path.touch()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert result_box["result"].exit_code == 0


@pytest.mark.parametrize(
    ("failure_site", "failure"),
    [
        ("allocation", ProviderObservationError("pane_allocation_failed")),
        ("tail", ProviderObservationError("tail_start_failed")),
        ("callback", OSError("display unavailable")),
        ("tmux_server", ProviderObservationError("server_unavailable")),
        ("transcript", ProviderObservationError("transcript_finalize_failed")),
        ("teardown", ProviderObservationError("pane_teardown_failed")),
    ],
)
@pytest.mark.parametrize("enabled", [False, True])
def test_observation_failures_do_not_change_ordinary_result(
    tmp_path: Path,
    failure_site: str,
    failure: BaseException,
    enabled: bool,
) -> None:
    handle = _RecordingHandle(
        append_failure=failure if failure_site == "callback" else None,
        health_failure=failure if failure_site == "tmux_server" else None,
        finalize_failure=(
            failure if failure_site in {"transcript", "teardown"} else None
        ),
    )
    manager = _RecordingManager(
        handle,
        open_failure=(
            failure if failure_site in {"allocation", "tail"} else None
        ),
    )

    result = _executor(tmp_path, enabled=enabled, manager=manager).execute(
        _ordinary_invocation()
    )

    assert result.exit_code == 0
    assert result.stdout == b"ordinary-out"
    assert result.stderr == b"ordinary-err"
    assert result.error is None
    if not enabled:
        assert manager.open_calls == []
        assert handle.display_chunks == []
        assert handle.health_calls == 0
        assert handle.finalize_calls == 0
    else:
        assert len(manager.open_calls) == 1
        if failure_site not in {"allocation", "tail"}:
            assert handle.health_calls >= 1


def test_preopened_handle_is_used_without_touching_manager(
    tmp_path: Path,
) -> None:
    automatic_handle = _RecordingHandle()
    manager = _RecordingManager(automatic_handle)
    preopened = _RecordingHandle()
    executor = _executor(tmp_path, enabled=True, manager=manager)

    result = executor.execute(
        _ordinary_invocation(),
        observation_handle=preopened,
    )

    assert result.exit_code == 0
    assert manager.open_calls == []
    assert automatic_handle.display_chunks == []
    assert preopened.display_chunks == [b"ordinary-out"]
    assert preopened.health_calls >= 1
    assert preopened.finalize_calls == 0


@pytest.mark.parametrize("failure_site", ["allocation", "health", "finalize"])
def test_observation_does_not_mask_process_control_exceptions(
    tmp_path: Path,
    failure_site: str,
) -> None:
    interrupt = KeyboardInterrupt(failure_site)
    handle = _RecordingHandle(
        health_failure=interrupt if failure_site == "health" else None,
        finalize_failure=interrupt if failure_site == "finalize" else None,
    )
    manager = _RecordingManager(
        handle,
        open_failure=interrupt if failure_site == "allocation" else None,
    )

    with pytest.raises(KeyboardInterrupt, match=failure_site):
        _executor(tmp_path, enabled=True, manager=manager).execute(
            _ordinary_invocation()
        )


@pytest.mark.parametrize("enabled", [False, True])
def test_observation_append_failure_preserves_controlled_result(
    tmp_path: Path,
    enabled: bool,
) -> None:
    handle = _RecordingHandle(append_failure=OSError("display unavailable"))
    manager = _RecordingManager(handle)
    executor = _executor(tmp_path, enabled=enabled, manager=manager)

    result = executor.execute(
        _ordinary_invocation(),
        control=ProviderExecutionControl(),
    )

    assert result.exit_code == 0
    assert result.stdout == b"ordinary-out"
    assert result.stderr == b"ordinary-err"
    assert result.classification == "normal"
    assert handle.display_chunks == ([b"ordinary-out"] if enabled else [])
