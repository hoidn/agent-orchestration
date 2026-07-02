# Shared EMPTY Run-State Retirement And Reference-Family Evidence Alignment Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees for this repository.

**Goal:** Retire the remaining shared `std/drain::SelectionResult.EMPTY.run-state` compatibility-carrier contract and align Design Delta reference-family evidence so the carrier-free route is the checked source of truth across shared validation, Design Delta regression coverage, and build/report artifacts.

**Architecture:** Start by locking the actual causal split in the current checkout: the shared owner lane still requires `EMPTY.run-state` in builtin stdlib and exact workflow-ref validation, while higher-level Design Delta checks already assume a carrier-free route and the build/report lane still depends on stale reference-family inputs or bridge classifications. Tighten the proving tests first, then retire the shared `EMPTY` field and exact validator requirement, and only touch build/report/reference-family plumbing generically if carrier-free `EMPTY` exposes a real shared evidence-resolution defect rather than a stale Design Delta fixture.

What this makes harder later: any legacy consumer that still wants `run_state_path`, old drain summaries, or bridge-shaped retirement evidence will need an explicit compatibility or historical-evidence lane with a named owner. It will no longer be able to piggyback on shared `SelectionResult.EMPTY` or on stale reference-family constants.

**Tech Stack:** Workflow Lisp stdlib and workflow-ref validation under `orchestrator/workflow_lisp/`, Design Delta `.orc` modules and checked evidence manifests under `workflows/library/lisp_frontend_design_delta/` and `workflows/examples/inputs/workflow_lisp_migrations/`, and focused `pytest` compile/build/smoke lanes that exercise shared stdlib, Design Delta feasibility, and build-artifact/report generation.

---

## Fixed Inputs

Treat these as authoritative for execution:

- `docs/index.md`
- `docs/design/README.md`
- `docs/capability_status_matrix.md`
- `docs/steering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-shared-empty-run-state-retirement-and-reference-family-evidence-alignment/implementation_architecture.md`
- `state/workflow_lisp/calls/20260701T093008Z-31cpte/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.desig_f289187df7d2/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`

## Current Checkout Baseline

Use the live checkout as the starting point, not the generated gap text alone.

Observed on July 1, 2026:

- Shared owner-lane code is still stale:
  - `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` still declares:
    - `SelectionResult.EMPTY (run-state StateExisting)`
  - `orchestrator/workflow_lisp/typecheck_calls.py` still requires:
    - exact `EMPTY.run-state`
    - exact `EMPTY` field set `("run-state",)`
- Focused shared and family regression checks already include carrier-free expectations:
  - `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "selection_result or selector_empty or target_contract_exposes_selector_blocked_variant or contract_inventory_matches_promoted_stdlib_route" -q`
    - result: `4 passed, 52 deselected`
  - `python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "removes_run_state_from_authored_loop_state or removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge or shared_stdlib_empty_variant_no_longer_carries_run_state" -q`
    - result: `2 passed, 91 deselected`
- The build/report lane is not yet a reliable acceptance gate for this slice without alignment:
  - `python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "checked_inputs_keep_work_item_run_state_retirement_row or boundary_authority_report_keeps_live_work_item_run_state_bridge_visible or records_drain_run_state_bridge_as_checked_compatibility or default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only" -q`
    - result: `3 failed, 1 passed`
    - failure class: `reference_family_conformance_invalid`
    - first missing input: `artifacts/work/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/drain-summary.json`
- `tests/test_workflow_lisp_build_artifacts.py` already has helper hooks for patched reference-family inputs (`run_state_path`, `drain_summary_path`, `implementation_architecture_root`, parity paths, and related monkeypatches), so do not assume the right fix is a hard-coded new constant until the stale-input owner is proven.

## Causal Failure

The earliest functional failure is not in runtime-native drain state, terminal effects, or Design Delta-only authoring. It is a split shared contract:

1. The shared builtin selector contract still says `SelectionResult.EMPTY` carries a state relpath.
2. Exact workflow-ref validation still enforces that field for `SelectionResult` and `std/drain::SelectionResult`.
3. Downstream Design Delta tests and checked evidence have already started retiring the carrier, so the owner lane and the evidence lane disagree.
4. The build/report lane currently mixes two separate problems:
   - stale bridge/evidence expectations for `work_item.loop.run_state_path` and `transitions.resource.drain_run_state`; and
   - stale or missing reference-family input routing, which can fail before the targeted row assertions even execute.

