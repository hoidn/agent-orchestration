# Stdlib Backlog-Drain Callable-Child Owner Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees for this repository. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute only the selected callable-child owner-boundary gap contract: prove the promoted-route imported and same-file `backlog-drain` surfaces lower through one generated `std/drain::backlog-drain` child that owns the loop, returns typed `DrainResult`, and keeps terminal effects separate from value return.

**Architecture:** Treat the gap architecture, shared owner-lane ledger, and recovered work-item context as the authority chain. The owner-boundary slice is implemented only in the frontend/lowering/stdlib surfaces that control authored head resolution, WCC/schema-2 route admission, generated child emission, terminal responsibility split, provenance, and runtime execution. The downstream design-delta transition-authoring manifest failure is not this gap's mechanism and must be recorded only as post-slice classification evidence, never as a blocking implementation task for this work item. What this makes harder later: downstream lanes must carry their own direct-input cleanup instead of piggybacking on the owner-boundary gap, so follow-on work may require a separate selection even when the first visible red gate appears immediately after this slice.

**Tech Stack:** Python 3, Workflow Lisp `.orc`, WCC/schema-2 lowering, shared validation, executable/runtime workflow execution, `pytest`, and `python -m orchestrator compile` for non-blocking downstream classification only.

---

## Authority And Current Checkout Evidence

Use these authorities in order:

1. `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-runtime-native-drain-stdlib-backlog-drain-callable-child-owner-boundary/implementation_architecture.md`
2. `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R40/drain/iterations/10/recovered-gap/recovered-work-item-context.md`
3. `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md` (Sections 2.1 and 2.1.1)
4. `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (Sections 9.1, 12.2, 13.4)
5. `docs/design/workflow_lisp_frontend_specification.md`
6. `docs/design/workflow_command_adapter_contract.md`
7. Fresh command output from the current checkout

Fresh output from this checkout already shows the scope boundary that this plan must preserve:

- `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q` -> `61 passed in 12.79s`
- `python -m pytest tests/test_workflow_lisp_transition_authoring.py -q` -> `3 failed, 10 passed`
- `python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json` -> `[transition_authoring_invalid] ... stale_allowed_origins`

Current-checkout surface audit also shows the mechanism family the architecture names is present in the expected code surfaces:

- `orchestrator/workflow_lisp/drain_stdlib.py` defines `BacklogDrainSpec.preserve_owner_boundary`
- `orchestrator/workflow_lisp/expressions.py` and `orchestrator/workflow_lisp/form_registry.py` route `backlog-drain-callable-boundary` to the shared intrinsic shape
- `orchestrator/workflow_lisp/lowering/phase_drain.py` owns the promoted-route owner-boundary gate and generated `std/drain::backlog-drain` child
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc` contains `consume-drain-terminal-effects`
- `tests/test_workflow_lisp_drain_stdlib.py` contains the imported-route, same-file, provenance, specialization, terminal-split, and negative hidden-bridge proofs the architecture names

This means the plan is executable in the current checkout without inventing a missing route or absent artifact. The plan must therefore stay on owner-boundary verification and repair, not switch lanes to downstream manifest/test cleanup.

## Scope And Non-Scope

In scope:

- promoted-route callable-child lowering for imported and same-file `backlog-drain`
- authored-head resolution for `backlog-drain` and `backlog-drain-callable-boundary`
- WCC/schema-2 admission of the owner-boundary route
- generation and specialization identity of the lowered `std/drain::backlog-drain` child
- terminal responsibility split between typed value return and declared effects
- source-map/provenance preservation and hidden-compatibility negative coverage that this slice owns
- generic runtime or lowering repairs only if fresh in-scope acceptance failures prove the emitted owner-boundary shape still lacks shared substrate support

