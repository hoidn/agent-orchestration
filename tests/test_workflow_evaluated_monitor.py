"""Monitor events and previews use evaluated authority and real writer locks."""

from dataclasses import replace
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

import pytest

from orchestrator.monitor.classifier import classify_run
from orchestrator.monitor.messages import render_event_email
from orchestrator.monitor.models import MonitorEventKind, MonitorWorkspace, ProcessMetadata
from orchestrator.monitor.scanner import scan_monitor_runs
from tests.test_monitor_messages_emailer import _config as _email_config
from tests.test_workflow_evaluated_readers import _pure_run, _scalar_run
from tests.test_workflow_evaluated_invalidate import _completed_run, _cli, _tree_bytes, _fixture as _command_fixture
from tests.test_workflow_evaluated_resume_kills import _write_command_case, _run_root
from tests.test_workflow_evaluated_view_publication import _live_writer, _wait_marker
from tests.test_workflow_evaluated_views import _forbid_mutable_paths
from tests.test_workflow_evaluated_providers import _fixture, _cli as _provider_cli, _requests
from tests.test_workflow_evaluated_view_publication import _provider_env
from tests.test_workflow_evaluated_dashboard import _corrupt_authority, _outputs, _detail as _dashboard_detail, _forbid_legacy
from tests.test_workflow_evaluated_run_ref import _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_evaluated_cli import _run_cli
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp


def _config(workspace):
    return replace(_email_config(), workspaces=(MonitorWorkspace("repo", workspace),))


def _scan(workspace):
    run, = scan_monitor_runs(_config(workspace))
    return run


def _forbidden(*_args, **_kwargs):
    pytest.fail("evaluated monitor reached legacy PID/heartbeat or mutable preparation")


def _observe(workspace, status):
    before = _tree_bytes(workspace)
    run = _scan(workspace)
    assert run.state["status"] == status and run.process is None
    event = classify_run(run, stale_after_seconds=1)
    assert _tree_bytes(workspace) == before
    return run, event


@pytest.mark.parametrize("kill_stage", ["first", "last"])
def test_monitor_real_writer_partial_tail_settling_and_immediate_kill(tmp_path, monkeypatch, kill_stage):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    with _live_writer(workspace, arguments) as (process, control):
        _wait_marker(process, control / "started")
        _forbid_mutable_paths(monkeypatch)
        monkeypatch.setattr("orchestrator.monitor.scanner.read_process_metadata", _forbidden)
        monkeypatch.setattr("orchestrator.monitor.classifier.process_identity_matches", _forbidden)
        initial, event = _observe(workspace, "running")
        assert event is None
        contradictory = replace(initial, process=ProcessMetadata(-1, "1970-01-01T00:00:00+00:00"))
        assert classify_run(contradictory, stale_after_seconds=1) is None
        (control / "started.release").touch()
        _wait_marker(process, control / "partial")
        partial, event = _observe(workspace, "running")
        assert event is None and partial.state["memo_offset"] == initial.state["memo_offset"]
        (control / "partial.release").touch()
        _wait_marker(process, control / "first")
        current, event = _observe(workspace, "running")
        assert event is None and current.state["next_effect"] is not None
        if kill_stage == "last":
            (control / "first.release").touch()
            _wait_marker(process, control / "last")
            current, event = _observe(workspace, "settling")
            assert event is None
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        _run, event = _observe(workspace, "interrupted")
        _assert_interrupted(event)


