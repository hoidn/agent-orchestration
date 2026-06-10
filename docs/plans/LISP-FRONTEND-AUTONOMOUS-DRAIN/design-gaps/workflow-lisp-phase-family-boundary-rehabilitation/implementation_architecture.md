# Workflow Lisp Phase-Family Boundary Rehabilitation Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-phase-family-boundary-rehabilitation`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected Tranche 3A phase-family boundary gap:

- make the real design-delta `plan_phase.orc` and work-item phase-family
  candidates compile as high-level Workflow Lisp phase surfaces without
  exposing `PhaseCtx`, phase state roots, generated write roots, or synthetic
  top-level context fields as public authored inputs;
- keep the already-working implementation-phase parent-callable WCC route as a
  regression guard, not as fresh design work;
- classify retained legacy `state/` inputs in the real phase-family candidates
  as private runtime context or explicit compatibility bridge bindings, with
  provenance in boundary projection and build artifacts;
- make generated helper/private workflow boundaries that carry phase-family
  context use accepted runtime-owned context transport instead of failing with
  `workflow_boundary_type_invalid`;
- preserve the WCC route and the completed WCC `IfExpr` prerequisite; if the
  route still blocks after this slice, the diagnostic must belong to another
  documented tranche.

Out of scope for this slice:

- WCC `IfExpr` support itself, which is already a separate completed
  prerequisite;
- the broader `RunCtx` / `ItemCtx` / `DrainCtx` bootstrap design beyond the
  bounded `PhaseCtx` direct-entry and helper-boundary rehabilitation needed by
  plan/work-item candidates;
- selector typed projection, variant-scoped output identity, resource
  transition ownership, parent backlog-drain composition, or promotion parity;
- changing work-item run-state semantics, terminal classification semantics,
  selector routing, or recovery decisions;
- adding new scripts, new command adapters, runtime-native effects, report
  parsing, pointer-as-state behavior, or inline semantic Python/shell glue;
- weakening the existing lint that rejects low-level state paths in promoted
  high-level `.orc` boundaries.

The success condition is narrow: the real phase-family candidates advance past
`low_level_state_path_in_high_level_module` and
`workflow_boundary_type_invalid`, while any retained legacy state values are
machine-labeled as private or compatibility bridge inputs rather than normal
public `.orc` inputs.

## Problem Statement

The post-foundation design now treats WCC schema 2 as the accepted compiler
route for new nested-control work. The real implementation phase already has
parent-callable compile and smoke evidence under WCC. The work-item route has
advanced past the old returned-variant and `IfExpr` blockers and now exposes
the Tranche 3A boundary problem.

The real work-item fixture still declares a high-level entry boundary shaped
like a YAML-era phase wrapper:

- `phase-ctx PhaseCtx`;
- `selection_bundle_path SelectionBundlePath`;
- `manifest_path StateFileExisting`;
- `architecture_bundle_path StateFile`;
- `progress_ledger_path ProgressLedger`;
- `run_state_path RunStatePath`;
- ordinary public document/artifact inputs such as steering, target design,
  baseline design, and provider choices.

Those inputs mix three different authority classes:

1. runtime-owned context (`PhaseCtx` fields);
2. compatibility bridge state values from legacy YAML/workflow-family state;
3. genuine public authored inputs.

Current lowerers and boundary projection can already represent generated
internal inputs, managed write roots, runtime-owned context inputs, and
compatibility bridge inputs in some routes. The missing capability is applying
that split to the real phase-family entry surfaces and generated
helper/private workflow boundaries, then making the lints inspect the split
rather than treating every flattened `state/` path as public API.

Fresh current-state evidence before this draft:

```bash
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py::test_design_delta_work_item_candidate_is_blocked_by_phase_family_boundary -q
```

