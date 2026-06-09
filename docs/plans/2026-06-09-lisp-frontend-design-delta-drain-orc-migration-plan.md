# Lisp Frontend Design Delta Drain .orc Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the `lisp_frontend_design_delta_drain` workflow family from YAML v2.14 to a principled Workflow Lisp `.orc` candidate while preserving typed dataflow, artifact authority, review/revise semantics, blocked recovery, resume behavior, and machine-computed promotion evidence. YAML remains primary until parity tooling proves the `.orc` family is non-regressive and promotable.

**Architecture:** Treat this as a workflow-family migration, not a one-file syntax rewrite. Start with an inventory and domain model, then migrate leaf phases, imported workflows, parent drain orchestration, recovery routing, and parity evidence. Use `.orc` records/unions/enums/procedures for semantic state; keep command scripts only as certified adapters or explicit migration debt; use structured provider/command results rather than reports, pointer files, stdout, or debug YAML as authority.

**Tech Stack:** Workflow Lisp `.orc`, YAML DSL v2.14, shared validation, Semantic IR / Executable IR, `std/phase.orc` review/revise forms, orchestrator CLI, `migration-parity`, pytest, fake-provider fixtures, command adapter scripts, provider prompt assets.

---

## Governing Documents

- `docs/index.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`

## Source Workflow Family

Primary YAML entrypoint:

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`

Imported workflows:

- `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`

Existing `.orc` examples to mine, not blindly copy:

- `workflows/examples/review_revise_design_docs.orc`
- `workflows/examples/review_revise_parametric_design_docs.orc`
- `workflows/examples/design_plan_impl_review_stack_v2_call.orc`
- `workflows/library/tracked_plan_phase.orc`
- `workflows/library/design_plan_impl_implementation_phase.orc`

## Non-Negotiables

- YAML stays authoritative until parity evidence passes and `--require-promotable` succeeds.
- Do not claim migration because the `.orc` candidate compiles or dry-runs.
- Do not translate the parent file only while leaving imported workflow semantics implicit.
- Do not route semantic workflow state through markdown reports, stdout, pointer files, prompt prose, or debug YAML.
- Do not expose compiler-generated write roots as public workflow inputs.
- Do not treat `REVISE` as terminal success.
- Do not bypass variant proof when accessing completed/blocked implementation fields.
- Do not use runtime closures or dynamic ProcRefs to work around frontend gaps.
- A thin `.orc` wrapper around YAML callees is allowed only as an interop checkpoint, not as the final migration.

## Target Module Family

The final candidate should be organized as a module family, with names adjusted to existing import conventions if needed:

- `workflows/examples/lisp_frontend_design_delta_drain.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc`
- `workflows/library/lisp_frontend_design_delta/selector.orc`
- `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
- `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
- `workflows/library/lisp_frontend_design_delta/adapters.md` or equivalent adapter inventory
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json` updates for this family

If the current `.orc` importer does not support nested library directories cleanly, use the nearest existing convention and record the import-layout gap in the plan artifact rather than inventing a parallel loader.

## Domain Types To Define First

Define authority-bearing types before translating steps:

