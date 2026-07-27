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
    assert payload["steps"][0]["kind"] == "unknown"


def test_prompt_context_state_only_report_has_exact_additive_empty_projection(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260727T000000Z-prompt-context"
    _write_run(runs_root, run_id)

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert tuple(payload) == ("run", "progress", "steps", "prompt_context")
    assert payload["prompt_context"] == {
        "schema_version": "workflow_prompt_context_report.v1",
        "attempts": [],
    }


def test_report_reads_persisted_legacy_state_without_reopening_source(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000003Z-persistedyaml"
    _write_run(runs_root, run_id)

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["run"]["run_id"] == run_id


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
            },
            "StepB": {"status": "pending"},
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


def test_report_json_does_not_reopen_authored_source_for_lint(
    tmp_path, capsys, monkeypatch
):
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
    assert "lint" not in payload
    assert "state-only" in payload["run"]["report_warning"]


def test_report_markdown_identifies_state_only_projection(
    tmp_path, capsys, monkeypatch
):
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
    assert "## Advisory Lint" not in out
    assert "state-only report" in out


def test_state_only_report_infers_peer_group_kind_from_unique_persisted_debug(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000008Z-peergroup"
    run_dir = _write_run(runs_root, run_id)
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    evidence = {
        "report_path": "provider_peer_groups/visit/report.json",
        "ledger_path": "provider_peer_groups/visit/ledger.jsonl",
    }
    state["status"] = "completed"
    state["steps"] = {
        "PeerGroup": {
            "status": "completed",
            "step_id": "root.peer_group",
            "exit_code": 0,
            "debug": {"provider_peer_group": evidence},
        }
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    [step] = payload["steps"]
    assert step["kind"] == "provider_peer_group"
    assert step["output"]["debug"]["provider_peer_group"] == evidence


def test_state_only_report_prefers_explicit_persisted_type_over_debug(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000008Z-explicittype"
    run_dir = _write_run(runs_root, run_id)
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["status"] = "completed"
    state["steps"] = {
        "Explicit": {
            "status": "completed",
            "type": "provider_supervision",
            "exit_code": 0,
            "debug": {
                "provider_peer_group": {"report_path": "group.json"},
                "provider_supervision": {"selected_attempt": {"ordinal": 1}},
            },
        }
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    assert result == 0
    payload = json.loads(capsys.readouterr().out)
    [step] = payload["steps"]
    assert step["kind"] == "provider_supervision"


def test_state_only_report_rejects_ambiguous_debug_kind_discriminators(
    tmp_path,
    capsys,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    runs_root = tmp_path / ".orchestrate" / "runs"
    run_id = "20260227T000008Z-ambiguouskind"
    run_dir = _write_run(runs_root, run_id)
    state_file = run_dir / "state.json"
    state = json.loads(state_file.read_text(encoding="utf-8"))
    state["status"] = "completed"
    state["steps"] = {
        "Ambiguous": {
            "status": "completed",
            "exit_code": 0,
            "debug": {
                "provider_peer_group": {"report_path": "group.json"},
                "provider_supervision": {"selected_attempt": {"ordinal": 1}},
            },
        }
    }
    state_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result = report_workflow(
        run_id=run_id,
        runs_root=str(runs_root),
        format="json",
    )

    captured = capsys.readouterr()
    assert result == 1
    assert captured.out == ""
    assert (
        "ambiguous persisted step kind debug discriminators: "
        "provider_peer_group, provider_supervision"
    ) in captured.err


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
