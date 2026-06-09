# Lisp Frontend Design Delta Drain .orc Migration Inventory

Status: inventory
Created: 2026-06-09
Plan: `docs/plans/2026-06-09-lisp-frontend-design-delta-drain-orc-migration-plan.md`

## Purpose

This inventory is the first execution slice for the `.orc` migration of
`workflows/examples/lisp_frontend_design_delta_drain.yaml`.

The migration target is the workflow family, not the parent YAML file alone.
YAML remains authoritative until machine-computed migration parity proves the
`.orc` candidate is both non-regressive and promotable.

## Current Baseline Evidence

Recent completed YAML run:

- Run: `20260609T003338Z-iroxpc`
- Workflow: `workflows/examples/lisp_frontend_design_delta_drain.yaml`
- Status: `completed`
- Started: `2026-06-09T00:33:38.730908+00:00`
- Updated: `2026-06-09T07:26:17.216947+00:00`
- Active runtime: `6h 52m 38s`
- Drain status: `DONE`
- Completed repeat iterations: `0` through `9`
- Run state: `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- Drain summary: `artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- Target design: `docs/design/workflow_lisp_runtime_migration_foundation.md`
- Baseline design: `docs/design/workflow_lisp_frontend_specification.md`
- Providers: `implementation_execute_provider=codex`, `implementation_review_provider=codex`

Validated local evidence:

- `python -m json.tool state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/run_state.json`
- `python -m json.tool artifacts/work/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain-summary.json`
- `python -m orchestrator report --run-id 20260609T003338Z-iroxpc`

## Workflow Family

