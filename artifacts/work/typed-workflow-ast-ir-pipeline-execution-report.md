# Completed In This Pass

- Switched bundle-backed top-level execution advancement onto typed executable node ids, using IR fallthrough and routed goto targets while still persisting compatibility `current_step.index` surfaces.
- Made resume planning projection-driven for typed workflows, so restart selection now scans projection-ordered node ids instead of drift-prone legacy adapter names.
- Moved workflow finalization bookkeeping onto projection/IR metadata for typed runs, including finalization entry routing by node id and projected `step_names` surfaces.
- Added regression coverage for projection-ordered resume selection under legacy-name drift and for projected finalization bookkeeping under legacy finalization-name drift.

# Completed Plan Tasks

- Tranche 4 runtime slice: top-level typed-bundle execution now advances through IR node ids instead of using legacy adapter list order as execution truth.
- Tranche 4 runtime slice: resume planning now uses projection-owned execution ordering and `step_id -> node_id` mapping for typed workflows.
- Tranche 4 runtime slice: finalization entry and bookkeeping now consume projection/IR metadata rather than drift-prone legacy finalization step names.

# Remaining Required Plan Tasks

- Tranche 4: migrate the remaining runtime helpers that still consult legacy lowered dict metadata or compatibility step lists as fallback dispatch inputs.
- Tranche 4: finish moving finalization/resume/reporting consumers onto IR regions/projection-only lookups so typed execution no longer depends on the legacy adapter outside the narrow leaf-step bridge.
- Tranche 5: remove the second lowering path and steady-state legacy magic metadata, then update maintainer docs to the `parse -> elaborate -> lower -> execute` model.

# Verification

- `pytest --collect-only -q tests/test_workflow_state_projection.py tests/test_workflow_executor_characterization.py`
  - `19 tests collected`
- `pytest tests/test_workflow_state_projection.py::test_resume_planner_uses_projection_ordering_when_legacy_step_names_drift tests/test_workflow_executor_characterization.py::test_executor_uses_projection_names_for_finalization_bookkeeping_when_legacy_names_drift -q`
  - `2 passed`
- `pytest tests/test_workflow_executor_characterization.py tests/test_for_each_execution.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_subworkflow_calls.py tests/test_workflow_state_projection.py -k "current_step or transition_count or repeat_until or finalization or call or report or projection" -q`
  - `72 passed, 80 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

# Residual Risks

- The executor still relies on the legacy adapter as the leaf-step payload source, so Tranche 5 adapter removal is still required.
- Some runtime/reporting paths still retain compatibility fallbacks for legacy dict metadata, which means typed IR is not yet the sole steady-state authority everywhere.
- This pass did not remove the legacy adapter renderer or imported-metadata shims, so raw dict cleanup and doc updates remain outstanding.
