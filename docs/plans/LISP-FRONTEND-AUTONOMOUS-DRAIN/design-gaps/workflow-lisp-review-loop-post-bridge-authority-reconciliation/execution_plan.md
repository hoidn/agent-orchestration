# Workflow Lisp Review-Loop Post-Bridge Authority Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reconcile the durable current-checkout Workflow Lisp docs with the already-landed ordinary `std/phase.orc` `review-revise-loop` route so package/design guidance no longer describes deleted bridge owners or a still-live temporary bridge.

**Architecture:** Treat `orchestrator/workflow_lisp/README.md` as the current package map, `docs/design/workflow_lisp_stdlib_lowering.md` as the durable current-checkout lowering/status summary, and the accepted target design plus prior implementation architectures as historical/architectural authority rather than mutable current-state ownership docs. The implementation is documentation-only: repair stale duplicate authority in those two primary surfaces, apply at most one narrow consistency update in `docs/lisp_workflow_drafting_guide.md` or `docs/index.md` if a direct contradiction remains, and verify the repaired docs against current source ownership, focused existing proof tests, and the checked-in `design_plan_impl_stack` parity report.

**Tech Stack:** Markdown docs, Workflow Lisp package map docs, existing `pytest` proof surfaces, ripgrep, checked-in parity JSON under `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/design-gap-architect/work_item_context.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/10/design-gap-architect/check_commands.json`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-post-bridge-authority-reconciliation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-revise-loop-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-stdlib-review-loop-ownership-bridge-retirement/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-evidence-refresh/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-parity-surface-recovery/implementation_architecture.md`

Reference current implementation truth from:

- `orchestrator/workflow_lisp/README.md`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`

## Current Checkout Facts

Do not rediscover these during implementation:

- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still `{"ledger_version":1,"events":[]}`, so no later ledger event supersedes this work item.
- `docs/steering.md` is empty at this checkout and does not widen scope.
- `orchestrator/workflow_lisp/README.md` still lists `phase_stdlib_typecheck.py` in the pipeline and describes it as the owner seam for a temporary review-loop bridge.
- The same README still describes `lowering/phase_stdlib.py` as a review-loop bridge quarantine.
- `docs/design/workflow_lisp_stdlib_lowering.md` still says `review-revise-loop` is only conditionally feasible in the current checkout and still refers to `ReviewReviseLoopExpr` as current feasibility framing.
- `docs/lisp_workflow_drafting_guide.md` still says primary-migration parity is pending the ordinary stdlib/generic composition lowering, which is now a direct contradiction if the primary docs are repaired without a narrow follow-up.
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc` already exports `review-revise-loop` and `review-revise-loop-proc`, owns `ReviewReportPath`, `ReviewFindingsJsonPath`, `ReviewFindings`, `ReviewDecision`, and `ReviewLoopResult`, and keeps `validate_review_findings_v1` on an explicit `command-result` boundary.
- `orchestrator/workflow_lisp/stdlib_contracts.py` already records `review-revise-loop` as `expr_type=ProcedureCallExpr` with adapter binding `validate_review_findings_v1`.
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py` is already a residual helper for ordinary lowering-contract shaping rather than a bridge lowerer.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json` already reports `non_regressive=true`.

## Hard Scope Limits

Implement only the bounded durable-authority reconciliation slice:

- repair `orchestrator/workflow_lisp/README.md` so it reflects the post-bridge owner map;
- repair `docs/design/workflow_lisp_stdlib_lowering.md` so it reflects the implemented ordinary stdlib route and keeps the command-adapter boundary explicit;
- update one additional current guidance surface only if a direct contradiction remains after those two primary repairs;
- run focused verification proving the docs match current source ownership and checked-in parity evidence.

Explicit non-goals:

- no frontend/runtime behavior changes under `orchestrator/workflow_lisp/` or `orchestrator/workflow/`;
- no edits to the accepted target design `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`;
- no edits to historical implementation architectures, execution plans, execution reports, `state/`, backlog queues, or run-state files just to erase bridge history;
- no new tests that assert literal documentation prose;
- no repo-wide stale-doc sweep outside the selected review-loop authority footprint.

Because this slice is documentation-only, focused existing proof surfaces plus the checked-in parity artifact are sufficient verification. A new orchestrator smoke run is not required unless a touched current-checkout claim proves false against the existing proof surfaces.

## File Ownership

Modify:

- `orchestrator/workflow_lisp/README.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`

Modify only if the primary repair leaves a direct contradiction:

- `docs/lisp_workflow_drafting_guide.md`
- `docs/index.md`

Inspect but do not modify unless a focused proof unexpectedly fails for an in-scope reason:

- `orchestrator/workflow_lisp/stdlib_contracts.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_key_migrations.py`

## Required Decisions

These are fixed for this slice:

- `README.md` is a current package map, not a migration diary.
- `docs/design/workflow_lisp_stdlib_lowering.md` should describe the implemented current-checkout route for `review-revise-loop` while keeping workflow-family parity and promotion caveats explicit.
- Historical bridge discussion belongs in the accepted target design and historical artifacts, not in current-checkout authority docs.
- `validate_review_findings_v1` must remain described as an explicit command/adaptor boundary with visible effects, never as hidden glue.
- If the narrow follow-up consistency pass is needed, prefer `docs/lisp_workflow_drafting_guide.md` over `docs/index.md` unless the contradiction is routing/discoverability rather than authoring guidance.
- If any focused proof surface contradicts the intended doc repair, stop and resolve the truth claim before broadening doc edits.

## Task Checklist

### Task 1: Audit The Current Authority Footprint And Pin The Exact Contradictions

**Files:**

- Inspect: `orchestrator/workflow_lisp/README.md`
- Inspect: `docs/design/workflow_lisp_stdlib_lowering.md`
- Inspect: `docs/lisp_workflow_drafting_guide.md`
- Inspect: `docs/index.md`
- Inspect: `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- Inspect: `orchestrator/workflow_lisp/stdlib_contracts.py`
- Inspect: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Inspect: `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json`

