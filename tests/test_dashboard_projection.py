"""Tests for dashboard run projection."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_state(workspace: Path, run_dir_id: str, payload: dict) -> Path:
    run_dir = workspace / ".orchestrate" / "runs" / run_dir_id
    run_dir.mkdir(parents=True)
    state_path = run_dir / "state.json"
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return state_path


def _scan_one(workspace: Path):
    return RunScanner([workspace]).scan().runs[0]


def test_projector_uses_workflow_metadata_and_keeps_display_status_separate(tmp_path: Path):
    workflow_path = _write_yaml(
        tmp_path / "workflows" / "flow.yaml",
        {
            "version": "1.3",
            "name": "dashboard-flow",
            "steps": [
                {"name": "Prep", "command": ["bash", "-lc", "echo prep"]},
                {"name": "Draft", "provider": "codex"},
            ],
        },
    )
    stale_updated = datetime.now(timezone.utc) - timedelta(minutes=30)
    state = {
        "run_id": "run1",
        "status": "running",
        "workflow_file": str(workflow_path.relative_to(tmp_path)),
        "started_at": "2026-04-13T12:00:00+00:00",
        "updated_at": stale_updated.isoformat(),
        "steps": {"Prep": {"status": "completed", "exit_code": 0}},
    }
    state_path = _write_state(tmp_path, "run1", state)
    before = state_path.read_text(encoding="utf-8")

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.row.workflow_name == "dashboard-flow"
    assert detail.row.persisted_status == "running"
    assert detail.row.display_status == "failed"
    assert detail.row.display_status_reason == "stale_running_without_current_step"
    assert [step.name for step in detail.steps] == ["Prep", "Draft"]
    assert detail.steps[0].kind == "command"
    assert state_path.read_text(encoding="utf-8") == before


def test_projector_uses_injected_time_for_workflow_aware_stale_heartbeat(
    tmp_path: Path,
):
    workflow_path = _write_yaml(
        tmp_path / "workflows" / "flow.yaml",
        {
            "version": "1.3",
            "name": "dashboard-flow",
            "steps": [{"name": "Step", "command": ["bash", "-lc", "true"]}],
        },
    )
    _write_state(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "workflow_file": str(workflow_path.relative_to(tmp_path)),
            "current_step": {
                "name": "Step",
                "step_id": "root.step",
                "last_heartbeat_at": "2030-01-01T00:00:00+00:00",
            },
        },
    )
    run = _scan_one(tmp_path)

    detail = RunProjector(
        now=datetime(2030, 1, 1, 0, 6, tzinfo=timezone.utc),
    ).project_detail(run)

    assert detail.row.display_status == "failed"
    assert detail.row.display_status_reason == "stale_running_step_heartbeat_timeout"


def test_projector_exposes_elapsed_current_step_start_and_heartbeat_separately(
    tmp_path: Path,
):
    _write_state(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "started_at": "2026-04-13T12:00:00+00:00",
            "updated_at": "2026-04-13T12:02:00+00:00",
            "current_step": {
                "name": "Step",
                "started_at": "2026-04-13T12:01:00+00:00",
                "last_heartbeat_at": "2026-04-13T12:01:30+00:00",
            },
        },
    )

    detail = RunProjector(
        now=datetime(2026, 4, 13, 12, 2, 30, tzinfo=timezone.utc),
    ).project_detail(_scan_one(tmp_path))

    assert detail.row.elapsed_seconds == 150
    assert detail.row.current_step_started_at == "2026-04-13T12:01:00+00:00"
    assert detail.row.heartbeat_at == "2026-04-13T12:01:30+00:00"
    assert detail.row.heartbeat_age_seconds == 60


def test_projector_falls_back_to_state_only_when_workflow_file_is_unsafe(tmp_path: Path):
    outside = tmp_path.parent / "outside-workflow.yaml"
    state = {
        "run_id": "run2",
        "status": "failed",
        "workflow_file": str(outside),
        "steps": {
            "A": {"status": "completed", "output": "done"},
            "B": {"status": "failed", "error": {"message": "boom"}},
        },
    }
    _write_state(tmp_path, "run2", state)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.degraded is True
    assert detail.row.workflow_name is None
    assert [step.name for step in detail.steps] == ["A", "B"]
    assert detail.row.failure_summary == "boom"
    assert any("workflow file is outside workspace" in warning for warning in detail.warnings)


def test_projector_represents_parse_failures_as_rows(tmp_path: Path):
    run_dir = tmp_path / ".orchestrate" / "runs" / "bad"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text("{bad", encoding="utf-8")

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    assert detail.row.run_dir_id == "bad"
    assert detail.row.display_status == "unreadable"
    assert detail.row.failure_summary.startswith("failed to parse state")


def test_projector_links_safe_artifacts_and_warns_on_unsafe_artifacts(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "result.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok", encoding="utf-8")
    outside = tmp_path.parent / "outside-artifact.txt"
    state = {
        "run_id": "run3",
        "status": "completed",
        "steps": {
            "Produce": {
                "status": "completed",
                "artifacts": {
                    "safe_path": "artifacts/result.txt",
                    "unsafe_path": str(outside),
                },
            }
        },
        "artifact_versions": {
            "safe_path": [{"version": 1, "value": "artifacts/result.txt", "producer": "Produce"}]
        },
        "artifact_consumes": {"Use": {"safe_path": 1}},
    }
    _write_state(tmp_path, "run3", state)

    detail = RunProjector().project_detail(_scan_one(tmp_path))
    produce = detail.steps[0]

    assert produce.file_refs["safe_path"].route_path == "artifacts/result.txt"
    assert "unsafe_path" not in produce.file_refs
    assert detail.artifact_versions["safe_path"][0]["file_ref"].route_path == "artifacts/result.txt"
    assert detail.artifact_consumes == {"Use": {"safe_path": 1}}
    assert any("unsafe artifact unsafe_path" in warning for warning in detail.warnings)


def test_projector_exposes_call_frame_local_artifact_lineage(tmp_path: Path):
    frame_artifact = tmp_path / "artifacts" / "frame-result.txt"
    frame_artifact.parent.mkdir()
    frame_artifact.write_text("frame", encoding="utf-8")
    outside = tmp_path.parent / "outside-frame-artifact.txt"
    state = {
        "run_id": "run4",
        "status": "running",
        "current_step": {"name": "Call", "step_id": "root.call"},
        "call_frames": {
            "root.call::visit::1": {
                "step_id": "root.call",
                "state": {
                    "artifact_versions": {
                        "frame_result": [
                            {
                                "version": 1,
                                "value": "artifacts/frame-result.txt",
                                "producer": "Nested",
                            }
                        ],
                        "unsafe_frame_result": [
                            {"version": 1, "value": str(outside), "producer": "Nested"}
                        ],
                    },
                    "artifact_consumes": {"NestedReview": {"frame_result": 1}},
                },
            }
        },
    }
    _write_state(tmp_path, "run4", state)

    detail = RunProjector().project_detail(_scan_one(tmp_path))

    frame_versions = detail.call_frame_artifact_versions["root.call::visit::1"]
    assert frame_versions["frame_result"][0]["file_ref"].route_path == (
        "artifacts/frame-result.txt"
    )
    assert "unsafe_frame_result" in frame_versions
    assert "file_ref" not in frame_versions["unsafe_frame_result"][0]
    assert detail.call_frame_artifact_consumes == {
        "root.call::visit::1": {"NestedReview": {"frame_result": 1}}
    }
    assert any(
        "unsafe call frame root.call::visit::1 artifact unsafe_frame_result" in warning
        for warning in detail.warnings
    )
