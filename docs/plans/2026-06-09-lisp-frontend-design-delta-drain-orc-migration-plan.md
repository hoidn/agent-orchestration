# Lisp Frontend Design Delta Drain .orc Migration Implementation Plan

> **Execution note for agentic workers:** This is a task-by-task execution plan. Use the repo's current agent instructions and available implementation-planning skills before making large edits. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the `lisp_frontend_design_delta_drain` workflow family from YAML v2.14 to a principled Workflow Lisp `.orc` candidate while preserving typed dataflow, artifact authority, review/revise semantics, blocked recovery, resume behavior, and machine-computed promotion evidence. YAML remains primary until parity tooling proves the `.orc` family is non-regressive and promotable.

**Architecture:** Treat this as a workflow-family migration, not a one-file syntax rewrite. Start with an inventory and domain model, then migrate leaf phases, imported workflows, parent drain orchestration, recovery routing, and parity evidence. Use `.orc` records/unions/enums/procedures for semantic state; keep command scripts only as certified adapters or explicit migration debt; use structured provider/command results rather than reports, pointer files, stdout, or debug YAML as authority.

**Implementation Surfaces:** Workflow Lisp `.orc`, YAML DSL v2.14, shared validation, Semantic IR / Executable IR, `std/phase.orc` review/revise forms imported from the standard library, implementation file path to verify as `orchestrator/workflow_lisp/stdlib_modules/std/phase.orc`, orchestrator CLI, `migration-parity`, pytest, fake-provider fixtures, command adapter scripts, provider prompt assets.

---

## Governing Documents

- `docs/index.md`
- `docs/work_definition_model.md`
- `docs/lisp_workflow_drafting_guide.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/providers.md`
- `specs/state.md`

## Authority And Prerequisite Status

Normative runtime and DSL behavior is owned by `specs/`. The design documents listed above are migration architecture and authoring guidance unless a linked spec says otherwise. This plan is procedural: it does not promote any `.orc` workflow and does not redefine runtime semantics.

Before implementation work beyond inventory, verify the current checkout satisfies the runtime migration foundation required for this family:

- command structured-output bundles validate and fail closed;
- frontend-lowered private typed values can cross runtime boundaries without pointer-file authority;
- provider `output_bundle.path` and `variant_output.path` target binding is runtime-owned;
- `migration-parity` enforces strict schema/version/gate behavior;
- StateLayout / PathAllocator owns generated state and bundle paths;
- compiler-owned write roots are not exposed as public workflow inputs; and
- source maps and Semantic IR include generated-path provenance.

If any item is missing, record a prerequisite gap and stop before translating the workflow family, except for inventory and characterization work.

The foundation gate is not a risk note. It is a hard prerequisite for promotion-grade translation. The runtime migration foundation says YAML remains authoritative until parity computes non-regression, and the post-foundation composition design says further `.orc` primary-promotion work is blocked until the foundation success criteria are complete.

## Source Workflow Family

Primary YAML entrypoint:

- `workflows/examples/lisp_frontend_design_delta_drain.yaml`

Imported workflows:

- `workflows/library/lisp_frontend_design_delta_selector.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml`
- `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml`

Reference `.orc` examples to inspect, not copy:

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

