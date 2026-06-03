# Workflow Lisp Design/Plan/Impl Stack Review-Loop Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining `design_plan_impl_stack` family parity gap by moving the real review/revise behavior into the reusable library `.orc` phase workflows, carrying validated findings through revise/fix, applying approved-only `resume-or-start` reuse at the example wrapper boundary, restoring the YAML public defaults on that wrapper, and refreshing family parity evidence.

**Architecture:** Keep the three library phase modules as the reusable family surface and keep `workflows/examples/design_plan_impl_review_stack_v2_call.orc` as a thin promoted wrapper. Each library phase adopts imported `std/phase.review-revise-loop` composition with family-local internal loop contracts that preserve report-path types, carry `ReviewFindings` internally, and project only approved results back to the existing outward phase records. The wrapper imports those library phases, restores the YAML defaults, wraps each phase call in approved-only `resume-or-start`, preserves the existing public `StackOutput`, and relies on the already-selected findings, reusable-state, default, and promotion-report substrate instead of reopening generic frontend or runtime work.

**Tech Stack:** Workflow Lisp `.orc`, shared Workflow Lisp lowering/runtime, `std/phase` review-loop and `resume-or-start`, certified findings/reusable-state adapters, `pytest`, `python -m orchestrator`

---

## Fixed Inputs

Treat these as implementation authority:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/steering.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/work_item_context.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/6/design-gap-architect/check_commands.json`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-design-plan-impl-stack-review-loop-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-findings-structured-dataflow/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-migration-promotion-parity-report-gate/implementation_architecture.md`

Current checkout facts that must not be rediscovered during implementation:

- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json` is empty, so no later ledger event supersedes this selected family slice.
- `docs/steering.md` is empty in this checkout and does not widen scope.
- `workflows/library/tracked_design_phase.orc`, `workflows/library/tracked_plan_phase.orc`, and `workflows/library/design_plan_impl_implementation_phase.orc` are still single-pass draft or execute plus one review workflows.
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc` still duplicates phase logic locally instead of being a thin wrapper over the library modules.
- The YAML baseline still owns the real bounded review/revise behavior and the example YAML still declares public defaults that the `.orc` wrapper must restore.
- `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/design_plan_impl_stack.md` still records `Non-regressive: false` and still identifies the full YAML review/revise mechanic as the unresolved debt for this family.
- The provider and prompt extern manifests for this family already declare the expected design, plan, and implementation draft/review/revise bindings, and `design_plan_impl_stack.commands.json` is intentionally empty.
- This slice consumes already-selected generic findings, reusable-state, defaults, review-loop, and parity-report work. If those prerequisites are broken, stop and return the blocker rather than editing generic substrate here.

## Hard Scope Limits

Implement only this bounded family slice:

- rewrite the three library phase modules around imported `std/phase.review-revise-loop`;
- carry validated findings internally through review/revise or fix iterations;
- route approved, blocked, and exhausted loop terminals back onto the current family outward behavior;
- make the example `.orc` file a thin wrapper that imports the library phases, restores YAML-compatible defaults, and applies approved-only `resume-or-start` around the phase calls;
- update only the focused migration, stdlib, recovery, and parity tests needed to prove this family now consumes the already-landed generic surfaces;
- rerun the existing promotion-report command after the family actually uses those surfaces.

Explicit non-goals:

- no new generic review-loop, findings, reusable-state, workflow-default, or promotion-report design work;
- no edits to the YAML baseline workflows;
- no new runtime-native effects, inline Python or shell workflow glue, pointer-as-state behavior, or markdown report parsing;
- no widening of the public family outputs to include findings or reusable-state sidecars;
- no generic compiler, runtime, or adapter redesign unless a prerequisite proof fails and the blocker is handed back to the owning slice.

## File Ownership

Modify:

- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_phase_stdlib.py`

Inspect first, then modify only if the family proof requires it:

- `tests/test_neurips_plan_gate_recovery.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`

Do not modify unless focused verification proves the plan incomplete:

- `workflows/examples/design_plan_impl_review_stack_v2_call.yaml`
- `workflows/library/tracked_design_phase.yaml`
- `workflows/library/tracked_plan_phase.yaml`
- `workflows/library/design_plan_impl_implementation_phase.yaml`
- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`
- generic substrate under `orchestrator/workflow_lisp/` and `orchestrator/workflow/`

## Required Family Decisions

These are fixed implementation decisions for this slice:

- The reusable family surface remains the library phase modules with stable shared-root module identities:
  - `library/tracked_design_phase`
  - `library/tracked_plan_phase`
  - `library/design_plan_impl_implementation_phase`
