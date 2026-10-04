"""Evaluated dashboard file routes use the current attempt's real evidence."""

import html
import json
import os
from pathlib import Path
from urllib.parse import quote

import pytest

from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp
from tests.test_workflow_evaluated_dashboard import _detail, _forbid_legacy
from tests.test_workflow_evaluated_invalidate import _completed_run, _cli, _tree_bytes, _fixture as _command_fixture
from tests.test_workflow_evaluated_providers import _fixture, _cli as _provider_cli, _requests
from tests.test_workflow_evaluated_resume_kills import _run_root
from tests.test_workflow_evaluated_view_publication import _provider_env
from tests.test_workflow_evaluated_views import _snapshot


def _preview(app, run_root, reference, *, raw=False):
    route = f"/runs/w0/{run_root.name}/files/run/{quote(reference.route_path, safe='/')}"
    return app.handle("GET", route + ("?raw=1" if raw else ""))


def test_command_current_attempt_files_and_missing_result_keep_memo_value(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    step = _detail(tmp_path, run_root).steps[1]
    row = _snapshot(run_root).active_commits[step.ref].data
    assert set(step.file_refs) == {"result", "stdout", "stderr"}
    assert step.file_refs["result"].route_path == row["result_path"]
    app = DashboardApp(RunScanner([tmp_path]))
    for reference in step.file_refs.values():
        response = _preview(app, run_root, reference)
        assert response.status == 200
    assert _tree_bytes(tmp_path) == before
    (run_root / row["result_path"]).unlink()
    before = _tree_bytes(tmp_path)
    step = _detail(tmp_path, run_root).steps[1]
    assert json.loads(step.output_preview) == 20
    response = _preview(app, run_root, step.file_refs["result"])
    assert response.status == 200 and "missing" in response.body.decode()
    assert _tree_bytes(tmp_path) == before


def _assert_provider_preview(workspace, run_root, attempt):
    before = _tree_bytes(workspace)
    detail = _detail(workspace, run_root)
    step, = detail.steps
    row = detail.state["steps"][step.ref]
    assert row["attempt"] == attempt
    assert set(step.file_refs) == {"result", "prompt", "stdout", "stderr"}
    app = DashboardApp(RunScanner([workspace]))
    for name in ("prompt", "stdout", "stderr"):
        reference = step.file_refs[name]
        assert f"attempt-{attempt}/" in reference.route_path
        content = reference.absolute_path.read_text()
        response = _preview(app, run_root, reference)
        assert response.status == 200 and html.escape(content, quote=False) in response.body.decode()
    assert _tree_bytes(workspace) == before
    return step, row


def test_provider_retry_previews_keep_latest_error_and_older_attempts(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    binary = tmp_path / "bin" / "codex"
    binary.write_text(binary.read_text().replace('b"complete stderr\\n"', '("stderr-" + mode + "<script>\\n").encode()'))
    assert _provider_cli(tmp_path, fixture, mode="nonzero").returncode == 1
    run_root = _run_root(tmp_path)
    _forbid_legacy(monkeypatch)
    first, first_row = _assert_provider_preview(tmp_path, run_root, 1)
    old = _tree_bytes(first.file_refs["prompt"].absolute_path.parent)
    _provider_env(monkeypatch, tmp_path, "invalid")
    assert _cli(tmp_path, "resume", run_root.name).returncode == 1
    second, second_row = _assert_provider_preview(tmp_path, run_root, 2)
    assert second.error["code"] != first.error["code"]
    assert "value" not in second_row
    monkeypatch.setenv("PROVIDER_SHIM_MODE", "success")
    assert _cli(tmp_path, "resume", run_root.name).returncode == 0
    final, final_row = _assert_provider_preview(tmp_path, run_root, 3)
    assert final.error is None and final_row["value"] == {"ok": True}
    assert len(_requests(tmp_path)) == 3
    assert _tree_bytes(first.file_refs["prompt"].absolute_path.parent) == old


def test_invalidate_retry_previews_use_new_attempt_and_preserve_old_files(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    original = _detail(tmp_path, run_root)
    identities = [step.ref for step in original.steps]
    old = [_tree_bytes(step.file_refs["result"].absolute_path.parent) for step in original.steps]
    result = _cli(tmp_path, "invalidate", run_root.name, identities[1])
    assert result.returncode == 0, result.stderr
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    invalid = _detail(tmp_path, run_root)
    assert [step.status for step in invalid.steps] == ["completed", "invalidated", "invalidated"]
    assert invalid.cursor.summary == identities[1] and invalid.workflow_outputs is None
    assert _tree_bytes(tmp_path) == before
    result = _cli(tmp_path, "resume", run_root.name)
    assert result.returncode == 0, result.stderr
    final = _detail(tmp_path, run_root)
    assert [step.ref for step in final.steps] == identities
    assert [row["attempt"] for row in final.state["steps"].values()] == [1, 2, 2]
    _assert_old_files(original.steps, old)
    assert "attempt-2/" in final.steps[1].file_refs["result"].route_path


def test_attempt_file_routes_reject_symlink_escape_and_traversal(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    step = _detail(tmp_path, run_root).steps[0]
    stream = step.file_refs["stdout"].absolute_path
    outside = tmp_path / "outside.txt"
    outside.write_text("private outside bytes")
    stream.unlink()
    stream.symlink_to(outside)
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    detail = _detail(tmp_path, run_root)
    assert "stdout" not in detail.steps[0].file_refs
    assert any("unsafe stdout" in warning for warning in detail.warnings)
    app = DashboardApp(RunScanner([tmp_path]))
    response = _preview(app, run_root, step.file_refs["stdout"])
    assert response.status == 400 and b"private outside bytes" not in response.body
    route = f"/runs/w0/{run_root.name}/files/run/%2e%2e/outside.txt"
    assert app.handle("GET", route).status == 400
    assert _tree_bytes(tmp_path) == before


def test_actual_stream_preview_escapes_limits_and_raw_download(tmp_path, monkeypatch):
    source, commands = _command_fixture(tmp_path, 20)
    script = tmp_path / "prefix.py"
    script.write_text(script.read_text() + '\nprint("<script>unsafe</script>" + "X" * 70000)\n')
    result = _cli(tmp_path, "run", str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    run_root = _run_root(tmp_path)
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    reference = _detail(tmp_path, run_root).steps[0].file_refs["stdout"]
    app = DashboardApp(RunScanner([tmp_path]))
    response = _preview(app, run_root, reference)
    assert response.status == 200
    assert "&lt;script&gt;unsafe&lt;/script&gt;" in response.body.decode()
    assert "truncated" in response.body.decode().lower()
    raw = _preview(app, run_root, reference, raw=True)
    assert raw.status == 200 and raw.body == reference.absolute_path.read_bytes()
    assert raw.headers["X-Content-Type-Options"] == "nosniff"
    assert raw.headers["Content-Disposition"].startswith("attachment")
    assert _tree_bytes(tmp_path) == before


def _assert_old_files(steps, old):
    for index, step in enumerate(steps):
        assert _tree_bytes(step.file_refs["result"].absolute_path.parent) == old[index]


def _escaped_loop_run(workspace):
    source, commands = _command_fixture(workspace, 20)
    source.write_text("""(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule invalidate_public) (export run)
      (defworkflow run () -> Int
        (loop/recur :max 2 :state (loop-state (round Int 0)) :on-exhausted 99
          (fn (state)
            (let* ((emit/part (command-result prefix :argv ("python" "prefix.py") :returns Int)))
              (if (= state.round 0)
                (continue (record-update state :round 1)) (done emit/part)))))))""")
    result = _cli(workspace, "run", str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    return _run_root(workspace)


def test_report_dashboard_and_invalidate_share_escaped_loop_identity(tmp_path, monkeypatch):
    run_root = _escaped_loop_run(tmp_path)
    detail = _detail(tmp_path, run_root)
    identities = [step.ref for step in detail.steps]
    assert len(identities) == 2
    assert all("emit%2Fpart" in identity for identity in identities)
    assert "[1]" in identities[0] and "[2]" in identities[1]
    result = _cli(tmp_path, "report", "--run-id", run_root.name,
                  "--runs-root", str(run_root.parent), "--format", "json")
    assert result.returncode == 0, result.stderr
    assert [row["name"] for row in json.loads(result.stdout)["steps"]] == identities
    _assert_canonical_step_route(tmp_path, run_root, identities[1])
    result = _cli(tmp_path, "invalidate", run_root.name, identities[1])
    assert result.returncode == 0, result.stderr
    _forbid_legacy(monkeypatch)
    before = _tree_bytes(tmp_path)
    invalid = _detail(tmp_path, run_root)
    assert invalid.cursor.summary == identities[1]
    assert [step.status for step in invalid.steps] == ["completed", "invalidated"]
    assert _tree_bytes(tmp_path) == before


def _assert_canonical_step_route(workspace, run_root, identity):
    before = _tree_bytes(workspace)
    app = DashboardApp(RunScanner([workspace]))
    response = app.handle("GET", f"/runs/w0/{run_root.name}/steps/{quote(identity, safe='')}")
    assert response.status == 200
    assert html.escape(identity) in response.body.decode()
    assert _tree_bytes(workspace) == before
