# Workflow Lisp Imported-Child Returned-Variant Work-Item Prerequisite Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` or `superpowers:subagent-driven-development` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the selected imported-child returned-variant prerequisite is already satisfied in the current checkout, keep that Tranche 2 route green, and close the stale recovered-gap item only after the required lowering, feasibility, smoke, and build-artifact proof surfaces either pass or classify cleanly to Tranche 3A phase-family boundary rehabilitation.

**Architecture:** Treat the selected work-item context as a `stale_duplicate` relative to the current target design and live feasibility evidence. Execution starts by re-running the authoritative Tranche 2 lowering selectors, the recorded design-delta feasibility/smoke proof command, and the required build-artifact selector from `check_commands.json`. If the imported-child route stays green and the remaining non-passing surfaces fail only with documented Tranche 3A boundary/path diagnostics, do not edit frontend lowering or runtime code; instead, record closure evidence that the remaining work-item, parent-call, and build-artifact failures are now owned by `workflow-lisp-phase-family-boundary-rehabilitation`. Only if the selected Tranche 2 selectors regress may this plan touch the original frontend-local union-normalization files.

**Tech Stack:** Python 3, Workflow Lisp frontend lowering under `orchestrator/workflow_lisp/`, design-delta feasibility and build-artifact tests, `pytest`, JSON/Markdown execution artifacts, and `git diff --check`.

---

## Fixed Inputs

Treat these as the authority chain for this plan:

- `docs/index.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  - `4.2 Current status snapshot`
  - `13. Tranche 2: Union Result Normalization And Variant-Scoped Output Identity`
  - `13.2 Union-to-union normalization rule`
  - `13.5 Acceptance`
  - `18.2 Parent-callable phase surfaces`
  - `22. Dependencies And Sequencing`
  - `27.3 Union and variant-output tests`
  - `27.4A Phase-family boundary rehabilitation tests`
  - `29. Success Criteria`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/execution_plan.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/check_commands.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/13/recovered-gap/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/13/recovered-gap/work-item/work-item-inputs.json`

## Status Reconciliation

This plan resolves one explicit inconsistency before execution:

- The selected work-item context and recovered-gap selection still point at `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`.
- The current target design now says the imported-child returned-variant route is already cleared enough that the next blocker is Tranche 3A phase-family boundary rehabilitation.
- Live feasibility evidence from 2026-06-10 agrees with the current target design, not the stale selector wording.

Execution must therefore follow this rule:

- if the Tranche 2 selectors below pass and the required feasibility/build-artifact proof surfaces either pass or fail only with documented Tranche 3A boundary/path diagnostics, this work item is closure-only and must not reopen union-normalization implementation;
- if those selectors fail with `union_return_variant_ambiguous`, `union_return_variant_incompatible`, or equivalent same-target pass-through regressions, fix only the original Tranche 2 frontend-local slice;
- if the downstream smoke or build-artifact proof surfaces fail on `workflow_boundary_type_invalid`, `low_level_state_path_in_high_level_module`, or other phase-family boundary diagnostics after the Tranche 2 selectors pass, stop and hand off to `workflow-lisp-phase-family-boundary-rehabilitation` instead of widening this item;
- if the build-artifact proof surface fails for any other reason, do not close the item until the failure is classified as either a true imported-child regression or a different documented owner.

## Current Checkout Facts

These facts were re-verified on 2026-06-10 while drafting this plan:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` contains no events, so no later recorded execution supersedes the selected stale item.
- The authoritative parent-callable proof source for this slice is the
  checked-in candidate under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` plus
  the verification-only parent wrapper
  `tests/fixtures/workflow_lisp/valid/design_delta_parent_calls_work_item.orc`;
  the shipping library module remains closure-only until the separate
  parent-callable work-item composition slice lands.
