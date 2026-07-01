# Design Delta Compatibility-Carrier Retirement Implementation Plan

> **For agentic workers:** Use the repository's normal planning/execution skills.
> Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Remove `run_state_path` / `run-state` as a live internal Workflow Lisp
compatibility carrier for the Design Delta parent-drain route.

**Architecture:** This is a carrier-retirement slice, not a report-refresh
slice. Retire executable/typecheck/lowering admission for `run_state_path` as a
live promoted-route carrier. Reports, census files, manifests, and checked JSON
are conditional consumers only: touch them only when a changed executable
contract makes a current check fail.

## Governing Inputs

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-compatibility-carrier-retirement/implementation_architecture.md`
- current-run selector/work-item context for this gap

## Scope

In scope:

- remove or quarantine stale Design Delta `run-state` payload types used by
  promoted/internal composition;
- remove generic `run_state_path` bridge omission/classification from
  typecheck/lowering/private-boundary helpers;
- update authoritative checked fixture mirrors when a touched Design Delta
  library module is byte-mirrored under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`;
- update report/census/manifest consumers only if they fail after the live
  executable carrier is retired;
- preserve still-live non-`run_state_path` compatibility bridges, such as
  `progress_ledger_path`, when they have a real current consumer;
- prove the promoted parent-drain route still compiles and smokes without
  reviving `run_state_path`.

Out of scope:

- broad census, manifest, parity, or report refreshes whose only purpose is to
  realign stale evidence, ordering, timestamps, or summaries;
- provider request-record migration;
- consumer-side rendering completion;
- YAML-primary promotion;
- rewriting unrelated stdlib drain semantics.

## Task 1: Confirm The Live Carrier Surface

Run:

```bash
rg -n "run_state_path|run-state StateExisting|ctx__run_state_path|drain\\.loop\\.run_state_path|work_item\\.loop\\.run_state_path" \
  workflows/library/lisp_frontend_design_delta \
  orchestrator/workflow_lisp \
  workflows/examples/inputs/workflow_lisp_migrations \
  tests
```

Classify hits into:

- live executable/typecheck/lowering admission;
- live family type surface;
- negative tests;
- historical report/census mentions.

Do not promote report/census hits into implementation obligations during this
task. Treat them as diagnostic consumers unless a focused runnable check fails
after the live carrier is removed.

## Task 2: Remove Live Admission

Edit only the files that own live admission:

- `workflows/library/lisp_frontend_design_delta/types.orc`, if the stale
  `SelectionResult.DONE (run-state StateExisting)` shape is still reachable from
  promoted/internal composition;
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/*.orc`,
  but only when a changed authoritative library module is mirrored there and
  the fixture must stay byte-aligned with the library module set;
- `orchestrator/workflow_lisp/typecheck_calls.py`, to remove any
  `run_state_path` private-omission special case;
- `orchestrator/workflow_lisp/phase_family_boundary.py`, to remove
  `run_state_path` from live compatibility-bridge parameter recognition;
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`, to remove live
  managed input contracts for `run_state_path`;
- `orchestrator/workflow_lisp/lowering/phase_scope.py`, to remove
  `ctx.run_state_path` compatibility-bridge authority mapping.

Keep `progress_ledger_path`, `manifest_path`, and other current bridges intact.
Do not rename `run_state_path` into another carrier.
If `types.orc` changes, inspect the authoritative mirror test before finishing
the task and update only the mirrored module bytes required to keep the checked
fixture synchronized.

## Task 3: Repair Direct Consumers Only If They Fail

After Task 2, run the focused checks below. If a report, census, manifest, or
checked JSON consumer fails because it directly reads the retired executable
contract, update that consumer narrowly to stop requiring the retired carrier.
Do not edit report/census owner code or checked inputs preemptively.

Allowed examples:

- a boundary inspection check still reports a promoted-route `run_state_path`
  after the executable carrier has been removed;
- a build-artifact check fails because the compiled contract no longer contains
  the retired field;
- a checked fixture mirror must be updated because the source `.orc` module
  changed.

Forbidden examples:

- refreshing a census or manifest solely because it mentions historical
  `run_state_path` rows;
- broad inventory, parity, or report realignment;
- adding new evidence lanes that do not protect a changed executable consumer.

## Task 4: Update Focused Tests

Update only tests that fail because the live carrier was retired.

Required coverage:

- promoted Design Delta route has no public or private `run_state_path` bridge;
- `run-state` is absent from active family composition or quarantined outside
  the promoted route;
- checked Design Delta fixture mirrors stay byte-aligned with the authoritative
  library module set when any mirrored `.orc` module changes;
- helper-level workflow-ref omission/specialization owners still agree on which
  hidden bridge inputs are omittable versus required;
- arbitrary callers still cannot omit real private bridge inputs;
- one still-live bridge remains covered so generic bridge behavior is not
  deleted wholesale;
- direct build and runtime consumers stop treating the retired carrier as live
  promoted-route semantics; and
- runtime-native `drain_run_state` remains distinguishable from hidden
  `run_state_path` carriage where those consumers are touched.

Prefer narrow tests in:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_typed_prompt_inputs.py`
- `tests/test_workflow_lisp_workflows.py`
- `tests/test_workflow_lisp_build_artifacts.py`, only when compiled-contract
  outputs change

Add report/census/resume/alignment suites only when the implementation edits
those owners or their checked inputs.

## Verification

Run the narrow selectors that match the files actually touched.
Because the current parent-family CLI dry-run is explicitly waived for this
slice in the checked parity target metadata, minimum verification must still
include the bounded parent-callable smoke lane that backs that waiver.

Minimum verification:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "run_state or carrier or bridge or selected_item_stdlib or drain_run_state" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "fixture_mirror or mirror_matches_library_module_set" -q
python -m pytest tests/test_workflow_lisp_lowering.py -k "carries_derived_phase_context_bindings or private_compatibility_bridge_omission" -q
python -m pytest tests/test_workflow_lisp_typed_prompt_inputs.py -k "hidden_bridge or request_field_authority" -q
python -m pytest tests/test_workflow_lisp_workflows.py -k "bridge_omission_helpers or private_bridge_type_helper" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "derived_child_phase_binding or hidden_compatibility_bridge or parent_drain_imported_backlog_drain or boundary_authority" -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_smokes" -q
```

If tests were added or renamed, run `pytest --collect-only` for those modules.

If checked inputs or report-owner code changed outside those selectors because
a direct consumer failed, add only the direct consumer suite for that touched
contract surface.

## Completion Criteria

- `run_state_path` is not a promoted-route public input, private bridge input,
  workflow-ref omission, or lowering authority class.
- `run-state` is absent from active Design Delta family composition or clearly
  quarantined outside the promoted route.
- direct build/runtime consumers no longer describe the retired carrier as live
  promoted-route semantics.
- `transitions.resource.drain_run_state` is represented as runtime-native
  state-layout-backed behavior, not as a live `run_state_path` compatibility
  carrier.
- remaining compatibility bridges have current named consumers.
- authoritative checked fixture mirrors remain byte-aligned with the Design
  Delta library modules they mirror.
- the parent-drain compile entrypoint succeeds.
- the bounded parent-callable smoke lane passes via
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_drain_smokes"`,
  or a newly-runnable parent-family dry-run supersedes it with the waiver and
  plan updated accordingly.
- focused tests for touched code pass.
- no census, manifest, report, or parity artifact was refreshed unless tied to
  this concrete carrier-retirement contract.
