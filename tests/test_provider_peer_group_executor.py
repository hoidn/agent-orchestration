"""Executor integration checks for the atomic provider peer-group node."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from orchestrator.state import StateManager, StepResult
from orchestrator.workflow.executable_ir import ExecutableNodeKind
from orchestrator.workflow.executor import WorkflowExecutor


def test_top_level_peer_group_uses_its_separate_atomic_dispatch() -> None:
    executor = object.__new__(WorkflowExecutor)
    executor._execution_kind_for_step = (  # type: ignore[method-assign]
        lambda _step: ExecutableNodeKind.PROVIDER_PEER_GROUP
    )
    calls: list[tuple[Any, ...]] = []

    def execute(
        step: Any,
        state: dict[str, Any],
        *,
        step_name: str,
    ) -> dict[str, Any]:
        calls.append((step, state, step_name))
        return {"status": "completed", "exit_code": 0}

    executor._execute_provider_peer_group = execute  # type: ignore[method-assign]
    step = {"name": "Peers", "step_id": "root.peers"}
    state: dict[str, Any] = {"steps": {}}

    result = WorkflowExecutor._run_top_level_step(
        executor,
        step,
        state,
        step_name="Peers",
    )

    assert result == {"status": "completed", "exit_code": 0}
    assert calls == [(step, state, "Peers")]


def _atomic_executor(
    manager: StateManager,
) -> WorkflowExecutor:
    executor = object.__new__(WorkflowExecutor)
    executor.state_manager = manager
    executor._record_published_artifacts = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    executor._attach_outcome = (  # type: ignore[method-assign]
        lambda _step, result: dict(result)
    )
    executor._step_id = (  # type: ignore[method-assign]
        lambda _step: "root.peers"
    )
    executor._finalize_consumes = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    executor._to_step_result = (  # type: ignore[method-assign]
        lambda result, step_name: StepResult(
            status=result["status"],
            name=step_name,
            step_id=result["step_id"],
            exit_code=result["exit_code"],
            duration_ms=result.get("duration_ms", 0),
            artifacts=result.get("artifacts"),
            error=result.get("error"),
            debug=result.get("debug"),
            visit_count=result.get("visit_count"),
        )
    )
    executor._emit_step_summary = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: None
    )
    return executor


def _running_manager(tmp_path: Path) -> StateManager:
    workflow = tmp_path / "workflow.orc"
    workflow.write_text("; generated peer group\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="peer-group-atomic")
    manager.initialize("workflow.orc")
    manager.update_control_flow_counters(0, {"Peers": 1})
    manager.start_step(
        "Peers",
        0,
        "provider_peer_group",
        step_id="root.peers",
        visit_count=1,
    )
    return manager


def test_peer_group_finalizer_commits_state_and_result_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _running_manager(tmp_path)
    state = manager.load().to_dict()
    executor = _atomic_executor(manager)
    metadata_updates: list[dict[str, Any]] = []
    executor._update_provider_peer_group_visit_metadata = (  # type: ignore[method-assign]
        lambda _step, **kwargs: metadata_updates.append(kwargs)
    )
    writes = 0
    write_state = manager._write_state

    def count_write() -> None:
        nonlocal writes
        writes += 1
        write_state()

    monkeypatch.setattr(manager, "_write_state", count_write)
    result = WorkflowExecutor._finalize_provider_peer_group_settlement(
        executor,
        {"name": "Peers", "step_id": "root.peers"},
        state,
        step_name="Peers",
        result={
            "status": "completed",
            "exit_code": 0,
            "duration_ms": 1,
            "artifacts": {"__result__": "settled"},
        },
    )

    persisted = manager.load()
    assert result["status"] == "completed"
    assert writes == 1
    assert persisted.current_step is None
    assert persisted.steps["Peers"]["artifacts"] == {
        "__result__": "settled"
    }
    assert metadata_updates == [
        {
            "step_name": "Peers",
            "step_id": "root.peers",
            "visit_count": 1,
            "status": "completed",
            "publication_state": "committed_terminal_result",
        }
    ]


def test_peer_group_finalizer_rejects_current_step_drift_without_a_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = _running_manager(tmp_path)
    state = manager.load().to_dict()
    original_state = deepcopy(state)
    manager.start_step(
        "Other",
        1,
        "provider",
        step_id="root.other",
        visit_count=1,
    )
    executor = _atomic_executor(manager)
    prevalidation_calls: list[str] = []
    executor._record_published_artifacts = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: prevalidation_calls.append("publish")
    )
    executor._finalize_consumes = (  # type: ignore[method-assign]
        lambda *_args, **_kwargs: prevalidation_calls.append("consumes")
    )
    writes = 0
    write_state = manager._write_state

    def count_write() -> None:
        nonlocal writes
        writes += 1
        write_state()

    monkeypatch.setattr(manager, "_write_state", count_write)
    with pytest.raises(
        ValueError,
        match="current_step changed before atomic settlement",
    ):
        WorkflowExecutor._finalize_provider_peer_group_settlement(
            executor,
            {"name": "Peers", "step_id": "root.peers"},
            state,
            step_name="Peers",
            result={
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 1,
                "artifacts": {"__result__": "settled"},
            },
        )

    assert writes == 0
    assert state == original_state
    assert prevalidation_calls == []
    assert "Peers" not in manager.load().steps
