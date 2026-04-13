Completed In This Pass
- Fixed the dashboard scanner trust-boundary bug where a workspace-local `state.json` symlink could import state from outside the configured workspace.
- Fixed dashboard freshness projection so each request uses request-time `now`, including workflow-aware report snapshot projection.
- Implemented call-frame-local artifact lineage projection and run-detail rendering for `artifact_versions` and `artifact_consumes`.
- Added visible truncation messaging for capped state/file previews.
- Added regression coverage for the high-severity scanner/freshness findings, the call-frame lineage tranche, and the preview truncation display gap.

Completed Plan Tasks
- Completed the reviewed Tranche 3 Step 5 gap for call-frame-local artifact lineage, with `FileReferenceResolver` validation for frame-local artifact version values.
- Repaired the reviewed high-severity scanner and freshness regressions in the already-implemented dashboard work.
- Repaired the reviewed medium preview display gap for large capped previews.

Remaining Required Plan Tasks
- None identified for the approved dashboard MVP after this pass.
- Optional deferrals remain out of scope: persistent indexing, authentication, background workers/watchers, full-text search, rich binary rendering, dashboard-triggered actions, and multi-user deployment hardening.

Verification
- Red checks before fixes:
  - `pytest tests/test_dashboard_scanner.py::test_scanner_rejects_state_json_symlink_escape tests/test_dashboard_projection.py::test_projector_exposes_call_frame_local_artifact_lineage tests/test_dashboard_server.py::test_runs_index_uses_request_time_for_freshness tests/test_dashboard_server.py::test_run_detail_renders_call_frame_local_artifact_lineage tests/test_dashboard_server.py::test_file_preview_route_displays_truncated_large_files -v`: 5 failed as expected before implementation.
  - `pytest tests/test_dashboard_projection.py::test_projector_uses_injected_time_for_workflow_aware_stale_heartbeat -v`: failed as expected before wiring `now` into `build_status_snapshot`.
- Focused regression checks after fixes:
  - `pytest tests/test_dashboard_scanner.py::test_scanner_rejects_state_json_symlink_escape tests/test_dashboard_projection.py::test_projector_exposes_call_frame_local_artifact_lineage tests/test_dashboard_server.py::test_runs_index_uses_request_time_for_freshness tests/test_dashboard_server.py::test_run_detail_renders_call_frame_local_artifact_lineage tests/test_dashboard_server.py::test_file_preview_route_displays_truncated_large_files -v`: 5 passed.
  - `pytest tests/test_dashboard_projection.py::test_projector_uses_injected_time_for_workflow_aware_stale_heartbeat -v`: 1 passed.
- Affected module suite: `pytest tests/test_dashboard_scanner.py tests/test_dashboard_projection.py tests/test_dashboard_server.py -v`: 32 passed.
- Dashboard collection: `pytest --collect-only tests/test_dashboard_scanner.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py tests/test_dashboard_files.py tests/test_dashboard_preview.py tests/test_dashboard_commands.py tests/test_dashboard_server.py tests/test_cli_dashboard_command.py -q`: 53 tests collected.
- Targeted dashboard/report suite: `pytest tests/test_dashboard_scanner.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py tests/test_dashboard_files.py tests/test_dashboard_preview.py tests/test_dashboard_commands.py tests/test_dashboard_server.py tests/test_cli_dashboard_command.py tests/test_observability_report.py tests/test_cli_report_command.py -v`: 83 passed.
- Local dashboard smoke via tmux: `python -m orchestrator dashboard --workspace /home/ollie/Documents/agent-orchestration --host 127.0.0.1 --port 35057`; verified `/` returned 302 to `/runs`, `/runs` returned 200, one run detail page returned 200, and `/state` returned 200 with `X-Content-Type-Options: nosniff` and restrictive CSP.
- Static check: `git diff --check`: passed.

Residual Risks
- The broad non-dashboard test suite was not rerun in this pass.
- The dashboard remains the approved local read-only MVP and still intentionally omits persistent indexing, authentication, background watchers, full-text search, rich binary rendering, and dashboard-triggered actions.
