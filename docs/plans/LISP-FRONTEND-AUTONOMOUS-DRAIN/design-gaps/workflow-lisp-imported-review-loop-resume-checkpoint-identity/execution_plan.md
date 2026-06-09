# Workflow Lisp Imported Review-Loop Resume Checkpoint Identity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Confirm that the selected imported stdlib `review-revise-loop` checkpoint-identity slice is satisfied in the current checkout, and make only the narrowest correction if focused verification disproves the projection-owned frame-key contract.

**Architecture:** Keep the imported stdlib lowering route, runtime-plan checkpoint schema, `WorkflowStateProjection`, and typed `repeat_until` executor as the only authority chain for this slice. This plan is audit-first because the current checkout already appears to carry the frame-key accessor, typed loop persistence path, and focused interruption/resume proof; execution should verify that landed behavior matches the selected migration contract instead of assuming fresh implementation work is required.

**Tech Stack:** Python 3, Workflow Lisp compile fixtures, shared workflow runtime and state projection code, `pytest`

---

## Fixed Inputs

Treat these as implementation authority for this slice:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/work_definition_model.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/state.md`
- `docs/steering.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/prerequisite-selector/selection.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/4/recovered-gap/work-item/blocked-implementation-recovery.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/5/blocked-recovery-decision.json`
- `artifacts/review/LISP-MIGRATION-PARITY-DRAIN/workflow-lisp-design-plan-impl-stack-review-loop-parity-plan-review.json`

Related implementation architectures that are reused but not reopened here:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-loop-report-findings-path-split/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`

## Current Checkout Facts

Do not spend implementation time rediscovering these facts unless a targeted check disproves one:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this selected slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- The selected gap is `workflow-lisp-imported-review-loop-resume-checkpoint-identity`, and its `plan_target_path` is `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-imported-review-loop-resume-checkpoint-identity/execution_plan.md`.
- The compile proof `tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route` already proves:
  - the imported review-loop fixture lowers to one top-level loop named `rl_rl18_5_h_1__loop`;
  - the runtime plan emits `RuntimeResumeCheckpoint(node_id="root.rl_rl18_5_h_1__loop", presentation_key="rl_rl18_5_h_1__loop")`;
  - `WorkflowStateProjection.repeat_until_nodes["root.rl_rl18_5_h_1__loop"].frame_key == "rl_rl18_5_h_1__loop"`;
  - iteration-owned nested call-boundary checkpoints already point back to `iteration_owner_node_id == "root.rl_rl18_5_h_1__loop"`.
- `orchestrator/workflow/state_projection.py` already exposes `WorkflowStateProjection.repeat_until_frame_key(...)` as the read-only accessor for the canonical typed `repeat_until` frame key.
- `orchestrator/workflow/loops.py` already resolves typed `repeat_until` persistence through `_typed_repeat_until_frame_key(...)`, validates projection consistency, and uses the canonical frame key instead of relying on an implicit top-level `step_name` fallback for typed loop metadata.
- The focused runtime proof `tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint` now binds only true public inputs, reaches the forced `REVISE` interruption after loop entry, persists state under the projection-owned frame key, and resumes the same run successfully.
- `orchestrator/workflow/resume_planner.py` already treats the projection presentation key as the repeat-until lookup authority; no planner change is expected unless a focused selector disproves parity.
- The deterministic verification commands recorded in `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json` all passed in this checkout on 2026-06-03, including the full interruption/resume proof.

## Hard Scope Limits

Implement only this bounded prerequisite slice:

- confirm that typed imported review-loop execution persists `repeat_until` frame state under the projection-owned loop frame key;
- confirm that the same key remains authoritative across `steps`, `repeat_until`, iteration child presentation prefixes, and resume lookup;
- confirm that the focused imported review-loop runtime proof exercises the current runtime-owned hidden write-root policy and still proves the selected checkpoint contract;
- make only the minimum code or test correction required if one of those focused checks fails in the current checkout.

Explicit non-goals:

- no redesign of stdlib review-loop specialization, findings validation, reusable-state sidecars, `resume-or-start`, workflow input defaults, or the family-level `design_plan_impl_stack` parity rewrite;
- no changes to command bundle-path ownership, `ORCHESTRATOR_OUTPUT_BUNDLE_PATH`, managed write-root policy, command adapters, runtime-native effects, pointer/report authority, or hidden shell/Python glue;
- no general state-key redesign for every structured control form;
- no spec edits, migration-promotion policy work, or unrelated frontend/runtime refactors outside this typed loop persistence seam;
- no code churn solely to restate behavior that is already present and already proven by the focused acceptance selectors.

## File Ownership

Inspect first:

- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/resume_planner.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_state_projection.py`
- `tests/test_workflow_lowering_invariants.py`

Modify only if a focused failing check proves the current checkout does not satisfy the selected contract:

- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/resume_planner.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_state_projection.py`
- `tests/test_workflow_lowering_invariants.py`

Reused but not owned here:

- `orchestrator/workflow/runtime_plan.py`
- `orchestrator/workflow/lowering.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/state.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`

Do not modify unless a focused verification failure proves this plan incomplete:

- `specs/dsl.md`
- `specs/state.md`
- command adapter code under `scripts/`
- unrelated Workflow Lisp review-loop, defaults, reusable-state, or family parity modules

## Required Contract Decisions

These decisions are fixed for execution and should not be reopened during coding:

- The persisted identity for a typed imported review-loop frame is the projection-owned frame presentation key for the `repeat_until` node.
- Typed `repeat_until` execution must obtain that frame key from shared projection metadata when typed executable loop metadata exists.
- The same canonical frame key must drive:
  - `state.steps[frame_key]`
  - `state.repeat_until[frame_key]`
  - `state.steps[f"{frame_key}[i].<nested>"]`
  - restart and resume lookup for that loop frame
- If typed loop metadata exists but the projection cannot supply a frame key, execution must fail loudly with a runtime integrity-style error. Do not silently fall back to `step_name`, `node_id`, or any generated alias.
- Untyped or legacy loop execution stays on the existing `step_name` path.
- The focused imported review-loop proof must not bind runtime-owned `__write_root__*` inputs manually and must instead rely on the runtime-owned route selected by the command-result bundle-path slice.

## Execution Units

### Unit 1: Audit Landed Frame-Key Authority

Owns:

- `orchestrator/workflow/state_projection.py`
- `orchestrator/workflow/loops.py`
- `orchestrator/workflow/resume_planner.py`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_state_projection.py`

Responsibilities:

- prove from code and focused selectors that the canonical top-level loop frame key comes from shared projection metadata and remains the only typed `repeat_until` persistence/resume authority;
- confirm the imported review-loop runtime fixture no longer violates the runtime-owned hidden write-root policy;
- confirm the compile proof, projection helper, runtime executor, and resume proof all refer to the same loop frame identity.

### Unit 2: Conditional Narrow Correction

Owns only the minimal file set implicated by an actual failing selector.

Responsibilities:

- if Unit 1 selectors pass and the code matches the contract, make no edits and carry the no-op result forward;
- if a focused selector fails, patch only the smallest executor/projection/resume/test seam required to restore the projection-owned frame-key contract;
- rerun only the failing selector first, then the dependent focused selectors, before broadening back to the full recorded command set.

### Unit 3: End-To-End Acceptance And Closure

Owns:

- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_resume_command.py`
- `tests/test_workflow_state_projection.py`
- `tests/test_workflow_lowering_invariants.py`

Responsibilities:

- rerun the deterministic recorded verification commands in the intended order;
- keep the full interruption/resume proof as the final acceptance gate for this slice instead of an early task blocker;
- close the slice as already satisfied if all selectors pass without code edits, or as narrowly corrected if Unit 2 had to patch a real regression.

## Task Checklist

### Task 1: Audit The Current Checkout Against The Selected Contract

**Files:**

- Inspect: `orchestrator/workflow/state_projection.py`
- Inspect: `orchestrator/workflow/loops.py`
- Inspect: `orchestrator/workflow/resume_planner.py`
- Inspect: `tests/test_workflow_lisp_key_migrations.py`
- Inspect: `tests/test_resume_command.py`
- Inspect: `tests/test_workflow_state_projection.py`

