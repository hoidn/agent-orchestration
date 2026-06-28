# Workflow Lisp Runtime-Native Drain Selected-Item Stdlib Hidden Phase Context Regression Reopen Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the production selected-item stdlib route so `lisp_frontend_design_delta/work_item::run-selected-item-stdlib` can call `lisp_frontend_design_delta/work_item::run-work-item` through the existing hidden `derived_private_child_context` lane, eliminating the reopened `workflow_signature_mismatch` without widening public workflow boundaries or adding command glue.

**Architecture:** Treat this as a bounded shared-lane reuse repair, not a new Workflow Lisp feature. Start from the actual red baseline in the current checkout: the production route fails, the adjacent shared fixture lane is already red, and the full Design Delta parent-drain compile/build lane is blocked by unrelated validation and lint failures. Repair only the narrowest shared metadata/admission or hidden-input path needed to restore the production omitted-`phase-ctx` call, prove that route with focused compile and build-artifact evidence, and split any remaining promoted-entry or full-drain blockers into follow-on work instead of widening this slice.

**Tech Stack:** Workflow Lisp signature/catalog construction in `orchestrator/workflow_lisp/workflows.py`, call admission in `orchestrator/workflow_lisp/typecheck_calls.py`, hidden-context lowering in `orchestrator/workflow_lisp/lowering/{workflow_calls.py,phase_drain.py}`, family profile metadata in `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`, Design Delta compile proofs in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, focused build-artifact proofs in `tests/test_workflow_lisp_build_artifacts.py`, and `compile_stage3_entrypoint` / `build_frontend_bundle`-backed pytest selectors as the narrowest viable integration evidence for this slice.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/capability_status_matrix.md`
- `docs/steering.md`
  - currently empty in this checkout; do not treat that as permission to widen scope
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
  - `9.2 Shared Phase-Family Boundary Prerequisite`
  - `13.4 Design Delta Drain Acceptance`
  - `15. Success Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - workflow-call validation
  - private executable-context ownership
  - WCC/schema-2 validation order
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selected-item-stdlib-hidden-phase-context-regression-reopen/implementation_architecture.md`
- `state/workflow_lisp/calls/20260628T222059Z-vkdl6j/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`
- `state/workflow_lisp/calls/20260628T222059Z-vkdl6j/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.select_next_work.run_3b9c1f5ae273/lisp-frontend-design-delta-selector-v214/de14bca20ef59f36.json/selection.json`
- `state/workflow_lisp/calls/20260628T222059Z-vkdl6j/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/check_commands.json`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`
  - currently `{"ledger_version":1,"events":[]}`; there is no prior implementation event to reconcile

Reference these current seams before editing:

- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`

## Current Checkout Baseline

Fresh verification in this checkout establishes three facts that the old plan did not model:

- The production selected-item route is still red:
  - `pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'`
  - current result: `2 failed, 88 deselected`
  - both failures report `[workflow_signature_mismatch] call is missing required binding phase-ctx` at `run-selected-item-stdlib`
- The adjacent shared fixture lane is also red, so it cannot be treated as a green prerequisite:
  - `pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_item_ctx_child_phase_reuse_compiles or design_delta_item_ctx_child_phase_reuse_route_supports_arbitrary_module_identity or design_delta_item_ctx_child_phase_reuse_route_rejects_non_item_ctx_root'`
  - current result: `3 failed, 87 deselected`
  - two failures report `promoted_entry_hidden_context_binding_invalid`; the rejection selector now reports `workflow_signature_mismatch` instead of the expected `derived_phase_context_binding_invalid`
- The current build-artifact lane is split:
  - `pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_item_ctx_child_phase_reuse_build_artifacts_record_derived_child_phase_binding or design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding'`
  - current result: `2 failed, 178 deselected`
  - the shared fixture build fails on the same promoted-entry hidden-context issue
  - the parent-drain production build is blocked by unrelated `workflow_boundary_type_invalid` failures in `std/drain.orc` / `drain.orc` plus required `low_level_state_path_in_high_level_module` lints across multiple Design Delta modules

These baseline facts change the execution contract:

- production compile selectors are the primary in-scope regression proof;
- shared fixture selectors are characterization and collateral-regression checks, not a false-green prerequisite;
- full Design Delta parent-drain compile/build success is not an achievable done condition for this slice unless those unrelated blockers disappear without changing out-of-scope files; and
- this slice therefore needs a focused production build-artifact proof that does not depend on the blocked full-drain lane.

