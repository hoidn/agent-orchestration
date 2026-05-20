# Dashboard Observability Summary GUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only dashboard page that lets users browse run-level observability summaries and watch the currently in-progress step update while the page is open.

**Architecture:** Extend the existing stdlib dashboard with a `/summaries` route backed by `RUN_ROOT/summaries/index.json` plus a `/summaries/live.json` polling endpoint backed by request-time state projection. Reuse existing run-scoped file preview links and CSP/escaping behavior; allow only a nonce-protected inline updater on the summary hub page. Keep the route read-only and advisory-only.

**Structure panel extension:** Render an escaped ASCII workflow map near the top of the Summary Hub. Prefer the authored `state.workflow_file` YAML as the source; fall back to the observed unique step sequence from `summaries/index.json` when the workflow file cannot be read.

**Linked map extension:** Replace the ASCII-only map with a dashboard-native nested HTML tree. Step cards show kind badges plus safe links to existing prompt files and to published/consumed artifact files that the current run state can resolve.

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

## Task 6: Add Workflow Structure Panel

- [ ] Add a failing test that creates a workflow YAML with provider, command,
  repeat-until, and match-shaped nested steps.
- [ ] Assert `/runs/w0/run1/summaries` includes a "Workflow Structure" section
  before summary entries and renders the ordered ASCII tree without absolute
  paths.
- [ ] Add a failing fallback test where `state.workflow_file` is absent but
  `summaries/index.json` has entries, and assert the panel is labeled as an
  observed summary sequence.
- [ ] Implement a small dashboard-local workflow structure renderer in
  `orchestrator/dashboard/server.py`.
- [ ] Parse workflow YAML with `yaml.safe_load` through the existing
  workspace-scoped file resolver; do not execute or load workflow semantics for
  this display-only panel.
- [ ] Escape all rendered diagram text in the `<pre>` block.
- [ ] Run `python -m pytest tests/test_dashboard_server.py -q`.

## Task 7: Make Workflow Structure Linked And Readable

- [ ] Add a failing test with a workflow step that has `asset_file`,
  `asset_depends_on`, `publishes`, and `consumes`, plus run state containing
  existing artifact files for the published and consumed artifacts.
- [ ] Assert the Summary Hub renders a styled workflow tree rather than only a
  `<pre>` dump.
- [ ] Assert prompt links use workspace-scoped file routes and only appear when
  the prompt files exist.
- [ ] Assert published and consumed artifact links use run-scoped file routes
  and only appear when the resolved artifact values exist.
- [ ] Keep the observed-summary fallback, but render it as the same styled tree.
- [ ] Implement a small dashboard-local view model for workflow nodes and link
  groups in `orchestrator/dashboard/server.py`.
- [ ] Use the existing `FileReferenceResolver` for all links; never expose
  absolute paths.
- [ ] Run `python -m pytest tests/test_dashboard_server.py -q` and the focused
  dashboard/observability regression selectors.

## Task 8: Distinguish Provider Steps And Collapse Details

- [ ] Add failing tests that provider nodes render with a provider-specific
  class while deterministic nodes use the deterministic class.
- [ ] Add failing tests that workflow cards are native `<details>` controls and
  are collapsed by default.
- [ ] Add failing tests that summary entries appear inside the expanded card as
  step summary artifact links.
- [ ] Implement provider-specific visual styling and collapsed details cards in
  `orchestrator/dashboard/server.py`.
- [ ] Keep the one-line summary readable when collapsed: step name, kind badge,
  summary count, and link count.
- [ ] Run the focused dashboard/observability regression selectors and restart
  the dashboard.
