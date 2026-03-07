# DSL Evolution Implementation Report

## Completed In This Pass

- Fixed the additive `since_last_consume` freshness regression: post-v1.4 workflows now keep step-scoped freshness through `v1.5`-`v2.1`, and qualified-identity freshness remains additive beyond `v2.0` instead of being hard-coded to one release.
- Completed Task 8 from the approved execution plan:
  - added `version: "2.2"` loader support for top-level structured `if/else`
  - validated branch blocks (`id`, `steps`, `outputs`) with branch-local typed refs and conservative `goto` / `_end` rejection inside branches
  - lowered structured statements into guarded branch markers, lowered branch-body steps, and a join node with stable ancestry-derived `step_id`s
  - materialized selected-branch outputs onto the statement node and surfaced selected-branch debug/report metadata
  - verified resume restarts from the first unfinished lowered node instead of replaying completed branch work
  - added `workflows/examples/structured_if_else_demo.yaml`
  - updated the relevant specs, runtime lifecycle guide, drafting guide, and workflow catalog

## Completed Plan Tasks

- Task 1: Lock the normative rollout and version/state boundaries
- Task 2: Land D1 with first-class `assert` / gate steps
- Task 3: Land D2 typed predicates, structured `ref:` operands, and normalized outcomes
- Task 4: Land D2a lightweight scalar bookkeeping as a dedicated runtime primitive
- Task 5: Land D3 cycle guards with resume-safe persisted counters
- Task 6: Build the D4-D5 foundations: scoped refs and stable internal step IDs
- Task 7: Land D6 typed workflow signatures and top-level input/output binding
- Task 8: Add a structured statement layer with `if/else`

## Remaining Required Plan Tasks

- Task 9: Add structured finalization (`finally`) as a separate tranche
- Task 10: Lock the accepted-risk reusable-call contract before execution work
- Task 11: Land imports and `call` on top of typed boundaries and qualified identities
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_structured_control_flow.py -q`
  - `3 tests collected`
- `pytest tests/test_artifact_dataflow_integration.py -k "scoped_to_consumer_step" -v`
  - `7 passed, 15 deselected in 0.23s`
- `pytest tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_state_manager.py -k "if_else or lowered" -v`
  - `6 passed, 92 deselected in 0.10s`
- `pytest tests/test_resume_command.py -k structured_if_else_smoke -v`
  - `1 passed, 17 deselected in 0.10s`
- `pytest tests/test_workflow_examples_v0.py -k structured_if_else -v`
  - `1 passed, 14 deselected in 0.05s`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/structured_if_else_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`

## Residual Risks

- Task 8 intentionally stops at top-level `if/else`; nested structured statements and finalization semantics remain deferred.
- Lowered structured-control nodes now appear explicitly in reports/state. Later structured tranches (`finally`, `call`, `match`, `repeat_until`) must preserve the same durable ancestry model instead of inventing sibling-order-sensitive runtime ids.
- The broader DSL evolution roadmap remains incomplete from Task 9 onward; reusable-call/import semantics, `match`, `repeat_until`, score-aware gates, linting, and the final compatibility sweep are still required.
