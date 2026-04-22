# Workflow Dashboard Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` by default; use `superpowers:subagent-driven-development` only if the user explicitly authorizes subagents. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a worktree for this repo.

**Goal:** Add a local read-only `orchestrate dashboard` web dashboard for recent workflow runs, run details, safe file previews, and copyable operator commands across explicit workspace roots.

**Architecture:** Build tested read-model primitives before serving HTML: pure status projection, workspace scanning, execution-cursor projection, safe file references, capped preview rendering, and structured command generation. Serve server-rendered HTML from the existing CLI with the Python standard library and keep `state.json` plus the scanned run directory as the source of truth. The dashboard must never call the mutating `report_workflow()` path, execute commands, or trust paths recorded inside state as authority.

**Tech Stack:** Python 3.11, stdlib `http.server`/URL parsing/HTML escaping, existing `WorkflowLoader` and observability projection helpers, `state.json` run directories, pytest unit/integration tests, normative specs in `specs/`.

---

## Source Inputs

- Approved design: `docs/plans/2026-04-13-workflow-dashboard-observability-design.md`
- Documentation map: `docs/index.md`
- Normative references for implementation: `specs/cli.md`, `specs/observability.md`, `specs/security.md`, `specs/state.md`
- Existing projection path: `orchestrator/observability/report.py`
- Existing mutating CLI path to avoid in dashboard routes: `orchestrator/cli/commands/report.py::report_workflow`

## Compatibility Boundaries

- No state schema migration. The dashboard reads current and older `state.json` shapes defensively and degrades to state-only display when workflow metadata cannot be loaded.
- No workflow DSL version gate. Ordinary workflows must not add dashboard-specific fields.
- `report_workflow()` may keep its existing stale-run reconciliation behavior, but dashboard projection must keep `persisted_status` and advisory `display_status` separate and must not write `context.status_reconciled_*`.
- Run identity is `(resolved_workspace_root, run_directory_name)`. `state.run_id` is display metadata only and cannot alter routing or file scope.
- Route file references are workspace-relative or run-relative after validation. Raw absolute filesystem links must not appear in dashboard HTML.
- The first implementation remains local/operator-only. Binding beyond `127.0.0.1` is explicit operator choice, not a production security model.
- Python dependencies remain unchanged; do not add a SPA framework, web framework, or frontend build pipeline.

## Migrations

- Additive CLI surface: `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]`.
- Additive docs/spec updates: document the command, read-only dashboard contract, and dashboard file-serving/content-isolation rules.
- No persistent index, database, state upgrader, workflow YAML migration, artifact schema migration, or run-directory rewrite.

## Non-Goals

- Do not implement dashboard-triggered resume, repair, clean, delete, workflow mutation, tmux execution, or provider/shell command execution.
- Do not implement prompt recomposition, prompt diffing, rich binary artifact rendering, full-text log search, background workers, persistent indexing, multi-user hosting, authentication, or non-local deployment hardening.
- Do not infer future executor routing, repair stale runs, or decide whether resume would skip/replay/quarantine a step.
- Do not hard-code revision-study-specific pages or artifact semantics into the core read model.
- Do not write tests that assert literal prompt text or prompt phrasing.

## Proposed File Structure

- Modify: `orchestrator/observability/report.py`
  Extract or expose pure status projection helpers that dashboard and report can share without state mutation.
- Create: `orchestrator/dashboard/__init__.py`
  Package marker and public exports for dashboard read-model/server pieces.
- Create: `orchestrator/dashboard/models.py`
  Dataclasses or typed dictionaries for workspace records, run keys, index rows, detail models, file references, preview results, command models, and warnings.
- Create: `orchestrator/dashboard/scanner.py`
  Workspace resolution/deduplication and `.orchestrate/runs/*/state.json` candidate scanning.
- Create: `orchestrator/dashboard/projection.py`
  State loading, workflow-aware/state-only run projection, row/detail construction, artifact lineage extraction, and degraded parse/read error rows.
