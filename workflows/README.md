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
- `workflows/examples/prompts/`: prompt files used only by example workflows stored under `workflows/examples/`
- `prompts/workflows/`: shared prompt trees used by larger example workflows

## Workflow Catalog

| Path | DSL | Workflow Name | Purpose |
| --- | --- | --- | --- |
| `workflows/examples/backlog_plan_execute_v0.yaml` | `1.1.1` | `backlog-plan-execute-v0` | Minimal backlog -> draft plan -> execute flow with deterministic file outputs and optional review loop. |
| `workflows/examples/backlog_plan_execute_v1_2_dataflow.yaml` | `1.2` | `backlog-plan-execute-v1-2-dataflow` | Execute/review/fix loop showing publish/consume artifact lineage and freshness semantics. |
| `workflows/examples/backlog_plan_execute_v1_3_json_bundles.yaml` | `1.3` | `backlog-plan-execute-v1-3-json-bundles` | Execute/review/fix loop using `output_bundle` and `consume_bundle` for strict JSON-gated routing. |
| `workflows/examples/cycle_guard_demo.yaml` | `1.8` | `cycle-guard-demo` | Demonstrates `max_visits`/`max_transitions` counters, a typed `assert.compare` loop gate, and recovery from a guard trip without shell counters. |
| `workflows/examples/assert_gate_demo.yaml` | `1.5` | `assert-gate-demo` | Demonstrates first-class `assert` gates and `on.failure.goto` recovery without shell glue. |
| `workflows/examples/bad_processed.yaml` | `1.1` | `bad_processed` | Negative fixture for path-safety validation of an invalid `processed_dir`. |
| `workflows/examples/claude_basic.yaml` | `1.1` | `claude_basic_example` | Smallest Claude provider example using argv prompt delivery. |
| `workflows/examples/claude_with_model.yaml` | `1.1` | `claude_model_example` | Claude provider example with default model selection and per-step override. |
| `workflows/examples/cli_test.yaml` | `1.1` | `cli_test` | Minimal CLI-oriented workflow that creates a file and captures directory listing output. |
| `workflows/examples/conditional_demo.yaml` | `1.1` | `Conditional Execution Demo` | Demonstrates `when.equals`, `when.exists`, and `when.not_exists`. |
| `workflows/examples/dsl_follow_on_plan_impl_review_loop.yaml` | `1.4` | `dsl-follow-on-plan-impl-review-loop` | Waits for the active DSL ADR review loop to finish, drafts an implementation plan from the ADR, then runs bounded plan and implementation review/fix loops. |
| `workflows/examples/dsl_tracked_plan_review_loop.yaml` | `1.4` | `dsl-tracked-plan-review-loop` | Plan-only example showing stable finding tracking: fresh review plus open-findings reconciliation, targeted revision, and cycle-specific JSON review artifacts. |
| `workflows/examples/dsl_review_first_fix_loop.yaml` | `1.4` | `dsl-review-first-fix-loop` | Review-first Codex loop: review the DSL ADR, fix against consumed review feedback, repeat until no `## High` section remains. |
| `workflows/examples/env_literal.yaml` | `1.1` | _(unnamed)_ | Demonstrates literal `env` semantics, including loop variables that are not substituted inside `env`. |
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

## Related Docs

- `docs/workflow_drafting_guide.md`: authoring guidance for robust workflows
- `workflows/examples/README_v0_artifact_contract.md`: runbook for the artifact-contract prototype examples
- `docs/runtime_execution_lifecycle.md`: runtime sequencing and state transitions
