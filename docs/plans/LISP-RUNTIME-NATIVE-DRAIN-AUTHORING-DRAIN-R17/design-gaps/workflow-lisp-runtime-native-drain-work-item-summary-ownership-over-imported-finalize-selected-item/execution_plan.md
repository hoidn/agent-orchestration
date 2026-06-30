# Work-Item Summary Ownership Over Imported `finalize-selected-item` Execution Plan

**Goal:** Make `lisp_frontend_design_delta/work_item::run-work-item` return typed
`WorkItemResult` values without body-owned summary materialization. Delete
`artifacts/work/item_summary.json` unless a named public or legacy consumer is
still part of the accepted contract.

**Approach:** Change source behavior first.

What this makes harder later: any real legacy consumer must be named before it
can shape this route.

## Scope

- Update `workflows/library/lisp_frontend_design_delta/work_item.orc`.
- Update `workflows/library/lisp_frontend_design_delta/types.orc` only if the
  current `WorkItemResult.summary-path` type forces pre-rendered summary bytes.
- Update `workflows/library/lisp_frontend_design_delta/transitions.orc` only if
  blocked-recovery still couples typed return to summary-file rendering.
- Keep matching fixture copies under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/`
  aligned with edited library modules.
- Update direct behavior tests in
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`.
## Non-Goals

- Do not redesign `std/resource::finalize-selected-item` or
  `std/drain::backlog-drain`.
- Do not broaden into YAML-primary promotion, provider request-record rewrites,
  command-adapter retirement, or general Design Delta cleanup.
## Tasks

### 1. Tighten The Behavior Test

- Update
  `test_design_delta_parent_drain_summary_cleanup_removes_helper_owned_summary_rendering`
  so it fails while `run-work-item` still calls
  `materialize-canonical-work-item-summary`.
- Remove expectations that selected-item/work-item routes produce
  `artifacts/work/item_summary.json` unless the test names a real external
  consumer.
- Keep or reuse the existing complete, terminal-blocked, and blocked-recovery
  smokes so typed return behavior is covered after the source edit.
- If a test is added or renamed, run collect-only for the touched module.

### 2. Remove Body-Owned Summary Rendering

- In `work_item.orc`, change terminal branches so they construct and return
  `WorkItemResult` from typed values plus the declared summary target carrier.
- Do not call `materialize-canonical-work-item-summary` merely to make
  `WorkItemResult.summary-path` valid.
- Keep `project-work-item-result-summary` only as a typed projection helper.
- If the current `WorkItemResult.summary-path` type forces pre-rendered bytes,
  change the family-owned type to a target/carrier type that represents the
  declared output location instead of an already-materialized report.
- If `transitions.orc` is touched, keep the change limited to decoupling durable
  transition behavior from summary-file rendering.
- Mirror edited library `.orc` files into the runtime fixture directory.

### 3. Final Sanity Check

Use existing tests only as a sanity check for the changed path:

```bash
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py --collect-only -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -q -k "test_design_delta_parent_drain_summary_cleanup_removes_helper_owned_summary_rendering or test_design_delta_selected_item_stdlib_direct_route_returns_status_without_summary_path or test_design_delta_parent_call_work_item_smokes_complete_and_blocked_recovery_routes or test_design_delta_parent_call_work_item_smokes_terminal_blocked_route or test_design_delta_work_item_runtime_fixture_mirror_matches_library_module_set"
```

## Completion Criteria

- `run-work-item` no longer calls `materialize-canonical-work-item-summary`.
- `run-work-item` returns typed `WorkItemResult` values for complete,
  terminal-blocked, and blocked-recovery paths.
- The direct selected-item route does not require or produce
  `artifacts/work/item_summary.json` unless a named external consumer requires
  it.
- Any surviving summary path is outside ordinary internal composition.
- Edited fixture mirrors match edited library modules.
- The existing changed-path sanity checks pass, or any remaining failure is
  clearly unrelated to this summary-ownership slice.
