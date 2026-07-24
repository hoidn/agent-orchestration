"""Provider-execution parity tests for observation-only display mirroring."""

from __future__ import annotations

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
