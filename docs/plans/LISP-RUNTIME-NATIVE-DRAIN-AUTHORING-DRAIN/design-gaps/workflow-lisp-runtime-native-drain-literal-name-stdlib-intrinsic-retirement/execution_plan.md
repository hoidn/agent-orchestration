# Workflow Lisp Runtime-Native Drain Literal-Name Stdlib Intrinsic Retirement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Do not create a git worktree; this repo's `AGENTS.md` explicitly forbids worktrees. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove promoted-route literal-head handling for `finalize-selected-item` and `backlog-drain` so imported `std/resource` and `std/drain` are the only promoted authoring routes, while explicit legacy characterization remains available only through a route-aware legacy elaboration lane and Design Delta G8 deletion evidence fails if either head survives in promoted compiler surfaces.

**Architecture:** Execute this slice test-first in three bounded phases. First tighten the promoted-route contract in focused stdlib/G8 tests so promoted lookup, promoted bare-form compilation, legacy characterization, and compatibility-tagged G8 evidence all have explicit expectations. Next add the missing route-aware elaboration plumbing that lets `lowering_route="legacy"` use a legacy-only form lookup path without sharing the promoted registry, then remove promoted registry/elaboration/lowering admission for the two heads and guard `phase_drain.py` accounting the same way. This keeps the work local to compiler/frontend evidence boundaries and preserves imported stdlib owner routes, but it makes future full deletion of legacy characterization slightly harder because the compatibility lane becomes an explicit maintained route instead of disappearing as an accident of promoted plumbing.

**Tech Stack:** Python Workflow Lisp compiler/build modules under `orchestrator/workflow_lisp/`, Workflow Lisp fixture modules under `tests/fixtures/workflow_lisp/`, Design Delta compile/build/parity evidence in `tests/test_workflow_lisp_*`, and integration coverage through the real Design Delta parent drain compile/build routes.

---

## Scope Lock

This plan owns only the selected retirement slice:

- add explicit lowering-route-aware form lookup / expression elaboration plumbing so bare intrinsic characterization can survive only on an explicit legacy route;
- remove promoted registry exposure for `finalize-selected-item` and `backlog-drain`;
- remove or explicitly legacy-guard promoted elaboration into `FinalizeSelectedItemExpr` and `BacklogDrainExpr`;
- remove or explicitly legacy-guard promoted lowering dispatch and intrinsic accounting for those expression classes, including the secondary accounting path in `phase_drain.py`;
- preserve the existing imported stdlib owner routes as the positive promoted evidence path;
- tighten Design Delta G8 deletion evidence so compatibility-tagged promoted specs for the two heads still fail the artifact; and
- keep legacy/bare intrinsic coverage only as explicit characterization on a legacy route.

This plan does **not** own:

- changing `std/drain::backlog-drain` semantics;
- changing `std/resource::finalize-selected-item` semantics;
- changing Design Delta `.orc` workflow source shape;
- changing command-boundary manifests or adapter certification rules;
- changing runtime-transition, Semantic IR, executable IR, source-map, pointer-authority, or provider-output contracts;
- broad workflow-family hook cleanup beyond the literal-head/G8 slice;
- updating `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`; or
- claiming YAML-primary promotion.

## Authority Set

Use these as the governing inputs while executing:

- `docs/index.md`
- `docs/steering.md`
- `docs/capability_status_matrix.md`
- `docs/design/README.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `state/workflow_lisp/calls/20260628T214607Z-4ji8qu/root.drain_lisp_frontend_work_0.lisp_frontend_drain_iteration.route_selection.done_7bad823c3106/lisp-frontend-design-delta-design-gap-architect-v214/de14bca20ef59f36.json/work_item_context.md`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/lowering/phase_resource.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/build.py`
- `orchestrator/workflow_lisp/migration_parity.py`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_migration_parity.py`
- `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`
- `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item_stdlib.orc`
- `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain_stdlib.orc`

## File Ownership Map

Inspect first:

- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/lowering/phase_resource.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/build.py`
- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- `tests/test_workflow_lisp_migration_parity.py`

Modify in this slice:

