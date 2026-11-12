"""Tests for dashboard server routes."""

from __future__ import annotations

import html
import http.client
import json
import threading
import os
import re
from datetime import datetime, timedelta
from urllib.parse import quote
from pathlib import Path


import pytest

from orchestrator.dashboard.projection import RunProjector
from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp, make_dashboard_server
from orchestrator.workflow.evaluated.views import load_evaluated_view
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_evaluated_invalidate import _completed_run, _tree_bytes
from tests.test_workflow_evaluated_readers import _pure_run, _scalar_run
from tests.workflow_inprocess_cli_helpers import cli_inprocess


FAILING_SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule fresh_flow) (export run)
  (defworkflow run () -> String
    (let* ((shown (command-result shown :argv ("python" "shown.py") :returns String))
           (fail (command-result fail :argv ("python" "fail.py") :returns Int)))
      shown)))
'''


def _run_names(workspace: Path) -> set[str]:
    runs = workspace / ".orchestrate" / "runs"
    return {path.name for path in runs.iterdir()} if runs.exists() else set()


def _new_run(workspace: Path, before: set[str]) -> Path:
    (run_root,) = [path for path in (workspace / ".orchestrate" / "runs").iterdir() if path.name not in before]
    return run_root


def _failing_run(workspace: Path, exit_code: int = 3) -> Path:
    """A real evaluated run: `shown` commits an HTML-bearing string, then `fail` exits `exit_code`."""
    (workspace / "fresh_flow.orc").write_text(FAILING_SOURCE, encoding="utf-8")
    (workspace / "shown.py").write_text(
        'import json, os\nprint("<svg><script>log</script></svg>")\n'
        'open(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"], "w").write(json.dumps("<b>bad</b><img src=x>"))\n',
        encoding="utf-8")
    (workspace / "fail.py").write_text(
        f'import sys\nprint("<script>boom</script>", file=sys.stderr)\nsys.exit({exit_code})\n', encoding="utf-8")
    (workspace / "fail_commands.json").write_text(json.dumps({
        name: {"stable_command": ["python", f"{name}.py"], "closure": [f"{name}.py"]} for name in ("shown", "fail")
    }), encoding="utf-8")
    before = _run_names(workspace)
    result = cli_inprocess(workspace, "run", "fresh_flow.orc", "--command-boundaries-file", "fail_commands.json")
    assert result.returncode == 1, result.stderr
    return _new_run(workspace, before)


def _step(workspace: Path, run_root: Path, suffix: str):
    record = next(run for run in RunScanner([workspace]).scan().runs if run.run_root == run_root)
    return next(step for step in RunProjector().project_detail(record).steps if step.ref.endswith(suffix))


def _app(workspace: Path) -> DashboardApp:
    return DashboardApp(RunScanner([workspace]))


def _write_state_json_symlink_escape(workspace: Path) -> tuple[Path, Path]:
    """A real evaluated run whose derived `state.json` is replaced by a symlink leaving the workspace."""
    run_root = _pure_run(workspace)
    outside = workspace.parent / f"{workspace.name}-outside"
    outside.mkdir()
    external_state = outside / "state.json"
    external_state.write_text(
        json.dumps(
            {
                "run_id": "external-run",
                "status": "completed",
                "payload": "outside-secret",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").unlink()
    (run_root / "state.json").symlink_to(external_state)
    return outside, run_root


def test_root_redirects_to_runs(tmp_path: Path):
    response = _app(tmp_path).handle("GET", "/")

    assert response.status == 302
    assert response.headers["Location"] == "/runs"


def test_runs_index_returns_html_with_security_headers_and_escaped_fields(tmp_path: Path):
    workspace = tmp_path / "ws<script>run"
    workspace.mkdir()
    run_root = _pure_run(workspace)
    before = _tree_bytes(workspace)

    response = _app(workspace).handle("GET", "/runs")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "evaluated/inputs.orc" in body
    assert "ws&lt;script&gt;run" in body
    assert "<script>run" not in body
    assert f'href="/runs/w0/{run_root.name}"' in body
    assert "file://" not in body
    assert f'href="{tmp_path}' not in body
    assert _tree_bytes(workspace) == before


def test_runs_index_orders_entries_by_most_recent_updated_at_first(tmp_path: Path):
    older = _pure_run(tmp_path)
    before = _run_names(tmp_path)
    result = _run_cli(tmp_path, str(tmp_path / "evaluated" / "inputs.orc"), "--input", "score=0.75")
    assert result.returncode == 0, result.stderr
    newer = _new_run(tmp_path, before)
    assert load_evaluated_view(newer)["updated_at"] > load_evaluated_view(older)["updated_at"]

    response = _app(tmp_path).handle("GET", "/runs")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert body.index(f'href="/runs/w0/{newer.name}"') < body.index(f'href="/runs/w0/{older.name}"')


def test_unknown_route_returns_404(tmp_path: Path):
    response = _app(tmp_path).handle("GET", "/missing")

    assert response.status == 404


def test_runs_index_filters_by_status_workflow_recency_and_search(tmp_path: Path):
    old_run = _completed_run(tmp_path)
    fresh_run = _failing_run(tmp_path)
    updated = datetime.fromisoformat(load_evaluated_view(fresh_run)["updated_at"])
    app = DashboardApp(RunScanner([tmp_path]), now=updated + timedelta(hours=1))

    response = app.handle(
        "GET",
        "/runs?status=failed&workflow=fresh&recency=2h&search=exit%20code%203",
    )

    body = response.body.decode("utf-8")
    assert fresh_run.name in body
    assert old_run.name not in body
    stale = DashboardApp(RunScanner([tmp_path]), now=updated + timedelta(hours=3)).handle("GET", "/runs?recency=2h")
    assert fresh_run.name not in stale.body.decode("utf-8")


HOSTILE_ERROR_SOURCE = '''\
(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule hostile) (export run)
  (defworkflow run () -> Int
    (command-result hostile :argv ("<script>boom" "x") :returns Int)))
