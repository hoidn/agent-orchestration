"""Writer publication faults leave synchronized memo evidence authoritative."""

import json
import os
from dataclasses import replace
from contextlib import closing
from pathlib import Path
import sys

import pytest

from orchestrator.cli import main
from orchestrator.workflow import workspace_files as files_module
from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.evaluated.authority import load_run_authority
from orchestrator.workflow.evaluated.memo import append_record, MemoError
from orchestrator.workflow.run_ref.ledger import load_attempt_ledger
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_resume_kills import _write_command_case, _run_root
from tests.test_workflow_evaluated_views import _snapshot
from tests.test_workflow_evaluated_run_ref import _public_fixture, _authority
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap, _service_run
from tests.test_workflow_evaluated_readers import _pure_run
from tests.test_workflow_evaluated_invalidate import _tree_bytes


def _service_cli(monkeypatch, workspace, arguments):
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sys, "argv", ["orchestrator", *arguments])
    return main(arguments)


def test_view_replace_failure_preserves_synced_commit_and_stops_dispatch(tmp_path, monkeypatch, caplog):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    write_atomic = WorkspaceFiles.write_atomic
    failed = []

    def fail_first_commit(files, path, content, **kwargs):
        if Path(path).name == "state.json" and _snapshot(files.workspace).active_commits:
            failed.append(files.workspace)
            raise OSError("injected state replacement IO failure")
        return write_atomic(files, path, content, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, "write_atomic", fail_first_commit)
    result = _service_cli(monkeypatch, workspace, arguments)
    assert result == 1
    snapshot = _snapshot(_run_root(workspace))
    assert [row.data["record"] for row in snapshot.entries] == ["started", "committed"]
    assert failed == [_run_root(workspace)]
    assert json.loads((workspace / "dispatches.jsonl").read_text()) == {"kind": "first"}
    assert "injected state replacement IO failure" in caplog.text
    prefix = (_run_root(workspace) / "memo.jsonl").read_bytes()
    monkeypatch.setattr(WorkspaceFiles, "write_atomic", write_atomic)
    assert _service_cli(monkeypatch, workspace, ["resume", _run_root(workspace).name]) == 0
    assert (_run_root(workspace) / "memo.jsonl").read_bytes().startswith(prefix)
    assert [json.loads(line)["kind"] for line in (workspace / "dispatches.jsonl").read_text().splitlines()] == ["first", "second"]
    assert load_evaluated_view(_run_root(workspace))["status"] == "completed"


def _state_replace_fault(monkeypatch, workspace, record, *, by=None):
    write_atomic = WorkspaceFiles.write_atomic
    failures = []

    def fail_replace(source, destination, **kwargs):
        failures.append(destination)
        raise OSError("injected atomic state replace failure")

    def write(files, path, content, **kwargs):
        if Path(path).name != "state.json" or not files.workspace.is_relative_to(workspace):
            return write_atomic(files, path, content, **kwargs)
        row = _snapshot(files.workspace).entries[-1].data
        if row["record"] != record or (by is not None and row.get("by") != by):
            return write_atomic(files, path, content, **kwargs)
        with monkeypatch.context() as context:
            context.setattr(files_module.os, "replace", fail_replace)
            return write_atomic(files, path, content, **kwargs)

    monkeypatch.setattr(WorkspaceFiles, "write_atomic", write)
    return failures


def _fail_command(workspace):
    probe = workspace / "probe.py"
    probe.write_text(probe.read_text().replace(
        'value = 5 if kind == "first" else int(sys.argv[2]) + 1', 'sys.exit(9)'))


def _fail_allocation(monkeypatch, workspace):
    mkdir = WorkspaceFiles.mkdir_exclusive

    def refuse(files, path):
        if files.workspace.is_relative_to(workspace):
            raise PermissionError("injected attempt allocation failure")
        return mkdir(files, path)

    monkeypatch.setattr(WorkspaceFiles, "mkdir_exclusive", refuse)


def _assert_records(workspace, expected):
    snapshot = _snapshot(_run_root(workspace))
    assert [entry.data["record"] for entry in snapshot.entries] == expected
    return snapshot


def _assert_command_dispatch_count(workspace, fault):
    path = workspace / "dispatches.jsonl"
    rows = path.read_text().splitlines() if path.exists() else []
    assert len(rows) == {"started": 0, "allocation": 0, "effect": 1, "completed": 2, "failed-terminal": 1}[fault]


def _assert_completed_resume_readonly(monkeypatch, workspace, failures):
    before = _tree_bytes(workspace)
    assert _service_cli(monkeypatch, workspace, ["resume", _run_root(workspace).name]) == 0
    assert _tree_bytes(workspace) == before and failures == ["state.json"]


@pytest.mark.parametrize("fault,record,expected", [
    ("started", "started", ["started"]),
    ("allocation", "failed", ["started", "failed"]),
    ("effect", "failed", ["started", "failed"]),
    ("completed", "terminal", ["started", "committed", "started", "committed", "terminal"]),
    ("failed-terminal", "terminal", ["started", "failed", "terminal"]),
])
def test_atomic_replace_fault_at_command_publication_seams(tmp_path, monkeypatch, caplog, fault, record, expected):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    if fault == "allocation":
        _fail_allocation(monkeypatch, workspace)
    if fault in {"effect", "failed-terminal"}:
        _fail_command(workspace)
    failures = _state_replace_fault(monkeypatch, workspace, record)
    assert _service_cli(monkeypatch, workspace, arguments) == 1
    _assert_records(workspace, expected)
    _assert_command_dispatch_count(workspace, fault)
    assert failures == ["state.json"]
    assert "view_write_failed" in caplog.text
    assert "injected atomic state replace failure" in caplog.text
    if fault == "completed":
        _assert_completed_resume_readonly(monkeypatch, workspace, failures)


