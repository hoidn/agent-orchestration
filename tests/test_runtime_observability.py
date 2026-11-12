from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


from orchestrator.runtime_observability import (
    compute_active_runtime,
)
from orchestrator.state import StateManager
from tests.historical_state import write_historical_state


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def test_compute_active_runtime_sums_closed_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "completed",
                    "duration_ms": 1_200_000,
                }
            ],
        }
    }

    snapshot = compute_active_runtime(state, now=dt("2026-04-29T12:00:00Z"))

    assert snapshot["active_runtime_ms"] == 1_200_000
    assert snapshot["active_runtime"] == "20m 0s"
    assert snapshot["executor_session_count"] == 1


def test_compute_active_runtime_excludes_gap_between_sessions():
    state = {
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": "2026-04-29T10:20:00Z",
                    "status": "failed",
                    "duration_ms": 1_200_000,
                },
                {
                    "session_id": "exec-0002",
                    "started_at": "2026-04-29T22:15:00Z",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                    "pid": 123,
                },
            ],
        }
    }

    snapshot = compute_active_runtime(
        state,
        now=dt("2026-04-29T22:20:00Z"),
        process_is_live=lambda session: True,
    )

    assert snapshot["active_runtime_ms"] == 1_500_000
    assert snapshot["active_runtime"] == "25m 0s"
    assert snapshot["excluded_suspended_ms"] == 42_900_000
    assert snapshot["suspended_gap_excluded"] == "11h 55m 0s"


def test_compute_active_runtime_missing_field_is_unknown():
    snapshot = compute_active_runtime({}, now=dt("2026-04-29T12:00:00Z"))

    assert snapshot["active_runtime_ms"] is None
    assert snapshot["active_runtime"] is None
    assert snapshot["executor_session_count"] == 0


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
