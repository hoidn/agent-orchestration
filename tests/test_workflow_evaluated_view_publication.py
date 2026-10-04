"""Live writers publish complete memo prefixes before continuing execution."""

from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import time

import pytest

from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow.evaluated import memo, runtime, run_ref
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_resume_kills import _env, _run_root, _write_command_case
from tests.test_workflow_evaluated_invalidate import _cli, _tree_bytes, _completed_run
from tests.test_workflow_evaluated_views import _snapshot
from tests.test_workflow_evaluated_view_publication_faults import _service_cli, _fail_allocation, _fail_command
from tests.test_workflow_evaluated_run_ref import _public_fixture, _authority
from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap, _service_run
from tests.test_workflow_evaluated_providers import _fixture, _requests
from tests.test_workflow_evaluated_readers import _pure_run


def test_pure_failure_after_commit_preserves_ordinary_failed_terminal(tmp_path):
    source = tmp_path / "failure.orc"
    source.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule failure) (export run) (defworkflow run ((divisor Float)) -> Float
        (let* ((value (command-result value :argv ("python" "value.py") :returns Float)))
          (/ value divisor))))''')
    (tmp_path / "value.py").write_text('import os\nfrom pathlib import Path\n'
        'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7.0")\n')
    boundaries = tmp_path / "commands.json"
    boundaries.write_text(json.dumps({"value": {"stable_command": ["python", "value.py"], "closure": ["value.py"]}}))
    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(boundaries), "--input", "divisor=0")
    assert result.returncode == 1, result.stderr
    run_root = _run_root(tmp_path)
    snapshot = _snapshot(run_root)
    assert snapshot.terminal is not None
    assert snapshot.terminal.data["code"] == "pure_expr_division_by_zero"
    assert load_evaluated_view(run_root)["status"] == "failed"
    assert json.loads((run_root / "state.json").read_bytes())["memo_offset"] == snapshot.complete_bytes


_LIVE_WRITER = '''\
import json, os, sys, time
from pathlib import Path
from orchestrator.workflow.evaluated import attempts, memo, run_ref, runtime

control = Path(os.environ["ORCHESTRATOR_TEST_CONTROL"])
append = memo.append_record
write = os.write
commit_count = 0
partial_done = False

def pause(stage):
    (control / stage).write_text("ready")
    while not (control / (stage + ".release")).exists():
        time.sleep(0.01)

def split_write(fd, data):
    global partial_done
    payload = bytes(data)
    if payload.startswith(b"{") and b'"record":"committed"' in payload and not partial_done:
        partial_done = True
        cut = len(data) // 2
        first = write(fd, data[:cut])
        pause("partial")
        return first + write(fd, data[cut:])
    return write(fd, data)

def gate(path, record, **kwargs):
    global commit_count
    if "time" in record:
        record["time"] = 1.0
    entry = append(path, record, **kwargs)
    if record["record"] == "started" and commit_count == 0:
        pause("started")
    elif record["record"] == "committed":
        commit_count += 1
        pause("first" if commit_count == 1 else "last")
    return entry

