# ADR: Workflow Dashboard for Run Status and Artifacts

**Status:** Proposed
**Date:** 2026-04-13
**Owners:** Orchestrator maintainers

## Context

The orchestrator already records the data operators need to debug most workflow runs. The authoritative record is the run directory, especially `.orchestrate/runs/<run_id>/state.json`, with supporting observability files under `logs/`, `provider_sessions/`, state backups, summaries, and workspace artifacts referenced by step outputs and artifact lineage.

That data is useful but spread across several files and state substructures. A failed or still-running workflow can require manual inspection of `current_step`, `steps`, `repeat_until`, `for_each`, `call_frames`, `artifact_versions`, prompt audit logs, stdout/stderr spill files, provider-session metadata, and workflow input/output bookkeeping. The existing `orchestrate report` command helps, but the CLI command path reconciles stale running state by writing back to `state.json`, and the report view is not intended to be a multi-workspace file browser.

The dashboard should be a local operator aid for finding recent runs, understanding where a run is active, and opening the existing debug artifacts needed to resume or investigate the run. It should not become a second execution engine, state database, workflow authoring surface, or repair tool.

## Problem and Scope

Build a local read-only web dashboard, served from the existing `orchestrate` CLI, that can inspect recent workflow runs across one or more explicit workspace roots.

In scope:

- a CLI command shaped as `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]`
- a recent-run index with workspace, run id, workflow file, persisted status, display-derived status, active step/cursor, started/updated time, elapsed time, freshness, and failure summary
- filtering by workspace, persisted/display status, workflow name, and recency
- a run detail view that shows the execution cursor, step timeline, loop state, call-frame state, finalization, workflow inputs/outputs, run error context, and artifact lineage
- step and file views for prompt audits, stdout/stderr, provider-session metadata and transport logs, state backups, and artifact files
- capped and escaped previews for text/JSON files, with missing/unreadable/unsafe/binary/large files presented as normal display states
- copyable `orchestrate resume`, `orchestrate report`, and best-effort tmux attach/capture commands when they can be built with explicit workspace execution semantics from trusted metadata
- targeted spec/docs updates for the new CLI surface and dashboard safety/read-only contract

Out of immediate scope:

- persistent indexing or an independent run database
- dashboard-triggered resume, repair, clean, delete, or workflow mutation operations
- prompt recomposition, prompt diffing, or full-text search across logs
- a SPA framework or new web framework dependency
- workflow-specific dashboard fields that authors must add to ordinary workflows

## Decision Summary

1. Add a local read-only dashboard command to the existing CLI. It binds to `127.0.0.1` by default and serves server-rendered HTML with minimal static JavaScript only where it directly improves filtering or refresh behavior.

2. Use configured workspace roots as the trust boundary. The scanner only discovers `.orchestrate/runs/*/state.json` under explicitly configured workspaces. Startup resolves workspace roots through symlinks, deduplicates them, and rejects non-directory roots.

3. Keep `state.json` and the run directory as the source of truth. The dashboard builds an in-memory read model on page load or refresh and does not persist a separate run index in the MVP.

4. Key runs by `(resolved_workspace_root, run_directory_name)`, not by `state.run_id` alone. `state.run_id` remains display metadata and can produce a mismatch warning, but it must not allow cross-workspace aliasing or state-provided path spoofing.

5. Split or reuse the pure projection logic from `orchestrator/observability/report.py`, but do not call the mutating `report_workflow()` CLI command path. The dashboard must keep persisted status and display-derived stale status separate.

6. Add a dashboard-specific safe file reference resolver. All file links are dashboard routes with workspace-relative or run-relative references after validation. The UI never links raw absolute filesystem paths.

7. Treat all paths found in state, logs, artifacts, lineage entries, debug payloads, and provider-session metadata as untrusted. The scanned state path determines the run root. State-provided `run_root` and artifact paths may be displayed as data, but they do not define what the server is allowed to serve.

8. Treat approved file contents as untrusted browser content. Preview pages render log, prompt, provider, state, and artifact content only as escaped text or escaped JSON inside dashboard chrome, and file responses use restrictive content headers so HTML/SVG/script payloads cannot execute in the dashboard origin.

9. Generate copyable commands only from a structured command model that includes the scanned workspace as the execution directory, a quoted shell representation, the argv vector, and explicit behavior for `state.run_id` mismatches.

10. Make absence visible without treating it as a failure. Prompt audit logs only exist for debug runs, stdout logs may be absent for small outputs, stderr logs may be absent when empty, and provider-session files only exist for session-enabled provider visits.