- [ ] Confirm the stale current-checkout phrases named in the work-item context still exist in the README and stdlib lowering doc.
- [ ] Confirm the implemented route from current source: `std/phase.orc` owns the public review-loop protocol, `stdlib_contracts.py` records `ProcedureCallExpr` plus `validate_review_findings_v1`, and `lowering/phase_stdlib.py` is only a residual result-shaping helper.
- [ ] Confirm the checked-in parity evidence still reports `non_regressive=true` for `design_plan_impl_stack`.
- [ ] Decide whether `docs/lisp_workflow_drafting_guide.md` still directly contradicts the repaired primary surfaces; inspect `docs/index.md` only for routing contradiction, not for general wording polish.

**Blocking verification after Task 1:**

- [ ] `rg -n "phase_stdlib_typecheck|temporary bridge|bridge quarantine" orchestrator/workflow_lisp/README.md`
- [ ] `rg -n "conditionally feasible|ReviewReviseLoopExpr" docs/design/workflow_lisp_stdlib_lowering.md`
- [ ] `rg -n "ordinary stdlib/generic composition lowering" docs/lisp_workflow_drafting_guide.md`
- [ ] `python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json').read_text(encoding='utf-8'))
assert report['non_regressive'] is True
print('design_plan_impl_stack non_regressive=', report['non_regressive'])
PY`

### Task 2: Repair `orchestrator/workflow_lisp/README.md` As A Truthful Current Package Map

**Files:**

- Modify: `orchestrator/workflow_lisp/README.md`

- [ ] Remove `phase_stdlib_typecheck.py` from the documented compile pipeline.
- [ ] Replace the stale `phase_stdlib_typecheck.py` component-map entry with current owner descriptions already proven by source: `std/phase.orc` owns the public review-loop protocol/body, `stdlib_contracts.py` owns compile-time lowering-contract inventory, and `lowering/phase_stdlib.py` owns only residual result-contract shaping helpers for the ordinary route.
- [ ] Remove “temporary bridge” and “bridge quarantine” phrasing from the README entirely.
- [ ] Keep the README focused on current module ownership; do not paste bridge-retirement history or parity-report narrative into the package map.

**Blocking verification after Task 2:**

- [ ] `rg -n "phase_stdlib_typecheck|temporary bridge|bridge quarantine" orchestrator/workflow_lisp/README.md`
- [ ] Re-read the README pipeline and component list to confirm every named owner exists in the checkout and no deleted review-loop seam remains.

### Task 3: Repair The Stdlib Lowering Status Doc And Apply One Narrow Follow-Up Consistency Edit Only If Needed

**Files:**

- Modify: `docs/design/workflow_lisp_stdlib_lowering.md`
- Modify only if needed: `docs/lisp_workflow_drafting_guide.md`
- Modify only if needed: `docs/index.md`

