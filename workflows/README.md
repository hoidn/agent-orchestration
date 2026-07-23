# Workflow Index

This file is an informative catalog of workflow YAML and Workflow Lisp `.orc`
examples under `workflows/`. A promoted `.orc` entry with shared-validation,
runtime, and parity evidence is the primary surface for its family. Otherwise,
the retained YAML surface remains the exact-behavior authority until its own
promotion gate closes. That migration rule preserves existing authority; it
does not make YAML a starting point for new workflow families.

Existing YAML compatibility workflows can still be checked from the repo root:

```bash
python -m orchestrator run workflows/examples/<workflow>.yaml --dry-run
```

The promoted Design Delta primary uses the Workflow Lisp launch route. Supply
all of its declared typed inputs with `--input` or `--input-file`; the fully
input-complete invocation is recorded by the Gate P3 evidence step.

```bash
python -m orchestrator run workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json \
  --input-file <design-delta-inputs.json>
```

## Verified-Iteration Drain Launch

New verified-iteration launches use the promoted Workflow Lisp primary. Supply
the target-owned design and check-command paths together with any desired
provider/model overrides; the retained YAML twin is compatibility evidence,
not the launch route for new runs.

```bash
python -m orchestrator run workflows/library/verified_iteration_drain/drain.orc \
  --entry-workflow verified_iteration_drain/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/verified_iteration_drain.commands.json \
  --input target_design_path=<target-design-relpath> \
  --input check_commands_path=<check-commands-relpath>
```

## Generic Run Watchdog Launch

New watchdog launches use the promoted Workflow Lisp primary. Supply the
target run id and any desired provider or path overrides; the retained YAML
twin is compatibility evidence, not the launch route for new runs.

```bash
python -m orchestrator run workflows/library/generic_run_watchdog/watchdog.orc \
  --entry-workflow generic_run_watchdog/watchdog::watchdog \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/generic_run_watchdog.commands.json \
  --input target_run_id=<run-id>
```

## Which Example Should I Copy?

| Goal | Starting point | Route status |
| --- | --- | --- |
| Start new authoring | [Workflow Lisp review/revise example](examples/review_revise_design_docs.orc) | `preferred_current_guidance` / `wcc_default` in the route-readiness registry; use when its typed review/fix shape fits. |
| Maintain existing YAML | [Legacy YAML drafting guide](../docs/workflow_drafting_guide.md) | Compatibility guidance only; do not create a new YAML/YML workflow or template. |

Fresh preferred starting points:

- For current target-design / design-gap drain work, start with the promoted
  Workflow Lisp primary at
  `workflows/library/lisp_frontend_design_delta/drain.orc`. Its YAML twin is
  retained only as compatibility/reference evidence until the Stage 6 archive
  gate.
- For a generic `.orc` review/fix loop over a target design doc plus optional
  context docs, start with `workflows/examples/review_revise_design_docs.orc`.
- For the real-life-tested `.orc` review/fix path that revised the parametric
  design docs, inspect
  `workflows/examples/review_revise_parametric_design_docs.orc` as provenance;
  prefer `review_revise_design_docs.orc` when you need the generalized target
  design-doc shape.

Reference corpus:

- For the smallest Workflow Lisp `.orc` teaching example, read
  `workflows/examples/kiss_backlog_item.orc` as a compact reference, not as a
  direct template for new workflows.
- For structured variant/materialization behavior, inspect the v2.14 drain
  examples as reference corpus before copying patterns.
- For migration work, keep the YAML primary authoritative until the `.orc`
  candidate has compile, shared-validation, dry-run or smoke, and parity
  evidence.
- Avoid copying examples marked legacy, negative fixture, prompt asset issue, or
  needs schema cleanup unless that status matches your purpose.
- Treat workflows last modified more than one week ago as reference corpus:
  useful to read and adapt for concepts, but not direct copy templates.

## Workflow Lisp Route/Readiness Labels

