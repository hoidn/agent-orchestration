# DSL Evolution Implementation Report

## Completed In This Pass

- Fixed the typed-predicate single-operator bug: malformed nodes with multiple operator keys are now rejected at load time and raise deterministic runtime errors if evaluated directly.
- Fixed observability rendering for settled `for_each` summaries so completed loop steps no longer appear as `running` in status snapshots.
- Completed Task 7 from the approved execution plan:
  - added `version: "2.1"` workflow signatures with top-level `inputs` and `outputs`
  - added CLI binding via `--input` and `--input-file`
  - exposed bound inputs through `${inputs.<name>}` and typed `ref: inputs.<name>`
  - persisted `bound_inputs` and `workflow_outputs` in `state.json`
  - exported workflow outputs through validated `outputs.<name>.from` bindings
  - surfaced workflow-boundary inputs/outputs/errors in status snapshots
  - added `workflow_signature_demo.yaml` plus checked-in example input fixtures
  - updated the relevant specs, runtime lifecycle guide, drafting guide, and workflow catalog

## Completed Plan Tasks

- Task 1: Lock the normative rollout and version/state boundaries
- Task 2: Land D1 with first-class `assert` / gate steps
- Task 3: Land D2 typed predicates, structured `ref:` operands, and normalized outcomes
- Task 4: Land D2a lightweight scalar bookkeeping as a dedicated runtime primitive
- Task 5: Land D3 cycle guards with resume-safe persisted counters
- Task 6: Build the D4-D5 foundations: scoped refs and stable internal step IDs
- Task 7: Land D6 typed workflow signatures and top-level input/output binding

## Remaining Required Plan Tasks

- Task 8: Add a structured statement layer with `if/else`
- Task 9: Add structured finalization (`finally`) as a separate tranche
- Task 10: Lock the accepted-risk reusable-call contract before execution work
- Task 11: Land imports and `call` on top of typed boundaries and qualified identities
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_observability_report.py tests/test_cli_safety.py tests/test_state_manager.py tests/test_resume_command.py tests/test_output_contract.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -q`
  - `193 tests collected`
- `pytest tests/test_typed_predicates.py::test_typed_predicate_evaluator_rejects_multi_operator_nodes tests/test_loader_validation.py::TestLoaderValidation::test_typed_assert_rejects_multiple_operator_keys tests/test_loader_validation.py::TestLoaderValidation::test_nested_typed_predicates_reject_multiple_operator_keys tests/test_observability_report.py::test_snapshot_marks_completed_for_each_summary_as_completed tests/test_cli_safety.py::TestCLISafety::test_run_workflow_passes_bound_inputs_to_state tests/test_state_manager.py::TestStateManager::test_bound_inputs_and_workflow_outputs_persist_across_reload tests/test_resume_command.py::test_resume_preserves_bound_inputs_in_loaded_state tests/test_output_contract.py::test_validate_contract_value_accepts_native_json_scalars_and_relpaths tests/test_workflow_output_contract_integration.py::test_workflow_signature_binds_inputs_and_exports_outputs tests/test_workflow_output_contract_integration.py::test_workflow_output_export_fails_when_export_contract_is_invalid tests/test_workflow_examples_v0.py::test_workflow_signature_demo_runtime -q`
  - `11 passed in 0.16s`
- `pytest tests/test_loader_validation.py tests/test_cli_safety.py tests/test_state_manager.py tests/test_resume_command.py -k "inputs or outputs or bound_inputs or schema" -v`
  - `19 passed, 111 deselected in 0.10s`
- `pytest tests/test_output_contract.py tests/test_workflow_output_contract_integration.py -k "workflow_output or signature or export" -v`
  - `11 passed, 19 deselected in 0.14s`
- `pytest tests/test_workflow_examples_v0.py -k workflow_signature -v`
  - `1 passed, 13 deselected in 0.05s`
- `pytest tests/test_typed_predicates.py tests/test_loader_validation.py tests/test_observability_report.py -q`
  - `97 passed in 0.23s`
- `pytest tests/test_output_contract.py::test_validate_contract_value_accepts_native_json_scalars_and_relpaths -v`
  - `1 passed in 0.02s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/typed_predicate_routing.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/workflow_signature_demo.yaml --input-file workflows/examples/inputs/workflow_signature_demo.json --state-dir /tmp/dsl-evolution-workflow-signature-demo`
  - created run `20260307T231920Z-dtv6do`
  - `.orchestrate/runs/20260307T231920Z-dtv6do/state.json` recorded `status: completed`
  - exported `workflow_outputs: {"report_path": "artifacts/reports/demo-task-report.md", "cycles_used": 3}`
  - persisted `bound_inputs: {"task_path": "workflows/examples/inputs/demo-task.md", "max_cycles": 3}`
  - verified generated artifact `artifacts/reports/demo-task-report.md`

## Residual Risks

- Task 7 intentionally stops before structured finalization. Workflow output withholding/suppression around `finally` remains deferred to Task 9.
- The reusable-call/import boundary is still unimplemented, so workflow signatures are only exercised for top-level runs in this pass.
- The broader DSL evolution roadmap remains incomplete from Task 8 onward; structured statements, call semantics, match/repeat constructs, score-aware gates, linting, and the final compatibility sweep are still required.