- [ ] Replace the obsolete conditional-feasibility block with current-checkout status wording: the ordinary imported stdlib route is implemented, while promotion remains gated by workflow-family parity evidence.
- [ ] Keep the `review-revise-loop` status table row honest: implemented authoring/lowering route, no review-loop-specific compiler branch, promotion caveats stated as parity evidence rather than “not yet implemented.”
- [ ] Remove or explicitly historical-label any wording that treats `ReviewReviseLoopExpr` as a current route.
- [ ] Keep `validate_review_findings_v1` described in command-adapter-contract terms: explicit command boundary, visible effects, no hidden glue.
- [ ] Update `docs/lisp_workflow_drafting_guide.md` only if it still says the ordinary stdlib/generic composition lowering is merely pending after the primary doc repair.
- [ ] Update `docs/index.md` only if its routing/discoverability text would still send a reader to a stale current-checkout story after the primary repair.

**Blocking verification after Task 3:**

- [ ] `rg -n "conditionally feasible|ReviewReviseLoopExpr" docs/design/workflow_lisp_stdlib_lowering.md`
- [ ] `rg -n "phase_stdlib_typecheck|temporary bridge|bridge quarantine" orchestrator/workflow_lisp/README.md docs/design/workflow_lisp_stdlib_lowering.md docs/lisp_workflow_drafting_guide.md docs/index.md`
- [ ] `rg -n "validate_review_findings_v1" docs/design/workflow_lisp_stdlib_lowering.md docs/lisp_workflow_drafting_guide.md orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`
- [ ] Re-read the touched guidance surface and confirm any remaining “pending” wording refers only to parity or promotion, not to the ordinary stdlib route existing at all.

### Task 4: Run Focused Existing Proof Surfaces And Final Artifact Checks

**Files:**

- No new files

- [ ] Run the narrowest relevant existing Workflow Lisp review-loop ownership tests first.
- [ ] Run focused build-artifact proof tests that confirm the command-boundary and seed-path contracts still match the repaired docs.
- [ ] Run a focused `design_plan_impl_stack` family proof surface and re-check the checked-in parity artifact.
- [ ] If any check fails, stop and distinguish whether the failure is:
  - an unrelated dirty-checkout failure outside this slice;
  - a stale current-checkout doc claim that needs correction; or
  - an in-scope proof failure that must be resolved before the slice can be called complete.

**Required final verification commands:**

- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_phase_stdlib_review_loop_is_owned_directly_in_std_phase_module -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_specializes_to_ordinary_typed_forms -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_shared_validation_accepts_review_revise_loop -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py::test_review_loop_owner_split_moves_stdlib_bridge_typing_out_of_typecheck_facade -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_review_loop_command_boundary_surfaces_validate_review_findings_adapter -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_review_loop_bundle_preserves_distinct_review_report_and_findings_seed_paths -q`
- [ ] `python -m pytest tests/test_workflow_lisp_build_artifacts.py::test_stdlib_contract_inventory_is_compile_time_only_and_not_serialized_into_frontend_build_artifacts -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_design_plan_impl_stack_orc_compiles_with_phase_family_contracts -q`
- [ ] `python - <<'PY'
import json
from pathlib import Path
report = json.loads(Path('artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.json').read_text(encoding='utf-8'))
assert report['non_regressive'] is True
print('design_plan_impl_stack non_regressive=', report['non_regressive'])
PY`

## Acceptance Checklist

- [ ] `orchestrator/workflow_lisp/README.md` no longer names deleted `phase_stdlib_typecheck.py` or a live temporary review-loop bridge.
- [ ] `docs/design/workflow_lisp_stdlib_lowering.md` describes `review-revise-loop` as the implemented ordinary stdlib route in the current checkout and keeps promotion/parity caveats explicit.
- [ ] Any additional guide/index edit is narrowly limited to eliminating one remaining direct contradiction or routing mismatch.
- [ ] `validate_review_findings_v1` remains described as an explicit command/adaptor boundary rather than hidden glue.
- [ ] Existing focused proof surfaces still pass without adding doc-literal tests.
- [ ] The checked-in `design_plan_impl_stack` parity artifact still reports `non_regressive=true`.
- [ ] No runtime/frontend behavior changes, no historical doc rewrites, no run-state edits, and no broad repo-wide doc cleanup were introduced.
