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
| `workflows/examples/backlog_plan_execute_v0.yaml` | Legacy or migration | `1.1.1` | `backlog-plan-execute-v0` | Minimal backlog -> draft plan -> execute flow with deterministic file outputs and optional review loop. |
| `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` | Legacy or migration | `1.2` | `backlog-plan-execute-v1-2-dataflow` | Execute/review/fix loop showing publish/consume artifact lineage and freshness semantics. |
| `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml` | Legacy or migration | `1.3` | `backlog-plan-execute-v1-3-json-bundles` | Execute/review/fix loop using `output_bundle` and `consume_bundle` for strict JSON-gated routing. |
| `workflows/examples/backlog_priority_design_plan_impl_stack_v2_call.yaml` | Reusable call-based | `2.7` | `backlog-priority-design-plan-impl-stack-v2-call` | Ordered backlog driver: iterates a priority manifest, runs one per-item design -> plan -> implementation stack, and skips only the current item when any phase fails. |
| `workflows/examples/call_subworkflow_demo.yaml` | Reusable call-based | `2.5` | `call-subworkflow-demo` | Demonstrates inline reusable `call` execution, persisted call-frame state, and caller-visible outputs exported from a library workflow. |
| `workflows/examples/cycle_guard_demo.yaml` | Current canonical | `1.8` | `cycle-guard-demo` | Demonstrates `max_visits`/`max_transitions` counters, a typed `assert.compare` loop gate, and terminal guard-stop behavior without shell counters. |
| `workflows/examples/depends_on_inject_imported_v2_call.yaml` | Reusable call-based | `2.7` | `depends-on-inject-imported-v2-call` | Demonstrates an imported callee that combines workflow-source prompt assets with workspace `depends_on.inject`, using a local provider to emit a deterministic review decision. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | Current canonical; reusable call-based | `2.7` | `design-plan-impl-review-stack-v2-call` | Full stack example: tracked design/ADR loop, tracked plan loop, then implementation review/fix, composed from reusable `call`-based phase workflows. |
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
| `workflows/library/tracked_design_phase.yaml` | `2.7` | `tracked-design-phase` | Reusable tracked design/ADR phase: draft design, run tracked hard-nosed review/revise loop, allow explicit `BLOCK`, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/tracked_plan_phase.yaml` | `2.7` | `tracked-plan-phase` | Reusable tracked plan phase: draft plan from an approved design, reconcile carried findings across iterations, and ship its bundled prompt assets from `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/design_plan_impl_implementation_phase.yaml` | `2.7` | `design-plan-impl-implementation-phase` | Reusable implementation phase for the full stack example: implement against design + plan, then review/fix until the implementation is approved, using bundled prompt assets under `workflows/library/prompts/design_plan_impl_stack_v2_call/`. |
| `workflows/library/depends_on_inject_imported_review.yaml` | `2.7` | `depends-on-inject-imported-review` | Library workflow for the imported-injection example: prepends workflow-source rubric assets, then injects a caller-produced runtime manifest into the provider prompt before exporting an enum review decision. |
| `workflows/library/review_fix_loop.yaml` | `2.5` | `review-fix-loop` | Minimal reusable call demo library used by `call_subworkflow_demo.yaml`. |

## Related Docs

- `docs/workflow_drafting_guide.md`: authoring guidance for robust workflows
- `workflows/examples/README_v0_artifact_contract.md`: runbook for the artifact-contract prototype examples
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
