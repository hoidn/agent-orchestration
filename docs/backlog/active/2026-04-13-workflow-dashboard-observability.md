# Backlog Item: Workflow Dashboard for Run Status and Artifacts

- Status: active
- Created on: 2026-04-13
- Plan: none yet

## Scope
Design and implement a local read-only dashboard for inspecting recent workflow runs across one or more workspaces.

The dashboard should make it easy to answer:

- which recent workflows are running, completed, or failed
- which step, loop iteration, or nested call frame is currently active
- what artifacts a run produced and consumed
- what debug-populated prompts were sent to providers
- what stdout, stderr, provider-session metadata, transport logs, and state backups exist for a run
- what workflow inputs, outputs, context, timing, and failure metadata were recorded

The source of truth should remain the existing run directory, especially `.orchestrate/runs/<run_id>/state.json`. The dashboard should index and link existing observability surfaces rather than introducing an independent run database or requiring workflow-specific dashboard fields.

The dashboard is an operator aid. It must not mutate workflow state, repair state, resume runs, delete artifacts, or infer control-flow decisions that the orchestrator would not make from workflow YAML and `state.json`.

## Desired Outcome
Provide a local CLI-served web dashboard that can scan configured workspace roots and present:

- a recent-run index with run id, workspace, workflow file, status, current step, started/updated time, elapsed time, and failure summary
- filters for `running`, `failed`, `completed`, workflow name, workspace, and recency
- a run detail page with a clear active execution cursor, step timeline, `repeat_until` state, `for_each` state, call-frame state, finalization state, workflow inputs/outputs, and artifact lineage
- direct links to `logs/<Step>.prompt.txt`, `logs/<Step>.stdout`, `logs/<Step>.stderr`, and `provider_sessions/*`
- direct links to step artifact paths, `artifact_versions`, `artifact_consumes`, and common review artifacts such as design, plan, review JSON, open-findings, manifest, and checklist files when present
- copyable resume, report, and tmux attach/capture commands when enough metadata is available
- visible live-run freshness metadata, including last read time, state `updated_at`, heartbeat age when present, and stale/unreadable state warnings

## Recommended MVP
Start with a read-only local web UI served by the existing CLI, for example:

```bash
orchestrate dashboard \
  --workspace /home/ollie/Documents/agent-orchestration \
  --workspace /home/ollie/Documents/PtychoPINN \
  --workspace /home/ollie/Documents/ptychopinnpaper2
```

The first version should focus on three user tasks:

- find the latest running, failed, or completed runs across configured workspaces
- inspect where one run is in the workflow, including nested loop/call context when present
- open the prompt, stdout/stderr, provider-session, state-backup, and artifact files needed to debug or resume the run

Use a server-rendered UI or minimal static JavaScript. Do not introduce a persistent database, SPA framework, or background worker until filesystem scanning or refresh behavior proves insufficient.

## Design Constraints
Do not make workflow authors add dashboard-only fields to ordinary workflows.

Do not recompose prompts in the dashboard. Use the debug prompt audit files written by `--debug`, where known secrets have already been masked.

Do not serve arbitrary filesystem paths. Configure explicit workspace roots and only link files under those roots or under the selected run root.

Treat every path read from `state.json`, step artifacts, lineage entries, debug payloads, logs, and provider-session metadata as untrusted input. Resolve symlinks before serving or linking a file, reject unresolved paths that escape configured roots, and derive the selected run root from the scanned `state.json` location rather than trusting any path recorded inside state.

Do not make control-flow decisions from dashboard summaries. The orchestrator should continue to derive control flow from workflow YAML and `state.json`.

Do not hard-code revision-study-specific behavior into the core. Revision-study affordances can be optional recognizers for common artifact names and JSON shapes.

Do not use the dashboard server as a control surface in the MVP. It may show copyable `orchestrate resume`, `orchestrate report`, and tmux commands, but it must not execute them.

## Candidate Implementation Shape
Start with a narrow local command:

- `orchestrate dashboard --workspace <root> [--workspace <root> ...] [--host 127.0.0.1] [--port <port>]`
- scan `.orchestrate/runs/*/state.json` on page load or refresh into an in-memory index
- key runs by `(workspace_root, run_id)` so cross-workspace run-id collisions cannot alias each other
- provide read-only routes for the recent-run index, run detail, JSON state preview, log/provider-session previews, and safe file downloads
- defer `runs_index.json` or any persistent database until there is evidence that filesystem scanning is too slow or that cross-workspace history needs richer querying

Useful internal units:

