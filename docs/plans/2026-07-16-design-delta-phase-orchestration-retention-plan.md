# Design Delta Phase-Orchestration Retention Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:test-driven-development` while executing this plan. This is a
> bounded Task 5 fail-closed retention package; do not modify production
> source, runtime mirrors, YAML, compiler/runtime code, checkpoint baselines,
> or run state.

**Status:** Complete by fail-closed public-entry and checkpoint-identity
retention. Phase orchestration contains exactly nine internal call records.
Four unique callees are exported workflow entries, and the fifth is a private
workflow whose exact inline hypothetical changes checkpoint identity. Task 5
remains open; completed finalization (two calls) is current, and subfamily
order is unchanged.

**Goal:** Reconcile the nine phase-orchestration calls with their compiled
public-entry and checkpoint-identity evidence without changing executable
source.

**Architecture:** Compile the retained Design Delta entry to classify exported
members by their actual export namespace and binding kind. For the private
`run-work-item-pending` callee, use the existing read/write-safe exact-path
source override to compile a minimal `defproc :lowering inline` hypothetical,
preserve its declared caller-visible effects, and compare compiler-generated
checkpoint identities with the retained executable. Record the four public
boundaries separately from the nine internal calls.

**Tech Stack:** Workflow Lisp compiler/export graph, pytest, JSON inventory,
Markdown routing surfaces.

**Approach tradeoff:** All nine calls remain workflow boundaries. This avoids
silently retiring public selection identities or the private pending
checkpoint namespace, but it leaves completed finalization as the next Task 5
subfamily and defers further procedure conversion until identity compatibility
can be preserved or explicitly retired.

---

## Exact boundary

- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-work-item-inputs:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:project-work-item-inputs:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:run-plan-phase:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:run-plan-phase:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:implementation-phase:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:implementation-phase:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:classify-work-item-terminal:1`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:classify-work-item-terminal:2`
- `internal-call:workflows/library/lisp_frontend_design_delta/work_item.orc:run-work-item-pending:1`

The four separate public records are:

- `public-entry:lisp_frontend_design_delta/bootstrap::project-work-item-inputs`
- `public-entry:lisp_frontend_design_delta/plan_phase::run-plan-phase`
- `public-entry:lisp_frontend_design_delta/implementation_phase::implementation-phase`
- `public-entry:lisp_frontend_design_delta/projections::classify-work-item-terminal`

The internal-call rows remain distinct records and never use
`public-boundary` classification.

## Task 1: Lock the retained source and inventory contract

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add a RED test enumerating exactly the nine IDs and four public-entry
  IDs, requiring internal `effect-adapter` classification and separate public
  `public-boundary` classification.
- [x] Compile the current Design Delta entry and require each public callee to
  appear in its owning module's `workflows_by_name` with binding kind
  `workflow`, while absent from `procedures_by_name`.
- [x] Require the four exported definitions plus private
  `run-work-item-pending` to remain `defworkflow`, require exact call counts
  `2 + 2 + 2 + 2 + 1`, require `run-work-item` to remain exported, and require
  the private pending callee to be absent from the export surface.
- [x] Run the selector and confirm RED is caused by the nine current
  `procedure-candidate` rows and four missing public records.

## Task 2: Characterize the private pending identity delta

**Files:**

- Modify: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`

- [x] Add a minimal source transformation that converts only
  `run-work-item-pending` to `defproc :lowering inline`, changes its one caller
  to positional procedure application, and declares the callee's existing
  effects.
- [x] Compile retained and hypothetical bytes through the exact production
  path with the read/write-safe helper; prove both compile and prove the
  procedure effects remain visible to the caller.
- [x] Lock the exact checkpoint comparison from a fresh reproducible compile:
  the caller-owned workflow-call boundary checkpoint
  `ckpt:086b77522a63d90a481896c2` is removed, and twelve caller-owned inline
  checkpoints are added with different checkpoint/storage identities and a
  different generated presentation-path namespace.
- [x] Do not assert runtime parity; strict compatibility retention rests on the
  identity delta.

## Task 3: Reconcile inventory and routing

**Files:**

- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.json`
- Modify: `docs/plans/2026-07-13-procedure-first-reuse-inventory.md`
- Modify: `docs/plans/2026-07-13-procedure-first-migration-waves-plan.md`
- Modify: `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`
- Modify: `docs/capability_status_matrix.md`
- Modify: `docs/index.md`
- Modify only if needed for historical public-count context:
  `docs/plans/2026-07-16-design-delta-finalizer-projection-checkpoint-retention-plan.md`
