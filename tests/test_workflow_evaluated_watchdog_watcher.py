"""Usage watchdog reads the real package while pane actions remain stand-ins."""

from pathlib import Path
import time
import json
import signal
import os

import pytest

from tests.test_watch_workflow_usage_limit import watcher, _wait_for_calls
from tests.test_workflow_evaluated_readers import _pure_run, _scalar_run
from tests.test_workflow_evaluated_invalidate import _tree_bytes, _cli
from tests.test_workflow_evaluated_providers import _fixture, _cli as _provider_cli
from tests.test_workflow_evaluated_view_publication import _provider_env, _live_writer, _wait_marker
from tests.test_workflow_evaluated_resume_kills import _write_command_case
from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_watchdog_probe import _reader_spies, _guard_loaded, _probe
from tests.test_workflow_evaluated_dashboard import _corrupt_authority
from tests.test_workflow_evaluated_run_ref import _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_evaluated_invalidate import _completed_run
from tests.test_workflow_evaluated_monitor import _assert_terminal_or_invalidated_parity
from tests.test_workflow_evaluated_monitor import _provider_message
from tests.test_workflow_evaluated_dashboard import _detail


def _clear_pane(watcher):
    watcher.tmux("send-keys", "-t", "target:0.0", "C-l")
    deadline = time.monotonic() + 5
    while "usage limit" in watcher.capture():
        assert time.monotonic() < deadline, "pane did not clear"
        time.sleep(0.05)
    watcher.tmux("clear-history", "-t", "target:0.0")


def _cycle(watcher, process):
    deadline = time.monotonic() + 30
    while True:
        text = watcher.log.read_text()[process.log_offset:] if watcher.log.exists() else ""
        if "state " in text or "requeued provider-limit" in text:
            assert _guard_loaded(process.reader_guard, "-"), "checked reader startup guard was not installed"
            return text
        assert process.poll() is None, text
        assert time.monotonic() < deadline, text
        time.sleep(0.05)


def _start(watcher, outcomes="run", **overrides):
    guard = _reader_spies(watcher.log.parent)
    overrides["PYTHONPATH"] = str(guard)
    overrides["ORCHESTRATOR_TEST_GUARD_RECEIPT"] = str(guard / "loaded.jsonl")
    offset = len(watcher.log.read_text()) if watcher.log.exists() else 0
    process = watcher(outcomes, **overrides)
    process.reader_guard = guard
    process.log_offset = offset
    return process


def test_watcher_reads_completed_authority_without_snapshot(watcher):
    run_root = _pure_run(watcher.workspace)
    (run_root / "state.json").unlink()
    _clear_pane(watcher)
    before = _tree_bytes(watcher.workspace)
    process = _start(watcher, RUN_ID=run_root.name)
    text = _cycle(watcher, process)
    assert "state completed" in text and "state read failed" not in text
    assert watcher.calls() == []
    assert _tree_bytes(watcher.workspace) == before


@pytest.mark.parametrize("stage", ["started", "last", "killed"])
def test_watcher_lock_status_ignores_old_pane_limit(watcher, tmp_path, stage):
    target = tmp_path / "T"
    args, _hashes = _write_command_case(target)
    with _live_writer(target, args) as (writer, control):
        _wait_marker(writer, control / "started")
        if stage == "last":
            for marker, next_stage in (("started", "partial"), ("partial", "first"), ("first", "last")):
                (control / (marker + ".release")).touch()
                _wait_marker(writer, control / next_stage)
        if stage == "killed":
            os.killpg(writer.pid, signal.SIGKILL)
            writer.wait(timeout=5)
        run_root, = (target / ".orchestrate/runs").iterdir()
        before = _tree_bytes(target)
        process = _start(watcher, WORKSPACE=str(target), RUN_ID=run_root.name)
        text = _cycle(watcher, process)
        assert "detected provider usage/rate limit" not in text
        expected = {"started": "running", "last": "settling", "killed": "interrupted"}[stage]
        assert f"state {expected}" in text
        assert watcher.calls() == []
        assert _tree_bytes(target) == before


def _retry_provider(workspace, monkeypatch, *, latest_limit):
    fixture = _fixture(workspace)
    assert _provider_cli(workspace, fixture, mode="nonzero").returncode == 1
    run_root, = (workspace / ".orchestrate/runs").iterdir()
    first, = load_evaluated_view(run_root)["steps"].values()
    old_stream = run_root / Path(first["result_path"]).parent / "stderr.txt"
    old_stream.write_text("old clean" if latest_limit else "old rate limit reached")
    old = _tree_bytes(old_stream.parent)
    _provider_env(monkeypatch, workspace, "invalid" if latest_limit else "success")
    assert _cli(workspace, "resume", run_root.name).returncode == (1 if latest_limit else 0)
    latest, = load_evaluated_view(run_root)["steps"].values()
    current_stream = run_root / Path(latest["result_path"]).parent / "stderr.txt"
    current_stream.write_text("current rate limit reached" if latest_limit else "current clean")
    return run_root, old_stream.parent, old


