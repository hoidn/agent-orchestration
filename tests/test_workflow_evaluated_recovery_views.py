"""Public recovery after a view failure, an early later divergence and a completed terminal."""

from __future__ import annotations

import json

import pytest

from orchestrator.cli.commands import evaluated as evaluated_cli
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.workflow.evaluated import run_ref as adapter
from orchestrator.workflow.evaluated import runtime as evaluated_runtime
from orchestrator.workflow.evaluated import views as views_module
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes
from tests.test_workflow_evaluated_readers import _pure_run
from tests.test_workflow_evaluated_resume_kills import (
    _attempt_files, _cli, _env, _run_root, _snapshot, _write_command_case,
)
from tests.test_workflow_evaluated_resume_replay import _create_completed_three_command_run
from tests.test_workflow_evaluated_resume_replay_boundary import _create_public_failed_terminal_command
from tests.test_workflow_evaluated_run_ref import _authority, _public_fixture
from tests.test_workflow_evaluated_run_ref_settlement import _mixed_fixture
from tests.test_workflow_evaluated_view_publication_faults import _service_cli, _state_replace_fault


_MUTABLE_RESUME_STEPS = (
    (evaluated_runtime, "reconcile_evaluated_run_ref"),
    (adapter, "recover_run_ref_settlement"),
    (adapter, "prepare_run_ref_settlement"),
    (adapter, "finalize_run_ref_parent_commit"),
    (evaluated_runtime, "repair_torn_tail"),
    (evaluated_runtime, "_start_and_perform_effect"),
    (evaluated_runtime, "execute_pure_run"),
    (views_module, "publish_evaluated_view"),
)


def _spy(calls, name, real):
    def call(*args, **kwargs):
        calls.append(name)
        return real(*args, **kwargs)
    return call


def _count_mutable_steps(monkeypatch):
    """Count, without replacing, every reconcile, repair, dispatch, continuation and view publication."""
    calls = []
    for owner, name in _MUTABLE_RESUME_STEPS:
        monkeypatch.setattr(owner, name, _spy(calls, name, getattr(owner, name)))
    return calls


def _record_resume_results(monkeypatch):
    results = []
    real = evaluated_cli.execute_pure_resume

    def record(*args, **kwargs):
        results.append(real(*args, **kwargs))
        return results[-1]

    monkeypatch.setattr(evaluated_cli, "execute_pure_resume", record)
    return results


def _dispatches(workspace):
    return [json.loads(line)["kind"] for line in (workspace / "dispatches.jsonl").read_text().splitlines()]


def _records(run_root):
    return [entry.data["record"] for entry in _snapshot(run_root).entries]


def _fail_view_after_first_commit(workspace, monkeypatch, caplog):
    """Fail the real atomic replace of state.json right after the first synchronized commit."""
    arguments, _hashes = _write_command_case(workspace)
    write_atomic = WorkspaceFiles.write_atomic
    failures = _state_replace_fault(monkeypatch, workspace, "committed")
    assert _service_cli(monkeypatch, workspace, arguments) == 1
    monkeypatch.setattr(WorkspaceFiles, "write_atomic", write_atomic)
    assert failures == ["state.json"]
    assert "view_write_failed" in caplog.text
    assert "injected atomic state replace failure" in caplog.text
    run_root = _run_root(workspace)
    assert _records(run_root) == ["started", "committed"]
    assert _dispatches(workspace) == ["first"]
    return run_root


def _assert_view_lags_memo(run_root, identity):
    old_view = json.loads((run_root / "state.json").read_bytes())
    assert old_view["memo_offset"] < (run_root / "memo.jsonl").stat().st_size
    assert old_view["steps"][identity]["status"] == "running"
    assert load_evaluated_view(run_root)["steps"][identity]["status"] == "completed"


@pytest.mark.parametrize("view", ["stale", "absent"])
def test_public_resume_after_view_failure_reuses_synced_commit(tmp_path, monkeypatch, caplog, view):
    workspace = tmp_path / "commands"
    run_root = _fail_view_after_first_commit(workspace, monkeypatch, caplog)
    (first,) = _snapshot(run_root).active_commits.values()
    prefix, evidence = (run_root / "memo.jsonl").read_bytes(), _attempt_files(run_root, first.data)
    _assert_view_lags_memo(run_root, first.data["identity"])
    if view == "absent":
        (run_root / "state.json").unlink()

    resumed = _cli(workspace, ["resume", run_root.name], _env(workspace))

    assert resumed.returncode == 0, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes().startswith(prefix)
    assert _records(run_root) == ["started", "committed", "started", "committed", "terminal"]
    after = _snapshot(run_root)
    assert after.active_commits[first.data["identity"]] == first
    assert after.terminal.data["value"] == first.data["value"] + 1
    assert _dispatches(workspace) == ["first", "second"]
    assert _attempt_files(run_root, first.data) == evidence
    assert json.loads((run_root / "state.json").read_bytes()) == load_evaluated_view(run_root)


