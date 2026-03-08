## Completed In This Pass

- Completed the next required approved tranche from the review: Task 13 `repeat_until`.
  - added `version: "2.7"` gating in the loader and top-level-only validation for structured post-test loops
  - required typed `repeat_until.condition`, non-empty declared loop outputs, bounded `max_iterations`, and rejected direct `self.steps.*` condition refs in favor of `self.outputs.*`
  - rejected `goto` / `_end`, nested structured control, nested `for_each`, and nested `call` inside the first-tranche loop body
- Implemented runtime execution and resume-safe persistence for `repeat_until`.
  - loop-frame outputs now materialize on the authored outer step while per-iteration nested results persist under indexed keys such as `ReviewLoop[1].WriteDecision`
  - repeat loop progress persists under `state.repeat_until`, including current iteration, completed iterations, and whether the current iteration's condition already evaluated
  - resume now restarts the first unfinished nested step in the current iteration, or advances directly if the prior iteration body and condition were already settled before interruption
  - loop exhaustion now fails with `repeat_until_iterations_exhausted`
- Added the shipped example, docs, and report-surface coverage for the new loop kind.
  - `workflows/examples/repeat_until_demo.yaml`
  - workflow catalog, drafting guide, DSL/state/observability/versioning/acceptance docs updated for `v2.7`
  - added `tests/test_observability_report.py` coverage for authored `repeat_until` status snapshots

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
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche

## Remaining Required Plan Tasks

- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest tests/test_observability_report.py --collect-only -q`
  - collected `10 tests`
- `pytest tests/test_observability_report.py tests/test_loader_validation.py tests/test_structured_control_flow.py tests/test_resume_command.py tests/test_workflow_examples_v0.py -k repeat_until -v`
  - `8 passed, 142 deselected`
- `pytest tests/test_structured_control_flow.py -v`
  - `14 passed`
- `pytest tests/test_resume_command.py -k 'structured_if_else_smoke or finally_smoke or repeat_until' -v`
  - `4 passed, 18 deselected`
- `pytest tests/test_workflow_examples_v0.py -k 'structured_if_else_demo or finally_demo or match_demo or repeat_until_demo' -v`
  - `4 passed, 15 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --dry-run`
  - workflow validation succeeded
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/repeat_until_demo.yaml --state-dir /tmp/dsl-evolution-repeat-until-demo-final`
  - run completed successfully; persisted `ReviewLoop.artifacts.review_decision == "APPROVE"` in the generated `state.json`

## Residual Risks

- The reusable-`call` verification gap called out in the review remains open. This pass prioritized the higher-severity unfinished required tranche (`repeat_until`) and did not add the missing direct tests for caller-visible producer identity, preserved internal provenance, callee-private defaults isolation, or call-scoped freshness bookkeeping.
- Later approved plan work remains open and unstarted in this pass: score-aware gates, linting/normalization, and the final compatibility sweep.