os.write = split_write
memo.append_record = attempts.append_record = run_ref.append_record = runtime.append_record = gate
from orchestrator.cli import main
raise SystemExit(main())
'''


def _wait_marker(process, marker):
    deadline = time.monotonic() + 15
    while not marker.exists():
        if process.poll() is not None:
            pytest.fail(f"writer exited before {marker.name}: {process.communicate()}")
        if time.monotonic() >= deadline:
            pytest.fail(f"writer did not reach {marker.name}")
        time.sleep(0.01)


@contextmanager
def _live_writer(workspace, arguments):
    control = workspace / ".test-control"
    control.mkdir()
    runner = control / "live_writer.py"
    runner.write_text(_LIVE_WRITER)
    process = subprocess.Popen([sys.executable, str(runner), *arguments], cwd=workspace,
        env={**_env(workspace), "ORCHESTRATOR_TEST_CONTROL": str(control)},
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        yield process, control
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
        process.communicate(timeout=5)


def _assert_live_view(run_root, status):
    before = _tree_bytes(run_root)
    view = load_evaluated_view(run_root)
    assert view["status"] == status
    assert view["workflow_outputs"] is None
    assert _tree_bytes(run_root) == before
    return view


def _assert_partial_reader(workspace, run_root, initial):
    before = _tree_bytes(run_root)
    view = _assert_live_view(run_root, "running")
    assert view["memo_offset"] == initial["memo_offset"]
    assert len((run_root / "memo.jsonl").read_bytes()) > view["memo_offset"]
    result = _cli(workspace, "report", "--run-id", run_root.name,
                  "--runs-root", str(run_root.parent), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["run"]["status"] == "running"
    assert _tree_bytes(run_root) == before


@pytest.mark.parametrize("kill_stage", ["first", "last"])
def test_real_writer_tail_liveness_and_immediate_interruption(tmp_path, kill_stage):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    with _live_writer(workspace, arguments) as (process, control):
        _wait_marker(process, control / "started")
        run_root = _run_root(workspace)
        initial = _assert_live_view(run_root, "running")
        assert not (run_root / "effects").exists()
        assert next(iter(initial["steps"].values()))["started_at"].startswith("1970")
        (control / "started.release").touch()
        _wait_marker(process, control / "partial")
        _assert_partial_reader(workspace, run_root, initial)
        (control / "partial.release").touch()
        _wait_marker(process, control / "first")
        after = _assert_live_view(run_root, "running")
        assert after["memo_offset"] > initial["memo_offset"]
        if kill_stage == "last":
            (control / "first.release").touch()
            _wait_marker(process, control / "last")
            _assert_live_view(run_root, "settling")
        os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=5)
        _assert_live_view(run_root, "interrupted")


def _observe_publication_order(monkeypatch):
    events, journals = [], {}
    open_append, fsync = memo._open_append, os.fsync
    write, mkdir = WorkspaceFiles.write_atomic, WorkspaceFiles.mkdir_exclusive

    def opened(path, run_files=None):
        fd = open_append(path, run_files)
        info = os.fstat(fd)
        journals[fd] = (run_files.workspace, info.st_dev, info.st_ino)
        return fd

    def synced(fd):
        fsync(fd)
        if fd in journals and stat.S_ISREG(os.fstat(fd).st_mode):
            info = os.fstat(fd)
            if (info.st_dev, info.st_ino) != journals[fd][1:]:
                return
            raw = os.pread(fd, os.fstat(fd).st_size, 0)
            try:
                row = json.loads(raw.splitlines()[-1])
            except (ValueError, IndexError):
                return
            if isinstance(row, dict) and "record" in row:
                events.append(("sync", journals[fd][0], row))

    def published(files, path, content, **kwargs):
        write(files, path, content, **kwargs)
        if Path(path).name == "state.json":
            snapshot = _snapshot(files.workspace)
            assert json.loads(content)["memo_offset"] == snapshot.complete_bytes
            assert files.read(path) == content
            events.append(("view", files.workspace, snapshot.entries[-1].data))

    def allocated(files, path):
        assert events[-1][:2] == ("view", files.workspace)
        assert events[-1][2]["record"] == "started"
        return mkdir(files, path)

    monkeypatch.setattr(memo, "_open_append", opened)
    monkeypatch.setattr(os, "fsync", synced)
    monkeypatch.setattr(WorkspaceFiles, "write_atomic", published)
    monkeypatch.setattr(WorkspaceFiles, "mkdir_exclusive", allocated)
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.run_writer_active",
                        lambda *_args, **_kwargs: pytest.fail("writer probed its own lock"))
    return events


def _assert_publication_pairs(events, run_root, records):
    selected = [(kind, row["record"]) for kind, root, row in events if root == run_root]
    assert selected == [(kind, record) for record in records for kind in ("sync", "view")]


@pytest.mark.parametrize("outcome", ["completed", "failed", "allocation"])
def test_sync_view_and_allocation_order_for_command_rows(tmp_path, monkeypatch, outcome):
    workspace = tmp_path / "commands"
    arguments, _hashes = _write_command_case(workspace)
    events = _observe_publication_order(monkeypatch)
    if outcome == "failed":
        _fail_command(workspace)
    if outcome == "allocation":
        _fail_allocation(monkeypatch, workspace)
    assert _service_cli(monkeypatch, workspace, arguments) == (0 if outcome == "completed" else 1)
    records = ["started", "committed", "started", "committed", "terminal"] if outcome == "completed" else ["started", "failed", "terminal"]
    _assert_publication_pairs(events, _run_root(workspace), records)
    if outcome == "completed":
        identity = next(iter(_snapshot(_run_root(workspace)).active_commits))
        assert _service_cli(monkeypatch, workspace, ["invalidate", _run_root(workspace).name, identity]) == 0
        _assert_publication_pairs(events, _run_root(workspace), [*records, "invalidated"])


def _provider_args(root, fixture):
    source, providers, prompts, _request = fixture
    return ["run", str(source), "--provider-externs-file", str(providers),
            "--prompt-externs-file", str(prompts), "--input", "message=typed input"]


def _provider_env(monkeypatch, root, mode):
    monkeypatch.setenv("PATH", str(root / "bin") + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("PROVIDER_SHIM_MODE", mode)


def test_provider_publication_uses_the_same_synced_prefix(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _provider_env(monkeypatch, tmp_path, "success")
    events = _observe_publication_order(monkeypatch)
    assert _service_cli(monkeypatch, tmp_path, _provider_args(tmp_path, fixture)) == 0
    _assert_publication_pairs(events, _run_root(tmp_path), ["started", "committed", "terminal"])
    assert len(_requests(tmp_path)) == 1


@pytest.mark.parametrize("recovery", [False, True])
def test_coordinator_sync_view_precedes_prepare_finalize_and_next_effect(tmp_path, monkeypatch, recovery):
    parent, source, refs = _public_fixture(tmp_path)
    prepare, finalize = run_ref.prepare_evaluated_run_ref, run_ref.finalize_run_ref_parent_commit
    if recovery:
        authority, _before = _commit_gap(monkeypatch, parent, source, refs)
    events = _observe_publication_order(monkeypatch)

    def prepared(authority, *args, **kwargs):
        assert events[-1][:2] == ("view", authority.run_root)
        assert events[-1][2]["record"] == "started"
        return prepare(authority, *args, **kwargs)

    def finalized(request, *args, **kwargs):
        assert events[-1][:2] == ("view", request.parent_run_root)
        assert events[-1][2]["record"] == "committed"
        return finalize(request, *args, **kwargs)

    monkeypatch.setattr(run_ref, "prepare_evaluated_run_ref", prepared)
    monkeypatch.setattr(run_ref, "finalize_run_ref_parent_commit", finalized)
    if recovery:
        assert _service_cli(monkeypatch, parent, ["resume", authority.run_root.name]) == 0
        expected = ["settled", "terminal"]
    else:
        assert _service_run(monkeypatch, parent, source, refs).exit_code == 0
        authority, _after = _authority(parent)
        expected = ["started", "committed", "settled", "terminal"]
    _assert_publication_pairs(events, authority.run_root, expected)


def _latest_failed_provider(run_root, attempt):
    snapshot = _snapshot(run_root)
    view = load_evaluated_view(run_root)
    row = next(iter(view["steps"].values()))
    failed = next(entry.data for entry in reversed(snapshot.entries) if entry.data["record"] == "failed")
    assert (view["status"], row["status"], row["attempt"], row["effect_class"]) == ("failed", "failed", attempt, "provider")
    assert row["error"]["code"] == failed["code"]
    assert "value" not in row and "completed_at" not in row
    assert f"attempt-{attempt}/result.json" in row["result_path"]
    assert json.loads((run_root / "state.json").read_bytes()) == view
    return row


def _assert_provider_completed_retry(root, run_root):
    view = load_evaluated_view(run_root)
    row = next(iter(view["steps"].values()))
    assert (view["status"], row["status"], row["attempt"]) == ("completed", "completed", 3)
    assert "error" not in row
    assert len(_requests(root)) == 3


def test_provider_retry_rows_use_current_error_and_preserve_earlier_attempts(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    _provider_env(monkeypatch, tmp_path, "nonzero")
    assert _service_cli(monkeypatch, tmp_path, _provider_args(tmp_path, fixture)) == 1
    run_root = _run_root(tmp_path)
    first = _latest_failed_provider(run_root, 1)
    first_root = run_root / Path(first["result_path"]).parent
    old_files = _tree_bytes(first_root)
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "invalid")
    assert _service_cli(monkeypatch, tmp_path, ["resume", run_root.name]) == 1
    second = _latest_failed_provider(run_root, 2)
    assert second["error"]["code"] != first["error"]["code"]
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    assert _service_cli(monkeypatch, tmp_path, ["resume", run_root.name]) == 0
    _assert_provider_completed_retry(tmp_path, run_root)
    assert _tree_bytes(first_root) == old_files


def test_public_suffix_invalidation_and_retry_publish_current_attempt_rows(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    before = load_evaluated_view(run_root)
    identities = list(before["steps"])
    old_files = {identity: _tree_bytes(run_root / Path(row["result_path"]).parent)
                 for identity, row in before["steps"].items()}
    assert _service_cli(monkeypatch, tmp_path, ["invalidate", run_root.name, identities[1]]) == 0
    published = json.loads((run_root / "state.json").read_bytes())
    assert [row["status"] for row in published["steps"].values()] == ["completed", "invalidated", "invalidated"]
    assert published["workflow_outputs"] is None
    assert _service_cli(monkeypatch, tmp_path, ["resume", run_root.name]) == 0
    after = load_evaluated_view(run_root)
    assert list(after["steps"]) == identities
    assert [row["attempt"] for row in after["steps"].values()] == [1, 2, 2]
    assert after == json.loads((run_root / "state.json").read_bytes())
    _assert_old_attempt_files(run_root, before, old_files)


def _assert_old_attempt_files(run_root, before, old_files):
    for identity, row in before["steps"].items():
        assert _tree_bytes(run_root / Path(row["result_path"]).parent) == old_files[identity]


@pytest.mark.parametrize("view", [None, b'{"status":"stale"}'])
def test_completed_resume_keeps_missing_or_stale_view_without_publication(tmp_path, monkeypatch, view):
    run_root = _pure_run(tmp_path)
    if view is None:
        (run_root / "state.json").unlink()
    else:
        (run_root / "state.json").write_bytes(view)
    before = _tree_bytes(run_root)
    monkeypatch.setattr("orchestrator.workflow.evaluated.views.publish_evaluated_view",
                        lambda *_args, **_kwargs: pytest.fail("completed resume published a view"))
    assert _service_cli(monkeypatch, tmp_path, ["resume", run_root.name]) == 0
    assert _tree_bytes(run_root) == before