## Scope Lock

This plan owns only the selected regression reopen:

- restore omitted `phase-ctx` admission for the production call from `run-selected-item-stdlib` to `run-work-item`;
- preserve the fixed imported `std/drain::backlog-drain` `run-item` workflow-ref shape: `(ItemCtx, selection payload) -> SelectedItemResult`;
- preserve the hidden binding identity `phase-ctx__work-item` with `bridge_class = "derived_private_child_context"`;
- keep public authored boundaries free of `PhaseCtx`, state roots, artifact roots, run ids, or generated hidden-input names; and
- prove the repaired production route through focused compile and build-artifact evidence that does not require fixing unrelated `std/drain` or high-level-module lint debt.

This plan does **not** own:

- widening `run-selected-item-stdlib`, `run-work-item`, selector, or `std/drain` workflow-ref signatures;
- editing `std/drain.orc`, `std/resource.orc`, or `std/phase.orc` semantics to make the full family compile green;
- changing `run-work-item` phase behavior, result branching, finalization, summary ownership, or gap convergence;
- fixing promoted-entry hidden-context regressions unless the same shared repair that restores production also fixes them without adding new scope;
- adding wrappers whose only job is to transport `phase-ctx`;
- adding scripts, command adapters, inline Python, report parsing, pointer-state reads, or compatibility-bundle rereads;
- editing `progress_ledger.json`, run state, or unrelated docs; or
- claiming YAML-primary promotion.

## File Ownership Map

Inspect first:

- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/phase.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`

Primary modification candidates:

- `orchestrator/workflow_lisp/workflows.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`

Modify only if the reproduced failure proves catalog metadata is present but call admission still rejects the production omitted binding:

- `orchestrator/workflow_lisp/typecheck_calls.py`

Modify only if production compile proof passes but focused build-artifact evidence is still stale:

- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`

Modify only if the checked profile metadata is stale or incomplete:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`

Do not modify in this slice:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
  - unless a reproduced compile failure proves the authored boundary itself drifted from the implementation architecture, which is not expected here
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`
- `specs/`

## Locked Decisions

- The accepted repair is reuse of the existing generic `derived_private_child_context` lane, not a Design Delta-specific compiler hook.
- `run-selected-item-stdlib` must continue to omit authored `:phase-ctx`; adding it would violate the target design.
- Production success is defined by the selected-item route itself, not by unrelated full-drain compile/lint debt.
- Use the existing parent-call work-item entrypoint fixture (`_compile_design_delta_parent_call_work_item_entrypoint(...)` and its source fixture) as the anchor for narrow production compile proof.
- If the existing parent-drain build-artifact selector becomes reachable after the repair, it may remain as additional evidence; if it is still blocked by unrelated `std/drain` or high-level lint failures, add or tighten a focused production build-artifact selector that compiles or builds only the parent-call work-item route.
- Shared fixture selectors are mandatory characterization after shared-layer edits, but they are not a blocking prerequisite. If they remain red only with promoted-entry-specific failures after the production route is fixed, record that as follow-on work instead of widening this slice into a broader promoted-entry repair.
- A full `python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc ...` command may be rerun for evidence refresh, but it is not a done condition for this slice unless it becomes green without out-of-scope edits.
- A focused pytest-backed compile/build proof is sufficient integration evidence here because the full family CLI compile is currently blocked by independent `std/drain` validation and Design Delta lint debt outside this selected gap.

## Task 1: Reproduce The Actual Red Baseline And Classify Which Lanes Belong To This Slice

**Files:**

- Inspect: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Inspect: `tests/test_workflow_lisp_build_artifacts.py`
- Inspect: `workflows/library/lisp_frontend_design_delta/work_item.orc`
- Inspect: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`

- [ ] **Step 1: Collect the touched test modules before changing anything**

Run:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- collection succeeds for both modules; and
- the production, shared-fixture, and build-artifact selectors listed in `check_commands.json` are present.

- [ ] **Step 2: Reproduce the exact failing production selectors**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'
```

Expected baseline:

- `2 failed`; and
- both failures report `workflow_signature_mismatch` for missing required binding `phase-ctx` from `run-selected-item-stdlib`.

