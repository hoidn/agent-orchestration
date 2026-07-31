from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

import orchestrator.workflow.executor as executor_module
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.workflow_fixture_loader import WorkflowLoader


class _FakeObservationManager:
    def __init__(self, run_root: Path, *, fail_close: bool = False) -> None:
        self.run_root = Path(run_root)
        self.fail_close = fail_close
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1
        if self.fail_close:
            raise RuntimeError("observation teardown failed")


class _RecordingProviderExecutor:
    constructions: list[tuple[bool, object | None]] = []
    instances: list["_RecordingProviderExecutor"] = []

    def __init__(
        self,
        _workspace: Path,
        _registry: object,
        _secrets_manager: object,
        *,
        provider_observation_enabled: bool = False,
        observation_manager: object | None = None,
    ) -> None:
        self.provider_observation_enabled = provider_observation_enabled
        self.observation_manager = observation_manager
        self.constructions.append(
            (provider_observation_enabled, observation_manager)
        )
        self.instances.append(self)


def _write_bundle(
    workspace: Path,
    payload: dict[str, object],
    *,
    name: str = "workflow.fixture.json",
):
    path = workspace / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    return WorkflowLoader(workspace).load_bundle(path), path


def _install_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fail_close: bool,
) -> list[_FakeObservationManager]:
    managers: list[_FakeObservationManager] = []

    def _manager_factory(run_root: Path) -> _FakeObservationManager:
        manager = _FakeObservationManager(run_root, fail_close=fail_close)
        managers.append(manager)
        return manager

    _RecordingProviderExecutor.constructions = []
    _RecordingProviderExecutor.instances = []
    monkeypatch.setattr(
        executor_module,
        "ProviderObservationManager",
        _manager_factory,
    )
    monkeypatch.setattr(
        executor_module,
        "ProviderExecutor",
        _RecordingProviderExecutor,
    )
    return managers


def test_root_provider_observation_is_enabled_by_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managers = _install_fakes(monkeypatch, fail_close=False)
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "default-observation-owner",
            "steps": [
                {
                    "name": "Complete",
                    "id": "complete",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    state_manager = StateManager(
        tmp_path,
        run_id="default-observation-owner",
    )
    state_manager.initialize(str(workflow_path))

    executor = WorkflowExecutor(bundle, tmp_path, state_manager)

    assert executor.provider_observation_enabled is True
    assert managers == []
    assert _RecordingProviderExecutor.constructions == [
        (True, None)
    ]
    assert _RecordingProviderExecutor.instances[0].observation_manager is None

    state = executor.execute()

    assert state["status"] == "completed"
    assert len(managers) == 1
    assert _RecordingProviderExecutor.instances[0].observation_manager is (
        managers[0]
    )
    assert managers[0].close_calls == 1


@pytest.mark.parametrize("provider_observation_enabled", [False, True])
def test_root_provider_observation_manager_is_run_scoped_and_best_effort_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_observation_enabled: bool,
) -> None:
    managers = _install_fakes(monkeypatch, fail_close=True)
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "root-observation-owner",
            "steps": [
                {
                    "name": "Complete",
                    "id": "complete",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    state_manager = StateManager(tmp_path, run_id="root-observation-owner")
    state_manager.initialize(str(workflow_path))

    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        provider_observation_enabled=provider_observation_enabled,
    )

    assert managers == []
    assert len(_RecordingProviderExecutor.instances) == 1
    provider_executor = _RecordingProviderExecutor.instances[0]
    assert (
        provider_executor.provider_observation_enabled
        is provider_observation_enabled
    )
    assert provider_executor.observation_manager is None

    state = executor.execute()

    assert state["status"] == "completed"
    assert len(managers) == int(provider_observation_enabled)
    expected_manager = managers[0] if managers else None
    assert provider_executor.observation_manager is expected_manager
    if expected_manager is not None:
        assert expected_manager.run_root == state_manager.run_root
        assert expected_manager.close_calls == 1


@pytest.mark.parametrize("provider_observation_enabled", [False, True])
def test_provider_observation_manager_construction_failure_is_non_interfering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_observation_enabled: bool,
) -> None:
    allocation_attempts = 0

    def _fail_manager_allocation(_run_root: Path) -> object:
        nonlocal allocation_attempts
        allocation_attempts += 1
        raise RuntimeError("observation allocation failed")

    _RecordingProviderExecutor.constructions = []
    _RecordingProviderExecutor.instances = []
    monkeypatch.setattr(
        executor_module,
        "ProviderObservationManager",
        _fail_manager_allocation,
    )
    monkeypatch.setattr(
        executor_module,
        "ProviderExecutor",
        _RecordingProviderExecutor,
    )
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "observation-allocation-failure",
            "steps": [
                {
                    "name": "Complete",
                    "id": "complete",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    state_manager = StateManager(
        tmp_path,
        run_id="observation-allocation-failure",
    )
    state_manager.initialize(str(workflow_path))

    state = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        provider_observation_enabled=provider_observation_enabled,
    ).execute()

    assert allocation_attempts == int(provider_observation_enabled)
    assert len(_RecordingProviderExecutor.instances) == 1
    provider_executor = _RecordingProviderExecutor.instances[0]
    assert (
        provider_executor.provider_observation_enabled
        is provider_observation_enabled
    )
    assert provider_executor.observation_manager is None
    assert state["status"] == "completed"


def test_owned_observation_manager_is_acquired_after_fallible_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managers = _install_fakes(monkeypatch, fail_close=False)
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "late-observation-acquisition",
            "steps": [
                {
                    "name": "Complete",
                    "id": "complete",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    state_manager = StateManager(
        tmp_path,
        run_id="late-observation-acquisition",
    )
    state_manager.initialize(str(workflow_path))
    monkeypatch.setattr(
        executor_module,
        "DependencyResolver",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("later initialization failed")
        ),
    )

    with pytest.raises(RuntimeError, match="later initialization failed"):
        WorkflowExecutor(
            bundle,
            tmp_path,
            state_manager,
            provider_observation_enabled=True,
        )

    assert managers == []


class _LifecycleObservationHandle:
    def __init__(self, events: list[str]) -> None:
        self._events = events

    def check_health(self) -> bool:
        return True

    def append_display(self, _data: bytes) -> None:
        pass

    def finalize(self) -> dict[str, object]:
        self._events.append("handle_finalized")
        return {"status": "finalized"}


class _LifecycleObservationManager:
    def __init__(self, _run_root: Path) -> None:
        self.events: list[str] = []
        self.closed = threading.Event()

    def open_observation(self, **_identity: str) -> _LifecycleObservationHandle:
        self.events.append("handle_opened")
        return _LifecycleObservationHandle(self.events)

    def close(self) -> None:
        self.events.append("manager_closed")
        self.closed.set()


class _BlockingSummaryObserver:
    def __init__(self, manager_getter) -> None:
        self._manager_getter = manager_getter
        self.started = threading.Event()
        self.release = threading.Event()
        self._thread: threading.Thread | None = None

    def emit(self, *_args, **_kwargs) -> None:
        def _run() -> None:
            manager = self._manager_getter()
            handle = manager.open_observation(
                invocation_id="summary-invocation",
                member_id="ordinary",
                turn_id="turn-1",
            )
            self.started.set()
            assert self.release.wait(timeout=5)
            handle.finalize()

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()
        assert self.started.wait(timeout=5)

    def wait_for_pending(self) -> None:
        if self._thread is not None:
            self._thread.join()


def test_owned_manager_closes_after_async_summary_observation_finishes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    managers: list[_LifecycleObservationManager] = []
    observers: list[_BlockingSummaryObserver] = []

    def _manager_factory(run_root: Path) -> _LifecycleObservationManager:
        manager = _LifecycleObservationManager(run_root)
        managers.append(manager)
        return manager

    def _summary_factory(executor: WorkflowExecutor):
        observer = _BlockingSummaryObserver(
            lambda: executor.provider_observation_manager
        )
        observers.append(observer)
        return observer

    monkeypatch.setattr(
        executor_module,
        "ProviderObservationManager",
        _manager_factory,
    )
    monkeypatch.setattr(
        WorkflowExecutor,
        "_create_summary_observer",
        _summary_factory,
    )
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "async-summary-observation-lifecycle",
            "steps": [
                {
                    "name": "Complete",
                    "id": "complete",
                    "command": [sys.executable, "-c", "pass"],
                }
            ],
        },
    )
    state_manager = StateManager(
        tmp_path,
        run_id="async-summary-observation-lifecycle",
    )
    state_manager.initialize(str(workflow_path))
    executor = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        provider_observation_enabled=True,
    )
    result_box: dict[str, object] = {}
    worker = threading.Thread(
        target=lambda: result_box.setdefault("state", executor.execute()),
        daemon=True,
    )
    worker.start()

    observer = observers[0]
    assert observer.started.wait(timeout=5)
    assert len(managers) == 1
    manager = managers[0]
    try:
        assert manager.closed.wait(timeout=0.2) is False
        assert worker.is_alive()
    finally:
        observer.release.set()
    worker.join(timeout=5)

    assert not worker.is_alive()
    assert result_box["state"]["status"] == "completed"
    assert manager.events == [
        "handle_opened",
        "handle_finalized",
        "manager_closed",
    ]