- `DrainIterationStatus`: `CONTINUE`, `DONE`, `BLOCKED`
- `DrainTerminalStatus`: `DONE`, `BLOCKED`, `EXHAUSTED`
- `DrainResult`: terminal status plus `run_state_path` and `drain_summary_path`
- `SelectionStatus`: `SELECT_BACKLOG_ITEM`, `DRAFT_DESIGN_GAP`, `DONE`, `BLOCKED`
- `SelectionResult`: selected work item, design gap request, done, blocked
- `PreSelectionRoute`: `SELECT_NORMAL_WORK`, `SELECT_PREREQUISITE_WORK`, `RECOVER_BLOCKED_DESIGN_GAP`, `BLOCKED`
- `BlockedRecoveryDecision`: `GAP_DESIGN_REVISION_REQUIRED`, `TARGET_DESIGN_REVISION_REQUIRED`, `PREREQUISITE_GAP_REQUIRED`, `TERMINAL_BLOCKED`
- `BlockedRecoveryReason`: existing reason enum values, with user-input-required reserved for genuine intention ambiguity or external environment intervention
- `DesignRevisionDecision`: `REVISED`, `BLOCKED`, plus any current source values.
- `DesignRevisionReviewDecision`: `APPROVE`, `REVISE`, `BLOCKED`.
- `DesignRevisionResult`: record wrapper for design revision decisions and report evidence.
- `RecoveryDrainStatus`: `CONTINUE`, `BLOCKED`, `RUN_RECOVERED_GAP`.
- `RecoveredGapAttempt`: recovered draft, validation result, prepared work-item route, unavailable retry.
- `BlockedRecoveryOutcome`: recorded recovery event, retry-ready event, terminal block, or prerequisite child edge.
- `ArchitectureValidationResult`: `VALID`, `BLOCKED`, `INVALID`
- `WorkItemSource`: `BACKLOG_ITEM`, `DESIGN_GAP`
- `WorkItemTerminalRoute`: `COMPLETE`, `PLAN_REVIEW_EXHAUSTED`, `IMPLEMENTATION_BLOCKED`, `IMPLEMENTATION_REVIEW_EXHAUSTED`
- `PlanPhaseResult`
- `ImplementationAttempt`: `COMPLETED` or `BLOCKED`
- `ImplementationPhaseResult`
- `ReviewDecision`: use stdlib type where possible
- `ReviewFindings`: use stdlib type where possible
- path records for steering, target/baseline design docs, ledgers, run state, state roots, artifact roots, report/check targets, architecture bundle paths, and selection bundles

Current frontend constraint: workflow-boundary union payloads should remain
first-order fields. Do not put a union-valued field inside another union return
surface until Stage 3 explicitly supports nested union boundary lowering. Use
flat recovery outcome variants at exported workflow boundaries and reserve
nested helper unions for internal procedures only when the compiler route
supports them.

Current boundary/lint constraint: recovery records that carry low-level
`state/` paths are internal/private or certified-adapter surfaces until
StateLayout/private executable contracts are foundation-ready. Public
high-level `.orc` boundaries should expose typed decisions and stable artifact
paths instead of raw generated state paths.

Current return constraint: exported workflows must return record or union
types. Bare enum decisions should be wrapped in record result types that carry
the decision plus any report or evidence path.

## Adapter Classification Rules

Every command helper must be classified before migration, including transitive helpers called by named scripts:

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

The inventory must classify not only direct workflow command steps, but also scripts that call other scripts, parse reports, move queue/run-state resources, read pointer files, decide variants, or perform ad hoc JSON rewrites. The command-adapter contract is behavior-based: hidden routing, report parsing, pointer-as-state, and unvalidated JSON state are migration debt whenever they determine workflow state or resource movement.

## Implementation Tasks

### 0. Runtime Foundation Readiness Gate

- [x] Verify command structured-output bundle conformance is implemented and covered by fail-closed tests.
- [x] Verify private frontend-lowered typed values can validate, materialize as views when needed, publish, consume, and render without pointer-file authority.
- [x] Verify provider `output_bundle.path` and `variant_output.path` target binding is runtime-owned and wrong-path output fails closed.
- [x] Verify `migration-parity` strict schema/version/gate behavior exists for `--require-non-regressive` and `--require-promotable`.
- [x] Verify StateLayout / PathAllocator owns generated state and bundle paths used by Workflow Lisp lowering.
- [x] Verify compiler-owned write roots do not appear as public workflow inputs.
- [x] Verify source maps and Semantic IR contain generated-path provenance for the relevant lowered forms.
- [x] Record the gate outcome; no missing prerequisite gap remains after the imported `PhaseCtx` proof fix.

Verification:

