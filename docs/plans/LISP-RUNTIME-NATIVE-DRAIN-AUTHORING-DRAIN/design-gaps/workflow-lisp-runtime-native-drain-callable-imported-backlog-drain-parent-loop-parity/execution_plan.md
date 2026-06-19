# Workflow Lisp Runtime-Native Drain Callable Imported `backlog-drain` Parent-Loop Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm and preserve the selected callable imported `std/drain::backlog-drain` parent-loop parity slice without reopening broader runtime-native drain work: parent workflows must delegate to the child owner boundary, the child owner boundary must keep the shared terminal-finalization lane, and the recorded verification surfaces must match the current landed checkout.

**Architecture:** Treat the current checkout, not the stale prior narrative, as the baseline. `phase_drain.py` already materializes a terminal carrier and lowers callable child terminals through the shared helper-owned finalizer lane; focused child-boundary/runtime selectors and the downstream Design Delta consumer selector are green. Start by re-running that evidence. If the evidence stays green, do not touch shared lowering or stdlib tests; close the slice with fresh verification/reporting only. If the evidence regresses, apply the narrow shared lowering/test repair already bounded by the implementation architecture and re-prove it with the same focused selectors.

**Tech Stack:** Workflow Lisp lowering in `orchestrator/workflow_lisp/lowering/phase_drain.py`, shared stdlib source in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`, focused drain stdlib/runtime tests in `tests/test_workflow_lisp_drain_stdlib.py`, route-accounting checks in `tests/test_workflow_lisp_stdlib_form_migration.py`, downstream consumer coverage in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`, counted verification metadata in `docs/workflow_lisp_g6_verification_gate.json`, and manifest validation in `tests/test_workflow_lisp_verification_gate.py`.

**Plan Authority:** Execute only the bounded callable-parent-loop parity slice defined by `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-parent-loop-parity/implementation_architecture.md`, while preserving the authority split from `docs/design/workflow_lisp_runtime_native_drain_authoring.md` and `docs/design/workflow_lisp_frontend_specification.md`. If fresh evidence confirms the current checkout already satisfies this slice, closure/reporting is the intended outcome.

---

## Fixed Inputs

Treat these as the implementation authority for this slice:

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/capability_status_matrix.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/workflow_lisp_g6_verification_gate.json`
- `tests/README.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-parent-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-callable-imported-backlog-drain-boundary/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-stdlib-backlog-drain-parent-loop-contract/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-parent-terminal-reprojection-over-imported-backlog-drain/implementation_architecture.md`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain/iterations/25/design-gap-architect/work_item_context.md`

## Scope Lock

This plan still owns only the bounded shared callable-parent-loop parity slice selected for iteration 25:

- keep the promoted parent route as one call to `std/drain::backlog-drain`;
- keep the child `std/drain::backlog-drain` workflow as the owner of `repeat_until`;
- preserve the child owner boundary's shared terminal-carrier plus shared finalizer lane;
- keep callable-route assertions and runtime proof centered on the child owner boundary rather than the parent caller;
- keep route-accounting and gate-manifest surfaces aligned with the current landed meaning of the proof; and
- record downstream consumer status without converting unrelated family work into a blocker for this slice.

This plan does **not** own:

- changing the accepted `std/drain` parent-loop contract itself;
- rewriting `workflows/library/lisp_frontend_design_delta/*.orc`;
- reopening the later parent-terminal reprojection slice;
- request-record, bootstrap, publication, transition, `std/phase`, or child-phase transport redesign;
- unrelated private-exec bootstrap diagnostic cleanup;
- new adapters, scripts, report parsing, pointer protocols, or family-local wrappers; or
- YAML-primary promotion.

## Current Checkout Facts

