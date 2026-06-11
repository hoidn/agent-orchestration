# Workflow Lisp Parent Backlog-Drain Composition Parity Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-parent-backlog-drain-composition-parity`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Tranche 7/8 parent-family gap:

- add the first real Design Delta Drain parent `.orc` family entrypoint that
  composes the current selector, design-gap architect, work-item, plan, and
  implementation candidates;
- prove the parent route compiles, lowers through WCC schema 2, shared-validates,
  and can smoke at least a selected-work path and a blocked/recovery path;
- carry `DrainCtx`, `ItemCtx`, selection state, recovery state, and generated
  paths privately, using boundary projection and compatibility bridge metadata
  already established by prior slices;
- record boundary and artifact justifications for the family, including
  `parity_constrained` labels where the YAML primary forces a temporary shape;
- expose resource-transition or certified-adapter evidence for run-state,
  recovery, terminal, prerequisite, and drain-summary updates;
- extend migration-parity evidence so leaf-only evidence cannot satisfy
  `--require-non-regressive` or `--require-promotable` for this family.

Out of scope for this slice:

- changing WCC lowering architecture or adding a second helper-hoisting route;
- reworking plan, implementation, selector, architect, or work-item semantics;
- promoting the YAML primary to `.orc`;
- implementing a runtime-native resource transaction if certified adapters can
  provide the first migration bridge;
- broad legacy YAML lint enforcement;
- treating reports, pointer files, stdout, materialized views, or debug YAML as
  semantic authority.

The success condition is bounded: one parent-callable Design Delta Drain family
path becomes real evidence instead of a set of compileable leaves.

## Problem Statement

The checkout now has the prerequisite pieces that previously blocked parent
work:

- WCC `IfExpr` support is recorded complete in run state.
- Phase-family boundary rehabilitation is recorded complete.
- The implementation phase has parent-callable WCC evidence.
- The real work-item route compiles as a parent-callable workflow with hidden
  phase context and compatibility bridge inputs.
- Selector bundle projection and command-boundary lineage have focused tests.

What is still missing is a family parent. Existing tests prove leaves and small
stdlib examples, but not a real Design Delta Drain parent that:

```text
selects work -> matches typed selection -> runs design-gap/work-item route
-> records declared resource transitions -> updates typed loop state
-> emits parity-comparable drain terminal evidence
```

Without that parent route, the migration remains leaf evidence. The target
design explicitly says leaf compile or leaf smoke evidence is useful progress
but cannot prove family non-regression or promotion eligibility.

## Design Constraints

This architecture is governed by:

- `docs/index.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`;
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  Sections 10A, 18, 19, 20, 21, 25, 27, 28, and 29;
- `docs/design/workflow_lisp_frontend_specification.md`;
- `docs/design/workflow_lisp_core_calculus_middle_end.md`;
- `docs/design/workflow_lisp_state_layout.md`;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`;
- `docs/design/workflow_command_adapter_contract.md`;
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, and `specs/state.md`.

Guardrails:

- WCC schema 2 (`LoweringRoute.WCC_M4`, schema version 2) is the only compiler
  route for new parent composition evidence.
- Use `WorkflowBoundaryProjection`, generated internal input metadata,
  compatibility bridge labels, source maps, Semantic IR state layout entries,
  and `StateLayout` / `PathAllocator`; do not define a second metadata model.
- Default to scoped typed values between phases. Author artifacts only when
  required for public boundary identity, parity comparison, external/legacy
  consumption, or cross-run durability.
- Context inside the parent family is ordinary scoped data. Entry/bootstrap and
  compatibility bridge machinery appear only at promoted entry or YAML
  compatibility boundaries.
- Any retained helper script that decides run state, recovery, routing,
  resource movement, or terminal status must be represented as a certified
  adapter or declared resource-transition bridge with fixture evidence.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/2/design-gap-architect/existing-architecture-index.md`
was reviewed. The full index-listed corpus was scanned for scope, ownership,
and conflict sections.

Directly constraining slices read closely:

- `workflow-lisp-wcc-ifexpr-work-item-route`;
- `workflow-lisp-phase-family-boundary-rehabilitation`;
- `workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr`;
- `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`;
- `workflow-lisp-promoted-entry-hidden-reusable-call-binding`;
- `workflow-lisp-state-layout-path-allocator-foundation`;
- `resource-drain-library`;
- `rich-semantic-effect-graph`;
- `workflow-boundary-type-flattening`;
- `workflow-refs-compile-time-linking`;
- `workflow-lisp-design-plan-impl-stack-parity-evidence-refresh`;
- `source-map-runtime-lineage`;
- `semantic-workflow-ir-shared-contract`;
- `executable-ir-runtime-plan`.

### Decisions Reused

- Reuse WCC M4 as the accepted route for nested parent composition.
- Reuse boundary projection to distinguish public authored inputs, generated
  internal inputs, runtime-owned context, managed write roots, and compatibility
  bridge inputs.