- Each library phase must define internal completed/input/terminal loop contracts before projecting back to the outward family records.
- Review reports stay on the family review-report path types rooted under `artifacts/review`.
- Findings use the already-selected `std/phase.ReviewFindings` carrier with `items_path` rooted under `artifacts/work`.
- Evidence artifact identities such as `design_path`, `plan_path`, and `execution_report_path` remain carried authoritative state; reviewers may judge them but must not replace them by returning substitute artifact paths.
- Findings remain internal phase state and revise/fix input. They do not become public outputs of the wrapper workflow.
- `resume-or-start` is applied only at the thin example wrapper boundary, and only approved terminal results are reusable for this family.
- Wrapper defaults are restored exactly from the YAML example for these seven public inputs:
  - `brief_path`
  - `design_target_path`
  - `design_review_report_target_path`
  - `plan_target_path`
  - `plan_review_report_target_path`
  - `execution_report_target_path`
  - `implementation_review_report_target_path`
- Extern manifest names remain stable unless a concrete family wiring mismatch forces a narrow fix.

## Implementation Units

### Unit 1: Rewrite The Library Phases As Real Review/Revise Workflows

Owns:

- `workflows/library/tracked_design_phase.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`

Stable responsibilities:

- import and use the shared `std/phase` review-loop surface;
- replace single-pass review with iterative review/revise or review/fix behavior;
- define family-local internal records and terminal unions that satisfy the shared review-loop contract without widening the public family records;
- preserve the current outward output record names and field meanings;
- keep design `BLOCK` as explicit non-success and keep plan or implementation exhaustion as deterministic non-success rather than a successful outward `REVISE`.

### Unit 2: Keep Findings Internal And Preserve Artifact Authority

Owns:

- the same three library phase modules
- `tests/test_workflow_lisp_phase_stdlib.py`
- focused family assertions in `tests/test_workflow_lisp_key_migrations.py`

Stable responsibilities:

- revise or fix hooks receive validated `ReviewFindings`, not extracted JSON glue;
- findings survive loop state and resume through the already-selected structured-findings path;
- outward phase outputs continue to expose only the family’s current path and decision fields;
- approved outputs come from the last approved loop state, not the first review pass.

### Unit 3: Thin Wrapper Defaults And Approved-Only Reuse

Owns:

- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- focused family assertions in `tests/test_workflow_lisp_key_migrations.py`

Stable responsibilities:

- remove duplicated example-local phase workflow definitions;
- import and call the library modules;
- restore the YAML public defaults on the wrapper entry workflow;
- wrap design, plan, and implementation phase calls in approved-only `resume-or-start`;
- keep context bootstrap, reusable-state handles, write roots, and other plumbing off the public boundary;
- preserve the current public `StackOutput` fields.

### Unit 4: Focused Family Proof And Parity Evidence Refresh

Owns:

- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_neurips_plan_gate_recovery.py` only if family reuse coverage needs adjustment
- `tests/test_workflow_lisp_migration_parity.py` and `parity_targets.json` only if the family parity assertions still point at stale selectors or the explicit-input dry-run path

Stable responsibilities:

- prove the library phases are no longer single-pass;
- prove the wrapper imports those phases instead of shadowing them locally;
- prove defaults and approved-only reuse are exercised on the family wrapper;
- rerun `orchestrator migration-parity` and verify the family report either clears the deprecated YAML review-loop mechanic or names a different explicit blocker.

## Task Checklist

### Task 1: Run Prerequisite Proofs And Fail Fast On Shared-Slice Regressions

**Files:**

- Reference only: `tests/test_workflow_lisp_key_migrations.py`
- Reference only: `tests/test_neurips_plan_gate_recovery.py`

- [ ] Run the shared prerequisite proofs for imported review-loop lowering, resume-safe review-loop resume, promoted-entry hidden-context bootstrap, approved-only reusable-state parity, and reusable-state validator or loader recovery.
- [ ] If any prerequisite proof fails, stop immediately and report the blocker against the owning prerequisite implementation-architecture file instead of patching shared substrate here.
- [ ] Record that the progress ledger is empty and therefore does not override the selected family scope.

**Blocking verification after Task 1:**

- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_parity_fixture_compiles_to_resume_safe_repeat_until_via_imported_stdlib_route -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_review_loop_imported_stdlib_route_resumes_after_revise_checkpoint -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py::test_resume_or_start_plan_gate_reusable_state_parity_path -q`
- [ ] `python -m pytest tests/test_neurips_plan_gate_recovery.py -k "plan_gate_recovery_resume_validator or plan_gate_recovery_loader" -q`

### Task 2: Rewrite The Library Phase Modules Around Imported Review Loops

**Files:**

- Modify: `workflows/library/tracked_design_phase.orc`
- Modify: `workflows/library/tracked_plan_phase.orc`
- Modify: `workflows/library/design_plan_impl_implementation_phase.orc`
- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify only if one more family assertion is needed: `tests/test_workflow_lisp_phase_stdlib.py`

- [ ] Change each library file to expose the stable shared-root module identity chosen by the earlier import-path slice.
- [ ] Replace draft or execute once plus review once behavior with imported `review-revise-loop` composition.
- [ ] Define phase-local internal completed records, input records, and terminal unions so the loop can carry approved state, findings, and any explicit non-success terminals while keeping the public family output records unchanged.
- [ ] Keep the existing provider and prompt extern names for design, plan, and implementation review or revise paths.
- [ ] Carry validated findings into revise or fix hooks and keep findings internal to phase state.
- [ ] Preserve artifact authority by carrying forward draft or execution artifacts rather than accepting reviewer-authored replacement paths.
- [ ] Route design `BLOCK`, plan exhaustion, and implementation exhaustion to deterministic non-success family behavior rather than widening the outward success surface.
- [ ] Add or revise focused family migration tests so they prove the library modules are no longer single-pass and still compile as the reusable family surface.

