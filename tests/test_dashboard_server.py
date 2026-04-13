"""Tests for dashboard server routes."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from orchestrator.dashboard.scanner import RunScanner
from orchestrator.dashboard.server import DashboardApp


def _write_yaml(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return path


def _write_run(workspace: Path, run_dir_id: str, state: dict) -> None:
    run_dir = workspace / ".orchestrate" / "runs" / run_dir_id
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def _app(workspace: Path) -> DashboardApp:
    return DashboardApp(RunScanner([workspace]))


def test_root_redirects_to_runs(tmp_path: Path):
    response = _app(tmp_path).handle("GET", "/")

    assert response.status == 302
    assert response.headers["Location"] == "/runs"


def test_runs_index_returns_html_with_security_headers_and_escaped_fields(tmp_path: Path):
    workflow = _write_yaml(
        tmp_path / "workflows" / "flow.yaml",
        {
            "version": "1.3",
            "name": "<script>flow</script>",
            "steps": [{"name": "StepA", "command": ["bash", "-lc", "true"]}],
        },
    )
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "<script>run</script>",
            "status": "completed",
            "workflow_file": str(workflow.relative_to(tmp_path)),
        },
    )

    response = _app(tmp_path).handle("GET", "/runs")

    assert response.status == 200
    body = response.body.decode("utf-8")
    assert response.headers["Content-Type"] == "text/html; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'none'" in response.headers["Content-Security-Policy"]
    assert "&lt;script&gt;flow&lt;/script&gt;" in body
    assert "&lt;script&gt;run&lt;/script&gt;" in body
    assert 'href="/runs/w0/run1"' in body
    assert "file://" not in body
    assert f'href="{tmp_path}' not in body


def test_unknown_route_returns_404(tmp_path: Path):
    response = _app(tmp_path).handle("GET", "/missing")

    assert response.status == 404


def test_runs_index_filters_by_status_workflow_recency_and_search(tmp_path: Path):
    fresh_workflow = _write_yaml(
        tmp_path / "workflows" / "fresh.yaml",
        {"version": "1.3", "name": "fresh-flow", "steps": []},
    )
    old_workflow = _write_yaml(
        tmp_path / "workflows" / "old.yaml",
        {"version": "1.3", "name": "old-flow", "steps": []},
    )
    _write_run(
        tmp_path,
        "fresh-run",
        {
            "run_id": "fresh-run",
            "status": "failed",
            "workflow_file": str(fresh_workflow.relative_to(tmp_path)),
            "updated_at": "2026-04-13T12:00:00+00:00",
            "error": {"message": "needle failure"},
        },
    )
    _write_run(
        tmp_path,
        "old-run",
        {
            "run_id": "old-run",
            "status": "completed",
            "workflow_file": str(old_workflow.relative_to(tmp_path)),
            "updated_at": "2026-04-01T12:00:00+00:00",
        },
    )
    app = DashboardApp(RunScanner([tmp_path]), now="2026-04-13T13:00:00+00:00")

    response = app.handle(
        "GET",
        "/runs?status=failed&workflow=fresh&recency=2h&search=needle",
    )

    body = response.body.decode("utf-8")
    assert "fresh-run" in body
    assert "old-run" not in body


def test_run_detail_route_shows_cursor_commands_lineage_and_warnings(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "result.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok", encoding="utf-8")
    _write_run(
        tmp_path,
        "dir-run",
        {
            "run_id": "state-run",
            "status": "running",
            "workflow_file": "missing.yaml",
            "current_step": {"name": "ReviewLoop", "step_id": "root.review_loop"},
            "bound_inputs": {"goal": "ship"},
            "workflow_outputs": {"report": "artifacts/result.txt"},
            "repeat_until": {"ReviewLoop": {"current_iteration": 1}},
            "finalization": {"status": "running", "workflow_outputs_status": "pending"},
            "steps": {
                "ReviewLoop": {
                    "status": "running",
                    "step_id": "root.review_loop",
                    "artifacts": {"result": "artifacts/result.txt"},
                }
            },
            "artifact_versions": {
                "result": [{"version": 1, "value": "artifacts/result.txt", "producer": "ReviewLoop"}]
            },
        },
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/dir-run")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "state.run_id mismatch" in body
    assert "orchestrate report --run-id dir-run" in body
    assert "orchestrate resume dir-run" not in body
    assert "ReviewLoop" in body
    assert "repeat_until" in body
    assert "workflow_outputs_status" in body
    assert "goal" in body
    assert "artifact_versions" in body


def test_step_detail_route_resolves_by_name_and_escapes_payloads(tmp_path: Path):
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "failed",
            "steps": {
                "StepA": {
                    "status": "failed",
                    "step_id": "root.step_a",
                    "output": "<b>bad</b>",
                    "error": {"message": "<script>boom</script>"},
                    "debug": {"payload": "<img src=x>"},
                }
            },
        },
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/steps/StepA")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "&lt;b&gt;bad&lt;/b&gt;" in body
    assert "&lt;script&gt;boom&lt;/script&gt;" in body
    assert "&lt;img src=x&gt;" in body


def test_state_preview_route_uses_capped_escaped_json_preview(tmp_path: Path):
    _write_run(
        tmp_path,
        "run1",
        {"run_id": "run1", "status": "completed", "context": {"html": "<script>x</script>"}},
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/state")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "&lt;script&gt;x&lt;/script&gt;" in body
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_file_preview_route_escapes_workspace_and_run_files(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "payload.html"
    run_log = tmp_path / ".orchestrate" / "runs" / "run1" / "logs" / "Step.stderr"
    artifact.parent.mkdir()
    run_log.parent.mkdir(parents=True)
    artifact.write_text("<script>artifact</script>", encoding="utf-8")
    run_log.write_text("<svg><script>log</script></svg>", encoding="utf-8")
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "completed",
            "steps": {"Step": {"status": "completed", "artifacts": {"payload": "artifacts/payload.html"}}},
        },
    )

    workspace_response = _app(tmp_path).handle(
        "GET",
        "/runs/w0/run1/files/workspace/artifacts/payload.html",
    )
    run_response = _app(tmp_path).handle("GET", "/runs/w0/run1/files/run/logs/Step.stderr")

    assert workspace_response.status == 200
    assert "&lt;script&gt;artifact&lt;/script&gt;" in workspace_response.body.decode("utf-8")
    assert "&lt;svg&gt;&lt;script&gt;log&lt;/script&gt;&lt;/svg&gt;" in run_response.body.decode("utf-8")
    assert workspace_response.headers["X-Content-Type-Options"] == "nosniff"


def test_file_raw_route_forces_attachment_text_plain(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "payload.svg"
    artifact.parent.mkdir()
    artifact.write_text("<svg><script>x</script></svg>", encoding="utf-8")
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})

    response = _app(tmp_path).handle(
        "GET",
        "/runs/w0/run1/files/workspace/artifacts/payload.svg?raw=1",
    )

    assert response.status == 200
    assert response.headers["Content-Disposition"].startswith("attachment;")
    assert response.headers["Content-Type"] == "text/plain; charset=utf-8"
    assert response.headers["X-Content-Type-Options"] == "nosniff"


def test_file_route_rejects_traversal_and_displays_missing_state(tmp_path: Path):
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})

    traversal = _app(tmp_path).handle("GET", "/runs/w0/run1/files/workspace/../secret.txt")
    missing = _app(tmp_path).handle("GET", "/runs/w0/run1/files/workspace/missing.txt")

    assert traversal.status == 400
    assert missing.status == 200
    assert "missing" in missing.body.decode("utf-8")


def test_detail_links_artifacts_through_dashboard_file_routes(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "payload.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok", encoding="utf-8")
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "completed",
            "steps": {"Step": {"status": "completed", "artifacts": {"payload": "artifacts/payload.txt"}}},
        },
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1")

    body = response.body.decode("utf-8")
    assert 'href="/runs/w0/run1/files/workspace/artifacts/payload.txt"' in body
    assert str(artifact) not in body


def test_index_and_detail_support_safe_meta_refresh(tmp_path: Path):
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})
    app = _app(tmp_path)

    index = app.handle("GET", "/runs?refresh=5")
    detail = app.handle("GET", "/runs/w0/run1?refresh=5")

    assert '<meta http-equiv="refresh" content="5">' in index.body.decode("utf-8")
    assert '<meta http-equiv="refresh" content="5">' in detail.body.decode("utf-8")
    assert index.headers["Content-Security-Policy"] == detail.headers["Content-Security-Policy"]


def test_invalid_refresh_value_is_ignored_and_escaped(tmp_path: Path):
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})

    response = _app(tmp_path).handle("GET", "/runs?refresh=%3Cscript%3E")

    body = response.body.decode("utf-8")
    assert "http-equiv=\"refresh\"" not in body
    assert "<script>" not in body
