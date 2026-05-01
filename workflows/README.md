# Workflow Index

This file is an informative catalog of workflow YAML under `workflows/`.
The YAML files remain the source of truth for exact behavior, prompts, contracts, and routing.

Run workflows from the repo root:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/<workflow>.yaml --dry-run
```

Some workflows declare required typed inputs. For those, pass fixture inputs explicitly:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/workflow_signature_demo.yaml \
  --dry-run --input task_path=workflows/examples/inputs/demo-task.md

PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml \
  --dry-run --input upstream_state_path=workflows/examples/inputs/dsl-follow-on-upstream-completed-state.json
```

## Directory Map

- `workflows/examples/`: runnable example workflows and validation fixtures
- `workflows/library/`: reusable imported subworkflows used by `call`-based examples
- `workflows/library/prompts/`: repo-owned prompt assets bundled with reusable imported workflows
- `workflows/examples/prompts/`: prompt files used only by example workflows stored under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by standalone or monolithic workflows

When invoking a workflow from another repository checkout, prefer copying the relevant call-based stack
with its imported library workflows and bundled prompt directory. Use a no-import monolith such as
`workflows/library/revision_study_design_plan_impl_monolith.yaml` only as a portability or debugging
fallback when copying the import tree is not practical.

## Prompt Resolution

For an exhaustive workflow-to-prompt table, see `docs/workflow_prompt_map.md`.

Resolution rules:
- `input_file` is repo-root relative and is intended for workspace-owned or runtime-generated prompt material.
- `asset_file` is relative to the workflow YAML file and is intended for prompt assets bundled with reusable workflows.
- `asset_depends_on` follows the same workflow-source-relative rule as `asset_file`.

The prompt map reports missing paths; a missing path may indicate a stale example, a downstream snapshot with external assets, or a prompt generated at runtime by an earlier step.

## Catalog Status

- **Current canonical**: preferred examples for new workflow authoring.
- **Reusable call-based**: examples that exercise imported library workflows and bundled prompt assets.
- **Legacy or migration**: still useful as historical or migration references, but not the first place to copy patterns.
- **Negative fixture**: expected to fail validation or runtime checks for a specific test purpose.
- **Input-required**: requires `--input` or fixture files for dry-run validation.
- **Prompt asset issue**: references missing or external prompt assets; check `docs/workflow_prompt_map.md` before running.
- **Needs schema cleanup**: use this status when an example fails dry-run validation because it predates current loader schema.

## Workflow Catalog