'''


def _hostile_error_run(workspace: Path, monkeypatch) -> Path:
    """A real run whose failed effect's error carries hostile text: the launcher's exec error names the program."""
    program = workspace / "bin" / "<script>boom"
    program.parent.mkdir()
    program.write_bytes(b"\x00\x01 not an executable format")
    program.chmod(0o700)
    monkeypatch.setenv("PATH", str(program.parent) + os.pathsep + os.environ["PATH"])
    (workspace / "hostile.orc").write_text(HOSTILE_ERROR_SOURCE, encoding="utf-8")
    (workspace / "hostile_commands.json").write_text(
        json.dumps({"hostile": {"stable_command": ["<script>boom"], "closure": []}}), encoding="utf-8")
    before = _run_names(workspace)
    result = cli_inprocess(workspace, "run", "hostile.orc", "--command-boundaries-file", "hostile_commands.json")
    assert result.returncode == 1, result.stderr
    return _new_run(workspace, before)


def test_step_detail_route_resolves_by_name_and_escapes_payloads(tmp_path: Path, monkeypatch):
    run_root = _failing_run(tmp_path)
    hostile_root = _hostile_error_run(tmp_path, monkeypatch)
    shown, failed = _step(tmp_path, run_root, "/ shown"), _step(tmp_path, run_root, "/ fail")
    hostile = _step(tmp_path, hostile_root, "")  # the run's one effect
    assert "<script>boom" in json.dumps(hostile.error)
    before = _tree_bytes(tmp_path)
    app = _app(tmp_path)

    response = app.handle("GET", f"/runs/w0/{run_root.name}/steps/{quote(shown.name, safe='')}")
    error_page = app.handle("GET", f"/runs/w0/{hostile_root.name}/steps/{quote(hostile.name, safe='')}")
    stderr = app.handle("GET", f"/runs/w0/{run_root.name}/files/run/{failed.file_refs['stderr.txt'].route_path}")

    body = response.body.decode("utf-8")
    assert response.status == 200 and error_page.status == 200
    assert "&lt;b&gt;bad&lt;/b&gt;" in body
    assert "&lt;img src=x&gt;" in body and "<img src=x>" not in body
    error_body = error_page.body.decode("utf-8")
    assert "&lt;script&gt;boom" in error_body and "<script>boom" not in error_body
    assert "&lt;script&gt;boom&lt;/script&gt;" in stderr.body.decode("utf-8")
    assert _tree_bytes(tmp_path) == before


def test_state_preview_route_uses_capped_escaped_json_preview(tmp_path: Path):
    run_root = _scalar_run(tmp_path, "String", '"<script>x</script>"')

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/state")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "&lt;script&gt;x&lt;/script&gt;" in body
    assert "<script>x" not in body
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_file_preview_route_escapes_workspace_and_run_files(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "payload.html"
    artifact.parent.mkdir()
    artifact.write_text("<script>artifact</script>", encoding="utf-8")
    run_root = _failing_run(tmp_path)
    run_log = _step(tmp_path, run_root, "/ shown").file_refs["stdout.txt"].route_path

    workspace_response = _app(tmp_path).handle(
        "GET",
        f"/runs/w0/{run_root.name}/files/workspace/artifacts/payload.html",
    )
    run_response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/files/run/{run_log}")

    assert workspace_response.status == 200
    assert "&lt;script&gt;artifact&lt;/script&gt;" in workspace_response.body.decode("utf-8")
    assert "&lt;svg&gt;&lt;script&gt;log&lt;/script&gt;&lt;/svg&gt;" in run_response.body.decode("utf-8")
    assert workspace_response.headers["X-Content-Type-Options"] == "nosniff"
    assert run_response.headers["X-Content-Type-Options"] == "nosniff"


def test_markdown_file_preview_renders_safe_markdown_html(tmp_path: Path):
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text(
        "# Rendered Note\n\nA **strong** point with <script>bad()</script>.\n\n- first\n- second\n",
        encoding="utf-8",
    )
    run_root = _pure_run(tmp_path)

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/files/workspace/docs/note.md")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert '<article class="markdown-preview">' in body
    assert "<h1>Rendered Note</h1>" in body
    assert "<strong>strong</strong>" in body
    assert "<li>first</li>" in body
    assert "<script>bad()</script>" not in body
    assert "&lt;script&gt;bad()&lt;/script&gt;" in body
    assert "Download raw" in body


def test_file_raw_route_forces_attachment_text_plain(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "payload.svg"
    artifact.parent.mkdir()
    artifact.write_text("<svg><script>x</script></svg>", encoding="utf-8")
    run_root = _pure_run(tmp_path)

    response = _app(tmp_path).handle(
        "GET",
        f"/runs/w0/{run_root.name}/files/workspace/artifacts/payload.svg?raw=1",
    )

    assert response.status == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_file_route_rejects_traversal_and_displays_missing_state(tmp_path: Path):
    run_root = _pure_run(tmp_path)

    traversal = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/files/workspace/../secret.txt")
    missing = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/files/workspace/missing.txt")

    assert traversal.status == 400
    assert missing.status == 200
    assert "missing" in missing.body.decode("utf-8")


def test_detail_links_artifacts_through_dashboard_file_routes(tmp_path: Path):
    run_root = _completed_run(tmp_path)
    stdout = _step(tmp_path, run_root, "/ prefix").file_refs["stdout.txt"]

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}")

    body = response.body.decode("utf-8")
    assert f'href="/runs/w0/{run_root.name}/files/run/{stdout.route_path}"' in body
    assert str(stdout.absolute_path) not in body
    assert f'href="{tmp_path}' not in body


def test_index_and_detail_support_safe_meta_refresh(tmp_path: Path):
    run_root = _pure_run(tmp_path)
    app = _app(tmp_path)

    index = app.handle("GET", "/runs?refresh=5")
    detail = app.handle("GET", f"/runs/w0/{run_root.name}?refresh=5")

    assert '<meta http-equiv="refresh" content="5">' in index.body.decode("utf-8")
    assert '<meta http-equiv="refresh" content="5">' in detail.body.decode("utf-8")
    assert index.headers["Content-Security-Policy"] == detail.headers["Content-Security-Policy"]


def test_invalid_refresh_value_is_ignored_and_escaped(tmp_path: Path):
    _pure_run(tmp_path)

    response = _app(tmp_path).handle("GET", "/runs?refresh=%3Cscript%3E")

    body = response.body.decode("utf-8")
    assert "http-equiv=\"refresh\"" not in body
    assert "<script>" not in body


def test_file_preview_route_displays_truncated_large_files(tmp_path: Path):
    large = tmp_path / "artifacts" / "large.log"
    large.parent.mkdir()
    large.write_text("a" * (70 * 1024), encoding="utf-8")
    run_root = _pure_run(tmp_path)

    response = _app(tmp_path).handle(
        "GET",
        f"/runs/w0/{run_root.name}/files/workspace/artifacts/large.log",
    )

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "truncated" in body.lower()


def test_rejected_state_json_symlink_detail_does_not_render_outside_commands(
    tmp_path: Path,
):
    outside, run_root = _write_state_json_symlink_escape(tmp_path)
    before = _tree_bytes(tmp_path)

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}")

    body = response.body.decode("utf-8")
    assert response.status == 200
    outputs = re.search(r"<h2>Outputs</h2>\s*<pre>(.*?)</pre>", body, re.S).group(1)
    assert json.loads(html.unescape(outputs)) == {"accepted": True, "score": 0.75}
    assert f"orchestrate report --run-id {run_root.name}" in body
    assert "external-run" not in body
    assert str(outside) not in body
    assert "outside-secret" not in body
    assert _tree_bytes(tmp_path) == before


def test_rejected_state_json_symlink_state_preview_is_not_served(tmp_path: Path):
    outside, run_root = _write_state_json_symlink_escape(tmp_path)
    before = _tree_bytes(tmp_path)

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/state")

    body = response.body.decode("utf-8")
    assert response.status == 400
    assert "Unsafe state path" in body
    assert "external-run" not in body
    assert "outside-secret" not in body
    assert str(outside) not in body
    assert _tree_bytes(tmp_path) == before


def test_rejected_state_json_symlink_file_route_uses_scanned_run_root(
    tmp_path: Path,
):
    outside, run_root = _write_state_json_symlink_escape(tmp_path)

    response = _app(tmp_path).handle("GET", f"/runs/w0/{run_root.name}/files/run/foo")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "missing" in body
    assert "outside-secret" not in body
    assert str(outside) not in body


@pytest.mark.parametrize("authority", ["run.json", "closed_program.json", "memo.jsonl"])
def test_symlinked_authority_file_leaving_workspace_is_unreadable_and_not_served(tmp_path: Path, authority: str):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_root = _pure_run(workspace)
    outside = tmp_path / f"outside-{authority}"
    outside.write_bytes((run_root / authority).read_bytes() + b"\nOUTSIDE-AUTHORITY-MARKER\n")
    (run_root / authority).unlink()
    (run_root / authority).symlink_to(outside)
    before = _tree_bytes(tmp_path)
    app = _app(workspace)

    index = app.handle("GET", "/runs").body.decode("utf-8")
    page = app.handle("GET", f"/runs/w0/{run_root.name}")
    preview = app.handle("GET", f"/runs/w0/{run_root.name}/files/run/{authority}")
    raw = app.handle("GET", f"/runs/w0/{run_root.name}/files/run/{authority}?raw=1")

    row = next(line for line in index.splitlines() if f'href="/runs/w0/{run_root.name}"' in line)
    assert "<td>unreadable</td>" in row
    body = page.body.decode("utf-8")
    assert page.status == 200 and "memo_inconsistent" in body and "0.75" not in body
    assert preview.status == raw.status == 400
    for response_body in (index, body, preview.body.decode("utf-8"), raw.body.decode("utf-8")):
        assert "OUTSIDE-AUTHORITY-MARKER" not in response_body and str(outside) not in response_body
    assert _tree_bytes(tmp_path) == before


def test_removed_routes_return_404(tmp_path: Path):
    run_root = _pure_run(tmp_path)
    (run_root / "summaries").mkdir()
    (run_root / "summaries" / "index.json").write_text('{"schema": "orchestrator_summary_index/v1", "entries": []}')
    retired = tmp_path / ".orchestrate" / "runs" / "retired-run"
    retired.mkdir()
    (retired / "state.json").write_text('{"run_id": "retired-run", "status": "running"}')
    before = _tree_bytes(tmp_path)
    app = _app(tmp_path)

    for run_dir_id in (run_root.name, retired.name):
        for route in ("summaries", "summaries/live.json", "tmux"):
            assert app.handle("GET", f"/runs/w0/{run_dir_id}/{route}").status == 404
    assert _tree_bytes(tmp_path) == before


def _retired_state(run_dir: Path, outside: Path, kind: str) -> None:
    marker = '{"run_id": "RETIRED-MARKER", "status": "completed", "workflow_file": "RETIRED-MARKER.yaml"}'
    state = run_dir / "state.json"
    if kind == "regular":
        state.write_text(marker)
    elif kind == "malformed":
        state.write_text("RETIRED-MARKER {not json")
    elif kind == "symlink-outside":
        outside.write_text(marker)
        state.symlink_to(outside)
    else:
        state.symlink_to(outside / "missing-RETIRED-MARKER.json")


@pytest.mark.parametrize("kind", ["regular", "malformed", "symlink-outside", "broken-symlink"])
def test_dashboard_lists_retired_run_as_one_line_refusal(tmp_path: Path, kind: str):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_root = _pure_run(workspace)
    retired = workspace / ".orchestrate" / "runs" / "20250101T000000Z-retired"
    retired.mkdir()
    _retired_state(retired, tmp_path / "outside-state.json", kind)
    before = _tree_bytes(tmp_path)
    app = _app(workspace)

    index = app.handle("GET", "/runs").body.decode("utf-8")
    page = app.handle("GET", f"/runs/w0/{retired.name}")
    below = [app.handle("GET", f"/runs/w0/{retired.name}/{route}")
             for route in ("state", "steps/x", "files/run/state.json", "files/run/state.json?raw=1")]

    refusal = f"workflow_execution_profile_retired: run {retired.name} was written by the retired runtime"
    assert f'href="/runs/w0/{run_root.name}"' in index and f'href="/runs/w0/{retired.name}"' in index
    row = next(line for line in index.splitlines() if f'href="/runs/w0/{retired.name}"' in line)
    assert "<td>retired</td>" in row and refusal in row
    assert page.status == 200 and refusal in page.body.decode("utf-8")
    assert "git tag archive/retired-run-readers-2026-11-11" in page.body.decode("utf-8")
    assert [response.status for response in below] == [404] * 4
    assert all(refusal in response.body.decode("utf-8") for response in below)
    for body in [index, page.body.decode("utf-8"), *(response.body.decode("utf-8") for response in below)]:
        assert "RETIRED-MARKER" not in body
    assert _tree_bytes(tmp_path) == before


def _http_get(port: int, path: str, host_header):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=30)
    try:
        connection.putrequest("GET", path, skip_host=True)
        if host_header is not None:
            connection.putheader("Host", host_header)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, response.read()
    finally:
        connection.close()


def test_real_http_server_refuses_foreign_host_headers_before_any_route(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    run_root = _pure_run(workspace)
    before = _tree_bytes(workspace)
    server = make_dashboard_server(scanner=RunScanner([workspace]), host="127.0.0.1", port=0)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    raw_path = f"/runs/w0/{quote(run_root.name)}/files/run/run.json?raw=1"
    try:
        accepted = {host: _http_get(port, raw_path, host)
                    for host in (f"127.0.0.1:{port}", f"localhost:{port}", f"LOCALHOST:{port}", f"[::1]:{port}")}
        refused = {host: _http_get(port, raw_path, host)
                   for host in (f"evil.example:{port}", "evil.example", f"127.0.0.1:{port + 1}", "127.0.0.1",
                                f"[::2]:{port}", None)}
    finally:
        server.shutdown()
        server.server_close()
    run_json = (run_root / "run.json").read_bytes()
    assert {host: status for host, (status, _) in accepted.items()} == dict.fromkeys(accepted, 200)
    assert all(body == run_json for _, body in accepted.values())
    assert {host: status for host, (status, _) in refused.items()} == dict.fromkeys(refused, 421)
    assert not any(run_json in body or run_root.name.encode() in body for _, body in refused.values())
    assert _tree_bytes(workspace) == before


def test_run_directory_with_non_utf8_name_is_skipped_with_a_warning(tmp_path: Path):
    run_root = _pure_run(tmp_path)
    bad = os.path.join(os.fsencode(run_root.parent), b"bad\xff")
    os.mkdir(bad)
    with open(os.path.join(bad, b"state.json"), "wb") as handle:
        handle.write(b'{"status": "running"}')
    before = _tree_bytes(tmp_path)

    response = _app(tmp_path).handle("GET", "/runs")

    body = response.body.decode()
    assert response.status == 200
    assert f">{run_root.name}</a>" in body
    assert "bad\\xff" in body and "not UTF-8" in body
    assert _tree_bytes(tmp_path) == before