Out of scope:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `tests/test_workflow_lisp_transition_authoring.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- design-delta compile-gate cleanup, stale allowlist repair, or transition-authoring report matcher changes
- manifest, conformance, parity, summary, inventory, or status-label work that is not a direct owner-boundary runtime requirement
- reintroducing public `DrainResult.run-state` or compatibility-bundle rereads
- widening the approved route to legacy schema-1 or family-local wrapper repairs

If a command in this plan surfaces only the already-known `transition_authoring_invalid: stale_allowed_origins` failure after the owner-boundary acceptance surface is green, stop and route that as the first downstream blocker. Do not spend this gap fixing it.

## Working Tree Safety

This repository may already be dirty. Do not rely on whole-file staging.

Use path-scoped review only:

- before editing a touched file, inspect `git diff -- <path>`
- after each task, inspect `git diff -- <paths>` and `git diff --stat -- <paths>`
- if a later user-requested commit is needed, stage only owned hunks after verifying `git diff --cached`

## File Map

Primary implementation surfaces for this gap:

- `orchestrator/workflow_lisp/drain_stdlib.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/wcc/route.py`
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`

Primary acceptance and regression surfaces:

- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_wcc_m4.py`
- `tests/test_workflow_lisp_value_flow_census.py`
- `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_lisp_frontend_autonomous_drain_runtime.py`

Read-only downstream classification surfaces:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `tests/test_workflow_lisp_transition_authoring.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `orchestrator/workflow_lisp/transition_authoring.py`
- `orchestrator/workflow_lisp/build.py`

## Task 1: Reconfirm The Selected Owner-Boundary Acceptance Surface

**Files:**

- Read: `tests/test_workflow_lisp_drain_stdlib.py`
- Read: `orchestrator/workflow_lisp/drain_stdlib.py`
- Read: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Read: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`

- [ ] **Step 1: Re-run the primary owner-boundary acceptance module**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected: green. In the current checkout this is `61 passed`. If this stays green, treat it as proof that the selected mechanism family is already landed and do not invent additional source work under this gap.

- [ ] **Step 2: If Step 1 regresses, localize the failure to the architecture-owned mechanism**

Run only if Step 1 fails:

```bash
python -m pytest \
  tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_preserves_imported_backlog_drain_as_callable_boundary \
  tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_target_contract_routes_default_imported_surface_through_callable_child \
  tests/test_workflow_lisp_drain_stdlib.py::test_same_file_callable_boundary_preserves_generated_backlog_drain_owner_lane \
  tests/test_workflow_lisp_drain_stdlib.py::test_backlog_drain_target_contract_separates_terminal_value_from_effect_consumers \
  tests/test_workflow_lisp_drain_stdlib.py::test_compile_stage3_module_rejects_hidden_compatibility_bridge_public_run_item_fixture \
  -q
```

Use the first failure to classify the repair:

- authored-spec or head-resolution failure -> `drain_stdlib.py`, `expressions.py`, `form_registry.py`
- promoted-route admission or generated-child emission failure -> `phase_drain.py`, `wcc/route.py`, `wcc/defunctionalize.py`
- terminal value/effect split failure -> `phase_drain.py`, `std/drain.orc`
- runtime execution or generic emitted-shape support failure -> shared runtime substrate only if the emitted owner-boundary shape is otherwise correct

- [ ] **Step 3: Reconfirm the neighboring shared-lane regressions the recovered progress report used**

Run:

```bash
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_resource_stdlib.py -q
python -m pytest tests/test_workflow_lisp_value_flow_census.py tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
```

Expected: green. These are still in-scope because they guard the shared promoted-route/runtime substrate that the owner-boundary slice depends on. They are not downstream design-delta compile-gate work.

## Task 2: Repair Only The Owner-Boundary Mechanism If Fresh In-Scope Evidence Demands It

**Files:**

- Modify only the architecture-owned surface implicated by Task 1
- Test: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Make the smallest repair consistent with the architecture**

Allowed repair shapes:

- restore `preserve_owner_boundary` authored-spec plumbing without widening public callable contracts
- restore `backlog-drain` / `backlog-drain-callable-boundary` routing onto the shared intrinsic lowering path
- restore WCC/schema-2 route admission for the bounded `BacklogDrainExpr` owner-boundary shape
- restore generated `std/drain::backlog-drain` child emission, specialization reuse, source-map provenance, or parent-call lowering
- restore the terminal responsibility split so result artifacts are returned before declared transition/view effects
- restore a generic shared runtime/lowering substrate requirement only if the emitted owner-boundary shape is already architecture-correct and the substrate is the remaining blocker

- [ ] **Step 2: Keep the route and contract boundaries closed**

Forbidden repair shapes:

- do not edit transition-authoring manifests, report code, or build-artifact expectations
- do not broaden the owner-boundary route to legacy schema-1
- do not reintroduce public `run-state` carrier fields, compatibility rereads, or family-local wrapper workflows
- do not add workflow-family or module-name special cases outside the architecture's shared route ownership
- do not weaken hidden-bridge, provenance, or typed-return checks just to make a red test disappear

- [ ] **Step 3: Review only the owner-boundary diff before rerunning tests**

Run:

```bash
git diff -- orchestrator/workflow_lisp/drain_stdlib.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow_lisp/wcc/route.py orchestrator/workflow_lisp/wcc/defunctionalize.py orchestrator/workflow_lisp/stdlib_modules/std/drain.orc tests/test_workflow_lisp_drain_stdlib.py
git diff --stat -- orchestrator/workflow_lisp/drain_stdlib.py orchestrator/workflow_lisp/expressions.py orchestrator/workflow_lisp/form_registry.py orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow_lisp/wcc/route.py orchestrator/workflow_lisp/wcc/defunctionalize.py orchestrator/workflow_lisp/stdlib_modules/std/drain.orc tests/test_workflow_lisp_drain_stdlib.py
```

Expected: only owner-boundary mechanism and proof changes appear.

## Task 3: Re-Run In-Scope Acceptance To Closure

**Files:**

- Test: `tests/test_workflow_lisp_drain_stdlib.py`
- Test: `tests/test_workflow_lisp_wcc_m4.py`
- Test: `tests/test_workflow_lisp_value_flow_census.py`
- Test: `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- Test: `tests/test_workflow_lisp_resource_stdlib.py`
- Test: `tests/test_lisp_frontend_autonomous_drain_runtime.py`