Result: `1 passed in 0.47s`. The test still expects the work-item route to be
blocked by a post-`IfExpr` phase-family boundary diagnostic.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`;
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  Sections 14.1-14.4A, 18.2, 25.1, and 27.4A;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 19, 20, 74,
  and 83;
- `docs/design/workflow_lisp_core_calculus_middle_end.md`;
- `docs/design/workflow_lisp_state_layout.md`;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, and `specs/state.md`;
- the real design-delta candidates under
  `workflows/library/lisp_frontend_design_delta/` and
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`;
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
- `tests/test_workflow_lisp_build_artifacts.py`;
- `tests/test_workflow_lisp_key_migrations.py`.

Guardrails:

- Keep Workflow Lisp frontend ownership under `orchestrator/workflow_lisp/`;
  shared validation and runtime execution remain under `orchestrator/workflow/`.
- Reuse `WorkflowSignature`, `WorkflowBoundaryProjection`,
  `GeneratedInternalInput`, `PrivateExecContextBinding`,
  `WorkflowProvenance`, `StateLayout` / `PathAllocator`, source maps, and
  Semantic IR projections. Do not introduce a second boundary metadata model.
- Keep WCC schema 2 as the only new compiler lane. Do not reintroduce
  helper-hoisting or bespoke work-item lowerers.
- Keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files/materialized views as representations.
- Do not relax `low_level_state_path_in_high_level_module`; make the public
  boundary accurate so the lint no longer sees private or compatibility bridge
  values as public high-level API.
