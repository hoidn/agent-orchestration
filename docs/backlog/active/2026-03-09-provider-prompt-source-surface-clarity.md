# Backlog Item: Workflow Authoring Surface Clarity

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