- `DrainStatus`: `CONTINUE`, `DONE`, `BLOCKED`
- `DrainResult`: terminal status plus `run_state_path` and `drain_summary_path`
- `SelectionStatus`: `SELECT_BACKLOG_ITEM`, `DRAFT_DESIGN_GAP`, `DONE`, `BLOCKED`
- `SelectionResult`: selected work item, design gap request, done, blocked
- `PreSelectionRoute`: `SELECT_NORMAL_WORK`, `SELECT_PREREQUISITE_WORK`, `RECOVER_BLOCKED_DESIGN_GAP`, `BLOCKED`
- `BlockedRecoveryDecision`: `GAP_DESIGN_REVISION_REQUIRED`, `TARGET_DESIGN_REVISION_REQUIRED`, `PREREQUISITE_GAP_REQUIRED`, `TERMINAL_BLOCKED`
- `BlockedRecoveryReason`: existing reason enum values, with user-input-required reserved for genuine intention ambiguity or external environment intervention
- `ArchitectureValidationResult`: `VALID`, `BLOCKED`, `INVALID`
- `WorkItemSource`: `BACKLOG_ITEM`, `DESIGN_GAP`
- `WorkItemTerminalRoute`: `COMPLETE`, `PLAN_REVIEW_EXHAUSTED`, `IMPLEMENTATION_BLOCKED`, `IMPLEMENTATION_REVIEW_EXHAUSTED`
- `PlanPhaseResult`
- `ImplementationAttempt`: `COMPLETED` or `BLOCKED`
- `ImplementationPhaseResult`
- `ReviewDecision`: use stdlib type where possible
- `ReviewFindings`: use stdlib type where possible
- path records for steering, target/baseline design docs, ledgers, run state, state roots, artifact roots, report/check targets, architecture bundle paths, and selection bundles

## Adapter Classification Rules

Every command helper must be classified before migration:

| Behavior | Preferred treatment |
| --- | --- |
| Pure path/string derivation | pure `defun` or StateLayout-derived context |
| Structured JSON output | `command-result` with typed schema |
| Provider-facing artifact preparation | runtime materialization or typed artifact publish |
| Queue, ledger, run-state mutation | `resource-transition` or certified effectful `defproc` |
| Final fan-in/status projection | typed terminal projection |
| Legacy script that must remain | certified command adapter |
| Inline Python/shell deciding routing/state | migration debt to replace or quarantine |

Command adapters that remain must have a stable script path, typed inputs/outputs, declared effects, path-safety behavior, exit-code taxonomy, fixtures, negative tests, and source-map coverage.

## Implementation Tasks

### 1. Baseline Inventory And Migration Record

- [x] Create a migration inventory artifact under `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/` or a new clearly named migration directory.
- [x] List every workflow in the YAML family and every imported prompt/script it uses.
- [x] List every command helper and classify it using the adapter rules above.
- [x] List every provider step, prompt asset, structured output contract, and expected artifact.
- [x] List every manual pointer/materialization behavior that must become typed authority, a value view, or a certified adapter.
- [x] List every loop and recovery route, including normal selection, prerequisite selection, design-gap drafting, blocked recovery, recovered-gap retry, and drain summary.
- [x] Record current YAML baseline commands and representative run evidence, including the recent completed drain against `docs/design/workflow_lisp_runtime_migration_foundation.md`.
- [x] Add a migration record skeleton for this workflow family with status `inventory`.

Verification:

- [x] `python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- [x] `python -m json.tool artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- [x] `rg -n "command:|provider:|output_bundle:|variant_output:|repeat_until|requires_variant|call:" workflows/examples/lisp_frontend_design_delta_drain.yaml workflows/library/lisp_frontend_design_delta_*.v214.yaml`
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit inventory and migration record only.

### 2. Feasibility Probe For .orc Imports, Calls, And Existing Stdlib Forms

- [x] Compile the existing tested `.orc` review/revise workflow to confirm the current frontend route still works.
- [x] Compile or add a tiny fixture that imports one library `.orc` module from the planned target layout.
- [x] Probe whether `.orc` can call YAML workflows directly. If unsupported or semantically too weak, record that a YAML-call wrapper is not a valid migration route.
- [x] Compile a tiny fixture using `review-revise-loop` from `std/phase.orc`.
- [x] Compile a tiny fixture that returns a union and narrows it with `match`.
- [x] Compile a tiny fixture that passes provider aliases through inputs, or record the current provider-alias limitation.

Verification:

- [x] Narrow pytest selectors for existing `.orc` examples.
- [x] New compile-only fixture tests for import layout, union/match, and stdlib review/revise use.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit feasibility fixtures and any recorded gaps.

### 3. Domain Type Module

