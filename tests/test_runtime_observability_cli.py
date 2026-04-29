from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.runtime_observability import compute_active_runtime
from orchestrator.state import StateManager


def _write_workflow(workspace: Path) -> Path:
    workflow = workspace / "workflow.yaml"
    workflow.write_text(
        "\n".join(
            [
                'version: "1.1"',
                "name: runtime-cli-test",
                "steps:",
                "  - name: Step1",
                '    command: ["bash", "-lc", "true"]',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return workflow


def _run_args(workflow: Path) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        dry_run=False,
        debug=False,
        quiet=False,
        verbose=False,
        log_level="info",
        backup_state=False,
        state_dir=None,
        on_error="stop",
        max_retries=0,
        retry_delay=1000,
        stream_output=False,
        step_summaries=False,
        summary_mode=None,
        summary_timeout_sec=120,
        summary_max_input_chars=12000,
        summary_provider="claude_sonnet_summary",
    )


def _latest_state(workspace: Path) -> dict:
    runs_root = workspace / ".orchestrate" / "runs"
    run_dir = sorted(path for path in runs_root.iterdir() if path.is_dir())[-1]
    return json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


def test_run_workflow_records_closed_executor_session(tmp_path: Path, monkeypatch):
    workflow = _write_workflow(tmp_path)
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.run.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        result = run_workflow(_run_args(workflow))

    state = _latest_state(tmp_path)
    sessions = state["runtime_observability"]["executor_sessions"]
    assert result == 0
    assert len(sessions) == 1
    assert sessions[0]["entrypoint"] == "run"
    assert sessions[0]["status"] == "completed"
    assert isinstance(sessions[0]["duration_ms"], int)


def test_resume_workflow_records_second_session_and_excludes_gap(tmp_path: Path, monkeypatch):
    workflow = _write_workflow(tmp_path)
    manager = StateManager(tmp_path, run_id="resume-runtime")
    state = manager.initialize("workflow.yaml")
    state.status = "failed"
    state.updated_at = "2026-04-29T10:20:00+00:00"
    state.runtime_observability = {
        "schema_version": 1,
        "executor_sessions": [
            {
                "session_id": "exec-0001",
                "entrypoint": "run",
                "pid": 111,
                "process_start_time": "old",
                "started_at": "2026-04-29T10:00:00+00:00",
                "ended_at": "2026-04-29T10:20:00+00:00",
                "status": "failed",
                "duration_ms": 1_200_000,
            }
        ],
    }
    manager._write_state()
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.resume.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        result = resume_workflow(run_id="resume-runtime")

    persisted = json.loads(
        (tmp_path / ".orchestrate" / "runs" / "resume-runtime" / "state.json").read_text(
            encoding="utf-8"
        )
    )
    sessions = persisted["runtime_observability"]["executor_sessions"]
    runtime = compute_active_runtime(persisted)

    assert result == 0
    assert [session["entrypoint"] for session in sessions] == ["run", "resume"]
    assert sessions[1]["status"] == "completed"
    assert runtime["active_runtime_ms"] >= 1_200_000
    assert runtime["active_runtime_ms"] < runtime["excluded_suspended_ms"]
