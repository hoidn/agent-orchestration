"""Tests for dashboard server routes."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
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


def test_runs_index_orders_entries_by_most_recent_updated_at_first(tmp_path: Path):
    _write_run(
        tmp_path,
        "aaa-old",
        {
            "run_id": "aaa-old",
            "status": "completed",
            "updated_at": "2026-04-13T10:00:00+00:00",
        },
    )
    _write_run(
        tmp_path,
        "zzz-new",
        {
            "run_id": "zzz-new",
            "status": "completed",
            "updated_at": "2026-04-13T12:00:00+00:00",
        },
    )

    response = _app(tmp_path).handle("GET", "/runs")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert body.index('href="/runs/w0/zzz-new"') < body.index('href="/runs/w0/aaa-old"')


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


def test_summary_provider_flow_orders_design_gap_architecture_before_plan(tmp_path: Path):
    app = _app(tmp_path)
    review_plan_loop = {
        "label": "PlanReviewLoop",
        "kind": "repeat_until max=12",
        "provider": False,
        "children": [
            {"label": "ReviewPlan", "kind": "provider", "provider": True, "children": []},
            {
                "label": "RoutePlanDecision",
                "kind": "match",
                "provider": False,
                "children": [
                    {"label": "case APPROVE", "kind": "case", "provider": False, "children": []},
                    {
                        "label": "case REVISE",
                        "kind": "case",
                        "provider": False,
                        "children": [
                            {"label": "RevisePlan", "kind": "provider", "provider": True, "children": []}
                        ],
                    },
                ],
            },
        ],
    }
    architecture_loop = {
        "label": "ArchitectureReviewLoop",
        "kind": "repeat_until max=8",
        "provider": False,
        "children": [
            {
                "label": "ReviewDesignGapArchitecture",
                "kind": "provider",
                "provider": True,
                "children": [],
            },
            {
                "label": "RouteArchitectureDecision",
                "kind": "match",
                "provider": False,
                "children": [
                    {"label": "case APPROVE", "kind": "case", "provider": False, "children": []},
                    {
                        "label": "case REVISE",
                        "kind": "case",
                        "provider": False,
                        "children": [
                            {
                                "label": "ReviseDesignGapArchitecture",
                                "kind": "provider",
                                "provider": True,
                                "children": [],
                            }
                        ],
                    },
                ],
            },
        ],
    }
    nodes = [
        {
            "label": "DrainLispFrontendWork",
            "kind": "repeat_until max=60",
            "provider": False,
            "children": [
                {"label": "SelectNextWork", "kind": "provider", "provider": True, "children": []},
                {
                    "label": "RouteSelection",
                    "kind": "match",
                    "provider": False,
                    "children": [
                        {
                            "label": "case SELECT_BACKLOG_ITEM",
                            "kind": "case",
                            "provider": False,
                            "children": [review_plan_loop],
                        },
                        {
                            "label": "case DRAFT_DESIGN_GAP",
                            "kind": "case",
                            "provider": False,
                            "children": [
                                {
                                    "label": "DraftDesignGapArchitecture",
                                    "kind": "provider",
                                    "provider": True,
                                    "children": [],
                                },
                                architecture_loop,
                                review_plan_loop,
                            ],
                        },
                    ],
                },
            ],
        }
    ]

    html = app._provider_flow_mermaid_html(nodes)
    normalized_html = html.replace("<wbr>", "")

    assert normalized_html.index("SelectNextWork") < normalized_html.index("DraftDesignGapArchitecture")
    assert normalized_html.index("ArchitectureReviewLoop") < normalized_html.index("PlanReviewLoop")


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


def test_run_detail_links_summary_hub_when_index_exists(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Summary Hub" in body
    assert 'href="/runs/w0/run1/summaries"' in body
    assert 'href="/runs/w0/run1/files/run/summaries/index.json"' in body


def test_summary_hub_route_renders_entries_and_escaped_rollup(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    frame_root = "call_frames/root.loop#0/frame1"
    frame_summaries = run_root / frame_root / "summaries"
    summaries.mkdir(parents=True)
    frame_summaries.mkdir(parents=True)
    (frame_summaries / "SelectNextWork.provider.summary.md").write_text(
        "# Summary\n<script>bad</script>\n",
        encoding="utf-8",
    )
    (frame_summaries / "SelectNextWork.provider.snapshot.json").write_text(
        '{"step":{"name":"SelectNextWork"}}',
        encoding="utf-8",
    )
    (summaries / "run-summary.md").write_text(
        (
            "# Rollup\n\n"
            "## Generated Summaries\n\n"
            "- SelectNextWork (provider): completed - "
            "[summary](../call_frames/root.loop#0/frame1/summaries/SelectNextWork.provider.summary.md)\n\n"
            "<script>rollup</script>\n"
        ),
        encoding="utf-8",
    )
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "SelectNextWork",
                        "kind": "provider",
                        "profile": "phase-performance",
                        "status": "completed",
                        "duration_ms": 1234,
                        "frame_root": frame_root,
                        "summary_path": f"{frame_root}/summaries/SelectNextWork.provider.summary.md",
                        "snapshot_path": f"{frame_root}/summaries/SelectNextWork.provider.snapshot.json",
                        "error_path": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "Summary Hub" in body
    assert "SelectNextWork" in body
    assert "provider" in body
    assert "phase-performance" in body
    assert "completed" in body
    assert "1234 ms" in body
    assert (
        'href="/runs/w0/run1/files/run/call_frames/root.loop%230/frame1/summaries/SelectNextWork.provider.summary.md"'
        in body
    )
    assert (
        'href="/runs/w0/run1/files/run/call_frames/root.loop%230/frame1/summaries/SelectNextWork.provider.snapshot.json"'
        in body
    )
    assert '<article class="markdown-preview run-summary-preview">' in body
    assert "<h1>Rollup</h1>" in body
    assert "<h2>Generated Summaries</h2>" in body
    assert "[summary](" not in body
    assert (
        '<li>SelectNextWork (provider): completed - '
        '<a href="/runs/w0/run1/files/run/call_frames/root.loop%230/frame1/summaries/'
        'SelectNextWork.provider.summary.md">summary</a></li>'
        in body
    )
    assert (
        'href="/runs/w0/run1/files/run/call_frames/root.loop%230/frame1/summaries/SelectNextWork.provider.summary.md"'
        in body
    )
    assert "&lt;script&gt;rollup&lt;/script&gt;" in body
    assert "<script>rollup</script>" not in body
    assert str(run_root) not in body


def test_summary_hub_renders_provider_visit_stats(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    first = run_root / "call_frames" / "root.loop#0.review__visit__1" / "summaries"
    second = run_root / "call_frames" / "root.loop#1.review__visit__1" / "summaries"
    third = run_root / "call_frames" / "root.loop#1.fix__visit__1" / "summaries"
    for directory in (summaries, first, second, third):
        directory.mkdir(parents=True)
    (first / "ReviewImplementation.provider.summary.md").write_text("first", encoding="utf-8")
    (second / "ReviewImplementation.provider.error.json").write_text("{}", encoding="utf-8")
    (third / "FixImplementation.provider.summary.md").write_text("fix", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ReviewImplementation",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.loop#0.review__visit__1",
                        "summary_path": (
                            "call_frames/root.loop#0.review__visit__1/"
                            "summaries/ReviewImplementation.provider.summary.md"
                        ),
                    },
                    {
                        "step_name": "ReviewImplementation",
                        "kind": "provider",
                        "status": "error",
                        "frame_root": "call_frames/root.loop#1.review__visit__1",
                        "error_path": (
                            "call_frames/root.loop#1.review__visit__1/"
                            "summaries/ReviewImplementation.provider.error.json"
                        ),
                    },
                    {
                        "step_name": "FixImplementation",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.loop#1.fix__visit__1",
                        "summary_path": (
                            "call_frames/root.loop#1.fix__visit__1/"
                            "summaries/FixImplementation.provider.summary.md"
                        ),
                    },
                    {
                        "step_name": "ImplementationReviewLoop",
                        "kind": "phase",
                        "status": "completed",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Provider Visit Stats" in body
    assert "ReviewImplementation" in body
    assert "2 visits" in body
    assert "1 completed" in body
    assert "1 error" in body
    assert "FixImplementation" in body
    assert "1 visit" in body
    assert "ImplementationReviewLoop</a>" not in body
    assert 'href="/runs/w0/run1/files/run/call_frames/root.loop%230.review__visit__1/summaries/ReviewImplementation.provider.summary.md"' in body
    assert 'href="/runs/w0/run1/files/run/call_frames/root.loop%231.review__visit__1/summaries/ReviewImplementation.provider.error.json"' in body


def test_summary_hub_links_tmux_session_when_monitor_metadata_exists(
    tmp_path: Path,
    monkeypatch,
):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "monitor_process.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator-monitor-process/v1",
                "pid": 222,
                "started_at": "2026-04-13T12:00:00+00:00",
                "tmux": "/tmp/test-dashboard.sock,999,0",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "running"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        DashboardApp,
        "_resolve_tmux_target",
        lambda self, socket, pid: "lisp-run:0.0",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert 'id="tmux-session"' in body
    assert "lisp-run:0.0" in body
    assert "tmux -S /tmp/test-dashboard.sock attach -t lisp-run:0.0" in body
    assert 'href="/runs/w0/run1/tmux"' in body
    assert "tmux://attach" not in body


def test_tmux_viewer_renders_captured_pane_from_monitor_metadata(
    tmp_path: Path,
    monkeypatch,
):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    run_root.mkdir(parents=True)
    (run_root / "monitor_process.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator-monitor-process/v1",
                "pid": 222,
                "started_at": "2026-04-13T12:00:00+00:00",
                "tmux": "/tmp/test-dashboard.sock,999,0",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "running"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        DashboardApp,
        "_resolve_tmux_target",
        lambda self, socket, pid: "lisp-run:0.0",
    )
    monkeypatch.setattr(
        DashboardApp,
        "_capture_tmux_pane",
        lambda self, socket, target, lines=240: "agent output\n<script>bad</script>\n",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/tmux")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Tmux Pane" in body
    assert "lisp-run:0.0" in body
    assert "agent output" in body
    assert "&lt;script&gt;bad&lt;/script&gt;" in body
    assert "<script>bad</script>" not in body


def test_summary_hub_renders_authored_workflow_structure(tmp_path: Path):
    prompt = tmp_path / "workflows" / "prompts" / "select.md"
    context = tmp_path / "workflows" / "prompts" / "context.md"
    input_file = tmp_path / "docs" / "operator-input.md"
    for path, body in (
        (prompt, "select prompt"),
        (context, "context"),
        (input_file, "input"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    workflow = _write_yaml(
        tmp_path / "workflows" / "structured.yaml",
        {
            "version": "2.7",
            "name": "StructuredWorkflow",
            "artifacts": {
                "review_state": {
                    "kind": "scalar",
                    "type": "enum",
                    "allowed": ["APPROVE", "REVISE"],
                }
            },
            "steps": [
                {
                    "name": "SelectNextWork",
                    "provider": "selector",
                    "asset_file": "prompts/select.md",
                    "asset_depends_on": ["prompts/context.md"],
                },
                {
                    "name": "ReadOperatorInput",
                    "provider": "selector",
                    "input_file": "docs/operator-input.md",
                },
                {
                    "name": "RunReviewLoop",
                    "id": "run_review_loop",
                    "repeat_until": {
                        "id": "review_iteration",
                        "max_iterations": 3,
                        "outputs": {
                            "review_state": {
                                "kind": "scalar",
                                "type": "enum",
                                "allowed": ["APPROVE", "REVISE"],
                                "from": {
                                    "ref": "self.steps.RouteDecision.artifacts.review_state"
                                },
                            }
                        },
                        "condition": {
                            "compare": {
                                "left": {"ref": "self.outputs.review_state"},
                                "op": "eq",
                                "right": "APPROVE",
                            }
                        },
                        "steps": [
                            {
                                "name": "Review",
                                "id": "review",
                                "provider": "reviewer",
                                "expected_outputs": [
                                    {
                                        "name": "decision",
                                        "path": "state/review-decision.txt",
                                        "type": "enum",
                                        "allowed": ["APPROVE", "REVISE"],
                                    }
                                ],
                            },
                            {
                                "name": "RouteDecision",
                                "id": "route_decision",
                                "match": {
                                    "ref": "self.steps.Review.artifacts.decision",
                                    "cases": {
                                        "APPROVE": {
                                            "id": "approve_path",
                                            "outputs": {
                                                "review_state": {
                                                    "kind": "scalar",
                                                    "type": "enum",
                                                    "allowed": ["APPROVE", "REVISE"],
                                                    "from": {
                                                        "ref": "self.steps.PublishApproval.artifacts.review_state"
                                                    },
                                                }
                                            },
                                            "steps": [
                                                {
                                                    "name": "PublishApproval",
                                                    "id": "publish_approval",
                                                    "set_scalar": {
                                                        "artifact": "review_state",
                                                        "value": "APPROVE",
                                                    },
                                                }
                                            ]
                                        },
                                        "REVISE": {
                                            "id": "revise_path",
                                            "outputs": {
                                                "review_state": {
                                                    "kind": "scalar",
                                                    "type": "enum",
                                                    "allowed": ["APPROVE", "REVISE"],
                                                    "from": {
                                                        "ref": "self.steps.WriteRevision.artifacts.review_state"
                                                    },
                                                }
                                            },
                                            "steps": [
                                                {"name": "Fix", "provider": "fixer"},
                                                {
                                                    "name": "WriteRevision",
                                                    "id": "write_revision",
                                                    "set_scalar": {
                                                        "artifact": "review_state",
                                                        "value": "REVISE",
                                                    },
                                                },
                                            ],
                                        },
                                    },
                                },
                            },
                        ],
                    },
                },
                {"name": "Finalize", "command": ["python", "finalize.py"]},
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert body.index("Current Step") < body.index("Workflow Structure")
    assert "Workflow: StructuredWorkflow" in body
    assert "Provider Flow" in body
    assert '<div class="provider-flow-strip"' in body
    assert '<svg class="provider-flow-svg"' not in body
    assert "provider-flow-loop-card" in body
    assert "provider-flow-provider-card" in body
    assert '<details class="provider-flow-source">' in body
    assert "<summary>Mermaid source</summary>" in body
    assert "flowchart TD" in body
    assert "SelectNextWork" in body
    assert "RunReviewLoop" in body
    assert "repeat_until max=3" in body
    assert "Review" in body
    assert "Fix" in body
    assert "loops until approved" in body
    assert "-. repeat .-&gt;" in body
    assert "classDef provider" in body
    assert "classDef loop" in body
    assert 'class="workflow-node provider"' in body
    assert 'class="workflow-node deterministic"' in body
    assert 'class="workflow-node deterministic contains-provider"' in body
    assert "provider inside" in body
    assert "<details class=\"workflow-card\">" in body
    assert "<details class=\"workflow-card\" open>" not in body
    assert "<summary class=\"workflow-title\">" in body
    assert "SelectNextWork" in body
    assert "RunReviewLoop" in body
    assert "repeat_until max=3" in body
    assert "RouteDecision" in body
    assert "case APPROVE" in body
    assert "PublishApproval" in body
    assert "case REVISE" in body
    assert "Fix" in body
    assert "Finalize" in body
    assert 'href="/runs/w0/run1/files/workspace/workflows/prompts/select.md"' in body
    assert 'href="/runs/w0/run1/files/workspace/workflows/prompts/context.md"' in body
    assert 'href="/runs/w0/run1/files/workspace/docs/operator-input.md"' in body
    assert "Prompts" in body
    assert str(tmp_path) not in body


def test_summary_hub_classifies_structure_from_loaded_typed_step_kinds(tmp_path: Path):
    workflow = _write_yaml(
        tmp_path / "workflows" / "typed-structure.yaml",
        {
            "version": "1.1",
            "name": "TypedStructure",
            "steps": [
                {
                    "name": "VisitItems",
                    "for_each": {
                        "items": ["one"],
                        "as": "item",
                        "steps": [
                            {"name": "Visit", "command": ["echo", "${item}"]},
                        ],
                    },
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert '<span class="workflow-kind">for_each</span>' in body
    assert '<span class="workflow-name">Visit</span>' in body
    assert '<span class="workflow-kind">command</span>' in body


def test_summary_hub_falls_back_to_observed_sequence_when_typed_surface_is_unavailable(
    tmp_path: Path,
):
    workflow = _write_yaml(
        tmp_path / "workflows" / "invalid-call.yaml",
        {
            "version": "2.14",
            "name": "invalid-call",
            "steps": [{"name": "InvalidCall", "call": "missing_import"}],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {"step_name": "SelectNextWork", "kind": "provider"},
                    {"step_name": "SelectNextWork", "kind": "phase"},
                    {"step_name": "ExecuteImplementation", "kind": "provider"},
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Observed summary sequence" in body
    assert "SelectNextWork" in body
    assert "ExecuteImplementation" in body
    assert "InvalidCall" not in body
    assert body.count('<span class="workflow-name">SelectNextWork</span>') == 1
    assert 'class="workflow-node provider observed"' in body


def test_summary_hub_expands_called_workflow_links_from_call_frame(tmp_path: Path):
    prompt = tmp_path / "workflows" / "library" / "prompts" / "selector" / "select.md"
    steering = tmp_path / "docs" / "steering.md"
    selection = tmp_path / "state" / "selection.json"
    for path, body in (
        (prompt, "select prompt"),
        (steering, "steering"),
        (selection, "{}"),
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    child = _write_yaml(
        tmp_path / "workflows" / "library" / "selector.yaml",
        {
            "version": "2.14",
            "name": "selector",
            "inputs": {"state_root": {"type": "relpath", "under": "state"}},
            "steps": [
                {
                    "name": "MaterializeInputs",
                    "command": ["python", "materialize.py"],
                    "publishes": [{"artifact": "steering", "from": "steering_path"}],
                },
                {
                    "name": "SelectNextWork",
                    "provider": "codex",
                    "asset_file": "prompts/selector/select.md",
                    "consumes": [{"artifact": "steering"}],
                    "output_bundle": {
                        "path": "${inputs.state_root}/selection.json",
                        "fields": [
                            {
                                "name": "selection_bundle_path",
                                "json_pointer": "/selection_bundle_path",
                                "type": "relpath",
                            }
                        ],
                    },
                },
            ],
        },
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "examples" / "top.yaml",
        {
            "version": "2.14",
            "name": "top",
            "imports": {"selector": "../library/selector.yaml"},
            "steps": [
                {
                    "name": "CallSelector",
                    "id": "call_selector",
                    "call": "selector",
                    "with": {"state_root": "state"},
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "call_frames": {
                    "root.call_selector::visit::1": {
                        "state": {
                            "workflow_file": str(child.relative_to(tmp_path)),
                            "status": "completed",
                            "steps": {
                                "MaterializeInputs": {
                                    "status": "completed",
                                    "artifacts": {"steering_path": "docs/steering.md"},
                                },
                                "SelectNextWork": {
                                    "status": "completed",
                                    "artifacts": {"selection_bundle_path": "state/selection.json"},
                                },
                            },
                            "artifact_versions": {
                                "steering": [
                                    {"version": 1, "value": "docs/steering.md", "producer": "MaterializeInputs"}
                                ]
                            },
                            "artifact_consumes": {"SelectNextWork": {"steering": 1}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "CallSelector" in body
    assert "SelectNextWork" in body
    assert 'href="/runs/w0/run1/files/workspace/workflows/library/prompts/selector/select.md"' in body
    assert 'href="/runs/w0/run1/files/workspace/docs/steering.md"' in body
    assert 'href="/runs/w0/run1/files/workspace/state/selection.json"' in body
    assert "Prompts" in body
    assert "Published" in body
    assert "Consumed" in body


def test_summary_hub_step_details_include_summary_artifact_links(tmp_path: Path):
    workflow = _write_yaml(
        tmp_path / "workflows" / "flow.yaml",
        {
            "version": "2.14",
            "name": "flow",
            "steps": [{"name": "ProviderStep", "provider": "codex"}],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "ProviderStep.provider.summary.md").write_text("summary", encoding="utf-8")
    (summaries / "ProviderStep.provider.snapshot.json").write_text("{}", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ProviderStep",
                        "kind": "provider",
                        "profile": "phase-performance",
                        "status": "completed",
                        "duration_ms": 123,
                        "frame_root": "call_frames/root.loop#2.run_provider__visit__4",
                        "summary_path": "summaries/ProviderStep.provider.summary.md",
                        "snapshot_path": "summaries/ProviderStep.provider.snapshot.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "steps": {"ProviderStep": {"status": "completed"}},
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert '<span class="workflow-badge">1 summary</span>' in body
    assert "Step summary artifacts" in body
    assert "provider completed loop iteration 2 / visit 4 123 ms" in body
    assert "ProviderStep <span class=\"summary-context\">loop iteration 2 / visit 4</span>" in body
    assert 'href="/runs/w0/run1/files/run/summaries/ProviderStep.provider.summary.md"' in body
    assert 'href="/runs/w0/run1/files/run/summaries/ProviderStep.provider.snapshot.json"' in body


def test_summary_hub_links_provider_dependency_and_output_targets_from_bound_inputs(tmp_path: Path):
    prompt = tmp_path / "workflows" / "library" / "prompts" / "review.md"
    prompt.parent.mkdir(parents=True)
    prompt.write_text("review", encoding="utf-8")
    steering = tmp_path / "docs" / "steering.md"
    steering.parent.mkdir()
    steering.write_text("# Steering\n", encoding="utf-8")
    review = tmp_path / "artifacts" / "review" / "architecture-review.md"
    review.parent.mkdir(parents=True)
    review.write_text("# Review\n", encoding="utf-8")
    state_root = tmp_path / "state" / "item"
    state_root.mkdir(parents=True)
    (state_root / "architecture_review_report_path.txt").write_text(
        "artifacts/review/architecture-review.md\n",
        encoding="utf-8",
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "library" / "review.yaml",
        {
            "version": "2.14",
            "name": "review",
            "inputs": {
                "state_root": {"type": "relpath", "under": "state"},
                "steering_path": {"type": "relpath"},
            },
            "steps": [
                {
                    "name": "ReviewArchitecture",
                    "provider": "codex",
                    "asset_file": "prompts/review.md",
                    "depends_on": {"required": ["${inputs.steering_path}"]},
                    "expected_outputs": [
                        {
                            "name": "architecture_review_report_path",
                            "path": "${inputs.state_root}/architecture_review_report_path.txt",
                            "type": "relpath",
                            "under": "artifacts/review",
                            "must_exist_target": True,
                        }
                    ],
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "bound_inputs": {
                    "state_root": "state/item",
                    "steering_path": "docs/steering.md",
                },
                "steps": {
                    "ReviewArchitecture": {
                        "status": "completed",
                        "artifacts": {
                            "architecture_review_report_path": "artifacts/review/architecture-review.md",
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Inputs" in body
    assert "Outputs" in body
    assert 'href="/runs/w0/run1/files/workspace/docs/steering.md" title="docs/steering.md">steering_path</a>' in body
    assert ">required 1</a>" not in body
    assert (
        'href="/runs/w0/run1/files/workspace/artifacts/review/architecture-review.md" '
        'title="artifacts/review/architecture-review.md">architecture-review.md</a>'
    ) in body
    assert (
        'href="/runs/w0/run1/files/workspace/state/item/architecture_review_report_path.txt" '
        'title="state/item/architecture_review_report_path.txt">architecture_review_report_path pointer</a>'
    ) in body
    assert ">architecture_review_report_path</a>" not in body


def test_summary_hub_links_relpath_fields_from_output_bundle(tmp_path: Path):
    architecture = tmp_path / "docs" / "plans" / "arch.md"
    architecture.parent.mkdir(parents=True)
    architecture.write_text("# Architecture\n", encoding="utf-8")
    state_root = tmp_path / "state" / "item"
    state_root.mkdir(parents=True)
    (state_root / "bundle.json").write_text(
        json.dumps({"architecture_path": "docs/plans/arch.md", "status": "DRAFTED"}),
        encoding="utf-8",
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "draft.yaml",
        {
            "version": "2.14",
            "name": "draft",
            "inputs": {"state_root": {"type": "relpath", "under": "state"}},
            "steps": [
                {
                    "name": "DraftArchitecture",
                    "provider": "codex",
                    "output_bundle": {
                        "path": "${inputs.state_root}/bundle.json",
                        "fields": [
                            {
                                "name": "architecture_path",
                                "json_pointer": "/architecture_path",
                                "type": "relpath",
                            },
                            {
                                "name": "status",
                                "json_pointer": "/status",
                                "type": "enum",
                                "allowed": ["DRAFTED"],
                            },
                        ],
                    },
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "bound_inputs": {"state_root": "state/item"},
                "steps": {"DraftArchitecture": {"status": "completed", "artifacts": {"status": "DRAFTED"}}},
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert 'href="/runs/w0/run1/files/workspace/state/item/bundle.json"' in body
    assert 'href="/runs/w0/run1/files/workspace/docs/plans/arch.md" title="docs/plans/arch.md">arch.md</a>' in body
    assert ">architecture_path</a>" not in body


def test_summary_hub_links_root_result_relpath_from_empty_pointer_output_bundle(tmp_path: Path):
    architecture = tmp_path / "docs" / "plans" / "arch.md"
    architecture.parent.mkdir(parents=True)
    architecture.write_text("# Architecture\n", encoding="utf-8")
    state_root = tmp_path / "state" / "item"
    state_root.mkdir(parents=True)
    (state_root / "bundle.json").write_text(
        json.dumps("docs/plans/arch.md"),
        encoding="utf-8",
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "draft.yaml",
        {
            "version": "2.14",
            "name": "draft",
            "steps": [
                {
                    "name": "DraftArchitecture",
                    "provider": "codex",
                    "output_bundle": {
                        "path": "state/item/bundle.json",
                        "fields": [
                            {
                                "name": "__result__",
                                "json_pointer": "",
                                "type": "relpath",
                            }
                        ],
                    },
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "steps": {"DraftArchitecture": {"status": "running"}},
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert 'href="/runs/w0/run1/files/workspace/state/item/bundle.json"' in body
    assert 'href="/runs/w0/run1/files/workspace/docs/plans/arch.md" title="docs/plans/arch.md">arch.md</a>' in body
    assert ">__result__</a>" not in body


def test_summary_hub_groups_repeated_step_summaries_by_invocation(tmp_path: Path):
    workflow = _write_yaml(
        tmp_path / "workflows" / "flow.yaml",
        {
            "version": "2.14",
            "name": "flow",
            "steps": [{"name": "ProviderStep", "provider": "codex"}],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    first = run_root / "call_frames" / "root.loop#0.provider__visit__1" / "summaries"
    second = run_root / "call_frames" / "root.loop#1.provider__visit__1" / "summaries"
    for directory in (summaries, first, second):
        directory.mkdir(parents=True)
    (first / "ProviderStep.provider.summary.md").write_text("first", encoding="utf-8")
    (second / "ProviderStep.provider.summary.md").write_text("second", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ProviderStep",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.loop#0.provider__visit__1",
                        "summary_path": (
                            "call_frames/root.loop#0.provider__visit__1/"
                            "summaries/ProviderStep.provider.summary.md"
                        ),
                    },
                    {
                        "step_name": "ProviderStep",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.loop#1.provider__visit__1",
                        "summary_path": (
                            "call_frames/root.loop#1.provider__visit__1/"
                            "summaries/ProviderStep.provider.summary.md"
                        ),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "steps": {"ProviderStep": {"status": "completed"}},
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "Invocation 1" in body
    assert "Invocation 2" in body
    assert 'href="/runs/w0/run1/files/run/call_frames/root.loop%230.provider__visit__1/summaries/ProviderStep.provider.summary.md"' in body
    assert 'href="/runs/w0/run1/files/run/call_frames/root.loop%231.provider__visit__1/summaries/ProviderStep.provider.summary.md"' in body


def test_summary_hub_invocation_links_use_matching_call_frame_state(tmp_path: Path):
    child = _write_yaml(
        tmp_path / "workflows" / "library" / "child.yaml",
        {
            "version": "2.14",
            "name": "child",
            "inputs": {"state_root": {"type": "relpath", "under": "state"}},
            "steps": [
                {
                    "name": "ReviewArchitecture",
                    "provider": "codex",
                    "expected_outputs": [
                        {
                            "name": "review_report_path",
                            "path": "${inputs.state_root}/review_report_path.txt",
                            "type": "relpath",
                            "under": "artifacts/review",
                            "must_exist_target": True,
                        }
                    ],
                }
            ],
        },
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "top.yaml",
        {
            "version": "2.14",
            "name": "top",
            "imports": {"child": "library/child.yaml"},
            "steps": [
                {
                    "name": "CallChild",
                    "id": "call_child",
                    "call": "child",
                    "with": {"state_root": "state/default"},
                }
            ],
        },
    )
    first_state_root = tmp_path / "state" / "first"
    second_state_root = tmp_path / "state" / "second"
    first_state_root.mkdir(parents=True)
    second_state_root.mkdir(parents=True)
    (first_state_root / "review_report_path.txt").write_text("artifacts/review/first.md\n", encoding="utf-8")
    (second_state_root / "review_report_path.txt").write_text("artifacts/review/second.md\n", encoding="utf-8")
    first_report = tmp_path / "artifacts" / "review" / "first.md"
    second_report = tmp_path / "artifacts" / "review" / "second.md"
    first_report.parent.mkdir(parents=True)
    first_report.write_text("# First\n", encoding="utf-8")
    second_report.write_text("# Second\n", encoding="utf-8")

    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    first_summary = run_root / "call_frames" / "root.call_child__visit__1" / "summaries"
    second_summary = run_root / "call_frames" / "root.call_child__visit__2" / "summaries"
    for directory in (summaries, first_summary, second_summary):
        directory.mkdir(parents=True)
    (first_summary / "ReviewArchitecture.provider.summary.md").write_text("first summary", encoding="utf-8")
    (second_summary / "ReviewArchitecture.provider.summary.md").write_text("second summary", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ReviewArchitecture",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.call_child__visit__1",
                        "summary_path": (
                            "call_frames/root.call_child__visit__1/"
                            "summaries/ReviewArchitecture.provider.summary.md"
                        ),
                    },
                    {
                        "step_name": "ReviewArchitecture",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.call_child__visit__2",
                        "summary_path": (
                            "call_frames/root.call_child__visit__2/"
                            "summaries/ReviewArchitecture.provider.summary.md"
                        ),
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "steps": {"CallChild": {"status": "completed"}},
                "call_frames": {
                    "root.call_child::visit::1": {
                        "state": {
                            "workflow_file": str(child.relative_to(tmp_path)),
                            "bound_inputs": {"state_root": "state/first"},
                            "steps": {
                                "ReviewArchitecture": {
                                    "status": "completed",
                                    "artifacts": {"review_report_path": "artifacts/review/first.md"},
                                }
                            },
                        }
                    },
                    "root.call_child::visit::2": {
                        "state": {
                            "workflow_file": str(child.relative_to(tmp_path)),
                            "bound_inputs": {"state_root": "state/second"},
                            "steps": {
                                "ReviewArchitecture": {
                                    "status": "completed",
                                    "artifacts": {"review_report_path": "artifacts/review/second.md"},
                                }
                            },
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    first_start = body.index("Invocation 1")
    second_start = body.index("Invocation 2")
    first_panel = body[first_start:second_start]
    second_panel = body[second_start:]
    assert "/files/workspace/state/first/review_report_path.txt" in first_panel
    assert "/files/workspace/artifacts/review/first.md" in first_panel
    assert "/files/workspace/state/second/review_report_path.txt" not in first_panel
    assert "/files/workspace/artifacts/review/second.md" not in first_panel
    assert "/files/workspace/state/second/review_report_path.txt" in second_panel
    assert "/files/workspace/artifacts/review/second.md" in second_panel


def test_summary_hub_does_not_attach_provider_summaries_to_same_named_call_step(tmp_path: Path):
    child = _write_yaml(
        tmp_path / "workflows" / "library" / "child.yaml",
        {
            "version": "2.14",
            "name": "child",
            "steps": [{"name": "DraftDesignGapArchitecture", "provider": "codex"}],
        },
    )
    workflow = _write_yaml(
        tmp_path / "workflows" / "top.yaml",
        {
            "version": "2.14",
            "name": "top",
            "imports": {"child": "library/child.yaml"},
            "steps": [
                {
                    "name": "DraftDesignGapArchitecture",
                    "id": "draft_design_gap_architecture",
                    "call": "child",
                }
            ],
        },
    )
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    frame_summaries = run_root / "call_frames" / "root.draft_design_gap_architecture__visit__1" / "summaries"
    summaries.mkdir(parents=True)
    frame_summaries.mkdir(parents=True)
    (frame_summaries / "DraftDesignGapArchitecture.provider.summary.md").write_text("summary", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "DraftDesignGapArchitecture",
                        "kind": "provider",
                        "status": "completed",
                        "frame_root": "call_frames/root.draft_design_gap_architecture__visit__1",
                        "summary_path": (
                            "call_frames/root.draft_design_gap_architecture__visit__1/"
                            "summaries/DraftDesignGapArchitecture.provider.summary.md"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": str(workflow.relative_to(tmp_path)),
                "steps": {"DraftDesignGapArchitecture": {"status": "completed"}},
                "call_frames": {
                    "root.draft_design_gap_architecture::visit::1": {
                        "state": {
                            "workflow_file": str(child.relative_to(tmp_path)),
                            "steps": {"DraftDesignGapArchitecture": {"status": "completed"}},
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    call_start = body.index('<span class="workflow-kind">call child</span>')
    provider_start = body.index('<span class="workflow-kind">provider</span>', call_start)
    call_panel = body[call_start:provider_start]
    provider_panel = body[provider_start:]
    assert "1 summary" not in call_panel
    assert "Step summary artifacts" not in call_panel
    assert "1 summary" in provider_panel
    assert "Step summary artifacts" in provider_panel


def test_summary_live_endpoint_includes_current_step_iteration_and_visit(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "current_step": {
                    "name": "DrainLoop",
                    "step_id": "root.drain_loop",
                    "visit_count": 3,
                    "started_at": "2026-04-13T12:01:00+00:00",
                },
                "steps": {
                    "DrainLoop": {
                        "debug": {
                            "structured_repeat_until": {
                                "current_iteration": 7,
                            }
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_step"]["name"] == "DrainLoop"
    assert payload["current_step"]["iteration"] == 7
    assert payload["current_step"]["visit_count"] == 3
    assert payload["current_step"]["context_label"] == "DrainLoop iteration 7 / visit 3"
    assert payload["current_step"]["display_name"] == "DrainLoop (DrainLoop iteration 7 / visit 3)"


def test_summary_context_label_uses_scoped_call_frame_iterations(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ReviewImplementation",
                        "kind": "provider",
                        "profile": "phase-performance",
                        "status": "completed",
                        "frame_root": (
                            "call_frames/root.drain_lisp_frontend_work#0."
                            "route_selection.design_gap_path.run_design_gap_work_item__visit__1/"
                            "call_frames/root.run_implementation_phase__visit__1"
                        ),
                        "summary_path": (
                            "call_frames/root.drain_lisp_frontend_work#0."
                            "route_selection.design_gap_path.run_design_gap_work_item__visit__1/"
                            "call_frames/root.run_implementation_phase__visit__1/"
                            "summaries/ReviewImplementation.provider.summary.md"
                        ),
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed", "workflow_file": "workflow.yaml", "steps": {}}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "ReviewImplementation <span class=\"summary-context\">drain_lisp_frontend_work iteration 0 / visit 1 / run_implementation_phase visit 1</span>" in body


def test_summary_context_label_prefers_loop_step_id_iteration_over_visit_one(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ReviewImplementation",
                        "kind": "provider",
                        "profile": "phase-performance",
                        "status": "completed",
                        "step_id": "root.implementation_review_loop#3.implementation_review_iteration.route_iteration_work.completed_iteration_path.review_implementation",
                        "visit_count": 1,
                        "frame_root": (
                            "call_frames/root.drain_lisp_frontend_work#0."
                            "route_selection.design_gap_path.run_design_gap_work_item__visit__1/"
                            "call_frames/root.run_implementation_phase__visit__1"
                        ),
                        "summary_path": "summaries/ReviewImplementation.provider.summary.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed", "workflow_file": "workflow.yaml", "steps": {}}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "implementation_review_loop iteration 3" in body
    assert "implementation_review_loop iteration 3 / visit 1" not in body


def test_summary_live_endpoint_returns_current_step_and_latest_summary(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    logs = run_root / "call_frames" / "root.loop#0" / "logs"
    summaries.mkdir(parents=True)
    logs.mkdir(parents=True)
    (summaries / "ExecuteImplementation.provider.summary.md").write_text("summary", encoding="utf-8")
    (summaries / "live-current-step.md").write_text("The agent is editing the implementation.\n", encoding="utf-8")
    (logs / "PreviousProvider.prompt.txt").write_text("older prompt", encoding="utf-8")
    (logs / "PreviousProvider.stderr").write_text("completed", encoding="utf-8")
    (logs / "ReviewDesignGapArchitecture.prompt.txt").write_text("current prompt", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "ExecuteImplementation",
                "step_id": "root.execute",
                "visit_count": 1,
                "provider": "cheap_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "ExecuteImplementation",
                        "kind": "provider",
                        "profile": "phase-performance",
                        "status": "completed",
                        "duration_ms": 1234,
                        "summary_path": "summaries/ExecuteImplementation.provider.summary.md",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "current_step": {
                    "name": "ExecuteImplementation",
                    "step_id": "root.execute",
                    "started_at": "2026-04-13T12:01:00+00:00",
                    "last_heartbeat_at": "2026-04-13T12:02:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )
    app = DashboardApp(RunScanner([tmp_path]), now="2026-04-13T12:03:30+00:00")

    response = app.handle("GET", "/runs/w0/run1/summaries/live.json")

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert response.headers["Content-Type"] == "application/json; charset=utf-8"
    assert payload["schema"] == "dashboard_summary_live/v1"
    assert payload["run"]["display_status"] == "running"
    assert payload["current_step"]["name"] == "ExecuteImplementation"
    assert payload["current_step"]["step_id"] == "root.execute"
    assert payload["current_step"]["age_text"] == "2m 30s"
    assert payload["current_step"]["heartbeat_age_text"] == "1m 30s"
    assert payload["summaries"]["total"] == 1
    assert payload["summaries"]["counts"] == {"provider": 1}
    assert payload["summaries"]["current_step_latest"]["summary_href"] == (
        "/runs/w0/run1/files/run/summaries/ExecuteImplementation.provider.summary.md"
    )
    assert payload["current_provider_step"]["name"] == "ReviewDesignGapArchitecture"
    assert payload["current_provider_step"]["status"] == "in_progress"
    assert payload["current_provider_step"]["prompt_href"] == (
        "/runs/w0/run1/files/run/call_frames/root.loop%230/logs/ReviewDesignGapArchitecture.prompt.txt"
    )
    assert payload["current_provider_step"]["stderr_href"] is None
    assert payload["live_note"]["text"] == "The agent is editing the implementation.\n"
    assert payload["live_note"]["summary_href"] == "/runs/w0/run1/files/run/summaries/live-current-step.md"
    assert payload["live_note"]["metadata_href"] == "/runs/w0/run1/files/run/summaries/live-current-step.json"
    assert payload["live_note"]["provider"] == "cheap_summary"
    assert str(run_root) not in json.dumps(payload)


def test_summary_live_endpoint_falls_back_to_most_recent_provider_step(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "logs"
    summaries = run_root / "summaries"
    logs.mkdir(parents=True)
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (logs / "OlderProvider.prompt.txt").write_text("older prompt", encoding="utf-8")
    (logs / "OlderProvider.stderr").write_text("older done", encoding="utf-8")
    (logs / "RouteReview.REVISE.ReviseDesign.prompt.txt").write_text("new prompt", encoding="utf-8")
    (logs / "RouteReview.REVISE.ReviseDesign.stderr").write_text("new done", encoding="utf-8")
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "running", "current_step": {"name": "ReviewLoop"}}),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_provider_step"]["name"] == "ReviseDesign"
    assert payload["current_provider_step"]["qualified_name"] == "RouteReview.REVISE.ReviseDesign"
    assert payload["current_provider_step"]["status"] == "most_recent"
    assert payload["current_provider_step"]["prompt_href"] == (
        "/runs/w0/run1/files/run/logs/RouteReview.REVISE.ReviseDesign.prompt.txt"
    )
    assert payload["current_provider_step"]["stderr_href"] == (
        "/runs/w0/run1/files/run/logs/RouteReview.REVISE.ReviseDesign.stderr"
    )


def test_summary_live_endpoint_accepts_note_for_active_nested_provider(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    logs = run_root / "call_frames" / "root.loop#0" / "logs"
    summaries = run_root / "summaries"
    logs.mkdir(parents=True)
    summaries.mkdir(parents=True)
    (logs / "DraftPlan.prompt.txt").write_text("current prompt", encoding="utf-8")
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.md").write_text("The planner is drafting.\n", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "DraftPlan",
                "step_id": "root.draft_plan",
                "visit_count": 2,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "current_step": {
                    "name": "DrainLispFrontendWork",
                    "step_id": "root.drain_lisp_frontend_work",
                    "started_at": "2026-04-13T12:01:00+00:00",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_provider_step"]["name"] == "DraftPlan"
    assert payload["current_provider_step"]["status"] == "in_progress"
    assert payload["live_note"]["available"] is True
    assert payload["live_note"]["text"] == "The planner is drafting.\n"


def test_summary_live_endpoint_accepts_note_for_nested_provider_state_without_prompt_log(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.md").write_text("The architect is drafting.\n", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "DraftDesignGapArchitecture",
                "step_id": "root.draft_design_gap_architecture",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "current_step": {
                    "name": "DrainLispFrontendWork",
                    "step_id": "root.drain_lisp_frontend_work",
                    "type": "repeat_until",
                    "status": "running",
                },
                "call_frames": {
                    "root.drain_lisp_frontend_work#0.draft_design_gap_architecture::visit::1": {
                        "state": {
                            "status": "running",
                            "current_step": {
                                "name": "DraftDesignGapArchitecture",
                                "step_id": "root.draft_design_gap_architecture",
                                "type": "provider",
                                "status": "running",
                                "visit_count": 1,
                                "started_at": "2026-04-13T12:01:00+00:00",
                                "last_heartbeat_at": "2026-04-13T12:02:00+00:00",
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_provider_step"]["name"] == "DraftDesignGapArchitecture"
    assert payload["current_provider_step"]["status"] == "in_progress"
    assert payload["current_provider_step"]["prompt_href"] is None
    assert payload["live_note"]["available"] is True
    assert payload["live_note"]["text"] == "The architect is drafting.\n"


def test_summary_live_endpoint_uses_live_note_metadata_when_nested_provider_state_is_absent(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.md").write_text("The reviewer is checking the architecture.\n", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "ReviewDesignGapArchitecture",
                "step_id": "root.architecture_review_loop#0.architecture_review_iteration.review_design_gap_architecture",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "observability": {
                    "step_summaries": {
                        "live_agent_notes": {
                            "enabled": True,
                            "provider": "claude_haiku_summary",
                        }
                    }
                },
                "current_step": {
                    "name": "DrainLispFrontendWork",
                    "step_id": "root.drain_lisp_frontend_work",
                    "type": "repeat_until",
                    "status": "running",
                },
                "call_frames": {
                    "root.drain_lisp_frontend_work#0.draft_design_gap_architecture::visit::1": {
                        "state": {
                            "status": "running",
                            "current_step": {
                                "name": "ArchitectureReviewLoop",
                                "step_id": "root.architecture_review_loop",
                                "type": "repeat_until",
                                "status": "running",
                                "visit_count": 1,
                            },
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_provider_step"]["name"] == "ReviewDesignGapArchitecture"
    assert payload["current_provider_step"]["step_id"] == (
        "root.architecture_review_loop#0.architecture_review_iteration.review_design_gap_architecture"
    )
    assert payload["current_provider_step"]["status"] == "most_recent"
    assert payload["current_provider_step"]["prompt_href"] is None
    assert payload["live_note"]["available"] is True
    assert payload["live_note"]["text"] == "The reviewer is checking the architecture.\n"


def test_summary_live_endpoint_prefers_newer_live_note_over_stale_provider_log(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    old_logs = run_root / "call_frames" / "old" / "logs"
    summaries.mkdir(parents=True)
    old_logs.mkdir(parents=True)
    old_prompt = old_logs / "RouteIterationWork.COMPLETED.ReviewImplementation.prompt.txt"
    old_prompt.write_text("old review prompt\n", encoding="utf-8")
    old_stderr = old_logs / "RouteIterationWork.COMPLETED.ReviewImplementation.stderr"
    old_stderr.write_text("", encoding="utf-8")
    old_time = datetime(2026, 4, 13, 12, 2, tzinfo=timezone.utc).timestamp()
    os.utime(old_prompt, (old_time, old_time))
    os.utime(old_stderr, (old_time, old_time))
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.error.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note_error/v1",
                "step_name": "RouteIterationWork.COMPLETED.ReviewImplementation",
                "step_id": "root.old_review",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
                "stage": "execute",
                "error": {"message": "live note provider exited 1"},
            }
        ),
        encoding="utf-8",
    )
    (summaries / "live-current-step.md").write_text("The reviewer is checking the current design.\n", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "ReviewDesignGapArchitecture",
                "step_id": "root.current_review",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:04:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "observability": {
                    "step_summaries": {
                        "live_agent_notes": {
                            "enabled": True,
                            "provider": "claude_haiku_summary",
                        }
                    }
                },
                "current_step": {
                    "name": "DrainLispFrontendWork",
                    "step_id": "root.drain_lisp_frontend_work",
                    "type": "repeat_until",
                    "status": "running",
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["current_provider_step"]["name"] == "ReviewDesignGapArchitecture"
    assert payload["live_note"]["available"] is True
    assert payload["live_note"]["text"] == "The reviewer is checking the current design.\n"
    assert "error_href" not in payload["live_note"]


def test_summary_live_endpoint_explains_missing_live_note_when_not_enabled(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "observability": {
                    "step_summaries": {
                        "enabled": True,
                        "mode": "async",
                    }
                },
                "current_step": {
                    "name": "DrainLoop",
                    "type": "repeat_until",
                    "step_id": "root.drain_loop",
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json")

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert payload["live_note"]["available"] is False
    assert "not enabled" in payload["live_note"]["reason"]


def test_summary_live_endpoint_reports_live_note_provider_errors(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.error.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note_error/v1",
                "step_name": "ExecuteImplementation",
                "step_id": "root.execute",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:04:00+00:00",
                "stage": "execute",
                "error": {"message": "You've hit your limit · resets 2:50am"},
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "observability": {
                    "step_summaries": {
                        "enabled": True,
                        "live_agent_notes": {
                            "enabled": True,
                            "provider": "claude_haiku_summary",
                        },
                    }
                },
                "current_step": {
                    "name": "ExecuteImplementation",
                    "step_id": "root.execute",
                    "visit_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json")

    payload = json.loads(response.body.decode("utf-8"))
    assert response.status == 200
    assert payload["live_note"]["available"] is False
    assert payload["live_note"]["stage"] == "execute"
    assert payload["live_note"]["provider"] == "claude_haiku_summary"
    assert "You've hit your limit" in payload["live_note"]["reason"]
    assert payload["live_note"]["error_href"] == "/runs/w0/run1/files/run/summaries/live-current-step.error.json"


def test_summary_live_endpoint_ignores_error_superseded_by_newer_live_note(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (summaries / "live-current-step.error.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note_error/v1",
                "step_name": "ExecuteImplementation",
                "step_id": "root.execute",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:02:00+00:00",
                "stage": "execute",
                "error": {"message": "live note provider exited 1"},
            }
        ),
        encoding="utf-8",
    )
    (summaries / "live-current-step.md").write_text("The agent recovered after a transient note error.\n", encoding="utf-8")
    (summaries / "live-current-step.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_live_agent_note/v1",
                "step_name": "ExecuteImplementation",
                "step_id": "root.execute",
                "visit_count": 1,
                "provider": "claude_haiku_summary",
                "generated_at": "2026-04-13T12:03:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "running",
                "observability": {
                    "step_summaries": {
                        "enabled": True,
                        "live_agent_notes": {
                            "enabled": True,
                            "provider": "claude_haiku_summary",
                        },
                    }
                },
                "current_step": {
                    "name": "ExecuteImplementation",
                    "step_id": "root.execute",
                    "visit_count": 1,
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(_app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json").body.decode("utf-8"))

    assert payload["live_note"]["available"] is True
    assert payload["live_note"]["text"] == "The agent recovered after a transient note error.\n"
    assert "error_href" not in payload["live_note"]


def test_summary_hub_page_contains_live_panel_and_nonce_script(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps({"schema": "orchestrator_summary_index/v1", "entries": []}),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "running", "current_step": {"name": "StepA"}}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    nonce_match = re.search(r"<script nonce=\"([^\"]+)\"", body)
    assert response.status == 200
    assert 'id="live-current-step"' in body
    assert 'data-live-url="/runs/w0/run1/summaries/live.json"' in body
    assert 'class="live-note-text"' in body
    assert 'data-live-field="live-note"' in body
    assert 'data-live-field="provider-step"' in body
    assert 'data-live-link="provider-prompt"' in body
    assert nonce_match is not None
    assert f"script-src 'nonce-{nonce_match.group(1)}'" in response.headers["Content-Security-Policy"]


def test_summary_hub_missing_or_invalid_index_is_safe(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    run_root.mkdir(parents=True)
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )

    missing = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")
    assert missing.status == 200
    assert "No summary hub is available" in missing.body.decode("utf-8")

    summaries = run_root / "summaries"
    summaries.mkdir()
    (summaries / "index.json").write_text("{invalid", encoding="utf-8")
    invalid = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")
    body = invalid.body.decode("utf-8")
    assert invalid.status == 200
    assert "Summary index is invalid" in body
    assert 'href="/runs/w0/run1/files/run/summaries/index.json"' in body


def test_summary_hub_surfaces_typed_terminal_summary_and_live_payload(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "typed-terminal-summary.json").write_text(
        json.dumps(
            {
                "schema_id": "workflow_lisp_observability_summary.v1",
                "authority": "observability_only",
                "paths": {
                    "json": "summaries/typed-terminal-summary.json",
                    "markdown": "summaries/typed-terminal-summary.md",
                    "report": "summaries/observability_summary_report.json",
                },
                "terminal_value": {"status": "BLOCKED", "selected_item": "docs/design/example.md"},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (summaries / "typed-terminal-summary.md").write_text("typed terminal summary\n", encoding="utf-8")
    (summaries / "observability_summary_report.json").write_text(
        json.dumps(
            {
                "schema_id": "workflow_lisp_observability_summary_report.v1",
                "status": "pass",
                "diagnostics": {"errors": [], "warnings": []},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "workflow-terminal",
                        "kind": "typed_terminal",
                        "profile": "workflow-lisp-c2",
                        "status": "completed",
                        "authority": "observability_only",
                        "summary_path": "summaries/typed-terminal-summary.md",
                        "snapshot_path": "summaries/typed-terminal-summary.json",
                        "report_path": "summaries/observability_summary_report.json",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    state_file = run_root / "state.json"
    state_file.write_text(
        json.dumps(
            {
                "run_id": "run1",
                "status": "completed",
                "workflow_file": "workflow.yaml",
                "workflow_outputs": {"status": "BLOCKED"},
                "steps": {},
            }
        ),
        encoding="utf-8",
    )
    before = state_file.read_text(encoding="utf-8")

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")
    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "workflow-terminal" in body
    assert "typed-terminal-summary.md" in body
    assert "typed-terminal-summary.json" in body
    assert "observability_summary_report.json" in body

    live_response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries/live.json")
    payload = json.loads(live_response.body.decode("utf-8"))
    assert live_response.status == 200
    assert payload["summaries"]["counts"]["typed_terminal"] == 1
    latest = payload["summaries"]["current_step_latest"]
    if latest is not None:
        assert latest["kind"] == "typed_terminal"
    assert state_file.read_text(encoding="utf-8") == before


def test_summary_hub_does_not_link_unsafe_index_paths(tmp_path: Path):
    run_root = tmp_path / ".orchestrate" / "runs" / "run1"
    summaries = run_root / "summaries"
    summaries.mkdir(parents=True)
    (summaries / "index.json").write_text(
        json.dumps(
            {
                "schema": "orchestrator_summary_index/v1",
                "entries": [
                    {
                        "step_name": "UnsafeStep",
                        "kind": "provider",
                        "status": "completed",
                        "summary_path": "../outside.md",
                        "snapshot_path": "summaries/safe.json",
                        "error_path": None,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_root / "state.json").write_text(
        json.dumps({"run_id": "run1", "status": "completed"}),
        encoding="utf-8",
    )

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/summaries")

    body = response.body.decode("utf-8")
    assert response.status == 200
    assert "UnsafeStep" in body
    assert "unsafe path" in body
    assert "../outside.md" not in body
    assert "/files/run/../outside.md" not in body


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


def test_markdown_file_preview_renders_safe_markdown_html(tmp_path: Path):
    note = tmp_path / "docs" / "note.md"
    note.parent.mkdir()
    note.write_text(
        "# Rendered Note\n\nA **strong** point with <script>bad()</script>.\n\n- first\n- second\n",
        encoding="utf-8",
    )
    _write_run(tmp_path, "run1", {"run_id": "run1", "status": "completed"})

    response = _app(tmp_path).handle("GET", "/runs/w0/run1/files/workspace/docs/note.md")

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
