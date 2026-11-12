"""Tests for report CLI command."""

import json
from pathlib import Path

from orchestrator.cli.commands.report import report_workflow
from orchestrator.cli.main import create_parser
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _completed_run, _tree_bytes
from tests.test_workflow_evaluated_readers import _pure_run


def test_parser_supports_report_subcommand():
    parser = create_parser()
    args = parser.parse_args(["report", "--run-id", "abc", "--format", "json"])

    assert args.command == "report"
    assert args.run_id == "abc"
    assert args.format == "json"


def test_report_prints_markdown_for_explicit_run(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_root = _pure_run(tmp_path)

    result = report_workflow(
        run_id=run_root.name,
        runs_root=str(run_root.parent),
        format="md",
    )

    assert result == 0
    out = capsys.readouterr().out
    assert "# Workflow Status" in out
    assert run_root.name in out


def test_report_defaults_to_latest_run(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    first = _pure_run(tmp_path)
    result = _run_cli(tmp_path, str(tmp_path / "evaluated" / "inputs.orc"), "--input", "score=0.75")
    assert result.returncode == 0, result.stderr
    names = sorted(path.name for path in first.parent.iterdir())
    assert len(names) == 2

    result = report_workflow(runs_root=str(first.parent), format="md")

    assert result == 0
    out = capsys.readouterr().out
    assert names[-1] in out
    assert names[0] not in out


def test_report_supports_json_format(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_root = _completed_run(tmp_path)

    result = report_workflow(
        run_id=run_root.name,
        runs_root=str(run_root.parent),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["run_id"] == run_root.name
    assert payload["steps"][0]["kind"] == "command"


def test_report_writes_output_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_root = _pure_run(tmp_path)

    output_path = tmp_path / "report.md"
    result = report_workflow(
        run_id=run_root.name,
        runs_root=str(run_root.parent),
        format="md",
        output=str(output_path),
    )

    assert result == 0
    assert output_path.exists()
    assert "# Workflow Status" in output_path.read_text()


def _retired_run(runs_root: Path, run_id: str) -> Path:
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text(
        json.dumps({"run_id": run_id, "status": "completed", "workflow_file": "RETIRED-MARKER.yaml"}),
        encoding="utf-8",
    )
    return run_dir


def test_report_refuses_retired_run_with_one_line(tmp_path):
    runs_root = tmp_path / ".orchestrate" / "runs"
    _retired_run(runs_root, "20250101T000000Z-retired")
    before = _tree_bytes(tmp_path)

    for format in ("md", "json"):
        result = _cli(tmp_path, "report", "--run-id", "20250101T000000Z-retired", "--format", format)

        assert result.returncode == 2
        assert result.stdout == ""
        assert result.stderr == (
            "Error: workflow_execution_profile_retired: run 20250101T000000Z-retired was written by the "
            "retired runtime; report and the dashboard read evaluated runs only "
            "(old readers: git tag archive/retired-run-readers-2026-11-11)\n"
        )
    assert _tree_bytes(tmp_path) == before


def test_report_latest_skips_retired_runs(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_root = _pure_run(tmp_path)
    _retired_run(run_root.parent, "99991231T235959Z-retired")

    result = report_workflow(runs_root=str(run_root.parent), format="json")

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["run_id"] == run_root.name