def test_scanned_terminal_refreshes_checked_authority_after_invalidate(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    stale = _scan(tmp_path)
    old_view = (run_root / "state.json").read_bytes()
    identity = list(stale.state["steps"])[1]
    result = _cli(tmp_path, "invalidate", run_root.name, identity)
    assert result.returncode == 0, result.stderr
    (run_root / "state.json").write_bytes(old_view)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    event = classify_run(stale, stale_after_seconds=1)
    assert event.kind is MonitorEventKind.CRASHED
    assert event.run.state["status"] == "interrupted"
    assert event.run.state["workflow_outputs"] is None
    assert event.run.state["next_effect"] == identity
    assert _tree_bytes(tmp_path) == before


def test_scanned_completed_view_never_survives_authority_removal(tmp_path, monkeypatch):
    run_root = _pure_run(tmp_path)
    stale = _scan(tmp_path)
    for name in ("run.json", "closed_program.json", "memo.jsonl"):
        (run_root / name).unlink()
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    assert classify_run(stale, stale_after_seconds=1) is None
    fresh = _scan(tmp_path)
    assert fresh.state is None and "memo_inconsistent" in fresh.read_error
    assert _tree_bytes(tmp_path) == before


def _assert_interrupted(event):
    assert event.kind is MonitorEventKind.CRASHED
    assert "lock" in event.reason and "interrupted" in event.reason


@pytest.mark.parametrize("returns,expression,value", [
    ("Int", "0", 0), ("Bool", "false", False), ("Optional[Int]", "null", None),
    ("List[Int]", "(list 1 2)", [1, 2]), ("List[Int]", "(list)", []),
])
def test_completed_monitor_message_preserves_direct_json_without_sources(tmp_path, monkeypatch, returns, expression, value):
    run_root = _scalar_run(tmp_path, returns, expression)
    (tmp_path / "scalar.orc").unlink()
    (tmp_path / "inputs.json").unlink(missing_ok=True)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "completed")
    assert event.kind is MonitorEventKind.COMPLETED
    body = render_event_email(event, _config(tmp_path)).get_content()
    output = _message_output(body)
    assert output == value and type(output) is type(value)
    assert "Heartbeat at:" not in body
    assert _tree_bytes(tmp_path) == before


def _message_output(body):
    assert "Workflow outputs:\n" in body
    return json.loads(body.split("Workflow outputs:\n", 1)[1].split("\n\nSuggested commands:", 1)[0])


def _provider_message(workspace, status, attempt):
    before = _tree_bytes(workspace)
    run, event = _observe(workspace, status)
    body = render_event_email(event, _config(workspace)).get_content()
    row, = run.state["steps"].values()
    assert f"Attempt: {attempt}" in body
    assert row["identity"] in body
    assert f"attempt-{attempt}/stderr.txt" in body
    assert "prompt.txt" not in body and "Heartbeat at:" not in body
    assert _tree_bytes(workspace) == before
    return body, row


