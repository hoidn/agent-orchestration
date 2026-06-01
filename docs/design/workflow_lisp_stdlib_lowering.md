# Workflow Lisp Frontend Standard Library Lowering

Status: draft internal design  
Depends on: `docs/design/workflow_lisp_core_stmt_taxonomy.md`,
`docs/design/workflow_lisp_semantic_workflow_ir.md`,
`docs/design/workflow_command_adapter_contract.md`

## Purpose

This document defines the contract for high-level Lisp library forms to compile
to Core AST and Semantic IR without hiding unresolved semantics.

The default implementation path is ordinary `.orc` stdlib code compiled through
the shared effectful composition model. A form should receive bespoke compiler
lowering only when it is explicitly accepted as a primitive rather than as a
library abstraction.

Each standard-library form needs an exact generated-shape contract before it can
be implemented or promoted.

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

## Adapter Backends

Some standard-library forms may initially lower to certified command adapters
when the runtime does not yet expose a native effect.

Allowed examples:

- `resource-transition` lowering to a queue-move adapter with typed outputs;
- `command-result` invoking a deterministic validator;
- temporary `resume-or-start` validation behind an adapter while canonical
  reusable-state validation is being specified.

Adapter-backed lowering must still expose:

- typed inputs and outputs;
- declared effects;
- source-map links from the high-level form to the adapter invocation;
- fixture and negative-test obligations;
- validate-before-publication behavior for structured outputs.

Inline command text is not an acceptable lowering target for standard-library
forms.

## Runtime-Native Promotion

Do not promote every adapter into a runtime primitive. Promote only when the
form needs runtime-level properties that an adapter cannot provide well:

- atomic multi-file/resource transition semantics;
- resumability tied to runtime state checkpoints;
- source-map and observability fidelity beyond command logs;
- path-safety guarantees that must be enforced before command launch;
- proof, effect, or reference information needed by Semantic IR.

`resume-or-start` also requires a canonical reusable-state validation contract:
the prior-state schema, reusable terminal variants, artifact-existence checks,
failure modes, and normalization between resumed and fresh branches must be
specified before the form can claim runtime-integrated semantics.

## Required Invariants

- A stdlib form must reduce a recurring correctness burden, not only reduce
  punctuation.
- Every generated effect is visible in the effect graph.
- Every generated statement is source-mapped.
- Command-backed forms use certified command adapters, not hidden inline glue.
- Provider decisions become structured state, with reports as views.
- If no faithful lowering exists, the form is not implementation-ready.

## Open Questions

- Whether `resource-transition` starts as a certified command adapter or waits
  for runtime-native support.
- Whether stdlib `review-revise-loop` can be expressed through current
  `repeat_until` without needing new terminal-result semantics.
- Whether `resume-or-start` needs a new canonical-state validation primitive.