- [ ] Add the `.orc` domain type module with enums, unions, records, and path aliases.
- [ ] Keep the module side-effect free.
- [ ] Reuse stdlib `ReviewDecision`, `ReviewFindings`, and review-loop result types where they fit.
- [ ] Avoid duplicating stdlib types unless the drain family needs stricter domain-specific wrappers.
- [ ] Add compile tests proving the type module imports from at least two candidate modules.

Verification:

- [ ] Type module compile test.
- [ ] Import visibility test.
- [ ] Negative test for invalid enum/variant usage if the current test harness supports it.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit type module and tests.

### 4. Plan Phase Candidate

- [ ] Translate `lisp_frontend_design_delta_plan_phase.v214.yaml` into `plan_phase.orc`.
- [ ] Preserve inputs and outputs: plan path, plan review report path, final plan review decision.
- [ ] Replace the manual `repeat_until` review loop with stdlib `review-revise-loop` or an equivalent typed procedure built from the same semantics.
- [ ] Preserve `APPROVE` and `REVISE`; exhaustion must remain explicit and must not masquerade as approval.
- [ ] Convert draft/review/revise provider calls to `provider-result` with typed return records or unions.
- [ ] Replace final inline Python pointer validation with a typed terminal projection or a certified adapter if the runtime still requires a compatibility pointer.
- [ ] Preserve prompt assets and prompt consume semantics without moving routing decisions into prompt prose.

Verification:

- [ ] Compile/typecheck `plan_phase.orc`.
- [ ] Fake-provider approval path test.
- [ ] Fake-provider revise-then-approve test.
- [ ] Exhaustion test returning non-approval terminal state.
- [ ] Source-map check for generated review loop steps.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit plan phase candidate and focused tests.

### 5. Implementation Phase Candidate

- [ ] Translate `lisp_frontend_design_delta_implementation_phase.v214.yaml` into `implementation_phase.orc`.
- [ ] Model `COMPLETED` and `BLOCKED` as an `ImplementationAttempt` union.
- [ ] Preserve variant proof for completed-only execution/check/review fields and blocked-only progress report fields.
- [ ] Convert `ExecuteImplementation` to `provider-result` returning the implementation attempt union.
- [ ] Convert checks to `command-result` or a certified checks adapter.
- [ ] Replace the manual implementation review/fix `repeat_until` with stdlib review/revise semantics where possible.
- [ ] Preserve `NOT_APPLICABLE` review decision for blocked attempts.
- [ ] Remove copy-recovery behavior that treats stale execution reports as authority unless it is explicitly certified as a compatibility adapter.
- [ ] Preserve output parity for `implementation_state` and `implementation_review_decision`.

Verification:

- [ ] Compile/typecheck `implementation_phase.orc`.
- [ ] Fake-provider completed/approve path.
- [ ] Fake-provider completed/revise/approve path.
- [ ] Fake-provider blocked path.
- [ ] Bad variant access negative test.
- [ ] Missing/wrong report target negative test.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit implementation phase candidate and focused tests.

### 6. Selector Candidate

- [ ] Translate `lisp_frontend_design_delta_selector.v214.yaml` into `selector.orc`.
- [ ] Replace materialized pointer inputs with typed artifacts or private value views.
- [ ] Convert `SelectNextWork` to `provider-result` returning `SelectionResult`.
- [ ] Replace `PublishSelectionBundle` with either a typed projection or a certified adapter.
- [ ] Preserve selection status and selection bundle path output contracts.
- [ ] Keep selection bundle as structured state, not as report prose.

Verification:

- [ ] Compile/typecheck `selector.orc`.
- [ ] Fake-provider tests for backlog item, draft design gap, done, and blocked variants.
- [ ] Selection bundle path validation test.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit selector candidate and focused tests.

### 7. Design Gap Architect Candidate

- [ ] Translate `lisp_frontend_design_delta_design_gap_architect.v214.yaml` into `design_gap_architect.orc`.
- [ ] Replace inline target path construction with pure typed functions or StateLayout-derived allocation.
- [ ] Keep existing architecture-index builder as a certified command adapter unless replaced by native logic.
- [ ] Convert draft provider step to `provider-result`.
- [ ] Convert validation to `command-result` with typed `ArchitectureValidationResult`.
- [ ] Preserve target design, baseline design, command adapter contract, selection bundle, and existing architecture index as explicit inputs/consumes.

