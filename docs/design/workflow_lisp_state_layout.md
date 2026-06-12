# Workflow Lisp State Layout

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`StateLayout` defines how high-level contexts such as `RunCtx`, `PhaseCtx`,
`ItemCtx`, `DrainCtx`, `SelectionCtx`, and `RecoveryCtx` derive canonical
state paths, bundle paths, snapshot paths, temp paths, artifact roots, and
optional pointer paths.

The goal is to keep high-level frontend code from hand-managing state paths.

## Ownership Boundary

State layout owns:

- canonical bundle paths
- temporary bundle paths
- snapshot storage paths
- phase state namespaces
- item state namespaces
- drain state namespaces
- optional pointer materialization paths
- observability labels

State layout does not own:

- arbitrary child-process filesystem effects
- provider report content
- semantic artifact values
- queue movement semantics

## Contexts

Initial context types:

- `RunCtx`
- `PhaseCtx`
- `ItemCtx`
- `DrainCtx`
- `SelectionCtx` (reserved in this slice; no executable bootstrap yet)
- `RecoveryCtx` (reserved in this slice; no executable bootstrap yet)

Each context must map to a deterministic state namespace and artifact namespace.

Initial derivation responsibilities:

- `RunCtx`: run id plus run-scoped `state/` and `artifacts/` roots.
- `PhaseCtx`: nested run context plus phase-scoped `state/<phase>` and
  `artifacts/<phase>` roots.
- `ItemCtx`: nested run context plus item-scoped state/artifact namespaces and
  ledger location.
- `DrainCtx`: nested run context plus drain manifest/ledger state namespace.
- `SelectionCtx`: reserved for typed selection-state and bundle-view identity.
- `RecoveryCtx`: reserved for blocked/retry recovery state and reconciliation
  resources.

## Layout Rules

High-level forms should request semantic targets:

```text
phase-target(ctx, "execution-report")
phase-state(ctx, "implementation-result")
```

The layout layer derives concrete paths such as:

```text
state/phases/implementation/state.json
state/phases/implementation/snapshots/...
artifacts/work/implementation/execution-report.md
```

Exact paths are design choices, not frontend syntax.

## Generated Path Identity

Generated bundle and temporary paths are run-isolated by default unless an
authored contract explicitly requests a stable workspace artifact.

Stable semantic identity belongs to source maps, debug/explain projections, and
generated-name manifests. Concrete private write paths should include the
runtime run root or another collision-proof generated namespace so parallel or
repeated runs cannot write the same compiler-owned bundle by accident.

Resume must reconstruct the same concrete generated path for the same run and
call-frame/loop identity. A new run may receive a different private concrete
path while preserving the same semantic identity in debug output.

## Current Generated Path Roles

The current checkout adds these generated path roles:

- `PURE_PROJECTION_BUNDLE`
  Compiler/runtime-private bundle transport for a visible generated
  `pure_projection` step. These allocations are `PRIVATE_GENERATED`, resume at
  `STEP_VISIT` scope, and normally render through a generated managed
  write-root input rather than a user-authored path.
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

## Validation Responsibilities

State layout validation checks:

- generated paths are workspace-relative
- generated paths do not escape allowed roots
- canonical and temp paths are in the same directory when atomic rename is
  required
- pointer paths do not conflict with canonical artifact pointers
- generated names are stable across compile/resume where required
- generated private write paths are collision-proof across parallel/repeated
  runs unless explicitly authored as stable workspace artifacts
- `pure_projection_bundle` allocations round-trip through the same managed
  write-root bridge as other private generated result bundles
- `resource_state` and `transition_audit` allocations remain private generated
  state, not public boundary inputs or materialized view paths
- `materialized_value_view` allocations remain rendered views, not bridge
  backing or resume-authority state

## Required Invariants

- State layout has deterministic semantic identity.
- Private generated write paths are run-isolated by default.
- Generated pure projection bundles remain private transport, not public
  authored workflow inputs.
- Runtime-owned `resource_state` and `transition_audit` paths remain private
  generated state even when one transition still bridges to a legacy state
  document.
- State paths are source-mapped when generated from frontend forms.
- Private executable context bindings remain private workflow inputs; public
  authored boundaries expose only user-bindable inputs.
- Pointer files remain representations, not authority.

## Open Questions

- Which generated paths need stable public names for debugging versus private
  generated names.
