## Completed In This Pass

- Fixed the high-severity reusable-`call` lineage defect from review.
  - routed `call` step results through the standard `_record_published_artifacts()` path so exported callee outputs can satisfy outer-step `publishes.from`
  - added a direct regression test proving caller-visible `call` outputs publish into `artifact_versions`, preserve inner-step provenance metadata, and can be consumed by a downstream caller step
- Completed the next required approved tranche: Task 15 `authoring-time linting and normalization`.
  - added `orchestrator/workflow/linting.py` with initial advisory warnings for shell gates, stringly `when.equals`, raw `goto` diamonds, and colliding imported output names
  - surfaced lint warnings in `orchestrate report` JSON/Markdown output and in `orchestrate run --dry-run`
  - added focused lint/report tests and updated DSL/CLI/versioning/authoring docs for `v2.9`

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
- Task 15: Add authoring-time linting and normalization after the new syntax exists

## Remaining Required Plan Tasks

- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest tests/test_subworkflow_calls.py -v`
  - `10 passed`
- `pytest --collect-only tests/test_dsl_linting.py -q`
  - collected `4 tests`
- `pytest tests/test_dsl_linting.py tests/test_cli_report_command.py -v`
  - `12 passed`
- `PYTHONPATH=/home/ollie/Documents/agent-orchestration python -m orchestrator run workflows/examples/call_subworkflow_demo.yaml --dry-run`
  - workflow validation succeeded

## Residual Risks

- Task 16's full compatibility and smoke sweep is still required before merge.
- This pass closed the caller-visible `call` publish gap and added direct lineage/provenance proof, but it did not add fresh targeted tests for every remaining reusable-`call` acceptance item called out in review (notably callee-private defaults isolation and call-scoped freshness/finalization behavior).
