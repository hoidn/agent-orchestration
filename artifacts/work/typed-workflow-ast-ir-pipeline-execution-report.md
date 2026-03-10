# Completed In This Pass

- Bundle-backed top-level execution now prefers thawed IR raw payloads for typed leaf/helper nodes, so typed command/goto execution no longer drifts when the legacy compatibility adapter is mutated after load.
- Typed goto resolution now stays on IR/projection data and no longer scans compatibility step names for bundle-backed execution.
- Top-level typed routing now honors non-counting `call_return` transfer metadata, fixing the concrete IR/runtime contract mismatch without changing current repeat-until transition compatibility.
- Added regression coverage for typed payload drift and non-counting typed call-return routing.

# Completed Plan Tasks

- Tranche 4 runtime slice: reduced top-level executor dependence on the legacy lowered-dict adapter by sourcing typed leaf/helper step payloads from IR raw data where the runtime can consume authored shape directly.
- Tranche 4 runtime slice: tightened typed goto routing so bundle-backed execution resolves targets from IR/projection metadata instead of compatibility step-name scans.
- Tranche 4 runtime slice: aligned typed top-level transition accounting with IR transfer metadata for non-counting call returns.

# Remaining Required Plan Tasks

- Tranche 4: finish migrating loop, finalization, and call helpers that still require legacy compatibility payloads or name/index-based bookkeeping.
- Tranche 4: move the remaining reporting/linting/runtime consumers off legacy helper-key and magic-metadata fallbacks.
- Tranche 5: remove the legacy lowering/metadata path entirely and update maintainer docs to the typed `parse -> elaborate -> lower -> execute` model.

# Verification

- `pytest --collect-only -q tests/test_workflow_executor_characterization.py`
  - `13 tests collected`
- `pytest -q tests/test_workflow_executor_characterization.py -k "projection or goto or transition or raw_step_payloads or typed_call_return_transition"`
  - `5 passed, 8 deselected`
- `pytest -q tests/test_workflow_state_compatibility.py -k "transition_count or call_frame or finalization or repeat_until"`
  - `3 passed, 1 deselected`
- `pytest -q tests/test_resume_command.py -k "transition_count or current_step or call or finalization"`
  - `7 passed, 23 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

# Residual Risks

- `repeat_until` and `for_each` top-level frames still execute through the compatibility adapter because their runtime helpers have not finished the Tranche 4 migration.
- Loop-exit transition counting still follows existing compatibility behavior; only typed call-return routing is projection/IR-driven in this pass.
- Reporting, linting, and bundle helper cleanup from the approved Tranche 5 work remains outstanding.
