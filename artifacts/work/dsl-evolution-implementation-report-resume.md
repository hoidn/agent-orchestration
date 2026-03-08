## Completed In This Pass

- Completed the next required approved tranche from the review: Task 12 `match`.
  - added `version: "2.6"` gating in the loader
  - added top-level structured `match` validation over typed enum refs only
  - required exhaustive case coverage across the enum's allowed values
  - enforced case-id stability and rejected `goto` / `_end` inside case blocks
- Lowered structured `match` onto the existing structured-control execution model.
  - lowered case markers and join nodes now use stable `step_id` ancestry derived from the authored statement and case ids
  - selected-case outputs materialize on the statement node just like `if/else`
  - non-selected cases persist explicitly as `skipped`
- Added the shipped example and author/operator docs for the new surface.
  - `workflows/examples/match_demo.yaml`
  - workflow catalog, drafting guide, DSL/state/observability/versioning/acceptance docs updated for `v2.6`

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

## Remaining Required Plan Tasks

- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest tests/test_loader_validation.py tests/test_structured_control_flow.py -k match -v`
  - `6 passed, 89 deselected`
- `pytest tests/test_workflow_examples_v0.py -k match_demo -v`
  - `1 passed, 17 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/match_demo.yaml --dry-run`
  - workflow validation succeeded
- `pytest tests/test_structured_control_flow.py -k 'if_else or match' -v`
  - `7 passed, 5 deselected`

## Residual Risks

- The reusable-`call` verification gap called out in the review remains open. This pass prioritized the higher-severity unfinished required tranche (`match`) and did not add the missing direct tests for caller-visible producer identity, preserved internal provenance, callee-private defaults isolation, or call-scoped freshness bookkeeping.
- `match` report/status kinds were updated in the runtime surface, but this pass did not add a dedicated `tests/test_observability_report.py` assertion for `structured_match_case` / `structured_match_join`.
- Later approved plan work remains open and unstarted in this pass: `repeat_until`, score-aware gates, linting/normalization, and the final compatibility sweep.
