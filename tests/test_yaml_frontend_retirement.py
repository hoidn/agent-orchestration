"""Focused contracts for retiring YAML from runtime-facing frontends."""

from __future__ import annotations

import json
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from orchestrator.cli.commands.report import report_workflow
from orchestrator.cli.commands.resume import (
    _load_resume_workflow_bundle,
    resume_workflow,
)
from orchestrator.cli.commands.run import run_workflow
from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.state import StateManager


def _run_args(workflow: Path) -> Namespace:
    return Namespace(
        workflow=str(workflow),
        context=None,
        context_file=None,
        input=None,
        input_file=None,
        clean_processed=False,
        archive_processed=None,
        dry_run=True,
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


def _write_minimal_orc(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.15")',
                "  (defmodule entry)",
                "  (export run)",
                "  (defrecord Result (ok Bool))",
                "  (defworkflow run",
                "    ()",
                "    -> Result",
                "    (record Result :ok true)))",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_run_state(
    workspace: Path,
    *,
    run_id: str,
    workflow_file: str,
    status: str,
    steps: dict[str, object] | None = None,
    schema_version: str = StateManager.SCHEMA_VERSION,
    updated_at: str = "2026-07-23T12:00:00+00:00",
) -> Path:
    run_root = workspace / ".orchestrate" / "runs" / run_id
    run_root.mkdir(parents=True)
    state = {
        "schema_version": schema_version,
        "run_id": run_id,
        "workflow_file": workflow_file,
        "workflow_checksum": "sha256:retired-source",
        "started_at": "2026-07-23T11:00:00+00:00",
        "updated_at": updated_at,
        "status": status,
        "context": {},
        "steps": steps or {},
    }
    state_path = run_root / "state.json"
    state_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    return state_path


def _run_tree_snapshot(run_root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(run_root).as_posix(): path.read_bytes()
        for path in run_root.rglob("*")
        if path.is_file()
    }


def test_run_rejects_non_orc_before_creating_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    workflow = tmp_path / "legacy.YmL"
    workflow.write_text("not: parsed\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_run_args(workflow))

    assert result == 1
    assert ".orc required" in caplog.text
    assert not (tmp_path / ".orchestrate").exists()


def test_run_accepts_case_insensitive_orc_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _write_minimal_orc(tmp_path / "entry.ORC")
    monkeypatch.chdir(tmp_path)

    result = run_workflow(_run_args(workflow))

    assert result == 0
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_completed_legacy_resume_is_state_only_noop_when_source_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_run_state(
        tmp_path,
        run_id="completed-legacy",
        workflow_file="retired.yaml",
        status="completed",
        schema_version="1.1.1",
    )
    monkeypatch.chdir(tmp_path)

    result = resume_workflow("completed-legacy")

    assert result == 0
    assert "already completed successfully" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("status", "force_restart", "schema_version"),
    [
        ("failed", False, "1.1.1"),
        ("completed", True, StateManager.SCHEMA_VERSION),
    ],
)
def test_resume_rejects_executable_legacy_runs_with_orc_required(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: str,
    force_restart: bool,
    schema_version: str,
) -> None:
    state_path = _write_run_state(
        tmp_path,
        run_id="legacy-execution",
        workflow_file="retired.YAML",
        status=status,
        schema_version=schema_version,
    )
    run_root = state_path.parent
    before = _run_tree_snapshot(run_root)
    monkeypatch.chdir(tmp_path)

    result = resume_workflow("legacy-execution", force_restart=force_restart)

    assert result == 1
    assert ".orc required" in capsys.readouterr().err
    assert _run_tree_snapshot(run_root) == before


def test_force_restart_orc_without_process_metadata_uses_frontend_build(
    tmp_path: Path,
) -> None:
    workflow = _write_minimal_orc(tmp_path / "entry.ORC")
    run_root = tmp_path / ".orchestrate" / "runs" / "missing-metadata"
    run_root.mkdir(parents=True)

    loaded = _load_resume_workflow_bundle(
        workflow_path=workflow,
        workspace_dir=tmp_path,
        run_root=run_root,
        force_restart=True,
    )

    assert loaded.lowering_schema_version is not None
    assert loaded.bundle.surface.name == "entry::run"


def test_report_uses_state_only_when_legacy_source_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_run_state(
        tmp_path,
        run_id="legacy-report",
        workflow_file="deleted.yaml",
        status="failed",
        steps={
            "PersistedStep": {
                "status": "failed",
                "step_id": "root.persisted",
                "error": {"message": "persisted failure"},
            }
        },
    )
    monkeypatch.chdir(tmp_path)

    result = report_workflow(
        run_id="legacy-report",
        runs_root=str(tmp_path / ".orchestrate" / "runs"),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["display_status"] == "failed"
    assert [step["name"] for step in payload["steps"]] == ["PersistedStep"]
    assert "state-only" in payload["run"]["report_warning"]


def test_report_state_only_projection_reconciles_stale_running_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    stale = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    state_path = _write_run_state(
        tmp_path,
        run_id="stale-legacy-report",
        workflow_file="deleted.yml",
        status="running",
        updated_at=stale,
        steps={"FailedStep": {"status": "failed", "error": {"message": "boom"}}},
    )
    monkeypatch.chdir(tmp_path)

    result = report_workflow(
        run_id="stale-legacy-report",
        runs_root=str(tmp_path / ".orchestrate" / "runs"),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["display_status"] == "failed"
    assert payload["run"]["display_status_reason"] == (
        "stale_running_terminal_not_finalized"
    )
    persisted = json.loads(state_path.read_text(encoding="utf-8"))
    assert persisted["status"] == "failed"
    assert persisted["context"]["status_reconciled_reason"] == (
        "stale_running_terminal_not_finalized"
    )


def test_dashboard_degrades_non_orc_run_without_reading_authored_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "workflows" / "legacy.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("this: [is: not: valid\n", encoding="utf-8")
    _write_run_state(
        tmp_path,
        run_id="legacy-dashboard",
        workflow_file=str(source.relative_to(tmp_path)),
        status="failed",
        steps={"PersistedStep": {"status": "failed", "error": {"message": "boom"}}},
    )
    run = RunScanner([tmp_path]).scan().runs[0]

    detail = RunProjector().project_detail(run)

    assert detail.degraded is True
    assert detail.workflow_structure is None
    assert detail.row.workflow_name is None
    assert [step.name for step in detail.steps] == ["PersistedStep"]
    assert any("legacy authored workflow" in warning for warning in detail.warnings)
    assert not any("failed to load workflow metadata" in warning for warning in detail.warnings)