- `tests/test_workflow_lisp_stdlib_form_migration.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/form_registry.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/procedure_typecheck.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/functions.py`
- `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- `orchestrator/workflow_lisp/lowering/phase_drain.py`
- `orchestrator/workflow_lisp/build.py`

Modify only if focused tests prove the explicit legacy lane still depends on them:

- `orchestrator/workflow_lisp/lowering/phase_resource.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_migration_parity.py`
- comments or naming in `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
- comments or naming in `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`

Do not modify in this slice:

- `orchestrator/workflow_lisp/stdlib_modules/std/resource.orc`
- `orchestrator/workflow_lisp/stdlib_modules/std/drain.orc`
- Design Delta library workflows under `workflows/library/lisp_frontend_design_delta/`
- command-boundary manifests under `workflows/examples/inputs/workflow_lisp_migrations/`
- `state/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/progress_ledger.json`

## Task 1: Lock The Contract In Tests Before Touching Compiler Plumbing

**Files:**

- Modify: `tests/test_workflow_lisp_stdlib_form_migration.py`
- Inspect: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`
- Inspect: `tests/test_workflow_lisp_build_artifacts.py`
- Inspect: `tests/test_workflow_lisp_migration_parity.py`
- Inspect: `tests/fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc`
- Inspect: `tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc`

- [ ] **Step 1: Confirm the focused verification selectors still collect cleanly**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_stdlib_form_migration.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_migration_parity.py \
  -q
```

Expected:

- collection succeeds; and
- the touched verification modules are stable before adding the new slice coverage.

- [ ] **Step 2: Replace the stale promoted-registry expectation with the target contract**

Implementation requirements:

- in `tests/test_workflow_lisp_stdlib_form_migration.py`, stop asserting that promoted `get_form_spec("finalize-selected-item")` and `get_form_spec("backlog-drain")` return compatibility-only specs;
- replace that coverage with assertions that promoted lookup no longer exposes those two heads, while `with-phase` remains the only imported-only compatibility head on the promoted registry; and
- keep the intrinsic-accounting API test unchanged.

- [ ] **Step 3: Add explicit promoted-negative and legacy-positive coverage for bare literal heads**

Implementation requirements:

- use the existing bare-form fixtures or equivalent inline modules to prove default/promoted compilation of bare `finalize-selected-item` and bare `backlog-drain` fails without imported stdlib expansion;
- assert the failure cites the offending head and that intrinsic-lowering counts for that head remain `0` on the promoted route;
- preserve explicit `lowering_route="legacy"` coverage showing the same bare fixtures still compile and record one intrinsic hit; and
- do not create new promoted “valid” fixtures for the bare heads.

- [ ] **Step 4: Tighten fixture wording so the legacy lane is unmistakable**

Implementation requirements:

- keep the existing legacy-route tests that compile the two bare-form fixtures with `lowering_route="legacy"` and expect one intrinsic-accounting hit;
- if the fixture naming or comments still read like promoted-route evidence, tighten the wording so they are clearly marked as compatibility characterization only; and
- keep imported stdlib owner-route fixtures as the only promoted positive evidence.

- [ ] **Step 5: Run the stdlib-form module and confirm it fails only because implementation is still stale**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -q
```

Expected before implementation:

- the new promoted-registry and promoted-negative tests fail because the current checkout still admits the two heads on the promoted route; and
- the imported stdlib positive tests and explicit legacy characterization tests continue to pass.

## Task 2: Add Explicit Route-Aware Legacy Elaboration Plumbing

**Files:**

- Modify: `orchestrator/workflow_lisp/compiler.py`
- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify: `orchestrator/workflow_lisp/workflows.py`
- Modify: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify: `orchestrator/workflow_lisp/definitions.py`
- Modify: `orchestrator/workflow_lisp/functions.py`
- Inspect while editing: `tests/test_workflow_lisp_stdlib_form_migration.py`

- [ ] **Step 1: Thread lowering-route identity into the expression elaboration entrypoints**

Implementation requirements:

- identify the smallest existing compiler surface that already carries normalized `lowering_route` and thread that route into every `elaborate_expression(...)` callsite that can compile workflow, procedure, function, or transition expression bodies;
- prefer an explicit elaboration-mode or route parameter over new hidden globals;
- keep promoted/WCC-default behavior as the default path for non-legacy callers; and
- keep the change local to elaboration plumbing rather than widening downstream runtime or IR contracts.

- [ ] **Step 2: Split promoted form lookup from the explicit legacy-only lookup**

Implementation requirements:

- make the promoted lookup path the default `get_form_spec(...)` behavior;
- add a legacy-only lookup or equivalent resolver that explicit legacy elaboration can call for characterization fixtures;
- ensure the legacy resolver is reachable only when compilation was explicitly requested with `lowering_route="legacy"` or the equivalent schema-1 identity; and
- leave `with-phase` behavior unchanged because it remains the one imported-only compatibility head on the promoted registry.

- [ ] **Step 3: Re-run the explicit legacy selectors to prove the new plumbing preserves the compatibility lane**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_stdlib_form_migration.py -k "legacy_intrinsic_fixtures_use_compatibility_intrinsic_accounting or bare_with_phase_uses_compatibility_intrinsic_accounting" \
  -q
```

