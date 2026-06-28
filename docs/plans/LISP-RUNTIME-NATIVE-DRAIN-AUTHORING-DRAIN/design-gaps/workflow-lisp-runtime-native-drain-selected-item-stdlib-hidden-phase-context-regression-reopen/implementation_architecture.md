# Workflow Lisp Runtime-Native Drain Selected-Item Stdlib Hidden Phase Context Regression Reopen Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-runtime-native-drain-selected-item-stdlib-hidden-phase-context-regression-reopen`
Target design: `docs/design/workflow_lisp_runtime_native_drain_authoring.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`
Command-adapter authority: `docs/design/workflow_command_adapter_contract.md`

## Scope

This slice covers exactly the selected target-design gap:

- restore the production selected-item stdlib route so
  `lisp_frontend_design_delta/work_item::run-selected-item-stdlib` may call
  `lisp_frontend_design_delta/work_item::run-work-item` without authoring or
  publicizing the callee's `phase-ctx` binding;
- reuse the existing shared `derived_private_child_context` lane for
  `ItemCtx + typed payload` callers rather than introducing a Design
  Delta-specific compiler hook;
- preserve the fixed imported `std/drain::backlog-drain` `run-item`
  workflow-ref shape: `(ItemCtx, selection payload) -> SelectedItemResult`;
  and
- prove that the Design Delta parent-call work-item and parent-drain
  entrypoint routes compile through the WCC/schema-2 path with hidden
  `PhaseCtx` boundary evidence.

Out of scope:

- changing `std/drain::backlog-drain` loop semantics or workflow-ref arity;
- widening `run-selected-item-stdlib`, `run-work-item`, selector, or
  gap-drafter public signatures;
- replacing the selected-item route with a family-local wrapper whose only job
  is to smuggle `phase-ctx`;
- changing `run-work-item` phase/body semantics, plan/implementation phase
  workflows, `finalize-selected-item`, terminal reprojection, summary
  ownership, gap re-entry convergence, or provider request-record behavior;
- changing Core Workflow AST, Semantic Workflow IR, executable IR, SourceMap,
  pointer authority, or variant-proof contracts;
- adding scripts, command adapters, inline Python, report parsing, pointer
  files, stdout JSON, or compatibility-bundle rereads; and
- claiming YAML-primary promotion.

This is a bounded implementation architecture for one regression reopen. It
does not replace the runtime-native drain target design or the accepted
Workflow Lisp frontend baseline.

## Problem Statement

Fresh verification of the selected subject fails in the same place for both
named routes:

```text
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py \
  -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'
```

Both tests fail with:

```text
[workflow_signature_mismatch] call is missing required binding `phase-ctx`
form: workflow-lisp > defworkflow > run-selected-item-stdlib
```

The failing source is
`workflows/library/lisp_frontend_design_delta/work_item.orc`, where
`run-selected-item-stdlib` has the desired stdlib-facing signature:

```lisp
(defworkflow run-selected-item-stdlib
  ((item-ctx std/context/ItemCtx)
   (selection DesignDeltaSelectedItemPayload))
  -> SelectedItemResult
  ...)
```

but calls `run-work-item` without `:phase-ctx`:

```lisp
(call run-work-item
  :work_item_bootstrap selection.work_item_bootstrap
  :steering_path selection.steering_path
  :target_design_path selection.target_design_path
  :baseline_design_path selection.baseline_design_path
  :progress_ledger_path selection.progress_ledger_path)
```

The callee still has an internal phase-first boundary:

```lisp
(defworkflow run-work-item
  ((phase-ctx PhaseCtx)
   ...)
  -> WorkItemResult
  ...)
```

That boundary is not itself the selected gap. The target design allows
internal reusable definitions to mention private context when lowering supplies
that context through hidden binding evidence. The selected gap is that the
production stdlib selected-item route no longer reaches the existing hidden
`phase-ctx` derivation path.

## Design Constraints

This slice must preserve these contracts:

- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` Section 9.2
  requires hidden private-context transport for item-context-first work-item
  families without public `PhaseCtx`, widened `run-item` workflow refs,
  compatibility-bundle rereads, or family-local wrapper decomposition.
- Section 13.4 requires the Design Delta parent-drain route to prove hidden
  private-context bindings and matched child-workflow unions on the WCC route
  before claiming the shared phase-family boundary prerequisite.
- Section 15 requires private runtime context and generated paths to stay off
  public authored boundaries, and requires phase/item/drain behavior to remain
  ordinary stdlib or family-library Workflow Lisp over generic
  context/resource mechanics.
- `docs/design/workflow_lisp_frontend_specification.md` requires workflow calls
  to validate signatures before lowering, with private executable context
  bindings remaining runtime-owned boundary classes and not public authored
  inputs.
- `docs/design/workflow_command_adapter_contract.md` forbids repairing hidden
  workflow semantics with command glue. This slice has no command-adapter work;
  the fix is typed Workflow Lisp context binding and validation.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index for this request listed these prior slices,
and this architecture was drafted against them:

- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-family-specific-compiler-hook-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-gap-drafter-callable-boundary-over-imported-backlog-drain/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-literal-name-stdlib-intrinsic-retirement/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-call-contract-regression-reopen/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-selector-stdlib-single-ctx-signature-alignment-regression-reopen/implementation_architecture.md`
- `docs/plans/LISP-RUNTIME-NATIVE-DRAIN-AUTHORING-DRAIN/design-gaps/workflow-lisp-runtime-native-drain-shared-std-phase-owner-lane-self-hosting-regression-reopen/implementation_architecture.md`

### Decisions Reused

- Reuse the family-specific compiler-hook retirement slice's rule that Design
  Delta parent-family gaps must not be repaired with new hardcoded compiler or
  build hooks.
- Reuse the gap-drafter callable-boundary slice's owner split: imported
  `backlog-drain` owns the child loop and fixed workflow-ref calls; family
  routes conform through typed values rather than wrapper transport.
- Reuse the literal-name stdlib intrinsic retirement slice's rule that
  promoted stdlib behavior must arrive through imported stdlib composition and
  ordinary typed forms, not direct literal-name lowerers.
- Reuse both selector regression slices' narrow repair discipline: fix stale
  family wiring or missing shared admission directly, and split any broader
  compiler or family adoption issue discovered during implementation.
- Reuse the shared `std/phase` owner-lane self-hosting slice's prerequisite
  discipline: downstream Design Delta evidence may cite shared owner-lane
  proof only after the shared path itself is green.

### New Decisions In This Slice

- Treat `run-selected-item-stdlib` as the production consumer of the existing
  shared `ItemCtx + typed payload` hidden-context proof lane.
- The active fix should make the omitted `phase-ctx` call admissible through
  `derived_private_child_context` metadata and eligibility, not by adding
  `:phase-ctx` to the authored call.
- The production `run-work-item` hidden-context rule remains profile-backed by
  `design_delta_parent_drain.family_profile.json`, where its phase identity is
  `work-item`.
- Add production evidence for `phase-ctx__work-item` hidden binding on the
  `run-selected-item-stdlib -> run-work-item` call. Existing fixture evidence
  for `phase-ctx__plan` and `phase-ctx__implementation` stays adjacent proof,
  not a substitute for this production route.

### Conflicts Or Revisions

No prior architecture decision is revised.

The current checkout conflicts with the accepted target because the production
selected-item stdlib route has the correct fixed `ItemCtx + selection payload`
surface but fails before hidden phase-context binding is admitted. This slice
resolves that conflict by reusing the shared derived-context path.

No shared concepts such as spans, diagnostics, Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, variant proof,
resource transition, or command adapter certification are redefined here.

## Current Checkout Facts

- `workflows/library/lisp_frontend_design_delta/drain.orc` passes
  `run-selected-item-stdlib` as the `:run-item` workflow ref to imported
  `std/drain::backlog-drain`.
