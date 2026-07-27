from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from orchestrator.providers.observation import (
    ProviderObservationError,
    ProviderObservationManager,
)


class _FakeObservationBackend:
    def __init__(self) -> None:
        self.start_calls = 0
        self.open_calls: list[tuple[Path, str, Path]] = []
        self.close_calls: list[str] = []
        self.close_server_calls = 0
        self.live_targets: set[str] = set()
        self.server_live = False
        self.start_error: BaseException | None = None
        self.open_error: ProviderObservationError | None = None
        self.open_raw_error: BaseException | None = None
        self.close_error: ProviderObservationError | None = None
        self.close_server_error: ProviderObservationError | None = None
        self.close_server_entered = threading.Event()
        self.allow_close_server = threading.Event()
        self.allow_close_server.set()
        self._lock = threading.Lock()

    def start_server(self, socket_path: Path, session_name: str) -> None:
        del socket_path, session_name
        if self.start_error is not None:
            raise self.start_error
        with self._lock:
            self.start_calls += 1
            self.server_live = True

    def open_pane(
        self,
        socket_path: Path,
        session_name: str,
        display_path: Path,
    ) -> str:
        del socket_path
        assert display_path.exists()
        if self.open_error is not None:
            raise self.open_error
        if self.open_raw_error is not None:
            raise self.open_raw_error
        with self._lock:
            target = f"%pane-{len(self.open_calls) + 1}"
            self.open_calls.append((Path("opaque"), session_name, display_path))
            self.live_targets.add(target)
            return target

    def pane_alive(self, socket_path: Path, target: str) -> bool:
        del socket_path
        return target in self.live_targets

    def server_alive(self, socket_path: Path, session_name: str) -> bool:
        del socket_path, session_name
        return self.server_live

    def close_pane(self, socket_path: Path, target: str) -> None:
        del socket_path
        self.close_calls.append(target)
        self.live_targets.discard(target)
        if self.close_error is not None:
            raise self.close_error

    def close_server(self, socket_path: Path) -> None:
        del socket_path
        self.close_server_calls += 1
        self.close_server_entered.set()
        assert self.allow_close_server.wait(timeout=5)
        if self.close_server_error is not None:
            raise self.close_server_error
        self.server_live = False
        self.live_targets.clear()


def _open(
    manager: ProviderObservationManager,
    suffix: str = "1",
):
    return manager.open_observation(
        invocation_id=f"invocation-{suffix}",
        member_id="worker",
        turn_id=f"turn-{suffix}",
    )


def test_observation_manager_uses_one_server_and_unique_precreated_panes(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)

    first = _open(manager, "1")
    second = _open(manager, "2")

    assert backend.start_calls == 1
    assert first.target != second.target
    assert first.display_path != second.display_path
    assert first.transcript_path != second.transcript_path
    assert first.display_path.exists()
    assert second.display_path.exists()
    manager.close()


def test_observation_manager_allocates_run_scoped_invocation_identities(
    tmp_path: Path,
) -> None:
    manager = ProviderObservationManager(
        tmp_path,
        backend=_FakeObservationBackend(),
    )

    assert manager.next_invocation_id() == "provider-invocation-000001"
    assert manager.next_invocation_id() == "provider-invocation-000002"

    manager.close()
    with pytest.raises(ProviderObservationError) as exc_info:
        manager.next_invocation_id()
    assert exc_info.value.code == "manager_closed"