Verification:

- [ ] Compile/typecheck `design_gap_architect.orc`.
- [ ] Fake-provider drafted path.
- [ ] Blocked draft path.
- [ ] Validation invalid path.
- [ ] Adapter fixture for architecture index and validation scripts.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit design gap architect candidate and focused tests.

### 8. Work Item Candidate

- [ ] Translate `lisp_frontend_design_delta_work_item.v214.yaml` into `work_item.orc`.
- [ ] Replace `ResolveWorkItemInputs` with typed projection logic or a certified adapter.
- [ ] Call the `.orc` plan and implementation phase candidates.
- [ ] Model terminal routes as a typed union or enum with structured payloads.
- [ ] Convert blocked implementation recovery classification to `provider-result`.
- [ ] Convert recovery route selection and terminal recording to typed procedures, resource transitions, or certified adapters.
- [ ] Preserve item summary path and drain status outputs.
- [ ] Ensure completion is recorded only after plan and implementation approval criteria are met.

Verification:

- [ ] Compile/typecheck `work_item.orc`.
- [ ] Completed backlog item path.
- [ ] Completed design gap path.
- [ ] Plan review exhausted path.
- [ ] Implementation blocked with recoverable route.
- [ ] Implementation review exhausted path.
- [ ] Run-state mutation adapter tests.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit work item candidate and focused tests.

### 9. Parent Drain Candidate

- [ ] Translate `lisp_frontend_design_delta_drain.yaml` into `lisp_frontend_design_delta_drain.orc`.
- [ ] Use a typed bounded drain loop with an accumulator and explicit exhaustion behavior.
- [ ] Express pre-selection as `PreSelectionRoute`, not placeholder string files.
- [ ] Call selector, design gap architect, and work item `.orc` modules.
- [ ] Model normal work, prerequisite work, design-gap drafting, blocked recovery, recovered retry, and terminal blocked as typed branches.
- [ ] Convert drain summary publishing to a typed terminal projection or certified adapter.
- [ ] Preserve max iteration budget of 60 unless a separate design change says otherwise.
- [ ] Preserve public inputs and outputs of the YAML primary.

Verification:

- [ ] Compile/typecheck parent `.orc`.
- [ ] Shared validation pass.
- [ ] Dry-run using the same input shape as the YAML primary.
- [ ] Fake-provider normal completion path.
- [ ] Fake-provider done path.
- [ ] Fake-provider blocked path.
- [ ] Fake-provider prerequisite recovery path.
- [ ] Fake-provider recovered design-gap retry path.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit parent drain candidate and focused tests.

### 10. Resume, Checkpoint, And Recovery Parity

- [ ] Define stable checkpoint identity for parent drain iterations.
- [ ] Define stable checkpoint identity for plan review loop, implementation review loop, recovered gap retry, and prerequisite recovery.
- [ ] Verify recovered-gap paths do not depend on stale transient bundles.
- [ ] Verify parent-child prerequisite edges reconcile when child work completes in a later iteration.
- [ ] Verify blocked recovery can revise gap design, revise target design, draft prerequisite gaps, or terminally block only for genuine user-intention ambiguity or external environment intervention.
- [ ] Verify `resume-or-start` certified bindings are available before typecheck/lowering assertions for compatibility harnesses.

Verification:

- [ ] Resume from interrupted parent drain after selection.
- [ ] Resume from interrupted plan review loop.
- [ ] Resume from interrupted implementation review/fix loop.
- [ ] Resume from recovered design-gap materialization.
- [ ] Regression for stale parent recovery state after child completion.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit resume and recovery parity tests/fixes.

### 11. Migration Parity Evidence