- [ ] **Step 1: Run collection only if any owner-boundary test name changed**

Run only if tests were added or renamed:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py --collect-only -q
```

- [ ] **Step 2: Re-run the primary acceptance suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected: green.

- [ ] **Step 3: Re-run the supporting promoted-route and runtime checks**

Run:

```bash
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_resource_stdlib.py -q
python -m pytest tests/test_workflow_lisp_value_flow_census.py tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q
```

Expected: green.

- [ ] **Step 4: Accept a no-edit closure when the suite is already green**

If Tasks 1 and 3 are green without source edits, that is valid completion for this gap. Record that the selected owner-boundary contract is satisfied in the current checkout and do not manufacture extra implementation work from downstream red gates.

## Task 4: Record The First Downstream Blocker Without Re-Scoping This Gap

**Files:**

- Read only: `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- Read only: `tests/test_workflow_lisp_transition_authoring.py`

- [ ] **Step 1: Re-run the downstream compile gate only after Task 3 is green**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected in the current checkout: the first downstream blocker remains `[transition_authoring_invalid] ... stale_allowed_origins`.

- [ ] **Step 2: Stop at the first downstream blocker and route it honestly**

If Step 1 still fails on transition-authoring stale allowlist rows, record that exact diagnostic as an out-of-scope direct-input validation failure and stop. Do not touch:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `tests/test_workflow_lisp_transition_authoring.py`
- `orchestrator/workflow_lisp/transition_authoring.py`
- `orchestrator/workflow_lisp/build.py`

If a different first downstream failure appears, record that first diagnostic exactly and route it based on the owning architecture. Do not continue past first-failure classification under this gap.

## Completion Criteria

This plan is complete when fresh output shows:

- `python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q` is green
- `python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_resource_stdlib.py -q` is green
- `python -m pytest tests/test_workflow_lisp_value_flow_census.py tests/test_workflow_lisp_resume_plumbing_retirement.py -q` is green
- `python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py::test_lisp_frontend_drain_design_gap_runtime_smoke -q` is green
- any required source edits stay within the owner-boundary mechanism surfaces named in this plan
- a persisted downstream `transition_authoring_invalid: stale_allowed_origins` result is treated only as post-slice blocker classification, not as an incomplete owner-boundary implementation

This plan is not complete when:

- success depends on editing transition-authoring manifests/tests or build-report code
- success depends on clearing the design-delta compile gate
- success depends on reintroducing retired public run-state carriers or compatibility rereads
- success depends on broadening the approved route beyond the promoted WCC/schema-2 owner-boundary slice