def _settled_prefix_without_terminal(authority, snapshot):
    """Cut the genuine journal at its terminal, leaving a torn tail and the original post-terminal
    view, now ahead of the journal (a contradictory view, §8.4)."""
    rows = [entry.data for entry in snapshot.entries]
    assert [row["record"] for row in rows] == ["started", "committed", "settled", "started", "committed", "terminal"]
    coordinator, later = (row for row in rows if row["record"] == "committed")
    assert coordinator["effect_class"] == "run_ref" and rows[2]["by"] == "settle"
    assert coordinator["identity"] in later["depends_on"]
    journal = authority.memo_path.read_bytes()
    authority.memo_path.write_bytes(journal[:snapshot.terminal.offset] + b'{"record":"partial"')
    prefix = _snapshot(authority.run_root)
    assert prefix.terminal is None and prefix.tail and not prefix.pending_starts
    assert len(prefix.active_commits) == 2 and not prefix.unsettled_coordinators
    ahead = json.loads((authority.run_root / "state.json").read_bytes())
    assert ahead["status"] == "completed" and ahead["memo_offset"] > prefix.complete_bytes
    return coordinator["identity"], later["identity"], journal


@pytest.mark.parametrize("later", ["command", "provider"])
def test_later_committed_divergence_precedes_reconcile_and_tail_repair(tmp_path, monkeypatch, caplog, later):
    parent, source, refs, extra = _mixed_fixture(tmp_path, monkeypatch, later=later)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs), *extra)
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    coordinator, divergent, journal = _settled_prefix_without_terminal(authority, snapshot)
    changed = parent / ("probe.py" if later == "command" else "prompt.md")
    original = changed.read_bytes()
    changed.write_bytes(original + b"\n# changed declared input\n")
    calls = _count_mutable_steps(monkeypatch)
    monkeypatch.chdir(parent)
    before, children = _tree_bytes(tmp_path), _tree_bytes(refs)

    assert resume_workflow(authority.run_root.name) == 2

    assert f"{divergent}: effect input diverged" in caplog.text
    assert f"{coordinator}: effect input diverged" not in caplog.text
    assert _tree_bytes(tmp_path) == before and calls == []
    changed.write_bytes(original)
    assert resume_workflow(authority.run_root.name) == 0
    assert calls == ["repair_torn_tail", "execute_pure_run", "publish_evaluated_view"]
    assert authority.memo_path.read_bytes() == journal
    assert _tree_bytes(refs) == children


def _completed_coordinator(tmp_path):
    parent, source, refs = _public_fixture(tmp_path)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    assert len(snapshot.settlements) == 1 and not snapshot.unsettled_coordinators
    return authority.run_root, True


def _completed_after_failed_attempt(tmp_path, monkeypatch, caplog):
    """Repeated preflight refusals keep the failed terminal; the retry's start reopens it."""
    run_root, helper, memo = _create_public_failed_terminal_command(tmp_path)
    failed = memo.read_bytes()
    assert _records(run_root) == ["started", "failed", "terminal"]
    monkeypatch.chdir(tmp_path)
    before = _tree_bytes(tmp_path)
    for refusal in range(1, 3):
        assert resume_workflow(run_root.name) == 2
        assert _tree_bytes(tmp_path) == before
        assert caplog.text.count("effect_input_diverged") == refusal
    helper.write_text("def value():\n    return 5\n", encoding="utf-8")
    assert resume_workflow(run_root.name) == 0
    assert memo.read_bytes().startswith(failed)
    assert [(entry.data["record"], entry.data.get("attempt")) for entry in _snapshot(run_root).entries][3:] == [
        ("started", 2), ("committed", 2), ("terminal", None)]
    assert (tmp_path / "dispatches.txt").read_text(encoding="utf-8").splitlines() == ["attempt-1", "attempt-2"]
    return run_root, 5


def _completed_scenario(tmp_path, monkeypatch, caplog, scenario):
    if scenario == "effectful":
        return _create_completed_three_command_run(tmp_path), 3
    if scenario == "pure-only":
        return _pure_run(tmp_path), {"accepted": True, "score": 0.75}
    if scenario == "coordinator":
        return _completed_coordinator(tmp_path)
    return _completed_after_failed_attempt(tmp_path, monkeypatch, caplog)


@pytest.mark.parametrize("scenario", ["effectful", "pure-only", "coordinator", "failed-attempt"])
def test_completed_resume_twice_is_byte_identical(tmp_path, monkeypatch, caplog, scenario):
    run_root, expected = _completed_scenario(tmp_path, monkeypatch, caplog, scenario)
    assert _snapshot(run_root).terminal.data == {"record": "terminal", "outcome": "completed", "value": expected}
    calls = _count_mutable_steps(monkeypatch)
    results = _record_resume_results(monkeypatch)
    monkeypatch.chdir(run_root.parents[2])
    before = _tree_bytes(tmp_path)

    for _ in range(2):
        assert resume_workflow(run_root.name) == 0
        assert _tree_bytes(tmp_path) == before

    assert results == [(0, expected), (0, expected)]
    assert calls == []
