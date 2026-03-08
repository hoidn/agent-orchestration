"""Tests for report CLI command."""

import json
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