**Blocking verification after Task 2:**

- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or findings or exhausted" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture" -q`

### Task 3: Make The Example `.orc` File A Thin Defaulted Wrapper With Approved-Only Reuse

**Files:**

- Modify: `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- Modify: `tests/test_workflow_lisp_key_migrations.py`

- [ ] Remove the duplicated example-local phase workflow definitions from the example file.
- [ ] Import and call `library/tracked_design_phase`, `library/tracked_plan_phase`, and `library/design_plan_impl_implementation_phase`.
- [ ] Restore the seven YAML-compatible public defaults exactly on the wrapper entry workflow.
- [ ] Wrap each phase call in approved-only `resume-or-start`.
- [ ] Normalize resumed and fresh branches back to the same outward records before building `StackOutput`.
- [ ] Keep all context bootstrap, reusable-state handles, state roots, artifact roots, and managed write roots internal.
- [ ] Add or revise family-focused migration tests so they prove:
  - the wrapper imports the library phases rather than shadowing them;
  - the wrapper boundary exposes only the authored business inputs;
  - approved-only reuse works through the wrapper path;
  - final outputs come from the approved iteration.

**Blocking verification after Task 3:**

- [ ] `python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] `python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --dry-run`

### Task 4: Refresh Focused Family Evidence And Rerun The Existing Promotion Gate

**Files:**

- Modify: `tests/test_workflow_lisp_key_migrations.py`
- Modify only if the family selectors or report expectations are still stale: `tests/test_workflow_lisp_migration_parity.py`
- Modify only if evidence-command expectations are still stale: `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- Refresh generated evidence under `artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity/`

- [ ] Run `pytest --collect-only` over the touched verification modules before broader selectors if any family tests were added or renamed.
- [ ] Keep the iteration-6 recorded command set green.
- [ ] Rerun `python -m orchestrator migration-parity` against the existing targets manifest.
- [ ] Inspect the refreshed `design_plan_impl_stack` parity report and confirm:
  - the family-specific compile, dry-run, runtime, artifact, and resume evidence is present;
  - the report no longer lists `full YAML review-revise loop with carried findings extraction` as unresolved debt, or, if `non_regressive` remains `false`, the remaining blocker is a different explicit evidence axis;
  - any manifest or parity-test edits remained family-local and did not alter unrelated targets.

**Blocking verification after Task 4:**

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py tests/test_neurips_plan_gate_recovery.py tests/test_workflow_lisp_migration_parity.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or findings or resume_or_start or exhausted" -q`
- [ ] `python -m pytest tests/test_neurips_plan_gate_recovery.py -k "resume_or_start or reusable_state" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity`

## Final Verification

Run the exact iteration-6 deterministic commands, plus the wrapper-default dry-run required by the accepted family architecture:

- [ ] `python -m pytest --collect-only tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_key_migrations.py tests/test_neurips_plan_gate_recovery.py tests/test_workflow_lisp_migration_parity.py -q`
- [ ] `python -m pytest tests/test_workflow_lisp_phase_stdlib.py -k "review_loop or findings or resume_or_start or exhausted" -q`
- [ ] `python -m pytest tests/test_neurips_plan_gate_recovery.py -k "resume_or_start or reusable_state" -q`
- [ ] `python -m pytest tests/test_workflow_lisp_key_migrations.py -k "design_plan_impl_stack or review_loop_parity_fixture or resume_or_start_plan_gate_reusable_state_parity_path" -q`
- [ ] `python -m orchestrator compile workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json`
- [ ] `python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --input brief_path=workflows/examples/inputs/major_project_brief.md --input design_target_path=docs/plans/parity-design.md --input design_review_report_target_path=artifacts/review/parity-design-review.md --input plan_target_path=docs/plans/parity-plan.md --input plan_review_report_target_path=artifacts/review/parity-plan-review.md --input execution_report_target_path=artifacts/work/parity-execution.md --input implementation_review_report_target_path=artifacts/review/parity-implementation-review.md --dry-run`
- [ ] `python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.orc --entry-workflow design-plan-impl-review-stack --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_plan_impl_stack.commands.json --dry-run`
- [ ] `python -m orchestrator migration-parity --targets-file workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --output-root artifacts/work/LISP-MIGRATE-KEY-WORKFLOWS/parity`

## Completion Notes

- If any shared prerequisite proof fails, stop and report the owning prerequisite slice instead of widening this family plan.
- If `tests/test_workflow_lisp_migration_parity.py` or `parity_targets.json` already encode the desired family-specific selectors and defaulted dry-run evidence, leave them unchanged.
- Record what changed and exactly which verification commands passed when implementation completes.
