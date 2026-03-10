# Workflow Index

This file is an informative catalog of workflow YAML under `workflows/`.
The YAML files remain the source of truth for exact behavior, prompts, contracts, and routing.

Run workflows from the repo root:

```bash
PYTHONPATH=/home/ollie/Documents/agent-orchestration \
python -m orchestrator run workflows/examples/<workflow>.yaml --dry-run
```

## Directory Map

- `workflows/examples/`: runnable example workflows and validation fixtures
- `workflows/library/`: reusable imported subworkflows used by `call`-based examples
- `workflows/examples/prompts/`: prompt files used only by example workflows stored under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by larger example workflows

## Workflow Catalog

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/examples/backlog_plan_execute_v0.yaml` | `1.1.1` | `backlog-plan-execute-v0` | Minimal backlog -> draft plan -> execute flow with deterministic file outputs and optional review loop. |
| `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` | `1.2` | `backlog-plan-execute-v1-2-dataflow` | Execute/review/fix loop showing publish/consume artifact lineage and freshness semantics. |
| `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml` | `1.3` | `backlog-plan-execute-v1-3-json-bundles` | Execute/review/fix loop using `output_bundle` and `consume_bundle` for strict JSON-gated routing. |
| `workflows/examples/call_subworkflow_demo.yaml` | `2.5` | `call-subworkflow-demo` | Demonstrates inline reusable `call` execution, persisted call-frame state, and caller-visible outputs exported from a library workflow. |
| `workflows/examples/cycle_guard_demo.yaml` | `1.8` | `cycle-guard-demo` | Demonstrates `max_visits`/`max_transitions` counters, a typed `assert.compare` loop gate, and terminal guard-stop behavior without shell counters. |
| `workflows/examples/design_plan_impl_review_stack_v2_call.yaml` | `2.7` | `design-plan-impl-review-stack-v2-call` | Full stack example: tracked design/ADR loop, tracked plan loop, then implementation review/fix, composed from reusable `call`-based phase workflows. |
| `workflows/examples/assert_gate_demo.yaml` | `1.5` | `assert-gate-demo` | Demonstrates first-class `assert` gates and `on.failure.goto` recovery without shell glue. |
| `workflows/examples/bad_processed.yaml` | `1.1` | `bad_processed` | Negative fixture for path-safety validation of an invalid `processed_dir`. |
| `workflows/examples/claude_basic.yaml` | `1.1` | `claude_basic_example` | Smallest Claude provider example using argv prompt delivery. |
| `workflows/examples/claude_with_model.yaml` | `1.1` | `claude_model_example` | Claude provider example with default model selection and per-step override. |
| `workflows/examples/cli_test.yaml` | `1.1` | `cli_test` | Minimal CLI-oriented workflow that creates a file and captures directory listing output. |
| `workflows/examples/conditional_demo.yaml` | `1.1` | `Conditional Execution Demo` | Demonstrates `when.equals`, `when.exists`, and `when.not_exists`. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml` | `1.4` | `dsl-follow-on-plan-impl-review-loop` | Waits for the active DSL ADR review loop to finish, drafts an implementation plan from the ADR, then runs bounded plan and implementation review/fix loops. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2.yaml` | `2.7` | `dsl-follow-on-plan-impl-review-loop-v2` | Structured rewrite of the follow-on workflow using typed `inputs`/`outputs`, stable step `id`s, `match`, and `repeat_until`, while leaving the `1.4` version in place for comparison. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop_v2_call.yaml` | `2.7` | `dsl-follow-on-plan-impl-review-loop-v2-call` | Modular follow-on rewrite: a small parent workflow waits for upstream completion, then `call`s reusable plan and implementation phase subworkflows and exports their declared outputs directly. |
| `workflows/examples/dsl_tracked_plan_review_loop.yaml` | `1.4` | `dsl-tracked-plan-review-loop` | Plan-only example showing stable finding tracking: fresh review plus open-findings reconciliation, targeted revision, and cycle-specific JSON review artifacts. |
| `workflows/examples/dsl_review_first_fix_loop.yaml` | `1.4` | `dsl-review-first-fix-loop` | Review-first Codex loop: review the DSL ADR, fix against consumed review feedback, repeat until no `## High` section remains. |
| `workflows/examples/dsl_review_first_fix_loop_provider_session.yaml` | `2.10` | `dsl-review-first-fix-loop-provider-session` | Provider-session migration example: fresh review-session creation, runtime-owned session-handle publication, review gating, and resume-based fix steps without hard-coded shell `codex exec resume ...` glue. |
| `workflows/examples/env_literal.yaml` | `1.1` | _(unnamed)_ | Demonstrates literal `env` semantics, including loop variables that are not substituted inside `env`. |
| `workflows/examples/finally_demo.yaml` | `2.3` | `finally-demo` | Demonstrates top-level `finally`, resume-safe cleanup bookkeeping, and workflow outputs deferred until cleanup succeeds. |
| `workflows/examples/match_demo.yaml` | `2.6` | `match-demo` | Demonstrates top-level structured `match`, exhaustive enum case coverage, and case outputs materialized onto the statement node. |
| `workflows/examples/repeat_until_demo.yaml` | `2.7` | `repeat-until-demo` | Demonstrates post-test `repeat_until` with loop-frame outputs, nested `call` + `match` body composition, and resume-safe iteration/condition bookkeeping. |
| `workflows/examples/score_gate_demo.yaml` | `2.8` | `score-gate-demo` | Demonstrates the `score` predicate helper for benchmark thresholds plus score-band routing through top-level structured control. |
| `workflows/examples/for_each_demo.yaml` | `1.1` | _(unnamed)_ | Demonstrates `for_each` with `items_from`, aliases, and JSON dot-path array selection. |
| `workflows/examples/generic_task_plan_execute_review_loop.yaml` | `1.4` | `generic-task-plan-execute-review-loop` | Full task workflow with plan, execution, checks, review, fix, and bounded cycles. |
| `workflows/examples/injection_demo.yaml` | `1.1.1` | _(unnamed)_ | Demonstrates dependency injection modes and placement behavior for provider prompts. |
| `workflows/examples/observability_runtime_config_demo.yaml` | `1.3` | `observability_runtime_config_demo` | Shows runtime observability flags without adding observability syntax to the DSL. |
| `workflows/examples/output_capture_demo.yaml` | `1.1` | `output_capture_demo` | Demonstrates `text`, `lines`, and `json` capture modes plus tee behavior. |
| `workflows/examples/prompt_audit_demo.yaml` | `1.1.1` | _(unnamed)_ | Demonstrates prompt audit files emitted by `--debug` for argv and stdin providers. |
| `workflows/examples/ptychopinn_backlog_plan_slice_impl_review_loop.yaml` | `1.2` | `backlog-plan-impl-review-loop-v2` | Downstream reference workflow for a non-trivial backlog/implementation/review loop. |
| `workflows/examples/retry_demo.yaml` | `1.1` | `Retry Demo Workflow` | Demonstrates retry defaults, explicit retry policy, and timeout handling. |
| `workflows/examples/scalar_bookkeeping_demo.yaml` | `1.7` | `scalar-bookkeeping-demo` | Demonstrates `set_scalar`/`increment_scalar` producing local step artifacts and publishing scalar lineage without shell glue. |
| `workflows/examples/structured_if_else_demo.yaml` | `2.2` | `structured-if-else-demo` | Demonstrates top-level structured `if/else`, lowered branch-node identities, and branch outputs materialized onto the statement node. |
| `workflows/examples/test_fix_loop_v0.yaml` | `1.1.1` | `test-fix-loop-v0` | Minimal test/fix loop with a shell gate and bounded retry count. |
| `workflows/examples/test_validation.yml` | `1.1` | `validation test` | Loader-validation fixture showing valid and intentionally commented invalid forms. |
| `workflows/examples/typed_predicate_routing.yaml` | `1.6` | `typed-predicate-routing` | Demonstrates structured `ref:` predicates against step artifacts and normalized recovered-failure outcomes. |
| `workflows/examples/unit_of_work_plus_test_fix_v0.yaml` | `1.1.1` | `unit-of-work-plus-test-fix-v0` | Unit-of-work execution followed by a bounded post-work test/fix loop. |
| `workflows/examples/workflow_signature_demo.yaml` | `2.1` | `workflow-signature-demo` | Demonstrates typed workflow `inputs`/`outputs`, `${inputs.*}` substitution, `ref: inputs.*` gating, and validated workflow output export. |
| `workflows/examples/wait_for_example.yaml` | `1.1` | `wait-for-example` | Minimal `wait_for` example for task-file arrival polling. |