Workflow Lisp `.orc` copy-safety is recorded in
`docs/workflow_lisp_route_readiness_registry.json`. The registry labels, not
filenames, modification dates, or prose status alone, determine whether an
example is current WCC/schema-2 guidance, legacy compatibility evidence,
migration-only evidence, historical negative coverage, or stale material.

Use `wcc_default` entries as current WCC/schema-2 examples. Treat
`legacy_schema1_compat` as compatibility evidence, not new authoring guidance.
Treat `migration_candidate` as mid-migration until migration parity supplies
the required family evidence. Do not cite `stale_needs_update` entries as
current evidence. Markdown catalog rows are a view over that registry and
nearby parity evidence; route identity remains registry metadata.

## Directory Map

- `workflows/examples/`: runnable example workflows and validation fixtures
- `workflows/examples/*.orc`: Workflow Lisp authoring examples that compile
  through the frontend; check each catalog entry before treating one as a
  runnable replacement for YAML
- `workflows/templates/`: frozen non-running compatibility-template inventory;
  new template work starts from a registry-approved `.orc` example
- `workflows/library/`: reusable imported subworkflows used by `call`-based examples
- `workflows/library/prompts/`: repo-owned prompt assets bundled with reusable imported workflows
- `workflows/examples/prompts/`: prompt files used only by example workflows stored under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by standalone or monolithic workflows

When adapting a workflow from another repository checkout, inspect the relevant
call-based stack together with its imported library workflows and bundled
prompt directory. Revalidate the adapted workflow against current specs and
guides before using it. Use a no-import monolith such as
`workflows/library/revision_study_design_plan_impl_monolith.yaml` only as a
portability or debugging fallback when adapting the import tree is not
practical.

## Prompt Resolution

For an exhaustive workflow-to-prompt table, see `docs/workflow_prompt_map.md`.

Resolution rules:
- `input_file` is repo-root relative and is intended for workspace-owned or runtime-generated prompt material.
- `asset_file` is relative to the workflow YAML file and is intended for prompt assets bundled with reusable workflows.
- `asset_depends_on` follows the same workflow-source-relative rule as `asset_file`.

The prompt map reports missing paths; a missing path may indicate a stale example, a downstream snapshot with external assets, or a prompt generated at runtime by an earlier step.

## Catalog Status

- **Current canonical**: current feature demos. If an entry is old, read it as a
  stable reference and revalidate before adapting; do not copy it directly as a
  new workflow template.
- **Reusable call-based**: examples that exercise imported library workflows and bundled prompt assets.
- **Legacy or migration**: still useful as historical or migration references, but not the first place to copy patterns.
- **Negative fixture**: expected to fail validation or runtime checks for a specific test purpose.
- **Input-required**: requires `--input` or fixture files for dry-run validation.
- **Prompt asset issue**: references missing or external prompt assets; check `docs/workflow_prompt_map.md` before running.
- **Needs schema cleanup**: use this status when an example fails dry-run validation because it predates current loader schema.

## Workflow Catalog

