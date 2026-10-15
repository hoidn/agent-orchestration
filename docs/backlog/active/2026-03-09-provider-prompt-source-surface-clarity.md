# Backlog Item: Workflow Authoring Surface Clarity

Current disposition: **open authoring-clarity intent; original DSL context historical.**

Separating business inputs, file dependencies, prompt sources and artifact lineage remains an open documentation intent. The kind/type and YAML-field incidents below are historical; no lint or runtime feature is selected.

Gate retained: Current scope must be evidenced before another cleanup plan; no lint/runtime feature selected.
This is a documentation disposition, not evidence of implementation completion
or authorization for new execution, spend, prompt edits or runtime work.
Current owners: [lisp workflow drafting guide](../../lisp_workflow_drafting_guide.md), [workflow lisp evaluated execution](../../design/workflow_lisp_evaluated_execution.md), [cli](../../../specs/cli.md), [workflow lisp provider prompt dependencies](../../design/workflow_lisp_provider_prompt_dependencies.md), [workflow lisp provider call policy](../../design/workflow_lisp_provider_call_policy.md).
[Backlog status inventory](../README.md).

Original proposal / historical checkpoint begins below. Its original status,
commands, measurements and tense are preserved; they do not override the current
scope notice.


- Status: active
- Created on: 2026-03-09
- Prior plans:
  - `docs/plans/2026-03-09-provider-prompt-source-surface-clarity-implementation-plan.md`
  - `docs/plans/2026-03-09-workflow-boundary-kind-type-redundancy-implementation-plan.md`
- Plan: none yet

## Scope
Resolve the current cluster of author-facing DSL surface confusions that are individually small but collectively noisy:
- provider-step prompt source fields such as `input_file` being mistaken for workflow business inputs
- redundant workflow-boundary `kind: relpath` plus `type: relpath` authoring
- unclear separation between workflow-boundary `inputs` / `outputs`, runtime data dependencies, provider prompt sources, and artifact contract surfaces

This merged item should produce one coherent docs/examples/lint cleanup pass instead of multiple overlapping backlog tickets that all touch the same authoring guidance and example workflows.

## Desired Outcome
This follow-on should leave the repo with:
- one clear vocabulary for workflow-boundary data, runtime dependencies, provider prompt sources, and artifact storage contracts
- canonical examples that use the preferred authoring forms
- compatibility-preserving lint or guidance for redundant/misleading surfaces
- no behavior change unless a later, separately reviewed follow-up introduces an additive alias or warning

## Likely Cleanup Areas
The follow-on plan should evaluate:
- docs/spec wording for `inputs`, `outputs`, `input_file`, `asset_file`, `depends_on`, and `consumes`
- whether boundary `kind: relpath` should be documented as redundant and linted
- whether prompt-source naming needs only docs or also an additive alias
- which workflow examples should be rewritten to reflect the preferred style
