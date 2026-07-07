# Design Delta Work-Item Private Phase Context Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to execute this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Finish the private-`PhaseCtx` work-item boundary slice by carrying the already-repaired generic source-map/transition-authoring route through the remaining stale checked `boundary_authority`, `value_flow_census`, and `consumer_rendering_census` inputs on the Design Delta parent-drain acceptance path.

**Architecture:** Treat the source/runtime repair and the first checked-input reconciliation as already identified on the blocked route, but do not trust prior attempt state without re-verification: the authored-mapping source-map fallback must classify lowered declared transitions generically, the checked transition-authoring manifest/tests must reflect the live imported-finalizer route, and the checked boundary/value-flow manifests must describe only live compiled rows. Task 1 proves whether those baselines are actually present on the execution checkout; only then should implementation reconcile stale checked parent-drain consumer-rendering rows whose C0 consumer lane no longer matches the live C3 entry-publication/materialize-view evidence. What this makes harder later: the checked manifest lanes now depend explicitly on compiled evidence ordering, so future route changes must update the checked inputs and their focused guards together instead of assuming downstream reports will remain stable.

**Tech Stack:** Workflow Lisp `.orc`, shared compile/build validation, source maps, checked manifest reconciliation, `python -m orchestrator compile`, `pytest`, and `rg`

---

## Fixed Inputs And Authority

Use these inputs as the governing contract for this plan:

- `docs/index.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-work-item-private-phasectx-boundary/implementation_architecture.md`
- the recovery-provided work-item context artifact identified by the current
  recovery bundle or implementation handoff state; this durable plan must
  describe the artifact by role rather than hard-code a generated run path.

Consumed but non-governing context: `docs/steering.md` was reviewed because it
was supplied with the work item, but `docs/index.md` routes that document to
the unrelated DSL v2.14 materialization / variant-output backlog drain rather
than this Design Delta gap slice. Do not treat it as execution authority here.

Acceptance authority, highest first:

1. The implementation architecture's root-cause classification, shared-surface rules, allowed shapes, forbidden shapes, and acceptance conditions.
2. `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Sections 7.4, 7.5, 7.7, 8.1, 12.1, and 13.4.
3. `docs/design/workflow_lisp_frontend_specification.md` for the parent frontend/routing contract and the rule that private context stays off public boundaries while transition effects remain visible in source maps and Semantic IR.
4. `docs/design/workflow_command_adapter_contract.md` for fail-closed checked-manifest discipline.

Do not make manifest cleanup, summary refresh, parity inventory, or status-label work a blocking task unless the artifact is a direct compile/build input for the gated behavior. In this slice, `transition_authoring.json`, `boundary_authority.json`, `value_flow_census.json`, and `consumer_rendering_census.json` are such direct inputs.

## Current Causal State

Plan from the live failure chain, not from the older symptom that "the work-item route is still blocked."

1. The work-item owner boundary itself is already the accepted live contract.
   - `run-work-item` remains the owner boundary.
   - `phase-ctx__work-item` remains the derived private runtime binding.
   - public `RunCtx`, `PhaseCtx`, generated roots, checkpoint paths, and `run_state_path` are still forbidden on the promoted boundary.
2. The first causal source/runtime defect was already identified and repaired in the prior attempt.
   - no-bundle source-map serialization must emit `resource_transition` for lowered declared-transition steps;
   - imported `std/resource::finalize-selected-item-proc` transition origins must stay visible in the source map and transition-authoring report;
   - stale `std/drain` result-proc transition-authoring rows were removed because those procs are pure constructors on the live route.
3. After that repair, the same parent-drain acceptance route failed closed on two checked-input lanes that described a superseded boundary shape.
   - `tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact` failed with `value_flow_census_invalid`.
   - the target compile entrypoint failed with `workflow_boundary_authority_unclassified`.
   - both failures pointed at stale checked rows tied to retired `std_drain_*_drain_result_proc_*__outcome__result_bundle` boundary/value-flow shapes.
4. The previous implementation attempt removed those stale boundary/value-flow rows and verified the raw boundary registry against compiled expected rows (`STALE 0`, `MISSING 0`), then the same acceptance route advanced to a new direct checked-input gate:
   - the target compile entrypoint now fails with `[interior_publication] design-delta entry publication report failed: interior_publication: c0.std_drain_materialized_shared_drain_result_summary`;
   - the failing row lives in `design_delta_parent_drain.consumer_rendering_census.json`;
   - the row is selected for entry publication even though its live `workflow_surface` is the imported non-entry `std/drain::backlog-drain` workflow and compiled evidence still includes body-level `materialize_view` effects for that workflow.
5. Therefore the remaining owned work is checked-input reconciliation, not a new workflow-authoring change.
   - preserve the generic source-map repair and the transition-authoring contract if they are already green;
   - preserve the boundary/value-flow reconciliation if it is already aligned;
   - reconcile only stale checked consumer-rendering rows whose C0 classification no longer matches the live C3 publication/materialize-view route;
   - keep all fail-closed gates active.

## Scope Guards

- Do not edit `drain.orc`, `work_item.orc`, `selector.orc`, `plan_phase.orc`, `implementation_phase.orc`, or stdlib `.orc` modules unless fresh verification proves the source/runtime repair is missing or regressed on this checkout.
- Do not weaken or bypass `transition_authoring_invalid`, `workflow_boundary_authority_unclassified`, or `value_flow_census_invalid`.
- Do not weaken or bypass `consumer_rendering_census_invalid`, `entry_publication_c0_row_missing`, or `interior_publication`.
- Do not keep stale checked rows by relabeling them as compatibility bridges, runtime-derived values, or generated-internal values if the live compiled route no longer emits them.
- Do not keep a non-entry body materialization row selected for entry publication if live compiled evidence proves it is not a legal entry-workflow terminal publication.
- Do not add Design Delta-specific branches in shared Python surfaces.
- Do not reintroduce `run_state_path`, public `PhaseCtx`, or any compatibility carrier on the work-item route.
- Do not treat report existence as proof; the report contents and fail buckets must match the live route.

## File Map

Primary checked-input and consumer surfaces:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.rendering_cleanup.json`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/phase_family_boundary.py`
- `orchestrator/workflow_lisp/value_flow_census.py`
- `orchestrator/workflow_lisp/consumer_rendering_census.py`
- `orchestrator/workflow_lisp/entry_publication.py`

Preserve-and-verify generic repair surfaces:

- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/transition_authoring.py`
- `tests/test_workflow_lisp_source_map.py`
- `tests/test_workflow_lisp_transition_authoring.py`

Focused checked-input proof surfaces:

- `tests/test_workflow_lisp_build_artifacts.py`

Read-only live route and boundary fixtures:

- `workflows/library/lisp_frontend_design_delta/drain.orc`
- `workflows/library/lisp_frontend_design_delta/work_item.orc`
- `workflows/library/lisp_frontend_design_delta/transitions.orc`

## Task 1: Reconfirm The Repaired Baseline And Capture The First Remaining Checked-Input Failures

**Files:**

- Read:
  - `orchestrator/workflow_lisp/source_map.py`
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
  - `tests/test_workflow_lisp_source_map.py`
  - `tests/test_workflow_lisp_transition_authoring.py`
  - `tests/test_workflow_lisp_build_artifacts.py`

- Modify only if the baseline repair is missing on this checkout:
  - `orchestrator/workflow_lisp/source_map.py`
  - `orchestrator/workflow_lisp/transition_authoring.py`
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
  - `tests/test_workflow_lisp_source_map.py`
  - `tests/test_workflow_lisp_transition_authoring.py`

- [ ] **Step 1: Re-run the transition-authoring approval lane**

Run:

```bash
pytest tests/test_workflow_lisp_transition_authoring.py -q
```