- run scanner: discovers candidate `state.json` files under configured workspaces and records scan errors without failing the whole dashboard
- status projector: derives display rows from state and workflow metadata without mutating `state.json`
- safe file reference resolver: converts state/log/artifact paths to route-scoped file references only after `realpath` validation
- preview renderer: serves capped text/JSON previews with file size, mtime, and "download/open raw file" affordances
- command builder: emits copyable commands only from trusted workspace/run metadata and best-effort tmux metadata

Useful parsed surfaces:

- `state.json`: run identity, status, current step, step results, loop bookkeeping, call frames, workflow inputs/outputs, artifact lineage, finalization, and error objects
- `logs/`: prompt audit files, stdout, stderr, debug files, and orchestrator logs
- `provider_sessions/`: provider-session metadata and transport spools
- state backups: `state*.json` snapshots created by `--debug` or `--backup-state`
- common artifact files referenced from step artifacts or lineage entries

## Read Model and State Projection
Reuse the existing status snapshot model where possible, especially the projection logic in `orchestrator/observability/report.py`. Do not call the mutating `report_workflow()` command path from the dashboard, because report rendering may reconcile stale running state by writing back to `state.json`.

The dashboard should have a pure read model that:

- loads `state.json` defensively and reports parse/read errors per run
- loads the workflow file only when it can be resolved safely under the workspace
- handles missing workflow files by falling back to raw state-driven display
- maps `current_step.step_id` and presentation keys when workflow projection metadata is available
- exposes nested context from `repeat_until`, `for_each`, and `call_frames` instead of showing only the outer call or loop frame
- marks display-derived status separately from persisted `state.status` when stale-heartbeat heuristics are used

## UX and Information Architecture
The MVP should use these pages or equivalent panels:

- Recent runs: table grouped/filterable by workspace and status, with active step, run age, heartbeat/staleness, failure summary, and debug-log availability.
- Run detail: top summary, active execution cursor, timeline/step list, loops and call frames, workflow inputs/outputs, finalization state, and run-level error context.
- Step detail: status, duration, visit count, output preview, artifacts, consumed/published lineage, prompt audit link when present, stdout/stderr links when present, provider-session metadata when present.
- Files/logs: capped preview by default, explicit raw/download action, size and mtime shown, missing/unreadable/unsafe files called out as normal states.

The dashboard should make absence visible without treating it as failure: prompt audits only exist for debug runs, stdout logs may be omitted for small outputs, stderr logs only exist when non-empty, and provider-session files only exist for session-enabled provider visits.

## Path Safety and File Serving
All file links should be dashboard routes backed by safe file references, not raw absolute filesystem links.

Required behavior:

- normalize configured workspace roots with symlinks resolved at startup
- derive a run root from each scanned `state.json` path and require it to be under one configured workspace root
- for artifact paths, first resolve workspace-relative values against that run's workspace; for run-local files, resolve against that run root
- reject absolute paths unless they resolve under an explicitly configured workspace root or the selected run root
- reject any path containing `..` before resolution and reject any resolved path that escapes the allowed roots
- treat broken symlinks, unreadable files, very large files, binary files, and racey files as display states rather than server failures
- label prompt audits as masked debug prompt files, and label stdout/stderr/provider transport logs as execution/provider logs that may not have the same masking guarantees

## Deferred Work
Defer these until the read-only MVP is useful:

- persistent database or cross-workspace search index
- dashboard-triggered resume/repair/clean operations
- auto-discovered tmux control beyond displaying copyable commands when launch metadata is available
- revision-study-specific pages; keep only optional common artifact recognizers in the MVP
- full-text search across prompt/log bodies
- rich artifact rendering beyond text and JSON preview
- prompt recomposition or prompt diffing

## Related Specs and Docs
Use these as starting points for the design:

- `docs/index.md`
- `specs/state.md`
- `specs/observability.md`
- `specs/cli.md`
- `specs/security.md`
- `docs/runtime_execution_lifecycle.md`

## Success Criteria
This item is satisfied when a follow-on design or plan specifies the dashboard route/page structure, run-indexing behavior, path-safety rules, parsed metadata model, read-only projection behavior, live-refresh behavior, and a minimal verification plan.

The verification plan should include:

- a debug-enabled run with populated prompt audit logs
- a non-debug run where prompt logs are absent
- a failed run with stderr or run-level error context
- a running or stale-running run with `current_step` and heartbeat metadata
- a nested loop or reusable-call run with `repeat_until`, `for_each`, or `call_frames`
- safe-file tests for symlink escape, absolute-path rejection, path traversal, missing files, large log previews, and state-provided paths that disagree with the scanned run root
- task-based usability checks: identify the active provider, find the latest failure and stderr tail, open a produced artifact, inspect consumed artifact lineage, and copy a correct report/resume command