11. Defer persistence, background workers, full-text search, rich artifact rendering, and dashboard control actions until the read-only MVP proves that filesystem scanning and capped previews are insufficient.

## Core Contracts and Invariants

### Read-only behavior

The dashboard must not mutate workflow state or workspace artifacts.

Required invariant:

- no route writes to `state.json`, state backups, artifact files, logs, provider-session metadata, workflow YAML, or workspace source files
- no route invokes `orchestrate resume`, `orchestrate repair`, `orchestrate clean`, tmux, provider CLIs, shell commands, or child processes on behalf of the operator
- copyable commands are plain text generated from trusted workspace/run metadata and never executed by the dashboard
- stale-running heuristics may produce an advisory `display_status`, but they must not reconcile `state.status` or write `context.status_reconciled_*`

This is why the dashboard must not call `orchestrator.cli.commands.report.report_workflow()`. That command intentionally self-heals stale running status once it derives a terminal state.

### Source of truth

The source of truth remains the scanned run directory and `state.json`.

Required invariant:

- run root is derived from the real path of the discovered `state.json` parent directory
- workspace root is derived from the real path of the configured `--workspace` value
- workflow metadata may be loaded only when `state.workflow_file` resolves safely under the selected workspace
- missing or invalid workflow files fall back to a state-only display instead of failing the whole run detail page
- state parse/read failures become run index rows with error details when enough path metadata exists to identify the candidate run directory

### Run identity

Run ids are not globally unique across multiple workspaces.

Required invariant:

- dashboard routes include a workspace identity and a run directory identity
- the row key is `(workspace_root, run_dir_name)`
- if `state.run_id` differs from `run_dir_name`, the UI displays a warning and continues to use `run_dir_name` for routing and file scoping
- no state-provided `run_root` value can change the selected run root

### Projection semantics

Dashboard projection is for display only.

Required invariant:

- persisted `state.status` and advisory `display_status` are separate fields
- stale heartbeat logic reports a reason such as `stale_running_step_heartbeat_timeout` without mutating the run
- `current_step.step_id` is preferred over display name when workflow projection metadata is available
- presentation keys remain compatibility display keys; durable `step_id` values remain the lineage/resume identity
- the dashboard does not infer the next control-flow target or decide whether resume would skip, replay, or quarantine anything

The read model should reuse the existing report projection where it is pure, especially current-step name resolution and stale-heartbeat classification, but it must extend the model for dashboard needs rather than squeezing dashboard behavior through report rendering.

### Nested execution cursor

The active cursor must show nested context, not only the outer top-level step.

Required invariant:

- top-level `state.current_step` is shown first
- when the current top-level step is a `call`, matching running entries in `state.call_frames` are traversed to show callee workflow file, call frame id, bound inputs, nested `current_step`, and nested state
- nested `call_frames` are traversed recursively with a bounded recursion guard and cycle detection over frame ids
- `repeat_until` entries display current iteration, completed iterations, condition evaluation state, last condition result, and any loop-frame step result
- `for_each` entries display item count, current index, completed indices, and available summary/result state
- finalization state displays `body_status`, cleanup progress, workflow output export status, and failure details when present

This cursor is a state projection. It must not emulate the executor's routing logic.

### File serving

The dashboard may serve only files under the selected workspace or selected run root after validation.

Required invariant:

- configured workspaces are resolved through symlinks at startup
- scanned run roots are resolved through symlinks and must remain under one configured workspace root
- any path containing `..` as a path component is rejected before resolution
- workspace-relative values resolve against the selected workspace root
- run-local log/session/backup values resolve against the selected run root
- absolute paths are accepted only after realpath validation proves they are under the selected workspace root or selected run root, and they are converted back to a workspace-relative or run-relative dashboard reference before rendering a link
- broken symlinks, missing files, unreadable files, very large files, binary files, and files that change during read are display states, not 500 errors
- prompt audits are labeled as masked debug prompt files; stdout/stderr and provider transport logs are labeled as execution/provider logs that may not have the same masking guarantees

### Browser content isolation

Path validation is necessary but not sufficient. Every approved file body is still untrusted content that could contain HTML, SVG, JavaScript, control characters, or prompt-injected payloads.

Required invariant:

