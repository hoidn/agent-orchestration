from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import build_observability_config, run_workflow
from orchestrator.runtime_observability import compute_active_runtime
from orchestrator.state import StateManager


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CLI_FIXTURES = WORKFLOW_LISP_FIXTURES / "cli"
LISP_ENTRYPOINT = (
    WORKFLOW_LISP_FIXTURES
    / "modules"
    / "valid"
    / "imported_bundle_mix"
    / "neurips"
    / "entry.orc"
)
LISP_SOURCE_ROOT = WORKFLOW_LISP_FIXTURES / "modules" / "valid" / "imported_bundle_mix"


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
        summary_profile=None,
        live_agent_notes=False,
        live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0,
        live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000,
        entry_workflow=None,
        source_root=None,
        provider_externs_file=None,
        prompt_externs_file=None,
        imported_workflow_bundles_file=None,
        command_boundaries_file=None,
        emit_debug_yaml=False,
    )


def test_summary_config_default_timeout_preserves_existing_run_default():
    config = build_observability_config(
        Namespace(
            step_summaries=True,
            summary_mode=None,
            summary_profile=None,
            live_agent_notes=False,
            summary_max_input_chars=12000,
            summary_provider="claude_sonnet_summary",
        )
    )

    assert config["step_summaries"]["timeout_sec"] == 120


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


def test_run_workflow_persists_compiled_frontend_provenance_for_orc_runs(tmp_path: Path, monkeypatch):
    args = _run_args(LISP_ENTRYPOINT)
    args.entry_workflow = "orchestrate"
    args.source_root = [str(LISP_SOURCE_ROOT)]
    args.provider_externs_file = str(CLI_FIXTURES / "providers.json")
    args.prompt_externs_file = str(CLI_FIXTURES / "prompts.json")
    args.imported_workflow_bundles_file = str(CLI_FIXTURES / "imported_workflow_bundles.json")
    args.command_boundaries_file = str(CLI_FIXTURES / "commands.json")
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")
    args.input = [
        "input__status=ready",
        "input__report=artifacts/work/existing-report.md",
        "report_path=artifacts/work/existing-report.md",
    ]
    monkeypatch.chdir(tmp_path)

    with patch("orchestrator.cli.commands.run.WorkflowExecutor") as executor_cls:
        executor = MagicMock()
        executor.execute.return_value = {"status": "completed"}
        executor_cls.return_value = executor

        result = run_workflow(args)

    state = _latest_state(tmp_path)
    frontend = state["runtime_observability"]["compiled_frontend"]
    assert result == 0
    assert frontend["frontend_kind"] == "workflow_lisp"
    assert frontend["frontend_entry_workflow"] == "neurips/entry::orchestrate"
    assert frontend["frontend_build_root"].endswith("/")
    assert frontend["frontend_source_trace_path"].endswith("source_map.json")
    assert frontend["source_map_schema_version"] == "workflow_lisp_source_map.v1"
    assert frontend["source_map_coverage"] == {
        "frontend_ast": "covered",
        "lowered_surface": "covered",
        "shared_validation_subjects": "covered",
        "executable_ir": "covered",
        "runtime_logs": "covered",
        "core_workflow_ast": "covered",
        "semantic_ir": "covered",
    }
    assert "command_boundaries" not in frontend
    assert "core_nodes" not in frontend


def test_run_workflow_logs_compiled_frontend_source_context(
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    source_root = tmp_path / "runtime"
    source_root.mkdir()
    workflow = source_root / "entry.orc"
    workflow.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule runtime/entry)",
                "  (export orchestrate)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (status String)",
                "    (report WorkReport))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow orchestrate",
                "    ((input ChecksResult)",
                "     (report_path WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((remote",
                "             (call selector-run",
                "               :input input",
                "               :report_path report_path)))",
                "      (record ImplementationSummary",
                "        :report remote.report))))",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "artifacts" / "work" / "existing-report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("ok\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    args = _run_args(workflow)
    args.entry_workflow = "orchestrate"
    args.source_root = [str(tmp_path)]
    args.provider_externs_file = str(CLI_FIXTURES / "providers.json")
    args.prompt_externs_file = str(CLI_FIXTURES / "prompts.json")
    args.imported_workflow_bundles_file = str(CLI_FIXTURES / "imported_workflow_bundles.json")
    args.command_boundaries_file = str(CLI_FIXTURES / "commands.json")
    args.input = [
        "input__status=ready",
        "input__report=artifacts/work/existing-report.md",
        "report_path=artifacts/work/existing-report.md",
    ]

    with caplog.at_level("INFO", logger="orchestrator.workflow.executor"):
        result = run_workflow(args)

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert result == 1
    assert "Running step runtime/entry::orchestrate__remote__call_selector-run" in messages
    assert f"source: {workflow}" in messages
    assert "form: workflow-lisp > defworkflow > orchestrate" in messages