- [x] Focused runtime/provider/CLI pytest selectors for each foundation surface.
- [x] Compile and dry-run of a small `.orc` fixture exercising provider/command structured outputs and generated paths.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit readiness evidence or prerequisite-gap records before starting translation.

### 1. Baseline Inventory And Migration Record

- [x] Create a migration inventory artifact under `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/` or a new clearly named migration directory.
- [x] List every workflow in the YAML family and every imported prompt/script it uses.
- [x] List every command helper and classify it using the adapter rules above.
- [x] List every provider step, prompt asset, structured output contract, and expected artifact.
- [x] List every manual pointer/materialization behavior that must become typed authority, a value view, or a certified adapter.
- [x] List every loop and recovery route, including normal selection, prerequisite selection, design-gap drafting, blocked recovery, recovered-gap retry, and drain summary.
- [x] Record reproducible YAML baseline evidence:
  - repo commit SHA;
  - exact workflow command(s);
  - input file(s) or CLI input JSON;
  - provider mode, fake-provider fixtures, and model aliases;
  - run id(s);
  - final `drain_status`, `run_state_path`, and `drain_summary_path`;
  - checksums for run-state, summaries, selection bundles, work-item summaries, reports, validation bundles, and recovery bundles;
  - known accepted differences, if any; and
  - whether evidence is real-provider, fake-provider, or dry-run evidence.
- [x] Add a migration record skeleton for this workflow family with status `inventory`.

Verification:

- [x] `python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- [x] `python -m json.tool artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- [x] `rg -n "command:|provider:|output_bundle:|variant_output:|repeat_until|requires_variant|call:" workflows/examples/lisp_frontend_design_delta_drain.yaml workflows/library/lisp_frontend_design_delta_*.v214.yaml`
- [x] Checksum command output for baseline evidence artifacts recorded in the migration inventory.
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

- [x] Add the `.orc` domain type module with enums, unions, records, and path aliases.
- [x] Keep the module side-effect free.
- [x] Reuse stdlib `ReviewDecision`, `ReviewFindings`, and review-loop result types where they fit.
- [x] Avoid duplicating stdlib types unless the drain family needs stricter domain-specific wrappers.
- [x] Add compile tests proving the type module imports from at least two candidate modules.

Verification:

- [x] Type module compile test.
- [x] Import visibility test.
- [x] Negative test for invalid enum/variant usage if the current test harness supports it.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit type module and tests.

### 4. Plan Phase Candidate

- [x] Translate `lisp_frontend_design_delta_plan_phase.v214.yaml` into `plan_phase.orc`.
- [ ] Preserve inputs and outputs: plan path, plan review report path, final plan review decision.
- [x] Replace the manual `repeat_until` review loop with stdlib `review-revise-loop` or an equivalent typed procedure built from the same semantics.
- [x] Preserve `APPROVE` and `REVISE`; exhaustion must remain explicit and must not masquerade as approval.
- [x] Convert draft/review/revise provider calls to `provider-result` with typed return records or unions.
- [x] Replace final inline Python pointer validation with a typed terminal projection or a certified adapter if the runtime still requires a compatibility pointer.
- [x] Preserve prompt assets and prompt consume semantics without moving routing decisions into prompt prose.
- [x] Record the current public-boundary delta: the first `.orc` candidate avoids raw public `state/` path inputs and requires a parent/private context bridge before parity can claim boundary equivalence.

Verification:

- [x] Compile/typecheck `plan_phase.orc`.
- [ ] Fake-provider approval path test.
- [ ] Fake-provider revise-then-approve test.
- [ ] Exhaustion test returning non-approval terminal state.
- [ ] Source-map check for generated review loop steps.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit plan phase candidate and focused tests.

### 5. Implementation Phase Candidate

