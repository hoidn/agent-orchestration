## Completed In This Pass

- Completed the next required approved tranche from the review: Task 14 `score-aware gates`.
  - added `version: "2.8"` loader support and a `score` typed-predicate helper for numeric threshold and band checks
  - kept the feature as thin sugar over the existing predicate system so `score` works under `when`, `assert`, and structured control without adding a separate routing surface
  - validated numeric refs, required at least one bound, rejected conflicting `gt`/`gte` and `lt`/`lte` declarations, and rejected empty score-band ranges
- Added focused verification and example coverage for the new helper surface.
  - created `tests/test_score_gates.py`
  - added structured-control coverage for score-band routing
  - added `workflows/examples/score_gate_demo.yaml`
  - updated DSL/versioning/workflow-drafting/workflow-catalog docs for `v2.8`

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
- Task 14: Add score-aware gates on top of the stable predicate system

## Remaining Required Plan Tasks

- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_score_gates.py -q`
  - collected `6 tests`
- `pytest tests/test_score_gates.py tests/test_structured_control_flow.py -v`
  - `21 passed`
- `pytest tests/test_workflow_examples_v0.py -k score_gate -v`
  - `1 passed, 19 deselected`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/score_gate_demo.yaml --dry-run`
  - workflow validation succeeded

## Residual Risks

- The earlier medium review finding around direct `call` acceptance proof remains open. This pass prioritized the earliest required unfinished tranche and did not add the missing direct tests for caller-visible producer identity, preserved internal provenance, callee-private defaults isolation, or call-scoped freshness bookkeeping.
- Task 15 linting/normalization and Task 16 compatibility/smoke verification remain unstarted in this pass.