- [ ] **Step 3: Reproduce the adjacent shared-fixture and build-artifact failures as characterization, not as false-green gates**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_item_ctx_child_phase_reuse_compiles or design_delta_item_ctx_child_phase_reuse_route_supports_arbitrary_module_identity or design_delta_item_ctx_child_phase_reuse_route_rejects_non_item_ctx_root'
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_item_ctx_child_phase_reuse_build_artifacts_record_derived_child_phase_binding or design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding'
```

Expected baseline:

- the shared compile selectors fail in their current state;
- at least one shared failure is `promoted_entry_hidden_context_binding_invalid`;
- the fixture rejection selector currently emits `workflow_signature_mismatch` instead of the older expected diagnostic code; and
- the parent-drain build selector is blocked by unrelated `std/drain` / `drain.orc` validation or high-level-module lint failures rather than by the selected production omission alone.

- [ ] **Step 4: Identify the narrow production artifact-proof seam before editing compiler code**

Inspect the existing helper/test surfaces around:

- `_compile_design_delta_parent_call_work_item_entrypoint(...)`
- `PARENT_CALL_WORK_ITEM_CANDIDATE_FIXTURE`
- `_build_design_delta_parent_drain(...)`
- `test_design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding`

Decision rule:

- if the existing parent-drain build selector can become reachable without touching out-of-scope files, reuse it as the production artifact proof;
- otherwise, plan to add a focused helper in `tests/test_workflow_lisp_build_artifacts.py` that builds the same parent-call work-item entrypoint fixture used by the compile selector and asserts the hidden binding there instead of through the blocked full-drain lane.

## Task 2: Repair Production Signature Or Catalog Admission Through The Shared Hidden-Context Lane

**Files:**

- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify only if necessary: `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify only if necessary: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`

- [ ] **Step 1: Audit signature construction for the production caller and callee**

Inspect these seams:

- `_phase_family_hidden_context_requirements(...)`
- `_shared_proof_item_ctx_worker_workflow_names(...)`
- the workflow-catalog signature rewrite that persists `hidden_context_requirements` and `allowed_hidden_context_callees`

Required outcome:

- `run-work-item` retains a hidden-context requirement for `phase-ctx` with `binding_kind = "derived_private_child_context"` and `phase_name = "work-item"`;
- `run-selected-item-stdlib` is recognized as an eligible `ItemCtx + typed payload` caller on the same generic route as the existing proof lane; and
- no Design Delta-specific name branch is introduced.

- [ ] **Step 2: Repair only the metadata path that blocks the production omitted-binding call**

Implementation requirements:

- preserve generic `derived_private_child_context_eligibility(...)` ownership in `phase.py`;
- ensure the production caller receives the same `allowed_hidden_context_callees` or equivalent shared-lane admission metadata as the generic `ItemCtx + typed payload` route;
- keep `workflow_signature_mismatch` as the failure mode for truly missing metadata or ineligible callers; and
- do not widen any public workflow signature or inject an authored `phase-ctx`.

- [ ] **Step 3: Rerun the production compile selectors immediately after the metadata repair**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'
```

Expected:

- both selectors pass; or
- one selector advances past signature admission into a build-artifact/lowering issue for the same production route.

- [ ] **Step 4: Touch `typecheck_calls.py` only if the production call still fails despite correct signature metadata**

Allowed change shape:

- keep the omitted-binding gate strict;
- repair only the path that compares active signature eligibility against the callee's `derived_private_child_context` requirement; and
- preserve existing generic diagnostics:
  - `derived_phase_context_binding_invalid`
  - `derived_phase_context_ambiguous`
  - `workflow_signature_mismatch`

## Task 3: Prove The Production Hidden Binding Without Depending On The Blocked Full-Drain Lane

**Files:**

