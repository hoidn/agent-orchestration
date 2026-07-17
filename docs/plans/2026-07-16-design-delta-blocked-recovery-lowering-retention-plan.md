# Design Delta Blocked-Recovery Lowering-Retention Plan

> **For agentic workers:** This is a bounded Task 5 fail-closed decision. Do
> not change production source, its runtime mirror, YAML, compiler/runtime
> code, checkpoint baselines, or run state from this plan.

**Status:** Complete by two bounded retention grounds: exported-entry strict
compatibility retains the classifier call, and a compiler stop retains the five
blocked-finalizer calls. All six rows remain workflow/effect-adapter boundaries.
Phase orchestration (nine calls) is the current Task 5 subfamily; Task 5 remains
open and its order does not change.

**Goal:** Classify the six blocked recovery/finalization calls against their
actual boundaries: one exported classifier and five blocked-finalizer calls.

**Architecture:** Keep the production `work_item.orc` at its real path and use
the existing fail-closed, same-path source override to compile retained bytes
and a deterministic minimal inline conversion of only the blocked finalizer.
The classifier is not part of that hypothetical: the compiled export graph
already makes it a strict-compatibility public boundary.

**Approach tradeoff:** This keeps two internal helpers and six call sites as
workflow boundaries. It avoids inventing a type-erasing shim or changing
shared lowering, but leaves later phase-orchestration work unable to assume
that all adjacent blocked-recovery helpers are procedures.

## Exact boundary

- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:classify-blocked-implementation-recovery:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-blocked-implementation:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-blocked-implementation:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-blocked-implementation:3`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-blocked-implementation:4`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-blocked-implementation:5`

## Execution plan

- [x] Add a structural/current-inventory test that requires the two callees to
  remain `defworkflow`, exactly six authored workflow-call occurrences,
  exported `run-work-item`, and exactly the six active rows as `effect-adapter`.
- [x] Run the focused selector and record RED caused only by the current six
  `procedure-candidate` classifications.
- [x] Add an exact-path compile test proving production compiles and the
  deterministic five-call finalizer conversion is rejected with
  `pure_expr_operand_type_mismatch` because `BlockerClass.roadmap_conflict` is
  reduced to `String` where `std/resource::BlockerClass` is required.
- [x] Reclassify exactly six active rows, add the classifier's separate public
  entry, preserve `source_commit` and the one history row, and reconcile active
  internal counts to 12/20/63 with nine public entries.
- [x] Update the inventory narrative, parent migration plan, canonical routing
  surfaces, and routing tests so phase orchestration (nine calls) is current,
  Task 5 remains open, and all later ordering is unchanged.
- [x] Run JSON parse, focused retention/inventory/public-wrapper tests, the full
  routing module, collect-only, unchanged-source/mirror checks, and touched-file
  diff checks.

No finalizer hypothetical executable exists. Therefore this decision makes no
added/removed checkpoint-delta claim and no affected-route runtime parity
claim.

## Governing result

The retained production module compiles, and its compiled export graph contains
both `run-work-item` and `classify-blocked-implementation-recovery` in
`workflows_by_name`. The classifier is therefore an exported, CLI-selectable
workflow requiring `strict_compatibility`. Its internal-call row remains
`effect-adapter`, and the inventory records the callee separately as
`public-entry:lisp_frontend_design_delta/work_item::classify-blocked-implementation-recovery`.

The deterministic hypothetical converts only
`finalize-selected-item-from-blocked-implementation`: it changes that
definition to `defproc :lowering inline`, declares its existing effects,
changes its exact five keyword workflow calls to positional applications, and
removes only the corresponding caller-visible `calls-workflow` declarations.

That real compiler invocation fails with the single diagnostic code
`pure_expr_operand_type_mismatch` at the
`BlockerClass.roadmap_conflict` operand. In the lowered pure expression the
operand is a `String`, while
`finalize-selected-item-from-blocked-implementation` requires
`std/resource::BlockerClass`. The finalizer hypothetical therefore cannot
produce an executable under the current accepted compiler. This type
rejection, not the process-local exploratory probe used to identify the
minimal edit, is durable evidence for the five finalizer calls only. The
diagnostic is not evidence for classifier retention.

Therefore:

- `classify-blocked-implementation-recovery` and
  `finalize-selected-item-from-blocked-implementation` remain `defworkflow`;
- their exact one plus five occurrences remain explicit workflow calls;
- exported `run-work-item` remains a workflow;
- the classifier row remains `effect-adapter` because its callee is exported;
- the five finalizer rows remain `effect-adapter` because their hypothetical
  fails compiler typechecking;
- active counts become 12 procedure candidates, 20 effect adapters, and 63
  legacy-retire rows;
- public entries become nine, including the classifier; the one history row
  and inventory `source_commit` remain unchanged; and
- phase orchestration, containing exactly nine active call IDs, becomes the
  current Task 5 subfamily.

## Evidence and claim boundary

The executable selectors are:

- `tests/test_workflow_lisp_procedure_first_migrations.py::test_design_delta_blocked_recovery_rows_retain_workflow_boundaries`; and
- `tests/test_workflow_lisp_procedure_first_migrations.py::test_design_delta_blocked_recovery_hypothetical_fails_closed_at_typecheck`.

The compiler selector uses the existing fail-closed override for the exact
absolute production path. It counts and hashes every served `Path.read_bytes`,
`Path.read_text`, and read-only `Path.open` access, rejects write-capable open
modes and direct pathlib writes, and verifies production disk bytes again on
normal and exceptional exits. The production source and its derived runtime
mirror remain byte-equal at SHA-256
`216e53dedc2e815d33166c2f3d5e5b6e69319b91bee9a97222a197f771b2dcba`.

The export assertion is form-aware: it reads the compiled module's
`export_surfaces_by_name["lisp_frontend_design_delta/work_item"].workflows_by_name`
rather than matching export text.

This decision changes no source, mirror, YAML, compiler/runtime implementation,
checkpoint baseline, inventory history, or run state. Because the finalizer
hypothetical fails before an executable exists, this decision records neither
an added/removed checkpoint delta nor affected-route runtime parity. It also
does not accept or encode the exploratory process-local equivalence shim as
evidence.

The current-source inventory authority remains
`docs/plans/2026-07-13-procedure-first-reuse-inventory.json`; its unchanged
`source_commit` is `db9889937a895d67810dee1ea0b1b53552d30eca` because authored
source and the active-source population do not change.
