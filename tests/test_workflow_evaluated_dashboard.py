"""Public dashboard reads evaluated authority without mutating run evidence."""

import html
import json
import re
import os
import signal
import subprocess
import sys
from urllib.parse import quote

import pytest

from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from orchestrator.state import StateManager
from orchestrator.workflow.evaluated.memo import MemoError
from orchestrator.workflow.workspace_files import WorkspaceFiles
from orchestrator.workflow.evaluated.views import has_evaluated_authority
from tests.test_workflow_evaluated_readers import _pure_run, _scalar_run
from tests.test_workflow_evaluated_invalidate import _tree_bytes, _completed_run, _cli
from tests.test_workflow_evaluated_resume_kills import _write_command_case, _run_root
from tests.test_workflow_evaluated_view_publication import _live_writer, _wait_marker
from tests.test_workflow_evaluated_views import _forbid_mutable_paths, _snapshot
from tests.test_workflow_evaluated_run_ref import _public_fixture, _repeated_fixture, _authority
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap
from tests.test_run_lock import _subprocess_writer
from tests.test_workflow_evaluated_cli import _run_cli


def _outputs(response):
    match = re.search(r"<h2>Outputs</h2>\s*<pre>(.*?)</pre>", response.body.decode(), re.S)
    assert match is not None
    return json.loads(html.unescape(match.group(1)))


def test_dashboard_discovers_evaluated_root_without_state(tmp_path):
    run_root = _pure_run(tmp_path)
    (run_root / "state.json").unlink()
    before = _tree_bytes(tmp_path)
    app = DashboardApp(RunScanner([tmp_path]))
    index = app.handle("GET", "/runs")
    detail = app.handle("GET", f"/runs/w0/{run_root.name}")
    assert index.status == 200 and run_root.name in index.body.decode()
    assert detail.status == 200
    assert _outputs(detail) == {"accepted": True, "score": 0.75}
    assert _tree_bytes(tmp_path) == before


def _detail(workspace, run_root):
    record = next(run for run in RunScanner([workspace]).scan().runs if run.run_root == run_root)
    return RunProjector().project_detail(record)


def _no_legacy(*_args, **_kwargs):
    pytest.fail("evaluated dashboard reached legacy metadata/status/observability")


def _forbid_legacy(monkeypatch):
    _forbid_mutable_paths(monkeypatch)
    for name in ("_load_workflow", "_steps_from_state", "_row", "_observability_files", "_availability"):
        monkeypatch.setattr(RunProjector, name, _no_legacy)
    monkeypatch.setattr("orchestrator.dashboard.projection.build_status_snapshot", _no_legacy)
    monkeypatch.setattr("orchestrator.dashboard.projection.derive_status_projection", _no_legacy)


