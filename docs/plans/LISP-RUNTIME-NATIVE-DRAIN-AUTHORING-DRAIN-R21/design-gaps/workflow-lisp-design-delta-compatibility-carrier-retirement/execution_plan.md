# Design Delta Compatibility-Carrier Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Do not create a git worktree; this repo's `AGENTS.md` forbids worktrees.

**Goal:** Retire the remaining `run-state` compatibility carrier from the promoted Design Delta drain route by removing dead `std/drain` carrier fields, shared lowering plumbing, and the bridge-backed family `drain-run-state` lane, while restoring the currently red runtime-proof fixtures and keeping all existing gates fail-closed.

**Architecture:** The causal failure is already identified by the accepted gap architecture: the runtime proof fixtures call `emit-drain-status-transition-audit` in the intended carrier-free shape, but the surviving bridge wrapper still requires `run_state_path`, and that wrapper exists only because `std/drain` plus shared `backlog-drain` lowering still thread a dead `run-state` carrier. Fix the source of truth first: remove the carrier from `std/drain`, remove the generic lowering plumbing that only feeds it, collapse the family bridge/native duplication onto the surviving state-layout-backed runtime-native lane, and only then realign manifests, parity rows, fixtures, and tests to the new carrier-free contract. This preserves the generic owner split from the target design and avoids selected-case exceptions.

**Tech Stack:** Workflow Lisp `.orc` modules, shared WCC/schema-2 lowering, compile/build gates, transition-authoring and parity manifests, and focused `python -m orchestrator compile` plus `pytest`

---

## Governing Inputs

Implement strictly against these authorities:

- `docs/index.md`
- `docs/design/README.md`
- `docs/steering.md`
- `docs/work_definition_model.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN-R21/design-gaps/workflow-lisp-design-delta-compatibility-carrier-retirement/implementation_architecture.md`
- `state/workflow_lisp/calls/20260706T043621Z-6higvw/root.drain_lisp_frontend_work_4.lisp_frontend_drain_iteration.route_selection.desig_2c604e1d1c99/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`
- `state/workflow_lisp/calls/20260706T043621Z-6higvw/root.drain_lisp_frontend_work_4.lisp_frontend_drain_iteration.route_selection.desig_2c604e1d1c99/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/check_commands.json`

Target-design clauses that bind this slice:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:718` Section 12.1 requires compatibility bridges to be deleted, isolated at a declared public/legacy boundary, or replaced by typed composition.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:754` Section 12.2 requires phase/drain behavior to move into ordinary stdlib/family `.orc` ownership rather than family-specific compiler assumptions.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:824` Section 13.4 requires source/runtime behavior repair before incidental fixture maintenance and requires the real promoted route to stay runnable.
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md:922` Section 15 requires internal compatibility carriers to disappear from ordinary stdlib child-call composition unless a live consumer forces an isolated declared boundary.

## Scope Guards

- Keep the fix generic where behavior is shared: no `lisp_frontend_design_delta`, drain-family, or transition-name special cases in shared lowering/compiler code.
- Do not weaken transition-authoring, parity, resume-plumbing, runtime-proof, or deny-guard validation to make retirement appear green.
- Do not reintroduce surrogate `run-state` values, placeholder paths, or bridge aliases under new names.
- Do not change `std_drain_backlog_drain__normalize_result__*` write-root identities, result-proc purity, terminal-effect ownership, backend kind, fail-closed behavior, audit projection, or idempotency on survivor transitions.
- Do not treat fixture refresh as the fix. The fix is source/runtime behavior repair; fixture and manifest updates follow only after the real lane changes.
- If a focused check proves a live consumer still needs one YAML-era run-state JSON write, isolate exactly that write at a declared legacy boundary per `workflow_command_adapter_contract.md`; otherwise remove the lane outright.
- Generic runtime/frontend `bridge` support and non-family checkpoint/resume `run_state_path` uses are out of scope.

## File Map

Primary source files:

- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/lowering/drain_terminal.py`
- `workflows/library/lisp_frontend_design_delta/transitions.orc`
- `workflows/library/lisp_frontend_design_delta/types.orc`
- `workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc`
- `workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc`

Checked contract and gate files:

- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.transition_authoring.json`
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.resume_plumbing_retirement.json`
- `workflows/examples/inputs/workflow_lisp_migrations/parity_targets.json`
- `orchestrator/workflow_lisp/resume_plumbing_retirement.py`

Likely test and fixture files:

- `tests/test_workflow_lisp_drain_stdlib.py`
- `tests/test_workflow_lisp_transition_authoring.py`
- `tests/test_workflow_lisp_resume_plumbing_retirement.py`
- `tests/test_workflow_lisp_view_dual_run.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_resource_stdlib.py`
- `tests/test_workflow_lisp_resource_transition_runtime.py`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/...` only if a focused failure proves mirror maintenance is required