Expected: `13 passed`. If this fails, do not touch `boundary_authority.json`, `value_flow_census.json`, or `consumer_rendering_census.json` yet; restore the prior generic source-map/transition-authoring repair first because the causal source/runtime defect is still open.

- [ ] **Step 2: Re-run the source-map regression lane**

Run:

```bash
pytest tests/test_workflow_lisp_source_map.py -q
```

Expected: green, including `test_source_map_no_bundle_finalize_selected_item_resource_transition_regression`.

- [ ] **Step 3: Re-run the preserved private-context and work-item guards**

Run:

```bash
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_call_work_item_boundary_projection_records_derived_work_item_phase_binding \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_work_item_runtime_context_inputs_stay_internal \
  tests/test_workflow_lisp_transition_authoring.py::test_design_delta_parent_drain_shared_validation_clears_direct_boundary_state_path_lints \
  -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item" -q
```

Expected:

- the three focused selectors pass;
- the feasibility lane stays green (`17 passed` on the consumed retry baseline).

- [ ] **Step 4: Reproduce the first still-failing parent-drain build selector**

Run:

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact -q
```

Expected on the revised checkout: the selector should no longer fail with `value_flow_census_invalid` or `workflow_boundary_authority_unclassified`. If it fails, the first failure should be the newly exposed consumer-rendering / entry-publication gate (`interior_publication` for `c0.std_drain_materialized_shared_drain_result_summary`) rather than a reopened source/runtime defect. If it passes, continue to the compile entrypoint because the build helper may already be using an aligned C0 fixture.

- [ ] **Step 5: Reproduce the target compile entrypoint**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected on the revised checkout: fail closed with `[interior_publication]` against `c0.std_drain_materialized_shared_drain_result_summary`. It must not fail with `workflow_boundary_authority_unclassified` or `value_flow_census_invalid`; those indicate the prior checked-input reconciliation regressed.

- [ ] **Step 6: Stop and reclassify if the failure chain changed**

If Steps 1-5 do not match the expected ordering, stop and record the new first failing causal defect before editing any checked manifests. This plan assumes the source/runtime repair is already present, the boundary/value-flow rows are aligned or directly reconcilable, and the remaining blocker is stale consumer-rendering classification.

- [ ] **Step 7: Restore the generic source-map repair first if Steps 1-2 prove it missing**

If `tests/test_workflow_lisp_source_map.py` or
`tests/test_workflow_lisp_transition_authoring.py` fail because lowered
declared-transition steps on the no-bundle serialization route still emit kind
`step`, repair `orchestrator/workflow_lisp/source_map.py` generically before
editing any checked manifests:

- classify any authored-mapping fallback node that carries declared
  `resource_transition` config as step kind `resource_transition`;
- do not add workflow-name, path-name, or stdlib-specific branches; and
- add or update the focused source-map regression in
  `tests/test_workflow_lisp_source_map.py` so the no-bundle finalizer route
  proves the generic rule.

Then rerun:

```bash
pytest tests/test_workflow_lisp_source_map.py -q
pytest tests/test_workflow_lisp_transition_authoring.py -q
```

Expected: the source-map suite is green and the transition-authoring suite no
longer loses imported `std/resource::finalize-selected-item-proc` origins due
to fallback misclassification.

- [ ] **Step 8: Restore the checked transition-authoring contract if Step 1 still fails after Step 7**

If the transition-authoring suite still fails on `stale_allowed_origins` or on
the stale pass-case expectations after the generic source-map repair is green,
reconcile the checked direct input and focused guards before touching
boundary/value-flow/consumer-rendering manifests:

- remove the three stale
  `low_level.imported_*_drain_result` rows from
  `design_delta_parent_drain.transition_authoring.json`;
- preserve `low_level.imported_finalize_selected_item` and the family
  transitions helper rows that still exist on the live route;
- update `tests/test_workflow_lisp_transition_authoring.py` so the pass-case
  asserts the live contract: pass status, empty violation buckets, transitions
  attributed to `lisp_frontend_design_delta/transitions` and
  `lisp_frontend_design_delta/work_item`, and imported finalize rows anchored
  to `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`; and
- inspect `orchestrator/workflow_lisp/transition_authoring.py` only if the
  manifest and focused guards already match the compiled origins yet the report
  still disagrees. Any code fix there must stay generic to report filtering or
  matching logic.

Then rerun:

```bash
pytest tests/test_workflow_lisp_transition_authoring.py -q
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact -q
```

Expected: the transition-authoring suite is green and the build no longer fails
on the transition-authoring gate.

- [ ] **Step 9: Re-run Steps 1-5 and continue only after the baseline repair is proven**

After any Step 7-8 repair, rerun the Task 1 verification ladder from the top.
Do not continue to Task 2, Task 3, or Task 4 until:

- `tests/test_workflow_lisp_transition_authoring.py` passes;
- `tests/test_workflow_lisp_source_map.py` passes; and
- the first remaining parent-drain failure is no earlier than
  `workflow_boundary_authority_unclassified`,
  `value_flow_census_invalid`, or the known
  `interior_publication` consumer-rendering gate.

## Task 2: Reconcile The Checked Boundary-Authority Registry To The Live Compiled Boundary Projection

**Files:**

- Modify:
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`