| Path | Status | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- | --- |
| `workflows/examples/revision_study_priority_design_plan_impl_stack_v2_call.yaml` | Reusable call-based | `2.7` | `revision-study-priority-design-plan-impl-stack-v2-call` | Thin runnable wrapper around the reusable revision-study priority adapter, with an example manifest fixture. |
| `workflows/library/generic_run_watchdog/watchdog.orc` | Workflow Lisp production primary; input-required | `2.15` | `generic_run_watchdog/watchdog::watchdog` | Promoted generic watchdog primary with exact clean, repair, retry/resume, artifact-lineage, and typed parity evidence. New launches use this `.orc` route; the final report is `artifacts/work/YAML-RETIREMENT-TASK5/parity/generic-run-watchdog-final/generic_run_watchdog.json`. |
| `workflows/examples/generic_run_watchdog.yaml` | Compatibility/reference twin; retained until Task 6 deletion gate | `2.14` | `generic-run-watchdog-v214` | Retained executable YAML compatibility watchdog. Do not use it for new launches; Task 6 owns its reference and supported-run deletion gates. |
| `workflows/library/lisp_frontend_design_delta/drain.orc` | Workflow Lisp production primary; reusable library; input-required | `2.14` | `lisp_frontend_design_delta/drain::drain` | Primary Design Delta target/baseline drain. Its route-readiness entry is `wcc_default` / `promotion_eligible` with preferred-current-guidance copy safety. The retained strict migration-parity report records the historical promotion decision; it is not a live parity target. Fresh promotion compile, dry-run, smoke, and parity evidence is recorded; Phase 3 Tasks 3.1–3.4 are complete, and Gates P3 and P4 are independently reviewed and satisfied while retaining the historical report. Task 4.1 stripped the Design-Delta-only parity lanes, and Task 4.2 retired the temporary G8 build serializer. Task 4.1 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.2 is complete and independently reviewed, with SPEC PASS and CODE QUALITY PASS. Task 4.3 is complete. Phase 4 is complete. Gate S3 is satisfied. The semantic-migration freeze is lifted. Current work selection and later-stage order are governed by `docs/plans/2026-07-09-procedure-first-roadmap-execution-sequence.md`. |
| `workflows/library/verified_iteration_drain/drain.orc` | Workflow Lisp production primary; input-required | `2.15` | `verified_iteration_drain/drain::drain` | Promoted verified-iteration primary with exact compile/runtime/parity evidence. New launches use this `.orc` route; the final typed parity report is `artifacts/work/YAML-RETIREMENT-TASK5/parity/verified-iteration-final/verified_iteration_drain.json`. |
| `workflows/examples/verified_iteration_drain.yaml` | Compatibility/reference twin; retained until Task 6 deletion gate | `2.14` | `verified-iteration-drain` | Retained executable YAML compatibility surface for one verification cycle. Do not use it for new launches; Task 6 owns its reference and supported-run deletion gates. |
| `workflows/examples/lisp_frontend_design_delta_drain.yaml` | Compatibility/reference twin; retained until Stage 6 | `2.14` | `lisp-frontend-design-delta-drain-v214` | Former Design Delta primary retained for one verification cycle and historical contract comparison. Do not use it as the current launch or authoring surface; archive it only at the Stage 6 gate. |
| `workflows/examples/kiss_backlog_item.orc` | Workflow Lisp shared-validation example; input-required | `2.14` | `run-backlog-item` | Minimal `.orc` single-backlog-item stack: typed backlog item inputs, plan provider result, plan review/revise loop, implementation provider result, implementation review/fix loop, and final structured summary output. It compiles through shared validation and dry-runs through the `.orc` runtime bridge; it is a single-item authoring example, not a production queue drain or parity replacement for the mature YAML stacks. |
| `workflows/examples/cycle_guard_demo.orc` | Historical Workflow Lisp migration surface; input-required | `2.14` | `cycle-guard-demo` | Preserved `.orc` surface from the cycle-guard migration tranche. Its certified command boundary and frozen historical contract/evidence remain useful migration context; it is not a live YAML-parity target or preferred authoring route. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.orc` | Historical Workflow Lisp migration surface; input-required | `2.14` | `design-plan-impl-review-stack` | Preserved `.orc` surface for the call-based design->plan->implementation family, with typed provider/prompt extern bindings and frozen historical YAML contract/evidence. Inspect it for stack migration context; it is not a live YAML-parity target or the real-life-tested design-doc review/fix workflow. |
| `workflows/examples/review_revise_design_docs.orc` | Workflow Lisp generic review/fix workflow; input-required | `2.14` | `review_revise_design_docs::review-revise-design-docs` | Generic `.orc` workflow that runs a bounded stdlib review/fix loop over a parameterized `target_doc`, `context_docs`, and `review_focus`. Use it as the current model for targeted design-doc review/fix loops; it is not a production drain or YAML parity replacement. |
| `workflows/examples/review_revise_parametric_design_docs.orc` | Workflow Lisp historical one-off review/fix workflow; input-required | `2.14` | `review-revise-parametric-design-docs` | Earlier one-off `.orc` workflow for the Workflow Lisp review/revise stdlib integration, structural parametric constraints, and compile-time parametric specialization docs. Keep it as provenance for the real-life-tested review path, but prefer `review_revise_design_docs.orc` for new targeted design-doc review/fix authoring. |
| `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | Reusable call-based; input-required | `2.7` | `neurips-hybrid-resnet-tranche-drain-plan-impl-review` | Loops over roadmap tranche selection from supplied design + roadmap inputs, then reuses the roadmap-seeded plan phase and implementation review/fix phase for each selected tranche. |
| `workflows/examples/neurips_steered_backlog_drain.yaml` | Downstream reference; reusable call-based; input-required | `2.14` | `neurips-steered-backlog-drain-v214` | Canonical steered backlog drain wrapper copied from PtychoPINN: builds a raw backlog manifest, applies a deterministic roadmap gate that emits the eligible manifest used by selection/execution, recovers in-progress items, drafts missing authorized backlog items, and calls the same-version v2.14 NeurIPS selected-item stack. Malformed non-selected active items are excluded with diagnostics instead of crashing selection. A selected item's validated block is recorded and skipped on the next selector pass rather than stopping the whole drain. Provider-role inputs can route implementation execute/review/fix steps; the top-level wrapper defaults implementation execute to Claude Opus and review/fix to Codex. |
| `workflows/examples/neurips_steered_backlog_drain.legacy.yaml` | Legacy or migration; input-required | `2.7` | `neurips-steered-backlog-drain` | Legacy copy of the pre-v2.14 top-level NeurIPS drain, retained as the old-stack comparison surface for equivalence tests. Do not use it as the normal authoring target. |
| `workflows/examples/repeat_until_demo.yaml` | Current canonical; reusable call-based | `2.7` | `repeat-until-demo` | Demonstrates post-test `repeat_until` with loop-frame outputs, nested `call` + `match` body composition, and resume-safe iteration/condition bookkeeping. |
| `workflows/examples/generic_task_plan_execute_review_loop.yaml` | Legacy or migration | `1.4` | `generic-task-plan-execute-review-loop` | Full task workflow with plan, execution, checks, review, fix, and bounded cycles. |
| `workflows/examples/output_capture_demo.yaml` | Legacy or migration | `1.1` | `output_capture_demo` | Demonstrates `text`, `lines`, and `json` capture modes plus tee behavior. |
| `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml` | Downstream reference; prompt asset issue | `1.2` | `backlog-plan-impl-review-loop-v2` | Downstream reference workflow for a non-trivial backlog/implementation/review loop. |
| `workflows/examples/retry_demo.yaml` | Legacy or migration; prompt asset issue | `1.1` | `Retry Demo Workflow` | Demonstrates retry defaults, explicit retry policy, and timeout handling. |
| `workflows/examples/test_fix_loop_v0.yaml` | Legacy or migration | `1.1.1` | `test-fix-loop-v0` | Minimal test/fix loop with a shell gate and bounded retry count. |
| `workflows/examples/test_validation.yml` | Legacy or migration | `1.1` | `validation test` | Loader-validation fixture showing valid and intentionally commented invalid forms. |
| `workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml` | One-off | `2.7` | `typed-workflow-ast-ir-pipeline-finish-item0` | One-off workflow for backlog item `typed-workflow-ast-ir-pipeline`: reuse the approved design and plan, then run only the implementation review/fix phase with isolated state and report outputs. |
| `workflows/examples/unit_of_work_plus_test_fix_v0.yaml` | Legacy or migration | `1.1.1` | `unit-of-work-plus-test-fix-v0` | Unit-of-work execution followed by a bounded post-work test/fix loop. |
| `workflows/examples/wait_for_example.yaml` | Legacy or migration | `1.1` | `wait-for-example` | Minimal `wait_for` example for task-file arrival polling. |