def test_watcher_latest_clean_attempt_ignores_old_stream_and_pane_limit(watcher, monkeypatch):
    run_root, old_dir, old = _retry_provider(watcher.workspace, monkeypatch, latest_limit=False)
    before = _tree_bytes(watcher.workspace)
    process = _start(watcher, RUN_ID=run_root.name)
    text = _cycle(watcher, process)
    assert "detected provider usage/rate limit" not in text
    assert watcher.calls() == []
    assert _tree_bytes(old_dir) == old and _tree_bytes(watcher.workspace) == before


@pytest.mark.parametrize("interrupted", [False, True])
def test_watcher_current_limit_resumes_existing_run(watcher, monkeypatch, interrupted):
    run_root, old_dir, old = _retry_provider(watcher.workspace, monkeypatch, latest_limit=True)
    if interrupted:
        journal = run_root / "memo.jsonl"
        rows = journal.read_bytes().splitlines(keepends=True)
        journal.write_bytes(b"".join(rows[:-1]))
        assert load_evaluated_view(run_root)["status"] == "interrupted"
    _clear_pane(watcher)
    before = _tree_bytes(watcher.workspace)
    process = _start(watcher, RUN_ID=run_root.name)
    _wait_for_calls(watcher, 1, timeout=40)
    assert watcher.calls() == [f"resume {run_root.name} --stream-output"]
    assert process.poll() is None
    assert _guard_loaded(process.reader_guard, "-")
    assert _tree_bytes(old_dir) == old and _tree_bytes(watcher.workspace) == before