- [x] Translate the leaf execute-attempt and completed-review portions of `lisp_frontend_design_delta_implementation_phase.v214.yaml` into `implementation_phase.orc`.
- [x] Model `COMPLETED` and `BLOCKED` as an `ImplementationAttempt` union.
- [x] Preserve variant proof at the execute-attempt boundary; full completed-vs-blocked phase composition remains blocked by the current nested structured-control limitation.
- [x] Convert `ExecuteImplementation` to `provider-result` returning the implementation attempt union.
- [x] Convert checks to `command-result` or a certified checks adapter.
- [x] Replace the manual implementation review/fix `repeat_until` with stdlib review/revise semantics for the completed-review leaf workflow.
- [ ] Preserve `NOT_APPLICABLE` review decision for blocked attempts.
- [ ] Remove copy-recovery behavior that treats stale execution reports as authority unless it is explicitly certified as a compatibility adapter.
- [ ] Preserve output parity for `implementation_state` and `implementation_review_decision`.
- [x] Record the current composition delta: the full phase cannot yet place the stdlib review loop inside the `COMPLETED` arm of the implementation-attempt `match` without shared-validation failures for nested structured `repeat_until`/`match`.

Verification:

- [x] Compile/typecheck `implementation_phase.orc` leaf workflows.
- [ ] Fake-provider completed/approve path.
- [ ] Fake-provider completed/revise/approve path.
- [ ] Fake-provider blocked path.
- [ ] Bad variant access negative test.
- [ ] Missing/wrong report target negative test.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit implementation phase candidate and focused tests.

### 6. Selector Candidate

- [x] Translate the provider-decision portion of `lisp_frontend_design_delta_selector.v214.yaml` into `selector.orc`.
- [x] Replace materialized pointer inputs with typed artifact inputs for the first candidate.
- [x] Convert `SelectNextWork` to `provider-result` returning a typed selection decision.
- [ ] Replace `PublishSelectionBundle` with either a typed projection or a certified adapter.
- [ ] Preserve selection status and selection bundle path output contracts.
- [ ] Keep selection bundle as structured state, not as report prose.
- [x] Record the current public-boundary delta: YAML selector state-root inputs and selection-bundle state paths require a private context/adapter bridge before parity can claim equivalence.

Verification:

- [x] Compile/typecheck `selector.orc`.
- [ ] Fake-provider tests for backlog item, draft design gap, done, and blocked variants.
- [ ] Selection bundle path validation test.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit selector candidate and focused tests.

### 7. Design Gap Architect Candidate

- [x] Decide whether this migration is strictly behavior-preserving for the current `lisp_frontend_design_delta_design_gap_architect.v214.yaml` or whether it also incorporates the accepted architecture review/revise target from `docs/design/lisp_frontend_review_fix_loops.md`.
- [x] If behavior-preserving, translate the current draft + validate shape and record architecture review/revise as an accepted follow-on gap.
- [ ] If incorporating architecture review/revise, add `ArchitectureReviewDecision`, `ArchitectureLoopResult`, and architecture-review-exhausted terminal routing before implementation.
- [ ] Replace inline target path construction with pure typed functions or StateLayout-derived allocation.
- [ ] Keep existing architecture-index builder as a certified command adapter unless replaced by native logic.
- [x] Convert draft provider step to `provider-result`.
- [x] Convert validation to `command-result` with typed architecture validation result.
- [x] Preserve target design, baseline design, command adapter contract, selection bundle, and existing architecture index as explicit inputs/consumes for the leaf candidate.
- [x] Record the current path-boundary delta: target derivation, architecture-index building, and work-item state bundle parity still need StateLayout/private context or certified-adapter bridges.

Verification:

- [x] Compile/typecheck `design_gap_architect.orc` leaf workflows.
- [ ] Fake-provider drafted/valid path.
- [ ] Blocked draft path.
- [ ] Validation invalid path.
- [ ] If architecture review/revise is in scope: approve, revise-then-approve, blocked, and exhaustion paths.
- [ ] Adapter fixture for architecture index and validation scripts.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit design gap architect candidate and focused tests.

### 8. Work Item Candidate