@pytest.mark.parametrize("record", ["committed", "settled"])
def test_coordinator_replace_failure_stops_before_finalize_or_terminal(tmp_path, monkeypatch, caplog, record):
    parent, source, refs = _public_fixture(tmp_path)
    failures = _state_replace_fault(monkeypatch, parent, record)
    assert _service_run(monkeypatch, parent, source, refs).exit_code == 1
    authority, snapshot = _authority(parent)
    expected = ["started", "committed"] + (["settled"] if record == "settled" else [])
    assert [entry.data["record"] for entry in snapshot.entries] == expected
    ledger = load_attempt_ledger(authority.run_root / "run-ref-attempts.jsonl")
    assert ledger.rows[-1].stage == ("committed" if record == "settled" else "completed_pending_parent_commit")
    assert len(list(refs.rglob("child-request.json"))) == 1
    assert failures == ["state.json"]
    assert "view_write_failed" in caplog.text


def test_reconcile_replace_failure_keeps_settlement_without_recursive_terminal(tmp_path, monkeypatch, caplog):
    parent, source, refs = _public_fixture(tmp_path)
    authority, _snapshot_before = _commit_gap(monkeypatch, parent, source, refs)
    failures = _state_replace_fault(monkeypatch, parent, "settled", by="reconcile")
    assert _service_cli(monkeypatch, parent, ["resume", authority.run_root.name]) == 1
    _assert_records(parent, ["started", "committed", "settled"])
    assert len(list(refs.rglob("child-request.json"))) == 1
    assert failures == ["state.json"]
    assert "view_write_failed" in caplog.text


def test_public_invalidation_replace_failure_preserves_range_and_old_view(tmp_path, monkeypatch, capsys):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    assert _service_cli(monkeypatch, workspace, arguments) == 0
    run_root = _run_root(workspace)
    snapshot = _snapshot(run_root)
    identity = next(iter(snapshot.active_commits))
    old_view = (run_root / "state.json").read_bytes()
    failures = _state_replace_fault(monkeypatch, workspace, "invalidated")
    assert _service_cli(monkeypatch, workspace, ["invalidate", run_root.name, identity]) == 2
    after = _snapshot(run_root)
    assert after.entries[-1].data["record"] == "invalidated" and not after.active_commits
    assert (run_root / "state.json").read_bytes() == old_view
    assert load_evaluated_view(run_root)["status"] == "interrupted"
    assert failures == ["state.json"]
    assert "view_write_failed" in capsys.readouterr().err


@pytest.mark.parametrize("context", ["missing-owner", "other-owner", "other-root", "other-journal"])
def test_checked_publication_context_rejects_mismatch_before_append(tmp_path, context):
    run_root = _pure_run(tmp_path)
    with closing(WorkspaceFiles(run_root)) as files, closing(WorkspaceFiles(run_root)) as other:
        authority = load_run_authority(run_root, run_files=files)
        path = authority.memo_path
        if context == "missing-owner":
            authority = replace(authority, run_files=None)
        elif context == "other-owner":
            authority = replace(authority, run_files=other)
        elif context == "other-root":
            authority = replace(authority, run_root=tmp_path)
            path = authority.memo_path
        else:
            path = run_root / "other.jsonl"
        before = _tree_bytes(tmp_path)
        with pytest.raises(MemoError, match="publication"):
            append_record(path, {"record": "invalidated", "from_commit": 0, "time": 1.0},
                          run_files=files, checked_authority=authority)
        assert _tree_bytes(tmp_path) == before


def _swap_root_after_commit_sync(monkeypatch, workspace):
    fsync = os.fsync
    displaced = []

    def synced(fd):
        fsync(fd)
        if displaced:
            return
        roots = list((workspace / ".orchestrate" / "runs").glob("*"))
        if not roots or not (roots[0] / "memo.jsonl").exists():
            return
        root = roots[0]
        info, journal = os.fstat(fd), (root / "memo.jsonl").stat()
        if not info.st_size or (info.st_dev, info.st_ino) != (journal.st_dev, journal.st_ino):
            return
        if json.loads(os.pread(fd, info.st_size, 0).splitlines()[-1])["record"] != "committed":
            return
        old_root = root.with_name(root.name + "-displaced")
        root.rename(old_root)
        root.mkdir()
        (root / "substitute.txt").write_text("untouched")
        displaced.append(old_root)

    monkeypatch.setattr(os, "fsync", synced)
    return displaced


def test_retained_root_change_after_synced_commit_stops_as_publication_error(tmp_path, monkeypatch, caplog):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    displaced = _swap_root_after_commit_sync(monkeypatch, workspace)
    assert _service_cli(monkeypatch, workspace, arguments) == 1
    old_root, = displaced
    rows = [json.loads(line) for line in (old_root / "memo.jsonl").read_text().splitlines()]
    assert [row["record"] for row in rows] == ["started", "committed"]
    assert (old_root / "state.json").exists()
    substitute = old_root.with_name(old_root.name.removesuffix("-displaced"))
    assert list(substitute.iterdir()) == [substitute / "substitute.txt"]
    assert (substitute / "substitute.txt").read_text() == "untouched"
    assert "view_write_failed" in caplog.text
    assert "reserved_run_root_changed" in caplog.text