- `workflows/library/lisp_frontend_design_delta/work_item.orc` defines
  `run-selected-item-stdlib ((item-ctx std/context/ItemCtx) (selection
  DesignDeltaSelectedItemPayload)) -> SelectedItemResult`.
- The same file defines `run-work-item ((phase-ctx PhaseCtx) ...) ->
  WorkItemResult`, and its body uses `with-phase phase-ctx work-item` plus
  calls to plan, implementation, recovery classification, and finalization.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`
  declares a hidden-context rule for
  `lisp_frontend_design_delta/work_item::run-work-item`:
  `parameter_name = "phase-ctx"` and `phase_identity = "work-item"`.
- `orchestrator/workflow_lisp/phase.py` already defines
  `derived_private_child_context_eligibility(...)`, which requires exactly one
  `(item-ctx ItemCtx)` source parameter plus one typed payload record.
- `orchestrator/workflow_lisp/typecheck_calls.py` already allows omitted
  hidden context when the callee has a
  `binding_kind="derived_private_child_context"` requirement and the active
  caller signature passes that eligibility check.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py` and
  `orchestrator/workflow_lisp/lowering/phase_drain.py` already know how to
  declare runtime-owned hidden inputs for omitted derived child context
  bindings.
- `tests/test_workflow_lisp_build_artifacts.py` already proves derived child
  phase bindings for the fixture route
  `design_delta_item_ctx_child_phase_reuse::run-item-ctx-first`, including
  source provenance and carried `item-ctx.run.*` input sources.
- The production failing route lacks equivalent passing evidence for
  `lisp_frontend_design_delta/work_item::run-selected-item-stdlib`.

## Feasibility Proof

This slice is feasible without a new language feature:

1. The source shape of `run-selected-item-stdlib` already matches the shared
   eligibility model: one private `ItemCtx` argument and one typed selection
   payload record.
2. The callee `run-work-item` already has a family-profile hidden-context rule
   naming `phase-ctx` and phase identity `work-item`.
3. The typechecker and lowerers already implement the two halves of omitted
   derived context: signature admission and runtime hidden-input declaration.
4. Existing fixture tests prove the same mechanism for item-context-first child
   phase reuse in a non-production module.
5. The fresh failure occurs before lowering, at call type validation. That
   localizes the primary repair to signature/catalog metadata and call
   admission, with lowering/build artifacts as regression evidence.

The main implementation risk is that production library imports may canonicalize
`std/context/ItemCtx` or `DesignDeltaSelectedItemPayload` differently than the
fixture route. The fix should address that as a generic type-resolution or
signature metadata issue. It must not special-case the Design Delta workflow
name except through the already checked family profile.

## Ownership Boundaries

This slice owns:

- `orchestrator/workflow_lisp/workflows.py`
  - ensure signature construction preserves or derives
    `hidden_context_requirements` for profile-backed `run-work-item` and
    `allowed_hidden_context_callees` for the production selected-item stdlib
    caller;
  - ensure the shared proof lane recognizes production imported/family modules
    as well as fixture modules when the caller has exactly `ItemCtx + typed
    payload`.
- `orchestrator/workflow_lisp/typecheck_calls.py`
  - keep omitted hidden-context validation strict;
  - repair only if the current active/callee signature metadata prevents the
    already-defined `derived_private_child_context` path from admitting the
    production call.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py` and
  `orchestrator/workflow_lisp/lowering/phase_drain.py`
  - preserve hidden-input emission for the omitted production `phase-ctx`;
  - ensure generated binding ids, carried input sources, source provenance, and
    boundary projection rows use `phase-ctx__work-item` for this route.
- `workflows/examples/inputs/workflow_lisp_migrations/design_delta_parent_drain.family_profile.json`
  - adjust only if the existing hidden-context rule is incomplete or stale;
  - do not introduce compiler-name behavior outside checked profile metadata.
- Focused tests in:
  - `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
  - `tests/test_workflow_lisp_build_artifacts.py`; and
  - existing invalid derived-context fixtures if a new negative is needed.

