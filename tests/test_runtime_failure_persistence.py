"""Regression tests for durable runtime failure evidence."""

import json
from pathlib import Path

import pytest

from orchestrator.cli.commands.report import report_workflow


def test_report_handles_orc_run_state_without_yaml_loader_error(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
):
    workflow_path = tmp_path / "workflow.orc"
    workflow_path.write_text("(defworkflow placeholder () nil)\n", encoding="utf-8")
    run_root = tmp_path / "runs" / "orc-failed-run"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "schema_version": "2.1",
                "run_id": "orc-failed-run",
                "workflow_file": str(workflow_path),
                "status": "failed",
                "started_at": "2026-06-08T00:00:00+00:00",
                "updated_at": "2026-06-08T00:00:01+00:00",
                "steps": {},
                "current_step": {
                    "name": "ReviewLoop",
                    "step_id": "review.loop",
                    "status": "failed",
                },
                "error": {
                    "type": "executor_unhandled_exception",
                    "message": "synthetic failed .orc run",
                },
            }
        ),
        encoding="utf-8",
    )

    exit_code = report_workflow(
        run_id="orc-failed-run",
        runs_root=str(tmp_path / "runs"),
    )

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "orc-failed-run" in captured.out
    assert "failed" in captured.out
    assert "synthetic failed .orc run" in captured.out
    assert "showing a state-only report" in captured.out
    assert "Workflow must be a YAML object/dictionary" not in captured.err
