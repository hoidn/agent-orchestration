# DSL Evolution Implementation Report

## Completed In This Pass

- Completed Task 10 from the approved execution plan:
  - locked the reusable-call contract boundary across the normative DSL/spec modules and the workflow drafting guide
  - reserved the future workflow-source-relative asset surface (`imports`, `asset_file`, `asset_depends_on`) without claiming current runtime support
  - documented the source-relative versus workspace-relative path taxonomy so `call` will namespace identities, not authored workspace files
  - documented the first-tranche accepted operational-risk boundary: inline/non-isolating `call`, mandatory typed `relpath` write-root inputs for reusable workflows, and distinct per-invocation bindings when managed paths could collide
  - scheduled the explicit Task 11 state boundary (`schema_version: "2.1"`) for call frames, call-scoped lineage/freshness, and the outer-producer/internal-provenance split for exported call outputs
  - added reusable-call acceptance items 147-158 plus an explicit Task 10 -> Task 11 proof crosswalk in `specs/acceptance/index.md`
  - added authoring guidance for preparing workflows for later `call` reuse

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

## Remaining Required Plan Tasks

- Task 11: Land imports and `call` on top of typed boundaries and qualified identities
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest tests/test_loader_validation.py -k "call or import or version" -v`
  - `9 passed, 71 deselected`
- `rg -n '^(147|148|149|150|151|152|153|154|155|156|157|158)\.|^\| (147|148|149|150|151|152|153|154|155|156|157|158) \|' specs/acceptance/index.md`
  - confirmed acceptance items 147-158 exist and each item has an explicit Task 11 proof-mapping row in the rollout crosswalk

## Residual Risks

- Task 10 is a docs/contract tranche only: the current loader/runtime still stop at the implemented `v2.3` surface and do not yet execute `imports`, `call`, `asset_file`, or `asset_depends_on`.
- Task 11 must still enforce the documented write-root/input contract and deliver the planned `schema_version: "2.1"` call-frame state boundary for private callee lineage and freshness bookkeeping.
- The broader roadmap remains incomplete from Task 11 onward; reusable-call execution, `match`, `repeat_until`, score-aware gates, linting, and the final full-suite smoke sweep are still required.