- Command-backed work-item helpers remain governed by
  `docs/design/workflow_command_adapter_contract.md`. This slice may preserve
  existing certified/declared adapter calls in fixtures, but it must not add
  hidden command glue or treat scripts as a solution to boundary transport.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/1/design-gap-architect/existing-architecture-index.md`
was reviewed. The full index-listed corpus was scanned for scope, ownership,
and conflict sections so this slice does not redefine shared concepts.

Directly constraining slices read closely:

- `workflow-boundary-type-flattening`;
- `phase-context-stdlib`;
- `workflow-lisp-promoted-entry-hidden-reusable-call-binding`;
- `workflow-lisp-state-layout-path-allocator-foundation`;
- `workflow-lisp-wcc-ifexpr-work-item-route`;
- `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`;
- `frontend-required-lints`;
- `workflow-lisp-expression-traversal-prerequisite`;
- `source-map-runtime-lineage`;
- `workflow-core-ast-lowering-structured-results`;
- `defproc-procedural-substrate`;
- `workflow-lisp-lowering-core-family-decomposition`;
- `workflow-lisp-typecheck-family-decomposition`;
- `resume-or-start-reusable-state-validation`;
- `resource-drain-library`.

### Decisions Reused

- Reuse `WorkflowBoundaryProjection` as the bridge between typed frontend
  signatures and flat runtime-compatible contracts.
- Reuse generated internal inputs with reasons:
  `managed_write_root` for compiler-owned write roots and
  `runtime_owned_context` for runtime-owned context leaves.
- Reuse `PrivateExecContextBinding` as the provenance record for hidden
  `PhaseCtx` transport.
- Reuse `compatibility_bridge_inputs` as the machine-readable label for
  retained legacy state/path values that are not normal public Workflow Lisp
  API.
- Reuse Stage 5 `RunCtx`, `PhaseCtx`, `with-phase`, and structural/capability
  context recognition. No second context record family is introduced.
- Reuse WCC's route discipline: new post-foundation compiler-lane behavior
  extends WCC or boundary projection around WCC output; it does not create a
  second helper/private-workflow lowering route.
- Reuse the command-adapter contract's distinction between certified adapter
  behavior and hidden semantic glue.

### New Decisions In This Slice

- Add a bounded phase-family boundary classification pass for compiled
  Workflow Lisp entry workflows. It classifies flattened boundary fields as:
  `public_authored`, `runtime_owned_context`, `compatibility_bridge`, or
  `generated_internal`.
- Permit a direct promoted phase-family entry workflow to hide its own
  top-level `PhaseCtx` flattened fields as `runtime_owned_context`, not only
  hidden `PhaseCtx` values required by a child call.
- Define a conservative compatibility bridge policy for the real design-delta
  phase-family path inputs:
  - `ProgressLedger`, `RunStatePath`, `StateFile`, `StateFileExisting`, and
    `SelectionBundlePath` under `state/` are compatibility bridge candidates
    only when selected by this phase-family route;
  - document/artifact inputs such as steering, target design, baseline design,
    plans, reports, and provider choices remain public authored inputs unless
    another accepted design reclassifies them;
  - any compatibility bridge input must be listed in boundary projection and
    provenance before the low-level-state lint ignores it as public API.
- Require generated helper/private workflows that carry `PhaseCtx` to use the
  same runtime-owned context binding metadata as entry workflows. They must
  not pass structured `PhaseCtx` through an invalid public workflow boundary.
- Make build-artifact inspection the acceptance surface: public inputs,
  private runtime context bindings, private managed write roots, and
  compatibility bridge inputs must be separately visible in
  `workflow_boundary_projection.json`.

### Conflicts Or Revisions

The promoted-entry hidden-binding slice focused on an entry workflow calling a
child workflow that required `RunCtx` / `PhaseCtx`. This slice narrows and
extends that decision:

- a direct phase-family entry may itself require `PhaseCtx`;
- that top-level `PhaseCtx` can be satisfied as runtime-owned context for the
  selected phase-family route;
- synthetic top-level `PhaseCtx` defaults remain compatibility-only and do not
  count as parent-callable boundary evidence.

The boundary-flattening slice separated authored inputs from generated internal
write-root inputs. This slice adds one more classification for retained legacy
state values: compatibility bridge inputs are not public authored inputs and
not generated runtime context. They are explicit migration bridges with
provenance.

No shared concept is redefined. Core Workflow AST, Semantic Workflow IR,
Executable IR, TypeCatalog, SourceMap, pointer authority, variant proof,
command-step semantics, and runtime state authority remain with their existing
owners.

## Ownership Boundaries

This slice owns:

- phase-family boundary classification for selected Workflow Lisp entry
  workflows;
- direct-entry `PhaseCtx` runtime-owned context projection;
- compatibility bridge labeling for retained legacy `state/` path inputs in
  real design-delta phase-family candidates;
- helper/private workflow boundary transport for phase-family `PhaseCtx`
  values;
- low-level-state lint integration with the public/private/compatibility
  boundary split;
- build-artifact/source-map/provenance coverage for the new classifications;
- focused feasibility, build-artifact, and smoke tests proving the selected
  phase-family routes clear the Tranche 3A diagnostics.

This slice intentionally does not own:

- the semantic meaning of work-item run-state updates or recovery decisions;
- resource-transition or ledger-update replacement;
- selector bundle typed projection;
- parent drain composition or promotion gates;
- command adapter declaration ergonomics beyond preserving existing adapter
  certification rules;
- broad repo-wide lint enforcement for legacy YAML or unrelated `.orc`
  workflows.

## Current Checkout Facts

- `orchestrator/workflow_lisp/contracts.py` defines
  `GeneratedInternalInput`, `WorkflowBoundaryProjection`, and union/record
  flattening metadata.
- `orchestrator/workflow_lisp/lowering/workflow_calls.py` already records
  `runtime_owned_context` generated inputs for eligible child calls and emits
  `PrivateExecContextBinding`.
- `orchestrator/workflow_lisp/lowering/core.py` already separates
  `managed_write_root_inputs` from `runtime_context_inputs` when validating
  lowered workflows.
- `orchestrator/workflow_lisp/build.py` serializes public inputs, private
  runtime context bindings, private managed write roots, and compatibility
  bridge inputs in `workflow_boundary_projection.json`.
- Existing tests prove the generic promoted-entry hidden context route and
  compatibility bridge serialization on synthetic fixtures.
- Existing design-delta work-item tests still expect real work-item and parent
  work-item compile/smoke routes to fail before execution, after old
  returned-variant and `IfExpr` blockers are excluded.
- The real work-item fixture contains command-backed helpers. Those helpers
  are not the boundary problem, but their adapter status must remain visible
  and cannot be used to hide new phase-boundary semantics.

## Proposed Architecture

### 1. Phase-Family Boundary Classification

Add a frontend-owned classifier that runs after typed workflow signatures and
boundary flattening are available, before public input contracts and lints are
finalized.

Conceptual record:

```text
PhaseFamilyBoundaryClassification
  workflow_name
  route_kind: direct_phase_entry | phase_child_helper | ordinary_workflow
  public_authored_inputs
  runtime_owned_context_inputs
  compatibility_bridge_inputs
  generated_internal_inputs
  source_provenance
