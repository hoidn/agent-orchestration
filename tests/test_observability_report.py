"""Tests for deterministic workflow status reporting."""

import json
import os

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType

import pytest

from tests.fixtures.historical_observability_bundles import HISTORICAL_OBSERVABILITY_BUNDLES
from orchestrator.observability.report import (
    build_status_snapshot,
    derive_status_projection,
    render_status_markdown,
)
from orchestrator.monitor.process import process_start_time_token


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

    snapshot = build_status_snapshot(HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"], state, run_root)
    md = render_status_markdown(snapshot)

    assert "# Workflow Status" in md
    assert "run3" in md
    assert "DraftPlan" in md
    assert "Prompt body" in md


def test_judgment_views_markdown_follows_prompt_context_without_full_content(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.judgment_views import (
        _project_group_views,
    )
    from orchestrator.workflow.prompt_identity import canonical_sha256

    run_root = tmp_path / ".orchestrate" / "runs" / "run-prompt-context"
    logs = run_root / "logs"
    logs.mkdir(parents=True)
    prompt_content = "private provider input for the judgment"
    (logs / "DraftPlan.prompt.txt").write_text(prompt_content, encoding="utf-8")
    state = {
        "run_id": "run-prompt-context",
        "status": "running",
        "started_at": "2026-07-27T00:00:00+00:00",
        "updated_at": "2026-07-27T00:00:01+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {},
    }
    digest = "sha256:" + ("1" * 64)
    coordinate = {
        "root_workflow_identity": digest,
        "call_frame_path": [],
        "runtime_step_id": "root.review",
        "enclosing_step_id": "root.review",
        "enclosing_visit": 1,
        "loop": None,
    }
    result_value = {"analysis": "private full result value"}
    comparison = {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": [],
        "reason": "no_predecessor",
    }
    judgment = {
        "schema_version": "workflow_judgment_inspection.v1",
        "status": "available",
        "coordinate": coordinate,
        "attempt_ordinal": 1,
        "result": {
            "declared_shape": "record_value",
            "contract_sha256": digest,
            "value_sha256": canonical_sha256(result_value),
            "value": result_value,
            "comparison": None,
        },
        "provenance": {
            "evidence_record_sha256": digest,
            "identity_schema_version": "workflow_prompt_attempt_identity.v1",
            "role_sha256": {
                "fragment_program": digest,
                "resolved_bindings": digest,
                "injected_dependencies": digest,
                "runtime_contributions": digest,
                "provider_policy": digest,
            },
            "final_prompt_sha256": digest,
            "composition_sha256": digest,
            "comparison": comparison,
        },
    }
    snapshot = build_status_snapshot(
        HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"],
        state,
        run_root,
    )
    matrices, disagreements = _project_group_views([judgment])
    snapshot["judgment_views"] = {
        "schema_version": "workflow_judgment_views.v1",
        "judgments": [judgment],
        "matrices": matrices,
        "disagreements": disagreements,
        "iteration_series": [],
    }

    markdown = render_status_markdown(snapshot)

    judgment_offset = markdown.index("## Judgment views")
    assert judgment_offset > markdown.index("## Prompt context") > markdown.index("## Steps")
    judgment_section = markdown[judgment_offset:]
    assert result_value["analysis"] not in judgment_section
    assert prompt_content not in judgment_section


def test_status_snapshot_surfaces_typed_terminal_observability_summary(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-typed-terminal"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    summary_payload = {
        "schema_id": "workflow_lisp_observability_summary.v1",
        "authority": "observability_only",
        "paths": {
            "json": "summaries/typed-terminal-summary.json",
            "markdown": "summaries/typed-terminal-summary.md",
            "report": "summaries/observability_summary_report.json",
        },
        "terminal_value": {"status": "BLOCKED", "selected_item": "docs/design/example.md"},
        "transition_audit": {"status": "available", "row_count": 1},
    }
    report_payload = {
        "schema_id": "workflow_lisp_observability_summary_report.v1",
        "status": "pass",
        "diagnostics": {"errors": [], "warnings": []},
    }
    (summaries / "typed-terminal-summary.json").write_text(
        json.dumps(summary_payload, indent=2),
        encoding="utf-8",
    )
    (summaries / "typed-terminal-summary.md").write_text(
        "Typed terminal observability summary\n",
        encoding="utf-8",
    )
    (summaries / "observability_summary_report.json").write_text(
        json.dumps(report_payload, indent=2),
        encoding="utf-8",
    )
    state = {
        "run_id": "run-typed-terminal",
        "status": "completed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "steps": {},
        "workflow_outputs": {"status": "BLOCKED"},
    }

    snapshot = build_status_snapshot(HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"], state, run_root)

    typed_terminal = snapshot["run"]["observability_summaries"]["typed_terminal"]
    assert typed_terminal["authority"] == "observability_only"
    assert typed_terminal["status"] == "pass"
    assert typed_terminal["summary_path"] == "summaries/typed-terminal-summary.md"
    assert typed_terminal["payload_path"] == "summaries/typed-terminal-summary.json"
    markdown = render_status_markdown(snapshot)
    assert "Typed Terminal Summary" in markdown
    assert "typed-terminal-summary.md" in markdown


def test_snapshot_and_markdown_surface_active_runtime(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "runtime-report"
    (run_root / "logs").mkdir(parents=True)
    state = {
        "run_id": "runtime-report",
        "status": "running",
        "started_at": "2026-04-29T10:00:00+00:00",
        "updated_at": "2026-04-29T22:15:00+00:00",
        "workflow_file": "workflows/test.yaml",
        "runtime_observability": {
            "schema_version": 1,
            "executor_sessions": [
                {
                    "session_id": "exec-0001",
                    "entrypoint": "run",
                    "started_at": "2026-04-29T10:00:00+00:00",
                    "ended_at": "2026-04-29T10:20:00+00:00",
                    "status": "failed",
                    "duration_ms": 1_200_000,
                },
                {
                    "session_id": "exec-0002",
                    "entrypoint": "resume",
                    "pid": os.getpid(),
                    "process_start_time": process_start_time_token(os.getpid()),
                    "started_at": "2026-04-29T22:15:00+00:00",
                    "ended_at": None,
                    "status": "running",
                    "duration_ms": None,
                },
            ],
        },
        "steps": {},
    }

    snapshot = build_status_snapshot(
        HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"],
        state,
        run_root,
        now=datetime(2026, 4, 29, 22, 20, tzinfo=timezone.utc),
    )
    md = render_status_markdown(snapshot)

    assert snapshot["run"]["active_runtime_ms"] == 1_500_000
    assert snapshot["run"]["active_runtime"] == "25m 0s"
    assert snapshot["run"]["executor_session_count"] == 2
    assert snapshot["run"]["excluded_suspended_ms"] == 42_900_000
    assert "- active_runtime: `25m 0s`" in md
    assert "- suspended_gap_excluded: `11h 55m 0s`" in md


def test_snapshot_exposes_repeat_until_debug_progress_and_markdown(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "repeat-progress-run"
    (run_root / "logs").mkdir(parents=True)

    workflow = HISTORICAL_OBSERVABILITY_BUNDLES['obs-repeat-progress']
    state = {
        "run_id": "repeat-progress-run",
        "status": "running",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "workflow_file": "workflows/test.yaml",
        "current_step": {
            "name": "ReviewLoop",
            "status": "running",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "ReviewLoop": {
                "status": "running",
                "step_id": "root.review_loop",
                "artifacts": {"review_decision": "REVISE"},
                "debug": {
                    "structured_repeat_until": {
                        "body_id": "iteration_body",
                        "max_iterations": 4,
                        "completed_iterations": [0],
                        "current_iteration": 1,
                        "condition_evaluated_for_iteration": None,
                        "last_condition_result": None,
                    }
                },
            }
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)
    review_loop = snapshot["steps"][0]
    markdown = render_status_markdown(snapshot)

    assert review_loop["output"]["debug"]["structured_repeat_until"] == {
        "body_id": "iteration_body",
        "max_iterations": 4,
        "completed_iterations": [0],
        "current_iteration": 1,
        "condition_evaluated_for_iteration": None,
        "last_condition_result": None,
    }
    assert "structured_repeat_until" in markdown
    assert "current_iteration" in markdown
    assert "completed_iterations" in markdown


def test_status_projection_is_pure_for_stale_running_state():
    stale_updated_at = datetime(2026, 2, 27, tzinfo=timezone.utc)
    now = stale_updated_at + timedelta(minutes=30)
    state = {
        "status": "running",
        "updated_at": stale_updated_at.isoformat(),
        "context": {},
    }
    read_only_state = MappingProxyType(state)

    projection = derive_status_projection(
        read_only_state,
        [{"status": "completed"}, {"status": "pending"}],
        now=now,
    )

    assert projection == {
        "persisted_status": "running",
        "display_status": "failed",
        "display_status_reason": "stale_running_without_current_step",
    }
    assert state == {
        "status": "running",
        "updated_at": stale_updated_at.isoformat(),
        "context": {},
    }


@pytest.mark.parametrize(
    "error_type",
    [
        "resume_projection_integrity_error",
        "workflow_checksum_mismatch",
    ],
)
def test_failed_projection_envelope_treats_unchanged_current_step_as_forensic(
    tmp_path: Path,
    error_type: str,
):
    run_root = tmp_path / ".orchestrate" / "runs" / f"forensic-{error_type}"
    (run_root / "logs").mkdir(parents=True)
    (run_root / "logs" / "DraftPlan.prompt.txt").write_text(
        "Prompt evidence from the interrupted visit",
        encoding="utf-8",
    )
    state = {
        "run_id": f"forensic-{error_type}",
        "status": "failed",
        "started_at": "2026-07-15T00:00:00+00:00",
        "updated_at": "2026-07-15T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "error": {
            "type": error_type,
            "message": "Resume preflight failed",
            "context": {"reason": "unknown_explicit_step_id"},
        },
        "current_step": {
            "name": "DraftPlan",
            "step_id": "root.draft_plan",
            "status": "running",
            "visit_count": 2,
            "started_at": "2026-07-15T00:00:01+00:00",
            "last_heartbeat_at": datetime.now(timezone.utc).isoformat(),
        },
        "steps": {
            "Prep": {
                "status": "completed",
                "step_id": "root.prep",
                "visit_count": 1,
                "exit_code": 0,
            }
        },
        "step_visits": {"Prep": 1, "DraftPlan": 2},
    }

    snapshot = build_status_snapshot(
        HISTORICAL_OBSERVABILITY_BUNDLES["obs-test"],
        state,
        run_root,
    )
    steps = {entry["name"]: entry for entry in snapshot["steps"]}
    markdown = render_status_markdown(snapshot)

    assert snapshot["run"]["status"] == "failed"
    assert snapshot["run"]["error"] == state["error"]
    assert snapshot["progress"] == {
        "total": 2,
        "completed": 1,
        "running": 0,
        "failed": 0,
        "skipped": 0,
        "pending": 1,
    }
    assert steps["DraftPlan"]["status"] == "pending"
    assert steps["DraftPlan"]["summary"] == "pending"
    assert steps["DraftPlan"]["current_visit_count"] is None
    assert "in progress" not in markdown
    assert error_type in markdown


def test_snapshot_preserves_historical_provider_session_quarantine_read_only_compatibility(
    tmp_path: Path,
):
    run_root = tmp_path / ".orchestrate" / "runs" / "run-session"
    (run_root / "logs").mkdir(parents=True)
    metadata_path = run_root / "provider_sessions" / "root.askprovider__v1.json"
    transport_spool_path = run_root / "provider_sessions" / "root.askprovider__v1.transport.log"

    workflow = HISTORICAL_OBSERVABILITY_BUNDLES['obs-provider-session']
    state = {
        "run_id": "run-session",
        "status": "failed",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:05+00:00",
        "workflow_file": "workflows/test.yaml",
        "error": {
            "type": "provider_session_interrupted_visit_quarantined",
            "message": "An interrupted provider-session visit was quarantined.",
            "context": {
                "metadata_path": str(metadata_path),
                "transport_spool_path": str(transport_spool_path),
            },
        },
        "steps": {
            "AskProvider": {
                "status": "failed",
                "exit_code": 2,
                "debug": {
                    "provider_session": {
                        "mode": "fresh",
                        "session_id": "sess-123",
                        "metadata_path": str(metadata_path),
                        "publication_state": "suppressed_failure",
                    }
                },
            }
        },
    }
    state_file = run_root / "state.json"
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")
    state_bytes_before = state_file.read_bytes()

    snapshot = build_status_snapshot(workflow, state, run_root)
    md = render_status_markdown(snapshot)

    assert state_file.read_bytes() == state_bytes_before
    assert snapshot["run"]["error"]["type"] == "provider_session_interrupted_visit_quarantined"
    assert snapshot["steps"][0]["output"]["provider_session"]["metadata_path"] == str(metadata_path)
    assert "provider_session_interrupted_visit_quarantined" in md
    assert str(metadata_path) in md


def test_snapshot_and_markdown_surface_variant_and_snapshot_summaries(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "variant-snapshot-report"
    (run_root / "logs").mkdir(parents=True)

    workflow = HISTORICAL_OBSERVABILITY_BUNDLES['variant-snapshot-report']
    state = {
        "run_id": "variant-snapshot-report",
        "status": "completed",
        "started_at": "2026-05-08T00:00:00+00:00",
        "updated_at": "2026-05-08T00:00:05+00:00",
        "workflow_file": "workflow.yaml",
        "steps": {
            "ExecuteImplementation": {
                "status": "completed",
                "exit_code": 0,
                "snapshots": {
                    "implementation_outcome_before": {
                        "schema": "snapshot_diff/v1",
                        "candidates": {
                            "COMPLETED": {
                                "path": "artifacts/work/execution_report.md",
                                "existed_before": False,
                                "exists_now": True,
                                "changed": True,
                            },
                            "BLOCKED": {
                                "path": "artifacts/work/progress_report.md",
                                "existed_before": False,
                                "exists_now": False,
                                "changed": False,
                            },
                        },
                    }
                },
            },
            "SelectImplementationOutcome": {
                "status": "completed",
                "exit_code": 0,
                "artifacts": {
                    "implementation_state": "COMPLETED",
                    "execution_report_path": "artifacts/work/execution_report.md",
                },
                "debug": {
                    "select_variant_output": {
                        "selected_variant": "COMPLETED",
                        "changed_candidate_keys": ["COMPLETED"],
                    }
                },
            },
        },
    }

    snapshot = build_status_snapshot(workflow, state, run_root)
    steps = {entry["name"]: entry for entry in snapshot["steps"]}

    assert steps["ExecuteImplementation"]["output"]["snapshots"] == {
        "implementation_outcome_before": {
            "schema": "snapshot_diff/v1",
            "candidate_count": 2,
            "changed_candidates": ["COMPLETED"],
        }
    }
    assert steps["SelectImplementationOutcome"]["output"]["selected_variant"] == "COMPLETED"

    markdown = render_status_markdown(snapshot)

    assert "selected_variant: `COMPLETED`" in markdown
    assert "implementation_outcome_before" in markdown