def test_dashboard_effect_rows_keep_memo_order_without_flat_sources(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    view = _snapshot(run_root)
    for name in ("invalidate_public.orc", "commands.json", "prefix.py", "writer.py", "reader.py"):
        (tmp_path / name).unlink()
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    detail = _detail(tmp_path, run_root)
    assert [step.ref for step in detail.steps] == list(view.active_commits)
    assert [step.kind for step in detail.steps] == ["command"] * 3
    assert [json.loads(step.output_preview) for step in detail.steps] == [1, 20, 20]
    assert detail.workflow_structure is None and detail.observability_files == {}
    assert detail.row.state_mtime is None and detail.row.heartbeat_at is None
    assert _tree_bytes(tmp_path) == before


def _assert_live_dashboard(workspace, run_root, status):
    before = _tree_bytes(run_root)
    detail = _detail(workspace, run_root)
    response = DashboardApp(RunScanner([workspace])).handle("GET", f"/runs/w0/{run_root.name}")
    assert response.status == 200 and _outputs(response) is None
    assert detail.row.display_status == status
    assert detail.row.heartbeat_at is None and detail.row.state_mtime is None
    assert detail.row.updated_at.startswith("1970")
    assert _tree_bytes(run_root) == before
    return detail


@pytest.mark.parametrize("kill_stage", ["first", "last"])
def test_dashboard_real_writer_partial_tail_cursor_and_kill(tmp_path, kill_stage):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    with _live_writer(workspace, arguments) as (process, control):
        _wait_marker(process, control / "started")
        run_root = _run_root(workspace)
        initial = _assert_live_dashboard(workspace, run_root, "running")
        assert initial.cursor.summary == initial.state["current_step"]["identity"]
        (control / "started.release").touch()
        _wait_marker(process, control / "partial")
        partial = _assert_live_dashboard(workspace, run_root, "running")
        assert partial.state["memo_offset"] == initial.state["memo_offset"]
        (control / "partial.release").touch()
        _wait_marker(process, control / "first")
        current = _assert_live_dashboard(workspace, run_root, "running")
        assert current.cursor.summary == current.state["next_effect"]
        if kill_stage == "last":
            (control / "first.release").touch()
            _wait_marker(process, control / "last")
            _assert_live_dashboard(workspace, run_root, "settling")
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        _assert_live_dashboard(workspace, run_root, "interrupted")


@pytest.mark.parametrize("reader", ["dashboard", "report", "state-manager"])
def test_completed_view_without_any_authority_is_readonly_refusal(tmp_path, reader):
    run_root = _pure_run(tmp_path)
    for name in ("run.json", "closed_program.json", "memo.jsonl"):
        (run_root / name).unlink()
    before = _tree_bytes(tmp_path)
    if reader == "dashboard":
        response = DashboardApp(RunScanner([tmp_path])).handle("GET", f"/runs/w0/{run_root.name}")
        assert response.status == 200
        assert _detail(tmp_path, run_root).row.display_status == "unreadable"
        assert "memo_inconsistent" in response.body.decode()
        assert _outputs(response) != {"accepted": True, "score": 0.75}
    elif reader == "report":
        result = _cli(tmp_path, "report", "--run-id", run_root.name,
                      "--runs-root", str(run_root.parent), "--format", "json")
        assert result.returncode == 1 and "memo_inconsistent" in result.stderr
        assert result.stdout == ""
    else:
        with pytest.raises(MemoError, match="memo_inconsistent"):
            StateManager(tmp_path, run_root.name).load()
    assert _tree_bytes(tmp_path) == before


def test_state_manager_missing_authority_uses_borrowed_root_and_keeps_fd(tmp_path):
    run_root = _pure_run(tmp_path)
    files = WorkspaceFiles(run_root)
    manager = StateManager(tmp_path, run_root.name)
    manager._retain_run_root_fd(files.root_fd)
    original = run_root.with_name(run_root.name + "-held")
    try:
        run_root.rename(original)
        run_root.mkdir()
        (run_root / "replacement.txt").write_text("untouched")
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            (original / name).unlink()
        before = _tree_bytes(tmp_path)
        with pytest.raises(MemoError, match="memo_inconsistent"):
            manager.load()
        assert not files.closed and os.fstat(files.root_fd).st_ino == original.stat().st_ino
        assert os.fstat(manager._run_root_fd)
        assert json.loads(files.read("state.json"))["status"] == "completed"
        assert _tree_bytes(tmp_path) == before
    finally:
        manager.close()
        files.close()


@pytest.mark.parametrize("borrowed", [False, True])
def test_legacy_missing_state_retains_file_not_found_contract(tmp_path, borrowed):
    manager = StateManager(tmp_path, "missing")
    manager.run_root.mkdir(parents=True, exist_ok=True)
    files = WorkspaceFiles(manager.run_root)
    try:
        if borrowed:
            manager._retain_run_root_fd(files.root_fd)
        before = _tree_bytes(tmp_path)
        with pytest.raises(FileNotFoundError):
            manager.load()
        assert _tree_bytes(tmp_path) == before
        assert not files.closed and os.fstat(files.root_fd)
    finally:
        manager.close()
        files.close()


def test_borrowed_authority_symlink_is_checked_memo_refusal(tmp_path):
    run_root = _pure_run(tmp_path)
    files = WorkspaceFiles(run_root)
    manager = StateManager(tmp_path, run_root.name)
    manager._retain_run_root_fd(files.root_fd)
    target = run_root / "run.json"
    outside = tmp_path / "outside-header.json"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    target.symlink_to(outside)
    before = _tree_bytes(tmp_path)
    try:
        with pytest.raises(MemoError, match="memo_inconsistent"):
            manager.load()
        assert _tree_bytes(tmp_path) == before
        assert not files.closed and os.fstat(files.root_fd)
    finally:
        manager.close()
        files.close()


@pytest.mark.parametrize("kind", ["regular", "symlink", "invalid-json"])
def test_view_hint_is_regular_nofollow_nonblocking_and_closes_owner(tmp_path, monkeypatch, kind):
    run_root = _pure_run(tmp_path)
    for name in ("run.json", "closed_program.json", "memo.jsonl"):
        (run_root / name).unlink()
    state = run_root / "state.json"
    _change_hint_file(tmp_path, state, kind)
    owners = []
    read = WorkspaceFiles.read
    def captured(files, path):
        owners.append(files)
        return read(files, path)
    monkeypatch.setattr(WorkspaceFiles, "read", captured)
    before = _tree_bytes(tmp_path)
    assert has_evaluated_authority(run_root) is (kind == "regular")
    assert owners and all(files.closed for files in owners)
    assert _tree_bytes(tmp_path) == before


def _change_hint_file(workspace, state, kind):
    if kind == "symlink":
        outside = workspace / "outside-state.json"
        outside.write_bytes(state.read_bytes())
        state.unlink()
        state.symlink_to(outside)
    elif kind == "fifo":
        state.unlink()
        os.mkfifo(state)
    elif kind == "invalid-json":
        state.write_bytes(b"invalid json")


def test_view_hint_borrows_owner_without_closing_or_using_replacement(tmp_path):
    run_root = _pure_run(tmp_path)
    files = WorkspaceFiles(run_root)
    original = run_root.with_name(run_root.name + "-original")
    try:
        for name in ("run.json", "closed_program.json", "memo.jsonl"):
            (run_root / name).unlink()
        run_root.rename(original)
        run_root.mkdir()
        before = _tree_bytes(tmp_path)
        assert has_evaluated_authority(run_root, run_files=files)
        assert not files.closed and os.fstat(files.root_fd).st_ino == original.stat().st_ino
        assert _tree_bytes(tmp_path) == before
    finally:
        files.close()


def test_scanner_confines_root_before_authority_detector(tmp_path, monkeypatch):
    outside, workspace = tmp_path / "outside", tmp_path / "workspace"
    outside.mkdir()
    workspace.mkdir()
    run_root = _pure_run(outside)
    runs = workspace / ".orchestrate" / "runs"
    runs.mkdir(parents=True)
    (runs / run_root.name).symlink_to(run_root, target_is_directory=True)
    monkeypatch.setattr("orchestrator.dashboard.scanner.has_evaluated_authority", _no_legacy)
    before = _tree_bytes(tmp_path)
    record, = RunScanner([workspace]).scan().runs
    assert record.state is None and "escapes workspace" in record.read_error
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("returns,expression,value", [
    ("Int", "0", 0), ("Bool", "false", False), ("Optional[Int]", "null", None),
    ("List[Int]", "(list 1 2)", [1, 2]), ("List[Int]", "(list)", []),
])
def test_public_dashboard_and_report_preserve_direct_json_without_sources(tmp_path, monkeypatch, returns, expression, value):
    run_root = _scalar_run(tmp_path, returns, expression)
    (tmp_path / "scalar.orc").unlink()
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    response = DashboardApp(RunScanner([tmp_path])).handle("GET", f"/runs/w0/{run_root.name}")
    detail = _detail(tmp_path, run_root)
    assert response.status == 200 and _outputs(response) == value
    assert type(detail.workflow_outputs) is type(value)
    result = _cli(tmp_path, "report", "--run-id", run_root.name,
                  "--runs-root", str(run_root.parent), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run"]["workflow_outputs"] == value
    assert _tree_bytes(tmp_path) == before


@pytest.mark.parametrize("corruption", ["unknown-schema", "unknown-profile", "missing-header", "bad-journal", "bad-terminal", "adjacent-terminal"])
def test_corrupt_authority_candidate_is_visible_without_completed_outputs(tmp_path, monkeypatch, corruption):
    run_root = _pure_run(tmp_path)
    _corrupt_authority(run_root, corruption)
    _forbid_mutable_paths(monkeypatch)
    before = _tree_bytes(tmp_path)
    app = DashboardApp(RunScanner([tmp_path]))
    index = app.handle("GET", "/runs")
    response = app.handle("GET", f"/runs/w0/{run_root.name}")
    assert index.status == 200 and run_root.name in index.body.decode()
    assert response.status == 200 and "memo_inconsistent" in response.body.decode()
    assert _detail(tmp_path, run_root).row.display_status == "unreadable"
    assert _outputs(response) != {"accepted": True, "score": 0.75}
    assert _tree_bytes(tmp_path) == before


def _corrupt_authority(run_root, corruption):
    if corruption in {"unknown-schema", "unknown-profile"}:
        path = run_root / "run.json"
        header = json.loads(path.read_bytes())
        key = "schema_version" if corruption == "unknown-schema" else "result_persistence_profile"
        header[key] = "unknown"
        path.write_text(json.dumps(header))
    elif corruption == "missing-header":
        (run_root / "run.json").unlink()
    elif corruption == "bad-journal":
        (run_root / "memo.jsonl").write_bytes(b"bad JSON\n")
    else:
        path = run_root / "memo.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        if corruption == "bad-terminal":
            rows[-1]["value"] = "wrong halt"
        else:
            rows.append(dict(rows[-1]))
        path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_dashboard_unsettled_coordinator_needs_no_reconciliation(tmp_path, monkeypatch):
    parent, source, refs = _public_fixture(tmp_path)
    authority, snapshot = _commit_gap(monkeypatch, parent, source, refs)
    _forbid_legacy(monkeypatch)
    with _subprocess_writer(authority.run_root):
        before = _tree_bytes(tmp_path)
        detail = _detail(parent, authority.run_root)
        assert detail.row.display_status == "settling" and detail.workflow_outputs is None
        step, = detail.steps
        assert step.kind == "run_ref" and step.status == "settling"
        assert detail.cursor.summary == step.ref
        assert detail.state["memo_offset"] == snapshot.complete_bytes
        assert _tree_bytes(tmp_path) == before


def test_view_hint_fifo_refuses_with_process_deadline(tmp_path):
    run_root = _pure_run(tmp_path)
    for name in ("run.json", "closed_program.json", "memo.jsonl"):
        (run_root / name).unlink()
    _change_hint_file(tmp_path, run_root / "state.json", "fifo")
    before = _tree_bytes(tmp_path)
    probe = "from pathlib import Path; from orchestrator.workflow.evaluated.views import has_evaluated_authority; import sys; assert not has_evaluated_authority(Path(sys.argv[1]))"
    result = subprocess.run([sys.executable, "-B", "-c", probe, str(run_root)],
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert _tree_bytes(tmp_path) == before


def test_dashboard_nested_loop_visits_preserve_committed_values_without_sources(tmp_path, monkeypatch):
    parent, source, refs = _repeated_fixture(tmp_path, child_target="2.35", structure="nested", forwarding=True)
    result = _run_cli(parent, str(source), "--run-ref-root", str(refs))
    assert result.returncode == 0, result.stderr
    authority, snapshot = _authority(parent)
    source.unlink()
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    detail = _detail(parent, authority.run_root)
    identities = list(snapshot.active_commits)
    assert [step.ref for step in detail.steps] == identities
    assert len(identities) == 2 and identities[0] != identities[1]
    assert [row["value"]["value"] for row in detail.state["steps"].values()] == [False, True]
    assert detail.workflow_outputs is True and detail.cursor.summary == ""
    response = DashboardApp(RunScanner([parent])).handle("GET", f"/runs/w0/{authority.run_root.name}/steps/{quote(identities[1], safe='')}")
    assert response.status == 200
    assert _tree_bytes(tmp_path) == before