- Create: `orchestrator/dashboard/cursor.py`
  Active execution cursor projection for top-level `current_step`, nested `call_frames`, `repeat_until`, `for_each`, and finalization state.
- Create: `orchestrator/dashboard/files.py`
  Safe file-reference resolver and route-scoped path validation for workspace-relative, run-relative, and validated absolute paths.
- Create: `orchestrator/dashboard/preview.py`
  Capped text/JSON preview loading, binary/large/missing/unreadable states, escaping, and safe raw-download metadata.
- Create: `orchestrator/dashboard/commands.py`
  Structured `CommandBuilder` with `cwd`, `argv`, POSIX `shell_text`, warnings, run-id mismatch behavior, non-default runs-root flags, and optional trusted tmux metadata.
- Create: `orchestrator/dashboard/server.py`
  `ThreadingHTTPServer`/request handler, route dispatch, query filtering, server-rendered HTML, redirects, safe response headers, and local bind logging.
- Create: `orchestrator/cli/commands/dashboard.py`
  CLI command implementation that validates workspace arguments and starts the dashboard server.
- Modify: `orchestrator/cli/main.py`
  Parser and dispatch wiring for `dashboard`.
- Modify: `orchestrator/cli/commands/__init__.py`
  Export `dashboard_workflow` or equivalent command handler.
- Modify: `specs/cli.md`, `specs/observability.md`, `specs/security.md`
  Normative dashboard CLI, observability, read-only, and file-serving contracts.
- Add tests:
  `tests/test_dashboard_scanner.py`,
  `tests/test_dashboard_projection.py`,
  `tests/test_dashboard_cursor.py`,
  `tests/test_dashboard_files.py`,
  `tests/test_dashboard_preview.py`,
  `tests/test_dashboard_commands.py`,
  `tests/test_dashboard_server.py`,
  `tests/test_cli_dashboard_command.py`.

## Tranche 1: Contracts and Pure Projection Prerequisite

**Purpose:** Pin the external contract and make pure status derivation reusable before dashboard code depends on it.

**Files:**
- Modify: `specs/cli.md`
- Modify: `specs/observability.md`
- Modify: `specs/security.md`
- Modify: `orchestrator/observability/report.py`
- Modify: `tests/test_observability_report.py`
- Test: `tests/test_cli_report_command.py`

- [ ] Step 1: Update specs for the new read-only dashboard surface.
  Add `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]` to `specs/cli.md`. In `specs/observability.md`, state that dashboard display status is advisory and does not reconcile persisted `state.status`. In `specs/security.md`, add dashboard-specific route file-serving and browser content-isolation rules.

- [ ] Step 2: Add tests proving pure projection does not mutate state.
  In `tests/test_observability_report.py`, cover a stale running state where the pure helper returns `display_status: failed`, `persisted_status: running`, and `display_status_reason: stale_running_*` without writing `state.json` or mutating the input dict.

- [ ] Step 3: Extract the pure status derivation.
  In `orchestrator/observability/report.py`, expose a pure helper such as `derive_status_projection(state, step_entries, now=None)` or `build_status_snapshot(..., mutate=False)` that returns persisted/display status separately. Keep `report_workflow()` as the only caller that writes reconciled stale status to disk.

- [ ] Step 4: Preserve existing report behavior.
  Update `tests/test_cli_report_command.py::test_report_reconciles_stale_running_state_on_disk` only if the helper shape changes; the report command should still self-heal stale running runs.

- [ ] Step 5: Verify tranche.
  Run:
  ```bash
  pytest tests/test_observability_report.py -k "stale or current_step or snapshot" -v
  pytest tests/test_cli_report_command.py -k "report_reconciles_stale_running_state_on_disk or parser_supports_report" -v
  ```
  Expected: all selected tests pass; stale projection is pure, while `report_workflow()` still mutates only through the existing report command.