| File | Role | Migration target |
| --- | --- | --- |
| `workflows/examples/lisp_frontend_design_delta_drain.yaml` | Parent bounded drain loop | `workflows/examples/lisp_frontend_design_delta_drain.orc` |
| `workflows/library/lisp_frontend_design_delta_selector.v214.yaml` | Work selector | `workflows/library/lisp_frontend_design_delta/selector.orc` |
| `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml` | Design-gap architecture drafter/validator | `workflows/library/lisp_frontend_design_delta/design_gap_architect.orc` |
| `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | Selected work item executor and terminal classifier | `workflows/library/lisp_frontend_design_delta/work_item.orc` |
| `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml` | Plan draft/review/revise phase | `workflows/library/lisp_frontend_design_delta/plan_phase.orc` |
| `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml` | Implementation attempt/check/review/fix phase | `workflows/library/lisp_frontend_design_delta/implementation_phase.orc` |

Shared domain types should live in `workflows/library/lisp_frontend_design_delta/types.orc`
or the nearest import layout supported by the current `.orc` importer.

## Parent Drain Inputs And Outputs

Authoritative public inputs in the YAML primary:

- `steering_path`
- `target_design_path`
- `baseline_design_path`
- `command_adapter_contract_path`
- `backlog_root`
- `progress_ledger_path`
- `drain_state_root`
- `run_state_target_path`
- `drain_summary_target_path`
- `artifact_work_root`
- `artifact_checks_root`
- `artifact_review_root`
- `architecture_index_root`
- `implementation_execute_provider`
- `implementation_review_provider`

Authoritative public outputs:

- `drain_status`
- `run_state_path`
- `drain_summary_path`

The `.orc` candidate must preserve this public boundary until migration parity
accepts an intentional difference.

## Provider Steps And Prompts

| Workflow | Step | Provider | Prompt source | Structured result |
| --- | --- | --- | --- | --- |
| selector | `SelectNextWork` | `codex` | `prompts/lisp_frontend_selector/select_next_design_delta_work.md` | `output_bundle` with `selection_status` |
| design-gap architect | `DraftDesignGapArchitecture` | `codex` | `prompts/lisp_frontend_design_delta_design_gap_architect/draft_implementation_architecture.md` | `output_bundle` with `draft_status` |
| plan phase | `DraftPlan` | `codex` | `prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md` | `expected_outputs` plan path |
| plan phase | `ReviewPlan` | `codex` | `prompts/lisp_frontend_design_delta_plan_phase/review_plan.md` | `expected_outputs` review report and decision |
| plan phase | `RevisePlan` | `codex` | `prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md` | `expected_outputs` plan path |
| implementation phase | `ExecuteImplementation` | selected execute provider | `prompts/lisp_frontend_design_delta_implementation_phase/implement_plan.md` | `variant_output` with `COMPLETED` / `BLOCKED` |
| implementation phase | `ReviewImplementation` | selected review provider | `prompts/lisp_frontend_design_delta_implementation_phase/review_implementation.md` | `expected_outputs` review report and decision |
| implementation phase | `FixImplementation` | selected execute provider | `prompts/lisp_frontend_design_delta_implementation_phase/fix_implementation.md` | provider edits execution report target |
| work item | `ClassifyBlockedImplementationRecovery` | selected review provider | `prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md` | `output_bundle` with blocked recovery route |
| parent drain | `ClassifyBlockedImplementationRecovery` | selected review provider | `workflows/library/prompts/lisp_frontend_design_delta_work_item/classify_blocked_implementation_recovery.md` | `output_bundle` with blocked recovery route |
| parent drain | `ReviseBlockedDesignGap` | selected execute provider | `workflows/library/prompts/lisp_frontend_design_delta_work_item/revise_prior_blocked_design_gap.md` | `output_bundle` with design revision decision |
| parent drain | `ReviewBlockedTargetDesignRevision` | selected review provider | `workflows/library/prompts/lisp_frontend_design_delta_work_item/review_prior_blocked_design_revision.md` | `expected_outputs` design revision review decision |

Migration note: provider routing must consume structured result contracts. Prompt
text can explain outputs, but it must not be the authority for loop routing,
variant proof, artifact identity, or recovery classification.

## Command Helper Classification

| Script or inline command | Current role | Initial migration classification |
| --- | --- | --- |
| `workflows/library/scripts/update_lisp_frontend_run_state.py` | Initializes run state and records completed/blocked work | Certified command adapter or future resource-transition owner |
| `workflows/library/scripts/build_lisp_frontend_backlog_manifest.py` | Builds backlog manifest for each drain iteration | Certified command adapter; candidate for runtime-native backlog query later |
| `workflows/library/scripts/prepare_lisp_frontend_iteration_paths.py` | Derives per-iteration state/report paths | StateLayout/path-allocation candidate; keep as certified adapter until allocator owns it |
| `workflows/library/scripts/detect_lisp_frontend_blocked_design_gap_recovery.py` | Detects pre-selection recovery route | Typed recovery procedure or certified adapter; semantic routing, so do not hide in glue long term |
| `workflows/library/scripts/write_lisp_frontend_drain_status.py` | Writes scalar drain status | Typed terminal projection candidate |
| `workflows/library/scripts/write_lisp_frontend_recovery_status.py` | Writes scalar recovery status | Typed terminal projection candidate |
| `workflows/library/scripts/write_lisp_frontend_relpath_value.py` | Writes/validates relpath scalar | Typed path/value projection candidate |
| `workflows/library/scripts/publish_lisp_frontend_selection_bundle.py` | Publishes selected bundle path | Typed projection or certified adapter |
| `workflows/library/scripts/build_lisp_frontend_architecture_index.py` | Builds markdown/JSON architecture index | Certified command adapter; external file-system scan is legitimate adapter behavior |
| `workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py` | Validates design-gap draft and emits work item bundle | Certified command adapter unless promoted to typed validation procedure |
| `workflows/library/scripts/materialize_lisp_frontend_work_item_inputs.py` | Resolves selected work-item inputs and target paths | Typed projection plus StateLayout candidate; certified adapter initially |
| `workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py` | Classifies plan/implementation terminal route | Typed terminal projection candidate |
| `workflows/library/scripts/select_lisp_frontend_blocked_recovery_route.py` | Normalizes blocked recovery route | Typed recovery route projection candidate |
| `workflows/library/scripts/record_lisp_frontend_blocked_recovery_outcome.py` | Records blocked recovery outcome in run state | Certified command adapter or future resource-transition owner |
| `workflows/library/scripts/record_lisp_frontend_prerequisite_recovery_outcome.py` | Reconciles prerequisite recovery state | Certified command adapter or future resource-transition owner |
| `workflows/library/scripts/materialize_lisp_frontend_recovered_design_gap_draft.py` | Reconstructs retry-ready design-gap draft | Certified adapter; must preserve deterministic recovery evidence |
| `workflows/library/scripts/prepare_lisp_frontend_recovered_design_gap_work_item.py` | Prepares recovered gap work-item route | Typed projection plus StateLayout candidate |
| `workflows/library/scripts/record_lisp_frontend_recovered_retry_unavailable.py` | Records retry-unavailable state | Certified command adapter or future resource-transition owner |
| `workflows/library/scripts/resolve_lisp_frontend_drain_iteration_status.py` | Resolves iteration terminal status from normal/recovery branches | Typed terminal projection candidate |
| `workflows/library/scripts/finalize_lisp_frontend_drain_summary.py` | Writes drain summary and final output pointers | Typed terminal projection or certified adapter |
| `workflows/library/scripts/run_neurips_backlog_checks.py` | Runs check commands and writes checks report | Certified command adapter |
| inline Python in `PrepareArchitectureTargets` | Derives architecture/work-item target paths | Pure function plus StateLayout candidate |
| inline Python in `FinalizePlanPhaseOutputs` | Validates final plan/report/decision pointers | Typed terminal projection candidate |
| inline Python in implementation report publish steps | Publishes completed/blocked report pointers | Typed variant-specific projection candidate |
| inline Python in `PublishUpdatedExecutionReport` | Preserves or copies execution report after fix | Migration-debt candidate; copy-recovery must not become semantic authority |
| inline Python in `WriteLoopReviewDecision` | Copies review decision into loop output | Typed projection candidate |
| inline Python in `FinalizeImplementationPhaseOutputs` | Validates final implementation terminal outputs | Typed terminal projection candidate |

## Manual Pointer And Materialization Surfaces

These are compatibility representations in the YAML primary and should not
become `.orc` semantic authority:

- `state_root/*_path.txt` input materialization files
- plan and review report target pointer files
- implementation execution/progress/check/review report pointer files
- scalar status files such as `drain-status.txt`, `normal-drain-status.txt`,
  `blocked-recovery-drain-status.txt`, and loop decision files
- recovered-gap route files that mirror already-typed recovery state

The `.orc` migration should replace these with typed values, structured
bundles, value views, or certified adapters. Pointer files may remain only as
compatibility views where parity requires them.

## Core Loops And Routing

| Surface | Current YAML shape | Migration target |
| --- | --- | --- |
| Parent drain | `repeat_until` max 60 over selection/recovery branches | typed bounded drain procedure with accumulator and explicit exhaustion |
| Plan review loop | `repeat_until` max 12 over `APPROVE` / `REVISE` | stdlib `review-revise-loop` or equivalent typed procedure |
| Implementation review loop | `repeat_until` max 40, skipped for blocked attempts | stdlib review/fix semantics over completed implementation attempts |
| Implementation attempt | provider `variant_output` `COMPLETED` / `BLOCKED` | `ImplementationAttempt` union with proof-preserving `match` |
| Work-item terminal route | command projection plus `match` | typed terminal route projection |
| Blocked recovery | pre-selection detection plus provider classifier and recorder scripts | typed recovery decision and resource transition |
| Recovered gap retry | materialized draft, validation, work-item call, retry-availability recorder | typed recovered-gap route with deterministic state reconstruction |

## Domain Types Needed Before Code Migration

- `DrainStatus`
- `DrainResult`
- `SelectionStatus`
- `SelectionResult`
- `PreSelectionRoute`
- `BlockedRecoveryDecision`
- `BlockedRecoveryReason`
- `ArchitectureValidationResult`
- `WorkItemSource`
- `WorkItemTerminalRoute`
- `PlanPhaseResult`
- `ImplementationAttempt`
- `ImplementationPhaseResult`
- stdlib-compatible `ReviewDecision`
- stdlib-compatible `ReviewFindings`
- path records for steering, target/baseline docs, ledgers, run-state roots,
  artifact roots, report targets, selection bundles, and architecture bundles

## Initial Risk Register

- The parent drain recovery path is substantially more complex than the current
  tested generic design-doc review/revise `.orc` workflow.
- Provider `variant_output.path` target binding must be foundation-ready before
  implementation-attempt routing can be promotion evidence.
- Some command helpers mutate run state and should not be treated as pure
  projections.
- `PublishUpdatedExecutionReport` contains copy-recovery behavior that must be
  reviewed against the authority model before migration.
- The current public YAML boundary uses many pointer files; the `.orc` boundary
  should preserve output parity without making those pointers semantic authority.
- Resume parity must cover stale parent recovery state after child prerequisite
  completion, recovered-gap retry, and nested review loops.

## Recommended Next Slice

Proceed to the feasibility probe before writing the domain type module:

1. compile the existing tested design-doc review/revise `.orc` workflow;
2. test the planned library import layout with a tiny `.orc` fixture;
3. probe whether `.orc` can call YAML directly, recording the result as an
   interop checkpoint only;
4. compile a tiny `review-revise-loop` fixture; and
5. compile a tiny union-returning provider or pure fixture with `match`.

Only after this probe should the migration create `types.orc`.
