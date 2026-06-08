"""Regression tests for durable runtime failure evidence."""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from orchestrator.cli.commands.report import report_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.loader import WorkflowLoader
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor


def _run_args(workflow_path: Path) -> Namespace:
    runs_root = workflow_path.parent / "runs"
    return Namespace(
        workflow=str(workflow_path),
        context=None,
        context_file=None,
        clean_processed=False,
        archive_processed=None,
        debug=False,
        stream_output=False,
        dry_run=False,
        backup_state=False,
        state_dir=str(runs_root),
        on_error="stop",
        max_retries=0,
        retry_delay=1000,
        quiet=True,
        verbose=False,
        log_level="info",
        step_summaries=False,
        summary_mode=None,
        summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
    )


def test_executor_unexpected_exception_persists_error_and_current_step_context(
    tmp_path: Path,
):
    workflow_path = tmp_path / "crash.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1.1",
                "name": "crash-workflow",
                "steps": [
                    {
                        "name": "Crash",
                        "kind": "command",
                        "command": "echo should-not-matter",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    workflow = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="crash-run")
    state_manager.initialize("crash.yaml")
    executor = WorkflowExecutor(workflow, tmp_path, state_manager)

    def raise_runtime(*_args, **_kwargs):
        raise RuntimeError("synthetic executor crash")

    executor._run_top_level_step = raise_runtime

    with pytest.raises(RuntimeError, match="synthetic executor crash"):
        executor.execute(on_error="stop")

    persisted = json.loads(
        (state_manager.run_root / "state.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "failed"
    assert persisted["error"]["type"] == "executor_unhandled_exception"
    assert persisted["error"]["exception_type"] == "RuntimeError"
    assert "synthetic executor crash" in persisted["error"]["message"]
    assert "traceback" in persisted["error"]
    assert persisted["error"]["context"]["step_name"] == "Crash"
    assert persisted["error"]["context"]["step_id"]
    assert persisted["current_step"]["status"] == "failed"


def test_run_command_persists_unexpected_executor_exception(tmp_path: Path):
    workflow_path = tmp_path / "crash.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "1.1.1",
                "name": "cli-crash-workflow",
                "steps": [
                    {
                        "name": "Crash",
                        "kind": "command",
                        "command": "echo should-not-matter",
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    with patch("orchestrator.cli.commands.run.WorkflowExecutor.execute") as execute:
        execute.side_effect = RuntimeError("cli executor crash")
        exit_code = run_workflow(_run_args(workflow_path))

    assert exit_code == 1
    run_dirs = sorted((tmp_path / "runs").iterdir())
    persisted = json.loads(
        (run_dirs[-1] / "state.json").read_text(encoding="utf-8")
    )
    assert persisted["status"] == "failed"
    assert persisted["error"]["type"] == "cli_unhandled_exception"
    assert persisted["error"]["exception_type"] == "RuntimeError"
    assert "cli executor crash" in persisted["error"]["message"]
    assert "traceback" in persisted["error"]


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
    assert "Workflow definition could not be loaded" in captured.out
    assert "Workflow must be a YAML object/dictionary" not in captured.err