- [x] Translate the terminal-classification and blocked-recovery-classification leaves of `lisp_frontend_design_delta_work_item.v214.yaml` into `work_item.orc`.
- [ ] Replace `ResolveWorkItemInputs` with typed projection logic or a certified adapter.
- [ ] Call the `.orc` plan and implementation phase candidates.
- [ ] Model terminal routes as a typed union or enum with structured payloads.
- [x] Convert terminal classification to a visible `command-result` adapter boundary.
- [x] Convert blocked implementation recovery classification to `provider-result`.
- [ ] Convert recovery route selection and terminal recording to typed procedures, resource transitions, or certified adapters.
- [ ] Preserve item summary path and drain status outputs.
- [ ] Ensure completion is recorded only after plan and implementation approval criteria are met.
- [x] Record the current composition delta: full work-item orchestration is blocked on `ResolveWorkItemInputs`, implementation-phase composition, and run-state/resource-transition bridges.

Verification:

- [x] Compile/typecheck `work_item.orc` leaf workflows.
- [ ] Completed backlog item path.
- [ ] Completed design gap path.
- [ ] Plan review exhausted path.
- [ ] Implementation blocked with recoverable route.
- [ ] Implementation review exhausted path.
- [ ] Run-state mutation adapter tests.
- [x] `git diff --check`

Commit checkpoint:

- [x] Commit work item candidate and focused tests.

### 9. Parent Drain Candidate

- [ ] Translate `lisp_frontend_design_delta_drain.yaml` into `lisp_frontend_design_delta_drain.orc`.
- [ ] Use a typed bounded drain loop with an accumulator and explicit exhaustion behavior.
- [ ] Keep iteration state separate from terminal result state: `DrainIterationStatus` has `CONTINUE`, `DONE`, `BLOCKED`; `DrainTerminalStatus` has `DONE`, `BLOCKED`, `EXHAUSTED`; `DrainResult` carries terminal status plus run-state and summary paths.
- [ ] Express pre-selection as `PreSelectionRoute`, not placeholder string files.
- [ ] Call selector, design gap architect, and work item `.orc` modules.
- [ ] Model normal work, prerequisite work, design-gap drafting, blocked recovery, recovered retry, and terminal blocked as typed branches.
- [ ] Convert drain summary publishing to a typed terminal projection or certified adapter.
- [ ] Preserve max iteration budget of 60 unless a separate design change says otherwise.
- [ ] Preserve public inputs and outputs of the YAML primary.
- [ ] Preserve public input defaults for target/baseline paths, artifact roots, provider aliases, and other defaulted YAML inputs.

Verification:

- [ ] Compile/typecheck parent `.orc`.
- [ ] Shared validation pass.
- [ ] Dry-run using the same input shape as the YAML primary.
- [ ] Fake-provider normal completion path.
- [ ] Fake-provider done path.
- [ ] Fake-provider blocked path.
- [ ] Fake-provider prerequisite recovery path.
- [ ] Fake-provider recovered design-gap retry path.
- [ ] Fake-provider exhaustion path where selection keeps returning work or `CONTINUE` until the 60-iteration budget is exhausted.
- [ ] Input-default parity tests: no optional inputs supplied, overridden artifact roots, overridden provider aliases, and identical defaulted public input hashes between YAML baseline and `.orc` candidate.
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
- Stage 3 currently rejects nested union payloads at workflow boundaries; keep exported recovery and drain result unions flat until that frontend gap is closed.
- Required lints currently reject low-level state paths on high-level workflow boundaries; do not expose recovery state internals publicly before the StateLayout/private contract gate passes.

## First Implementation Slice Recommendation

Start with the foundation readiness gate before translating any workflow phase.

Reasoning:

- The inventory prevents accidental YAML-shaped translation and identifies certified adapters before code churn.
- The feasibility probe and domain module show the target module layout is workable.
- The runtime foundation is now a hard prerequisite; provider output binding, private typed value transport, strict parity gates, and StateLayout cannot remain aspirational if the migrated family is expected to become promotion-grade.
- After the foundation gate passes, the plan phase remains the smallest meaningful loop with provider draft, provider review, provider revise, final projection, and exhaustion semantics.

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
