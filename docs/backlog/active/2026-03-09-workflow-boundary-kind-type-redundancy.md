# Backlog Item: Workflow Boundary `kind`/`type` Redundancy

- Status: retired
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-workflow-boundary-kind-type-redundancy-implementation-plan.md`

## Scope
Retired as a standalone backlog item and merged into [2026-03-09-provider-prompt-source-surface-clarity.md](2026-03-09-provider-prompt-source-surface-clarity.md), which now covers the broader workflow authoring surface clarity cleanup.

The underlying issue remains valid:
- workflow `inputs` / `outputs` commonly repeat `kind: relpath` and `type: relpath` even though the boundary contract is already effectively type-driven

But it is better handled as part of one combined docs/examples/lint pass covering boundary contracts, provider prompt-source terminology, and related author-facing DSL surface confusion.
