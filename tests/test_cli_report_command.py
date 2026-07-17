"""Tests for report CLI command."""

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orchestrator.cli.commands.report import report_workflow
from orchestrator.cli.main import create_parser


def _write_run(runs_root: Path, run_id: str, workflow_text: str | None = None) -> Path:
    run_dir = runs_root / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True)

    workflow = run_dir.parent.parent.parent / "workflow.yaml"
    workflow.write_text(
        (workflow_text or """
version: "1.3"
name: report-test
steps:
  - name: StepA
    command: ["echo", "hello"]
""").strip()
        + "\n"
    )

    state = {
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow),
        "workflow_checksum": "sha256:dummy",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": "2026-02-27T00:00:01+00:00",
        "status": "running",
        "context": {},
        "steps": {
            "StepA": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 7,
                "output": "ok",
            }
        },
    }
    (run_dir / "state.json").write_text(json.dumps(state, indent=2))
    return run_dir


def test_parser_supports_report_subcommand():
    parser = create_parser()
    args = parser.parse_args(["report", "--run-id", "abc", "--format", "json"])

    assert args.command == "report"
    assert args.run_id == "abc"
    assert args.format == "json"


def test_report_prints_markdown_for_explicit_run(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    _write_run(runs_root, "20260227T000001Z-aaaaaa")

    result = report_workflow(
        run_id="20260227T000001Z-aaaaaa",
        runs_root=str(runs_root),
        format="md",
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "# Workflow Status" in out
    assert "20260227T000001Z-aaaaaa" in out


def test_report_defaults_to_latest_run(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    _write_run(runs_root, "20260227T000001Z-aaaaaa")
    _write_run(runs_root, "20260227T000002Z-bbbbbb")

    result = report_workflow(runs_root=str(runs_root), format="md")

    assert result == 0
    out = capsys.readouterr().out
    assert "20260227T000002Z-bbbbbb" in out


def test_report_supports_json_format(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    _write_run(runs_root, "20260227T000003Z-cccccc")

    result = report_workflow(
        run_id="20260227T000003Z-cccccc",
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["run_id"] == "20260227T000003Z-cccccc"


def test_report_persisted_yaml_read_emits_no_authoring_deprecation(
    tmp_path,
    capsys,
    caplog,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000003Z-persistedyaml"
    _write_run(runs_root, run_id)

    with caplog.at_level(
        logging.WARNING,
        logger="orchestrator.loader.yaml_deprecation",
    ):
        result = report_workflow(
            run_id=run_id,
            runs_root=str(runs_root),
            format="json",
        )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["run_id"] == run_id
    assert [
        record
        for record in caplog.records
        if record.name == "orchestrator.loader.yaml_deprecation"
    ] == []


def test_report_json_surfaces_typed_terminal_observability_summary_read_only(
    tmp_path, capsys, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000003Z-typedterminal"
    run_dir = _write_run(runs_root, run_id)
    summaries = run_dir / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "typed-terminal-summary.json").write_text(
        json.dumps(
            {
                "schema_id": "workflow_lisp_observability_summary.v1",
                "authority": "observability_only",
                "paths": {
                    "json": "summaries/typed-terminal-summary.json",
                    "markdown": "summaries/typed-terminal-summary.md",
                    "report": "summaries/observability_summary_report.json",
                },
                "terminal_value": {"status": "BLOCKED"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (summaries / "typed-terminal-summary.md").write_text("typed terminal summary\n", encoding="utf-8")
    (summaries / "observability_summary_report.json").write_text(
        json.dumps(
            {
                "schema_id": "workflow_lisp_observability_summary_report.v1",
                "status": "pass",
                "diagnostics": {"errors": [], "warnings": []},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    state_file = run_dir / "state.json"
    state_payload = json.loads(state_file.read_text(encoding="utf-8"))
    state_payload["status"] = "completed"
    state_file.write_text(json.dumps(state_payload, indent=2), encoding="utf-8")
    before = state_file.read_text(encoding="utf-8")

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    typed_terminal = payload["run"]["observability_summaries"]["typed_terminal"]
    assert typed_terminal["authority"] == "observability_only"
    assert typed_terminal["payload_path"] == "summaries/typed-terminal-summary.json"
    assert typed_terminal["summary_path"] == "summaries/typed-terminal-summary.md"
    assert typed_terminal["report_path"] == "summaries/observability_summary_report.json"
    assert state_file.read_text(encoding="utf-8") == before


def test_report_writes_output_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    _write_run(runs_root, "20260227T000004Z-dddddd")

    output_path = tmp_path / "report.md"
    result = report_workflow(
        run_id="20260227T000004Z-dddddd",
        runs_root=str(runs_root),
        format="md",
        output=str(output_path),
    )

    assert result == 0
    assert output_path.exists()
    assert "# Workflow Status" in output_path.read_text()


def test_report_reconciles_stale_running_state_on_disk(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000005Z-eeeeee"
    run_dir = runs_root / run_id
    logs_dir = run_dir / "logs"
    logs_dir.mkdir(parents=True)

    workflow = tmp_path / "workflow.yaml"
    workflow.write_text(
        """
version: "1.3"
name: report-test
steps:
  - name: StepA
    command: ["echo", "a"]
  - name: StepB
    command: ["echo", "b"]
""".strip()
        + "\n"
    )

    stale_updated_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    state = {
        "schema_version": "1.1.1",
        "run_id": run_id,
        "workflow_file": str(workflow),
        "workflow_checksum": "sha256:dummy",
        "started_at": "2026-02-27T00:00:00+00:00",
        "updated_at": stale_updated_at,
        "status": "running",
        "context": {},
        "steps": {
            "StepA": {
                "status": "completed",
                "exit_code": 0,
                "duration_ms": 7,
                "output": "ok",
            }
        },
    }
    state_file = run_dir / "state.json"
    state_file.write_text(json.dumps(state, indent=2))

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["status"] == "failed"
    assert payload["run"]["status_reason"] == "stale_running_without_current_step"

    persisted = json.loads(state_file.read_text())
    assert persisted["status"] == "failed"
    assert persisted["context"]["status_reconciled_reason"] == "stale_running_without_current_step"


def test_report_json_includes_advisory_lint_warnings(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000006Z-ffffff"
    _write_run(
        runs_root,
        run_id,
        workflow_text="""
version: "1.4"
name: lint-report
steps:
  - name: CheckReady
    command: ["bash", "-lc", "test -f state/ready.txt"]
""",
    )

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["lint"]["warnings"][0]["code"] == "shell-gate-to-assert"


def test_report_markdown_appends_advisory_lint_section(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000007Z-gggggg"
    _write_run(
        runs_root,
        run_id,
        workflow_text="""
version: "1.4"
name: lint-report
steps:
  - name: CheckReady
    command: ["bash", "-lc", "test -f state/ready.txt"]
""",
    )

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="md",
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "## Advisory Lint" in out
    assert "CheckReady" in out


def test_report_markdown_surfaces_provider_session_quarantine_context(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000008Z-hhhhhh"
    run_dir = _write_run(
        runs_root,
        run_id,
        workflow_text="""
version: "2.10"
name: report-provider-session
steps:
  - name: AskProvider
    provider: codex
    provider_session:
      mode: fresh
      publish_artifact: implementation_session_id
artifacts:
  implementation_session_id:
    kind: scalar
    type: string
""",
    )
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    metadata_path = run_dir / "provider_sessions" / "root.askprovider__v1.json"
    transport_spool_path = run_dir / "provider_sessions" / "root.askprovider__v1.transport.log"
    metadata_path.parent.mkdir(parents=True)
    metadata_path.write_text("{}", encoding="utf-8")
    transport_spool_path.write_text("", encoding="utf-8")
    state["status"] = "failed"
    state["error"] = {
        "type": "provider_session_interrupted_visit_quarantined",
        "message": "An interrupted provider-session visit was quarantined.",
        "context": {
            "metadata_path": str(metadata_path),
            "transport_spool_path": str(transport_spool_path),
        },
    }
    state["steps"] = {
        "AskProvider": {
            "status": "failed",
            "exit_code": 2,
            "debug": {
                "provider_session": {
                    "mode": "fresh",
                    "metadata_path": str(metadata_path),
                    "publication_state": "suppressed_failure",
                }
            },
        }
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="md",
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "provider_session_interrupted_visit_quarantined" in out
    assert str(metadata_path) in out