@pytest.mark.parametrize("provider_observation_enabled", [False, True])
def test_imported_child_shares_root_provider_observation_manager_without_ownership(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider_observation_enabled: bool,
) -> None:
    managers = _install_fakes(monkeypatch, fail_close=False)
    child_path = tmp_path / "workflows" / "child.fixture.json"
    child_path.parent.mkdir(parents=True, exist_ok=True)
    child_path.write_text(
        json.dumps(
            {
                "version": "2.7",
                "name": "child",
                "steps": [
                    {
                        "name": "ChildComplete",
                        "id": "child_complete",
                        "command": [sys.executable, "-c", "pass"],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    bundle, workflow_path = _write_bundle(
        tmp_path,
        {
            "version": "2.7",
            "name": "root-with-child",
            "imports": {"child": "workflows/child.fixture.json"},
            "steps": [
                {
                    "name": "RunChild",
                    "id": "run_child",
                    "call": "child",
                }
            ],
        },
    )
    state_manager = StateManager(tmp_path, run_id="root-with-child")
    state_manager.initialize(str(workflow_path))

    state = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        provider_observation_enabled=provider_observation_enabled,
    ).execute()

    assert state["status"] == "completed"
    assert state["steps"]["RunChild"]["status"] == "completed"
    assert len(_RecordingProviderExecutor.instances) == 2
    assert {
        provider_executor.provider_observation_enabled
        for provider_executor in _RecordingProviderExecutor.instances
    } == {provider_observation_enabled}
    if provider_observation_enabled:
        assert len(managers) == 1
        assert {
            id(provider_executor.observation_manager)
            for provider_executor in _RecordingProviderExecutor.instances
        } == {id(managers[0])}
        assert managers[0].close_calls == 1
    else:
        assert managers == []
        assert all(
            provider_executor.observation_manager is None
            for provider_executor in _RecordingProviderExecutor.instances
        )
