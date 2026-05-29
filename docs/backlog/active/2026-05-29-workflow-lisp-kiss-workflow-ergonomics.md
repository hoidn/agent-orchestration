# Backlog Item: Improve Workflow Lisp KISS Workflow Ergonomics

- Status: active
- Created on: 2026-05-29
- Plan: none yet

## Problem

`workflows/examples/kiss_backlog_item.orc` proves that a realistic single
backlog-item workflow can be authored in Workflow Lisp and compiled through the
runtime bridge, but the authored file is still more verbose than the conceptual
workflow warrants.

The current `.orc` source is 199 physical LOC for a flow that conceptually does:

1. draft a plan;
2. review/fix the plan;
3. implement the approved plan;
4. review/fix the implementation;
5. return a summary.

That is much smaller than the generated debug YAML projection, but the example
still exposes missing ergonomic layers in the frontend and standard library.

## Observed Friction

The current workflow repeats or exposes too much low-level plumbing:

- common enums, records, and path types are defined inline instead of imported
  from a small standard module;
- `PhaseCtx` values and review-context roots are threaded manually;
- plan and implementation review-loop result projection is duplicated;
- provider and prompt extern names remain low-level at the authoring surface;
- there is no standard single-backlog-item stack for the common
  plan/review/implement/review pattern;
- the example needs a source-local prompt layout workaround for runtime launch.

These are ergonomics issues, not reasons to weaken validation or hide effects.

## Current Defproc Boundary

Do not try to improve this example by blindly converting every helper workflow
to `defproc`.

A temporary audit showed that a simple provider-only helper can compile and
dry-run as `defproc`, but a reviewed phase helper using `with-phase`,
`review-revise-loop`, and `match` fan-in still fails current lowering. That
lowering work belongs to
`docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md`.

This ergonomics item may use `defproc` where the current compiler already
supports it, but reviewed phase helpers should remain `defworkflow` until that
lowering boundary is fixed.

## Desired Outcome

Make the KISS single-backlog-item workflow read like a small typed workflow
program, while preserving the current semantic guarantees:

- frontend source still lowers through Core AST, shared validation, Semantic
  IR, executable IR, and the existing runtime;
- generated YAML remains a debug projection only;
- provider calls, command calls, artifacts, state updates, and review loops
  remain visible in generated artifacts and source maps;
- prompt and provider extern bindings stay explicit enough to audit.

## Candidate Improvements

Prefer small, composable changes over a large new abstraction:

- Move common example-local types into an importable Workflow Lisp module.
- Add or document a standard `review-result->report` helper/procedure so
  review-loop fan-in is not repeated by every workflow.
- Add a small `single-backlog-item` or `run-reviewed-implementation` stdlib
  helper only if it removes real repeated structure without hiding effects.
- Reduce explicit `PhaseCtx` plumbing with a context-construction helper or
  documented input convention.
- Improve prompt extern ergonomics so checked-in `.orc` examples can run from
  their canonical source location without a source-local copy.
- Add a README-style comparison showing authored `.orc` LOC, generated debug
  YAML LOC, and which remaining lines are real semantic declarations versus
  removable plumbing.

## Non-Goals

This item should not:

- relax shared validation;
- make `.orc` generate YAML text as its semantic target;
- hide provider, command, artifact, or state effects behind macros;
- replace the existing KISS workflow with a magical one-line demo;
- broaden into full Workflow Lisp migration work;
- duplicate the effectful-composition lowering backlog item.

## Acceptance Criteria

This item is complete when the KISS workflow ergonomics have a measured,
reviewable improvement:

- `workflows/examples/kiss_backlog_item.orc` or a successor example remains
  shared-validation and dry-run compatible;
- common boilerplate is moved behind typed modules, helpers, or documented
  conventions without losing source maps or effect visibility;
- authored LOC and generated debug YAML LOC are recorded before and after;
- remaining verbosity is classified as either semantic declaration or
  known frontend/stdlib debt;
- the example can be launched from its checked-in source location, or the
  remaining prompt-extern/source-root limitation is captured as a separate
  backlog item;
- docs explain why the improved `.orc` is clearer than spelling the same
  workflow in YAML.

## Related Context

- `workflows/examples/kiss_backlog_item.orc`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/workflow_lisp_mvp_comparison.md`
- `docs/backlog/active/2026-05-29-workflow-lisp-effectful-composition-lowering.md`
- `docs/backlog/active/2026-05-28-lisp-migrate-key-workflows.md`
