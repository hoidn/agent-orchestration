## Completed In This Pass

- Corrected the stale scalar-bookkeeping verification assertion so `tests/test_scalar_bookkeeping.py` matches the current persisted state contract, including `artifact_versions[*].producer_name`.
- Started Task 11 with the first coherent execution slice:
  - added loader support for `version: "2.5"`
  - added top-level `imports` loading and independent imported-workflow validation
  - enforced the first-tranche caller/callee same-version rule during import loading
  - added loader validation for `call` boundaries: authored stable `id` required, unknown import aliases rejected, and literal / `{ref: ...}` `with:` bindings checked against callee input contracts
  - rejected workflow-source-relative import-path escapes outside the authored workflow source tree
- Added workflow-source-relative provider asset support:
  - introduced `orchestrator/workflow/assets.py`
  - `asset_file` now reads provider prompt text relative to the authored workflow file
  - `asset_depends_on` now injects ordered source-asset content blocks before the base prompt
  - loader validation rejects invalid `asset_file` / `asset_depends_on` usage and source-tree traversal
- Added an explicit runtime failure path for `call` steps (`error.type: "call_not_implemented"`) so v2.5 validation support cannot silently no-op when executed before full call-frame runtime lands.

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

- Task 11: complete inline `call` execution on top of the new validation groundwork:
  - call-frame runtime/state model (`schema_version: "2.1"`)
  - deferred callee output export on the outer call step
  - callee-private providers/artifacts/context isolation at runtime
  - call-scoped `artifact_versions` / `artifact_consumes` / freshness bookkeeping
  - resume coverage for interrupted call frames
  - operator/runtime docs and example workflows for shipped call execution
- Task 12: Add `match` as a separate structured-control tranche
- Task 13: Add post-test `repeat_until` as its own loop tranche
- Task 14: Add score-aware gates on top of the stable predicate system
- Task 15: Add authoring-time linting and normalization after the new syntax exists
- Task 16: Run the final compatibility and smoke sweep before merge

## Verification

- `pytest --collect-only tests/test_subworkflow_calls.py -q`
  - `6 tests collected`
- `pytest tests/test_subworkflow_calls.py tests/test_prompt_contract_injection.py tests/test_scalar_bookkeeping.py -k 'asset or call or import or set_scalar' -v`
  - `10 passed, 17 deselected`
- `pytest tests/test_loader_validation.py -k 'version or unknown' -v`
  - `10 passed, 70 deselected`
- `pytest tests/test_prompt_contract_injection.py -k 'provider_expected_outputs_appends_contract_block_to_prompt or inject_output_contract_false or asset_file or asset_depends_on' -v`
  - `4 passed, 13 deselected`

## Residual Risks

- Task 11 is still partial. Validation and source-asset prompt composition are in place, but executing a `call` step still fails explicitly with `call_not_implemented` until the call-frame runtime/state work lands.
- The reserved reusable-call state boundary (`schema_version: "2.1"`) is still outstanding, so call-scoped lineage/freshness and resume semantics are not implemented yet.
- Normative docs/specs and workflow examples were intentionally left unchanged in this pass because the runtime contract for full reusable-call execution is not complete yet; those updates still belong to the remaining Task 11 runtime tranche.