def test_monitor_provider_retry_uses_latest_error_streams_and_preserves_old_attempt(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    binary = tmp_path / "bin" / "codex"
    binary.write_text(binary.read_text().replace('b"complete stderr\\n"',
        '("stream-" + mode + (" rate limit old" if mode == "nonzero" else " clean latest") + "\\n").encode()'))
    assert _provider_cli(tmp_path, fixture, mode="nonzero").returncode == 1
    run_root = _run_root(tmp_path)
    _forbid_mutable_paths(monkeypatch)
    _forbid_prompt_session_reads(monkeypatch)
    first_body, first = _provider_message(tmp_path, "failed", 1)
    assert "rate limit old" in first_body
    old = _tree_bytes(run_root / Path(first["result_path"]).parent)
    _provider_env(monkeypatch, tmp_path, "invalid")
    assert _cli(tmp_path, "resume", run_root.name).returncode == 1
    second_body, second = _provider_message(tmp_path, "failed", 2)
    _assert_latest_retry_error(first, second, second_body)
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    final_body, final = _provider_message(tmp_path, "completed", 3)
    assert "Error:" not in final_body and "rate limit old" not in final_body
    assert final["value"] == {"ok": True} and len(_requests(tmp_path)) == 3
    assert _tree_bytes(run_root / Path(first["result_path"]).parent) == old


def _assert_latest_retry_error(first, second, body):
    assert second["error"]["code"] != first["error"]["code"]
    assert second["error"]["code"] in body
    assert first["error"]["code"] not in body and "rate limit old" not in body
    assert "stream-invalid clean latest" in body


def _branch_run(workspace):
    source = workspace / "branch.orc"
    source.write_text("""(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule branch) (export run) (defworkflow run () -> Bool
        (let* ((choose (command-result choose :argv ("python" "choose.py") :returns Bool)))
          (if choose (command-result stale :argv ("python" "stale.py") :returns Bool) false))))""")
    scripts = {
        "choose": 'from pathlib import Path\nimport os\nvalue=Path("choice.txt").read_text()\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(value)\nprint("choose-stream-"+value)\n',
        "stale": 'from pathlib import Path\nimport os\nPath(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("true")\nprint("old-invalidated-stream")\n',
    }
    for name, text in scripts.items():
        (workspace / f"{name}.py").write_text(text)
    (workspace / "choice.txt").write_text("true")
    commands = workspace / "commands.json"
    commands.write_text(json.dumps({name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]} for name in scripts}))
    result = _cli(workspace, "run", str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    return _run_root(workspace)


def test_monitor_terminal_skips_old_invalidated_branch_streams(tmp_path, monkeypatch):
    run_root = _branch_run(tmp_path)
    initial = _scan(tmp_path)
    choose, stale = initial.state["steps"]
    old_root = run_root / Path(initial.state["steps"][stale]["result_path"]).parent
    old = _tree_bytes(old_root)
    assert _cli(tmp_path, "invalidate", run_root.name, choose).returncode == 0
    (tmp_path / "choice.txt").write_text("false")
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "completed")
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert run.state["steps"][stale]["status"] == "invalidated"
    assert "old-invalidated-stream" not in body
    assert f"Current/failed step: {choose}" in body and "Attempt: 2" in body
    assert _message_output(body) is False
    assert _tree_bytes(old_root) == old and _tree_bytes(tmp_path) == before


def test_monitor_stream_redaction_and_caps_use_real_command_output(tmp_path, monkeypatch):
    source, commands = _command_fixture(tmp_path, 20)
    script = tmp_path / "reader.py"
    script.write_text(script.read_text() + '\nimport sys\nprint("api_key=unconfigured-sensitive-value")\nprint("normal-env-credential-value")\nprint("stdout-visible" + "x" * 9000 + "stdout-beyond-cap")\nprint("stderr-visible" + "y" * 9000 + "stderr-beyond-cap", file=sys.stderr)\n')
    monkeypatch.setenv("SMTP_PASSWORD", "normal-env-credential-value")
    result = _cli(tmp_path, "run", str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "completed")
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert "stdout-visible" in body and "stderr-visible" in body
    assert "unconfigured-sensitive-value" not in body
    assert "normal-env-credential-value" not in body
    assert "stdout-beyond-cap" not in body and "stderr-beyond-cap" not in body
    _assert_stream_caps(body)
    assert _tree_bytes(tmp_path) == before


def _assert_stream_caps(body):
    sections = body.split("Log previews:\n", 1)[1].split("\n--- ")
    text = [section.split(" ---\n", 1)[1].rstrip("\n") for section in sections]
    assert all(len(value) <= 4096 for value in text)
    assert sum(map(len, text)) <= 8192


@pytest.mark.parametrize("corruption", ["unknown-schema", "unknown-profile", "missing-header", "bad-journal", "bad-terminal", "adjacent-terminal", "missing-authorities", "artifact"])
def test_monitor_corrupt_authority_is_visible_error_without_terminal_event(tmp_path, monkeypatch, corruption):
    run_root = _pure_run(tmp_path)
    if corruption == "missing-authorities":
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            (run_root / name).unlink()
    elif corruption == "artifact":
        (run_root / "closed_program.json").write_text("{}")
    else:
        _corrupt_authority(run_root, corruption)
    _forbid_mutable_paths(monkeypatch)
    monkeypatch.setattr("orchestrator.monitor.scanner.read_process_metadata", _forbidden)
    before = _tree_bytes(tmp_path)
    run = _scan(tmp_path)
    assert run.state is None and "memo_inconsistent" in run.read_error
    assert classify_run(run, stale_after_seconds=1) is None
    assert _tree_bytes(tmp_path) == before


