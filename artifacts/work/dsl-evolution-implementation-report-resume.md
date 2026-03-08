## Completed In This Pass

- Reconciled the stale Task 16 loader coverage with the approved repeated-call write-root contract. `test_repeat_until_body_accepts_nested_call_and_match` now binds the reusable-call `write_root` through a loop-local `PrepareCallInputs` step instead of using an invariant literal path inside `repeat_until`.
- Closed the remaining final merge gate by rerunning the Task 16 compatibility suite and required smoke matrix. The full targeted pytest sweep is green, the legacy and syntax-heavy dry-runs validate, and the stateful example runs reached their expected terminal states.

## Completed Plan Tasks

- Task 16: final compatibility and smoke sweep
  - aligned stale loader validation coverage with the approved Task 10/11 repeated-call write-root rule
  - reran the required targeted pytest gate from Task 16
  - reran the required legacy compatibility dry-runs
  - reran the required new-DSL dry-run and stateful smoke examples across Tasks 2, 3, 4, 5, 7, 8, 9, 11, 12, 13, and 14

## Remaining Required Plan Tasks

- None. The approved plan's final compatibility gate is now green.

## Verification

- `PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_loader_validation.py::TestLoaderValidation::test_repeat_until_body_accepts_nested_call_and_match -v`
  - `1 passed in 0.09s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_loader_validation.py tests/test_subworkflow_calls.py tests/test_structured_control_flow.py -k 'repeat_until and call' -v`
  - `4 passed, 116 deselected in 0.18s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration pytest tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_typed_predicates.py tests/test_control_flow_foundations.py tests/test_retry_behavior.py tests/test_state_manager.py tests/test_resume_command.py tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_observability_report.py tests/test_dsl_linting.py tests/test_scalar_bookkeeping.py tests/test_score_gates.py tests/test_cli_safety.py tests/test_workflow_examples_v0.py -v`
  - `436 passed in 9.65s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful` (with expected lint warnings on the legacy raw-goto shell gates)
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/structured_if_else_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/match_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/score_gate_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --state-dir /tmp/dsl-evolution-scalar-bookkeeping-demo`
  - `/tmp/dsl-evolution-scalar-bookkeeping-demo/20260308T091441Z-ib7meq/state.json` recorded `status: completed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --state-dir /tmp/dsl-evolution-cycle-guard-demo`
  - exit `1`; `/tmp/dsl-evolution-cycle-guard-demo/20260308T091441Z-19bgzs/state.json` recorded `status: failed` and `steps.GuardLoop.error.type: cycle_guard_exceeded` as expected for the guard-trip demo
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --state-dir /tmp/dsl-evolution-workflow-signature-demo`
  - `/tmp/dsl-evolution-workflow-signature-demo/20260308T091441Z-ww97s3/state.json` recorded `status: completed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --state-dir /tmp/dsl-evolution-finally-demo`
  - `/tmp/dsl-evolution-finally-demo/20260308T091441Z-iwkdyf/state.json` recorded `status: completed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --state-dir /tmp/dsl-evolution-call-subworkflow-demo`
  - `/tmp/dsl-evolution-call-subworkflow-demo/20260308T091441Z-wgvve1/state.json` recorded `status: completed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-demo`
  - `/tmp/dsl-evolution-repeat-until-demo/20260308T091441Z-mm5jm0/state.json` recorded `status: completed`

## Residual Risks

- `cycle_guard_demo.yaml` is an intentional fail-closed example, so the final smoke matrix still includes one expected nonzero command. Approval should judge it by the recorded `cycle_guard_exceeded` terminal state rather than by zero exit alone.
- The repo worktree remains dirty with unrelated generated/runtime artifacts (`__pycache__`, `.orchestrate/`, `artifacts/`, `logs/`, `state/`, and similar paths). This pass left unrelated files untouched and will stage only the scoped test/report updates.
