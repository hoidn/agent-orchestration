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

## Desired Outcome
Provide a local UI or CLI-served web app that can scan configured workspace roots and present:

- a recent-run index with run id, workspace, workflow file, status, current step, started/updated time, elapsed time, and failure summary
- filters for `running`, `failed`, `completed`, workflow name, workspace, and recency
- a run detail page with step timeline, `repeat_until` state, `for_each` state, call-frame state, finalization state, workflow inputs/outputs, and artifact lineage
- direct links to `logs/<Step>.prompt.txt`, `logs/<Step>.stdout`, `logs/<Step>.stderr`, and `provider_sessions/*`
- direct links to step artifact paths, `artifact_versions`, `artifact_consumes`, and common review artifacts such as design, plan, review JSON, open-findings, manifest, and checklist files when present
- copyable resume, report, and tmux attach/capture commands when enough metadata is available

## Design Constraints
Do not make workflow authors add dashboard-only fields to ordinary workflows.

Do not recompose prompts in the dashboard. Use the debug prompt audit files written by `--debug`, where known secrets have already been masked.

Do not serve arbitrary filesystem paths. Configure explicit workspace roots and only link files under those roots or under the selected run root.

Do not make control-flow decisions from dashboard summaries. The orchestrator should continue to derive control flow from workflow YAML and `state.json`.

Do not hard-code revision-study-specific behavior into the core. Revision-study affordances can be optional recognizers for common artifact names and JSON shapes.

## Candidate Implementation Shape
Start with a narrow local command, for example:

```bash
orchestrate dashboard \
  --workspace /home/ollie/Documents/agent-orchestration \
  --workspace /home/ollie/Documents/PtychoPINN \
  --workspace /home/ollie/Documents/ptychopinnpaper2
```

The first version can scan `.orchestrate/runs/*/state.json` on page load or maintain an in-memory/generated index such as `runs_index.json`. A persistent database should be deferred until there is evidence that filesystem scanning is too slow or that cross-workspace history needs richer querying.

Useful parsed surfaces:

- `state.json`: run identity, status, current step, step results, loop bookkeeping, call frames, workflow inputs/outputs, artifact lineage, finalization, and error objects
- `logs/`: prompt audit files, stdout, stderr, debug files, and orchestrator logs
- `provider_sessions/`: provider-session metadata and transport spools
- state backups: `state*.json` snapshots created by `--debug` or `--backup-state`
- common artifact files referenced from step artifacts or lineage entries

## Related Specs and Docs
Use these as starting points for the design:

- `docs/index.md`
- `specs/state.md`
- `specs/observability.md`
- `specs/cli.md`
- `specs/security.md`
- `docs/runtime_execution_lifecycle.md`

## Success Criteria
This item is satisfied when a follow-on design or plan specifies the dashboard route/page structure, run-indexing behavior, path-safety rules, parsed metadata model, and a minimal verification plan using at least one debug-enabled workflow run with populated prompt logs.
