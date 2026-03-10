# Completed In This Pass

- Lowered spec-authoritative `on.success|failure|always.goto` handlers into executable-IR routed transfers, including `_end` as an explicit typed terminal route.
- Switched typed top-level control-flow handling to consume IR routed transfers directly instead of resolving goto targets through projection/name lookup.
- Added regressions that lock the IR route metadata to the DSL `on.*.goto` surface and verify typed executor dispatch stays correct even when a materialized step payload's goto target text drifts.

# Completed Plan Tasks

- Tranche 4 routing slice: typed IR now encodes spec `on.*.goto` handlers as explicit node-id transfers instead of relying on unsupported raw `goto` lowering.
- Tranche 4 executor slice: bundle-backed typed runs no longer use `_resolve_goto_target()`'s projection/name-scan fallback for goto dispatch.
- Tranche 1/4 characterization slice: added focused IR/executor regressions around typed goto lowering and dispatch.

# Remaining Required Plan Tasks

- Tranche 4: finish removing the remaining top-level and nested leaf-execution adapters that still materialize legacy-shaped step dicts from `ExecutableNode.raw` before command/provider/wait/assert/scalar execution.
- Tranche 5: delete the legacy bundle/adapter plumbing and remaining magic-metadata compatibility paths once runtime callers no longer need them.
- Tranche 5: update maintainer docs for the typed `parse -> elaborate -> lower -> execute` pipeline and projection-backed runtime surfaces.

# Verification

- `pytest --collect-only -q tests/test_workflow_ir_lowering.py tests/test_workflow_executor_characterization.py`
  - `29 tests collected in 0.07s`
- `pytest tests/test_workflow_ir_lowering.py -k "on_goto_loop_call_and_finalization" -q`
  - `1 passed, 4 deselected in 0.10s`
- `pytest tests/test_workflow_executor_characterization.py -k "materialized_on_target_drifts" -q`
  - `1 passed, 23 deselected in 0.09s`
- `pytest tests/test_workflow_ir_lowering.py tests/test_workflow_executor_characterization.py tests/test_at56_at57_error_handling.py tests/test_at71_retries_goto.py -k "goto or routed_transfer or on_always or on_failure or on_success" -q`
  - `12 passed, 30 deselected in 3.20s`
- `pytest tests/test_workflow_executor_characterization.py tests/test_for_each_execution.py tests/test_artifact_dataflow_integration.py tests/test_state_manager.py tests/test_resume_command.py tests/test_observability_report.py tests/test_cli_report_command.py tests/test_subworkflow_calls.py -k "current_step or transition_count or repeat_until or finalization or call or report" -q`
  - `69 passed, 93 deselected in 0.93s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run`
  - `2026-03-10 12:29:34,481 - orchestrator.cli.commands.run - INFO - [DRY RUN] Workflow validation successful`

# Residual Risks

- Bundle-backed runtime still adapts command/provider/wait/assert/scalar execution through legacy-shaped dict payloads materialized from `ExecutableNode.raw`, so Tranche 4 is not yet at IR-only leaf execution.
- Legacy bundle compatibility surfaces and magic metadata remain in the tree for unchanged callers; Tranche 5 cleanup is still required before the migration can be declared complete.
