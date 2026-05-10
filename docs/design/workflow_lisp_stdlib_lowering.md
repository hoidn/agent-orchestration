# Workflow Lisp Frontend Standard Library Lowering

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_stmt_taxonomy.md`, `docs/design/workflow_lisp_semantic_workflow_ir.md`

## Purpose

`FrontendStdlibLowering` defines how high-level Lisp library forms lower to
Core AST and Semantic IR without hiding unresolved semantics.

Each standard-library form needs an exact lowering contract before it can be
implemented.

## Required Forms

Initial forms:

- `provider-result`
- `command-result`
- `produce-one-of`
- `run-provider-phase`
- `review-revise-loop`
- `resume-or-start`
- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`

## Lowering Contract Template

Each form must specify:

- inputs and return type
- effects
- generated Core statements
- generated Semantic IR facts
- state layout use
- reference catalog entries
- proof graph entries
- source-map behavior
- runtime backend requirements
- negative validation cases

## Example: `produce-one-of`

Expected lowering:

```text
CorePreSnapshot
CoreProducerStep
CoreSelectVariantOutput
```

Semantic requirements:

- snapshot candidates match union variants
- exactly one candidate changes
- selected bundle validates before commit
- selected variant fields are availability-scoped
- mtime is debug metadata only

## Example: `backlog-drain`

Expected lowering:

```text
bounded loop
call selector
match selection result
call selected-item runner or gap drafter
normalize terminal DrainResult
```

Semantic requirements:

- workflow refs are signature-checked
- selected item results are typed unions
- gap handling cannot hide an empty active queue as success unless the
  `DrainResult` variant says so
- loop state is explicit and bounded

## Required Invariants

- A stdlib form must reduce a recurring correctness burden, not only reduce
  punctuation.
- Every generated effect is visible in the effect graph.
- Every generated statement is source-mapped.
- If no faithful lowering exists, the form is not implementation-ready.

## Open Questions

- Whether `resource-transition` starts as a certified command adapter or waits
  for runtime-native support.
- Whether `review-revise-loop` can lower to current `repeat_until` without
  needing new terminal-result semantics.
- Whether `resume-or-start` needs a new canonical-state validation primitive.
