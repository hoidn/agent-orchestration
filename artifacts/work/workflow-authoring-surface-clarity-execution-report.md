## Completed In This Pass
- Aligned the active docs/specs with one four-surface workflow-authoring vocabulary and version-accurate consume wording.
- Moved repo-owned reusable-workflow prompt families into `workflows/library/prompts/...`, switched the affected library workflows to `asset_file`, and updated catalogs plus runtime smoke fixtures.
- Added the v2.9 advisory lint for redundant top-level workflow-boundary `kind: relpath` and rewrote active canonical workflows to prefer `type: relpath` alone.

## Completed Plan Tasks
- Tranche 1: updated `docs/index.md`, `specs/index.md`, `docs/runtime_execution_lifecycle.md`, `docs/workflow_drafting_guide.md`, `specs/dsl.md`, `specs/providers.md`, and `specs/variables.md`.
- Tranche 2: migrated the `design_plan_impl_stack_v2_call` and `dsl_follow_on_plan_impl_loop_v2_call` prompt families into `workflows/library/prompts/...`, updated the affected library workflows/tests/catalogs, and removed the old active copies from `prompts/workflows/...`.
- Tranche 3: added boundary compatibility/lint coverage, implemented the redundant-boundary advisory lint, updated `specs/versioning.md`, and cleaned the active example/library workflow boundaries.
- Tranche 4: reran the active-surface audits, targeted pytest gates, the reusable-stack dry-run smoke, and `git diff --check`.

## Remaining Required Plan Tasks
- None.

## Verification
- `pytest --collect-only tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -q` -> 126 tests collected.
- `pytest tests/test_artifact_dataflow_integration.py -k "v14_consume_relpath_is_read_only_for_pointer_file" -v` -> 1 passed.
- `pytest tests/test_prompt_contract_injection.py -k "asset_file or asset_depends_on" -v` -> 3 passed.
- `pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py -k "workflow or boundary or relpath or lint" -v` -> 38 passed.
- `pytest tests/test_workflow_examples_v0.py -k "backlog_priority_design_plan_impl_stack_v2_call_runtime or dsl_follow_on_plan_impl_review_loop_v2_call_runtime or design_plan_impl_review_stack_v2_call_runtime" -v` -> 3 passed.
- `pytest tests/test_workflow_examples_v0.py -k "workflow_signature or dsl_follow_on_plan_impl_review_loop_v2_call_runtime or design_plan_impl_review_stack_v2_call_runtime" -v` -> 3 passed.
- `pytest tests/test_loader_validation.py tests/test_dsl_linting.py tests/test_workflow_output_contract_integration.py tests/test_workflow_examples_v0.py -k "relpath or workflow_signature or backlog_priority_design_plan_impl_stack_v2_call or design_plan_impl_review_stack_v2_call or dsl_follow_on_plan_impl_review_loop_v2_call" -v` -> 15 passed.
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/design_plan_impl_review_stack_v2_call.yaml --dry-run` -> workflow validation successful.
- Active-surface `rg` audits for stale prompt-model wording, stale reusable prompt paths, and `kind: relpath` under `workflows/examples` / `workflows/library` returned no matches.
- `git diff --check` -> no formatting errors.

## Residual Risks
- Verification was targeted to the affected docs, lint surface, and reusable workflow examples; the full repo test suite was not run.
- Historical docs/plans outside the active-surface scope may still mention superseded prompt paths or older wording by design.