```

The classifier is intentionally conservative. It activates only for selected
phase-family workflows that meet all of these conditions:

- the workflow is compiled as a Workflow Lisp entry or generated/private child
  in the linked phase-family graph;
- the workflow has a structurally recognized `PhaseCtx` parameter or receives
  phase context from a caller;
- the workflow body establishes one unambiguous phase identity through
  existing `with-phase` / phase-scope analysis, or the parent call provides a
  recognized phase-family context;
- the lowered route is WCC-compatible or already accepted legacy
  compatibility; and
- all non-public state/path inputs are classifiable as runtime-owned context,
  managed generated inputs, or compatibility bridge inputs.

If any state/path input cannot be classified, the existing
`low_level_state_path_in_high_level_module` lint remains blocking.

### 2. Direct Entry `PhaseCtx` Bootstrap

Extend the existing runtime-owned context transport so a direct phase-family
entry workflow may declare `(phase-ctx PhaseCtx)` while public boundary
inspection hides its flattened leaves.

Implementation direction:

- derive flattened fields for the top-level `PhaseCtx` parameter using the
  existing boundary flattening logic;
- move those fields from public authored inputs to
  `GeneratedInternalInput(reason="runtime_owned_context")`;
- emit a `PrivateExecContextBinding` with:
  - `context_family="PhaseCtx"`;
  - `bridge_class="runtime_owned_context"`;
  - generated flattened input names;
  - derived phase identity from existing phase analysis;
  - source provenance pointing to the `defworkflow` parameter and `with-phase`
    form;
- make runtime input contracts include those fields while public input helpers
  exclude them;
- preserve source-map and boundary-projection entries so diagnostics can still
  explain the hidden fields.

This is not a new public defaulting rule. Authored callers still cannot rely on
synthetic `PhaseCtx` defaults as promotion evidence.

### 3. Compatibility Bridge Inputs For Legacy State Paths

Add a narrow compatibility bridge classifier for selected phase-family
boundary fields that are still legacy YAML/workflow-family state values.

Initial candidate families for this slice:

- `SelectionBundlePath`;
- `ProgressLedger`;
- `RunStatePath`;
- `StateFile`;
- `StateFileExisting`;
- equivalent flattened fields whose path contract is under `state/` and whose
  parameter name matches the real design-delta work-item/plan bridge roles.

Classification rules:

- compatibility bridge inputs remain part of the runtime contract while the
  legacy migration route needs them;
- they are excluded from public high-level `.orc` input contracts and listed
  in `private_compatibility_bridge_inputs`;
- they retain source provenance and path contracts;
- they are not semantic authority for new high-level Workflow Lisp code;
- they do not count as parent-drain promotion evidence except as explicitly
  labeled migration bridge values.

The classifier must not hide arbitrary `state/` paths. Inputs such as real user
documents, prompt assets, provider choices, and artifact/report targets remain
public or generated according to existing contracts.

### 4. Helper/Private Workflow Phase Context Transport

Generated helper/private workflows used by the real work-item route must not
fail because `PhaseCtx` is an invalid public boundary type. The implementation
should reuse the same metadata lane used for direct entries:

- when a private workflow captures or receives phase-family context, represent
  flattened `PhaseCtx` leaves as runtime-owned generated inputs or as explicit
  call bindings sourced from an ancestor runtime-owned context;
- preserve the helper's source-map origin and phase identity;
- reject ambiguous phase-context capture with a phase-family-specific
  diagnostic rather than falling back to `workflow_boundary_type_invalid`;
- leave ordinary user-authored workflows subject to the existing boundary type
  rules.

This keeps helper/private workflow generation compatible with WCC without
reintroducing a bespoke helper-hoisting route.

### 5. Lint And Boundary Inspection

Update the low-level state-path lint to consume boundary classification:

- public authored `state/` path inputs in high-level phase-family workflows
  still emit `low_level_state_path_in_high_level_module`;
- runtime-owned `PhaseCtx` fields do not emit that lint because they are no
  longer public authored inputs;
- compatibility bridge inputs do not emit that lint as public API, but they
  must appear in boundary projection and may emit warning/info migration debt
  if the active lint profile supports that severity;
- generated managed write roots remain internal and lint-exempt as public API.

Build-artifact acceptance should inspect:

- `workflow_boundary_projection.json`;
- `source_map.json` generated input/source frames;
- loaded bundle provenance, when validation succeeds;
- lowered workflow compatibility bridge metadata, when shared validation is
  intentionally bypassed for a focused artifact test.

### 6. Command Adapter Boundary

No new command behavior is introduced. Existing work-item command-backed
helpers remain under the command-adapter contract:

- certified adapter calls keep typed input/output/effect metadata;
- raw external-tool commands that mutate run state remain migration debt for
  later resource-transition ownership;
- this slice must not convert boundary classification into hidden command
  semantics.

## Proposed Code Footprint

Likely owned files:

- `orchestrator/workflow_lisp/contracts.py`
  - extend boundary projection metadata or helper APIs to support the
    phase-family privacy split without changing `WorkflowSignature` authority;
- `orchestrator/workflow_lisp/lowering/core.py`
  - apply direct-entry `PhaseCtx` classification and pass runtime context /
    compatibility bridge metadata into shared validation;
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - reuse/extend private `PhaseCtx` binding for helper/private workflow
    boundaries;
- `orchestrator/workflow_lisp/lowering/phase_scope.py` or `phase.py`
  - expose the bounded phase identity derivation helper if it is not already
    reusable for direct entries;
- `orchestrator/workflow_lisp/lints.py`
  - make `low_level_state_path_in_high_level_module` use the classified public
    boundary rather than raw flattened input names;
- `orchestrator/workflow_lisp/build.py`
  - ensure the new phase-family classifications serialize through existing
    boundary projection artifacts;
- `orchestrator/workflow_lisp/source_map.py` or lowering origin helpers
  - add source provenance only if existing generated-input source-map coverage
    does not already cover direct entry `PhaseCtx` fields.

Likely test files:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
- `tests/test_workflow_lisp_build_artifacts.py`;
- `tests/test_workflow_lisp_key_migrations.py`;
- narrow fixture updates under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` only
  when the real candidate needs expected compatibility labels.