def test_observation_finalize_uses_display_bytes_before_pane_teardown(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    handle = _open(manager)
    payload = b"first\nsecond\x00tail\n"

    handle.append_display(payload[:7])
    handle.append_display(payload[7:])
    record = handle.finalize()

    assert handle.transcript_path.read_bytes() == payload
    assert backend.close_calls == [handle.target]
    assert record["status"] == "finalized"
    assert handle.finalize() == record
    assert backend.close_calls == [handle.target]
    manager.close()


def test_stable_record_is_relative_and_excludes_live_tmux_address(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    handle = _open(manager)

    record = handle.stable_record
    serialized = json.dumps(record, sort_keys=True)

    assert set(record) == {
        "schema_version",
        "invocation_id",
        "member_id",
        "turn_id",
        "display_path",
        "transcript_path",
        "status",
        "failure_code",
    }
    assert record["schema_version"] == "provider_observation.v1"
    assert not Path(record["display_path"]).is_absolute()
    assert not Path(record["transcript_path"]).is_absolute()
    assert str(handle.socket_path) not in serialized
    assert handle.target not in serialized
    assert "socket" not in record
    assert "target" not in record
    manager.close()


def test_observation_handles_finalize_independently_and_manager_close_is_idempotent(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    first = _open(manager, "1")
    second = _open(manager, "2")

    first.finalize()
    assert first.target not in backend.live_targets
    assert second.target in backend.live_targets

    manager.close()
    manager.close()

    assert second.target not in backend.live_targets
    assert backend.close_server_calls == 1


def test_concurrent_observations_share_server_without_reusing_targets(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    barrier = threading.Barrier(3)

    def _allocate(suffix: str):
        barrier.wait()
        return _open(manager, suffix)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(_allocate, suffix) for suffix in ("1", "2")]
        barrier.wait()
        handles = [future.result(timeout=5) for future in futures]

    assert backend.start_calls == 1
    assert len({handle.target for handle in handles}) == 2
    assert len({handle.display_path for handle in handles}) == 2
    manager.close()


def test_observation_allocation_failure_is_typed_and_manager_remains_closable(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    backend.open_error = ProviderObservationError("tail_start_failed")
    manager = ProviderObservationManager(tmp_path, backend=backend)

    with pytest.raises(ProviderObservationError) as exc_info:
        _open(manager)

    assert exc_info.value.code == "tail_start_failed"
    manager.close()
    assert backend.close_server_calls == 1


def test_observation_server_start_and_raw_allocation_failures_are_typed(
    tmp_path: Path,
) -> None:
    start_backend = _FakeObservationBackend()
    start_backend.start_error = OSError("start unavailable")
    start_manager = ProviderObservationManager(
        tmp_path / "start",
        backend=start_backend,
    )

    with pytest.raises(ProviderObservationError) as start_error:
        _open(start_manager)
    assert start_error.value.code == "server_start_failed"
    start_manager.close()

    allocation_backend = _FakeObservationBackend()
    allocation_backend.open_raw_error = OSError("allocation unavailable")
    allocation_manager = ProviderObservationManager(
        tmp_path / "allocation",
        backend=allocation_backend,
    )

    with pytest.raises(ProviderObservationError) as allocation_error:
        _open(allocation_manager)
    assert allocation_error.value.code == "pane_allocation_failed"
    allocation_manager.close()


def test_observation_display_precreation_failure_is_typed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    original_touch = Path.touch

    def _fail_display_touch(path: Path, *args, **kwargs):
        if path.suffix == ".display":
            raise OSError("display unavailable")
        return original_touch(path, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", _fail_display_touch)

    with pytest.raises(ProviderObservationError) as exc_info:
        _open(manager)

    assert exc_info.value.code == "display_precreate_failed"
    manager.close()


def test_observation_health_and_teardown_failures_are_stable_evidence(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    lost = _open(manager, "lost")
    backend.server_live = False

    assert lost.check_health() is False
    lost_record = lost.finalize()
    assert lost_record["status"] == "failed"
    assert lost_record["failure_code"] == "server_unavailable"

    backend.server_live = True
    teardown = _open(manager, "teardown")
    backend.close_error = ProviderObservationError("pane_teardown_failed")
    teardown_record = teardown.finalize()
    assert teardown_record["status"] == "failed"
    assert teardown_record["failure_code"] == "pane_teardown_failed"
    manager.close()


def test_observation_pane_loss_is_recorded_before_finalize(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    handle = _open(manager)
    backend.live_targets.remove(handle.target)

    assert handle.check_health() is False
    record = handle.finalize()

    assert record["status"] == "failed"
    assert record["failure_code"] == "pane_unavailable"
    manager.close()


def test_observation_transcript_and_server_teardown_failures_are_recorded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _FakeObservationBackend()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    handle = _open(manager)
    original_read_bytes = Path.read_bytes

    def _fail_display_read(path: Path):
        if path == handle.display_path:
            raise OSError("transcript unavailable")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", _fail_display_read)
    record = handle.finalize()

    assert record["status"] == "failed"
    assert record["failure_code"] == "transcript_finalize_failed"

    backend.close_server_error = ProviderObservationError(
        "server_teardown_failed"
    )
    manager.close()
    assert manager.failure_code == "server_teardown_failed"
    assert backend.server_live is True
    assert handle.socket_path.parent.exists()

    backend.close_server_error = None
    manager.close()
    assert backend.server_live is False
    assert not handle.socket_path.parent.exists()


def test_concurrent_manager_close_waits_for_the_same_completed_teardown(
    tmp_path: Path,
) -> None:
    backend = _FakeObservationBackend()
    backend.allow_close_server.clear()
    manager = ProviderObservationManager(tmp_path, backend=backend)
    _open(manager)
    first_done = threading.Event()
    second_done = threading.Event()

    first = threading.Thread(
        target=lambda: (manager.close(), first_done.set()),
    )
    second = threading.Thread(
        target=lambda: (manager.close(), second_done.set()),
    )
    first.start()
    assert backend.close_server_entered.wait(timeout=5)
    second.start()

    assert second_done.wait(timeout=0.1) is False
    backend.allow_close_server.set()
    first.join(timeout=5)
    second.join(timeout=5)

    assert first_done.is_set()
    assert second_done.is_set()
    assert backend.close_server_calls == 1


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is unavailable")
def test_real_tmux_observation_tails_display_and_cleans_private_server(
    tmp_path: Path,
) -> None:
    manager = ProviderObservationManager(tmp_path)
    handle = _open(manager, "real")
    sentinel = "provider-observation-tail-sentinel"

    try:
        handle.append_display((sentinel + "\n").encode("utf-8"))
        deadline = time.monotonic() + 5
        captured = ""
        while time.monotonic() < deadline:
            completed = subprocess.run(
                [
                    "tmux",
                    "-S",
                    str(handle.socket_path),
                    "capture-pane",
                    "-p",
                    "-t",
                    handle.target,
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            captured = completed.stdout
            if sentinel in captured:
                break
            time.sleep(0.05)
        assert sentinel in captured

        record = handle.finalize()
        assert record["status"] == "finalized"
        assert handle.transcript_path.read_text(encoding="utf-8") == (
            sentinel + "\n"
        )
    finally:
        socket_path = handle.socket_path
        manager.close()

    completed = subprocess.run(
        ["tmux", "-S", str(socket_path), "has-session"],
        check=False,
        capture_output=True,
    )
    assert completed.returncode != 0


@pytest.mark.skipif(shutil.which("tmux") is None, reason="tmux is unavailable")
def test_real_tmux_observation_uses_bounded_socket_under_long_tmpdir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_root = tmp_path / "run"
    inherited_temp_root = tmp_path / ("inherited-" + ("x" * 96))
    inherited_temp_root.mkdir()
    monkeypatch.setenv("TMPDIR", str(inherited_temp_root))
    monkeypatch.setattr(tempfile, "tempdir", None)
    manager = ProviderObservationManager(run_root)

    try:
        handle = _open(manager, "long-tmpdir")
        assert len(os.fsencode(handle.socket_path)) <= 103
        assert not handle.socket_path.is_relative_to(inherited_temp_root)
        assert handle.display_path.is_relative_to(run_root)
        assert handle.finalize()["status"] == "finalized"
        socket_directory = handle.socket_path.parent
    finally:
        manager.close()

    assert not socket_directory.exists()
