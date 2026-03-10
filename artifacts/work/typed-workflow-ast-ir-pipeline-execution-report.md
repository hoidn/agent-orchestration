# Completed In This Pass

- Removed the bundle-backed bound-address scan fallback in `WorkflowExecutor` so typed node-id resolution now succeeds only through projection-owned keys or explicit loop-scope node indexes.
- Switched bundle-backed helper dispatch and helper metadata reads onto typed executable IR for structured `if`/`match` markers and joins, so those nodes no longer depend on legacy helper keys being present in adapter dicts.
- Changed reusable-call write-root collision checks to use typed imported-bundle provenance instead of imported legacy magic metadata.
- Added regression coverage for fail-closed bound-address lookup, typed helper dispatch under adapter drift, and runtime write-root collision detection without imported legacy metadata.

# Completed Plan Tasks

- Tranche 4 runtime slice: bundle-backed execution now uses typed helper-node kinds and typed helper metadata for structured control markers/joins instead of legacy helper-key dispatch.
- Tranche 4 runtime slice: bound references no longer resolve by scanning persisted compatibility entries and rewriting step ids.
- Tranche 4 call/runtime slice: managed write-root collision validation now reads typed import metadata from loaded bundles, not imported legacy dict magic.

# Remaining Required Plan Tasks

- Tranche 4: migrate top-level and nested execution advancement fully onto IR node ids plus routed transfers instead of ordered compatibility step lists.
- Tranche 4: move resume planning and finalization sequencing fully onto IR regions/projection state instead of the appended finalization-slice model.
- Tranche 5: replace the legacy adapter’s second lowering pipeline, remove steady-state legacy magic metadata, and update maintainer docs to the `parse -> elaborate -> lower -> execute` model.

# Verification

- `pytest --collect-only -q tests/test_workflow_executor_characterization.py tests/test_subworkflow_calls.py`
  - `30 tests collected`
- `pytest tests/test_workflow_executor_characterization.py::test_executor_bound_address_resolution_fails_closed_without_projection_owned_lookup tests/test_workflow_executor_characterization.py::test_executor_uses_typed_if_nodes_when_legacy_helper_keys_are_removed -v`
  - `2 passed`
- `pytest tests/test_subworkflow_calls.py::test_call_rejects_colliding_write_root_bindings_without_imported_legacy_magic -v`
  - `1 passed`
- `pytest tests/test_workflow_executor_characterization.py tests/test_workflow_state_projection.py tests/test_subworkflow_calls.py -v`
  - `37 passed`
- `pytest tests/test_resume_command.py::test_resume_fails_closed_on_projection_current_step_integrity_mismatch -v`
  - `1 passed`

# Residual Risks

- The executor still builds its top-level execution catalog from the compatibility adapter plus projection ordering, so IR routed transfers are not yet the sole execution truth.
- Structured branch body leaf steps still rely on lowered guard metadata for skip behavior until the broader IR-driven routing tranche lands.
- The legacy adapter still re-thaws and re-lowers surface data, so Tranche 5 cleanup remains necessary to eliminate the parallel lowering path entirely.