Conditional shared surfaces if carrier removal exposes a hidden generic dependency:

- `orchestrator/workflow_lisp/typecheck_dispatch.py`
- `orchestrator/workflow_lisp/wcc/elaborate.py`
- `orchestrator/workflow_lisp/procedure_specialization.py`
- `orchestrator/workflow_lisp/lowering/core.py`
- `orchestrator/workflow_lisp/value_flow_census.py`

## Task 1: Reproduce The Current Frontier And Pin The Causal Failure

**Files:**
- Inspect: `implementation_architecture.md`, `work_item_context.md`, `std/drain.orc`, `phase_drain.py`, `drain_terminal.py`, `transitions.orc`
- Test: red and green commands from `check_commands.json`

- [ ] **Step 1: Reproduce the real compile gate**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected: exit `0` on the already-landed parent-drain compile route.

- [ ] **Step 2: Reproduce the red runtime-proof fixtures that justify this slice**

Run:

```bash
python -m pytest tests/test_workflow_lisp_view_dual_run.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "runtime_transition_fixture or runtime_view_fixture" -q
```

Expected: failures rooted in `workflow_signature_mismatch` because the fixtures already call `emit-drain-status-transition-audit` with only `:summary_path` while the wrapper still requires `run_state_path`.

- [ ] **Step 3: Reconfirm the currently green guardrails that must stay green**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_workflow_lisp_transition_authoring.py -q
python -m pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_resource_transition_runtime.py tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -q
```

Expected: all pass before edits, proving the current debt is mostly contract-shift work rather than a broadly broken runtime.

- [ ] **Step 4: Prove the carrier is dead, not merely inconvenient**

Run:

```bash
rg -n "run-state|run_state|RunStatePath|drain-run-state|state/drain-run-state.json" orchestrator/workflow_lisp/stdlib_modules/std/drain.orc orchestrator/workflow_lisp/lowering/phase_drain.py orchestrator/workflow_lisp/lowering/drain_terminal.py workflows/library/lisp_frontend_design_delta/transitions.orc workflows/library/lisp_frontend_design_delta/types.orc workflows/library/lisp_frontend_design_delta/projections.orc
```

Expected:

- `std/drain.orc` shows the threaded carrier fields/params
- `phase_drain.py` and `drain_terminal.py` show generic loop/terminal plumbing for that carrier
- `transitions.orc` shows the bridge-backed wrapper lane
- `projections.orc` and other live family consumers do not read the retired `run-state` fields

- [ ] **Step 5: Record the implementation decision point**

Document for the implementation session:

- root cause: the live source still models a dead `run-state` compatibility carrier, and the red fixtures are the first place that now reject that stale contract
- repair order: shared/source carrier removal first, proof fixtures and manifest/test realignment second

## Task 2: Retire The `std/drain` Carrier Contract

**Files:**
- Modify: `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Test: `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Remove carrier fields from the public stdlib type surface**

Edit `std/drain.orc` to remove `run-state` / `run_state` from:

- `DrainResult.EMPTY`
- `DrainResult.COMPLETED`
- all `DrainLoopTerminal` variants
- `DrainLoopState`

Also delete the now-unused `StateExisting` import if that is the last consumer.

- [ ] **Step 2: Remove carrier parameters from constructor helpers**

Edit `std/drain.orc` so these helpers no longer accept or forward `run-state`:

- `empty-drain-result-proc`
- `blocked-drain-result-proc`
- `completed-drain-result-proc`
- `finalize-drain-terminal`

Constraint: helpers remain pure constructors with `:effects ()`; do not move terminal effects into them.

- [ ] **Step 3: Tighten tests to the carrier-free contract**

Update `tests/test_workflow_lisp_drain_stdlib.py` to assert:

- the retired fields are absent from exported result/terminal shapes
- custom unions or workflows that try to reintroduce `run-state` still fail
- no characterization assertion depends on the retired seed path or carrier field names

If test fixtures encode old shapes, refresh only the minimal ones needed by this module.

- [ ] **Step 4: Run the narrowest stdlib check first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected: pass against the new carrier-free contract before touching shared lowering or family transition wrappers.

## Task 3: Remove The Shared `backlog-drain` Carrier Plumbing

**Files:**
- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`, `orchestrator/workflow_lisp/lowering/drain_terminal.py`
- Conditional modify: `typecheck_dispatch.py`, `wcc/elaborate.py`, `procedure_specialization.py`, `lowering/core.py`
- Test: compile entrypoint plus `tests/test_workflow_lisp_drain_stdlib.py`