Implementation must fix the shared owner lane first, then align the evidence lane to that owner lane, and only widen into build/report path resolution if the stale reference-family root is part of the generic checked-evidence mechanism rather than a local test helper assumption.

## Scope Guards

- Do not replace `EMPTY.run-state` with another one-field carrier.
- Do not add Design Delta-specific compiler, validator, or lowerer allowlists.
- Do not widen selector arity or payload shapes beyond the accepted `EMPTY`, `GAP`, `SELECTED`, and `BLOCKED` contract.
- Do not reread reports, pointer files, summaries, stdout JSON, or debug YAML as state authority.
- Do not treat runtime-native `drain-run-state` audit/state artifacts as justification for keeping a shared relpath carrier.
- Do not broaden this slice into unrelated rendering-ergonomics or publication cleanup unless the failing proof shows the checked-evidence resolver itself is stale.
- If the reference-family failure is caused only by stale test helper inputs, keep the repair in the focused helper/test layer instead of changing shared build behavior.

## File Map

Primary owner-lane surfaces:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/typecheck_calls.py`
- `tests/test_workflow_lisp_drain_stdlib.py`

Primary Design Delta and evidence-alignment surfaces:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`

Conditional shared surfaces only if carrier-free `EMPTY` exposes a real shared defect:

- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/reference_family_conformance.py`
- `orchestrator/workflow_lisp/resume_plumbing_retirement.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`

Conditional Design Delta source surfaces only if shared retirement exposes a real family consumer dependency:

- `workflows/library/lisp_frontend_design_delta/*.orc`
- mirrored fixtures under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/`

## Tasks

### Task 1: Reproduce And Classify The Two Failure Lanes

**Files:**

- Read first:
  - `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
  - `orchestrator/workflow_lisp/typecheck_calls.py`
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  - `tests/test_workflow_lisp_build_artifacts.py`

- [ ] **Step 1: Re-run the focused owner-lane and evidence-lane commands**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "selection_result or selector_empty or contract_inventory_matches_promoted_stdlib_route" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "removes_run_state_from_authored_loop_state or removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge or shared_stdlib_empty_variant_no_longer_carries_run_state" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "checked_inputs_keep_work_item_run_state_retirement_row or boundary_authority_report_keeps_live_work_item_run_state_bridge_visible or records_drain_run_state_bridge_as_checked_compatibility or default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only" -q
```

Expected:

- shared stdlib/typecheck assertions expose the still-live `EMPTY.run-state` owner lane;
- family feasibility remains narrow and does not by itself prove the shared builtin contract is retired; and
- build-artifact failures clearly separate stale reference-family input loading from stale bridge classification.

- [ ] **Step 2: Decide whether the reference-family input failure is shared behavior or a stale focused helper**

Inspect and classify:

- `tests/test_workflow_lisp_build_artifacts.py`
  - `_build_design_delta_parent_drain(...)`
  - `_aligned_reference_family_drain_summary(...)`
  - any helper already capable of monkeypatching `REFERENCE_FAMILY_*` paths
- `orchestrator/workflow_lisp/build.py`
  - `REFERENCE_FAMILY_*` constants
- `orchestrator/workflow_lisp/reference_family_conformance.py`
  - required input loading and failure conditions

Decision rule:

- if the stale path is only in the focused test/helper layer, fix the helper and keep shared build logic unchanged;
- if the stale path is baked into shared checked-evidence resolution for the active family, repair that path generically so checked reference-family evidence resolves from the current owned family inputs rather than a retired hard-coded root, and mark the shared-resolver verification branch active for Task 5.

- [ ] **Step 3: If any tests are added or renamed later, re-run collect-only before continuing**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
```

### Task 2: Tighten The Proving Tests To The Carrier-Free Shared Contract

**Files:**

- Modify:
  - `tests/test_workflow_lisp_drain_stdlib.py`
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
  - `tests/test_workflow_lisp_build_artifacts.py`

- Modify only if broader evidence assertions need synchronization:
  - `tests/test_workflow_lisp_migration_parity.py`

- [ ] **Step 1: Replace stale shared-stdlib EMPTY expectations**

Required changes in `tests/test_workflow_lisp_drain_stdlib.py`:

- stop treating `{"variant": "EMPTY", "run-state": ...}` as the positive shared `SelectionResult.EMPTY` shape;
- replace `test_workflow_ref_resolution_rejects_selector_empty_run_state_omission` with the post-retirement rule:
  - shared `EMPTY` with no fields is accepted;
  - extra `EMPTY` fields are rejected;
- preserve exact typed checks for:
  - `GAP.gap`
  - `SELECTED.selection`
  - `BLOCKED.reason`

- [ ] **Step 2: Make the Design Delta feasibility lane prove the shared retirement instead of only local carrier hiding**

Required changes in `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`:

- keep `test_design_delta_parent_drain_removes_run_state_from_authored_loop_state`;
- keep `test_design_delta_parent_drain_removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge`;
- add or tighten one focused assertion proving the imported shared `std/drain::SelectionResult.EMPTY` contract is now fieldless, not merely family-owned or hidden behind a non-shared alias;
- keep runtime-native drain-state smoke assertions separate from selector result transport.

- [ ] **Step 3: Retarget the build-artifact tests to the retired evidence model**

Required changes in `tests/test_workflow_lisp_build_artifacts.py`:

- keep `work_item.loop.run_state_path` absent from checked inputs and retirement decisions;
- keep `transitions.resource.drain_run_state` visible only as retired or runtime-native evidence, not live compatibility;
- ensure the focused tests fail for stale bridge classification, stale manifest fingerprints, or stale owner-route claims, not for a missing reference-family summary file unrelated to the targeted row semantics.

### Task 3: Retire Shared `EMPTY.run-state` In The Owner Lane

**Files:**

- Modify:
  - `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
  - `orchestrator/workflow_lisp/typecheck_calls.py`
- Modify only if the carrier-free shared route exposes a real shared lowering defect:
  - `orchestrator/workflow_lisp/lowering/phase_drain.py`

- [ ] **Step 1: Remove the shared field from builtin stdlib**

Required edit in `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`:

- change `SelectionResult.EMPTY` from:
  - `(EMPTY (run-state StateExisting))`
- to:
  - `(EMPTY)`

Keep unchanged:

- the four selector variants `EMPTY`, `GAP`, `SELECTED`, `BLOCKED`;
- typed `GapPayload` and `SelectionPayload`;
- typed `DrainResult` projection and runtime-native `drain-run-state` transition effects.

- [ ] **Step 2: Retire exact workflow-ref enforcement of `EMPTY.run-state`**

Required edit in `orchestrator/workflow_lisp/typecheck_calls.py`:

- remove the exact `require_union_variant_field(... "EMPTY", "run-state", ...)` requirement for shared `SelectionResult`;
- replace `expected_fields=("run-state",)` with `expected_fields=()` for `EMPTY`;
- preserve the exact structural checks for `GAP`, `SELECTED`, and `BLOCKED`.

- [ ] **Step 3: Only widen into shared lowering if the fieldless shared union breaks a generic route**

Allowed follow-up only if the updated tests prove it is necessary:

- repair imported stdlib composition, branch reprojection, source-map lineage, or runtime-plan projection generically;
- do not add any branch keyed to Design Delta workflow names, module names, or caller identity.

### Task 4: Align Design Delta Evidence And Reference-Family Inputs To The Retired Contract

**Files:**

- Modify:
  - `tests/test_workflow_lisp_build_artifacts.py`
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.boundary_authority.json`
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`
  - `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.value_flow_census.json`

- Modify only if the stale reference-family root is a shared resolver bug:
  - `orchestrator/workflow_lisp/build.py`
  - `orchestrator/workflow_lisp/reference_family_conformance.py`

- Modify only if the shared retirement exposes a real consumer dependency in the Design Delta source:
  - `workflows/library/lisp_frontend_design_delta/*.orc`
  - mirrored runtime fixtures under `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/lisp_frontend_design_delta/`

- [ ] **Step 1: Refresh the checked evidence rows to the carrier-free route**

Update the checked JSON/manifests so they describe:

- no live `work_item.loop.run_state_path` row;
- no live `drain.loop.run_state_path` or `drain.output.return_run_state` transport claim;
- `transitions.resource.drain_run_state` as retired or runtime-native evidence only;
- no stale imported-finalizer owner-route claim used to justify a compatibility bridge that no longer exists.

- [ ] **Step 2: Restore a usable reference-family conformance input lane**

Preferred repair order:

1. If focused tests can patch aligned inputs from the current owned family root, do that in `tests/test_workflow_lisp_build_artifacts.py`.
2. If shared build/report code is the stale owner, replace the hard-coded path resolution generically so the active family uses the correct checked reference-family root and preserve the dedicated conformance-profile / reject-path behavior already covered in `tests/test_workflow_lisp_build_artifacts.py`.

Do not solve this by copying arbitrary files into the missing old root or by weakening the conformance profile's required-input checks.

- [ ] **Step 3: Update Design Delta source only if the retired shared contract exposes a true family consumer**

If a real `.orc` consumer still assumes `EMPTY.run-state`, remove that dependency from ordinary workflow dataflow and mirrored fixtures. Do not reintroduce a hidden bridge just to keep the family green.

### Task 5: Verification Ladder

**Files:**

- No new files unless a proving fixture must be added.

- [ ] **Step 1: Re-run the focused shared and family proof set**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "selection_result or selector_empty or contract_inventory_matches_promoted_stdlib_route" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "removes_run_state_from_authored_loop_state or removes_run_state_from_work_item_authored_signatures_while_preserving_private_bridge or shared_stdlib_empty_variant_no_longer_carries_run_state" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "checked_inputs_keep_work_item_run_state_retirement_row or boundary_authority_report_keeps_live_work_item_run_state_bridge_visible or records_drain_run_state_bridge_as_checked_compatibility or default_resume_report_marks_live_run_state_bridges_blocked_or_historical_only" -q
```

- [ ] **Step 2: If Task 4 touched the shared resolver surfaces, run the dedicated reference-family conformance suite**

Trigger:

- required when either `orchestrator/workflow_lisp/build.py` or `orchestrator/workflow_lisp/reference_family_conformance.py` changed;
- optional when Task 4 stayed inside focused test/helper inputs.

Run:

```bash
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "reference_family_conformance_profile or rejects_reference_family_completed_gap_summary_mismatch or rejects_reference_family_completed_gap_artifact_missing_when_architecture_index_omits_selected_gap or rejects_reference_family_parity_surface_mismatch or rejects_reference_family_invalid_parity_report or rejects_reference_family_malformed_parity_markdown" -q
```

Expected:

- the conformance profile still resolves the current family inputs correctly;
- completed-gap evidence validation still rejects mismatched or missing checked inputs; and
- parity input validation still rejects malformed or mismatched parity evidence after the resolver repair.

- [ ] **Step 3: Re-run collect-only if any test names changed**

Run:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py -q
```

- [ ] **Step 4: Run one real compile/smoke lane for the affected workflow family**

Run at least one of:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "shared_stdlib_empty_variant_no_longer_carries_run_state or smokes_selector_blocked_path" -q
```

Diagnostic-only if needed:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Treat a remaining `rendering_ergonomics_consumer_slot_missing` failure as out of scope unless this slice actually changed the rendering-ergonomics checked inputs.

## Acceptance

This work item is complete when all of the following are true:

- shared `std/drain::SelectionResult.EMPTY` is fieldless;
- exact workflow-ref validation accepts the fieldless shared `EMPTY` while preserving the fixed `GAP`, `SELECTED`, and `BLOCKED` payload contract;
- no Design Delta feasibility, build-artifact, or checked-manifest lane still treats `run_state_path` as the transport for shared `EMPTY`;
- runtime-native `drain-run-state` evidence remains visible only as typed transition/audit state, not as justification for a shared compatibility carrier;
- reference-family conformance/build tests execute against aligned current inputs and fail only for real evidence mismatches; and
- if the shared-resolver branch was taken, the dedicated reference-family conformance profile and reject-path tests still pass against the repaired generic resolver; and
- no family-specific validator, lowerer, wrapper, or compatibility-carrier workaround was introduced.