- Read or modify if assertions encode stale row IDs:
  - `tests/test_workflow_lisp_build_artifacts.py`

- Read only unless a real generic consumer bug is proven:
  - `orchestrator/workflow_lisp/build.py`
  - `orchestrator/workflow_lisp/phase_family_boundary.py`

- [ ] **Step 1: Derive the live expected boundary rows before editing the checked registry**

Use the raw checked registry as the discovery authority, not the normalized helper:

- `_load_design_delta_boundary_authority_registry()`
- `build_design_delta_boundary_authority_expected_rows(...)`

If you inspect the JSON directly instead of calling the loader, compare the checked file contents to the compiled expected-row keyset before touching any row ids, authority classes, or surface kinds. Do not use `_aligned_design_delta_boundary_authority_registry(tmp_path)` for this discovery step; that helper rebuilds the registry from compiled expected rows and can hide the stale checked rows this task must reconcile.

Expected finding on a checkout before the previous implementation attempt: the checked registry contains one or more `managed_write_root` rows for `lisp_frontend_design_delta/drain::drain` keyed to retired `std_drain_*_drain_result_proc_*__outcome__result_bundle` fields that are absent from the live compiled expected rows. Expected finding on the current blocked checkout: the raw registry is already aligned (`STALE 0`, `MISSING 0`) and this task is verification only.

- [ ] **Step 2: Remove or replace only rows the live compiled route proves stale**

Edit `design_delta_parent_drain.boundary_authority.json` so that every remaining row has a live compiled `(workflow_name, field_name, surface_kind)` match. Preserve:

- live `generated_internal` rows that still appear in the compiled boundary projection;
- imported finalizer-related rows that the current route still emits; and
- all negative stale-row rejection behavior in the build consumer.

Do not invent new authority classes or convert a stale row into a compatibility bridge to clear the gate.

- [ ] **Step 3: Re-run the focused positive and negative boundary-authority guards**

At this point it is valid to use `_aligned_design_delta_boundary_authority_registry(tmp_path)` indirectly through the existing positive-path tests, because the raw checked registry has already been reconciled and the helper is serving only as a compiled-fixture verifier.

Run:

```bash
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_boundary_authority_registry_covers_expected_rows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_stale_boundary_authority_registry_row_mismatch \
  -q
```

Expected:

- the positive report/build selectors pass;
- the synthetic stale-row negative test still fails closed with `workflow_boundary_authority_unclassified`.

- [ ] **Step 4: Re-run the compile entrypoint**

Run the compile command from Task 1 Step 5 again.

Expected: the compile no longer fails on `workflow_boundary_authority_unclassified`. If it now fails later on `value_flow_census_invalid`, the boundary registry is aligned and the next owned blocker is the checked census. If it fails with `interior_publication`, both the boundary registry and the value-flow census are past their old blockers and the remaining owned blocker is Task 4.