## Diagnostics

Reuse existing diagnostics where they remain accurate:

- `low_level_state_path_in_high_level_module`;
- `workflow_boundary_type_invalid`;
- `promoted_entry_hidden_phase_ctx_ambiguous`;
- `workflow_boundary_projection_missing_origin`.

Add narrow diagnostics only if existing codes cannot identify the failure:

- `phase_family_boundary_context_unclassified`
  - a selected phase-family workflow has a `PhaseCtx`-like field that cannot
    be derived as runtime-owned context;
- `phase_family_compatibility_bridge_unclassified`
  - a selected phase-family workflow has a `state/` path input that is neither
    public by contract nor accepted as a compatibility bridge;
- `phase_family_helper_context_boundary_invalid`
  - a generated helper/private workflow attempted to expose phase context
    through a public boundary instead of generated/private transport.

Diagnostics should include workflow name, parameter or generated field name,
source span, inferred authority class, and suggested next owner tranche when
the failure belongs to typed projection, resource transition, or parent drain.

## Test Strategy

### Focused Regression Tests

- The implementation-phase parent-callable compile/smoke tests continue to
  pass under WCC.
- The completed WCC `IfExpr` characterization and work-item route tests still
  prove the route is past unsupported `IfExpr`.
- Returned-variant tests continue to prove work-item does not regress to
  `union_return_variant_ambiguous`.

