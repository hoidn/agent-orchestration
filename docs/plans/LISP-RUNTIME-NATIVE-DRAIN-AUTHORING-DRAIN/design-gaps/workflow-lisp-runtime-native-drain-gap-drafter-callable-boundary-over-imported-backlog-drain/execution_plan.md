# Workflow Lisp Runtime-Native Drain Gap-Drafter Callable-Boundary Over Imported `backlog-drain` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve the selected shared prerequisite by verifying whether the current checkout already satisfies generic multi-field selector `GAP` payload carriage across the fixed imported `gap-drafter` boundary and, only if that audit fails, landing the narrow shared lowering/test repair without widening scope into Design Delta family adoption.

**Architecture:** The target design and frontend baseline still own the callable-boundary contract; the current checkout, counted shared suite, and verification-gate manifest own completion status. Execute this slice with an audit-first branch: if the shared owner lane already proves generic record-leaf `GAP` carriage, treat the generated work-item bundle as a stale duplicate and close the slice with evidence only; if not, repair only the shared lowering and shared stdlib proof surfaces that enforce `DrainCtx + gap record` over imported `std/drain::backlog-drain`.

**Tech Stack:** Workflow Lisp lowering in `orchestrator/workflow_lisp/lowering/phase_drain.py`, shared drain stdlib proofs in `tests/test_workflow_lisp_drain_stdlib.py`, shared fixtures under `tests/fixtures/workflow_lisp/{valid,invalid}/`, downstream consumer checks in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, and counted-suite routing in `docs/workflow_lisp_g6_verification_gate.json`.

---

## Disputed Behavior

The selected work-item bundle says shared rich `GAP` payload carriage over imported `backlog-drain` is still missing, but the current checkout and counted proof lane already appear to implement and verify it.

Consistency labels for this plan:

- `stale_duplicate`: the generated work-item context and prior execution plan restate an older missing-capability story.
- `routing_mismatch`: the selector chose a prerequisite gap that now looks landed in code/tests, while the progress ledger is still empty.

Source of truth for execution decisions:

1. `docs/design/workflow_lisp_runtime_native_drain_authoring.md` and `docs/design/workflow_lisp_frontend_specification.md` own the callable-boundary contract.
2. `orchestrator/workflow_lisp/lowering/phase_drain.py`, `tests/test_workflow_lisp_drain_stdlib.py`, and `docs/workflow_lisp_g6_verification_gate.json` decide whether the shared proof is actually present in the current checkout.
3. `state/.../work_item_context.md` and the previously generated `execution_plan.md` are historical planning artifacts, not status authority.

## Authority Set

