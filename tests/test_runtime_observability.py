from __future__ import annotations

import json
from pathlib import Path


from orchestrator.state import StateManager
from tests.historical_state import write_historical_state


def test_state_round_trips_runtime_observability(tmp_path: Path):
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text(r"""
{
  "version": "1.0",
  "name": "test",
  "steps": []
}
""", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="runtime-state")
    state = write_historical_state(manager, "workflow.yaml")

    state.runtime_observability = {
        "schema_version": 1,
        "executor_sessions": [{"session_id": "exec-0001", "status": "completed"}],
    }
    manager._write_state()

    loaded = StateManager(tmp_path, run_id="runtime-state").load()

    assert loaded.runtime_observability == state.runtime_observability


def test_old_state_without_runtime_observability_still_loads(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "old-state"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": StateManager.SCHEMA_VERSION,
                "run_id": "old-state",
                "workflow_file": "workflow.yaml",
                "workflow_checksum": "sha256:test",
                "started_at": "2026-04-29T10:00:00Z",
                "updated_at": "2026-04-29T10:00:00Z",
                "status": "running",
                "context": {},
                "bound_inputs": {},
                "workflow_outputs": {},
                "finalization": {},
                "steps": {},
                "for_each": {},
                "repeat_until": {},
                "call_frames": {},
                "artifact_versions": {},
                "artifact_consumes": {},
                "transition_count": 0,
                "step_visits": {},
            }
        ),
        encoding="utf-8",
    )

    loaded = StateManager(tmp_path, run_id="old-state").load()

    assert loaded.runtime_observability is None
