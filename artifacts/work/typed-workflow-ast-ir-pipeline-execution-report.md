# Completed In This Pass

- Parsed legacy `when/assert` conditions into typed surface nodes and carried them through the IR runtime so legacy `when.equals` no longer depends on raw dict condition fallback or gets silently ignored under typed execution.
- Removed raw-workflow fallbacks from loaded-bundle root metadata helpers and from DSL lint entrypoints, while preserving the `None -> empty contracts` import-validation path the loader still uses before it raises workflow validation errors.
- Switched advisory linting for stringly `when.equals` checks to typed surface condition nodes instead of `step.raw`, and added focused regression coverage for the bundle-only and typed-condition boundaries.

# Completed Plan Tasks

- Tranche 5: removed the reviewed bundle/lint raw-authority fallbacks so maintainer-facing helpers and linting now require typed loaded bundles instead of raw workflow mappings.
- Tranche 5: removed the reviewed executor mixed-mode legacy condition/ref fallback slice by evaluating only typed condition forms in the IR runtime.
- Tranche 5: reran the approved structured/finalization/call/report verification boundary and the required `design_plan_impl_review_stack_v2_call.yaml --dry-run` smoke check.

# Remaining Required Plan Tasks

- Remove the remaining `raw` payload storage and propagation on core AST/IR/contracts in `surface_ast.py`, `executable_ir.py`, and `lowering.py` so raw dicts stop escaping elaboration/lowering internals.
- Continue trimming remaining typed-pipeline compatibility scaffolding outside this slice, including any steady-state runtime/reporting helpers that still depend on raw compatibility payloads rather than typed bundle/IR/projection data.
- Finish the broader Tranche 5 steady-state cleanup and exit criteria before declaring the typed pipeline migration complete.

# Verification

- `pytest --collect-only -q tests/test_workflow_surface_ast.py tests/test_dsl_linting.py tests/test_workflow_executor_characterization.py`
  - `54 tests collected`
- `pytest -q tests/test_workflow_surface_ast.py -k 'loaded_workflow_helpers_require_loaded_bundle or parses_legacy_when_equals_into_condition_node' -v`
  - `2 passed`
- `pytest -q tests/test_dsl_linting.py -k 'lint_requires_loaded_workflow_bundle or typed_legacy_when_condition_when_step_raw_drifts' -v`
  - `2 passed`
- `pytest -q tests/test_workflow_executor_characterization.py -k respects_legacy_when_equals_without_condition_dict_fallback -v`
  - `1 passed`
- `pytest -q tests/test_workflow_surface_ast.py tests/test_dsl_linting.py tests/test_typed_predicates.py tests/test_workflow_output_contract_integration.py -k 'surface or lint or when or workflow_input_binding_uses_typed_contract_definition_when_legacy_contract_raw_drifts or workflow_output_export_uses_bound_ir_contracts_when_legacy_refs_are_corrupted or workflow_output_export_uses_typed_contract_definition_when_legacy_contract_raw_drifts' -v`
  - `26 passed, 21 deselected`
- `pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_subworkflow_calls.py tests/test_resume_command.py tests/test_workflow_examples_v0.py tests/test_observability_report.py tests/test_cli_report_command.py -k 'structured or repeat_until or finalization or call or report or design_plan_impl_review_stack_v2_call' -v`
  - `87 passed, 137 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

# Residual Risks

- Core AST/IR nodes and contract wrappers still retain `raw` payloads for compatibility and tests, so the typed-only “raw dicts do not escape parse/elaboration internals” end state is still incomplete.
- Bundle helpers still preserve `None -> {}` behavior for import prevalidation; that keeps loader validation stable, but the remaining Tranche 5 cleanup should continue auditing similar compatibility shims so they do not become steady-state runtime authority again.
