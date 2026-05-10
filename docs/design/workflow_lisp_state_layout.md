# Workflow Lisp State Layout

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`StateLayout` defines how high-level contexts such as `RunCtx`, `PhaseCtx`,
`ItemCtx`, and `DrainCtx` derive canonical state paths, bundle paths, snapshot
paths, temp paths, artifact roots, and optional pointer paths.

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

Each context must map to a deterministic state namespace and artifact namespace.

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

## Validation Responsibilities

State layout validation checks:

- generated paths are workspace-relative
- generated paths do not escape allowed roots
- canonical and temp paths are in the same directory when atomic rename is
  required
- pointer paths do not conflict with canonical artifact pointers
- generated names are stable across compile/resume where required

## Required Invariants

- State layout is deterministic.
- State paths are source-mapped when generated from frontend forms.
- Pointer files remain representations, not authority.

## Open Questions

- Whether state layout is compile-time only or may depend on runtime run id.
- Which generated paths need stable public names for debugging versus private
  generated names.