- Modify only if needed for historical public-count context:
  `docs/plans/2026-07-16-design-delta-blocked-recovery-lowering-retention-plan.md`
- Modify: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Reclassify exactly nine active internal rows as `effect-adapter`, with
  public-entry and checkpoint-identity reasons/evidence kept distinct.
- [x] Add exactly four public-entry rows and preserve `source_commit`, the one
  history row, and 95 active internal rows.
- [x] Reconcile counts to 3 procedure candidates, 29 effect adapters, 63
  legacy-retire rows, 13 public entries, and 108 active records.
- [x] Update the concise inventory summary and link this decision.
- [x] Mark phase orchestration retained and make completed finalization, with
  exactly two calls, the current Task 5 sub-selector. Keep Task 5 open and
  preserve all later ordering.
- [x] Keep the bounded-stop plan/routing file scope generic for later retained
  subfamilies.

## Task 4: Verify the bounded package

**Files:**

- Test: `tests/test_workflow_lisp_procedure_first_migrations.py`
- Test: `tests/test_workflow_lisp_drain_roadmap_routing.py`

- [x] Parse the JSON inventory.
- [x] Run the focused phase-retention, inventory, public-wrapper, and exact
  compile/checkpoint selectors.
- [x] Run the complete routing test module.
- [x] Run collection for both modified test modules.
- [x] Run scoped diff checks and verify production source and runtime mirrors
  are clean and unchanged.
- [x] Record that no runtime-parity, source-migration, remap, state-upgrader,
  cross-source-resume, YAML-retirement, or Task 5 completion claim is made.

## Governing result

Compiled export surfaces retain these four workflow entries in
`workflows_by_name`, with binding kind `workflow` and no same-named procedure
export:

- `lisp_frontend_design_delta/bootstrap::project-work-item-inputs`;
- `lisp_frontend_design_delta/plan_phase::run-plan-phase`;
- `lisp_frontend_design_delta/implementation_phase::implementation-phase`; and
- `lisp_frontend_design_delta/projections::classify-work-item-terminal`.

Their eight internal calls require public strict compatibility. The inventory
records the public entries separately; none of the eight internal rows becomes
`public-boundary`.

`run-work-item-pending` is private: it is absent from both exported workflow
and procedure namespaces. Its exact hypothetical converts only that definition
to `defproc :lowering inline`, converts only its one caller, and declares the
existing ten child-workflow, one provider, and one command effects. Both
retained and hypothetical sources compile through the exact production path,
and all twelve effects remain visible on the inline procedure and exported
`run-work-item` caller.

The successful hypothetical removes exactly
`ckpt:086b77522a63d90a481896c2` and adds exactly:

- `ckpt:00dc7237d9abde23fb40b69b`
- `ckpt:09ce859d00f0962b793dfebf`
- `ckpt:1b3c82661af3b2feaa35f42b`
- `ckpt:233ecfb0b10c3da348dc56a2`
- `ckpt:294b5ca0e981a654fe3bd2b0`
- `ckpt:30bafb11d2737afb8b1cf688`
- `ckpt:59af01e48a3e10414e79c371`
- `ckpt:905debcfe48342339d32bdf7`
- `ckpt:b629ae4c8beb869a841e46f0`
- `ckpt:bf70f41dfed8714340562b03`
- `ckpt:cce0b07caefb09af76cf8154`
- `ckpt:e737e9259c7ab5d6d3278eb8`

The removed checkpoint and every added checkpoint are owned by exported
`lisp_frontend_design_delta/work_item::run-work-item`. The twelve inline
checkpoints use the generated presentation-path namespace
`run-work-item__pending__lisp_frontend_design_delta/work_item::run-work-item-pending_1`.
The caller-owned workflow-call boundary checkpoint is therefore removed and
twelve caller-owned inline checkpoints are added. Their checkpoint/storage
identities and generated presentation-path namespace differ even though their
workflow owner remains `run-work-item`. Strict compatibility fails on that
identity delta even though the hypothetical compiles and exposes its effects.

## Claim boundary

This decision changes inventory classification and routing only. Production
source, runtime mirrors, YAML, compiler/runtime code, checkpoint baselines,
run state, inventory history, and `source_commit` remain unchanged. It does not
claim affected-route runtime parity, identity remapping, a state upgrader,
cross-source resume compatibility, YAML retirement, or Task 5 completion.