- Modify only if needed: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify only if needed: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify only if needed: `tests/test_workflow_lisp_build_artifacts.py`
- Modify only if needed: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`

- [ ] **Step 1: Inspect the production hidden-input emission path**

Audit the lowering branches that handle omitted `derived_private_child_context` parameters and confirm they emit:

- `binding_id = "phase-ctx__work-item"`
- `bridge_class = "derived_private_child_context"`
- `source_param_name = "item-ctx"`
- carried input sources rooted in `item-ctx.run.*`
- compile-time defaults for the `work-item` phase context
- source provenance pointing back to the `run-work-item` call in `work_item.orc`

- [ ] **Step 2: Repair lowering only if production artifact evidence is stale after Task 2**

Allowed fix scope:

- preserve the generic hidden-input declaration helper path already used by the shared lane;
- keep build-artifact serialization and `workflow_boundary_projection` aligned on the same binding metadata;
- update the family profile JSON only if the `run-work-item` hidden-context rule is missing or malformed in the checked-in profile; and
- do not add a second lowering path keyed to `lisp_frontend_design_delta`.

- [ ] **Step 3: Establish a focused production build-artifact selector**

Preferred order:

1. If `test_design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding` becomes reachable without touching `drain.orc`, `std/drain.orc`, or unrelated lint-owned modules, reuse it.
2. Otherwise, add a focused helper and selector in `tests/test_workflow_lisp_build_artifacts.py` that build the same parent-call work-item candidate fixture used by `_compile_design_delta_parent_call_work_item_entrypoint(...)`.

Required assertions for whichever selector is used:

- `phase-ctx__work-item` exists on the production route;
- its `bridge_class` is `derived_private_child_context`;
- its context family is `PhaseCtx`;
- carried input sources come from `item-ctx.run.*`;
- source provenance points to the `run-work-item` call owned by `run-selected-item-stdlib`; and
- public boundary rows do not expose `phase-ctx__*`.

- [ ] **Step 4: Rerun the focused production proof lanes**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_parent_call_work_item_build_artifacts_record_derived_child_phase_binding or design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding'
```

Expected:

- the production compile selectors pass; and
- at least one focused production build-artifact selector passes without requiring out-of-scope `drain.orc` / `std/drain.orc` / lint repairs.

## Task 4: Recheck Shared-Lane Collateral, Refresh Evidence, And Enforce Split Conditions

**Files:**

- No additional file edits required if Tasks 2-3 are green

- [ ] **Step 1: Re-run shared-fixture selectors only as collateral checks after shared-layer edits**

Run:

```bash
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_item_ctx_child_phase_reuse_compiles or design_delta_item_ctx_child_phase_reuse_route_supports_arbitrary_module_identity or design_delta_item_ctx_child_phase_reuse_route_rejects_non_item_ctx_root'
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_item_ctx_child_phase_reuse_build_artifacts_record_derived_child_phase_binding'
```

Acceptable outcomes:

- best case: these selectors also pass, proving the shared lane is green again; or
- bounded case: the production route stays green while shared selectors remain red only with promoted-entry-specific failures or the same diagnostic-code mismatch. In that case, record the remaining failures as follow-on work and do not widen this slice into promoted-entry semantics.

- [ ] **Step 2: Refresh full-drain evidence only as non-blocking characterization**

Optional run:

```bash
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding'
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Interpretation rule:

- if these commands become green without out-of-scope edits, keep the evidence;
- if they still fail on `std/drain` structured-validation issues, unknown-step refs in `drain.orc`, or `low_level_state_path_in_high_level_module` lints, record that the blockers are unchanged and do not keep this slice open for them.

- [ ] **Step 3: Re-run collect-only if you added or renamed tests**

Run only if Task 3 introduced or renamed selectors:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- collection succeeds for the edited modules.

- [ ] **Step 4: Enforce the stop conditions**

If the next failure is about any of these, stop and split the follow-on work instead of broadening this slice:

- promoted-entry hidden-context admission unrelated to the production omitted-binding route;
- called-workflow result branching or terminal reprojection;
- imported `finalize-selected-item` summary ownership;
- `std/phase` owner-lane self-hosting;
- unrelated `std/drain` structured-validation failures;
- `low_level_state_path_in_high_level_module` lint retirement across other Design Delta modules;
- gap re-entry convergence;
- command-adapter certification; or
- YAML-primary parity claims.

## Done Condition

This slice is complete when all of the following are true:

- the production selectors for hidden phase-context compilation pass;
- a focused production build-artifact selector records `phase-ctx__work-item` as private `derived_private_child_context` evidence without requiring out-of-scope full-drain fixes;
- public boundaries for the repaired route still exclude authored `PhaseCtx` or generated `phase-ctx__*` values;
- no new family-specific hook, wrapper transport, command glue, or public boundary widening was introduced; and
- any still-red shared-fixture or full-drain compile/build lanes are explicitly classified as follow-on blockers rather than silently absorbed into this slice.
