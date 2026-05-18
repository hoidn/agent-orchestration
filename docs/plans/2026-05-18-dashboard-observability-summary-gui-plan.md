# Dashboard Observability Summary GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only dashboard page that lets users browse run-level observability summaries and watch the currently in-progress step update while the page is open.

**Architecture:** Extend the existing stdlib dashboard with a `/summaries` route backed by `RUN_ROOT/summaries/index.json` plus a `/summaries/live.json` polling endpoint backed by request-time state projection. Reuse existing run-scoped file preview links and CSP/escaping behavior; allow only a nonce-protected inline updater on the summary hub page. Keep the route read-only and advisory-only.

**Tech Stack:** Python stdlib HTTP server, existing `orchestrator.dashboard` modules, pytest.

---

## Files

- Modify `orchestrator/dashboard/server.py`
  - Add route dispatch for `/runs/<workspace>/<run>/summaries`.
  - Add route dispatch for `/runs/<workspace>/<run>/summaries/live.json`.
  - Render a summary hub page from `summaries/index.json`.
  - Render a live current-step panel that polls the JSON endpoint.
  - Add a run-detail link to the summary hub.
- Modify `orchestrator/dashboard/projection.py`
  - Include summary hub files in run observability file discovery.
- Modify `specs/cli.md`
  - Document dashboard summary route in dashboard route list.
- Modify `specs/observability.md`
  - Document the dashboard summary hub as a read-only GUI over summary artifacts.
- Add/modify `tests/test_dashboard_server.py`
  - Cover route rendering, escaping, invalid/missing index behavior, and unsafe path handling.

## Task 1: Add Failing Dashboard Route Tests

- [ ] Add a test that writes `summaries/index.json`, `summaries/run-summary.md`, a nested summary file, and `state.json`.
- [ ] Assert run detail contains a `/summaries` link.
- [ ] Assert `/runs/w0/run1/summaries` renders the step name, kind, status, duration, escaped markdown preview, and safe `/files/run/...` links.
- [ ] Add missing-index and unsafe-path tests.
- [ ] Run the new selectors and verify they fail before implementation.

## Task 2: Implement Summary Route

- [ ] Add route dispatch for `/runs/<workspace>/<run>/summaries`.
- [ ] Add `_summary_hub(detail)` renderer.
- [ ] Read and validate `summaries/index.json`.
- [ ] Use `FileReferenceResolver.run_ref` for every summary/snapshot/error path before linking.
- [ ] Preview `summaries/run-summary.md` through `PreviewRenderer`.
- [ ] Render invalid/missing index states as safe HTML.

## Task 3: Integrate With Detail And Docs

- [ ] Add a run-detail "Summary Hub" link when the index exists.
- [ ] Include summary hub files in Observability Files.
- [ ] Update specs to mention the dashboard route.
- [ ] Run focused dashboard tests.

## Task 4: Verification

- [ ] Run `python -m pytest tests/test_dashboard_server.py tests/test_dashboard_files.py -q`.
- [ ] Run `python -m pytest tests/test_cli_dashboard_command.py tests/test_dashboard_projection.py -q`.
- [ ] Run a local dashboard smoke check against the current workspace if useful.
- [ ] Run `git diff --check` on touched files.

## Task 5: Add Live Current-Step View

- [ ] Add a failing test for `/runs/w0/run1/summaries/live.json` with a running `current_step`.
- [ ] Assert the JSON payload includes run status, current step identity, age fields, summary counts, and a safe latest-summary link.
- [ ] Add a failing test that the summary hub HTML contains a live current-step panel, a polling endpoint reference, and a nonce-protected script.
- [ ] Implement the JSON endpoint by reusing the existing request-time `DashboardRunDetail` projection.
- [ ] Add a small inline updater that polls every few seconds, writes via `textContent`, and leaves the static page useful without JavaScript.
- [ ] Verify existing missing-index, invalid-index, and unsafe-path behavior still works.