| Path | Status | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- | --- |
| `workflows/examples/adjudicated_provider_demo.yaml` | Current canonical | `2.11` | `adjudicated-provider-demo` | Demonstrates an adjudicated provider step with isolated candidate workspaces, evaluator scoring, selected artifact promotion, and a terminal score ledger mirror. |
| `workflows/examples/backlog_plan_execute_v0.yaml` | Legacy or migration | `1.1.1` | `backlog-plan-execute-v0` | Minimal backlog -> draft plan -> execute flow with deterministic file outputs and optional review loop. |
| `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` | Legacy or migration | `1.2` | `backlog-plan-execute-v1-2-dataflow` | Execute/review/fix loop showing publish/consume artifact lineage and freshness semantics. |
| `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml` | Legacy or migration | `1.3` | `backlog-plan-execute-v1-3-json-bundles` | Execute/review/fix loop using `output_bundle` and `consume_bundle` for strict JSON-gated routing. |
| `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml` | Reusable call-based | `2.7` | `backlog-priority-design-plan-impl-stack-v2-call` | Ordered backlog driver: iterates a priority manifest, runs one per-item design -> plan -> implementation stack, and skips only the current item when any phase fails. |
| `workflows/examples/revision_study_priority_design_plan_impl_stack_v2_call.yaml` | Reusable call-based | `2.7` | `revision-study-priority-design-plan-impl-stack-v2-call` | Thin runnable wrapper around the reusable revision-study priority adapter, with an example manifest fixture. |
| `workflows/examples/major_project_tranche_design_plan_impl_stack_v2_call.yaml` | Reusable call-based | `2.7` | `major-project-tranche-design-plan-impl-stack-v2-call` | One-tranche major-project driver: calls the roadmap phase from a broad brief, selects one ready tranche from the generated manifest, then calls the big-design -> plan -> implementation stack. |
| `workflows/examples/major_project_tranche_continue_from_approved_design_v2_call.yaml` | Reusable call-based; input-required | `2.12` | `major-project-tranche-continue-from-approved-design-v2-call` | One-tranche major-project continuation driver: selects the next ready tranche from an existing manifest, starts from an already-approved design at the plan phase, and still routes plan-level redesign escalation through the full big-design/plan/implementation stack before updating or blocking the manifest. |
| `workflows/examples/major_project_tranche_drain_stack_v2_call.yaml` | Reusable call-based | `2.7` | `major-project-tranche-drain-stack-v2-call` | Full major-project drain driver: calls the roadmap phase once, then loops by calling the reusable drain-iteration workflow until all tranches are complete or the queue is blocked. |
| `workflows/examples/major_project_tranche_drain_from_manifest_v2_call.yaml` | Reusable call-based; input-required | `2.7` | `major-project-tranche-drain-from-manifest-v2-call` | Continuation driver for an already-approved roadmap: consumes an existing project brief, project roadmap, and tranche manifest, then starts directly at the reusable manifest-drain iteration loop. |
| `workflows/examples/call_subworkflow_demo.yaml` | Reusable call-based | `2.5` | `call-subworkflow-demo` | Demonstrates inline reusable `call` execution, persisted call-frame state, and caller-visible outputs exported from a library workflow. |
| `workflows/examples/cycle_guard_demo.yaml` | Current canonical | `1.8` | `cycle-guard-demo` | Demonstrates `max_visits`/`max_transitions` counters, a typed `assert.compare` loop gate, and terminal guard-stop behavior without shell counters. |
| `workflows/examples/depends_on_inject_imported_v2_call.yaml` | Reusable call-based | `2.7` | `depends-on-inject-imported-v2-call` | Demonstrates an imported callee that combines workflow-source prompt assets with workspace `depends_on.inject`, using a local provider to emit a deterministic review decision. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | Current canonical; reusable call-based | `2.7` | `design-plan-impl-review-stack-v2-call` | Full stack example: tracked design/ADR loop, tracked plan loop, then implementation review/fix, composed from reusable `call`-based phase workflows. |
| `workflows/examples/neurips_hybrid_resnet_plan_impl_review.yaml` | Reusable call-based; input-required | `2.7` | `neurips-hybrid-resnet-tranche-drain-plan-impl-review` | Loops over roadmap tranche selection from supplied design + roadmap inputs, then reuses the roadmap-seeded plan phase and implementation review/fix phase for each selected tranche. |
| `workflows/examples/neurips_steered_backlog_drain.yaml` | Downstream reference; reusable call-based; input-required | `2.7` | `neurips-steered-backlog-drain` | Steered backlog drain wrapper copied from PtychoPINN: builds a raw backlog manifest, applies a deterministic roadmap gate that emits the eligible manifest used by selection/execution, recovers in-progress items, drafts missing authorized backlog items, and calls the reusable NeurIPS selected-item stack. Provider-role inputs can route implementation execute/review/fix steps while defaults remain Codex. |
| `workflows/examples/assert_gate_demo.yaml` | Current canonical | `1.5` | `assert-gate-demo` | Demonstrates first-class `assert` gates and `on.failure.goto` recovery without shell glue. |
| `workflows/examples/bad_processed.yaml` | Negative fixture | `1.1` | `bad_processed` | Negative fixture for path-safety validation of an invalid `processed_dir`. |
| `workflows/examples/claude_basic.yaml` | Legacy or migration; prompt asset issue | `1.1` | `claude_basic_example` | Smallest Claude provider example using argv prompt delivery. |
| `workflows/examples/claude_with_model.yaml` | Legacy or migration; prompt asset issue | `1.1` | `claude_model_example` | Claude provider example with default model selection and per-step override. |
| `workflows/examples/cli_test.yaml` | Legacy or migration | `1.1` | `cli_test` | Minimal CLI-oriented workflow that creates a file and captures directory listing output. |
| `workflows/examples/conditional_demo.yaml` | Legacy or migration | `1.1` | `Conditional Execution Demo` | Demonstrates `when.equals`, `when.exists`, and `when.not_exists`. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml` | Legacy or migration | `1.4` | `dsl-follow-on-plan-impl-review-loop` | Waits for the active DSL ADR review loop to finish, drafts an implementation plan from the ADR, then runs bounded plan and implementation review/fix loops. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml` | Current structured; input-required | `2.7` | `dsl-follow-on-plan-impl-review-loop-v2` | Structured rewrite of the follow-on workflow using typed `inputs`/`outputs`, stable step `id`s, `match`, and `repeat_until`, while leaving the `1.4` version in place for comparison. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` | Reusable call-based; input-required | `2.7` | `dsl-follow-on-plan-impl-review-loop-v2-call` | Modular follow-on rewrite: a small parent workflow waits for upstream completion, then `call`s reusable plan and implementation phase subworkflows and exports their declared outputs directly. |
| `workflows/examples/dsl_tracked_plan_review_loop.yaml` | Legacy or migration | `1.4` | `dsl-tracked-plan-review-loop` | Plan-only example showing stable finding tracking: fresh review plus open-findings reconciliation, targeted revision, and cycle-specific JSON review artifacts. |
| `workflows/examples/dsl_review_first_fix_loop.yaml` | Legacy or migration | `1.4` | `dsl-review-first-fix-loop` | Review-first Codex loop: review the DSL ADR, fix against consumed review feedback, repeat until no `## High` section remains. |
| `workflows/examples/dsl_review_first_fix_loop_provider_session.yaml` | Legacy or migration | `2.10` | `dsl-review-first-fix-loop-provider-session` | Provider-session migration example: fresh review-session creation, runtime-owned session-handle publication, review gating, and resume-based fix steps without hard-coded shell `codex exec resume ...` glue. |
| `workflows/examples/env_literal.yaml` | Legacy or migration | `1.1` | _(unnamed)_ | Demonstrates literal `env` semantics, including loop variables that are not substituted inside `env`. |
| `workflows/examples/finally_demo.yaml` | Current canonical | `2.3` | `finally-demo` | Demonstrates top-level `finally`, resume-safe cleanup bookkeeping, and workflow outputs deferred until cleanup succeeds. |
| `workflows/examples/match_demo.yaml` | Current canonical | `2.6` | `match-demo` | Demonstrates top-level structured `match`, exhaustive enum case coverage, and case outputs materialized onto the statement node. |
| `workflows/examples/repeat_until_demo.yaml` | Current canonical; reusable call-based | `2.7` | `repeat-until-demo` | Demonstrates post-test `repeat_until` with loop-frame outputs, nested `call` + `match` body composition, and resume-safe iteration/condition bookkeeping. |
| `workflows/examples/score_gate_demo.yaml` | Current canonical | `2.8` | `score-gate-demo` | Demonstrates the `score` predicate helper for benchmark thresholds plus score-band routing through top-level structured control. |
| `workflows/examples/for_each_demo.yaml` | Legacy or migration | `1.1` | _(unnamed)_ | Demonstrates `for_each` with `items_from`, aliases, and JSON dot-path array selection. |
| `workflows/examples/generic_task_plan_execute_review_loop.yaml` | Legacy or migration | `1.4` | `generic-task-plan-execute-review-loop` | Full task workflow with plan, execution, checks, review, fix, and bounded cycles. |
| `workflows/examples/injection_demo.yaml` | Legacy or migration; prompt asset issue | `1.1.1` | _(unnamed)_ | Demonstrates dependency injection modes and placement behavior for provider prompts. |
| `workflows/examples/observability_runtime_config_demo.yaml` | Legacy or migration | `1.3` | `observability_runtime_config_demo` | Shows runtime observability flags without adding observability syntax to the DSL. |
| `workflows/examples/output_capture_demo.yaml` | Legacy or migration | `1.1` | `output_capture_demo` | Demonstrates `text`, `lines`, and `json` capture modes plus tee behavior. |
| `workflows/examples/prompt_audit_demo.yaml` | Legacy or migration; prompt asset issue | `1.1.1` | _(unnamed)_ | Demonstrates prompt audit files emitted by `--debug` for argv and stdin providers. |
| `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml` | Downstream reference; prompt asset issue | `1.2` | `backlog-plan-impl-review-loop-v2` | Downstream reference workflow for a non-trivial backlog/implementation/review loop. |
| `workflows/examples/retry_demo.yaml` | Legacy or migration; prompt asset issue | `1.1` | `Retry Demo Workflow` | Demonstrates retry defaults, explicit retry policy, and timeout handling. |
| `workflows/examples/scalar_bookkeeping_demo.yaml` | Current canonical | `1.7` | `scalar-bookkeeping-demo` | Demonstrates `set_scalar`/`increment_scalar` producing local step artifacts and publishing scalar lineage without shell glue. |
| `workflows/examples/structured_if_else_demo.yaml` | Current canonical | `2.2` | `structured-if-else-demo` | Demonstrates top-level structured `if/else`, lowered branch-node identities, and branch outputs materialized onto the statement node. |
| `workflows/examples/test_fix_loop_v0.yaml` | Legacy or migration | `1.1.1` | `test-fix-loop-v0` | Minimal test/fix loop with a shell gate and bounded retry count. |
| `workflows/examples/test_validation.yml` | Legacy or migration | `1.1` | `validation test` | Loader-validation fixture showing valid and intentionally commented invalid forms. |
| `workflows/examples/typed_predicate_routing.yaml` | Current canonical | `1.6` | `typed-predicate-routing` | Demonstrates structured `ref:` predicates against step artifacts and normalized recovered-failure outcomes. |
| `workflows/examples/typed_workflow_ast_ir_pipeline_finish_item0.yaml` | One-off | `2.7` | `typed-workflow-ast-ir-pipeline-finish-item0` | One-off workflow for backlog item `typed-workflow-ast-ir-pipeline`: reuse the approved design and plan, then run only the implementation review/fix phase with isolated state and report outputs. |
| `workflows/examples/unit_of_work_plus_test_fix_v0.yaml` | Legacy or migration | `1.1.1` | `unit-of-work-plus-test-fix-v0` | Unit-of-work execution followed by a bounded post-work test/fix loop. |
| `workflows/examples/workflow_signature_demo.yaml` | Current canonical; input-required | `2.1` | `workflow-signature-demo` | Demonstrates typed workflow `inputs`/`outputs`, `${inputs.*}` substitution, `ref: inputs.*` gating, and validated workflow output export. |
| `workflows/examples/wait_for_example.yaml` | Legacy or migration | `1.1` | `wait-for-example` | Minimal `wait_for` example for task-file arrival polling. |