- Reuse hidden phase/context binding from the prior phase-family slices. This
  slice composes those candidates; it does not reopen `PhaseCtx` transport.
- Reuse `backlog-drain` lowering conventions where they fit: `repeat_until`,
  typed accumulator fields, selector/run-item/gap-drafter calls, managed call
  write roots, and source-mapped generated steps.
- Reuse the command-adapter contract for retained Design Delta scripts. Scripts
  are not semantic authority unless certified with typed input/output/effect
  metadata.
- Reuse migration-parity as the only authority for computed `non_regressive`.

### New Decisions In This Slice

- Add a real family parent source, tentatively
  `workflows/library/lisp_frontend_design_delta/drain.orc`, instead of only
  synthetic stdlib fixtures.
- Add a Design Delta parent-drain readiness record that lists each family
  boundary, its justification, route, schema version, and readiness label.
- Add family artifact-justification records for every authored artifact the
  parent exchanges or compares; parity-only artifacts are labeled
  `parity_constrained`.
- Add a parent-family resource-transition evidence lane. For the first slice,
  existing terminal/recovery/run-state update scripts may remain only as
  certified adapter bridges with declared behavior classes such as
  `resource_transition`, `ledger_update`, `outcome_finalization`, or
  `typed_projection`.
- Add a `design_delta_parent_drain` migration-parity target that fails
  promotable/non-regressive gates until parent-callable, resource-transition,
  and route-fresh evidence are present.

### Conflicts Or Revisions

No shared concepts are redefined. This slice does revise the practical use of
the earlier `backlog-drain` stdlib evidence: small `backlog-drain` fixtures
remain substrate evidence, not proof that the Design Delta Drain family is
parent-callable. The parent family must compile and smoke against the real
Design Delta modules.

## Architecture

### Parent Source Shape

Create a Design Delta parent module that imports the real family leaves:

```text
lisp_frontend_design_delta/drain
  imports:
    lisp_frontend_design_delta/types
    lisp_frontend_design_delta/selector::select-next-work
    lisp_frontend_design_delta/design_gap_architect::{draft, validate}
    lisp_frontend_design_delta/work_item::run-work-item
```

The parent entrypoint owns only the family-level loop and parity shape. Child
phase behavior stays in child modules.

The first implementation can use one explicit parent loop or the existing
`backlog-drain` surface, but the chosen route must satisfy the same facts:

- loop state is a typed `DrainState`;
- the next action is selected from typed selector/projection state, not by
  reading a pointer, markdown report, or status file;
- `ItemCtx` and recovery context are pure projections from `DrainCtx` plus the
  selected bundle/action;
- selected-item, design-gap, prerequisite/recovery, terminal-block, and
  exhausted routes update typed loop state;
- terminal result is the existing `DrainResult` union from
  `lisp_frontend_design_delta/types.orc`, or a narrow extension of it if the
  current union cannot represent parent evidence without string gates.

### Selector And Design-Gap Routing

The current selector returns `SelectorPublicResult` with a projected
`selection_bundle_path`. Parent composition must add a typed projection layer
over that result before branching:

```text
SelectorPublicResult
-> pure/typed projection
-> DesignDeltaDrainAction union
```

The projection may consume the validated provider bundle identity, but it must
not read the bundle path as pointer authority. If a script remains necessary
for compatibility, it must be certified as deterministic projection and marked
temporary with a native-projection replacement path.

For `DRAFT_DESIGN_GAP`, the parent calls the real architect draft and validation
leaves, then records a transition into a prepared work-item/retry state before
the loop continues. For `SELECT_BACKLOG_ITEM` or recovered prepared work, the
parent calls `run-work-item`.

### Context And Boundary Handling

The parent public boundary must not expose generated write roots, synthetic
`PhaseCtx`, `DrainCtx` internals, or YAML-era state paths as ordinary authored
inputs. It may retain YAML compatibility values only through boundary
projection labels:

```text
public_authored:
  steering, target_design, baseline_design, max_iterations, provider/prompt
  externs that are truly user-facing for the family

runtime_owned_context:
  run id, root namespaces, artifact root, entry write roots

compatibility_bridge:
  manifest, progress ledger, run state, selection bundle, architecture bundle
  only where parity with the YAML primary requires them
```

Inside the parent, context is ordinary scoped data. `DrainCtx`, `ItemCtx`,
`SelectionCtx`, and `RecoveryCtx` are built with `pure_projection` nodes and
passed to child calls as private arguments. The architecture explicitly rejects
threading context through a new special workflow-boundary carrier.

### Resource And Adapter Evidence

The first parent slice must classify every retained Design Delta helper script
that participates in parent state or routing:

- `materialize_lisp_frontend_work_item_inputs.py`: `typed_projection` /
  compatibility bridge into `ResolvedWorkItemInputs`;
- `classify_lisp_frontend_work_item_terminal.py`: `outcome_finalization`;
- `select_lisp_frontend_blocked_recovery_route.py`: `outcome_finalization`;
- terminal/recovery run-state writers: `resource_transition` and
  `ledger_update`;
