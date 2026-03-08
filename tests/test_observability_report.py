"""Tests for deterministic workflow status reporting."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.observability.report import build_status_snapshot, render_status_markdown


def _sample_workflow():
    return {
        "version": "1.3",
        "name": "obs-test",
        "steps": [
            {
                "name": "Prep",
                "command": ["bash", "-lc", "echo prep"],
                "consumes": [{"artifact": "plan_doc", "as": "plan"}],
            },
            {
                "name": "DraftPlan",
                "provider": "codex",
                "expected_outputs": [
                    {"name": "plan_path", "path": "state/plan_path.txt", "type": "path"}
                ],
            },
        ],
    }


def test_snapshot_counts_and_infers_running_from_prompt_audit(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    (logs / "DraftPlan.prompt.txt").write_text("Resolved prompt content")

    state = {
        "run_id": "run1",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)

    assert snapshot["progress"]["total"] == 2
    assert snapshot["progress"]["completed"] == 1
    assert snapshot["progress"]["running"] == 1
    assert snapshot["progress"]["pending"] == 0

    steps = {s["name"]: s for s in snapshot["steps"]}
    assert steps["DraftPlan"]["status"] == "running"
    assert "Resolved prompt content" in steps["DraftPlan"]["input"]["prompt"]


def test_snapshot_contains_command_input_and_output_summary(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run2"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "run2",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "failed",
                "exit_code": 1,
                "duration_ms": 11,
                "output": "x" * 250,
                "artifacts": {"log_path": "artifacts/log.txt"},
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert prep["input"]["command"] == ["bash", "-lc", "echo prep"]
    assert prep["output"]["exit_code"] == 1
    assert prep["output"]["duration_ms"] == 11
    assert prep["output"]["artifacts"]["log_path"] == "artifacts/log.txt"
    assert len(prep["output"]["output_preview"]) < 250


def test_snapshot_surfaces_normalized_outcome_fields(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-outcome"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "run-outcome",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "failed",
                "exit_code": 3,
                "duration_ms": 0,
                "error": {"type": "assert_failed", "message": "Assertion failed"},
                "outcome": {
                    "status": "failed",
                    "phase": "execution",
                    "class": "assert_failed",
                    "retryable": False,
                },
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert prep["output"]["outcome"] == {
        "status": "failed",
        "phase": "execution",
        "class": "assert_failed",
        "retryable": False,
    }


def test_snapshot_marks_completed_for_each_summary_as_completed(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-loop"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "1.3",
        "name": "obs-loop",
        "steps": [
            {
                "name": "Loop",
                "for_each": {
                    "items": ["one", "two"],
                    "steps": [
                        {
                            "name": "Inner",
                            "command": ["bash", "-lc", "echo inner"],
                        }
                    ],
                },
            }
        ],
    }
    state = {
        "run_id": "run-loop",
        "status": "completed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Loop": [
                {"Inner": {"status": "completed", "exit_code": 0}},
                {"Inner": {"status": "completed", "exit_code": 0}},
            ]
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["steps"][0]["status"] == "completed"
    assert snapshot["progress"]["running"] == 0
    assert snapshot["progress"]["completed"] == 1


def test_markdown_renderer_emits_human_readable_status(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run3"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    (logs / "DraftPlan.prompt.txt").write_text("Prompt body")

    state = {
        "run_id": "run3",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {},
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    md = render_status_markdown(snapshot)

    assert "# Workflow Status" in md
    assert "run3" in md
    assert "DraftPlan" in md
    assert "Prompt body" in md
    assert "Progress" in md


def test_snapshot_marks_stale_running_without_current_step_as_failed(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "stale-run"
    (run_root / "logs").mkdir(parents=True)

    stale_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    state = {
        "run_id": "stale-run",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": stale_updated_at,
        "workflow_file": "workflows/test.yaml",
        "steps": {
            "Prep": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)

    assert snapshot["run"]["status"] == "failed"
    assert snapshot["run"]["status_reason"] == "stale_running_without_current_step"


def test_snapshot_exposes_looped_resume_current_and_last_completed_visit_counts(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "looped-resume"
    (run_root / "logs").mkdir(parents=True)

    state = {
        "run_id": "looped-resume",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "step_visits": {"Prep": 2},
        "current_step": {
            "name": "Prep",
            "status": "running",
            "visit_count": 2,
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "Prep": {
                "status": "completed",
                "visit_count": 1,
                "exit_code": 0,
                "duration_ms": 31,
                "output": "prep done",
            }
        },
    }

    snapshot = build_status_snapshot(_sample_workflow(), state, run_root)
    prep = snapshot["steps"][0]

    assert snapshot["run"]["status"] == "running"
    assert prep["visit_count"] == 2
    assert prep["current_visit_count"] == 2


def test_snapshot_includes_finalization_progress_and_steps(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-finally"
    (run_root / "logs").mkdir(parents=True)

    workflow = {
        "version": "2.3",
        "name": "obs-finally",
        "steps": [
            {
                "name": "Body",
                "command": ["bash", "-lc", "echo body"],
            }
        ],
        "finally": {
            "token": "cleanup",
            "steps": [
                {
                    "name": "finally.ReleaseLock",
                    "command": ["bash", "-lc", "echo cleanup"],
                    "workflow_finalization": {"block_id": "cleanup"},
                }
            ],
        },
    }
    state = {
        "run_id": "run-finally",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "current_step": {
            "name": "finally.ReleaseLock",
            "status": "running",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "finalization": {
            "block_id": "cleanup",
            "status": "running",
            "body_status": "completed",
            "current_index": 0,
            "completed_indices": [],
            "workflow_outputs_status": "pending",
        },
        "steps": {
            "Body": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 12,
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)

    assert snapshot["run"]["finalization"]["status"] == "running"
    steps = {entry["name"]: entry for entry in snapshot["steps"]}
    assert steps["finally.ReleaseLock"]["kind"] == "finally"
    assert steps["finally.ReleaseLock"]["status"] == "running"