Use these as the live baseline instead of the stale prior failure narrative:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` remains the accepted owner contract: selector `BLOCKED` exists, selected-item `CONTINUE` re-enters selection and increments `items-processed`, empty versus completed is decided from carried loop state, and authored terminal effects route through `finalize-drain-terminal`.
- `orchestrator/workflow_lisp/lowering/phase_drain.py` now lowers callable child terminal behavior through:
  - a generated `terminal_carrier` step that materializes terminal-only statuses from the accumulator; and
  - `lower_shared_drain_terminal_result(...)`, which owns the shared finalizer lane for `EMPTY`, `COMPLETED`, `BLOCKED`, and `EXHAUSTED`.
- `tests/test_workflow_lisp_drain_stdlib.py` already inspects the generated child owner boundary for the selected proof lanes:
  - `test_lowering_backlog_drain_uses_repeat_until_with_typed_accumulator`;
  - `test_compile_stage3_module_preserves_imported_backlog_drain_as_callable_boundary`;
  - `test_backlog_drain_contract_inventory_matches_promoted_stdlib_route`;
  - `test_stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects`;
  - `test_compile_stage3_module_rebinds_imported_selector_provider_metadata`; and
  - `test_compile_stage3_module_rebinds_same_file_selector_provider_metadata`.
- Fresh repo-root verification from this checkout:
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "preserves_imported_backlog_drain_as_callable_boundary or backlog_drain_contract_inventory_matches_promoted_stdlib_route or stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects" -q` -> `9 passed, 37 deselected in 7.73s`
  - `python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -k "backlog_drain_stdlib_vector_compiles_on_promoted_route" -q` -> `1 passed, 12 deselected in 0.34s`
  - `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py --collect-only -q -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice"` -> `2/80 tests collected (78 deselected) in 0.28s`
  - `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice" -q` -> `2 passed, 78 deselected in 1.11s`
- `docs/workflow_lisp_g6_verification_gate.json` already describes `tests/test_workflow_lisp_drain_stdlib.py` as the promoted callable `std/drain` owner-boundary proof. If that file stays unchanged, the dedicated verification-gate suite does not need to rerun for this slice.

## Locked Decisions

- The default expected outcome is **no shared lowering or stdlib-test edit**. Code changes are justified only if the Task 1 evidence contradicts the current checkout facts above.
- Keep the main semantic proof in `tests/test_workflow_lisp_drain_stdlib.py`. `tests/test_workflow_lisp_stdlib_form_migration.py` stays a route-identity lane, not a second semantic parity suite.
- Keep `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` semantically unchanged unless fresh evidence proves the accepted owner contract itself is no longer expressible, which would be a new scope discussion rather than an automatic edit here.
- Do not reintroduce parent-owned inline loop fallback, Design-Delta-specific lowering branches, wrappers, or adapter-based terminal repair.
- If a regression appears in source-map or hidden-input provenance while repairing the child owner lane, prefer the narrowest generic fix in `orchestrator/workflow_lisp/lowering/workflow_calls.py` or `orchestrator/workflow_lisp/lowering/core.py`.
- If any test is added or renamed while repairing a regression, run `pytest --collect-only` on the touched module before claiming coverage exists.

## File Map

Inspect first:

- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `docs/workflow_lisp_g6_verification_gate.json`

Modify only if fresh evidence disproves the current landed baseline:

- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `tests/test_workflow_lisp_drain_stdlib.py`

Modify only if a repair exposes narrowly coupled provenance issues:

- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
- `orchestrator/workflow_lisp/lowering/core.py`

Modify only if wording is stale **and** you intentionally change that file:

- `docs/workflow_lisp_g6_verification_gate.json`

Leave unchanged unless a newly reproduced failure explicitly points there:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `workflows/library/lisp_frontend_design_delta/drain.orc`

## Task 1: Refresh The Landed Callable-Parity Baseline

**Files:**

- No edits before baseline
- Inspect:
  - `orchestrator/workflow_lisp/lowering/phase_drain.py`
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `docs/workflow_lisp_g6_verification_gate.json`