- `python -m pytest tests/test_workflow_lisp_lowering.py -k "cross_union_match_translation or union_return_variant_ambiguous or union_return_variant_incompatible or same_target_union" -q` currently passes: `5 passed`.
- `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_migration_cross_union_result_translation_compiles or design_delta_work_item_candidate_compiles_as_parent_callable_workflow" -q` currently passes: `2 passed`.
- `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes or design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes" -q` currently fails on Tranche 3A boundary/path seams:
  - `workflow_boundary_type_invalid`
  - `low_level_state_path_in_high_level_module`
- `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item_runtime_context_inputs_stay_internal or design_delta_work_item_command_boundary_lineage_records_family_adapters" -q` currently fails with the same Tranche 3A boundary/path seams:
  - `workflow_boundary_type_invalid`
  - `low_level_state_path_in_high_level_module`
- The current failing smokes do not fail on `union_return_variant_ambiguous`, which means the selected imported-child prerequisite is no longer the active blocker.
- The required build-artifact proof surface also does not expose a new imported-child union-normalization regression; it fails on the same phase-family boundary rehabilitation diagnostics as the parent-callable smoke route.
- The existing downstream owner already exists at `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/execution_plan.md`; this plan must hand off to that slice instead of duplicating it.

## Hard Scope Limits

Implement only the bounded closure/supersession pass for the selected imported-child item:

- re-run the authoritative Tranche 2 selectors and confirm they stay green;
- re-run the required build-artifact selector from `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/check_commands.json` and classify its result alongside the feasibility/smoke proof surfaces;
- preserve or tighten direct regression coverage only if those selectors regress or a proof gap is discovered inside the selected Tranche 2 acceptance surface;
- record closure evidence showing that any remaining smoke and build-artifact failures are Tranche 3A boundary blockers;
- hand off to the existing phase-family boundary rehabilitation slice without editing it.

Do not widen this plan into:

- Tranche 3A boundary/path rehabilitation;
- private executable context bootstrap;
- selector projection;
- adapter/resource-transition redesign;
- parent work-item or parent drain product design;
- shared runtime, shared validation, or migration-parity changes outside the original imported-child slice.

If execution reaches a failure that requires phase-family boundary changes after the Tranche 2 selectors are green, stop and report the handoff rather than editing code under this item.

## Conditional File Map

**Always produce execution artifacts**

- `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/execution_report.md`
- `artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite-checks.json`
- `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite-summary.json`
- `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/progress_report.md`

**Modify only if the selected Tranche 2 route regresses**

- `orchestrator/workflow_lisp/lowering/context.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/control_match.py`
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/procedures.py`
- `orchestrator/workflow_lisp/diagnostics.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify `tests/test_workflow_lisp_build_artifacts.py` only if a selected-slice proof gap is inside the imported-child closure evidence rather than the Tranche 3A owner slice