- [ ] Confirm `WorkflowStateProjection.repeat_until_frame_key(...)` is the read-only accessor used to expose the canonical typed loop frame key.
- [ ] Confirm typed `repeat_until` execution resolves the canonical frame key once, validates projection consistency, and reuses that key for persisted frame state instead of inventing a second authority path.
- [ ] Confirm the focused imported review-loop runtime proof binds only public inputs and relies on the runtime-owned write-root route rather than manual `__write_root__*` overrides.
- [ ] Confirm the compile proof, projection assertions, and resume-path tests all target the same authored/generated frame key.

**Blocking verification after Task 1:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_key_migrations.py tests/test_resume_command.py tests/test_workflow_state_projection.py tests/test_workflow_lowering_invariants.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route -q`
- [ ] `python -m pytest tests/test_resume_command.py -k "repeat_until_runtime_plan_checkpoint_metadata_preserves_projection_resume_authority or frontend_generated_loop_recur_runtime_plan_preserves_repeat_until_resume_authority" -q`
- [ ] `python -m pytest tests/test_workflow_state_projection.py -k "projection_formats_repeat_until_and_for_each_iteration_step_keys" -q`

### Task 2: Patch Only If The Audit Finds A Real Mismatch

**Files:**

- Modify only if Task 1 disproves the contract: `orchestrator/workflow/loops.py`
- Modify only if Task 1 disproves the contract: `orchestrator/workflow/state_projection.py`
- Modify only if Task 1 disproves the contract: `orchestrator/workflow/resume_planner.py`
- Modify only if Task 1 disproves the contract: `tests/test_workflow_lisp_key_migrations.py`
- Modify only if Task 1 disproves the contract: `tests/test_resume_command.py`
- Modify only if Task 1 disproves the contract: `tests/test_workflow_state_projection.py`
- Modify only if Task 1 disproves the contract: `tests/test_workflow_lowering_invariants.py`

- [ ] If every Task 1 selector passes and the inspected code matches the contract, record this task as intentionally skipped and make no edits.
- [ ] If a Task 1 selector fails, patch only the narrow executor/projection/resume/test seam implicated by that failure.
- [ ] Preserve untyped `repeat_until` behavior and the current runtime-owned hidden write-root rejection policy.
- [ ] Rerun the exact failing selector immediately after the patch before running any broader suite.
- [ ] If any tests are added or renamed while fixing a real mismatch, run `pytest --collect-only` on the touched modules before broader verification.

**Blocking verification after Task 2 only when edits were required:**

- [ ] Rerun the exact failing selector from Task 1 until it passes.
- [ ] Rerun every narrower dependent selector affected by the patch before proceeding to Task 3.

### Task 3: Run The Full Interruption/Resume Acceptance Proof

**Files:**

- No additional maintained source files unless Task 2 required a fix.

- [ ] Run the focused imported review-loop interruption/resume proof only after Task 1 audit is complete and any real Task 2 correction is finished.
- [ ] Confirm the first run fails for the intended forced interruption after loop entry rather than for `managed_write_root_override` or another pre-loop failure.
- [ ] Confirm persisted state contains both `repeat_until[frame_key]` and `steps[frame_key]` for the canonical projection-owned frame key.
- [ ] Confirm resume completes successfully through the same run and the same top-level loop frame identity.

**Blocking verification after Task 3:**

- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint -q`

### Task 4: Re-Run The Recorded Focused Suite And Close The Slice

**Files:**

- No new files are required for this task.

- [ ] Run the remaining recorded focused no-regression command after the end-to-end proof:
  - `python -m pytest tests/test_workflow_lowering_invariants.py::test_repeat_until_nested_call_and_match_surfaces_keep_stable_body_step_ids -q`
- [ ] If Task 2 made no edits and all recorded selectors pass, treat the selected work item as already satisfied in the current checkout and stop.
- [ ] If Task 2 made edits, rerun the full recorded command set from `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json` in the same order before closing.
- [ ] Record in the execution handoff whether this slice closed as a no-op acceptance confirmation or as a narrow corrective patch.

## Expected Outcome

Successful execution of this plan yields one of two valid outcomes, both within scope:

- **Acceptance-confirmed no-op:** the current checkout already satisfies the imported review-loop checkpoint-identity slice, and the recorded focused selectors prove it without code changes.
- **Narrow corrective patch:** a focused selector exposes a real mismatch, the minimal executor/projection/resume/test seam is fixed, and the same recorded selectors then prove the contract.

Any result that expands beyond the selected frame-key persistence/resume contract is out of scope for this plan.
