# Lisp ProcRef Partial Application Work Instructions

Status: active instructions for the ProcRef delta drain

These instructions are procedural guidance for the focused ProcRef / `bind-proc`
implementation tranche. They are not a replacement for the parent Workflow Lisp
frontend specification.

## Target And Baseline

Active target:

- `docs/design/workflow_lisp_proc_refs_partial_application.md`

Baseline contract:

- `docs/design/workflow_lisp_frontend_specification.md`

Implement the target delta while preserving the baseline frontend contract. If
the target and baseline conflict, return `BLOCKED` or draft the smallest design
gap that resolves the conflict before implementation.

## Selection Guidance

The selector should treat the ProcRef delta as the active scope. It should draft
design gaps or select work only for concrete obligations needed to implement:

- `ProcRef[...]` type parsing and type references;
- `(proc-ref ...)` literals;
- `bind-proc` keyword-only partial application;
- residual signature computation;
- procedure reference resolution through module/procedure catalogs;
- specialization before lowering;
- source-map and diagnostic behavior;
- effect-summary preservation;
- runtime-transport rejection;
- valid and invalid fixtures.

Do not reopen unrelated full-frontend work unless it is necessary to keep the
ProcRef delta compatible with the baseline contract.

## Implementation Guidance

Each implementation item should leave the compiler in a feature-expansion-ready
state. Refactoring may be selected only when it is required to implement the
delta cleanly, and it must not be selected twice in a row.

If a refactor changes current architecture that future workflow runs rely on,
update the corresponding current design documentation in the same item. Do not
rewrite historical per-gap implementation architecture documents.

## Completion Target

The drain is complete when the ProcRef delta has static-code evidence,
fixtures/tests, diagnostics, lowering behavior, source-map behavior, and docs
alignment matching the acceptance tests in the target design.