def test_monitor_confines_root_before_detector_or_process_metadata(tmp_path, monkeypatch):
    outside, workspace = tmp_path / "outside", tmp_path / "workspace"
    outside.mkdir()
    workspace.mkdir()
    run_root = _pure_run(outside)
    runs = workspace / ".orchestrate" / "runs"
    runs.mkdir(parents=True)
    (runs / run_root.name).symlink_to(run_root, target_is_directory=True)
    monkeypatch.setattr("orchestrator.monitor.scanner.has_evaluated_authority", _forbidden)
    monkeypatch.setattr("orchestrator.monitor.scanner.read_process_metadata", _forbidden)
    before = _tree_bytes(tmp_path)
    run = _scan(workspace)
    assert run.state is None and "escapes workspace" in run.read_error
    assert classify_run(run, stale_after_seconds=1) is None
    assert _tree_bytes(tmp_path) == before


def test_monitor_unsettled_coordinator_uses_lock_without_reconciliation(tmp_path, monkeypatch):
    parent, source, refs = _public_fixture(tmp_path)
    authority, snapshot = _commit_gap(monkeypatch, parent, source, refs)
    _forbid_mutable_paths(monkeypatch)
    with _subprocess_writer(authority.run_root):
        run, event = _observe(parent, "settling")
        assert event is None
        row, = run.state["steps"].values()
        assert row["effect_class"] == "run_ref" and row["status"] == "settling"
        assert run.state["memo_offset"] == snapshot.complete_bytes
    run, event = _observe(parent, "interrupted")
    _assert_interrupted(event)


def test_monitor_validates_pure_failure_terminal_without_sources(tmp_path, monkeypatch):
    source = tmp_path / "failure.orc"
    source.write_text("""(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule failure) (export run) (defworkflow run ((divisor Float)) -> Float (/ 1.0 divisor)))""")
    result = _run_cli(tmp_path, str(source), "--input", "divisor=0")
    assert result.returncode == 1, result.stderr
    source.unlink()
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "failed")
    assert event.kind is MonitorEventKind.FAILED
    assert run.state["error"]["code"] == "pure_expr_division_by_zero"
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert "pure_expr_division_by_zero" in body and "Workflow outputs:" not in body
    assert _tree_bytes(tmp_path) == before


def test_monitor_invalidated_current_identity_has_no_historical_attempt_or_streams(tmp_path, monkeypatch):
    run_root = _branch_run(tmp_path)
    choose = next(iter(_scan(tmp_path).state["steps"]))
    assert _cli(tmp_path, "invalidate", run_root.name, choose).returncode == 0
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "interrupted")
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert f"Current/failed step: {choose}" in body
    assert "Attempt:" not in body and "Log previews:" not in body
    assert "Workflow outputs:" not in body and "Error:" not in body
    assert _tree_bytes(tmp_path) == before


def test_monitor_attempt_stream_symlink_escape_is_not_read_or_exported(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    row = list(_scan(tmp_path).state["steps"].values())[-1]
    stream = run_root / Path(row["result_path"]).parent / "stdout.txt"
    outside = tmp_path / "outside-stream.txt"
    outside.write_text("private outside bytes")
    stream.unlink()
    stream.symlink_to(outside)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "completed")
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert "private outside bytes" not in body
    assert "outside-stream.txt" not in body
    assert _tree_bytes(tmp_path) == before