Treat these as the complete authority set for this slice:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/capability_status_matrix.md`
- `docs/steering.md`
- `docs/workflow_lisp_g6_verification_gate.json`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/29/design-gap-architect/work_item_context.md`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`

## Scope Lock

This plan owns only the selected shared prerequisite and its status reconciliation:

- verify whether the promoted shared lowering route already carries selector `GAP` payloads by declared record-leaf shape instead of a hardcoded `gap-id` surrogate;
- verify whether the counted shared stdlib lane already proves the fixed `gap-drafter` boundary with a richer typed record payload;
- if the audit fails, repair only the shared lowering and shared proof fixtures/assertions needed to satisfy that contract;
- keep the fixed callable boundary as exactly `(ctx DrainCtx)` plus one typed gap record;
- preserve the accepted parent one-call and child loop-owner split; and
- keep downstream Design Delta checks in consumer-only status.

This plan does **not** own:

- rewriting `workflows/library/lisp_frontend_design_delta/*.orc`;
- widening `gap-drafter`, `run-item`, or parent workflow-ref signatures;
- reopening parent terminal reprojection, child `PhaseCtx` transport, `std/phase` ownership, request-records, publication, bootstrap, or transitions;
- adding scripts, adapters, compatibility-bundle rereads, placeholder carriers, or report/pointer-state authority workarounds; or
- editing `progress_ledger.json`; the workflow/review lane owns run-state bookkeeping.

## Fresh Evidence Snapshot

These checks were already observed on the current checkout and should be treated as the expected baseline:

- `python -m pytest tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_carries_rich_gap_payload_across_callable_boundary tests/test_workflow_lisp_drain_stdlib.py::test_callable_backlog_drain_keeps_gap_drafter_boundary_narrow tests/test_workflow_lisp_drain_stdlib.py::test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload -q`
  Expected: `3 passed`
- `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_routes_design_gap_bundle_from_action -q`
  Expected: `1 passed`
- `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_still_requires_family_adoption_before_stdlib_delegation -q`
  Expected: `1 passed`

Interpretation:

- the shared stdlib owner lane already appears to prove rich gap-payload carriage and the fixed non-record rejection;
- downstream Design Delta still has not adopted stdlib delegation wholesale, so this slice must not drift into family-adoption work; and
- the likely remaining work is consistency closeout, not feature construction.

## File Ownership Map

Inspect first:

- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `docs/workflow_lisp_g6_verification_gate.json`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary_rich_gap_payload.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_gap_drafter_non_record_payload_invalid.orc`

Modify only if Task 1 proves the shared route is still broken on the branch being executed:

- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary_rich_gap_payload.orc`
- `tests/fixtures/workflow_lisp/invalid/backlog_drain_gap_drafter_non_record_payload_invalid.orc`

Modify only if the shared proof exists but the counted manifest wording is misleading:

- `docs/workflow_lisp_g6_verification_gate.json`

Do not modify in this slice:

- `workflows/library/lisp_frontend_design_delta/*.orc`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`
- `specs/`

## Task 1: Audit The Shared Route And Decide The Branch

**Files:**

- Inspect: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Inspect: `tests/test_workflow_lisp_drain_stdlib.py`
- Inspect: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Inspect: `docs/workflow_lisp_g6_verification_gate.json`

- [ ] **Step 1: Reconfirm the shared proof selectors**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_carries_rich_gap_payload_across_callable_boundary \
  tests/test_workflow_lisp_drain_stdlib.py::test_callable_backlog_drain_keeps_gap_drafter_boundary_narrow \
  tests/test_workflow_lisp_drain_stdlib.py::test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload \
  -q
```

Expected:

- `3 passed`; and
- the shared lane proves rich payload carriage, narrow fixed boundary, and negative non-record rejection.

- [ ] **Step 2: Reconfirm the downstream consumer boundary**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_routes_design_gap_bundle_from_action \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_still_requires_family_adoption_before_stdlib_delegation \
  -q
```

Expected:

- `2 passed`; and
- the Design Delta family still consumes the shared proof inputs while remaining blocked on separate stdlib-adoption work.

- [ ] **Step 3: Inspect the lowering and counted-manifest evidence**

Run:

```bash
sed -n '546,632p' orchestrator/workflow_lisp/lowering/phase_drain.py
sed -n '1448,1490p' tests/test_workflow_lisp_drain_stdlib.py
sed -n '1699,1845p' tests/test_workflow_lisp_drain_stdlib.py
rg -n "rich gap-drafter payload carriage|record-only second-parameter contract" docs/workflow_lisp_g6_verification_gate.json
```

Expected:

- `phase_drain.py` walks `gap_payload_type` with `_flatten_boundary_leaf_paths(...)`;
- there is no hardcoded `gap_value = {"gap-id": ...}` path on the promoted route;
- the shared test file asserts `gap__work-item-id`, `gap__plan-target-path`, and `gap__architecture-path`;
- the narrow-boundary test still asserts field-by-field `gap__...` bindings without widened arity; and
- the G6 manifest reason text already names rich gap-drafter payload carriage.

- [ ] **Step 4: Take the branch decision**

Decision rule:

- if Steps 1-3 all match the expected state, skip Task 2 and go directly to Task 3;
- if any proof selector fails, or if the code inspection shows a hardcoded single-field surrogate is still present on the target branch, execute Task 2 before Task 3.

## Task 2: Conditional Repair If The Shared Proof Is Missing On The Target Branch

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Modify only if needed: `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_callable_boundary_rich_gap_payload.orc`
- Modify only if needed: `tests/fixtures/workflow_lisp/invalid/backlog_drain_gap_drafter_non_record_payload_invalid.orc`
- Modify only if needed: `docs/workflow_lisp_g6_verification_gate.json`

- [ ] **Step 1: Restore generic record-leaf gap carriage in shared lowering**

Implementation requirements:

- validate `gap_drafter` parameter 2 as a `RecordTypeRef`;
- build `gap_value` by iterating `_flatten_boundary_leaf_paths(gap_payload_type, generated_name=...)`;
- populate each field through `_assign_nested_local_value(...)` from `self.steps.<selector>.artifacts.return__gap__...`;
- feed that record into `_build_call_bindings_from_record_value(...)`; and
- preserve source maps, managed write-root bindings, and the parent one-call / child loop-owner split.

- [ ] **Step 2: Restore the shared positive and negative proof surfaces**

Required proof coverage:

- the rich-gap fixture keeps the fixed `(ctx DrainCtx) (gap GapPayload)` boundary;
- the positive shared test asserts the `gap__work-item-id`, `gap__plan-target-path`, and `gap__architecture-path` bindings and asserts `gap__gap-id` is absent;
- the narrow-boundary test still proves ordinary field-by-field record carriage; and
- the non-record invalid fixture still fails with the stable fixed-boundary diagnostic.

- [ ] **Step 3: Re-run the narrow proof selectors**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_carries_rich_gap_payload_across_callable_boundary \
  tests/test_workflow_lisp_drain_stdlib.py::test_callable_backlog_drain_keeps_gap_drafter_boundary_narrow \
  tests/test_workflow_lisp_drain_stdlib.py::test_workflow_ref_resolution_rejects_gap_drafter_non_record_payload \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_routes_design_gap_bundle_from_action \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_still_requires_family_adoption_before_stdlib_delegation \
  -q
```

Expected:

- all five selectors pass; and
- the fix remains bounded to the shared prerequisite without reopening family-adoption work.

- [ ] **Step 4: Validate any touched manifest or renamed tests**

Run only if you changed the manifest or test names:

```bash
python -m json.tool docs/workflow_lisp_g6_verification_gate.json >/dev/null
python -m pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected:

- JSON parses cleanly; and
- collection succeeds for the edited test module.

## Task 3: Close The Slice Without Reopening Family Adoption

**Files:**

- No required repo edits if Task 1 passed cleanly
- Optional wording-only touch: `docs/workflow_lisp_g6_verification_gate.json`

- [ ] **Step 1: Record the conclusion using contract language**

If Task 1 passed without code edits, record this exact conclusion in the execution summary or review handoff:

- the selected prerequisite is already satisfied in the current checkout;
- the stale generated work-item bundle reflects older status, not a live missing capability;
- the accepted fixed boundary remains `DrainCtx + gap record`;
- the shared owner lane, not the Design Delta family, is the proof surface; and
- family adoption remains blocked by separate work proven by `test_design_delta_parent_drain_entrypoint_still_requires_family_adoption_before_stdlib_delegation`.

- [ ] **Step 2: Keep the closeout bounded**

Do not:

- edit `work_item_context.md` or `progress_ledger.json` just to force them to match the checkout;
- patch Design Delta production workflows;
- widen signatures or introduce wrapper transport; or
- treat the passed rich-gap selectors as proof that later stdlib delegation is also complete.

- [ ] **Step 3: Provide verification evidence**

Include the exact commands and outcomes from Task 1 or Task 2 in the handoff. Minimum acceptable evidence:

- shared stdlib proof selectors;
- downstream consumer selectors; and
- code inspection or manifest confirmation showing generic record-leaf carriage and counted-suite discoverability.

## Done Condition

This slice is complete when one of these states is true:

- **Audit-closeout path:** Task 1 passes exactly as written, no code changes are needed, and the final handoff clearly states that the selected prerequisite is already landed while downstream family adoption remains separate.
- **Repair path:** Task 2 lands the missing shared proof on the target branch, Task 3 confirms the bounded proof passes, and the final handoff states that the selected prerequisite is now satisfied without widening scope.
