# Backlog Item: Remediate Review-Loop Compiler Specialization Debt

- Status: active
- Created on: 2026-06-02
- Priority: P2
- Design: `docs/design/workflow_lisp_structural_parametric_constraints.md`
- Plan: none yet

## Problem

Workflow Lisp currently exposes `review-revise-loop` through `std/phase.orc`,
but the implementation is still materially compiler-special:

- `std/phase.orc` expands the public macro through
  `__stdlib-specialization__ phase-review-loop`;
- `expressions.py`, `typecheck.py`, `compiler.py`, and `lowering.py` still
  contain review-loop-specific parsing, contract validation, helper generation,
  command-boundary augmentation, and output-contract handling;
- `typecheck.py` carries most of the domain-specific review-loop semantics,
  including terminal variants, required fields, findings validation, generated
  helper names, and loop-state construction.

That path is acceptable as a temporary stdlib-internal intrinsic, but it should
not be treated as ordinary `.orc` stdlib composition. It weakens the architecture
boundary because future review-loop changes require Python compiler edits
instead of ordinary `.orc` library/type changes.

## Desired Outcome

Move `review-revise-loop` from a domain-specific compiler branch to a generic
imported-stdlib specialization route:

- the public `review-revise-loop` authoring surface remains stable;
- imported `std/phase` source remains the author-facing surface;
- specialization is generic and can be used by arbitrary `.orc` stdlib
  abstractions, not only review loops;
- after specialization, lowering sees ordinary generated helpers, calls,
  `loop/recur`, `provider-result`, `command-result`, `match`, records, unions,
  and projections;
- source maps preserve call site, imported stdlib source, specialization, and
  generated helper provenance;
- managed write roots remain compiler-owned and off public workflow inputs.

The type-system direction is structural parametric constraints: caller-specific
record and union shapes should be declared as `.orc` constraints and checked by
the type system, then specialized into concrete helpers before lowering. The
remediation should follow
`docs/design/workflow_lisp_structural_parametric_constraints.md` rather than
adding another review-loop-specific macro or compiler hook.

## Non-Goals

This item should not:

- block current migration parity work that merely consumes the existing
  `review-revise-loop` route;
- remove `review-revise-loop` authoring support before the generic route exists;
- introduce runtime closures, runtime procedure values, provider refs, or prompt
  refs;
- add inline Python/shell glue, report parsing, or pointer-as-state behavior;
- redesign findings, `resume-or-start`, command-result bundle paths, or
  migration promotion reporting.

## Suggested Implementation Direction

Use a strangler refactor:

1. Classify `review-revise-loop` as temporary compiler specialization debt, not
   as proof of ordinary stdlib composition.
2. Add guard tests that identify current production references in
   `expressions.py`, `typecheck.py`, `compiler.py`, and `lowering.py`.
3. Introduce a generic specialization request/carrier for imported `.orc`
   stdlib forms.
4. Move review/fix hook specialization through compile-time `ProcRef` helpers
   and ordinary generated definitions.
5. Add generic `loop/recur` terminal/exhaustion projection sufficient for the
   current review-loop behavior.
6. Remove the review-loop-specific expression/typecheck/lowering branches once
   the imported route passes parity fixtures.

## Acceptance Criteria

- `review-revise-loop` may appear in `std/phase.orc`, tests, docs, and
  compatibility notes, but not as a semantic branch in the core compiler.
- The production compiler path no longer contains dedicated
  `ReviewReviseLoopExpr`, `_elaborate_*review_loop*`,
  `_validate_review_loop_result_contract`, or lowering branches keyed to the
  literal `review-revise-loop` / `phase-review-loop` domain concept.
- Existing public `review-revise-loop` `.orc` fixtures still parse, typecheck,
  lower, and validate.
- At least one non-review-loop imported stdlib fixture proves the same generic
  specialization machinery works for arbitrary effectful `.orc` composition.
- Source-map/build artifacts identify the authored call site, imported stdlib
  source, generated helpers, and generated write-root provenance.
- Existing migration parity consumers can continue using review loops without
  public hidden write-root inputs or runtime callable values.

## Related Context

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
