# Workflow Lisp State Layout: Historical Sections

Status: **Historical.** Original sections retain their original tense, measurements
and acceptance language as evidence, not current authority or work selection.
Current owner: [workflow_lisp_state_layout.md](../../design/workflow_lisp_state_layout.md).

## Current Generated Path Roles

The current checkout adds these generated path roles:

- `PURE_PROJECTION_BUNDLE`
  Compiler/runtime-private bundle transport for a visible generated
  `pure_projection` step. These allocations are `PRIVATE_GENERATED`, resume at
  `STEP_VISIT` scope, and normally render through a generated managed
  write-root input rather than a user-authored path. Historical and noneligible
  projections retain that behavior. Under exact
  `result_persistence_profile: derived_pure_replay.v1`, an eligible projection
  retains the allocation only as compiled path carriage for executable identity
  and historical compatibility. That carriage does not authorize a runtime
  bundle read, reuse, or write. The runtime may derive the canonical path
  read-only when auditing that no forbidden persisted surface exists.
  The supported automatic creation policy selects the profile for typed public
  `.orc` run and force-restart roots plus fresh non-iterative typed Workflow
  Lisp children. Generic initialization remains explicit opt-in. Existing
  roots/frames, non-Workflow-Lisp callees, and iteration-owned frames retain
  historical bundle layout; a fresh eligible retry selects the profile without
  changing its failed predecessor.
- `ENTRYPOINT_MANAGED_WRITE_ROOT`
  Companion allocation that gives the generated write-root input a concrete
  run-scoped `.json` path under `.orchestrate/workflow_lisp/entry/...`.
- managed write-root input bridge
  The generated input name remains private runtime boundary surface. Loaded
  bundles must classify it as a managed write-root input rather than exposing
  it as a public authored workflow input.
- `RESOURCE_STATE`
  Runtime-owned private generated document path for native
  `Resource<TState>` backing. These allocations are `PRIVATE_GENERATED`,
  resume at `RUN` scope, and hold versioned typed state rather than public
  authored workflow inputs.
- `MATERIALIZED_VALUE_VIEW`
  Generated path role string for compiler/runtime-managed view files. Despite
  older design shorthand that said `materialized_view`, the shipped semantic
  role string remains `materialized_value_view`. These allocations are
  `PRIVATE_GENERATED` when the target is compiler-allocated, resume at
  `STEP_VISIT` scope, and hold deterministic rendered representations rather
  than semantic state.
- `TRANSITION_AUDIT`
  Runtime-owned private generated JSONL ledger path for append-only
  transition-audit rows. These allocations are `PRIVATE_GENERATED`, resume at
  `RUN` scope, and carry idempotency/replay evidence rather than user-authored
  artifacts.