def test_watcher_evaluated_completed_never_requeues_before_recipe_refusal(watcher):
    workspace = watcher.workspace
    source = workspace / "drain.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule drain) (export run)
      (defrecord Drain (drain_status String) (tranche_manifest_path String) (message String))
      (defworkflow run ((tranche_manifest_target_path String)) -> Drain
        (record Drain :drain_status "BLOCKED" :tranche_manifest_path tranche_manifest_target_path
          :message "provider usage limit reached")))''')
    result = _run_cli(workspace, str(source), "--input", "tranche_manifest_target_path=tranche-manifest.json")
    assert result.returncode == 0, result.stderr
    run_root, = (workspace / ".orchestrate/runs").iterdir()
    manifest = {"tranches": [{"tranche_id": "t-1", "status": "blocked",
        "last_item_outcome": "SKIPPED_AFTER_IMPLEMENTATION", "last_execution_report_path": "failed.md"}]}
    (workspace / "tranche-manifest.json").write_text(json.dumps(manifest))
    (workspace / "failed.md").write_text("failed before producing a report")
    _clear_pane(watcher)
    before = _tree_bytes(workspace)
    process = _start(watcher, RUN_ID=run_root.name)
    text = _cycle(watcher, process)
    assert _tree_bytes(workspace) == before
    assert watcher.calls() == [] and "requeued" not in text


@pytest.mark.parametrize("kind", ["late-line", "legacy-text"])
def test_watcher_current_stream_detection_never_uses_cutoff_or_profile_sentinel(watcher, monkeypatch, kind):
    run_root, _old_dir, _old = _retry_provider(watcher.workspace, monkeypatch, latest_limit=True)
    row, = load_evaluated_view(run_root)["steps"].values()
    stream = run_root / Path(row["result_path"]).parent / "stderr.txt"
    stream.write_text("clean\n" * 2000 + "current rate limit reached\n" if kind == "late-line" else "legacy")
    old_stdout = stream.parent.parent / "attempt-1/stdout.txt"
    old_stdout.write_text("legacy HISTORICAL_ONLY")
    _clear_pane(watcher)
    before = _tree_bytes(watcher.workspace)
    overrides = {"LIMIT_PATTERN": "legacy"} if kind == "legacy-text" else {}
    process = _start(watcher, RUN_ID=run_root.name, **overrides)
    _wait_for_calls(watcher, 1, timeout=40)
    assert watcher.calls() == [f"resume {run_root.name} --stream-output"]
    assert "HISTORICAL_ONLY" not in watcher.log.read_text()
    assert process.poll() is None and _tree_bytes(watcher.workspace) == before


@pytest.mark.parametrize("started_at", [None, "valid-non-ISO-time"])
def test_watcher_running_discovery_loads_authority_without_snapshot(watcher, tmp_path, started_at):
    target = tmp_path / "T"
    args, _hashes = _write_command_case(target)
    with _live_writer(target, args) as (writer, control):
        _wait_marker(writer, control / "started")
        run_root, = (target / ".orchestrate/runs").iterdir()
        if started_at is not None:
            header = json.loads((run_root / "run.json").read_text())
            header["started_at"] = started_at
            (run_root / "run.json").write_text(json.dumps(header))
        view = load_evaluated_view(run_root)
        (run_root / "state.json").unlink()
        _legacy_drain(target, view["workflow_file"])
        before = _tree_bytes(run_root)
        process = _start(watcher, WORKSPACE=str(target))
        deadline = time.monotonic() + 40
        while "watchdog switching" not in (watcher.log.read_text() if watcher.log.exists() else ""):
            assert process.poll() is None
            assert time.monotonic() < deadline, watcher.log.read_text()
            time.sleep(0.1)
        assert f"new running run_id={run_root.name}" in watcher.log.read_text()
        assert watcher.calls() == [f"run {view['workflow_file']} --stream-output"]
        assert writer.poll() is None and _tree_bytes(run_root) == before


def _legacy_drain(target, workflow_file):
    root = target / ".orchestrate/runs/target-run"
    root.mkdir()
    (root / "state.json").write_text(json.dumps({"run_id": "target-run", "status": "completed",
        "workflow_file": workflow_file, "workflow_outputs": {"drain_status": "BLOCKED",
        "message": "provider usage limit reached", "tranche_manifest_path": "tranche-manifest.json"}}))
    (target / "tranche-manifest.json").write_text(json.dumps({"tranches": [{"tranche_id": "t-1",
        "status": "blocked", "last_item_outcome": "SKIPPED_AFTER_IMPLEMENTATION", "last_execution_report_path": "failed.md"}]}))
    (target / "failed.md").write_text("failed before producing a report")


@pytest.mark.parametrize("corruption", ["bad-terminal", "missing-all-authority", "bad-artifact"])
def test_watcher_corrupt_authority_refuses_old_completed_recovery(watcher, corruption):
    root = _pure_run(watcher.workspace)
    snapshot = json.loads((root / "state.json").read_text())
    snapshot["workflow_outputs"] = {"drain_status": "BLOCKED", "message": "provider usage limit reached"}
    (root / "state.json").write_text(json.dumps(snapshot))
    if corruption == "missing-all-authority":
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            (root / name).unlink()
    elif corruption == "bad-artifact":
        (root / "closed_program.json").write_text("{}")
    else:
        _corrupt_authority(root, corruption)
    before = _tree_bytes(watcher.workspace)
    process = _start(watcher, RUN_ID=root.name)
    text = _wait_diagnostic(watcher, process, "state read failed memo_inconsistent")
    assert "state completed" not in text and "requeued" not in text
    assert "detected provider usage/rate limit" not in text and watcher.calls() == []
    assert _tree_bytes(watcher.workspace) == before


def _wait_diagnostic(watcher, process, expected):
    deadline = time.monotonic() + 30
    while True:
        text = watcher.log.read_text() if watcher.log.exists() else ""
        if text.count(expected) >= 2:
            assert _guard_loaded(process.reader_guard, "-")
            return text
        assert process.poll() is None, text
        assert time.monotonic() < deadline, text
        time.sleep(0.05)


@pytest.mark.parametrize("kind", ["external", "prompt", "session", "fifo"])
def test_watcher_attempt_stream_boundaries_do_not_trigger_recovery(watcher, monkeypatch, tmp_path, kind):
    root, _old_dir, _old = _retry_provider(watcher.workspace, monkeypatch, latest_limit=False)
    row, = load_evaluated_view(root)["steps"].values()
    stream = root / Path(row["result_path"]).parent / "stderr.txt"
    stream.unlink()
    _unsafe_stream(stream, root, tmp_path, kind)
    _clear_pane(watcher)
    before = _tree_bytes(watcher.workspace)
    process = _start(watcher, RUN_ID=root.name)
    text = _cycle(watcher, process)
    assert "detected provider usage/rate limit" not in text and watcher.calls() == []
    assert _tree_bytes(watcher.workspace) == before


def _unsafe_stream(stream, root, temporary, kind):
    if kind == "fifo":
        os.mkfifo(stream)
        return
    target = {"external": temporary / "outside.txt", "prompt": stream.parent / "prompt.txt",
        "session": root / "provider_sessions/session.txt"}[kind]
    target.parent.mkdir(exist_ok=True)
    target.write_text("provider usage limit reached")
    stream.symlink_to(target)


def test_watcher_unsettled_coordinator_ignores_prior_provider_stream(watcher, tmp_path, monkeypatch):
    specimen = tmp_path / "coordinator"
    specimen.mkdir()
    parent, source, refs = _public_fixture(specimen, definitions="(defrecord Result (ok Bool))",
        parameters="(message String)", body=lambda call: f'''(let* ((review (provider-result providers.review
          :prompt prompts.base :inputs (message) :returns Result)) (child {call})) child.value)''')
    fixture = _fixture(parent, source.read_text())
    _provider_env(monkeypatch, parent, "success")
    authority, _memo = _commit_gap(monkeypatch, parent, source, refs, extra=(
        "--provider-externs-file", str(fixture[1]), "--prompt-externs-file", str(fixture[2]), "--input", "message=x"))
    root = authority.run_root
    view = load_evaluated_view(root)
    prior = next(row for row in view["steps"].values() if row["effect_class"] == "provider")
    (root / Path(prior["result_path"]).parent / "stderr.txt").write_text("historical rate limit reached")
    with _subprocess_writer(root):
        current = load_evaluated_view(root)
        assert current["status"] == "settling"
        assert current["current_step"]["identity"] != prior["identity"]
        before = _tree_bytes(parent), _tree_bytes(refs)
        process = _start(watcher, WORKSPACE=str(parent), RUN_ID=root.name)
        text = _cycle(watcher, process)
        assert "state settling" in text and "detected provider usage/rate limit" not in text
        assert watcher.calls() == [] and (_tree_bytes(parent), _tree_bytes(refs)) == before


@pytest.mark.parametrize("invalidated", [False, True])
def test_probe_watcher_report_dashboard_monitor_same_root_parity(watcher, tmp_path, invalidated):
    root = _completed_run(watcher.workspace)
    state = root / "state.json"
    old_view = state.read_bytes()
    view = load_evaluated_view(root)
    if invalidated:
        identity = list(view["steps"])[1]
        result = _cli(watcher.workspace, "invalidate", root.name, identity)
        assert result.returncode == 0, result.stderr
        state.write_bytes(old_view)
    else:
        state.unlink()
    status = "interrupted" if invalidated else "completed"
    before = _tree_bytes(watcher.workspace)
    event = _assert_terminal_or_invalidated_parity(watcher.workspace, root, status)
    workspace = tmp_path / "W"
    workspace.mkdir()
    watch, evidence = _probe(workspace, root)
    assert watch["run_status"] == evidence["run_status"] == event.run.state["status"] == status
    assert watch["watch_status"] == ("CRASHED" if invalidated else "COMPLETED")
    assert evidence["running_steps"] == [] and evidence["failed_steps"] == []
    process = _start(watcher, RUN_ID=root.name)
    text = _cycle(watcher, process)
    assert f"state {status}" in text and watcher.calls() == []
    assert _tree_bytes(watcher.workspace) == before


def test_retried_failed_root_agrees_on_current_error_and_attempt(watcher, tmp_path, monkeypatch):
    root, old_dir, old = _retry_provider(watcher.workspace, monkeypatch, latest_limit=True)
    row, = load_evaluated_view(root)["steps"].values()
    before = _tree_bytes(watcher.workspace)
    body, monitor_row = _provider_message(watcher.workspace, "failed", 2)
    _assert_retry_reader_rows(watcher.workspace, root, row, monitor_row)
    workspace = tmp_path / "W"
    workspace.mkdir()
    watch, evidence = _probe(workspace, root)
    failed, = evidence["failed_steps"]
    assert failed["name"] == row["identity"] and failed["error_type"] == row["error"]["code"]
    assert watch["watch_status"] == "FAILED" and "current rate limit reached" in body
    _clear_pane(watcher)
    process = _start(watcher, RUN_ID=root.name,
        LIMIT_PATTERN="current rate limit reached|" + row["error"]["code"])
    _wait_for_calls(watcher, 1, timeout=40)
    _assert_retry_watcher(watcher, process, root, row)
    assert (_tree_bytes(watcher.workspace), _tree_bytes(old_dir)) == (before, old)


def _assert_retry_reader_rows(workspace, root, row, monitor_row):
    result = _cli(workspace, "report", "--run-id", root.name, "--runs-root", str(root.parent), "--format", "json")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    detail = _detail(workspace, root)
    report_row, = report["steps"]
    dashboard_row, = detail.state["steps"].values()
    keys = ("identity", "attempt", "value", "error")
    expected = tuple(row.get(key) for key in keys)
    assert all(tuple(observed.get(key) for key in keys) == expected
        for observed in (report_row, dashboard_row, monitor_row))
    assert report["run"]["workflow_outputs"] == detail.workflow_outputs is None


def _assert_retry_watcher(watcher, process, root, row):
    text = watcher.log.read_text()
    rows = [json.loads(line) for line in (root / "memo.jsonl").read_text().splitlines()]
    failures = [entry for entry in rows if entry["record"] == "failed"]
    assert row["error"]["code"] in text and failures[0]["code"] not in text
    assert "current rate limit reached" in text and _guard_loaded(process.reader_guard, "-")
    assert watcher.calls() == [f"resume {root.name} --stream-output"] and process.poll() is None