- [ ] Step 6: Commit tranche.
  ```bash
  git add specs/cli.md specs/observability.md specs/security.md orchestrator/observability/report.py tests/test_observability_report.py tests/test_cli_report_command.py
  git commit -m "feat: define dashboard observability contract"
  ```

## Tranche 2: Workspace Scanner, Models, and Safe File Boundary

**Purpose:** Establish route-independent trust boundaries before any HTML page can expose file links.

**Files:**
- Create: `orchestrator/dashboard/__init__.py`
- Create: `orchestrator/dashboard/models.py`
- Create: `orchestrator/dashboard/scanner.py`
- Create: `orchestrator/dashboard/files.py`
- Create: `orchestrator/dashboard/preview.py`
- Add: `tests/test_dashboard_scanner.py`
- Add: `tests/test_dashboard_files.py`
- Add: `tests/test_dashboard_preview.py`

- [ ] Step 1: Write scanner tests first.
  Cover zero runs, multiple workspaces, duplicate `state.run_id` values across workspaces, workspace symlink dedupe, non-directory workspace rejection, malformed `state.json` rows, and state/run-directory id mismatch warnings.

- [ ] Step 2: Implement `RunScanner`.
  Resolve workspace roots through symlinks at startup, deduplicate by real path, reject non-directories, and discover only `<workspace>/.orchestrate/runs/*/state.json`. Candidate run keys must use resolved workspace identity plus run directory name.

- [ ] Step 3: Write file resolver tests first.
  Cover workspace-relative paths, run-relative paths, absolute paths inside allowed roots, absolute paths outside allowed roots, `..` traversal before resolution, symlink escapes, broken symlinks, missing files, unreadable files, binary files, and large file truncation.

- [ ] Step 4: Implement `FileReferenceResolver`.
  Validate path components before realpath resolution. Resolve workspace-relative values against the selected workspace root and run-local values against the selected run root. Accept absolute paths only after realpath proves they remain under the selected workspace or selected run root, then convert them back into route-scoped file references.

- [ ] Step 5: Write preview tests first.
  Cover HTML escaping, JSON pretty-print as escaped text, decode-with-replacement, byte/char caps, binary detection, missing/unreadable/changed-during-read display states, `nosniff`, restrictive CSP metadata, and raw HTML/SVG defaulting to attachment-safe text/octet-stream.

- [ ] Step 6: Implement `PreviewRenderer`.
  Return a preview result object instead of HTML. Include file metadata, display text, truncation flags, binary/unsafe/missing/unreadable states, raw-download eligibility, and headers needed by route handlers.

- [ ] Step 7: Verify tranche.
  Run:
  ```bash
  pytest --collect-only tests/test_dashboard_scanner.py tests/test_dashboard_files.py tests/test_dashboard_preview.py -q
  pytest tests/test_dashboard_scanner.py tests/test_dashboard_files.py tests/test_dashboard_preview.py -v
  ```
  Expected: new tests collect and pass; no route code is needed yet.

- [ ] Step 8: Commit tranche.
  ```bash
  git add orchestrator/dashboard tests/test_dashboard_scanner.py tests/test_dashboard_files.py tests/test_dashboard_preview.py
  git commit -m "feat: add dashboard scan and file safety primitives"
  ```

## Tranche 3: Run Projection and Execution Cursor

**Purpose:** Build the dashboard read model that the index/detail pages will render.

**Files:**
- Create: `orchestrator/dashboard/projection.py`
- Create: `orchestrator/dashboard/cursor.py`
- Modify: `orchestrator/dashboard/models.py`
- Add: `tests/test_dashboard_projection.py`
- Add: `tests/test_dashboard_cursor.py`
- Reference: `orchestrator/workflow/state_projection.py`
- Reference: `specs/state.md`

