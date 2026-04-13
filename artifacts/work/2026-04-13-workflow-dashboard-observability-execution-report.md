Completed In This Pass
- Added a local read-only `orchestrate dashboard` command for explicit workspace roots.
- Added dashboard read-model primitives for workspace scanning, run projection, execution cursor projection, safe file references, capped previews, and structured copyable commands.
- Added stdlib server-rendered dashboard routes for run index, run detail, step detail, state preview, workspace/run file previews, raw download responses, filtering, and optional meta refresh.
- Updated dashboard CLI/observability/security specs for the new command, read-only status semantics, route-scoped file serving, restrictive CSP, and safe raw downloads.

Completed Plan Tasks
- Tranche 1: specs and pure report status projection.
- Tranche 2: workspace scanner, models, file resolver, and preview primitives.
- Tranche 3: run projection and execution cursor projection.
- Tranche 4: command builder and CLI parser/handler wiring.
- Tranche 5: server skeleton and recent-run index.
- Tranche 6: run detail, step detail, and state preview routes.
- Tranche 7: file preview and raw download routes.
- Tranche 8: page-level refresh, docs sweep, focused verification, smoke check, static check, and execution report.

Remaining Required Plan Tasks
- None for the approved MVP plan.

Verification
- `pytest --collect-only tests/test_dashboard_scanner.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py tests/test_dashboard_files.py tests/test_dashboard_preview.py tests/test_dashboard_commands.py tests/test_dashboard_server.py tests/test_cli_dashboard_command.py -q`: 44 tests collected.
- `pytest tests/test_dashboard_scanner.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py tests/test_dashboard_files.py tests/test_dashboard_preview.py tests/test_dashboard_commands.py tests/test_dashboard_server.py tests/test_cli_dashboard_command.py tests/test_observability_report.py tests/test_cli_report_command.py -v`: 74 passed.
- Local dashboard smoke via tmux: `python -m orchestrator dashboard --workspace /home/ollie/Documents/agent-orchestration --host 127.0.0.1 --port 8765`; `curl` verified `/` returned 302, `/runs` returned 200 HTML with `nosniff` and restrictive CSP, and `/runs/w0/20260413T205412Z-yhwi5l` plus `/state` returned non-empty HTML.
- `git diff --check`: passed.
- Additional broad check `pytest -m "not e2e" -v`: 875 passed, 53 failed, 11 deselected. The failures are outside the dashboard surface and are dominated by pre-existing legacy tests that instantiate `WorkflowExecutor` with raw dictionaries plus demo nanobragg provenance/alignment failures.

Residual Risks
- The dashboard is an MVP server-rendered operator view; it intentionally has no persistent index, authentication, background watcher, full-text search, or rich binary rendering.
- The run projector degrades to state-only display when workflow metadata cannot be safely loaded, so some step kind/order metadata may be less precise for invalid or missing workflow files.
- The broad non-e2e suite is not clean in this checkout; targeted dashboard/report verification and smoke checks pass, but unrelated failing tests remain in the repository.