- [ ] **Step 1: Delete the dead accumulator and seed literal**

Remove generic lowering artifacts that exist only to satisfy the retired `std/drain` fields:

- `acc__run-state`
- `terminal__run-state`
- `return__run-state`
- the literal seed `state/drain-run-state.json`

Do this as generic contract-driven cleanup keyed to the retired field shape, not by family name.

- [ ] **Step 2: Preserve all surviving loop and terminal semantics**

Verify the lowering still emits:

- the same selection/gap/item/terminal control flow
- the same terminal responsibility split
- the same `std_drain_backlog_drain__normalize_result__*` identities

Do not change artifact/write-root names or fan-in logic except to remove the dead carrier.

- [ ] **Step 3: Repair any hidden shared dependency only if a focused compile proves it exists**

If the carrier removal exposes a structural assumption elsewhere, patch the smallest shared owner:

- type projection expecting the retired field
- WCC elaboration expecting a loop-state slot
- specialization/lowering code still projecting `return__run-state`

Constraint: the fix must stay generic and fail-closed. If a broader shared prerequisite appears, stop and report it rather than rethreading the carrier.

- [ ] **Step 4: Re-run the shared compile and stdlib gate**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
```

Expected:

- parent-drain compile still exits `0`
- `drain_stdlib` remains green with the carrier-free contract

## Task 4: Collapse The Family Bridge Lane Onto The Survivor Transition Route

**Files:**
- Modify: `workflows/library/lisp_frontend_design_delta/transitions.orc`, `workflows/library/lisp_frontend_design_delta/types.orc`
- Modify: `workflows/library/lisp_frontend_design_delta/runtime_transition_fixture.orc`, `workflows/library/lisp_frontend_design_delta/runtime_view_fixture.orc`
- Test: `tests/test_workflow_lisp_view_dual_run.py`, focused feasibility selectors

- [ ] **Step 1: Delete the bridge-backed resource and bridge-only transitions**

In `transitions.orc`, remove:

- the `drain-run-state` resource with `:backing (bridge run_state_path)`
- bridge-only transition declarations tied to that resource
- wrapper workflows/procs whose only purpose is carrying `RunStatePath`

Do not touch the survivor state-layout-backed runtime-native lane beyond choosing its surviving public identity.

- [ ] **Step 2: Remove `RunStatePath` if it no longer has a live family consumer**

In `types.orc`, retire `RunStatePath` only if a repo-wide focused search shows no remaining in-scope family consumer after wrapper deletion.

Run:

```bash
rg -n "RunStatePath|run_state_path" workflows/library/lisp_frontend_design_delta orchestrator/workflow_lisp tests
```

Expected: only out-of-scope resume/checkpoint uses may remain; ordinary family composition must not.

- [ ] **Step 3: Repoint runtime-proof fixtures to the survivor lane**

Update `runtime_transition_fixture.orc` and `runtime_view_fixture.orc` so they call the surviving state-layout-backed transition/view route directly, using the already-intended carrier-free `:summary_path` shape.

Constraint: the fixture repair must preserve what they prove today: runtime-native transition execution and view rendering, not a weaker wrapper smoke check.

- [ ] **Step 4: Handle the only allowed legacy fallback**

If a focused check proves one live consumer still needs a YAML-era run-state JSON write, isolate exactly that one write at a declared compatibility boundary with:

- owner
- consumer
- schema
- authority class
- retirement condition

Do not keep the bridge wrapper in ordinary composition as the fallback.

- [ ] **Step 5: Re-run the red fixtures first**

Run:

```bash
python -m pytest tests/test_workflow_lisp_view_dual_run.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "runtime_transition_fixture or runtime_view_fixture" -q
```

Expected: both are green, proving the causal signature mismatch is eliminated by real source repair.

## Task 5: Realign Checked Manifests, Parity Rows, And Retirement Evidence

**Files:**
- Modify: `design_delta_parent_drain.transition_authoring.json`
- Modify: `design_delta_parent_drain.resume_plumbing_retirement.json`
- Modify: `parity_targets.json`
- Modify: `orchestrator/workflow_lisp/resume_plumbing_retirement.py`
- Test: `tests/test_workflow_lisp_transition_authoring.py`, `tests/test_workflow_lisp_resume_plumbing_retirement.py`, `tests/test_workflow_lisp_migration_parity.py`

- [ ] **Step 1: Update transition-authoring rows to live identities only**

Remove or repoint rows that name retired bridge-wrapper identities. Preserve the standing gate rule that every row must match at least one compiled origin.

- [ ] **Step 2: Discharge the bridge row fail-closed**

Update the resume-plumbing retirement manifest and `resume_plumbing_retirement.py` so:

- `transitions.resource.drain_run_state` moves from tolerated debt to a checked discharged-retirement decision
- validation proves the bridge symbol is absent from `transitions.orc`
- evidence constants name only surviving transition identities

Forbidden: silently deleting the row or turning the validator permissive.

- [ ] **Step 3: Repoint parity rows without weakening parity**

Update `parity_targets.json` and any directly coupled parity assertions so rows formerly naming `record-terminal-work-item` or sibling bridge identities point at the surviving runtime-native lane while preserving the same public-behavior comparison.

- [ ] **Step 4: Add regression coverage for reintroduced carriers**

Extend tests so focused failures occur if any of these reappear:

- `run-state` / `run_state` fields in `std/drain`
- shared lowering seed `state/drain-run-state.json`
- bridge-backed family `drain-run-state` resource
- `RunStatePath` wrapper parameters in ordinary family composition

- [ ] **Step 5: Run the contract-gate suite**

Run:

```bash
python -m pytest tests/test_workflow_lisp_transition_authoring.py -q
python -m pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -q
```

Expected: all pass with only live identities and fail-closed retirement evidence.

## Task 6: Run Full Acceptance Verification And Refresh Only Necessary Mirrors

**Files:**
- Modify only if a focused failure requires it: `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/...`
- Verify: all commands from `check_commands.json`

- [ ] **Step 1: Run the full required acceptance suite from repo root**

Run:

```bash
python -m orchestrator compile workflows/library/lisp_frontend_design_delta/drain.orc --entry-workflow lisp_frontend_design_delta/drain::drain --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q
python -m pytest tests/test_workflow_lisp_transition_authoring.py -q
python -m pytest tests/test_workflow_lisp_resume_plumbing_retirement.py -q
python -m pytest tests/test_workflow_lisp_view_dual_run.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "runtime_transition_fixture or runtime_view_fixture" -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "selected_item_stdlib or parent_drain_build_and_execution_smoke" -q
python -m pytest tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_resource_transition_runtime.py tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -q
```

Expected: every command is green.

- [ ] **Step 2: Refresh mirrored fixtures only if a focused acceptance check still points at stale copies**

If a remaining failure comes only from a mirrored test fixture that still embeds retired carrier shapes, update the mirror after the live route is already green and rerun the narrow failing selector.

Forbidden: changing mirrors before the live route is fixed, or treating mirror refresh as acceptance on its own.

- [ ] **Step 3: Run `pytest --collect-only` if any test module or test name changed**

Run only if tests were added or renamed:

```bash
python -m pytest tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_transition_authoring.py tests/test_workflow_lisp_resume_plumbing_retirement.py tests/test_workflow_lisp_view_dual_run.py tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_migration_parity.py --collect-only -q
```

Expected: collection succeeds with the renamed or added tests present.

- [ ] **Step 4: Capture the acceptance summary against the plan**

Record:

- which carrier surfaces were deleted outright
- whether any isolated legacy boundary remained, and the proof that forced it
- the exact verification commands run
- any residual out-of-scope debt left untouched

## Completion Criteria

The plan is complete when implementation can prove all of the following without rediscovering scope:

- no `run-state` / `run_state` carrier remains in `std/drain` drain result lanes
- no generic `backlog-drain` lowering emits or seeds the retired carrier
- no bridge-backed family `drain-run-state` resource or `RunStatePath` wrapper remains in ordinary Design Delta composition
- runtime-proof fixtures and the focused feasibility lane are green again because the real source contract changed
- transition-authoring, resume-retirement, parity, and runtime-proof gates remain fail-closed and pass on the surviving identities
- any fixture refresh happened only as downstream maintenance after the live route was already repaired
