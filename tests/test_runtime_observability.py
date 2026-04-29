from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from orchestrator.runtime_observability import (
    close_executor_session,
    compute_active_runtime,
    format_duration,
    open_executor_session,
    reconcile_open_sessions,
)
from orchestrator.monitor.process import write_process_metadata
from orchestrator.state import StateManager


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


def test_format_duration_uses_compact_units():
    assert format_duration(None) is None
    assert format_duration(4_000) == "4s"
    assert format_duration(65_000) == "1m 5s"
    assert format_duration(3_665_000) == "1h 1m 5s"


def test_open_and_close_executor_sessions_are_idempotent():
    state = {"updated_at": "2026-04-29T10:00:00Z"}

    session_id = open_executor_session(
        state,
        entrypoint="run",
        pid=123,
        process_start_time="proc-start",
        now=dt("2026-04-29T10:00:00Z"),
    )
    close_executor_session(
        state,
        session_id=session_id,
        status="completed",
        now=dt("2026-04-29T10:05:00Z"),
    )
    close_executor_session(
        state,
        session_id=session_id,
        status="failed",
        now=dt("2026-04-29T10:10:00Z"),
    )

    session = state["runtime_observability"]["executor_sessions"][0]
    assert session["session_id"] == "exec-0001"
    assert session["entrypoint"] == "run"
    assert session["status"] == "completed"
    assert session["duration_ms"] == 300_000


def test_reconcile_open_sessions_marks_dead_session_abandoned():
    state = {
        "updated_at": "2026-04-29T10:07:00Z",
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "entrypoint": "run",
                    "pid": 123,
                    "process_start_time": "old-proc",
                    "started_at": "2026-04-29T10:00:00Z",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                }
            ],
        },
    }

    reconcile_open_sessions(state, process_is_live=lambda session: False)

    session = state["runtime_observability"]["executor_sessions"][0]
    assert session["status"] == "abandoned"
    assert session["ended_at"] == "2026-04-29T10:07:00+00:00"
    assert session["duration_ms"] == 420_000


def test_state_round_trips_runtime_observability(tmp_path: Path):
    workflow = tmp_path / "workflow.yaml"
    workflow.write_text("version: '1.0'\nname: test\nsteps: []\n", encoding="utf-8")
    manager = StateManager(tmp_path, run_id="runtime-state")
    state = manager.initialize("workflow.yaml")

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


def test_process_metadata_can_record_executor_session_id(tmp_path: Path):
    path = write_process_metadata(tmp_path, executor_session_id="exec-0001")

    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["executor_session_id"] == "exec-0001"
