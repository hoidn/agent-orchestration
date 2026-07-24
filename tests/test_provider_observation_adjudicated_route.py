from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from tests.test_adjudicated_provider_runtime import _workflow
from tests.workflow_fixture_loader import WorkflowLoader


class _FakeObservationHandle:
    def append_display(self, _data: bytes) -> None:
        pass

    def check_health(self) -> bool:
        return True

    def finalize(self) -> dict[str, object]:
        return {"status": "finalized"}


class _FakeObservationManager:
    def __init__(self) -> None:
        self.open_calls: list[dict[str, str]] = []
        self.invocation_index = 0

    def next_invocation_id(self) -> str:
        self.invocation_index += 1
        return f"provider-invocation-{self.invocation_index:06d}"

    def open_observation(self, **coordinates: str) -> _FakeObservationHandle:
        self.open_calls.append(dict(coordinates))
        return _FakeObservationHandle()


@pytest.mark.parametrize("provider_observation_enabled", [False, True])
def test_adjudicated_provider_observes_candidates_and_evaluators_without_changing_selection(
    tmp_path: Path,
    provider_observation_enabled: bool,
) -> None:
    (tmp_path / "prompt.md").write_text(
        "Draft the best possible artifact.",
        encoding="utf-8",
    )
    (tmp_path / "evaluator.md").write_text(
        "Return strict JSON.",
        encoding="utf-8",
    )
    workflow_path = tmp_path / "workflow.fixture.json"
    workflow_path.write_text(
        json.dumps(_workflow()),
        encoding="utf-8",
    )
    bundle = WorkflowLoader(tmp_path).load_bundle(workflow_path)
    state_manager = StateManager(tmp_path, run_id="run-1")
    state_manager.initialize(str(workflow_path))
    observation_manager = _FakeObservationManager()

    state = WorkflowExecutor(
        bundle,
        tmp_path,
        state_manager,
        retry_delay_ms=0,
        provider_observation_enabled=provider_observation_enabled,
        provider_observation_manager=observation_manager,
    ).execute()

    result = state["steps"]["Draft"]
    assert result["adjudication"]["selected_candidate_id"] == "b"
    assert result["adjudication"]["selected_score"] == 0.9
    assert result["adjudication"]["promotion_status"] == "committed"
    assert len(observation_manager.open_calls) == (
        4 if provider_observation_enabled else 0
    )