- preview rendering decodes text with replacement, applies a cap before display, and HTML-escapes all file-derived bytes or text before insertion into dashboard templates
- JSON previews may pretty-print parsed JSON, but the rendered JSON string is still escaped as text and never injected as trusted markup
- preview pages never render artifact, prompt, provider, transport, stdout, stderr, state, or backup content with `text/html`, `image/svg+xml`, script-capable MIME types, same-origin iframes, or "safe HTML" template bypasses
- preview and raw routes set `X-Content-Type-Options: nosniff`; dashboard HTML routes set a restrictive `Content-Security-Policy` with `default-src 'none'`, `base-uri 'none'`, `object-src 'none'`, and `frame-ancestors 'none'`, plus only the minimum `style-src`, `img-src`, and `script-src` allowances needed by the server-rendered UI
- `?raw=1` responses default to `Content-Disposition: attachment` and `Content-Type: text/plain; charset=utf-8` for textual files or `application/octet-stream` for non-text files; a future inline renderer must be explicitly sandboxed before serving script-capable types inline
- provider transport logs and stdout/stderr previews are labeled as less-masked execution/provider logs, but they still receive the same escaping and response-header protections as prompt audit previews

### Command generation

Copyable commands are operator conveniences, not dashboard actions. They must account for the current `resume` and `report` CLI behavior, which resolves the workspace and relative workflow file paths from `Path.cwd()`.

Required invariant:

- `CommandBuilder` stores commands as `{cwd, argv, shell_text, warnings}` and derives `cwd` only from the scanned workspace root
- POSIX shell text uses `shlex.quote` or an equivalent tested quoting routine for every dynamic token; if the platform cannot produce a safe shell representation, the UI shows `cwd` and argv tokens separately instead of a one-line shell command
- default commands use the run directory id, not `state.run_id`: `cd <quoted_workspace> && orchestrate report --run-id <quoted_run_dir>` and `cd <quoted_workspace> && orchestrate resume <quoted_run_dir>`
- if the dashboard later supports non-default run roots, report commands include `--runs-root <quoted_runs_root>` and resume commands include `--state-dir <quoted_runs_root>` when the run root is not `<workspace>/.orchestrate/runs`
- if `state.run_id` differs from the scanned run directory id, the UI warns about the mismatch, continues to route by run directory id, suppresses the resume command for that run, and may show a report command only when it clearly uses the run directory id
- tmux attach/capture commands are shown only when launch metadata is trusted and scoped to the same workspace/run; otherwise the tmux command section is absent rather than guessed

## Read Model

The MVP should introduce a small dashboard read model rather than binding HTML views directly to raw state dictionaries.

Suggested internal units:

- `RunScanner`: takes resolved workspace roots, scans `<workspace>/.orchestrate/runs/*/state.json`, records per-workspace and per-run errors, and returns candidate run records
- `RunProjector`: loads state defensively, optionally loads workflow metadata through `WorkflowLoader`, builds index rows and run detail models, and keeps persisted status separate from display-derived status
- `ExecutionCursorProjector`: projects top-level current step, nested call frames, repeat-until progress, for-each progress, and finalization state without deciding future control flow
- `FileReferenceResolver`: turns run-local and workspace-relative values into route-scoped file references only after validation
- `PreviewRenderer`: reads capped text/JSON previews and returns escaped display text, file metadata, truncation, binary/unreadable/missing/unsafe flags, content-isolation headers, and raw-download eligibility
- `CommandBuilder`: emits structured copyable commands using trusted workspace root, run directory id, shell-safe quoting, mismatch warnings, and optional tmux metadata when present

Minimum row fields:

- workspace label and resolved root
- run directory id and display `state.run_id`
- workflow file and workflow name when safely available
- persisted status from `state.status`
- display status and display status reason
- current cursor summary, including call-frame/nested step when present
- `started_at`, `updated_at`, state file mtime, dashboard read time, heartbeat time, and heartbeat age
- failure summary from run-level `state.error`, failed step error, or stderr tail metadata when present
- booleans for debug prompt availability, stdout/stderr availability, provider-session availability, and state backup availability

Minimum run detail fields:

- run summary, freshness, and warnings
- workflow inputs from `bound_inputs`
- workflow outputs from `workflow_outputs`
- finalization status
- run-level error object
- active execution cursor
- step timeline with status, kind, step id, visit counts, duration, output preview, error, artifacts, and debug metadata
- top-level and call-frame-local `artifact_versions` and `artifact_consumes`
- safe file references for logs, prompt audits, provider sessions, state backups, and artifact paths

The projector should support a workflow-aware path and a state-only path:

- workflow-aware path: use the loaded bundle projection to order steps, map `current_step.step_id` to presentation keys, and expose authored kind/consumes/expected outputs
- state-only path: use `state.steps` insertion order plus `current_step`, `artifact_versions`, and raw loop/call-frame dictionaries; mark ordering and kind metadata as degraded

## Routes and Information Architecture