- [ ] **Step 5: Touch shared consumers only if the registry and compiled rows already agree**

If the checked registry and compiled expected rows match but the compile still raises `workflow_boundary_authority_unclassified`, inspect `build.py` and `phase_family_boundary.py`. Any repair there must be generic to checked boundary-row matching and must not key off Design Delta workflow names.

## Task 3: Reconcile The Checked Value-Flow Census To Live Boundary And Source Evidence

**Files:**

- Modify:
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`

- Read or modify if assertions encode stale row IDs:
  - `tests/test_workflow_lisp_build_artifacts.py`

- Read only unless a real generic reconciliation bug is proven:
  - `orchestrator/workflow_lisp/build.py`
  - `orchestrator/workflow_lisp/value_flow_census.py`

- [ ] **Step 1: Diff the checked census against live reconciliation output**

Use the raw checked census as the discovery authority:

- `_load_design_delta_value_flow_census()`
- `reconcile_value_flow_census(...)`

If you inspect the JSON directly instead of calling the loader, run reconciliation against the raw payload and compare its `missing_rows`, `stale_rows`, and `invalid_rows` before editing the checked file. Do not use `_aligned_design_delta_value_flow_census(tmp_path)` for this discovery step; that helper removes a stale row, injects a replacement row, and can rewrite row ids from reconciliation output when `tmp_path` is provided.

Expected finding on a checkout before the previous implementation attempt: stale and/or missing rows cluster around the same retired `std_drain_*_drain_result_proc_*__outcome__result_bundle` shape that the boundary-authority lane already proved obsolete. Expected finding on the current blocked checkout: the raw census is already aligned for those rows and this task is verification only.

- [ ] **Step 2: Update only the rows that no longer match the live compiled route**

For each stale checked row:

- remove it if the live route emits no replacement row; or
- replace it with the exact live compiled row if reconciliation shows a renamed/specialized boundary symbol for the same surviving surface.

Preserve coverage metadata, source evidence kinds, and the contract that path-like boundary inventory aligns with the checked boundary-authority registry.

- [ ] **Step 3: Re-run the focused value-flow guards**

After the raw census has been reconciled, the existing positive-path tests may use `_aligned_design_delta_value_flow_census(tmp_path)` as a verification fixture only. Do not treat that helper as proof of which raw checked rows needed editing.

Run:

```bash
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_value_flow_census_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_value_flow_census_report_refs_checked_path_like_boundary_inventory \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_value_flow_census_manifest_records_input_provenance \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_value_flow_census_rejects_stale_compiled_evidence \
  -q
```

Expected:

- the positive value-flow report selectors pass with empty `missing_rows`, `stale_rows`, `invalid_rows`, and `extra_compiled_rows`;
- the synthetic stale-row negative test still fails closed with `value_flow_census_invalid`.

- [ ] **Step 4: Re-run the previously blocked build-artifact selector**

Run:

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact -q
```

Expected: the build no longer fails with `value_flow_census_invalid` while consuming the reconciled `boundary_authority` and `value_flow_census` inputs. If it fails with `interior_publication` for `c0.std_drain_materialized_shared_drain_result_summary`, continue to Task 4. If it passes, still run Task 4's focused consumer-rendering checks because an aligned fixture path may be masking raw checked C0 drift.

- [ ] **Step 5: Touch shared census consumers only if the checked census and compiled rows already agree**

If the checked census matches the live reconciliation output but the build still reports `value_flow_census_invalid`, inspect `build.py` and `value_flow_census.py`. Any fix must be generic to compiled-row reconciliation, not a Design Delta-specific exception.

## Task 4: Reconcile The Checked Consumer-Rendering Census To Live Entry-Publication Evidence

**Files:**

- Modify:
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.consumer_rendering_census.json`

- Read or modify if assertions encode stale row IDs:
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.rendering_cleanup.json`
  - `tests/test_workflow_lisp_build_artifacts.py`