- [ ] Step 1: Write run projection tests first.
  Cover workflow-aware projection, state-only fallback when `state.workflow_file` is missing/unreadable/unsafe, persisted/display status separation, stale heartbeat classification, state parse/read failures as index rows, workflow names, row freshness timestamps, failure summary extraction, prompt/stdout/stderr/provider-session/state-backup availability booleans, and no writes to `state.json`.

- [ ] Step 2: Implement `RunProjector`.
  Load state defensively. Load workflow metadata only when `state.workflow_file` resolves safely under the selected workspace. Reuse pure report projection where possible for current-step name/status semantics, then extend the dashboard model for row/detail fields and degraded state-only display.

- [ ] Step 3: Write execution cursor tests first.
  Cover top-level `current_step`, a running `call` step with matching `call_frames`, recursively nested call frames with cycle detection, `repeat_until` progress, `for_each` progress, finalization state, and bounded recursion guard behavior.

- [ ] Step 4: Implement `ExecutionCursorProjector`.
  Project state into display-only cursor nodes. Show top-level `current_step` first, traverse running call-frame state by frame ids, include callee workflow file/bound inputs/nested `current_step`, and report loop/finalization bookkeeping without emulating executor routing.

- [ ] Step 5: Add artifact lineage projection.
  In `RunProjector`, expose top-level and call-frame-local `artifact_versions` and `artifact_consumes`. Link artifact values through `FileReferenceResolver` only after validation; unsafe/missing artifacts become warnings/display states.

- [ ] Step 6: Verify tranche.
  Run:
  ```bash
  pytest --collect-only tests/test_dashboard_projection.py tests/test_dashboard_cursor.py -q
  pytest tests/test_dashboard_projection.py tests/test_dashboard_cursor.py tests/test_observability_report.py -k "snapshot or stale or current_step" -v
  ```
  Expected: new tests collect and pass; report projection tests continue to pass.

- [ ] Step 7: Commit tranche.
  ```bash
  git add orchestrator/dashboard/projection.py orchestrator/dashboard/cursor.py orchestrator/dashboard/models.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py
  git commit -m "feat: project dashboard run details"
  ```

## Tranche 4: Structured Operator Commands and CLI Parser

**Purpose:** Make copyable commands safe before the UI displays them, then wire the command into `orchestrate`.

**Files:**
- Create: `orchestrator/dashboard/commands.py`
- Create: `orchestrator/cli/commands/dashboard.py`
- Modify: `orchestrator/cli/main.py`
- Modify: `orchestrator/cli/commands/__init__.py`
- Add: `tests/test_dashboard_commands.py`
- Add: `tests/test_cli_dashboard_command.py`

- [ ] Step 1: Write command builder tests first.
  Cover report/resume `cwd`, argv vector, `shlex.quote` shell text, default use of run directory id, state/run-id mismatch warning with resume suppression, report command survival on mismatch when it clearly uses the run directory id, non-default runs-root flags, absence of tmux commands when metadata is untrusted, and no command text generated from unvalidated state paths.

- [ ] Step 2: Implement `CommandBuilder`.
  Store commands as `{cwd, argv, shell_text, warnings}`. Derive `cwd` only from the scanned workspace root. Default to `cd <workspace> && orchestrate report --run-id <run_dir>` and `cd <workspace> && orchestrate resume <run_dir>` semantics. Add `--runs-root`/`--state-dir` only when the run root is not the default workspace `.orchestrate/runs`.

- [ ] Step 3: Write CLI parser tests first.
  Verify `create_parser()` accepts repeated `--workspace`, default `--host 127.0.0.1`, optional `--port`, and rejects missing workspace before server startup.

- [ ] Step 4: Implement CLI command wiring.
  Add `dashboard` parser in `orchestrator/cli/main.py` and implement a command handler in `orchestrator/cli/commands/dashboard.py`. The handler should validate workspaces through `RunScanner`, instantiate the server, print the local URL, and block until interrupted.