- [ ] Run the focused shared parity selector from the repo root.

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "preserves_imported_backlog_drain_as_callable_boundary or backlog_drain_contract_inventory_matches_promoted_stdlib_route or stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects" -q
```

- [ ] Run the narrow route-identity selector separately so route-accounting evidence stays distinct from semantic parity evidence.

```bash
python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -k "backlog_drain_stdlib_vector_compiles_on_promoted_route" -q
```

- [ ] Run collect-only on the downstream Design Delta consumer-status selector so the recorded gate stays runnable.

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py --collect-only -q -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice"
```

- [ ] Run the downstream Design Delta consumer-status selector as informational consumer status for this slice.

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice" -q
```

- [ ] Confirm the checkout facts directly in code/tests:
  - callable child terminal behavior flows through a generated terminal carrier plus `lower_shared_drain_terminal_result(...)`;
  - the child `std/drain::backlog-drain` workflow, not the parent caller, owns `repeat_until`;
  - the focused stdlib tests already inspect the child owner boundary; and
  - `docs/workflow_lisp_g6_verification_gate.json` already describes the callable owner-boundary proof accurately.

- [ ] Branch strictly from fresh evidence:
  - if the focused stdlib selector, route-identity selector, and downstream consumer-status commands above all succeed and the code/test reads match the facts above, treat the parity repair as already landed and continue to Task 2 with **no code edits**; or
  - if any selector fails or the child-boundary/shared-finalizer facts are missing, stop the closure path and continue to Task 3 before touching verification metadata.

Expected:

- fresh verification evidence replaces the stale failing-baseline narrative; and
- the implementer has an explicit go/no-go decision for whether any repair work still exists.

## Task 2: Close The Slice If The Baseline Is Confirmed

**Files:**

- No source edits required on the expected green path

- [ ] If Task 1 stays green, do **not** edit:
  - `orchestrator/workflow_lisp/lowering/phase_drain.py`;
  - `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`;
  - `tests/test_workflow_lisp_drain_stdlib.py`;
  - `tests/test_workflow_lisp_stdlib_form_migration.py`; or
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`.

- [ ] Record in the implementation report that the selected callable-parent-loop parity gap is already satisfied in the current checkout, citing:
  - the Task 1 selector outputs;
  - the child owner-boundary/shared-finalizer code evidence; and
  - the downstream consumer pass instead of a stale `workflow_boundary_type_invalid` blocker narrative.

- [ ] Keep the closure statement scoped:
  - this slice is satisfied because the selected shared parity proof is landed; and
  - any further work now belongs to a newly observed bounded gap or a different already-authored slice, not to this plan.

Expected:

- the work item closes without duplicating landed code changes; and
- the selected scope remains preserved instead of being silently retargeted.

## Task 3: Repair The Shared Child Owner Lane Only If Task 1 Regresses

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify: `tests/test_workflow_lisp_drain_stdlib.py`
- Inspect only if needed:
  - `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
  - `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - `orchestrator/workflow_lisp/lowering/core.py`

- [ ] Keep `_callable_backlog_drain_enabled()` and the promoted parent call boundary intact.

- [ ] Restore the child owner boundary to the accepted shared owner-lane semantics:
  - parent lowers to one call to `std/drain::backlog-drain`;
  - child owns `repeat_until`;
  - terminal behavior flows through the terminal carrier plus shared helper-owned finalization lane;
  - `EMPTY` versus `COMPLETED` is decided from carried loop state;
  - selector `BLOCKED` preserves compatibility blocker `user_decision_required`;
  - selected-item `CONTINUE` increments `items_processed`, carries `continued.run-state`, and preserves the carried summary path for finalization;
  - gap `CONTINUE` re-enters without incrementing the count; and
  - exhausted exit keeps the existing shared compatibility meaning rather than a custom wrapper route.

