# Backlog Item: Refactor Design/Plan/Implementation Stack To Consume Stdlib Review Loop

- Status: active
- Created on: 2026-06-05
- Priority: P2
- Plan: none yet

## Problem

`workflows/examples/design_plan_impl_review_stack_v2_call.orc` has frozen
historical contract and migration evidence for the `design_plan_impl_stack`
workflow family, but the authored `.orc` still carries older explicit
phase/review plumbing. It was written before the promoted `std/phase.orc`
review/revise-loop route was ready.

The current migration proves the direction but leaves ergonomics unrealized:

- the full `.orc` stack is about 512 physical LOC versus about 1,118 LOC in
  the frozen historical YAML stack;
- the frozen historical YAML contract included inline Bash/Python glue for
  path setup, findings extraction, routing, and finalization;
- the `.orc` version removes much of that low-level glue, but it still repeats
  review/fix/result projection structure that should now come from the stdlib
  review loop.

This item is about consuming the existing stdlib abstraction in a real migrated
workflow, not reimplementing the review loop or weakening the frozen historical
contract.

## Desired Outcome

Refactor the migrated `design_plan_impl_stack` `.orc` workflow family so design,
plan, and implementation review/fix phases call the promoted stdlib
review/revise-loop abstraction instead of spelling the loop and terminal
projection manually.

The refactor should make the authored workflow closer to the conceptual shape:

1. run the design phase through a reviewed provider loop;
2. run the plan phase through a reviewed provider loop;
3. run the implementation phase through a reviewed provider loop;
4. return typed phase outputs and review decisions;
5. preserve the behavior captured by the frozen historical YAML contract and
   evidence.

## Constraints

Do not:

- weaken the frozen historical YAML contract to make the `.orc` comparison
  easier;
- hide provider, prompt, artifact, path, or review effects from generated Core
  AST, Semantic IR, shared validation, source maps, or runtime state;
- reintroduce review-loop-specific Python compiler branches;
- treat generated debug YAML as semantic authority;
- reinterpret the historical migration evidence as proving artifact bytes that
  were not retained.

The stdlib loop may be used only through the promoted route. If the workflow
needs a missing stdlib helper around reviewed provider phases, record that as a
follow-on gap rather than rebuilding the old bridge in the workflow.

## Suggested Implementation Direction

1. Inventory the current `.orc` stack and identify duplicated review/fix
   structure in:
   - `workflows/examples/design_plan_impl_review_stack_v2_call.orc`;
   - `workflows/library/tracked_design_phase.orc`;
   - `workflows/library/tracked_plan_phase.orc`;
   - `workflows/library/design_plan_impl_implementation_phase.orc`.
2. Replace manual review-loop/projection code with calls to the stdlib
   review/revise-loop component where the current promoted route supports it.
3. Keep caller-specific phase result construction outside the stdlib loop when
   required by the current `ReviewLoopResult` contract.
4. Preserve prompt/provider extern bindings and artifact targets.
5. Validate `design_plan_impl_stack` against its frozen historical contract and
   evidence; historical artifact byte equality is not rerun or newly asserted
   after YAML retirement.
6. Record authored LOC before/after and classify remaining verbosity as:
   semantic declaration, migration parity requirement, or missing stdlib/
   frontend ergonomics.

## Acceptance Criteria

- The refactored `.orc` stack compiles and lowers through the promoted stdlib
  review-loop route.
- The stack does not use legacy review-loop bridge operands or Python-owned
  review-loop specialization.
- Generated Core AST, Semantic IR, source maps, and runtime artifacts still
  expose provider effects, review/fix effects, artifacts, and phase outputs.
- The frozen historical migration result for `design_plan_impl_stack` remains
  `non_regressive=true`.
- Output contract parity, terminal-state parity, artifact parity, and
  resume/reuse parity remain consistent with the frozen historical contract and
  evidence; historical artifact byte equality is not rerun.
- Authored LOC before/after is reported for the top-level `.orc`, library
  `.orc` phases, YAML primary, and YAML phase libraries.
- Remaining verbosity is documented, with follow-on backlog items for missing
  stdlib helpers rather than ad hoc local workarounds.

## Related Context

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/backlog/active/2026-05-28-lisp-migrate-key-workflows.md`
- `docs/backlog/active/2026-05-29-workflow-lisp-kiss-workflow-ergonomics.md`