## Prompt Asset Issue Notes

The generated prompt map is the source for exact missing-file rows. Current classifications:

- `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml`: external downstream snapshot; references downstream `prompts/workflows/backlog_plan_loop/*` assets not included in this repo snapshot.
- `workflows/examples/retry_demo.yaml`: stale example asset `test_prompt.txt`; keep as a retry schema example unless runnable provider prompt content becomes necessary.

## Reusable Library Workflows

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/library/backlog_item_design_plan_impl_stack.yaml` | `2.7` | `backlog-item-design-plan-impl-stack` | Per-item reusable stack for the priority backlog driver: run design, plan, and implementation phases, convert any phase failure into a terminal item outcome, and export item summary/report paths. |
| `workflows/library/seeded_design_plan_impl_stack.yaml` | `2.7` | `seeded-design-plan-impl-stack` | Reusable seeded stack: review/revise an existing design candidate, review/revise an existing plan candidate, then run the generic implementation review/fix phase. |
| `workflows/library/revision_study_priority_design_plan_impl_stack.yaml` | `2.7` | `revision-study-priority-design-plan-impl-stack` | Reusable revision-study adapter: reads a priority manifest of revision design inputs, emits mutable backlog-compatible working design seeds and per-item state/artifact roots, then calls the generic `backlog_item_design_plan_impl_stack.yaml` design -> plan -> implementation stack. |
| `workflows/library/tracked_design_phase.yaml` | `2.7` | `tracked-design-phase` | Reusable tracked design/ADR phase: draft design, run tracked hard-nosed review/revise loop, allow explicit `BLOCK`, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/tracked_design_phase.orc` | `2.14` | `tracked-design-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked design phase contract. |
| `workflows/library/tracked_plan_phase.yaml` | `2.7` | `tracked-plan-phase` | Reusable tracked plan phase: draft plan from an approved design, reconcile carried findings across iterations, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/tracked_plan_phase.orc` | `2.14` | `tracked-plan-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the tracked plan phase contract. |
| `workflows/library/roadmap_tranche_selector.yaml` | `2.7` | `roadmap-tranche-selector` | Reusable provider-backed selector that chooses the next coherent plan scope from design, roadmap, and progress-ledger context. |
| `workflows/library/roadmap_seeded_plan_phase.yaml` | `2.7` | `roadmap-seeded-plan-phase` | Reusable plan phase variant that injects both approved design and roadmap context into draft/review/revise planning provider steps while preserving the tracked plan review loop shape. |
| `workflows/library/design_plan_impl_implementation_phase.yaml` | `2.7` | `design-plan-impl-implementation-phase` | Reusable implementation phase for the full stack example: implement against design + plan, then review/fix until the implementation is approved, using bundled prompt assets under `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/design_plan_impl_implementation_phase.orc` | `2.14` | `design-plan-impl-implementation-phase` | Additive Workflow Lisp migration-tranche counterpart for compile/surface-parity checks of the implementation phase contract. |
| `workflows/library/neurips_backlog_selector.yaml` | `2.7` | `neurips-backlog-selector` | Reusable selector for the steered NeurIPS backlog drain: consumes steering, design, roadmap, backlog manifest, progress ledger, and run state, then emits `SELECTED`, `DONE`, or `BLOCKED`. |
| `workflows/library/neurips_backlog_gap_drafter.yaml` | `2.7` | `neurips-backlog-gap-drafter` | Reusable gap drafter that creates a missing active backlog item only when the current deterministic roadmap gate authorizes the missing scope, then validates the draft. |
| `workflows/library/neurips_backlog_roadmap_sync_phase.yaml` | `2.7` | `neurips-backlog-roadmap-sync-phase` | Reusable roadmap-sync phase for selected backlog items: reviews whether the selected item is roadmap-consistent and emits `NO_CHANGE`, `UPDATED`, or `BLOCKED`. |
| `workflows/library/neurips_backlog_seeded_plan_phase.yaml` | `2.7` | `neurips-backlog-seeded-plan-phase` | Reusable planning phase for one selected backlog item: drafts a fresh plan from steering, design, roadmap, item context, and progress ledger, then runs a review/revise loop. |
| `workflows/library/neurips_backlog_implementation_phase.yaml` | `2.7` | `neurips-backlog-implementation-phase` | Reusable implementation phase for one selected backlog item: executes one reviewable implementation pass, materializes fresh execution or blocker evidence, runs review/fix until approval, and exports `COMPLETED` only after review approval or `BLOCKED` only for a validated external blocker. Execute/review/fix provider roles are configurable through typed inputs with Codex defaults. Existing NeurIPS run state with old `RUNNING` or `WAITING` values should be completed, blocked, or restarted before resuming with this contract. |
| `workflows/library/neurips_selected_backlog_item.yaml` | `2.7` | `neurips-selected-backlog-item` | Reusable selected-item stack for the steered backlog drain: materializes selected item context, runs roadmap sync, moves active items to in-progress, plans, implements, reconciles, and emits the drain status. |
| `workflows/library/neurips_backlog_implementation_phase.v214.yaml` | `2.14` | `neurips-backlog-implementation-phase-v214` | Phase 2 same-version v2.14 counterpart to `neurips_backlog_implementation_phase.yaml`. Replaces the old `phase_started_at_ns` mtime gate plus flat-optional `output_bundle` variant emulation with `materialize_artifacts` for input/target pointers, `pre_snapshot` + `select_variant_output` for content-based outcome selection, and `requires_variant` proof for variant-only publish steps. |
| `workflows/library/neurips_backlog_selector.v214.yaml` | `2.14` | `neurips-backlog-selector-v214` | Same-version v2.14 selector counterpart used by the canonical top-level drain. It is currently a compatibility migration of the `2.7` selector so the top-level v2.14 workflow does not call an older callee. |
| `workflows/library/neurips_backlog_gap_drafter.v214.yaml` | `2.14` | `neurips-backlog-gap-drafter-v214` | Same-version v2.14 gap-drafter counterpart used by the canonical top-level drain. It is currently a compatibility migration of the `2.7` gap drafter so the top-level v2.14 workflow does not call an older callee. |
| `workflows/library/neurips_backlog_seeded_plan_phase.v214.yaml` | `2.14` | `neurips-backlog-seeded-plan-phase-v214` | Phase 2 same-version v2.14 counterpart to `neurips_backlog_seeded_plan_phase.yaml`. Replaces the old bash plan-context pointer-write boilerplate with one `materialize_artifacts` step while preserving the draft/review/revise plan loop. |
| `workflows/library/neurips_backlog_roadmap_sync.v214.yaml` | `2.14` | `neurips-backlog-roadmap-sync-v214` | Phase 2 same-version v2.14 counterpart to `neurips_backlog_roadmap_sync_phase.yaml`. Replaces the old bash pointer-write inputs step with one `materialize_artifacts` step; otherwise minimal compatibility refactor. |
| `workflows/library/neurips_selected_backlog_item.v214.yaml` | `2.14` | `neurips-selected-backlog-item-v214` | Phase 2 same-version v2.14 counterpart to `neurips_selected_backlog_item.yaml`. Imports only the `.v214.yaml` phase workflows, validates `selected-item-inputs.json` directly with `variant_output`, and keeps domain-shaped recovery, reconcile, queue-move, run-state, and outcome-recording scripts unchanged without reviving per-field pointer fanout. |
| `workflows/library/lisp_frontend_design_delta_selector.v214.yaml` | `2.14` | `lisp-frontend-design-delta-selector-v214` | Design-delta selector subworkflow: consumes steering, target/baseline design specs, backlog manifest, progress ledger, and run state, then emits `SELECT_BACKLOG_ITEM`, `DRAFT_DESIGN_GAP`, `DONE`, or `BLOCKED`. |
| `workflows/library/lisp_frontend_design_delta_design_gap_architect.v214.yaml` | `2.14` | `lisp-frontend-design-delta-design-gap-architect-v214` | Design-delta design-gap architect: target/baseline variant of the architecture drafting+validation stack. |
| `workflows/library/lisp_frontend_design_delta_work_item.v214.yaml` | `2.14` | `lisp-frontend-design-delta-work-item-v214` | Design-delta work-item stack: target/baseline variant that imports the design-delta plan and implementation phases. |
| `workflows/library/lisp_frontend_design_delta_plan_phase.v214.yaml` | `2.14` | `lisp-frontend-design-delta-plan-phase-v214` | Design-delta planning phase variant that treats target design as the active authority and baseline design as compatibility context. |
| `workflows/library/lisp_frontend_design_delta_implementation_phase.v214.yaml` | `2.14` | `lisp-frontend-design-delta-implementation-phase-v214` | Design-delta implementation phase variant using target/baseline design inputs and isolated design-delta prompt assets. |

### When to use the v2.14 NeurIPS stack

The canonical top-level NeurIPS drain at `workflows/examples/neurips_steered_backlog_drain.yaml` now runs as DSL `2.14` and imports only same-version v2.14 callees. The `*.v214.yaml` library workflows above are the Phase 2 same-version translation of the existing `2.7` NeurIPS selected-item stack. They replace only the glue patterns the v2.14 runtime now supports as first-class primitives:

- `materialize_artifacts`: deterministic input/target pointer materialization that previously required bash `printf` + pointer-file `expected_outputs`.
- `materialize_artifacts.input_values`: shorthand for uniform workflow-input pointer materialization when the authored contract is pure inheritance plus a repeated pointer template.
- `pre_snapshot` + `select_variant_output`: content-hash-based outcome selection that previously relied on `phase_started_at_ns` mtime checks plus a flat-optional `output_bundle` tagged-union emulation.
- `variant_output` (used directly on `selected-item-inputs.json` and implicitly through `select_variant_output`): a tagged-union JSON contract with optional `shared_fields`, validated atomically before commit, replacing optional-field and per-field fanout patterns.
- `requires_variant`: proof annotation that allows variant-only publish steps to reference selected-variant artifacts safely.

Compact v2.14 authoring pattern:

- Keep native JSON bundles when the producer already emits the right shape; prefer validating the bundle directly over splitting it into sidecar text files.
- Use `output_bundle` for fixed-shape JSON outputs whose fields are always available.
- Use `variant_output` only when field availability truly depends on a discriminant, and move always-present fields into `shared_fields`.

The original `2.7` workflows remain in place as the migration baseline and as the legacy comparison surface for behavioral-equivalence oracles. They are not deprecated by this tranche; a later removal decision is out of scope.
| `workflows/library/review_fix_loop.yaml` | `2.5` | `review-fix-loop` | Minimal reusable call demo library. |
| `workflows/library/revision_study_design_plan_impl_stack.yaml` | `2.7` | `revision-study-design-plan-impl-stack` | Specialized call-based revision-study workflow: treats a human revision design seed as read-only, produces an approved derived design, drafts/reviews a plan, then executes/reviews implementation using bundled prompts under `workflows/library/prompts/revision_study_stack/`. Read it with its imported phase workflows and prompt directory when the generic adapter is not enough, then adapt and revalidate rather than copying it directly. |
| `workflows/library/revision_study_design_plan_impl_monolith.yaml` | `2.7` | `revision-study-design-plan-impl-monolith` | No-import revision-study fallback for portability or debugging when adapting the call-based import tree is not practical. Keep behavior aligned with the call-based stack; do not use it as the normal authoring target. |
| `workflows/library/revision_study_design_phase.yaml` | `2.7` | `revision-study-design-phase` | Reusable design-review phase for revision studies; derives an approved design artifact from a read-only revision design seed and tracks open design findings. |
| `workflows/library/revision_study_plan_phase.yaml` | `2.7` | `revision-study-plan-phase` | Reusable plan-review phase for revision studies; drafts and reviews an implementation plan from the approved revision design. |
| `workflows/library/revision_study_implementation_phase.yaml` | `2.7` | `revision-study-implementation-phase` | Reusable implementation review/fix phase for revision studies; executes the approved plan and reviews remaining required study/manuscript work. |

## Related Docs

- `docs/workflow_drafting_guide.md`: authoring guidance for robust workflows
- `docs/work_definition_model.md`: explanatory split between semantic specs, work instructions, workflow mechanics, work items, and run evidence
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