The MVP should use server-rendered pages with query-string filters.

Recommended routes:

- `GET /` redirects to `/runs`
- `GET /runs` shows the recent-run index
- `GET /runs/<workspace_id>/<run_dir>` shows run detail
- `GET /runs/<workspace_id>/<run_dir>/steps/<step_ref>` shows one step detail, where `step_ref` is a URL-safe reference derived from presentation key or step id
- `GET /runs/<workspace_id>/<run_dir>/state` shows a capped JSON preview of the scanned `state.json`
- `GET /runs/<workspace_id>/<run_dir>/files/run/<path>` previews a run-relative file after validation
- `GET /runs/<workspace_id>/<run_dir>/files/workspace/<path>` previews a workspace-relative file after validation
- `GET /runs/<workspace_id>/<run_dir>/files/... ?raw=1` serves a raw/download response only after the same resolver approves the path and the response is forced to safe download/text semantics with `nosniff`

The recent-run index should support:

- workspace filter
- status filter using persisted or display status
- workflow filter
- recency filter
- search over run id/workflow file/failure summary
- manual refresh
- optional auto-refresh with a small query setting such as `?refresh=5` implemented by HTML meta refresh or minimal JavaScript polling

The run detail page should have panels or sections for:

- summary and copyable commands with explicit cwd and any mismatch warnings
- active execution cursor
- step timeline
- loop/call-frame/finalization state
- inputs and outputs
- artifact lineage
- logs and provider sessions
- state backups
- common artifacts

Common artifact recognition should be optional and label-only. The dashboard may highlight names such as `design_path`, `plan_path`, review JSON, open-findings files, manifests, and checklists when they are already present in step artifacts or lineage. It must not hard-code revision-study behavior into the core read model.

## Live Refresh and Freshness

The MVP should scan on page load and refresh rather than run a background watcher.

Required display fields:

- dashboard read time
- state file mtime
- `state.updated_at`
- `current_step.started_at`
- `current_step.last_heartbeat_at`
- heartbeat age when present
- stale-running reason when display status differs from persisted status
- scan/read/parse warnings

Use the existing stale-running timeout semantics from report projection as the initial default, currently 300 seconds, but label this as dashboard-derived freshness. The dashboard must not persist the derived result.

If filesystem scanning becomes too slow, the next step should be a bounded in-process cache keyed by workspace root and state file mtime. A persistent `runs_index.json`, SQLite database, or background worker should remain deferred until there is evidence that request-time scanning is not adequate.

## Internal Refactoring and Debt Paydown

Required before substantial UI work:

1. Extract or wrap pure report projection.

`orchestrator/observability/report.py` contains useful pure helpers for status snapshots, current-step name resolution, prompt audit discovery, output preview normalization, and stale-running classification. The dashboard should reuse those semantics, but it must not call `report_workflow()` because that command mutates stale running state.

The minimum refactor is to expose a pure snapshot/projection function that:

- accepts loaded workflow metadata when available
- supports a state-only fallback when workflow loading fails
- returns both `persisted_status` and `display_status`
- returns stale-status reasons without writing state
- can be reused by both `report` and `dashboard` over time

2. Add a safe file reference and content-isolation layer before any file preview route.

The file resolver and preview isolation headers are not optional infrastructure. Together they are the safety boundary for the dashboard. They should be implemented and tested before views expose state-provided artifact paths or file bodies.

3. Update normative docs in the same feature tranche.

Adding `orchestrate dashboard` changes the CLI contract and observability surface. At minimum, update `specs/cli.md` for the command, `specs/observability.md` for the read-only dashboard behavior, and `specs/security.md` or a linked subsection for dashboard file-serving rules.

Not required before MVP feature work:

- state schema changes
- executor control-flow refactors
- loader or IR rewrites
- workflow YAML changes
- a persistent index
- a new web framework or templating dependency

Possible follow-on debt, not MVP prerequisites:

- a shared `RunSnapshot` model used by both `report` and `dashboard`
- richer structured artifact descriptors for common review artifacts
- route-level JSON endpoints for a future richer UI
- configurable workspace aliases loaded from a config file

## Non-Goals

