# Design Delta Completed-Finalization Lowering-Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` while executing this plan. This is the
> bounded Task 5 closeout package; do not modify production source, runtime
> mirrors, YAML, compiler/runtime code, checkpoint baselines, or run state, and
> do not commit this package.

**Status:** Complete by fail-closed shared-validation retention. Completed
finalization contains exactly two internal calls to one private workflow. The
production source compiles; the complete exact-path inline hypothetical emits
exactly two `workflow_boundary_type_invalid` diagnostics and produces no
executable. Task 5 is complete, and Task 6 Step 1 is current.

**Goal:** Resolve the final two Task 5 calls from compiler evidence, retain
them fail-closed when shared validation rejects the exact inline hypothetical,
and advance the migration-wave selector to Task 6 Step 1 without changing
executable source.

**Architecture:** Lock the current private workflow, its two callers, and the
exported `run-work-item` contract structurally. Use the existing read/write-safe
same-path source override to convert only the completed-finalization definition
and calls, declare the same three caller-visible effects, remove only a
genuinely present stale self `calls-workflow` declaration, and compile through
the production entry path. Treat exact structured shared-validation diagnostics
as a fail-closed retention result; no hypothetical executable, checkpoint, or
runtime comparison follows a validation failure.

**Tech Stack:** Workflow Lisp compiler and shared validation, pytest, JSON
inventory, Markdown routing surfaces.

**Approach tradeoff:** Both calls remain workflow boundaries. This leaves an
internal function-shaped callee in the workflow namespace, but avoids masking
the approved-plan/completed-implementation blocker-class variant mismatch or
claiming parity for a hypothetical that never becomes executable.

---

## Exact boundary

- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-completed-implementation:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:finalize-selected-item-from-completed-implementation:2`

The callee remains private: it is absent from compiled workflow and procedure
exports. `lisp_frontend_design_delta/work_item::run-work-item` remains the
exported public workflow contract. No public-entry record is added.

## Task 1: Lock the retained source and inventory contract

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add a RED structural test enumerating exactly the two IDs and requiring
  both rows to be `effect-adapter` with this decision and the exact compile
  selector in their evidence paths.
- [x] Require exactly one `defworkflow` definition, no same-named `defproc`,
  exactly two workflow calls, and no same-named compiled workflow/procedure
  export.
- [x] Require exported `run-work-item` to retain its workflow binding and
  public contract.
- [x] Run the selector and confirm RED is caused by the two current
  `procedure-candidate` rows.

## Task 2: Prove the exact-path hypothetical fails shared validation

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add a complete, exact-count source transformation converting only
  `finalize-selected-item-from-completed-implementation` to
  `defproc :lowering inline`, its two calls to procedure applications, and its
  same three effects. Remove only a genuinely present stale self
  `calls-workflow` declaration.
- [x] Compile retained production bytes successfully through the production
  Design Delta entry.
- [x] Compile the hypothetical through the read/write-safe exact-path override
  and require shared validation to emit exactly two
  `workflow_boundary_type_invalid` diagnostics.
- [x] Assert diagnostic code, authored location, and offending symbols
  structurally: one approved-plan proof and one completed-implementation proof
  involving the blocker-class variant contract.
- [x] Prove production bytes are unchanged before and after both compiles.
- [x] Stop at validation failure; make no hypothetical executable,
  checkpoint-delta, resume, or runtime-parity claim.

## Task 3: Reconcile inventory and Task 5 closeout routing

**Files:**

- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Modify: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Reclassify exactly the two active rows as `effect-adapter`, with specific
  diagnostic reasons and the decision/source/inventory/structural/compile
  evidence paths.
- [x] Reconcile active counts to 1 procedure candidate, 31 effect adapters,
  and 63 legacy-retire rows; preserve 13 public entries, 108 active records,
  one history row, and `source_commit` unchanged.
- [x] Add a concise inventory link to this decision and preserve all historical
  audit-boundary counts.
- [x] Reconcile Task 5's four groups as 4 + 6 + 9 + 2 = 21 retained rows and
  mark Task 5 Steps 1-5 complete using retention evidence rather than fictional
  source commits.
- [x] Record focused structural, compile, inventory, and public-wrapper gates;
  mark Task 5 complete and Task 6 Step 1 current without changing later order.
- [x] Add canonical index, execution-sequence, capability-matrix, and routing
  test coverage for this decision and its plan discoverability.

## Task 4: Verify the bounded package

**Files:**

- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Parse the inventory JSON.
- [x] Run focused completed-finalization retention, exact compile-diagnostic,
  inventory, and public-wrapper selectors.
- [x] Run the complete routing test module and collect both modified modules.
- [x] Run diff checks and verify production source, runtime mirrors, YAML,
  compiler/runtime code, checkpoint baselines, and run state are untouched.
- [x] Record that the hypothetical produces no executable and supports no
  checkpoint, resume, or runtime delta claim.

## Governing claim boundary

This package may change tests, inventory classification, this decision, and
canonical routing only. Production and mirrored `.orc` bytes, YAML, compiler
and runtime implementation, checkpoint baselines, run state, inventory
history, and `source_commit` remain unchanged. Shared-validation rejection is
retention evidence only: it is not an executable, runtime-parity, checkpoint,
identity-remap, state-upgrader, cross-source-resume, promotion, or YAML-
retirement claim.