- [ ] Step 5: Verify tranche.
  Run:
  ```bash
  pytest --collect-only tests/test_dashboard_commands.py tests/test_cli_dashboard_command.py -q
  pytest tests/test_dashboard_commands.py tests/test_cli_dashboard_command.py -v
  ```
  Expected: command builder and parser tests pass without starting a long-lived server.

- [ ] Step 6: Commit tranche.
  ```bash
  git add orchestrator/dashboard/commands.py orchestrator/cli/commands/dashboard.py orchestrator/cli/main.py orchestrator/cli/commands/__init__.py tests/test_dashboard_commands.py tests/test_cli_dashboard_command.py
  git commit -m "feat: wire dashboard CLI command"
  ```

## Tranche 5: Server Skeleton and Recent-Run Index

**Purpose:** Serve the first useful page after the read model and command model are in place.

**Files:**
- Create: `orchestrator/dashboard/server.py`
- Modify: `orchestrator/dashboard/models.py`
- Add: `tests/test_dashboard_server.py`

- [ ] Step 1: Write server route tests first.
  Cover `GET /` redirecting to `/runs`, `GET /runs` returning HTML, unknown routes returning 404, restrictive CSP headers, `X-Content-Type-Options: nosniff`, no raw absolute filesystem links, HTML escaping of state-derived fields, and query filters for workspace/status/workflow/recency/search.

- [ ] Step 2: Implement stdlib server skeleton.
  Use `ThreadingHTTPServer` plus a small request handler. Keep route dispatch explicit and testable, with no new web framework. Generate server-rendered HTML with `html.escape` for all file/state/workflow-derived text.

- [ ] Step 3: Implement recent-run index.
  Show workspace label/root, route key, run directory id, display `state.run_id`, workflow file/name, persisted status, display status/reason, cursor summary, started/updated/state-mtime/read-time/heartbeat freshness, failure summary, availability flags, and safe detail links.

- [ ] Step 4: Implement filters and manual refresh.
  Use query-string filters for workspace, persisted/display status, workflow, recency, and search. Add a normal link/button for manual refresh. Do not add background workers or persistent caches.

- [ ] Step 5: Verify tranche.
  Run:
  ```bash
  pytest --collect-only tests/test_dashboard_server.py -q
  pytest tests/test_dashboard_server.py -k "index or headers or filters" -v
  pytest tests/test_dashboard_scanner.py tests/test_dashboard_projection.py -v
  ```
  Expected: index routes pass and scanner/projection tests remain green.

- [ ] Step 6: Commit tranche.
  ```bash
  git add orchestrator/dashboard/server.py orchestrator/dashboard/models.py tests/test_dashboard_server.py
  git commit -m "feat: serve dashboard run index"
  ```

## Tranche 6: Run Detail, Step Detail, and State Preview Routes

**Purpose:** Expose the operational detail needed to understand where a run is active or why it failed.

**Files:**
- Modify: `orchestrator/dashboard/server.py`
- Modify: `orchestrator/dashboard/projection.py`
- Modify: `orchestrator/dashboard/cursor.py`
- Modify: `tests/test_dashboard_server.py`
- Modify: `tests/test_dashboard_projection.py`
- Modify: `tests/test_dashboard_cursor.py`

- [ ] Step 1: Write detail route tests first.
  Cover `GET /runs/<workspace_id>/<run_dir>`, mismatch warning display, active cursor display, step timeline, loop/call-frame/finalization sections, workflow inputs/outputs, run error context, artifact lineage, logs/provider/state-backup/common-artifact sections, and safe handling of missing workflow metadata.

- [ ] Step 2: Implement run detail page.
  Render summary, warnings, copyable command models, active cursor, step timeline, loop/call-frame/finalization state, workflow inputs/outputs, run-level error, artifact lineage, logs/provider sessions, state backups, and common artifact labels.

