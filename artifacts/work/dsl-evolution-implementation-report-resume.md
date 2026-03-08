## Completed In This Pass

- Fixed the documented `v2.9` contract break.
  - extended `WorkflowLoader` version support/order through `2.9`
  - added a loader regression test proving a minimal `version: "2.9"` workflow now validates successfully
- Closed the remaining reusable-`call` verification gap from review.
  - added direct tests for callee-private context default isolation
  - added direct tests for call-frame-local `since_last_consume` bookkeeping
  - added direct tests for callee finalization export success/suppression behavior
- Fixed reusable-call managed-path substitution at runtime.
  - `consume_bundle.path` now resolves typed `inputs.*` relpath bindings inside call frames
  - aligned output-contract path handling so `expected_outputs[*].path` and `output_bundle.path` also resolve runtime path templates before validation
- During the Task 16 sweep, found and fixed a separate CLI contract bug.
  - `orchestrate run --state-dir` now threads the override into `StateManager`
  - `StateManager` now supports a custom runs root while still hashing workflows from the real workspace
  - the default archive destination logic now respects the overridden runs root
  - added CLI/state-manager regression tests for the override behavior
- Completed Task 16 by rerunning the full compatibility and smoke sweep after the final fixes landed.

## Completed Plan Tasks

- Task 1: Lock the normative rollout and version/state boundaries
- Task 2: Land D1 with first-class `assert` / gate steps
- Task 3: Land D2 typed predicates, structured `ref:` operands, and normalized outcomes
- Task 4: Land D2a lightweight scalar bookkeeping as a dedicated runtime primitive
- Task 5: Land D3 cycle guards with resume-safe persisted counters
- Task 6: Build the D4-D5 foundations: scoped refs and stable internal step IDs
- Task 7: Land D6 typed workflow signatures and top-level input/output binding
- Task 8: Add a structured statement layer with `if/else`
- Task 9: Add structured finalization (`finally`) as a separate tranche
- Task 10: Lock the accepted-risk reusable-call contract before execution work
- Task 11: Land imports and `call` on top of typed boundaries and qualified identities
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Remaining Required Plan Tasks

- None.

## Verification

- `pytest --collect-only tests/test_loader_validation.py -q`
  - collected `86` tests
- `pytest --collect-only tests/test_subworkflow_calls.py -q`
  - collected `14` tests
- `pytest --collect-only tests/test_cli_safety.py -q`
  - collected `22` tests
- `pytest --collect-only tests/test_state_manager.py -q`
  - collected `17` tests
- `pytest tests/test_loader_validation.py -k version_2_9_is_supported -v`
  - `1 passed`
- `pytest tests/test_subworkflow_calls.py -k "context_defaults_isolated or since_last_consume or finalization" -v`
  - `4 passed`
- `pytest tests/test_cli_safety.py -k state_dir_override -v`
  - `1 passed`
- `pytest tests/test_state_manager.py -k custom_state_dir -v`
  - `1 passed`
- `pytest tests/test_loader_validation.py tests/test_subworkflow_calls.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py tests/test_provider_execution.py -v`
  - `144 passed`
- `pytest tests/test_cli_safety.py tests/test_state_manager.py -k "state_dir or custom_state_dir or run_workflow" -v`
  - `8 passed`
- `pytest tests/test_loader_validation.py tests/test_conditional_execution.py tests/test_runtime_step_lifecycle.py tests/test_typed_predicates.py tests/test_control_flow_foundations.py tests/test_retry_behavior.py tests/test_state_manager.py tests/test_resume_command.py tests/test_artifact_dataflow_integration.py tests/test_for_each_execution.py tests/test_at65_loop_scoping.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_observability_report.py tests/test_dsl_linting.py tests/test_scalar_bookkeeping.py tests/test_score_gates.py tests/test_cli_safety.py tests/test_workflow_examples_v0.py -v`
  - `427 passed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run`
  - validation succeeded; advisory lint warnings only
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
- Stateful Task 16 smokes under corrected custom state roots:
  - `/tmp/dsl-evolution-scalar-bookkeeping-demo/20260308T035311Z-asq404/state.json` -> `status=completed`
  - `/tmp/dsl-evolution-cycle-guard-demo/20260308T035311Z-ok4u00/state.json` -> `status=completed`
  - `/tmp/dsl-evolution-workflow-signature-demo/20260308T035311Z-7d13x5/state.json` -> `status=completed`
  - `/tmp/dsl-evolution-finally-demo/20260308T035311Z-v03xnz/state.json` -> `status=completed`
  - `/tmp/dsl-evolution-call-subworkflow-demo/20260308T035311Z-s3mo9m/state.json` -> `status=completed`, `workflow_outputs={"approved": true}`
  - `/tmp/dsl-evolution-repeat-until-demo/20260308T035311Z-11k3x9/state.json` -> `status=completed`
- Docs audit:
  - `docs/workflow_drafting_guide.md` contains shipped author-facing guidance for `assert`, typed predicates, `if/else`, `match`, `repeat_until`, score gates, and reusable `call`
  - `docs/runtime_execution_lifecycle.md` contains runtime/operator guidance for structured lowering, finalization, call frames, loop resume, and workflow output export timing

## Residual Risks

- `orchestrate run --state-dir` now works, but `orchestrate resume` still has no matching runs-root override; resuming runs created under non-default roots remains unverified CLI territory outside this plan pass.
- Sandbox policy blocked `tmux` and `/tmp` cleanup, so long-running verification used direct polling and the stateful smoke evidence relied on fresh timestamped run directories under the requested roots.