### Boundary Classification Tests

- A direct phase entry with top-level `PhaseCtx` exposes runtime context fields
  in runtime inputs but not public inputs.
- `workflow_boundary_projection.json` lists private runtime context bindings
  for direct phase entries.
- Real `plan_phase.orc` no longer fails because `PhaseCtx` or phase state roots
  are public high-level inputs.
- Real `work_item.orc` no longer fails because `PhaseCtx`, `SelectionBundlePath`,
  `ProgressLedger`, `RunStatePath`, `StateFile`, or `StateFileExisting` are
  public high-level state-path inputs.
- Retained legacy state values appear in
  `private_compatibility_bridge_inputs`.

### Helper/Private Workflow Tests

- The approved-arm helper/private-workflow route used by the real work-item
  candidate clears `workflow_boundary_type_invalid` when carrying phase-family
  context.
- Ambiguous helper phase-context capture fails with a phase-family diagnostic.

### Lint Tests

- Public authored `state/` inputs outside the selected compatibility bridge
  route still fail with `low_level_state_path_in_high_level_module`.
- Compatibility bridge inputs are not presented as public inputs.
- Generated managed write roots remain excluded from public input contracts.

### Smoke Tests

- Work-item complete and blocked-recovery route tests advance from expected
  compile failure to controlled fake-runtime smoke once the boundary gap is
  cleared.
- Parent-call work-item smoke tests advance past the phase-family boundary; if
  they still fail, they must fail with a diagnostic owned by a later tranche.

## Implementation Sequence

1. Add a characterization test that inspects the current failure diagnostics
   for the real work-item route and asserts old blockers are absent.
2. Add the phase-family boundary classifier over existing boundary projection
   data, initially testable without changing runtime behavior.
3. Reclassify direct-entry `PhaseCtx` flattened fields as
   `runtime_owned_context` for selected phase-family workflows.
4. Reclassify selected legacy `state/` path inputs as compatibility bridges and
   serialize them through existing boundary projection surfaces.
5. Wire helper/private workflow `PhaseCtx` transport through runtime-owned
   context bindings instead of public workflow boundary fields.
6. Update the low-level-state lint to use classified public inputs.
7. Update real design-delta work-item/plan tests from expected boundary
   failure to compile/build-artifact assertions, then to smoke assertions where
   runtime fixtures already exist.
8. Run focused tests first, then the Workflow Lisp regression band named in
   the check-command bundle.

## Acceptance Conditions

- The real design-delta implementation-phase candidate keeps parent-callable
  compile and smoke evidence under WCC.
- The real design-delta work-item candidate no longer fails on WCC `IfExpr`.
- The remaining real design-delta `plan_phase.orc` and `work_item.orc`
  candidates no longer fail parent-callable compilation on
  `low_level_state_path_in_high_level_module`.
- The approved-arm helper/private-workflow route introduced by work-item
  composition no longer fails on `workflow_boundary_type_invalid` when it
  carries phase-family context.
- Public boundary inspection excludes `PhaseCtx` leaves, generated write
  roots, and retained compatibility `state/` values from public authored
  inputs.
- Boundary projection and source maps identify runtime-owned context bindings
  and compatibility bridge inputs with source provenance.
- Any remaining compile failure after this slice is another documented tranche
  diagnostic, not boundary/path exposure or invalid phase-helper boundary type.
- No new command glue, report parsing, pointer authority, resource transition,
  or parent-drain semantics are introduced.

## Verification Plan

Implementation should verify with narrow selectors first:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or parent_call_work_item or plan_phase_candidate or implementation_phase_candidate" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or runtime_context_inputs or compatibility_bridge or public_inputs" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_characterization.py -q
git diff --check
```

If test names change during implementation, keep the same evidence roles:
collect-only for changed modules, design-delta phase-family compile/smoke,
boundary projection/public-input inspection, WCC regression coverage, and
whitespace validation.
