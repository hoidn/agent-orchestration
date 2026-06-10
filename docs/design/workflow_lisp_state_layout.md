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

## Required Invariants

- State layout has deterministic semantic identity.
- Private generated write paths are run-isolated by default.
- State paths are source-mapped when generated from frontend forms.
- Private executable context bindings remain private workflow inputs; public
  authored boundaries expose only user-bindable inputs.
- Pointer files remain representations, not authority.

## Open Questions

- Which generated paths need stable public names for debugging versus private
  generated names.