This slice intentionally does not own:

- `workflows/library/lisp_frontend_design_delta/drain.orc`, except as the
  parent consumer that should compile after the repair;
- broad rewrites of `workflows/library/lisp_frontend_design_delta/work_item.orc`
  beyond possible source-shape assertions or minimal call-route cleanup;
- `std/drain.orc`, `std/resource.orc`, or `std/phase.orc` semantics;
- `run-work-item` plan/implementation/recovery/finalization behavior;
- provider externs, prompt externs, command-boundary manifests, certified
  adapters, or runtime transition semantics; or
- YAML-primary promotion and migration parity adjudication.

## Implementation Shape

Repair the production call by making the existing hidden-context pipeline see
the same facts it already requires:

```text
caller: lisp_frontend_design_delta/work_item::run-selected-item-stdlib
  params:
    item-ctx: std/context/ItemCtx
    selection: DesignDeltaSelectedItemPayload

callee: lisp_frontend_design_delta/work_item::run-work-item
  omitted param:
    phase-ctx: PhaseCtx
  hidden requirement:
    binding_kind: derived_private_child_context
    phase_name: work-item
```

The accepted compile-time route is:

1. family profile attaches the `phase-ctx` hidden-context requirement to
   `run-work-item`;
2. workflow signature analysis recognizes `run-selected-item-stdlib` as an
   eligible `ItemCtx + typed payload` caller;
3. call typechecking allows the omitted `phase-ctx` only because the callee
   requirement is `derived_private_child_context` and the active caller passes
   `derived_private_child_context_eligibility(...)`;
4. lowering emits runtime-owned hidden inputs for `phase-ctx__work-item`,
   carrying run anchors from `item-ctx.run.*` and compile-time defaults for
   phase name, state root, and artifact root; and
5. boundary projection and build artifacts record the binding as private
   runtime context, not public authored input.

Do not add `:phase-ctx` to `run-selected-item-stdlib`. Do not widen the
imported `backlog-drain` `run-item` workflow-ref surface. Do not introduce a
compatibility carrier or command boundary to recreate phase context.

## Data And Control Flow

1. `drain.orc` calls imported `std/drain::backlog-drain` with
   `:run-item run-selected-item-stdlib`.
2. Imported `backlog-drain` calls `run-selected-item-stdlib` through the fixed
   stdlib selected-item shape: `ItemCtx` plus selection payload.
3. `run-selected-item-stdlib` builds family item context and resolved work-item
   inputs, then calls `run-work-item` without an authored `phase-ctx`.
4. Typechecking admits the omission using the callee's profile-backed
   `derived_private_child_context` requirement and the caller's eligible
   `ItemCtx + typed payload` signature.
5. Lowering declares `phase-ctx__work-item` runtime-owned context inputs and
   binds the callee `phase-ctx` parameter from those hidden inputs.
6. `run-work-item` executes its existing phase-scoped body and returns
   `WorkItemResult`.
7. `run-selected-item-stdlib` matches that typed result and projects the
   stdlib `SelectedItemResult` expected by imported `backlog-drain`.

No report, pointer file, stdout payload, command output, or compatibility JSON
bundle participates in this context decision.

## Source Maps And Boundary Evidence

The repaired route must preserve these evidence properties:

- `phase-ctx`, `phase-ctx__state-root`, `phase-ctx__artifact-root`, and
  `phase-ctx__phase-name` do not appear as public inputs on parent or
  selected-item stdlib boundaries.
- `run-selected-item-stdlib` records one private runtime context binding for
  the omitted work-item phase, with:
  - `binding_id = "phase-ctx__work-item"`;
  - `source_param_name = "item-ctx"`;
  - `context_family = "PhaseCtx"`;
  - `bridge_class = "derived_private_child_context"`;
  - `derived_phase_identity = "work-item"`;
  - carried input sources rooted at `("item-ctx", "run", ...)`; and
  - source provenance pointing at the `run-work-item` call in
    `work_item.orc`.