- [ ] Step 3: Write step detail route tests first.
  Cover `GET /runs/<workspace_id>/<run_dir>/steps/<step_ref>` for presentation-key and step-id-derived references, missing step display, escaped output/error/debug payloads, and safe links to known prompt/stdout/stderr/provider files.

- [ ] Step 4: Implement step detail page.
  Resolve `step_ref` from the projected timeline. Display step identity, kind, status, visits, duration, output preview, error/outcome/debug data, artifacts, provider-session summary, and safe file references.

- [ ] Step 5: Implement state preview route.
  Add `GET /runs/<workspace_id>/<run_dir>/state` as a capped JSON preview of the scanned `state.json` through `PreviewRenderer`. It must not use state-provided `run_root`.

- [ ] Step 6: Verify tranche.
  Run:
  ```bash
  pytest tests/test_dashboard_server.py -k "detail or step or state" -v
  pytest tests/test_dashboard_projection.py tests/test_dashboard_cursor.py -v
  ```
  Expected: detail/step/state routes pass and projection remains display-only.

- [ ] Step 7: Commit tranche.
  ```bash
  git add orchestrator/dashboard/server.py orchestrator/dashboard/projection.py orchestrator/dashboard/cursor.py tests/test_dashboard_server.py tests/test_dashboard_projection.py tests/test_dashboard_cursor.py
  git commit -m "feat: add dashboard run detail pages"
  ```

## Tranche 7: File Preview and Raw Download Routes

**Purpose:** Expose prompt/log/provider/artifact files only through the safe resolver and inert preview/download behavior.

**Files:**
- Modify: `orchestrator/dashboard/server.py`
- Modify: `orchestrator/dashboard/files.py`
- Modify: `orchestrator/dashboard/preview.py`
- Modify: `tests/test_dashboard_server.py`
- Modify: `tests/test_dashboard_files.py`
- Modify: `tests/test_dashboard_preview.py`

- [ ] Step 1: Write route tests first.
  Cover `GET /runs/<workspace_id>/<run_dir>/files/run/<path>`, `GET /runs/<workspace_id>/<run_dir>/files/workspace/<path>`, `?raw=1`, traversal rejection, symlink escape rejection, missing/unreadable/binary/large display states, HTML/SVG/script payload inertness, text/plain or octet-stream raw responses, `Content-Disposition: attachment` for raw, and `nosniff` on preview/raw responses.

- [ ] Step 2: Implement file preview routes.
  Route all file requests through `FileReferenceResolver` and `PreviewRenderer`. Render preview bodies only as escaped text inside dashboard chrome. Do not serve script-capable MIME types inline.

- [ ] Step 3: Link files from detail and step pages.
  Link prompt audits, stdout/stderr, provider-session metadata/transport logs, state backups, and artifact files only when the resolver returns a safe route reference. Label prompt audits as masked debug prompt files and stdout/stderr/provider transport as less-masked execution/provider logs.

- [ ] Step 4: Verify tranche.
  Run:
  ```bash
  pytest tests/test_dashboard_server.py -k "file or raw or preview or headers" -v
  pytest tests/test_dashboard_files.py tests/test_dashboard_preview.py -v
  ```
  Expected: unsafe file inputs are display states or 4xx responses, never uncaught 500s; script-like content is inert.

- [ ] Step 5: Commit tranche.
  ```bash
  git add orchestrator/dashboard/server.py orchestrator/dashboard/files.py orchestrator/dashboard/preview.py tests/test_dashboard_server.py tests/test_dashboard_files.py tests/test_dashboard_preview.py
  git commit -m "feat: add safe dashboard file previews"
  ```

## Tranche 8: Refresh Behavior, Docs Sweep, and Smoke Verification

**Purpose:** Finish the MVP with low-risk refresh support, doc consistency, and an operator smoke check.

**Files:**
- Modify: `orchestrator/dashboard/server.py`
- Modify: `specs/cli.md`
- Modify: `specs/observability.md`
- Modify: `specs/security.md`
- Optional modify: `docs/index.md` only if a new dashboard-specific docs page is added
- Modify/add tests as needed from prior tranches