- drain status and drain summary writers: `outcome_finalization`,
  `ledger_update`, or `typed_projection` depending on the exact script.

Each retained semantic helper must have a `CertifiedAdapterBinding` or manifest
entry with typed inputs, typed outputs, effects, error codes, fixtures,
negative fixtures, owner module, and replacement path. Parent evidence must
show those effects in lowered workflow metadata and Semantic IR. Raw argv
without certification is allowed only for external tools whose semantics are
outside workflow routing.

### Parity Evidence

Add a Design Delta parent-drain parity target, separate from leaf parity:

```text
workflow_family: design_delta_parent_drain
candidate: workflows/library/lisp_frontend_design_delta/drain.orc
yaml_primary: workflows/examples/lisp_frontend_design_delta_drain.yaml
entry_workflow: lisp_frontend_design_delta/drain::drain
readiness_label: parent_callable_candidate
lowering_route: wcc_m4
lowering_schema_version: 2
```

The target initially should not be `promotion_eligible` unless the strict gate
has complete family evidence. The migration-parity command must fail
`--require-promotable` when only leaf/child evidence exists.

Evidence roles for this slice:

- compile/typecheck/lowering/shared validation for parent route;
- fake-provider smoke for selected item completed path;
- fake-provider smoke for blocked/recovery path;
- public/private boundary inspection;
- source-map and generated-path provenance;
- selector/projection evidence;
- resource-transition/certified-adapter evidence;
- route identity and schema-version freshness.

## Ownership Boundaries

This slice owns:

- `workflows/library/lisp_frontend_design_delta/drain.orc`;
- narrow additions to `workflows/library/lisp_frontend_design_delta/types.orc`
  for parent `DrainState`, action/projection, readiness, or terminal fields
  only when existing types are insufficient;
- parent-specific fixtures under `tests/fixtures/workflow_lisp/valid/` if the
  real module needs fixture-local provider/command assets;
- focused tests in
  `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`,
  `tests/test_workflow_lisp_drain_stdlib.py`,
  `tests/test_workflow_lisp_build_artifacts.py`, and
  `tests/test_workflow_lisp_migration_parity.py`;
- Design Delta parent target entries in migration parity manifests;
- adapter-binding/command-boundary manifest entries for retained parent-family
  semantic helpers;
- documentation updates to the generated work-item plan only, not global
  product specs, unless implementation exposes a lasting user-visible surface.

This slice intentionally does not own:

- WCC core calculus redesign;
- child phase implementation semantics;
- broad `resource-transition` runtime-native promotion;
- provider runtime behavior;
- shared Core Workflow AST, Semantic IR, TypeCatalog, SourceMap, pointer
  authority, or variant proof ownership;
- YAML primary replacement.

## Feasibility Proofs And Open Prerequisites

Feasibility already exists for:

- WCC M4 default route and route/schema identity;
- parent-callable implementation phase;
- work-item route past IfExpr and phase-family boundary blockers;
- selector bundle path projection;
- resource transition effects through `apply_resource_transition`;
- `backlog-drain` stdlib lowering into a typed loop in synthetic fixtures.

Open proof required by this slice:

- the real Design Delta parent module can compose current child signatures
  without forcing public generated context/state inputs;
- selector output can be projected into a typed parent action without pointer
  authority or string-status gates becoming semantic authority;
- retained state/recovery scripts can be certified or replaced before their
  effects are accepted as parent-family resource-transition parity;
- migration parity can reject leaf-only evidence for this family while
  accepting complete parent-callable evidence when present.

## Implementation Handoff

Recommended implementation order:

1. Add failing fixtures/tests for the new parent route, public/private boundary
   inspection, and leaf-only parity rejection.
2. Add the parent `drain.orc` module with typed loop/action state and child
   calls.
3. Add selector/action projection and context pure projections.
4. Register or require certified adapter bindings for retained parent-family
   semantic helpers.
5. Add smoke fixtures for selected item completed, blocked recovery, terminal
   blocked, and bounded exhaustion where feasible in this slice.
6. Add the migration-parity target and strict evidence role checks.
7. Update the execution plan and run the focused checks below.

## Verification

Minimum focused checks:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_drain_stdlib.py tests/test_workflow_lisp_migration_parity.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "design_delta_parent_call_work_item or design_delta_parent_drain" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or design_delta_parent_drain or command_boundary_lineage or compatibility_bridge" -q
python -m pytest tests/test_workflow_lisp_drain_stdlib.py -k "backlog_drain and (lowering or validates or contract_inventory)" -q
python -m pytest tests/test_workflow_lisp_migration_parity.py -k "promotable or non_regressive or leaf_only or design_delta_parent_drain" -q
git diff --check
```

If implementation changes workflow prompts, artifact contracts, command
adapter declarations, or demo trial mechanics, add an orchestrator compile/run
or dry-run smoke for `workflows/library/lisp_frontend_design_delta/drain.orc`
with fake provider/command fixtures before claiming completion.