Expected:

- explicit legacy characterization still compiles and records one intrinsic hit for the legacy-only heads; and
- promoted-default failures may still remain until the next task removes the stale promoted admission path.

## Task 3: Retire Promoted Registry Exposure And Promoted Literal-Head Elaboration

**Files:**

- Modify: `orchestrator/workflow_lisp/form_registry.py`
- Modify: `orchestrator/workflow_lisp/expressions.py`
- Modify only if required by the new elaboration parameter wiring: `orchestrator/workflow_lisp/workflows.py`
- Modify only if required by the new elaboration parameter wiring: `orchestrator/workflow_lisp/procedure_typecheck.py`
- Modify only if required by the new elaboration parameter wiring: `orchestrator/workflow_lisp/definitions.py`
- Modify only if required by the new elaboration parameter wiring: `orchestrator/workflow_lisp/functions.py`
- Inspect while editing: `tests/test_workflow_lisp_stdlib_form_migration.py`

- [ ] **Step 1: Remove the two heads from promoted lookup**

Implementation requirements:

- make promoted `get_form_spec(...)` stop returning compiler-known metadata for `finalize-selected-item` and `backlog-drain`;
- prefer deleting those specs from the promoted `_FORM_SPECS` path entirely;
- keep any remaining compatibility metadata behind the explicit legacy-only lookup introduced in Task 2 instead of reusing the promoted registry; and
- leave `with-phase`, `resource-transition`, and other unrelated heads unchanged.

- [ ] **Step 2: Remove or legacy-guard literal-head elaboration**

Implementation requirements:

- remove or explicitly legacy-guard `_elaborate_finalize_selected_item(...)` and `_elaborate_backlog_drain(...)` from the promoted elaboration path;
- make bare promoted uses fail as missing imported stdlib ownership or unknown form rather than constructing `FinalizeSelectedItemExpr` / `BacklogDrainExpr`;
- keep imported macro expansion from `std/resource` and `std/drain` untouched; and
- keep explicit legacy elaboration using the new route-aware resolver only for characterization coverage.

- [ ] **Step 3: Re-run the tightened stdlib-form tests**

Run:

```bash
python -m pytest tests/test_workflow_lisp_stdlib_form_migration.py -q
```

Expected:

- promoted registry tests now pass because the two heads are absent from promoted lookup;
- promoted bare-form negative tests now fail closed at compile time without intrinsic accounting;
- imported stdlib owner-route tests still pass; and
- legacy-route characterization still passes.

## Task 4: Quarantine Direct Lowerers And Intrinsic Accounting To Explicit Legacy Use

**Files:**

- Modify: `orchestrator/workflow_lisp/lowering/control_dispatch.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_stdlib.py`
- Modify: `orchestrator/workflow_lisp/lowering/phase_drain.py`
- Modify only if focused tests prove finalizer accounting still leaks through it: `orchestrator/workflow_lisp/lowering/phase_resource.py`
- Inspect while editing: `tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py`

- [ ] **Step 1: Make direct lowering unreachable on promoted/WCC-default routes**

Implementation requirements:

