## Completed In This Pass

- Completed the Task 11 reusable-call runtime tranche instead of leaving `call` validation-only:
  - `call` steps now execute imported workflows inline and persist nested call-frame state under `state.call_frames`
  - outer call steps export only declared callee `outputs` back to `steps.<CallStep>.artifacts`
  - resumed runs reuse the unfinished `call_frame_id` and restart from the first unfinished nested callee step instead of replaying completed nested work
  - top-level state moved to the reserved reusable-call boundary with `schema_version: "2.1"`
- Enforced the accepted write-root contract in the loader:
  - imported reusable workflows now reject hard-coded DSL-managed write roots
  - call sites now reject missing or colliding managed write-root bindings
  - import paths resolve relative to the authored workflow while remaining inside WORKSPACE
- Closed the observability gaps called out in review:
  - status snapshots now classify `call` steps as kind `call`
  - outer call-step snapshot output now includes persisted call metadata from `debug.call`
- Added the missing shipped artifacts for the tranche:
  - `workflows/library/review_fix_loop.yaml`
  - `workflows/examples/call_subworkflow_demo.yaml`
- Updated the normative/operator docs to match the shipped runtime:
  - call-frame state schema and v2.5 versioning
  - call-step observability/reporting
  - runtime lifecycle and authoring guidance for inline reusable calls
- Fixed the workspace-path bug exposed by the new example verification:
  - `output_file` capture now resolves against WORKSPACE and creates parent directories before capture writes

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

## Remaining Required Plan Tasks

- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_subworkflow_calls.py tests/test_state_manager.py tests/test_resume_command.py tests/test_workflow_examples_v0.py tests/test_observability_report.py -q`
  - `71 tests collected`
- `pytest tests/test_subworkflow_calls.py -v`
  - `9 passed`
- `pytest tests/test_observability_report.py -k call_steps -v`
  - `1 passed`
- `pytest tests/test_state_manager.py -k call_frames -v`
  - `1 passed`
- `pytest tests/test_resume_command.py -k call_subworkflow_smoke -v`
  - `1 passed`
- `pytest tests/test_workflow_examples_v0.py -k call_subworkflow -v`
  - `1 passed`
- `pytest tests/test_subworkflow_calls.py tests/test_loader_validation.py tests/test_state_manager.py tests/test_resume_command.py tests/test_observability_report.py tests/test_workflow_examples_v0.py -k 'call or call_frame or resume' -v`
  - `33 passed, 118 deselected`
- `pytest tests/test_dependency_resolution.py tests/test_dependency_injection.py tests/test_prompt_contract_injection.py tests/test_provider_execution.py tests/test_provider_integration.py tests/test_secrets.py -k 'asset or import or call or path or context' -v`
  - `5 passed, 73 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run`
  - workflow validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --state-dir /tmp/dsl-evolution-call-subworkflow-demo`
  - created run `20260308T014810Z-5yz2u2`
  - resulting `.orchestrate/runs/20260308T014810Z-5yz2u2/state.json` recorded `status: completed`, `steps.RunReviewLoop.status: completed`, `steps.RunReviewLoop.artifacts: {"approved": true}`, and one persisted call frame `root.run_review_loop::visit::1`

## Residual Risks

- The first shipped `call` tranche is still intentionally non-isolating. Undeclared child-process filesystem effects remain accepted operational risk; only DSL-managed write roots are enforced by the loader/runtime.
- Call-frame diagnostics are now persisted in `state.call_frames` and surfaced on the outer step snapshot, but there is still no dedicated nested call-tree renderer in markdown reports.
- Later approved plan work remains open and unstarted in this pass: `match`, `repeat_until`, score-aware gates, linting/normalization, and the final compatibility sweep.
