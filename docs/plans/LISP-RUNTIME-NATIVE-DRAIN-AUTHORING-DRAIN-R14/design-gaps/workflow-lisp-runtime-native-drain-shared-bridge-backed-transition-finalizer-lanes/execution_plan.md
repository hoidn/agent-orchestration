# Workflow Lisp Runtime-Native Drain Shared Bridge-Backed Transition Finalizer Lanes Plan

> **For agentic workers:** implement this from the repo root. Do not create a
> worktree. Track tasks with the checkbox list below.

**Goal:** Repair the selected-item/finalizer route so ordinary `.orc`
composition stops transporting `run_state_path` or summary files as hidden
semantic carriers. The source route must compile and return typed terminal
values first; closeout artifacts may be refreshed later.

**Scope:** This plan owns the broken Design Delta source call graph and focused
checks for the selected gap. It does not own broad manifest/report
realignment, promotion evidence, parity closeout, or checked conformance
profile refresh unless one of those files is a direct runtime input to the
failing behavior.

## Earliest Causal Failure

Start from the current behavior failure:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Current failure: `work_item.orc` calls `project-selected-compat` without the
required `run_state_path` binding. The same route also has latent missing
bindings for `project-compat-run-state` in `work_item.orc`,
`stdlib_payloads.orc`, and `stdlib_adapters.orc`.

Do not fix this by re-threading `run_state_path` through high-level selected
item, loop state, or public/domain payloads. Do not begin by editing checked
JSON manifests, reports, conformance profiles, or generated summaries to match
the broken source.

## Tasks

- [ ] Reproduce the compile failure above and the focused feasibility test:

  ```bash
  python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_compiles_with_hidden_private_context -q
  ```

- [ ] Repair the `.orc` source call graph so `project-selected-compat` and
  every live `project-compat-run-state` caller are either removed from ordinary
  composition or fed only through an explicitly allowed boundary/bridge path.
  Expected source files include:

  - `workflows/library/lisp_frontend_design_delta/work_item.orc`
  - `workflows/library/lisp_frontend_design_delta/work_item_bridge_support.orc`
  - `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
  - `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
  - mirrored runtime fixtures only when their authoritative source changes

- [ ] Keep imported `finalize-selected-item` typed-first. Its typed terminal
  return must not depend on body-owned summary materialization, report parsing,
  pointer files, or compatibility bundle rereads. Publication, bridge
  generation, or resource transition effects may remain only as separately
  declared effects over an already-typed result.

- [ ] Add or update only focused tests that prove the changed behavior:

  - the parent drain compiles through the repaired call graph;
  - selected-item/finalizer routes no longer require ordinary internal
    `run_state_path` transport;
  - runtime fixture mirrors stay aligned when touched; and
  - one outside-use check passes if a shared production helper was changed.

- [ ] Run the focused verification set:

  ```bash
  python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_compiles_with_hidden_private_context -q
  python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
  ```

  Add the narrowest relevant runtime smoke if the compile succeeds and the
  touched behavior is runnable in the local environment.

## Acceptance

This implementation slice is complete when the repaired source route compiles,
focused behavior tests pass, and no ordinary internal composition path carries
`run_state_path` or summary paths merely to make typed terminal return work.

Stale manifests, checked conformance profiles, parity reports, progress
summaries, or inventory rows are closeout follow-up unless they are direct
runtime inputs or demonstrate the repaired source behavior is still wrong.