- remove direct `FinalizeSelectedItemExpr` / `BacklogDrainExpr` dispatch from the promoted `control_dispatch` path, or make those branches fail closed unless the lowering route is explicitly legacy/schema-1;
- remove promoted wrappers for `_lower_finalize_selected_item(...)` and `_lower_backlog_drain(...)` from `phase_stdlib.py`;
- keep any remaining compatibility code only behind an explicit legacy-only admission path; and
- do not change the generic lowerers used by imported stdlib macro expansion.

- [ ] **Step 2: Guard every intrinsic-accounting path, including `phase_drain.py`**

Implementation requirements:

- ensure `record_intrinsic_form_lowering("finalize-selected-item")` and `record_intrinsic_form_lowering("backlog-drain")` can only happen on explicit legacy characterization routes;
- treat `orchestrator/workflow_lisp/lowering/phase_drain.py` as a required edit surface because it currently records `backlog-drain` hits independently of `control_dispatch.py`;
- inspect `phase_resource.py` and guard it too if `finalize-selected-item` still has a second accounting path there; and
- keep `with-phase` accounting behavior unchanged.

- [ ] **Step 3: Verify imported stdlib positive lanes stay at zero intrinsic hits while legacy selectors remain green**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_stdlib_form_migration.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py::test_dedicated_runtime_proof_profile_builds_validated_entry_bundle_for_imported_stdlib_drain \
  -q
```

Expected:

- the imported stdlib fixtures still compile successfully on the promoted route;
- the dedicated runtime proof for imported `std/drain::backlog-drain` still produces a validated entry bundle;
- promoted imported stdlib usage still records `0` intrinsic hits for the retired heads; and
- explicit legacy characterization still records one hit.

- [ ] **Step 4: Audit the source surfaces for stale promoted branches**

Run:

```bash
rg -n "finalize-selected-item|backlog-drain|FinalizeSelectedItemExpr|BacklogDrainExpr|compatibility_route_only" \
  orchestrator/workflow_lisp/form_registry.py \
  orchestrator/workflow_lisp/expressions.py \
  orchestrator/workflow_lisp/lowering/control_dispatch.py \
  orchestrator/workflow_lisp/lowering/phase_stdlib.py \
  orchestrator/workflow_lisp/lowering/phase_resource.py \
  orchestrator/workflow_lisp/lowering/phase_drain.py
```

Expected:

- promoted-path modules no longer expose the two heads as normal registry/elaboration/lowering surfaces; and
- any remaining mentions are explicit legacy guards, supporting data types, or comments that accurately describe legacy-only compatibility behavior.

## Task 5: Tighten Design Delta G8 Deletion Evidence And Downstream Checks

**Files:**

- Modify: `orchestrator/workflow_lisp/build.py`
- Modify: `tests/test_workflow_lisp_build_artifacts.py`
- Modify only if focused parity checks expose contract drift: `orchestrator/workflow_lisp/migration_parity.py`
- Modify only if focused parity checks expose contract drift: `tests/test_workflow_lisp_migration_parity.py`

- [ ] **Step 1: Close the compatibility-tag loophole in G8 serialization**

Implementation requirements:

- update `_serialize_design_delta_g8_deletion_evidence(...)` so `finalize-selected-item` and `backlog-drain` count as still present whenever promoted `get_form_spec(...)` returns a spec for them, even if that spec carries `compatibility_route_only`;
- keep `removed_registry_heads` aligned with the absence-based architecture contract, so the emitted lane records only heads that are absent from the promoted registry;
- preserve `with-phase` as the only imported-only registry head accepted in `hook_surface_delta["imported_only_registry_heads"]`; and
- keep the emitted artifact schema and field names unchanged.

- [ ] **Step 2: Strengthen build-artifact tests around removed registry heads**

Implementation requirements:

- update `test_design_delta_parent_drain_build_emits_g8_deletion_evidence_artifact` so it asserts the emitted payload lists only `finalize-selected-item` and `backlog-drain` in `removed_registry_heads`, while `with-phase` appears only in `imported_only_registry_heads`;
- extend `test_design_delta_parent_drain_build_rejects_removed_registry_heads_still_present` so it proves the build now rejects reintroduction of `finalize-selected-item` or `backlog-drain` even when the fake spec is compatibility-tagged; and
- keep the diagnostic code `design_delta_g8_removed_registry_head_present`.

- [ ] **Step 3: Touch parity tests only if the stricter artifact contract surfaces a mismatch**

Implementation requirements:

- prefer leaving `orchestrator/workflow_lisp/migration_parity.py` and `tests/test_workflow_lisp_migration_parity.py` unchanged if the existing payload expectations already match the tightened build artifact;
- if a parity helper or focused parity test assumes the two heads can still be compatibility-tagged in promoted evidence, update only the helper or selector that encodes that stale assumption; and
- do not widen the parity scope beyond the G8 deleted-head/imported-only-with-phase contract.

- [ ] **Step 4: Run the focused G8 build/parity selectors**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_emits_g8_deletion_evidence_artifact \
  tests/test_workflow_lisp_build_artifacts.py::test_design_delta_parent_drain_build_rejects_removed_registry_heads_still_present \
  tests/test_workflow_lisp_migration_parity.py::test_run_parity_target_fails_when_g8_evidence_does_not_require_imported_only_with_phase \
  -q
```

