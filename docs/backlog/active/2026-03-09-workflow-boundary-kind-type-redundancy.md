# Backlog Item: Workflow Boundary `kind`/`type` Redundancy

Current disposition: **retired merged item.**

The item remains retired/merged into provider-prompt source clarity. The YAML redundancy account below is historical, not a separate open obligation.

Gate retained: Merged disposition unchanged.
This is a documentation disposition, not evidence of implementation completion
or authorization for new execution, spend, prompt edits or runtime work.
Current owners: [lisp workflow drafting guide](../../lisp_workflow_drafting_guide.md), [workflow lisp evaluated execution](../../design/workflow_lisp_evaluated_execution.md), [cli](../../../specs/cli.md).
[Backlog status inventory](../README.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


- Status: retired
- Created on: 2026-03-09
- Plan: `docs/plans/2026-03-09-workflow-boundary-kind-type-redundancy-implementation-plan.md`

## Scope
Retired as a standalone backlog item and merged into [2026-03-09-provider-prompt-source-surface-clarity.md](2026-03-09-provider-prompt-source-surface-clarity.md), which now covers the broader workflow authoring surface clarity cleanup.

The underlying issue remains valid:
- workflow `inputs` / `outputs` commonly repeat `kind: relpath` and `type: relpath` even though the boundary contract is already effectively type-driven

But it is better handled as part of one combined docs/examples/lint pass covering boundary contracts, provider prompt-source terminology, and related author-facing DSL surface confusion.
