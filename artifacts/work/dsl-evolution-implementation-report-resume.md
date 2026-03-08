# DSL Evolution Implementation Report

## Completed In This Pass

- Fixed the Task 8 structured-control review defects:
  - loader validation now rejects duplicate lowered branch tokens for `then` / `else`, preventing durable `step_id` collisions
  - nested `for_each` bodies inside structured branches now resolve `parent.steps.*` against the enclosing lexical branch scope instead of the root scope
- Completed Task 9 from the approved execution plan:
  - added `version: "2.3"` loader support for top-level `finally`
  - validated `finally` block ids, rejected `goto` / `_end` routing inside cleanup steps, and assigned stable cleanup `step_id` ancestry under `root.finally.<block>`
  - appended finalization steps as durable top-level runtime/report nodes under `finally.<StepName>`
  - persisted finalization progress in `state.json` (`status`, `body_status`, `current_index`, `completed_indices`, `workflow_outputs_status`, optional failure details)
  - made resume continue from the first unfinished cleanup step instead of replaying completed cleanup
  - deferred workflow output export until finalization succeeded and suppressed exports on finalization failure
  - surfaced finalization bookkeeping in status snapshots and added `workflows/examples/finally_demo.yaml`
  - updated the relevant specs, lifecycle guide, acceptance map, and workflow catalog

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

## Remaining Required Plan Tasks

- Task 10: Lock the accepted-risk reusable-call contract before execution work
- Task 11: Land imports and `call` on top of typed boundaries and qualified identities
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_structured_control_flow.py tests/test_resume_command.py tests/test_observability_report.py tests/test_workflow_examples_v0.py -q`
  - `53 tests collected`
- `pytest tests/test_structured_control_flow.py tests/test_resume_command.py -k finally -v`
  - `6 passed, 23 deselected`
- `pytest tests/test_observability_report.py -k finalization -v`
  - `1 passed, 7 deselected`
- `pytest tests/test_workflow_examples_v0.py -k finally -v`
  - `1 passed, 15 deselected`
- `pytest tests/test_structured_control_flow.py tests/test_resume_command.py tests/test_observability_report.py tests/test_workflow_examples_v0.py -k 'duplicate_branch_ids or nested_for_each_parent_scope or finally' -v`
  - `9 passed, 44 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/for_each_demo.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/generic_task_plan_execute_review_loop.yaml --dry-run`
  - `[DRY RUN] Workflow validation successful`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/finally_demo.yaml --state-dir /tmp/dsl-evolution-finally-demo`
  - created run `20260308T003654Z-wzxvr2`
  - persisted state at `.orchestrate/runs/20260308T003654Z-wzxvr2/state.json` with:
    - `status: completed`
    - `workflow_outputs: {"final_decision": "APPROVE"}`
    - `finalization.block_id: cleanup`
    - `finalization.status: completed`
    - `finalization.completed_indices: [0, 1]`
    - `finalization.workflow_outputs_status: completed`

## Residual Risks

- Task 9 intentionally stops at top-level workflow finalization; block-scoped teardown/defer semantics remain deferred.
- Finalization first tranche is intentionally conservative: cleanup steps reject `goto` / `_end`, and nested structured statements inside `finally` remain out of scope until a later tranche defines lowering/identity behavior for them.
- The broader DSL evolution roadmap remains incomplete from Task 10 onward; reusable-call/import semantics, `match`, `repeat_until`, score-aware gates, linting, and the final compatibility sweep are still required.