- `run-work-item` may retain its direct-entry runtime-owned `phase-ctx`
  bootstrap evidence. That direct-entry evidence is separate from the derived
  child binding used by `run-selected-item-stdlib`.
- Build artifacts and `workflow_boundary_projection` serialize the same
  private binding metadata that shared validation and runtime input
  classification consume.

## Diagnostics And Failure Modes

The implementation should fail closed in these cases:

- caller has no private `ItemCtx` source: `derived_phase_context_binding_invalid`;
- caller has more than one private context source:
  `derived_phase_context_ambiguous`;
- caller has `ItemCtx` plus more than one non-context argument:
  `derived_phase_context_binding_invalid`;
- non-context argument is itself a private context or is not a typed record:
  `derived_phase_context_binding_invalid`;
- callee has no profile-backed or derived `phase-ctx` hidden requirement:
  `workflow_signature_mismatch` remains valid;
- profile rule names a non-`PhaseCtx` parameter:
  `workflow_family_profile_hidden_context_invalid`; and
- public boundary projection exposes `phase-ctx__*` fields:
  boundary-authority tests fail.

These diagnostics should remain generic. Do not add a caller-name allowlist for
`run-selected-item-stdlib`.

## Command Adapter Policy

No command adapter is proposed or needed. If implementation work touches
scripts, command boundaries, command manifests, runtime-native effects, or
certified adapters, `docs/design/workflow_command_adapter_contract.md` is
authoritative. Any command boundary carrying workflow semantics must declare
typed inputs, typed outputs, effects, path-safety rules, fixtures, negative
fixtures, source-map behavior, owner, and replacement path.

For this slice, hidden `phase-ctx` transport is typed Workflow Lisp call
semantics. Adding shell/Python glue, report parsing, pointer-state reads, or
stdout JSON would violate the selected target.

## Verification

Minimum deterministic checks for the implementation slice:

```bash
pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_parent_call_work_item_compiles_with_hidden_phase_context or design_delta_parent_drain_entrypoint_adopts_stdlib_owner_routes'
pytest -q tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k 'design_delta_item_ctx_child_phase_reuse_compiles or design_delta_item_ctx_child_phase_reuse_route_supports_arbitrary_module_identity or design_delta_item_ctx_child_phase_reuse_route_rejects_non_item_ctx_root'
pytest -q tests/test_workflow_lisp_build_artifacts.py -k 'design_delta_item_ctx_child_phase_reuse_build_artifacts_record_derived_child_phase_binding or design_delta_parent_drain_imported_backlog_drain_build_artifacts_record_derived_child_phase_binding'
```

Expected evidence:

- the selected failing tests no longer stop with
  `workflow_signature_mismatch` at `run-selected-item-stdlib`;
- public inputs for parent and selected-item routes exclude `phase-ctx__*`;
- `workflow_boundary_projection` records `phase-ctx__work-item` as
  `derived_private_child_context`;
- source provenance for the derived binding points to the production
  `work_item.orc` call site;
- existing fixture evidence for plan/implementation derived child contexts
  still passes; and
- invalid derived-context fixtures continue to fail with the existing generic
  diagnostics.

## Implementation Handoff

1. Reproduce the selected failure with the two-test selector and inspect the
   call diagnostic at `work_item.orc`.
2. Add or adjust a focused production build-artifact assertion for
   `run-selected-item-stdlib` that expects `phase-ctx__work-item` derived
   private-context metadata.
3. Repair signature/catalog admission so the production
   `run-selected-item-stdlib` caller receives `allowed_hidden_context_callees`
   for `run-work-item` through the same generic `ItemCtx + typed payload`
   route used by existing fixtures.
4. If typechecking passes but lowering/build artifacts omit
   `phase-ctx__work-item`, repair only the hidden-input emission path that
   serializes derived child context metadata.
5. Run the verification commands above.
6. If the next failure is in called-workflow result branching,
   finalizer placement, summary ownership, gap convergence, or command
   adapter certification, split it into the corresponding existing target
   prerequisite instead of broadening this slice.