## Reusable Library Workflows

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/library/follow_on_plan_phase.yaml` | `2.7` | `follow-on-plan-phase` | Reusable plan-phase subworkflow for the modular follow-on example: draft plan, run structured plan review/revise loop, export the final plan contract. |
| `workflows/library/follow_on_implementation_phase.yaml` | `2.7` | `follow-on-implementation-phase` | Reusable implementation-phase subworkflow for the modular follow-on example: execute plan work, run structured implementation review/fix loop, export final implementation outputs. |
| `workflows/library/tracked_design_phase.yaml` | `2.7` | `tracked-design-phase` | Reusable tracked design/ADR phase: draft design, run tracked hard-nosed review/revise loop, allow explicit `BLOCK`, and export the approved design contract. |
| `workflows/library/tracked_plan_phase.yaml` | `2.7` | `tracked-plan-phase` | Reusable tracked plan phase: draft plan from an approved design, reconcile carried findings across iterations, and export the approved plan contract. |
| `workflows/library/design_plan_impl_implementation_phase.yaml` | `2.7` | `design-plan-impl-implementation-phase` | Reusable implementation phase for the full stack example: implement against design + plan, then review/fix until the implementation is approved. |
| `workflows/library/review_fix_loop.yaml` | `2.5` | `review-fix-loop` | Minimal reusable call demo library used by `call_subworkflow_demo.yaml`. |

## Related Docs

- `docs/workflow_drafting_guide.md`: authoring guidance for robust workflows
- `workflows/examples/README_v0_artifact_contract.md`: runbook for the artifact-contract prototype examples
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