- Read only unless a real generic report bug is proven:
  - `orchestrator/workflow_lisp/build.py`
  - `orchestrator/workflow_lisp/consumer_rendering_census.py`
  - `orchestrator/workflow_lisp/entry_publication.py`

- [ ] **Step 1: Diff the checked C0 census against live rendering and publication evidence**

Use the raw checked consumer-rendering census as the discovery authority:

- `_load_design_delta_consumer_rendering_census()`
- `build_consumer_rendering_census_report(...)`
- `_build_entry_publication_report(...)`

Compare the raw checked rows against:

- live U0 value-flow rows from `design_delta_parent_drain.value_flow_census.json`;
- compiled `materialize_view` effects from the parent-drain build;
- selected C0 entry-publication rows from `select_entry_publication_rows(...)`;
- the actual selected entry workflow and its `:publish` policy rows; and
- rendering-cleanup decisions if focused guards consume them.

Do not use a helper or mutated fixture that silently changes C0 row lanes before
this discovery step. The known current blocker is
`c0.std_drain_materialized_shared_drain_result_summary`: it is selected for
entry publication even though live evidence identifies it as a non-entry
`std/drain::backlog-drain` body-materialization / retirement row.

- [ ] **Step 2: Reclassify or remove only stale C0 rows**

Edit `design_delta_parent_drain.consumer_rendering_census.json` so every
remaining row's `consumer_lane`, `track_c_decision`, durability, renderer, and
compiled-effect metadata match the live consumer seam.

For `c0.std_drain_materialized_shared_drain_result_summary`, choose the minimal
live classification proved by Step 1:

- remove it if the U0 row no longer exists or no live consumer requires it;
- reclassify it as a non-entry retirement / observability / timed-body row if
  the live route still tracks it as body materialization evidence; or
- split it only if one live entry-terminal row and one separate non-entry body
  row both exist.

Do not leave it selected by `select_entry_publication_rows(...)` unless the row
is for the selected entry workflow's typed terminal variant and no body-level
materialize-view effect remains on that workflow.

- [ ] **Step 3: Align focused rendering cleanup assertions only where they name stale C0 row IDs**

If `rendering_cleanup.json` or build-artifact tests still expect the stale
entry-publication classification, update them to the live row contract from
Step 2. Keep cleanup assertions behavioral: pass status, selected row IDs,
cleanup decisions, bridge metadata, and empty fail buckets. Do not assert
rendered prose or prompt text.

- [ ] **Step 4: Re-run focused consumer-rendering and entry-publication guards**

Run:

```bash
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_consumer_rendering_census_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_reclassifies_summary_rows_to_entry_publication_and_bridge_metadata \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_rendering_cleanup_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_entry_publication_build_fails_closed_when_selected_non_entry_keeps_materialize_view \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_consumer_rendering_report_reconciles_materialize_view_effects \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_consumer_rendering_report_rejects_unmatched_materialize_view_effect \
  -q
```

Expected:

- positive consumer-rendering, rendering-cleanup, and entry-publication
  selectors pass with empty missing/stale/invalid/diagnostic buckets;
- the synthetic non-entry materialize-view selector still fails closed with
  `interior_publication`; and
- unmatched materialize-view evidence still fails closed with
  `consumer_rendering_census_invalid`.

- [ ] **Step 5: Re-run the previously blocked build-artifact selector and compile entrypoint**

Run:

```bash
pytest tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact -q
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: both pass. The compile must emit passing transition-authoring,
boundary-authority, value-flow, consumer-rendering, and entry-publication
reports.

- [ ] **Step 6: Touch shared report consumers only if raw C0 rows and compiled evidence already agree**

If the raw C0 census matches live evidence but the build still reports
`consumer_rendering_census_invalid`, `entry_publication_c0_row_missing`, or
`interior_publication`, inspect `build.py`, `consumer_rendering_census.py`, and
`entry_publication.py`. Any fix must be generic to C0/C3 reconciliation and
must not key off Design Delta workflow names.

## Task 5: Run The Full Acceptance Ladder

**Files:**

- Read only:
  - `workflows/library/lisp_frontend_design_delta/drain.orc`
  - `workflows/library/lisp_frontend_design_delta/work_item.orc`
  - `workflows/library/lisp_frontend_design_delta/plan_phase.orc`
  - `workflows/library/lisp_frontend_design_delta/implementation_phase.orc`
  - `workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc`
  - `workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc`
  - `workflows/library/lisp_frontend_design_delta/selector.orc`
  - `workflows/library/lisp_frontend_design_delta/types.orc`
  - `workflows/library/lisp_frontend_design_delta/projections.orc`
  - `workflows/library/lisp_frontend_design_delta/bootstrap.orc`

- [ ] **Step 1: Re-run the guarded suites that prove the repaired route**

Run:

```bash
pytest tests/test_workflow_lisp_transition_authoring.py -q
pytest tests/test_workflow_lisp_source_map.py -q
pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_call_work_item_boundary_projection_records_derived_work_item_phase_binding \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_work_item_runtime_context_inputs_stay_internal \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_boundary_authority_report_for_all_target_workflows \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_value_flow_census_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_consumer_rendering_census_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_reclassifies_summary_rows_to_entry_publication_and_bridge_metadata \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_rendering_cleanup_report_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_transition_authoring_report_artifact \
  -q
pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item" -q
pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_resource_stdlib.py -q
```

Expected: all pass with no reopened `run_state_path`, private-context, source-map, or shared owner-lane regressions.

- [ ] **Step 2: Re-run the target compile entrypoint**

Run the compile command from Task 1 Step 5.

Expected: success, with the transition-authoring, boundary-authority, value-flow census, consumer-rendering census, and entry-publication reports emitted at `pass`.

- [ ] **Step 3: Reconfirm the ordinary route remains carrier-free**

Run:

```bash
rg -n "run_state_path" \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  workflows/library/lisp_frontend_design_delta/work_item.orc \
  workflows/library/lisp_frontend_design_delta/plan_phase.orc \
  workflows/library/lisp_frontend_design_delta/implementation_phase.orc \
  workflows/library/lisp_frontend_design_delta/stdlib_adapters.orc \
  workflows/library/lisp_frontend_design_delta/stdlib_payloads.orc \
  workflows/library/lisp_frontend_design_delta/selector.orc \
  workflows/library/lisp_frontend_design_delta/types.orc \
  workflows/library/lisp_frontend_design_delta/projections.orc \
  workflows/library/lisp_frontend_design_delta/bootstrap.orc
```

Expected: no matches on the ordinary drain/work-item route.

- [ ] **Step 4: Collect-only if any test names or locations changed**

If you add or rename tests while reconciling the checked inputs, run:

```bash
pytest tests/test_workflow_lisp_build_artifacts.py --collect-only -q
pytest tests/test_workflow_lisp_transition_authoring.py --collect-only -q
pytest tests/test_workflow_lisp_source_map.py --collect-only -q
```

Expected: collection succeeds cleanly.

## Completion Criteria

This slice is complete only when all of the following are true:

- the transition-authoring suite and source-map suite are green without reopening the prior source/runtime defect;
- the checked `boundary_authority.json` and `value_flow_census.json` inputs describe only live compiled rows for the parent-drain route;
- the checked `consumer_rendering_census.json` input describes only live C0 consumer rows and contains no illegal non-entry entry-publication row;
- the focused build-artifact guards for boundary authority, value-flow census, and transition authoring all pass;
- the focused build-artifact guards for consumer rendering, rendering cleanup, and entry publication all pass;
- the target compile entrypoint succeeds with fail-closed gates still active;
- the preserved private-context and work-item feasibility guards stay green; and
- the ordinary route still contains no public `run_state_path` carrier.

If fresh evidence shows a new first failing source/runtime defect instead of stale checked rows, stop and reopen the architecture rather than forcing a manifest-only repair.
