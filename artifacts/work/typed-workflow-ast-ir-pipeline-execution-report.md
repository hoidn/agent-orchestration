# Completed In This Pass

- Removed the remaining `raw` payload storage from `SurfaceWorkflow`, `SurfaceStep`, structured block AST nodes, and `ExecutableNodeBase`, so authored/lowered dict payloads no longer escape the typed AST/IR models.
- Removed the `_compatibility_step_definition()` raw fallback and rebuilt test-side compatibility materialization from typed AST/IR data instead of stored raw payloads.
- Updated the affected runtime and lint regressions to corrupt cached compatibility payloads instead of mutating nonexistent raw state, preserving coverage for typed authority over execution/reporting behavior.

# Completed Plan Tasks

- Tranche 5: removed the remaining raw AST/IR payload escape hatches in `orchestrator/workflow/surface_ast.py`, `orchestrator/workflow/elaboration.py`, `orchestrator/workflow/executable_ir.py`, and `orchestrator/workflow/lowering.py`.
- Tranche 5: removed the last raw-backed compatibility fallback in lowering and rewrote compatibility/test helpers to materialize from typed surface/IR/projection data.
- Tranche 5: reran the approved structured/call/finalization/report verification boundary and the required `design_plan_impl_review_stack_v2_call.yaml --dry-run` smoke check.

# Remaining Required Plan Tasks

- Remove the broader IR-to-dict execution/materialization adapter so executor, loop, and finalization paths consume only IR/projection data instead of rebuilding mutable step payloads.
- Finish the remaining Tranche 5 steady-state cleanup and maintainer-doc updates so the runtime boundary and docs match the typed pipeline architecture.

# Verification

- `pytest --collect-only -q tests/test_loader_validation.py tests/test_workflow_ir_lowering.py`
  - `106 tests collected`
- `pytest -q tests/test_loader_validation.py tests/test_workflow_ir_lowering.py -k 'surface_ast_exposes_no_raw_payloads or expose_no_legacy_raw_payloads' -v`
  - `2 passed, 104 deselected`
- `pytest -q tests/test_loader_validation.py tests/test_workflow_ir_lowering.py tests/test_workflow_surface_ast.py tests/test_workflow_lowering_invariants.py tests/test_workflow_state_projection.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_workflow_executor_characterization.py tests/test_workflow_output_contract_integration.py tests/test_dsl_linting.py tests/test_typed_predicates.py tests/test_observability_report.py tests/test_cli_safety.py tests/test_resume_command.py tests/test_workflow_examples_v0.py tests/test_provider_integration.py tests/test_secrets.py -v`
  - `376 passed`
- `pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_workflow_examples_v0.py tests/test_observability_report.py tests/test_cli_report_command.py -k 'structured or repeat_until or finalization or call or report or design_plan_impl_review_stack_v2_call' -v`
  - `87 passed, 138 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

# Residual Risks

- Executor, loop, and finalization execution still rebuild mutable compatibility step payloads from IR nodes, so the Tranche 5 “IR/projection only” runtime boundary is not finished yet.
- Maintainer docs still need the final parse/elaborate/lower/execute and projection-backed resume/report updates before the tranche can be declared fully complete.
