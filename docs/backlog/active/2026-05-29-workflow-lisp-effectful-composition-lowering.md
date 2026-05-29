# Backlog Item: Fix Workflow Lisp Effectful Composition And Reusable Lowering Boundaries

- Status: active
- Created on: 2026-05-29
- Plan: `docs/plans/2026-05-29-workflow-lisp-effectful-composition-lowering-fix-plan.md`

## Problem
Attempting to draft a small single-backlog-item Workflow Lisp `.orc` workflow
exposed several gaps between the accepted Workflow Lisp design and the current
Stage 3 lowering implementation.

The full design describes Workflow Lisp as a typed procedural authoring
language where `let*`, `match`, `with-phase`, provider results, review loops,
and workflow calls compose like ordinary typed workflow behavior. In practice,
several natural compositions either fail frontend lowering or compile only
before shared validation.

This blocks small, readable `.orc` workflows from becoming shared-validation
and runtime-ready replacements for existing YAML workflow stacks.

## Observed Failures
The attempted KISS backlog-item workflow uncovered these concrete boundaries:

- `match` cannot currently be used as an intermediate `let*` binding.
  Stage 3 lowering reports:
  `workflow_return_not_exportable: Stage 3 lowering does not support let* binding MatchExpr`.

- `with-phase` cannot currently be used as an intermediate `let*` binding.
  Stage 3 lowering reports:
  `workflow_return_not_exportable: Stage 3 lowering does not support let* binding WithPhaseExpr`.

- `match` arms are restricted to direct record expressions.
  Natural code that runs review/fix behavior only inside a proven successful
  variant branch is rejected with:
  `workflow_return_not_exportable: Stage 3 lowering requires match arms to return record expressions`.

- Same-file call bindings are too restrictive for locally constructed record
  values. Passing a freshly constructed record to a helper workflow can fail
  with:
  `workflow_signature_mismatch: Stage 3 lowering requires same-file call bindings to resolve to workflow inputs`.

- Reusable helper workflows that contain generated `review-revise-loop`
  `output_bundle.path` values fail shared validation because the generated
  write roots are not exposed as typed relpath inputs at the reusable workflow
  boundary.

- `run-provider-phase` can hit the same reusable-boundary problem by generating
  phase-owned bundle paths that shared validation rejects inside reusable
  workflow steps.

## Why This Matters
These are not just cosmetic parser limitations. They force authors away from
the intended high-level shape:

```lisp
(let* ((attempt (provider-result ...)))
  (match attempt
    ((COMPLETED completed)
     (review-revise-loop ...))
    ((BLOCKED blocked)
     (record-blocked ...))))
```

and toward either:

- YAML-shaped Lisp with many artificial helper workflows;
- compile-only examples that cannot pass shared validation;
- raw YAML for workflows that should be good Lisp migration candidates.

The result undermines the main frontend promise: typed procedural composition
over proven core workflow semantics.

## Desired Behavior
Workflow Lisp lowering should support effectful composition in the patterns the
language design already presents as normal authoring:

- `let*` bindings may bind effectful expressions whose outputs are later used
  by calls, `match`, `if`, and record construction.
- `match` arms may contain effectful workflow expressions, not only direct
  record literals, while preserving variant proof and runtime guards.
- `with-phase` should be usable as a scoped effectful expression in ordinary
  sequential composition.
- Locally constructed records should be passable to same-file workflow calls
  when every leaf can be lowered to a concrete input, artifact ref, or generated
  step output.
- Generated write roots for `review-revise-loop`, `run-provider-phase`, and
  related stdlib forms should cross reusable workflow boundaries as explicit
  typed relpath inputs or another shared-validation-approved mechanism.

## Acceptance Criteria
A fix should add at least one realistic `.orc` fixture or example that:

- models one selected backlog item or comparable unit of work;
- uses `provider-result` or `run-provider-phase` for a typed provider result;
- uses `match` over a provider-produced union;
- runs review/fix behavior only under the appropriate typed branch;
- uses `with-phase` inside normal sequential composition;
- passes frontend parse/typecheck/lowering;
- passes shared workflow validation;
- can be compiled through the CLI with emitted Core AST, Semantic IR, source
  map, and optional debug YAML;
- records any remaining runtime-only limitations explicitly.

The existing `workflows/examples/kiss_backlog_item.orc` compile example may be
used as a starting point, but the acceptance fixture should not be considered
complete until it passes shared validation.

## Suggested Implementation Direction
Investigate lowering in these areas first:

- `_lower_let_star_expr` and related local-value handling for effectful binding
  terminals;
- `_lower_match_expr` branch lowering so arms can lower general typed
  expressions while preserving branch output projection;
- call binding rendering for record expressions and step-backed local record
  values;
- stdlib lowering for `review-revise-loop` and `run-provider-phase`, especially
  generated bundle/write-root ownership across reusable workflow boundaries;
- source-map preservation for any newly generated steps or hidden inputs.

Do not weaken shared validation to make these examples pass. The frontend
should lower to Core AST that satisfies the existing reusable workflow boundary
rules.

## Related Context
Related docs and examples:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/lisp_workflow_drafting_guide.md`
- `workflows/examples/kiss_backlog_item.orc`
- `tests/test_workflow_lisp_examples.py`
- `docs/backlog/active/2026-05-28-lisp-migrate-key-workflows.md`

This item is a prerequisite for treating small `.orc` backlog-item workflows as
real runtime candidates rather than frontend-only compile examples.