- [ ] Step 1: Add auto-refresh as a page-level mechanism.
  Support an optional small query setting such as `?refresh=5` on index/detail pages using HTML meta refresh or minimal static JavaScript. Keep it off by default and do not add a watcher/background worker.

- [ ] Step 2: Test refresh behavior.
  Cover valid refresh intervals, invalid interval rejection/defaulting, escaping of query parameters, and unchanged CSP/script policy.

- [ ] Step 3: Perform docs sweep.
  Confirm `specs/cli.md`, `specs/observability.md`, and `specs/security.md` describe the final implemented behavior, especially read-only behavior, display-vs-persisted status, workspace trust boundaries, file-serving constraints, and local binding defaults.

- [ ] Step 4: Run focused unit/integration tests.
  Run:
  ```bash
  pytest --collect-only \
    tests/test_dashboard_scanner.py \
    tests/test_dashboard_projection.py \
    tests/test_dashboard_cursor.py \
    tests/test_dashboard_files.py \
    tests/test_dashboard_preview.py \
    tests/test_dashboard_commands.py \
    tests/test_dashboard_server.py \
    tests/test_cli_dashboard_command.py -q
  pytest \
    tests/test_dashboard_scanner.py \
    tests/test_dashboard_projection.py \
    tests/test_dashboard_cursor.py \
    tests/test_dashboard_files.py \
    tests/test_dashboard_preview.py \
    tests/test_dashboard_commands.py \
    tests/test_dashboard_server.py \
    tests/test_cli_dashboard_command.py \
    tests/test_observability_report.py \
    tests/test_cli_report_command.py -v
  ```
  Expected: collection succeeds and all targeted tests pass.

- [ ] Step 5: Run a local dashboard smoke check.
  Because the server is long-running, use the repo's `tmux` skill. Start the dashboard from the repo root on a free loopback port, request the index and one detail page with `curl` or `python -m urllib.request`, then stop the server.
  Example:
  ```bash
  python -m orchestrator dashboard --workspace "$(pwd)" --host 127.0.0.1 --port 8765
  curl -fsS http://127.0.0.1:8765/runs >/tmp/dashboard-runs.html
  ```
  Expected: the server prints a loopback URL, `/runs` returns HTML with restrictive headers, and at least one available run detail route returns non-empty escaped HTML when the workspace has runs.

- [ ] Step 6: Run final static checks.
  Run:
  ```bash
  git diff --check
  ```
  Expected: no whitespace errors.

- [ ] Step 7: Commit tranche.
  ```bash
  git add orchestrator/dashboard specs/cli.md specs/observability.md specs/security.md tests/test_dashboard_*.py tests/test_cli_dashboard_command.py
  git commit -m "feat: finish dashboard MVP"
  ```

## Final Acceptance Checklist

- [ ] `orchestrate dashboard --workspace <root>` starts a local loopback server and never requires workflow changes.
- [ ] The recent-run index handles multiple explicit workspaces, duplicate run ids, parse failures, stale display status, and state/run-directory id mismatches.
- [ ] Run detail shows active cursor, nested call frames, repeat-until/for-each progress, finalization, inputs/outputs, run errors, step timeline, and artifact lineage.
- [ ] File previews are capped, escaped, route-scoped, and safe for HTML/SVG/script-like payloads.
- [ ] Raw file responses default to safe download/text/octet-stream behavior with `nosniff`.
- [ ] Copyable commands are generated only from trusted scanned workspace/run metadata and are not executed by the dashboard.
- [ ] `state.json`, logs, artifacts, backups, workflow YAML, and workspace source files are never mutated by dashboard routes.
- [ ] Specs document the command and safety/read-only contract.
- [ ] Targeted dashboard/report tests and the local smoke check pass from the repo root with fresh output.