- Do not make workflow authors add dashboard-only fields.
- Do not recompose prompts.
- Do not treat prompt audit absence as failure.
- Do not serve arbitrary filesystem paths.
- Do not trust paths recorded inside `state.json` as authority.
- Do not render untrusted logs, prompts, provider transport files, state backups, artifacts, HTML, or SVG as executable browser content in the dashboard origin.
- Do not mutate workflow state or repair stale runs.
- Do not execute resume/report/tmux commands from the dashboard.
- Do not infer or alter orchestrator control-flow decisions.
- Do not introduce a persistent database in the MVP.
- Do not add a SPA framework or broad frontend build pipeline.
- Do not add revision-study-specific pages to the core dashboard.
- Do not implement full-text log search, rich binary artifact rendering, or prompt diffing in the MVP.
- Do not support non-local, multi-user, authenticated hosting in the MVP. Binding beyond loopback should be an explicit operator choice and should not imply production security.

## Sequencing Constraints

1. Land the pure read model and file resolver first.

The dashboard should start from tested scan/projection/path-safety primitives. UI routes should not directly parse arbitrary state paths.

2. Add CLI and server skeleton second.

Introduce `orchestrate dashboard` with workspace validation, local binding defaults, route dispatch, and a basic index route. Keep the server on the standard library stack unless a dependency is justified by concrete complexity.

3. Build the recent-run index before detailed file previews.

The index validates cross-workspace scan behavior, run keying, stale display status, and degraded parse-error rows before the UI links deeper observability files.

4. Add run detail and step detail after projection is stable.

The run detail should expose cursor, timeline, loop/call-frame state, finalization, inputs/outputs, and artifact lineage before adding recognizers for common review artifacts.

5. Add file previews only through safe file references and escaped preview rendering.

Prompt/stdout/stderr/provider-session/state-backup/artifact links should all share the same resolver, preview renderer, `nosniff` behavior, and restrictive CSP/header policy.

6. Add copyable commands only after the command builder can prove workspace semantics.

The first command UI should show structured `cwd` plus command text built from trusted workspace and run-directory metadata. If a run has a `state.run_id` mismatch or command quoting cannot be produced safely, omit the unsafe command instead of guessing.

7. Add refresh behavior last.

Manual refresh is enough for the first route smoke. Auto-refresh should remain a thin page-level mechanism and should not add a background worker.

8. Update specs and docs before declaring the feature complete.

The CLI command and read-only safety contract should be documented alongside implementation, not left as an implicit behavior.

## Verification Plan

Unit tests should cover:

- workspace scanning with zero runs, multiple workspaces, duplicate run ids across workspaces, unreadable or malformed `state.json`, and state/run-directory id mismatches
- projection with workflow metadata, projection fallback when workflow YAML is missing, persisted/display status separation, stale heartbeat classification, and no writes to `state.json`
- active cursor projection for top-level current step, nested `call_frames`, `repeat_until`, `for_each`, and finalization
- artifact lineage rendering from `steps.*.artifacts`, `artifact_versions`, and `artifact_consumes`
- safe file resolver behavior for workspace-relative paths, run-relative paths, absolute paths inside allowed roots, absolute paths outside allowed roots, path traversal, symlink escape, broken symlink, missing file, unreadable file, binary file, and large preview truncation
- preview content isolation for HTML escaping, JSON escaping, `Content-Type`, `Content-Disposition`, `X-Content-Type-Options: nosniff`, restrictive CSP, raw HTML/SVG download behavior, and malicious prompt/log/artifact bodies that must not execute script or fetch other dashboard routes
- command builder output for report/resume cwd, shell quoting, run directory id selection, `state.run_id` mismatch behavior, non-default runs root flags, and absent tmux metadata
- CLI parser wiring for `orchestrate dashboard --workspace ... --host ... --port ...`

Integration or smoke checks should include representative run fixtures or real runs for:

- a debug-enabled run with `logs/<Step>.prompt.txt`
- a non-debug run where prompt logs are absent
- a failed run with stderr or run-level error context
- a running or stale-running run with `current_step` and heartbeat metadata
- a nested loop or reusable-call run with `repeat_until`, `for_each`, or `call_frames`
- provider-session metadata and transport log links when present
- malicious HTML/SVG/script-like payloads in prompt audits, stderr/stdout, provider transport logs, and artifacts to verify they render or download as inert text/content

Task-based usability checks should verify that an operator can:

- identify the active provider or nested active step for a run
- find the latest failure and stderr tail
- open a produced artifact
- inspect consumed artifact lineage
- find prompt audit availability and understand when it is absent
- copy correct `orchestrate report` and `orchestrate resume` commands and see the workspace cwd that must be used to run them

Because this feature adds a CLI command and dashboard routes, the implementation tranche should run targeted pytest selectors for the new dashboard modules and CLI parser tests. If new tests are added, run `pytest --collect-only` on those modules. A final smoke should start the dashboard locally against at least one workspace fixture or the repo workspace and request the index plus one run detail page.
