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


def _write_state_json_symlink_escape(workspace: Path) -> Path:
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
    run_dir = workspace / ".orchestrate" / "runs" / "run1"
    run_dir.mkdir(parents=True)
    (run_dir / "state.json").symlink_to(external_state)
    return outside


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


def test_runs_index_renders_cursor_freshness_and_availability_fields(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    (run_root / "logs").mkdir(parents=True)
    (run_root / "provider_sessions").mkdir()
    (run_root / "logs" / "Step.prompt.txt").write_text("prompt", encoding="utf-8")
    (run_root / "logs" / "Step.stdout").write_text("stdout", encoding="utf-8")
    (run_root / "logs" / "Step.stderr").write_text("stderr", encoding="utf-8")
    (run_root / "provider_sessions" / "root.step__v1.json").write_text("{}", encoding="utf-8")
    (run_root / "state.json.step_Step.bak").write_text("{}", encoding="utf-8")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "started_at": "2026-04-13T12:00:00+00:00",
                "updated_at": "2026-04-13T12:02:00+00:00",
                "current_step": {
                    "name": "Step",
                    "step_id": "root.step",
                    "started_at": "2026-04-13T12:01:00+00:00",
                    "last_heartbeat_at": "2026-04-13T12:01:30+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    response = DashboardApp(
        RunScanner([tmp_path]),
        now="2026-04-13T12:02:30+00:00",
    ).handle("GET", "/runs")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Cursor" in body
    assert "Step" in body
    assert "Started" in body
    assert "Elapsed" in body
    assert "2m 30s" in body
    assert "Current step start" in body
    assert "2026-04-13T12:01:00+00:00" in body
    assert "State mtime" in body
    assert "Read time" in body
    assert "Heartbeat" in body
    assert "1m 0s" in body
    assert "Availability" in body
    assert "prompt_audits" in body
    assert "provider_sessions" in body
    assert "state_backups" in body


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


def test_run_detail_links_run_local_observability_files(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    provider_sessions = run_root / "provider_sessions"
    logs.mkdir(parents=True)
    provider_sessions.mkdir()
    (logs / "Step.prompt.txt").write_text("masked prompt", encoding="utf-8")
    (logs / "Step.stdout").write_text("stdout", encoding="utf-8")
    (logs / "Step.stderr").write_text("stderr", encoding="utf-8")
    (provider_sessions / "root.step__v1.json").write_text(
        '{"step_status":"completed"}',
        encoding="utf-8",
    )
    (provider_sessions / "root.step__v1.transport.log").write_text(
        "transport",
        encoding="utf-8",
    )
    (run_root / "state.json.step_Step.bak").write_text("{}", encoding="utf-8")
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "steps": {
                    "Step": {
                        "status": "completed",
                        "step_id": "root.step",
                        "visit_count": 1,
                        "debug": {
                            "provider_session": {
                                "metadata_path": str(provider_sessions / "root.step__v1.json"),
                                "transport_spool_path": str(
                                    provider_sessions / "root.step__v1.transport.log"
                                ),
                                "publication_state": "published",
                            }
                        },
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Prompt Audits" in body
    assert "masked debug prompt file" in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.prompt.txt"' in body
    assert "Execution Logs" in body
    assert "less-masked execution log" in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.stdout"' in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.stderr"' in body
    assert "Provider Sessions" in body
    assert "provider transport log" in body
    assert 'href="/runs/w0/run1/files/run/provider_sessions/root.step__v1.json"' in body
    assert (
        'href="/runs/w0/run1/files/run/provider_sessions/root.step__v1.transport.log"'
        in body
    )
    assert "State Backups" in body
    assert 'href="/runs/w0/run1/files/run/state.json.step_Step.bak"' in body


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


def test_step_detail_shows_visit_duration_outcome_and_observability_refs(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    provider_sessions = run_root / "provider_sessions"
    logs.mkdir(parents=True)
    provider_sessions.mkdir()
    (logs / "Step.prompt.txt").write_text("prompt", encoding="utf-8")
    (logs / "Step.stdout").write_text("stdout", encoding="utf-8")
    (logs / "Step.stderr").write_text("stderr", encoding="utf-8")
    (provider_sessions / "root.step__v3.json").write_text(
        '{"publication_state":"published"}',
        encoding="utf-8",
    )
    (provider_sessions / "root.step__v3.transport.log").write_text(
        "transport",
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "steps": {
                    "Step": {
                        "status": "completed",
                        "step_id": "root.step",
                        "duration_ms": 123,
                        "visit_count": 3,
                        "outcome": {
                            "status": "completed",
                            "phase": "execution",
                            "class": "completed",
                        },
                        "debug": {
                            "provider_session": {
                                "metadata_path": str(provider_sessions / "root.step__v3.json"),
                                "transport_spool_path": str(
                                    provider_sessions / "root.step__v3.transport.log"
                                ),
                                "publication_state": "published",
                            }
                        },
                    }
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/steps/Step")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Visit count: 3" in body
    assert "Duration: 123 ms" in body
    assert "Outcome" in body
    assert "published" in body
    assert "Provider Session" in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.prompt.txt"' in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.stdout"' in body
    assert 'href="/runs/w0/run1/files/run/logs/Step.stderr"' in body
    assert 'href="/runs/w0/run1/files/run/provider_sessions/root.step__v3.json"' in body
    assert (
        'href="/runs/w0/run1/files/run/provider_sessions/root.step__v3.transport.log"'
        in body
    )


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


def test_runs_index_uses_request_time_for_freshness(tmp_path: Path):
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "updated_at": "2026-04-13T11:59:00+00:00",
            "current_step": {
                "name": "Step",
                "started_at": "2026-04-13T11:56:00+00:00",
                "last_heartbeat_at": "2026-04-13T11:56:00+00:00",
            },
        },
    )
    request_times = iter(
        [
            "2026-04-13T12:00:00+00:00",
            "2026-04-13T12:02:00+00:00",
        ]
    )
    app = DashboardApp(RunScanner([tmp_path]), now=lambda: next(request_times))

    first = app.handle("GET", "/runs").body.decode("utf-8")
    second = app.handle("GET", "/runs?refresh=5").body.decode("utf-8")

    assert "running" in first
    assert "stale_running_step_heartbeat_timeout" not in first
    assert "stale_running_step_heartbeat_timeout" in second
    assert "6m 0s" in second


def test_run_detail_renders_call_frame_local_artifact_lineage(tmp_path: Path):
    artifact = tmp_path / "artifacts" / "frame.txt"
    artifact.parent.mkdir()
    artifact.write_text("ok", encoding="utf-8")
    _write_run(
        tmp_path,
        "run1",
        {
            "run_id": "run1",
            "status": "running",
            "current_step": {"name": "Call", "step_id": "root.call"},
            "call_frames": {
                "root.call::visit::1": {
                    "step_id": "root.call",
                    "state": {
                        "artifact_versions": {
                            "frame_result": [
                                {
                                    "version": 1,
                                    "value": "artifacts/frame.txt",
                                    "producer": "Nested",
                                }
                            ]
                        },
                        "artifact_consumes": {"Nested": {"frame_result": 1}},
                    },
                }
            },
        },
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "call_frame_artifact_versions" in body
    assert "root.call::visit::1" in body
    assert "frame_result" in body
    assert "artifacts/frame.txt" in body
    assert "call_frame_artifact_consumes" in body


def test_file_preview_route_displays_truncated_large_files(tmp_path: Path):
    large = tmp_path / "artifacts" / "large.log"
    large.parent.mkdir()
    large.write_text("a" * (70 * 1024), encoding="utf-8")
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})

    response = _app(tmp_path).handle(
        "GET",
        "/runs/w0/run1/files/workspace/artifacts/large.log",
    )

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "truncated" in body.lower()


def test_rejected_state_json_symlink_detail_does_not_render_outside_commands(
    tmp_path: Path,
):
    outside = _write_state_json_symlink_escape(tmp_path)

    response = _app(tmp_path).handle("GET", "/runs/w0/run1")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "state.json resolves outside workspace" in body
    assert "Commands unavailable" in body
    assert "orchestrate report" not in body
    assert "orchestrate resume" not in body
    assert str(outside) not in body
    assert "outside-secret" not in body


def test_rejected_state_json_symlink_state_preview_is_not_served(tmp_path: Path):
    outside = _write_state_json_symlink_escape(tmp_path)

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/state")

    body = response.body.decode("utf-8")
    assert response.status == 400
    assert "Unsafe state path" in body
    assert "external-run" not in body
    assert "outside-secret" not in body
    assert str(outside) not in body


def test_rejected_state_json_symlink_file_route_uses_scanned_run_root(
    tmp_path: Path,
):
    outside = _write_state_json_symlink_escape(tmp_path)

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/files/run/foo")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "missing" in body
    assert "outside-secret" not in body
    assert str(outside) not in body