Expected:

- the emitted G8 artifact still matches the checked-in contract;
- the build fails when a removed head is reintroduced on the promoted route, including compatibility-tagged fake specs for the two retired stdlib heads; and
- parity still requires `finalize-selected-item` and `backlog-drain` in `removed_registry_heads` while `with-phase` remains the only imported-only registry head.

## Task 6: Reconfirm The Design Delta Owner Route And Finish Verification

**Files:**

- Verify against: `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`
- Verify against: `tests/test_workflow_lisp_build_artifacts.py`
- Verify against: `workflows/library/lisp_frontend_design_delta/drain.orc`

- [ ] **Step 1: Re-run collection for every touched verification module**

Run:

```bash
python -m pytest --collect-only \
  tests/test_workflow_lisp_stdlib_form_migration.py \
  tests/test_workflow_lisp_stdlib_runtime_proof_boundary.py \
  tests/test_workflow_lisp_build_artifacts.py \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  tests/test_workflow_lisp_migration_parity.py \
  -q
```

Expected:

- collection succeeds after all test additions or renames; and
- no import/discovery regressions were introduced.

- [ ] **Step 2: Run the focused Design Delta owner-route integration selector**

Run:

```bash
python -m pytest \
  tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes \
  -q
```

Expected:

- the real Design Delta parent drain still compiles through the imported `std/drain::backlog-drain` owner route; and
- the work-item route still reaches imported `finalize-selected-item` behavior through the stdlib-owned path rather than a compiler literal-head shortcut.

- [ ] **Step 3: Optionally run the direct CLI compile as a human-readable smoke check**

Run:

```bash
python -m orchestrator compile \
  workflows/library/lisp_frontend_design_delta/drain.orc \
  --entry-workflow lisp_frontend_design_delta/drain::drain \
  --provider-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.providers.json \
  --prompt-externs-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.prompts.json \
  --command-boundaries-file workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.commands.json
```

Expected:

- compile succeeds without relying on promoted literal-head compatibility handling; and
- any failure here is treated as a real integration regression because this slice changes frontend/lowering behavior.

- [ ] **Step 4: Record bounded completion evidence**

Completion checklist:

- promoted `get_form_spec(...)` no longer exposes `finalize-selected-item` or `backlog-drain`;
- explicit legacy compilation reaches those bare heads only through the route-aware legacy lookup / elaboration lane;
- promoted elaboration cannot construct `FinalizeSelectedItemExpr` or `BacklogDrainExpr` from bare source heads;
- promoted/default lowering cannot dispatch those two heads through direct compatibility lowerers;
- legacy characterization remains explicit and still records intrinsic counts only on the legacy route;
- imported stdlib positive fixtures and dedicated runtime proof remain green with zero promoted intrinsic counts;
- `phase_drain.py` no longer records `backlog-drain` intrinsic hits on promoted routes;
- Design Delta G8 deletion evidence records `finalize-selected-item` and `backlog-drain` only in `removed_registry_heads`, fails if either retired head survives in promoted compiler surfaces, and still keeps `with-phase` as the only imported-only head; and
- the Design Delta parent drain owner-route integration selector still passes without editing stdlib semantics or workflow source shape.
