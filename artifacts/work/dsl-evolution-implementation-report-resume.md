## Completed In This Pass

- Closed the remaining Task 16 merge-boundary sweep required by the approved plan.
  - reran the full targeted unit/integration pytest sweep on the final branch state
  - reran the legacy compatibility dry-runs for `generic_task_plan_execute_review_loop.yaml` and `for_each_demo.yaml`
  - reran the new-DSL smoke set with dry-runs for the syntax-heavy tranches and isolated real runs for the stateful tranches
- Repaired the two normative spec drifts called out by review.
  - `specs/versioning.md` now matches the shipped v2.7 `repeat_until` contract: loop bodies still reject `goto`, nested `for_each`, and nested `repeat_until`, while direct nested `call`, `match`, and `if/else` bodies remain allowed and lowered with loop-local ref scoping
  - `specs/index.md` now advertises the shipped master-spec surface through v2.9, including `match`, `repeat_until`, score-aware gates, and advisory linting
- Completed the Task 16 doc audit.
  - confirmed `docs/workflow_drafting_guide.md`, `docs/runtime_execution_lifecycle.md`, and `workflows/README.md` were already aligned with the shipped structured-loop and `call` surfaces; only the two normative specs above needed repair

## Completed Plan Tasks

- Task 13: Add post-test `repeat_until` as its own loop tranche
  - remains complete from the prior pass; this pass revalidated its loader/runtime/resume/example coverage on the final branch state
- Task 16: Run the final compatibility and smoke sweep before merge
  - reran the plan-mandated targeted pytest sweep
  - reran the legacy compatibility dry-runs
  - reran the tranche-by-tranche dry-run and isolated real smoke set
  - completed the required authoring/runtime doc audit and repaired the remaining normative spec drift before merge

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_typed_predicates.py tests/test_control_flow_foundations.py tests/test_retry_behavior.py tests/test_state_manager.py tests/test_resume_command.py tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_observability_report.py tests/test_dsl_linting.py tests/test_scalar_bookkeeping.py tests/test_score_gates.py tests/test_cli_safety.py tests/test_workflow_examples_v0.py -v`
  - `432 passed in 9.41s`
- `pytest tests/test_dsl_linting.py tests/test_cli_report_command.py -v`
  - `12 passed in 0.07s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run`
  - validation succeeded; advisory lint warnings were emitted for legacy shell-gate/raw-`goto` patterns as expected
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/assert_gate_demo.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/structured_if_else_demo.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/match_demo.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/score_gate_demo.yaml --dry-run`
  - validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/scalar_bookkeeping_demo.yaml --state-dir /tmp/dsl-evolution-scalar-bookkeeping-demo`
  - run `20260308T045113Z-wbdafy` completed; persisted `artifact_versions` recorded `failed_count` with `2` versions
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/cycle_guard_demo.yaml --state-dir /tmp/dsl-evolution-cycle-guard-demo`
  - run `20260308T045113Z-njkx55` completed; persisted `transition_count` was `7` and `step_visits` was `{"InitializeBudget": 1, "RunCheck": 3, "GuardLoop": 3, "RecordGuardTrip": 1}`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --state-dir /tmp/dsl-evolution-workflow-signature-demo`
  - run `20260308T045113Z-7njej5` completed; persisted `bound_inputs` was `{"task_path": "workflows/examples/inputs/demo-task.md", "max_cycles": 3}` and `workflow_outputs` was `{"report_path": "artifacts/reports/demo-task-report.md", "cycles_used": 3}`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --state-dir /tmp/dsl-evolution-finally-demo`
  - run `20260308T045113Z-v8qljj` completed; persisted `finalization.status` was `completed` and `workflow_outputs` was `{"final_decision": "APPROVE"}`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --state-dir /tmp/dsl-evolution-call-subworkflow-demo`
  - run `20260308T045113Z-m38uxo` completed; persisted `call_frames` contained `root.run_review_loop::visit::1` and `workflow_outputs` was `{"approved": true}`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-demo`
  - run `20260308T045113Z-k5485u` completed; persisted `repeat_until.ReviewLoop` recorded `completed_iterations: [0]` and `last_condition_result: true`

## Residual Risks

- The repo worktree remains dirty with pre-existing generated/runtime artifacts (`__pycache__`, `.orchestrate/`, `artifacts/`, `logs/`, `state/`, and related files). This pass left unrelated files alone and only stages the scoped spec/report changes.
- Advisory lint warnings on legacy example workflows are expected in v2.9 and do not indicate validation failure.
- No additional runtime or contract defects were found in the final sweep, but the branch still depends on the documented accepted-risk boundary for inline `call` filesystem effects.