- [ ] Add this workflow family to the parity target manifest as exploratory.
- [ ] Generate compile, shared validation, dry-run, fake-provider smoke, output parity, terminal-state parity, artifact parity, and resume/reuse evidence.
- [ ] Ensure `non_regressive` is computed by tooling, never hand-authored.
- [ ] Ensure missing evidence, stale evidence, expired waivers, hidden write-root inputs, wrong variants, and report-only claims fail closed.
- [ ] Run `--require-non-regressive` before claiming the candidate is non-regressive.
- [ ] Run `--require-promotable` before claiming YAML can stop being primary.

Verification:

- [ ] `python -m orchestrator migration-parity workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --target <target-id> --require-non-regressive`
- [ ] `python -m orchestrator migration-parity workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json --target <target-id> --require-promotable`
- [ ] Negative parity tests for hand-authored `non_regressive` and stale report reuse.
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit parity manifest, reports, tests, and docs updates.

### 12. Documentation And Catalog Updates

- [ ] Update `workflows/README.md` to list the `.orc` candidate as candidate/exploratory until parity passes.
- [ ] Update `docs/lisp_workflow_drafting_guide.md` only if the migration reveals a reusable authoring rule.
- [ ] Update `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md` if the migration discovers a composition or stdlib gap.
- [ ] Update the command adapter inventory with any scripts that remain certified adapters.
- [ ] Add a migration record summarizing accepted differences and remaining gaps.
- [ ] Do not remove or demote the YAML primary unless `--require-promotable` succeeds and the user explicitly accepts promotion.

Verification:

- [ ] Link check by inspection for touched docs.
- [ ] `rg -n "lisp_frontend_design_delta_drain|design delta drain|primary|candidate|promotable" docs workflows`
- [ ] `git diff --check`

Commit checkpoint:

- [ ] Commit documentation/catalog updates.

## Expected Risk Areas

- The parent drain's recovery path is more complex than the basic review/revise `.orc` examples.
- Provider `variant_output.path` target binding must be foundation-ready before provider-heavy paths can be promotion evidence.
- Private collection/value transport may be needed for richer typed context docs, selected-work bundles, and recovered-gap state.
- Some command helpers encode real state transitions and cannot be safely replaced by pure functions.
- `backlog-drain` may not yet be expressive enough for normal/prerequisite/recovery work selection; if so, harden the stdlib/Core form before forcing the YAML shape into `.orc`.
- Source maps and Semantic IR layout entries must survive generated paths from loops, calls, and recovered-gap branches.
- Real smoke runs may be expensive; use fake-provider fixtures first and reserve provider runs for promotion evidence.

## First Implementation Slice Recommendation

Start with the inventory and plan phase candidate.

Reasoning:

- The inventory prevents accidental YAML-shaped translation and identifies certified adapters before code churn.
- The plan phase is the smallest meaningful loop with provider draft, provider review, provider revise, final projection, and exhaustion semantics.
- It exercises the stdlib review/revise route without the full parent drain recovery matrix.
- It gives early evidence for whether the target module layout and prompt extern model are workable.

Do not start by translating the parent drain. The parent depends on selector, gap architect, work item, plan phase, implementation phase, recovery routing, run-state mutation, and checkpoint identity; starting there would hide semantic gaps behind a large control-flow port.

## Completion Criteria

This migration is complete only when:

- The `.orc` workflow family compiles, typechecks, lowers, and passes shared validation.
- Fake-provider tests cover normal completion, done, blocked, plan revise, implementation revise, implementation blocked, prerequisite recovery, recovered gap retry, and exhaustion.
- Command helpers that remain are certified adapters or explicitly tracked migration debt.
- Reports, pointer files, prompt prose, stdout, and debug YAML are not semantic routing authority.
- Source maps and Semantic IR explain generated paths and hidden runtime bindings.
- Resume/reuse tests cover the parent drain and nested review/recovery loops.
- `migration-parity` computes `non_regressive=true`.
- `migration-parity --require-promotable` succeeds before any YAML-primary replacement.
- The user explicitly accepts promotion from YAML primary to `.orc` primary.