## Prompt Asset Issue Notes

The generated prompt map is the source for exact missing-file rows. Current classifications:

- `workflows/examples/claude_basic.yaml` and `workflows/examples/claude_with_model.yaml`: stale example assets under root `prompts/`; keep as legacy provider-shape examples unless the repo needs runnable Claude prompt fixtures.
- `workflows/examples/injection_demo.yaml`: stale example assets under root `prompts/`; the workflow now validates structurally, but the prompt files are not part of the current prompt catalog.
- `workflows/examples/prompt_audit_demo.yaml`: mixed case; `prompts/implement.md` is generated at runtime by `PreparePrompt`, while `prompts/analyze.md` is a stale example asset.
- `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml`: external downstream snapshot; references downstream `prompts/workflows/backlog_plan_loop/*` assets not included in this repo snapshot.
- `workflows/examples/retry_demo.yaml`: stale example asset `test_prompt.txt`; keep as a retry schema example unless runnable provider prompt content becomes necessary.

## Reusable Library Workflows

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/library/follow_on_plan_phase.yaml` | `2.7` | `follow-on-plan-phase` | Reusable plan-phase subworkflow for the modular follow-on example: draft plan, run structured plan review/revise loop, and ship its bundled prompt assets from `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/`. |
| `workflows/library/follow_on_implementation_phase.yaml` | `2.7` | `follow-on-implementation-phase` | Reusable implementation-phase subworkflow for the modular follow-on example: execute plan work, run structured implementation review/fix loop, and ship its bundled prompt assets from `workflows/library/prompts/dsl_follow_on_plan_impl_loop_v2_call/`. |
| `workflows/library/backlog_item_design_plan_impl_stack.yaml` | `2.7` | `backlog-item-design-plan-impl-stack` | Per-item reusable stack for the priority backlog driver: run design, plan, and implementation phases, convert any phase failure into a terminal item outcome, and export item summary/report paths. |
| `workflows/library/seeded_design_plan_impl_stack.yaml` | `2.7` | `seeded-design-plan-impl-stack` | Reusable seeded stack: review/revise an existing design candidate, review/revise an existing plan candidate, then run the generic implementation review/fix phase. |
| `workflows/library/major_project_roadmap_phase.yaml` | `2.7` | `major-project-roadmap-phase` | Reusable roadmap phase for broad project briefs: drafts, validates, reviews, and revises a project roadmap plus ordered tranche manifest before tranche execution. |
| `workflows/library/tracked_big_design_phase.yaml` | `2.7` | `tracked-big-design-phase` | Reusable big-design phase for one selected tranche: consumes project roadmap and escalation context, drafts a self-contained tranche design, and runs tracked review/revise with `BLOCK` plus roadmap-revision escalation. |
| `workflows/library/major_project_tranche_plan_phase.yaml` | `2.7` | `major-project-tranche-plan-phase` | Major-project-local plan phase: consumes upstream escalation context plus the roadmap-authoritative scope boundary, reviews plans with `APPROVE`, `REVISE`, `ESCALATE_REDESIGN`, or `BLOCK`, and emits plan escalation context. |
| `workflows/library/major_project_tranche_implementation_phase.yaml` | `2.7` | `major-project-tranche-implementation-phase` | Major-project-local implementation phase: consumes the roadmap-authoritative scope boundary, tracks cumulative implementation review iterations, injects threshold context, and lets review return `APPROVE`, `REVISE`, `ESCALATE_REPLAN`, `ESCALATE_ROADMAP_REVISION`, or `BLOCK`. |
| `workflows/library/major_project_roadmap_revision_phase.yaml` | `2.12` | `major-project-roadmap-revision-phase` | Major-project-local roadmap revision phase: consumes a structured roadmap change request, revises the approved roadmap plus tranche manifest, and records advisory review findings without blocking finalized candidates. |
| `workflows/library/major_project_tranche_drain_iteration.yaml` | `2.12` | `major-project-tranche-drain-iteration` | One major-project drain iteration: selects a tranche, runs the selected tranche stack, updates the manifest for terminal tranche outcomes, or promotes roadmap-revision outputs for advisory `APPROVE`, `REVISE`, or `BLOCK` decisions. Selection now publishes a scope-boundary path so local phases cannot redefine tranche completion. |
| `workflows/library/major_project_tranche_design_plan_impl_stack.yaml` | `2.7` | `major-project-tranche-design-plan-impl-stack` | Reusable major-project tranche stack: runs tracked big design, major-project-local planning, and major-project-local implementation with upward rerouting for replan, redesign, and roadmap revision. The stack materializes a roadmap-authoritative scope boundary and guards implementation approval before emitting item `APPROVED`. |
| `workflows/library/major_project_tranche_plan_impl_from_approved_design_stack.yaml` | `2.7` | `major-project-tranche-plan-impl-from-approved-design-stack` | Compatibility adapter for approved-design continuation: invokes the phase-complete major-project tranche stack with `initial_phase: plan`, preserving the historical input shape while sharing redesign, replan, implementation, and roadmap-escalation routing with the full stack. |
| `workflows/library/revision_study_priority_design_plan_impl_stack.yaml` | `2.7` | `revision-study-priority-design-plan-impl-stack` | Reusable revision-study adapter: reads a priority manifest of revision design inputs, emits mutable backlog-compatible working design seeds and per-item state/artifact roots, then calls the generic `backlog_item_design_plan_impl_stack.yaml` design -> plan -> implementation stack. |
| `workflows/library/tracked_design_phase.yaml` | `2.7` | `tracked-design-phase` | Reusable tracked design/ADR phase: draft design, run tracked hard-nosed review/revise loop, allow explicit `BLOCK`, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/tracked_plan_phase.yaml` | `2.7` | `tracked-plan-phase` | Reusable tracked plan phase: draft plan from an approved design, reconcile carried findings across iterations, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/roadmap_tranche_selector.yaml` | `2.7` | `roadmap-tranche-selector` | Reusable provider-backed selector that chooses the next coherent plan scope from design, roadmap, and progress-ledger context. |
| `workflows/library/roadmap_seeded_plan_phase.yaml` | `2.7` | `roadmap-seeded-plan-phase` | Reusable plan phase variant that injects both approved design and roadmap context into draft/review/revise planning provider steps while preserving the tracked plan review loop shape. |
| `workflows/library/design_plan_impl_implementation_phase.yaml` | `2.7` | `design-plan-impl-implementation-phase` | Reusable implementation phase for the full stack example: implement against design + plan, then review/fix until the implementation is approved, using bundled prompt assets under `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/neurips_backlog_selector.yaml` | `2.7` | `neurips-backlog-selector` | Reusable selector for the steered NeurIPS backlog drain: consumes steering, design, roadmap, backlog manifest, progress ledger, and run state, then emits `SELECTED`, `DONE`, or `BLOCKED`. |
| `workflows/library/neurips_backlog_gap_drafter.yaml` | `2.7` | `neurips-backlog-gap-drafter` | Reusable gap drafter that creates a missing active backlog item only when the current deterministic roadmap gate authorizes the missing scope, then validates the draft. |
| `workflows/library/neurips_backlog_roadmap_sync_phase.yaml` | `2.7` | `neurips-backlog-roadmap-sync-phase` | Reusable roadmap-sync phase for selected backlog items: reviews whether the selected item is roadmap-consistent and emits `NO_CHANGE`, `UPDATED`, or `BLOCKED`. |
| `workflows/library/neurips_backlog_seeded_plan_phase.yaml` | `2.7` | `neurips-backlog-seeded-plan-phase` | Reusable planning phase for one selected backlog item: drafts a fresh plan from steering, design, roadmap, item context, and progress ledger, then runs a review/revise loop. |
| `workflows/library/neurips_backlog_implementation_phase.yaml` | `2.7` | `neurips-backlog-implementation-phase` | Reusable implementation phase for one selected backlog item: executes the approved plan to terminal `COMPLETED` or `BLOCKED`, runs checks, and reviews/fixes completed work. Execute/review/fix provider roles are configurable through typed inputs with Codex defaults. Existing NeurIPS run state with old `RUNNING` or `WAITING` values should be completed, blocked, or restarted before resuming with this contract. |
| `workflows/library/neurips_selected_backlog_item.yaml` | `2.7` | `neurips-selected-backlog-item` | Reusable selected-item stack for the steered backlog drain: materializes selected item context, runs roadmap sync, moves active items to in-progress, plans, implements, reconciles, and emits the drain status. |
| `workflows/library/depends_on_inject_imported_review.yaml` | `2.7` | `depends-on-inject-imported-review` | Library workflow for the imported-injection example: prepends workflow-source rubric assets, then injects a caller-produced runtime manifest into the provider prompt before exporting an enum review decision. |
| `workflows/library/review_fix_loop.yaml` | `2.5` | `review-fix-loop` | Minimal reusable call demo library used by `call_subworkflow_demo.yaml`. |
| `workflows/library/revision_study_design_plan_impl_stack.yaml` | `2.7` | `revision-study-design-plan-impl-stack` | Specialized call-based revision-study workflow: treats a human revision design seed as read-only, produces an approved derived design, drafts/reviews a plan, then executes/reviews implementation using bundled prompts under `workflows/library/prompts/revision_study_stack/`. Copy this file with its imported phase workflows and prompt directory when the generic adapter is not enough. |
| `workflows/library/revision_study_design_plan_impl_monolith.yaml` | `2.7` | `revision-study-design-plan-impl-monolith` | No-import revision-study fallback for portability or debugging when copying the call-based import tree is not practical. Keep behavior aligned with the call-based stack; do not use it as the normal authoring target. |
| `workflows/library/revision_study_design_phase.yaml` | `2.7` | `revision-study-design-phase` | Reusable design-review phase for revision studies; derives an approved design artifact from a read-only revision design seed and tracks open design findings. |
| `workflows/library/revision_study_plan_phase.yaml` | `2.7` | `revision-study-plan-phase` | Reusable plan-review phase for revision studies; drafts and reviews an implementation plan from the approved revision design. |
| `workflows/library/revision_study_implementation_phase.yaml` | `2.7` | `revision-study-implementation-phase` | Reusable implementation review/fix phase for revision studies; executes the approved plan and reviews remaining required study/manuscript work. |

## Related Docs

- `docs/workflow_drafting_guide.md`: authoring guidance for robust workflows
- `workflows/examples/README_v0_artifact_contract.md`: runbook for the artifact-contract prototype examples
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