def _forbid_prompt_session_reads(monkeypatch):
    read = Path.read_text
    def guarded(path, *args, **kwargs):
        assert path.name != "prompt.txt" and "provider_sessions" not in path.parts
        return read(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", guarded)


def test_monitor_report_and_dashboard_agree_without_snapshot_and_after_invalidation(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    state = run_root / "state.json"
    old_view = state.read_bytes()
    state.unlink()
    _forbid_legacy(monkeypatch)
    event = _assert_terminal_or_invalidated_parity(tmp_path, run_root, "completed")
    assert event.kind is MonitorEventKind.COMPLETED
    identity = list(event.run.state["steps"])[1]
    result = _cli(tmp_path, "invalidate", run_root.name, identity)
    assert result.returncode == 0, result.stderr
    state.write_bytes(old_view)
    event = _assert_terminal_or_invalidated_parity(tmp_path, run_root, "interrupted")
    _assert_interrupted(event)


def _assert_terminal_or_invalidated_parity(workspace, run_root, status):
    before = _tree_bytes(workspace)
    run, event = _observe(workspace, status)
    report = _cli(workspace, "report", "--run-id", run_root.name, "--runs-root", str(run_root.parent), "--format", "json")
    assert report.returncode == 0, report.stderr
    payload = json.loads(report.stdout)
    response = DashboardApp(RunScanner([workspace])).handle("GET", f"/runs/w0/{run_root.name}")
    assert response.status == 200
    assert payload["run"]["status"] == status
    assert _outputs(response) == run.state["workflow_outputs"] == payload["run"]["workflow_outputs"]
    assert list(run.state["steps"]) == [row["name"] for row in payload["steps"]]
    assert _dashboard_detail(workspace, run_root).cursor.summary == (run.state["next_effect"] or "")
    assert _tree_bytes(workspace) == before
    return event


@pytest.mark.parametrize("stream_name", ["stdout", "stderr"])
def test_monitor_fifo_attempt_stream_refuses_with_subprocess_deadline(tmp_path, stream_name):
    run_root = _completed_run(tmp_path)
    row = list(_scan(tmp_path).state["steps"].values())[-1]
    stream = run_root / Path(row["result_path"]).parent / f"{stream_name}.txt"
    stream.unlink()
    os.mkfifo(stream)
    before = _tree_bytes(tmp_path)
    probe = """from pathlib import Path
import sys
from tests.test_workflow_evaluated_monitor import _config, _scan
from orchestrator.monitor.classifier import classify_run
from orchestrator.monitor.messages import render_event_email
workspace=Path(sys.argv[1])
event=classify_run(_scan(workspace), stale_after_seconds=1)
assert event.kind.value == "COMPLETED"
print("checked-terminal-before-stream-preview", flush=True)
print(render_event_email(event, _config(workspace)).get_content(), flush=True)
"""
    result = subprocess.run([sys.executable, "-B", "-c", probe, str(tmp_path)],
        capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr
    assert "checked-terminal-before-stream-preview" in result.stdout
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("target_kind", ["prompt", "session"])
def test_monitor_attempt_stream_cannot_export_in_root_prompt_or_session(tmp_path, monkeypatch, target_kind):
    fixture = _fixture(tmp_path)
    assert _provider_cli(tmp_path, fixture).returncode == 0
    run_root = _run_root(tmp_path)
    row = next(iter(_scan(tmp_path).state["steps"].values()))
    attempt = run_root / Path(row["result_path"]).parent
    target = attempt / "prompt.txt"
    if target_kind == "session":
        target = run_root / "provider_sessions" / "transport.log"
        target.parent.mkdir()
        target.write_text("private session payload")
    artifact_line = target.read_text().splitlines()[0]
    stream = attempt / "stdout.txt"
    stream.unlink()
    stream.symlink_to(target)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    run, event = _observe(tmp_path, "completed")
    body = render_event_email(event, _config(tmp_path)).get_content()
    assert artifact_line not in body
    assert str(target.relative_to(run_root)) not in body
    assert _tree_bytes(tmp_path) == before
