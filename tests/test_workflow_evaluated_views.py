"""Contracts for readonly evaluated views over real run authority."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.run_lock import run_writer_active
from orchestrator.state import RunState, StateManager
from orchestrator.workflow.evaluated import runtime
from orchestrator.workflow.evaluated import memo as memo_module
from orchestrator.cli.commands import evaluated as evaluated_cli
from orchestrator.workflow_lisp.closed import artifact
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.machine import site_classes
from orchestrator.workflow.evaluated.memo import MemoError, read_memo
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.run_ref import runtime as child_runtime
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _cli, _completed_run, _tree_bytes
from tests.test_workflow_evaluated_readers import _pure_run
from tests.test_workflow_evaluated_resume_kills import (
    _env, _kill_after_first_commit, _run_root, _write_command_case,
)
from tests.test_workflow_evaluated_resume_replay import _create_completed_three_command_run
from tests.test_workflow_evaluated_resume_replay_boundary import (
    _create_completed_branch_run, _create_public_failed_terminal_command,
    _create_two_command_run, _make_committed_branch_unreachable, _reverse_active_commit_journal,
)
from tests.test_workflow_evaluated_run_ref import _authority, _repeated_fixture


def _snapshot(run_root):
    authority = load_run_authority(run_root)
    return read_memo(authority.memo_path, site_classes(authority.program))


def _no_effects(*_args, **_kwargs):
    pytest.fail("readonly view reached mutable preparation or source preflight")


def _forbid_mutable_paths(monkeypatch):
    for name in ("_resolve_effect_input", "_check_resume_boundary", "_execute_effect",
                 "_replay_resume_prefix", "prepare_evaluated_run_ref", "validate_evaluated_run_ref"):
        monkeypatch.setattr(runtime, name, _no_effects)
    for name in ("prepare_run_ref_settlement", "recover_run_ref_settlement",
                 "validate_completed_run_ref_authority"):
        monkeypatch.setattr(child_runtime, name, _no_effects)
    for name in ("bind_program_inputs", "_bind_recipe", "_resume_build_request"):
        monkeypatch.setattr(evaluated_cli, name, _no_effects)
    monkeypatch.setattr(artifact, "build_closed_program_bundle", _no_effects)
    monkeypatch.setattr(memo_module, "repair_torn_tail", _no_effects)
    monkeypatch.setattr(memo_module, "append_record", _no_effects)


def test_committed_effect_rows_keep_order_and_values_without_filesystem_preflight(tmp_path, monkeypatch):
    run_root = _create_completed_three_command_run(tmp_path)
    snapshot = _snapshot(run_root)
    for entry in snapshot.active_commits.values():
        (run_root / entry.data["result_path"]).unlink()
    for name in ("replay.orc", "commands.json", "first.py", "second.py", "third.py"):
        (tmp_path / name).unlink()
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)

    view = load_evaluated_view(run_root)

    assert view["status"] == "completed"
    assert view["workflow_outputs"] == 3
    assert list(view["steps"]) == list(snapshot.latest_starts)
    assert [row["value"] for row in view["steps"].values()] == [1, 2, 3]
    assert {row["attempt"] for row in view["steps"].values()} == {1}
    assert view["current_step"] is None and view["next_effect"] is None
    assert _tree_bytes(tmp_path) == before


def test_real_killed_prefix_stops_at_first_missing_commit_without_preparation(tmp_path, monkeypatch):
    workspace = tmp_path / "interrupted"
    arguments, _hashes = _write_command_case(workspace)
    identity = _kill_after_first_commit(workspace, arguments, _env(workspace))
    run_root = _run_root(workspace)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(run_root)
    assert view["status"] == "interrupted"
    assert list(view["steps"]) == [identity]
    assert view["next_effect"].endswith(" / second")
    assert view["current_step"] is None
    assert view["workflow_outputs"] is None
    assert _tree_bytes(tmp_path) == before


def test_invalidation_replaces_old_completed_view_and_preserves_commit_rows(tmp_path):
    run_root = _completed_run(tmp_path)
    commits = list(_snapshot(run_root).active_commits.values())
    (run_root / "state.json").write_text('{"status":"completed","workflow_outputs":"stale"}')
    result = _cli(tmp_path, "invalidate", run_root.name, commits[1].data["identity"])
    assert result.returncode == 0, result.stderr
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(run_root)
    assert [row["status"] for row in view["steps"].values()] == ["completed", "invalidated", "invalidated"]
    assert view["status"] == "interrupted"
    assert view["next_effect"] == commits[1].data["identity"]
    assert view["workflow_outputs"] is None
    assert StateManager(tmp_path, run_root.name).load().to_dict() == view
    assert _tree_bytes(tmp_path) == before


def _path_run(root):
    source = root / "paths.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule paths) (export run)
      (defpath WorkPath :kind relpath :under "artifacts" :must-exist true)
      (defworkflow run () -> WorkPath
        (command-result emit :argv ("python" "emit.py") :returns WorkPath)))''')
    (root / "emit.py").write_text('import os\nfrom pathlib import Path\n'
        'Path("artifacts").mkdir()\nPath("artifacts/seed.txt").write_text("seed")\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(\'"artifacts/seed.txt"\')\n')
    boundaries = root / "commands.json"
    boundaries.write_text(json.dumps({"emit": {"stable_command": ["python", "emit.py"], "closure": ["emit.py"]}}))
    result = _run_cli(root, str(source), "--command-boundaries-file", str(boundaries))
    assert result.returncode == 0, result.stderr
    return _run_root(root)


def test_committed_must_exist_path_is_a_value_after_referent_disappears(tmp_path, monkeypatch):
    run_root = _path_run(tmp_path)
    (tmp_path / "artifacts" / "seed.txt").unlink()
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(run_root)
    assert view["workflow_outputs"] == "artifacts/seed.txt"
    assert next(iter(view["steps"].values()))["value"] == "artifacts/seed.txt"
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("structure", ["helper", "nested"])
def test_nested_loop_run_ref_values_replay_without_child_proof_or_source_io(tmp_path, monkeypatch, structure):
    parent, source, refs = _repeated_fixture(tmp_path, child_target="2.35", structure=structure, forwarding=True)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    for entry in snapshot.active_commits.values():
        (authority.run_root / entry.data["result_path"]).unlink()
    source.unlink()
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(authority.run_root)
    assert view["workflow_outputs"] is True
    assert list(view["steps"]) == list(snapshot.latest_starts)
    assert [row["value"]["value"] for row in view["steps"].values()] == [False, True]
    assert {row["status"] for row in view["steps"].values()} == {"completed"}
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("corruption", ["order", "unreachable", "halt", "missing", "type", "complete_line"])
def test_replay_rejects_inconsistent_real_memo_without_outputs_or_mutation(tmp_path, corruption):
    if corruption == "order":
        run_root = _create_two_command_run(tmp_path)
        _reverse_active_commit_journal(run_root)
    elif corruption == "unreachable":
        run_root = _create_completed_branch_run(tmp_path)
        _make_committed_branch_unreachable(run_root)
    else:
        run_root = _create_completed_three_command_run(tmp_path)
        path = run_root / "memo.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        _corrupt_rows(rows, corruption)
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))
        if corruption == "complete_line":
            with path.open("ab") as stream:
                stream.write(b"bad JSON\n")
    before = _tree_bytes(tmp_path)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        load_evaluated_view(run_root)
    assert _tree_bytes(tmp_path) == before


def _corrupt_rows(rows, corruption):
    if corruption == "halt":
        rows[-1]["value"] = True
    elif corruption == "missing":
        rows[:] = rows[:-3] + [rows[-1]]
    elif corruption == "type":
        rows[1]["value"] = True


def _set_unrepresentable_record_time(run_root, record):
    memo_path = run_root / "memo.jsonl"
    rows = [json.loads(line) for line in memo_path.read_text().splitlines()]
    next(row for row in rows if row["record"] == record)["time"] = 1e300
    memo_path.write_text("".join(json.dumps(row) + "\n" for row in rows))


@pytest.mark.parametrize("record", ["started", "committed"])
@pytest.mark.parametrize("reader", ["loader", "report"])
def test_unrepresentable_record_time_is_readonly_memo_refusal(tmp_path, record, reader):
    run_root = _create_completed_three_command_run(tmp_path)
    _set_unrepresentable_record_time(run_root, record)
    assert _snapshot(run_root).terminal.data["outcome"] == "completed"
    before = _tree_bytes(tmp_path)

    if reader == "loader":
        with pytest.raises(MemoError, match="memo_inconsistent"):
            load_evaluated_view(run_root)
    else:
        result = _cli(tmp_path, "report", "--run-id", run_root.name,
                      "--runs-root", str(run_root.parent), "--format", "json")
        assert result.returncode == 1
        assert "memo_inconsistent" in result.stderr
        assert "Traceback" not in result.stderr
        assert result.stdout == ""
    assert _tree_bytes(tmp_path) == before


def test_failed_terminal_cannot_hide_a_wrong_typed_last_active_commit(tmp_path):
    workspace = tmp_path / "failed"
    arguments, _hashes = _write_command_case(workspace)
    script = workspace / "probe.py"
    script.write_text(script.read_text().replace(
        'value = 5 if kind == "first" else int(sys.argv[2]) + 1',
        'if kind == "second": sys.exit(9)\nvalue = 5'))
    result = _cli(workspace, *arguments)
    assert result.returncode == 1, result.stderr
    run_root = _run_root(workspace)
    path = run_root / "memo.jsonl"
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert rows[-1]["outcome"] == "failed"
    commit = next(row for row in rows if row["record"] == "committed")
    commit["value"] = True
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    before = _tree_bytes(tmp_path)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        load_evaluated_view(run_root)
    assert _tree_bytes(tmp_path) == before


def test_failed_terminal_replays_failure_without_invented_timing_or_outputs(tmp_path):
    run_root, _helper, _memo = _create_public_failed_terminal_command(tmp_path)
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(run_root)
    row = next(iter(view["steps"].values()))
    assert view["status"] == "failed" and view["workflow_outputs"] is None
    assert row["status"] == "failed" and row["error"]["code"]
    assert row["effect_class"] == "command"
    assert "completed_at" not in row
    assert view["updated_at"] == row["started_at"]
    assert _tree_bytes(tmp_path) == before


def test_captured_partial_tail_is_ignored_without_repair_or_source_rebuild(tmp_path, monkeypatch):
    run_root = _create_completed_three_command_run(tmp_path)
    complete_bytes = (run_root / "memo.jsonl").stat().st_size
    with (run_root / "memo.jsonl").open("ab") as stream:
        stream.write(b'{"record":"partial"')
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    view = load_evaluated_view(run_root)
    assert view["memo_offset"] == complete_bytes
    assert view["workflow_outputs"] == 3
    assert _tree_bytes(tmp_path) == before


def test_three_authority_siblings_are_captured_once_through_borrowed_descriptor(tmp_path, monkeypatch):
    run_root = _pure_run(tmp_path)
    files = WorkspaceFiles(run_root)
    captured = []
    read = files.read
    def capture(path):
        captured.append(str(path))
        return read(path)
    monkeypatch.setattr(files, "read", capture)
    before = _tree_bytes(tmp_path)
    try:
        assert load_evaluated_view(run_root, run_files=files)["status"] == "completed"
        assert captured == ["run.json", "closed_program.json", "memo.jsonl"]
        assert not files.closed and os.fstat(files.root_fd)
    finally:
        files.close()
    assert _tree_bytes(tmp_path) == before


def test_terminal_requires_coordinator_settlement_without_reconciling(tmp_path, monkeypatch):
    parent, source, refs = _repeated_fixture(tmp_path, child_target="2.35")
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    rows = [entry.data for entry in snapshot.entries if entry.data["record"] != "settled"]
    authority.memo_path.write_text("".join(json.dumps(row) + "\n" for row in rows))
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    with pytest.raises(MemoError, match="memo_inconsistent"):
        load_evaluated_view(authority.run_root)
    assert _tree_bytes(tmp_path) == before


def test_lock_access_error_does_not_count_as_a_dead_writer(tmp_path, monkeypatch):
    run_root = _pure_run(tmp_path)
    open_file = os.open
    def refuse_lock(path, *args, **kwargs):
        if path == "run.lock":
            raise PermissionError("lock cannot be read")
        return open_file(path, *args, **kwargs)
    monkeypatch.setattr(os, "open", refuse_lock)
    before = _tree_bytes(tmp_path)
    with pytest.raises(MemoError, match="lock cannot be read"):
        load_evaluated_view(run_root)
    assert _tree_bytes(tmp_path) == before


def test_state_manager_borrows_its_retained_root_without_closing_it(tmp_path):
    run_root = _pure_run(tmp_path)
    files = WorkspaceFiles(run_root)
    manager = StateManager(tmp_path, run_root.name)
    manager._retain_run_root_fd(files.root_fd)
    before = _tree_bytes(tmp_path)
    try:
        assert manager.load().status == "completed"
        assert manager._read_state_from_disk().to_dict() == manager.state.to_dict()
        assert os.fstat(manager._run_root_fd) and os.fstat(files.root_fd)
        assert not files.closed
    finally:
        manager.close()
        files.close()
    assert _tree_bytes(tmp_path) == before


def test_lock_probe_ignores_missing_lock_and_never_closes_borrowed_root(tmp_path):
    run_root = _pure_run(tmp_path)
    (run_root / "run.lock").unlink()
    before = _tree_bytes(tmp_path)
    with_files = WorkspaceFiles(run_root)
    try:
        descriptor = with_files.root_fd
        assert not run_writer_active(run_root, root_fd=descriptor)
        assert load_evaluated_view(run_root, run_files=with_files)["status"] == "completed"
        assert os.fstat(descriptor)
        assert not with_files.closed
    finally:
        with_files.close()
    assert _tree_bytes(tmp_path) == before


def test_released_real_writer_lock_reports_immediate_interruption(tmp_path):
    workspace = tmp_path / "interrupted"
    arguments, _hashes = _write_command_case(workspace)
    _kill_after_first_commit(workspace, arguments, _env(workspace))
    run_root = _run_root(workspace)
    with _subprocess_writer(run_root) as writer:
        before = _tree_bytes(run_root)
        assert load_evaluated_view(run_root)["status"] == "running"
        assert _tree_bytes(run_root) == before
        writer.kill()
        writer.wait(timeout=5)
        assert load_evaluated_view(run_root)["status"] == "interrupted"


@pytest.mark.parametrize("status", ["running", "settling", "interrupted", "completed", "failed"])
def test_evaluated_run_state_roundtrip_omits_legacy_audit_fields(tmp_path, status):
    view = load_evaluated_view(_pure_run(tmp_path))
    view["status"] = status
    payload = RunState.from_dict(view).to_dict()
    assert payload == view
    assert not {"context", "heartbeat", "step_visits", "transition_count", "call_frames",
                "observability", "runtime_observability", "provider_sessions", "for_each"}.intersection(payload)