**Do Not Modify Under This Plan**

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/*`
- `orchestrator/workflow/*`
- `workflows/library/lisp_frontend_design_delta/*.orc`
- `specs/*`

unless the supposedly green Tranche 2 selectors fail and the root cause is unmistakably still inside the selected imported-child slice.

## Task 1: Re-Baseline The Selected Tranche 2 Closure Surface

**Files:**

- Modify only if selectors regress: `tests/test_workflow_lisp_lowering.py`
- Modify only if selectors regress: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify: `tests/test_workflow_lisp_build_artifacts.py`
- Produce: execution/check/progress artifacts listed above

- [ ] **Step 1: Run collection for the selected test surfaces**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
```

Expected:

- collection succeeds;
- the imported-child regression, downstream design-delta smoke tests, and build-artifact selectors remain discoverable.

- [ ] **Step 2: Re-run the direct Tranche 2 lowering proof**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "cross_union_match_translation or union_return_variant_ambiguous or union_return_variant_incompatible or same_target_union" -q
```

Expected:

- all targeted lowering tests pass;
- no failure cites `union_return_variant_ambiguous`, `union_return_variant_incompatible`, missing same-target pass-through metadata, or equivalent imported-child normalization regressions.

- [ ] **Step 3: Re-run the recorded design-delta feasibility proof command**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_migration_cross_union_result_translation_compiles or design_delta_work_item_candidate_compiles_as_parent_callable_workflow or design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes or design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes" -q
```

Expected:

- the compile selectors pass;
- any non-passing smoke portions fail only with documented Tranche 3A boundary/path diagnostics;
- the real imported-child route does not fail with `union_return_variant_ambiguous`.

- [ ] **Step 4: Re-run the supplemental downstream smokes to classify the remaining blocker completely**

Run:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes or design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes or design_delta_work_item_candidate_smokes_terminal_blocked_route or design_delta_parent_call_work_item_smokes_terminal_blocked_route" -q
```

Expected:

- if failures remain, they cite Tranche 3A boundary/path diagnostics such as `workflow_boundary_type_invalid` or `low_level_state_path_in_high_level_module`;
- failures must not cite the selected imported-child union-normalization diagnostics;
- if all four smokes unexpectedly pass, record that the selected item is closed and note that the Tranche 3A owner plan may also now be stale.

- [ ] **Step 5: Re-run the required build-artifact proof surface**

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item_runtime_context_inputs_stay_internal or design_delta_work_item_command_boundary_lineage_records_family_adapters" -q
```

Expected:

- the selector either passes or fails only with documented Tranche 3A boundary/path diagnostics;
- failures must not cite imported-child union-normalization regressions;
- the result explicitly classifies whether hidden runtime inputs and command-boundary lineage remain visible enough to support closure-only handoff.

## Task 2: Repair Only If The Selected Imported-Child Slice Regresses

**Files:**

- Modify only if needed: `orchestrator/workflow_lisp/lowering/context.py`
- Modify only if needed: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify only if needed: `orchestrator/workflow_lisp/lowering/control_match.py`
- Modify only if needed: `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- Modify only if needed: `orchestrator/workflow_lisp/lowering/procedures.py`
- Modify only if needed: `orchestrator/workflow_lisp/diagnostics.py`
- Test: `tests/test_workflow_lisp_lowering.py`
- Test: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify: `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Only enter this task if Task 1 shows a true Tranche 2 regression**

Allowed entry conditions:

- targeted lowering tests fail on same-target pass-through handling;
- the recorded feasibility proof command fails on cross-union normalization or `union_return_variant_ambiguous` in the imported-child route;
- the build-artifact selector exposes a selected-slice regression in command-boundary lineage or hidden runtime-input visibility that is traceable to the imported-child frontend-local route rather than to the Tranche 3A boundary owner;
- diagnostics regress back to raw `KeyError`, `union_return_variant_ambiguous`, or wrong-union ambiguity/incompatibility inside the selected slice.

Forbidden entry conditions:

- downstream smokes fail only on Tranche 3A boundary/path diagnostics;
- the build-artifact selector fails only on Tranche 3A boundary/path diagnostics;
- the selected Tranche 2 selectors are already green.

- [ ] **Step 2: Restore the bounded frontend-local imported-child route**

If this task is entered, keep the fix exactly inside the original selected slice:

- same-target union boundary pass-through metadata;
- terminal-copy preservation through `let*` and helper-hoist paths;
- `control_match.py` normalization precedence and diagnostics;
- no shared runtime or shared validation changes.

Do not redesign phase-family boundaries, hidden context, or public/private workflow signatures here.

- [ ] **Step 3: Re-run the selected Tranche 2 proofs until green**

Run:

```bash
python -m pytest tests/test_workflow_lisp_lowering.py -k "cross_union_match_translation or union_return_variant_ambiguous or union_return_variant_incompatible or same_target_union" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_migration_cross_union_result_translation_compiles or design_delta_work_item_candidate_compiles_as_parent_callable_workflow" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item_runtime_context_inputs_stay_internal or design_delta_work_item_command_boundary_lineage_records_family_adapters" -q
```

Expected:

- all selected imported-child proofs pass;
- any build-artifact selector touched by the selected slice passes or is no longer the blocker that entered Task 2;
- the route is restored without widening into boundary rehabilitation.

## Task 3: Produce Closure Evidence And Downstream Handoff

**Files:**

- Create/overwrite: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/execution_report.md`
- Create/overwrite: `artifacts/checks/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite-checks.json`
- Create/overwrite: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-child-returned-variant-work-item-prerequisite-summary.json`
- Create/overwrite: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/workflow-lisp-imported-child-returned-variant-work-item-prerequisite/progress_report.md`

- [ ] **Step 1: Write the execution report as a closure record, not a fresh implementation claim**

The report must state:

- the selected item came from stale recovered-gap selection state;
- the current target design and live tests agree that the imported-child prerequisite is already satisfied;
- the direct Tranche 2 selectors that passed;
- the exact downstream smoke selectors that still fail, with their current Tranche 3A boundary/path diagnostics;
- the exact build-artifact selector result, including whether it passed or failed only with the same Tranche 3A diagnostics;
- the handoff target:
  `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-phase-family-boundary-rehabilitation/execution_plan.md`.

- [ ] **Step 2: Write the checks report with exact command/result pairs**

Record at minimum:

- the collection command;
- the direct lowering proof command;
- the recorded design-delta feasibility proof command;
- the downstream smoke classification command;
- the build-artifact proof command;
- `git diff --check`.

For each command, record whether it passed or failed and, for failures, include the blocking diagnostic family.

- [ ] **Step 3: Write the item summary and progress report as supersession evidence**

The summary/progress artifacts must make these points explicit:

- selected item status: closed or no-op unless Task 2 was genuinely required;
- selected-item acceptance now satisfied by existing tests and current checkout behavior;
- remaining work moved to Tranche 3A phase-family boundary rehabilitation, including any non-passing build-artifact inspection that still fails only on documented boundary/path diagnostics;
- no attempt was made to widen this item into boundary rehabilitation work.

## Task 4: Final Verification

**Files:**

- Verify modified source/tests only if Task 2 was entered
- Verify generated artifacts from Task 3

- [ ] **Step 1: Run the full closure matrix**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_lowering.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "cross_union_match_translation or union_return_variant_ambiguous or union_return_variant_incompatible or same_target_union" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_migration_cross_union_result_translation_compiles or design_delta_work_item_candidate_compiles_as_parent_callable_workflow or design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes or design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_work_item_candidate_smokes_complete_and_blocked_recovery_routes or design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes or design_delta_work_item_candidate_smokes_terminal_blocked_route or design_delta_parent_call_work_item_smokes_terminal_blocked_route" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item_runtime_context_inputs_stay_internal or design_delta_work_item_command_boundary_lineage_records_family_adapters" -q
git diff --check
```

Expected:

- the selected imported-child selectors pass;
- the recorded feasibility command either passes entirely or any non-passing smoke portions fail only on later-tranche boundary/path diagnostics;
- downstream smokes either pass entirely or fail only on later-tranche boundary/path diagnostics;
- the build-artifact proof surface either passes or fails only on the documented Tranche 3A boundary/path diagnostics, with no imported-child union-normalization regression exposed there;
- `git diff --check` passes.

- [ ] **Step 2: Stop at the correct owner boundary**

Completion condition for this plan:

- the imported-child returned-variant prerequisite is proven green or repaired within its original frontend-local scope; and
- the remaining blocker, if any, is written down as a Tranche 3A handoff rather than silently absorbed here; and
- the required build-artifact proof surface has been exercised and recorded explicitly in that handoff evidence.

Do not begin implementing `workflow-lisp-phase-family-boundary-rehabilitation` from this work item after this plan completes.
