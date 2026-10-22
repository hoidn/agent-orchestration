from __future__ import annotations

import json
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from orchestrator.cli.main import main
from orchestrator.cli.commands.report import report_workflow
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from orchestrator.host_input import answer, pending
from orchestrator.monitor.ledger import NotificationLedger
from orchestrator.monitor.models import (
    EmailConfig, MonitorConfig, MonitorTiming, MonitorWorkspace,
)
from orchestrator.state import RunState, StateManager
from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.workflow_evaluated_host_input_helpers import files, resume, rows, start


def test_suspended_host_projection_roundtrips_through_run_state(tmp_path, monkeypatch):
    _, result = start(tmp_path, monkeypatch)

    view = load_evaluated_view(result.run_root)
    assert view["pending_host_input"] == pending(result.run_root)
    state = StateManager(tmp_path, result.run_root.name).load()

    assert view["status"] == state.status == "suspended"
    assert state.pending_host_input == view["pending_host_input"]
    assert state.to_dict() == view


def test_input_cli_reads_then_answers_without_resuming(tmp_path, monkeypatch, capsys):
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    before = (result.run_root / "memo.jsonl").read_bytes()

    assert main(["input", "get", result.run_root.name]) == 0
    assert json.loads(capsys.readouterr().out) == request
    assert (result.run_root / "memo.jsonl").read_bytes() == before

    assert main([
        "input", "answer", result.run_root.name, request["request_id"],
        "--value", '"APPROVED"', "--by", "alice",
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "variant": "ANSWERED", "value": "APPROVED", "by": "alice",
    }
    assert load_evaluated_view(result.run_root)["status"] == "interrupted"
    assert (tmp_path / "dispatches.txt").read_text().splitlines() == ["emit"]


def test_invalidated_pending_host_start_is_not_reported_running_before_resume(
    tmp_path, monkeypatch, capsys,
):
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    producer = next(
        row for row in rows(result.run_root)
        if row["record"] == "committed" and row["effect_class"] == "command"
    )

    assert main(["invalidate", result.run_root.name, producer["identity"]]) == 0
    capsys.readouterr()
    after_invalidate = files(tmp_path)

    view = load_evaluated_view(result.run_root)
    assert view["status"] == "interrupted"
    assert view.get("pending_host_input") is None
    assert view["current_step"] is None and view["next_effect"] is not None
    assert view["steps"][request["identity"]]["status"] == "invalidated"

    assert report_workflow(
        result.run_root.name, runs_root=str(result.run_root.parent), format="json"
    ) == 0
    report = json.loads(capsys.readouterr().out)
    request_step = next(step for step in report["steps"] if step["kind"] == "request_input")
    assert request_step["status"] == "invalidated"
    assert files(tmp_path) == after_invalidate


@pytest.mark.parametrize("raw", [
    '{"outer":{"key":1,"key":2}}', "NaN", "Infinity", "1e999",
])
def test_input_cli_rejects_non_strict_json_before_mutation(tmp_path, monkeypatch, capsys, raw):
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    before = files(result.run_root)

    assert main([
        "input", "answer", result.run_root.name, request["request_id"],
        "--value", raw, "--by", "alice",
    ]) == 2

    captured = capsys.readouterr()
    assert captured.out == "" and "host_input_answer_invalid" in captured.err
    assert files(result.run_root) == before


def test_input_cli_rejects_deeply_nested_json_without_traceback_or_writes(
    tmp_path, monkeypatch, capsys,
):
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    before = files(result.run_root)
    raw = "[" * 20_000 + "0" + "]" * 20_000

    assert main([
        "input", "answer", result.run_root.name, request["request_id"],
        "--value", raw, "--by", "alice",
    ]) == 2

    captured = capsys.readouterr()
    assert captured.out == "" and "host_input_answer_invalid" in captured.err
    assert "Traceback" not in captured.err
    assert files(result.run_root) == before


def test_input_cli_cancel_uses_custom_state_dir_and_evidence_override(tmp_path, monkeypatch, capsys):
    (tmp_path / "artifacts").mkdir()
    evidence = tmp_path / "artifacts" / "approval.txt"
    evidence.write_text("original")
    state_dir = tmp_path / "runs-outside-default"
    _, result = start(
        tmp_path,
        monkeypatch,
        state_dir=state_dir,
        options=":timeout-sec 60 :show (evidence)",
        declarations='(defpath Evidence :kind relpath :under "artifacts" :must-exist true)',
        params=" (evidence Evidence)",
        inputs=["question=<img src=x onerror=alert(1)>", "evidence=artifacts/approval.txt"],
    )
    request = pending(result.run_root)
    evidence.write_text("changed")

    assert main([
        "input", "cancel", result.run_root.name, request["request_id"],
        "--by", "alice", "--attestation", "ticket-9", "--accept-changed-evidence",
        "--state-dir", str(state_dir),
    ]) == 0
    assert json.loads(capsys.readouterr().out) == {"variant": "CANCELLED", "by": "alice"}
    commit = next(row for row in rows(result.run_root)
                  if row["record"] == "committed" and row["effect_class"] == "request_input")
    assert commit["host_reply"]["attestation"] == "ticket-9"
    assert commit["host_reply"]["accept_changed_evidence"] is True
    assert commit["host_reply"]["evidence_changes"][0]["path"] == "artifacts/approval.txt"
    assert load_evaluated_view(result.run_root)["status"] == "interrupted"
    assert resume(result.run_root, state_dir) == 0


@pytest.mark.parametrize("view_kind", ["missing", "stale", "malformed"])
def test_report_and_dashboard_rebuild_pending_request_readonly(tmp_path, monkeypatch, capsys, view_kind):
    (tmp_path / "artifacts").mkdir()
    evidence = tmp_path / "artifacts" / "approval.txt"
    evidence.write_text("private evidence body")
    _, result = start(
        tmp_path,
        monkeypatch,
        options=":timeout-sec 60 :show (evidence)",
        declarations='(defpath Evidence :kind relpath :under "artifacts" :must-exist true)',
        params=" (evidence Evidence)",
        inputs=["question=<img src=x onerror=alert(1)>", "evidence=artifacts/approval.txt"],
    )
    state_file = result.run_root / "state.json"
    if view_kind == "missing":
        state_file.unlink()
    elif view_kind == "stale":
        state_file.write_text('{"status":"completed","pending_host_input":{"question":"stale"}}')
    else:
        state_file.write_text("not JSON")
    before = files(tmp_path)
    request = pending(result.run_root)

    assert report_workflow(result.run_root.name, runs_root=str(result.run_root.parent), format="json") == 0
    report = json.loads(capsys.readouterr().out)
    assert report["run"]["status"] == "suspended"
    assert report["run"]["pending_host_input"] == request

    assert report_workflow(result.run_root.name, runs_root=str(result.run_root.parent), format="md") == 0
    markdown = capsys.readouterr().out
    assert request["request_id"] in markdown and "artifacts/approval.txt" in markdown

    detail = DashboardApp(RunScanner([tmp_path])).handle("GET", f"/runs/w0/{result.run_root.name}")
    page = detail.body.decode()
    assert detail.status == 200
    assert request["request_id"] in page and "artifacts/approval.txt" in page
    assert "&lt;img src=x onerror=alert(1)&gt;" in page and "<img src=x onerror=alert(1)>" not in page
    assert "files/workspace/artifacts/approval.txt" in page
    assert "private evidence body" not in page and "stale" not in page
    assert files(tmp_path) == before


def test_dashboard_shows_frozen_evidence_digest_when_view_and_file_are_missing(
    tmp_path, monkeypatch,
):
    (tmp_path / "artifacts").mkdir()
    evidence = tmp_path / "artifacts" / "approval.txt"
    evidence.write_text("original private body")
    _, result = start(
        tmp_path,
        monkeypatch,
        options=":timeout-sec 60 :show (evidence)",
        declarations='(defpath Evidence :kind relpath :under "artifacts" :must-exist true)',
        params=" (evidence Evidence)",
        inputs=["question=Review", "evidence=artifacts/approval.txt"],
    )
    request = pending(result.run_root)
    frozen_digest = request["show"][0]["sha256"]
    (result.run_root / "state.json").unlink()
    evidence.unlink()
    before = files(tmp_path)

    detail = DashboardApp(RunScanner([tmp_path])).handle(
        "GET", f"/runs/w0/{result.run_root.name}"
    )
    page = detail.body.decode()

    assert detail.status == 200
    assert "artifacts/approval.txt" in page and frozen_digest in page
    assert "original private body" not in page
    assert files(tmp_path) == before


def test_report_and_dashboard_show_sanitized_host_settlement(tmp_path, monkeypatch, capsys):
    _, result = start(tmp_path, monkeypatch)
    request = pending(result.run_root)
    answer(result.run_root, request["request_id"], "APPROVED", by="reviewer",
           attestation="private-ticket-7", workspace=tmp_path)

    assert report_workflow(result.run_root.name, runs_root=str(result.run_root.parent), format="json") == 0
    report = json.loads(capsys.readouterr().out)
    request_step = next(step for step in report["steps"] if step["kind"] == "request_input")
    assert request_step["host_reply"]["attestation"] == "private-ticket-7"
    assert request_step["value"]["by"] == "reviewer"
    assert request_step["host_settlement"]["settled_at"]

    assert report_workflow(result.run_root.name, runs_root=str(result.run_root.parent), format="md") == 0
    markdown = capsys.readouterr().out
    assert "reviewer" in markdown and "ANSWERED" in markdown and "settled_at" in markdown
    assert "private-ticket-7" not in markdown

    detail = DashboardApp(RunScanner([tmp_path])).handle(
        "GET", f"/runs/w0/{result.run_root.name}/steps/{quote(request['identity'], safe='')}"
    )
    page = detail.body.decode()
    assert detail.status == 200 and "reviewer" in page and "ANSWERED" in page
    assert "private-ticket-7" not in page


def test_monitor_notifies_once_per_sequential_host_request(tmp_path, monkeypatch):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts" / "approval.txt").write_text("runtime-doc-marker-DF91")
    declarations = '(defpath Evidence :kind relpath :under "artifacts" :must-exist true) '
    declarations += '(defprompt approval-question (:fills (report :doc Evidence)) -> Approval "Approve?")'
    body = '(let* ((first (request-input (approval-question :report evidence) '
    body += ':returns Approval :timeout-sec 60 :show (evidence))) '
    body += '(second (request-input (approval-question :report evidence) '
    body += ':returns Approval :timeout-sec 60 :show (evidence)))) second)'
    _, result = start(
        tmp_path, monkeypatch, body=body,
        declarations=declarations,
        params=" (evidence Evidence)", inputs=["evidence=artifacts/approval.txt"],
    )
    config = MonitorConfig(
        workspaces=(MonitorWorkspace("repo", tmp_path),),
        monitor=MonitorTiming(poll_interval_seconds=1, stale_after_seconds=1),
        email=EmailConfig(
            backend="smtp", from_address="monitor@example.com", to=("owner@example.com",),
            smtp_host="smtp.example.com",
        ),
    )

    class RecordingEmailer:
        def __init__(self):
            self.messages = []

        def send(self, message, *, dry_run=False):
            self.messages.append(message)
            return SimpleNamespace(sent=True, preview="")

    sender = RecordingEmailer()
    ledger_path = tmp_path.parent / f"{tmp_path.name}-monitor-ledger.json"
    ledger = NotificationLedger.load(ledger_path)
    try:
        from orchestrator.cli.commands.monitor import _scan_and_notify

        assert _scan_and_notify(config, ledger, sender, dry_run=False, mark_dry_run_sent=False) == 1
        first = pending(result.run_root)
        body_text = sender.messages[0].get_content()
        assert first["request_id"] in body_text
        assert "runtime-doc-marker-DF91" in first["question"]
        assert "runtime-doc-marker-DF91" not in body_text and "Question:" not in body_text
        assert "input get" in body_text and "--value JSON --by PRINCIPAL" in body_text
        assert "private-ticket-7" not in body_text and "artifacts/" not in body_text
        before = files(result.run_root)

        assert _scan_and_notify(config, ledger, sender, dry_run=False, mark_dry_run_sent=False) == 0
        assert len(sender.messages) == 1 and files(result.run_root) == before

        with monkeypatch.context() as clock:
            clock.setattr("orchestrator.workflow.evaluated.host_input.time.time",
                          lambda: first["deadline"] + 1)
            assert pending(result.run_root)["deadline_elapsed"] is True
            assert _scan_and_notify(config, ledger, sender, dry_run=False, mark_dry_run_sent=False) == 0
            assert len(sender.messages) == 1 and files(result.run_root) == before

        answer(result.run_root, first["request_id"], "APPROVED", by="reviewer",
               attestation="private-ticket-7", workspace=tmp_path)
        from tests.workflow_evaluated_host_input_helpers import resume
        assert resume(result.run_root) == 0
        second = pending(result.run_root)
        assert second["request_id"] != first["request_id"]
        assert _scan_and_notify(config, ledger, sender, dry_run=False, mark_dry_run_sent=False) == 1
        assert len(sender.messages) == 2
        second_body = sender.messages[1].get_content()
        assert second["request_id"] in second_body
        assert "runtime-doc-marker-DF91" in second["question"]
        assert "runtime-doc-marker-DF91" not in second_body
        assert "private-ticket-7" not in second_body
        assert _scan_and_notify(config, ledger, sender, dry_run=False, mark_dry_run_sent=False) == 0
        assert len(sender.messages) == 2
        reloaded = NotificationLedger.load(ledger_path)
        payload = json.loads(ledger_path.read_text())
        suspended = [entry for entry in payload["sent"] if entry["event_kind"] == "SUSPENDED"]
        assert {entry["request_id"] for entry in suspended} == {first["request_id"], second["request_id"]}
    finally:
        ledger_path.unlink(missing_ok=True)