- [ ] Keep the proof centered on the child owner boundary:
  - parent assertions stop at delegation;
  - child assertions own `repeat_until`, managed write roots, provider rebinding, accumulator fields, and terminal side effects.

- [ ] If you add or rename tests while repairing the regression, run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py --collect-only -q
```

- [ ] Do **not** add:
  - family-local wrappers;
  - parent-owned inline loop fallback;
  - command/adapter workarounds;
  - report parsing; or
  - pointer sidecar protocols.

Expected:

- the regression is repaired in the shared owner lane only; and
- the fix remains inside the original bounded callable-parent-loop parity scope.

## Task 4: Align Verification Metadata Only If It Actually Changes

**Files:**

- Modify only if needed: `docs/workflow_lisp_g6_verification_gate.json`

- [ ] Leave `docs/workflow_lisp_g6_verification_gate.json` untouched if Task 1 confirms the existing reason text still matches the landed callable owner-boundary proof.

- [ ] If you do edit `docs/workflow_lisp_g6_verification_gate.json`, keep the suite roster unchanged and limit the edit to wording that reflects the same selected callable-parity proof surface.

- [ ] If that file changes, rerun the dedicated manifest-validation suite before claiming verification is complete.

```bash
python -m pytest tests/test_workflow_lisp_verification_gate.py -q
```

Expected:

- any gate-manifest edit is paired with the suite that validates it; and
- no manifest churn is introduced when the current wording is already accurate.

## Task 5: Final Verification And Closure Record

**Files:**

- No new edits unless verification exposes a real regression

- [ ] If Task 1 stayed green and Tasks 3-4 made no changes, reuse the Task 1 command output as the final evidence for this slice.

- [ ] If Task 3 changed shared lowering/tests, rerun:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "preserves_imported_backlog_drain_as_callable_boundary or backlog_drain_contract_inventory_matches_promoted_stdlib_route or stdlib_backlog_drain_executes_promoted_route_with_terminal_side_effects" -q
```

- [ ] If Task 3 changed route-accounting-adjacent behavior, rerun:

```bash
python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -k "backlog_drain_stdlib_vector_compiles_on_promoted_route" -q
```

- [ ] If Task 3 changed shared lowering in a way that could affect the downstream consumer, rerun collect-only on the downstream consumer-status selector:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py --collect-only -q -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice"
```

- [ ] Then rerun the downstream consumer-status selector:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "still_requires_family_adoption_before_stdlib_delegation or current_route_stays_handwritten_pending_family_adoption_slice" -q
```

- [ ] If Task 4 changed `docs/workflow_lisp_g6_verification_gate.json`, rerun:

```bash
python -m pytest tests/test_workflow_lisp_verification_gate.py -q
```

- [ ] Record the closure evidence explicitly:
  - whether any shared source edit was required at all;
  - whether `std/drain.orc` stayed unchanged;
  - whether the focused shared parity selector passed;
  - whether the optional route-identity selector was rerun and how it behaved;
  - whether the downstream Design Delta consumer selector passed; and
  - whether the verification-gate suite ran because the manifest changed.

Expected:

- the slice closes with current, bounded evidence instead of stale assumptions; and
- the plan no longer instructs implementers to re-fix already-landed callable-parent-loop parity.

## Acceptance Checklist

- the plan baseline matches the current checkout rather than an obsolete failing narrative;
- parent workflows still delegate to one call to `std/drain::backlog-drain`;
- the child `std/drain::backlog-drain` workflow owns `repeat_until`;
- the child owner boundary keeps the shared terminal carrier plus shared finalizer lane, or is repaired back to that shape if Task 1 proves a regression;
- callable-route proof remains centered on the child owner boundary, not the parent caller;
- `docs/workflow_lisp_g6_verification_gate.json` is either left unchanged because it already matches the proof or is validated by `tests/test_workflow_lisp_verification_gate.py` after any edit; and
- downstream consumer status is recorded from fresh evidence without carrying forward the stale blocked-selector story.
