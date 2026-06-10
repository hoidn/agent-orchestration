# Workflow Lisp Phase-Family Boundary Rehabilitation Post-IfExpr Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-phase-family-boundary-rehabilitation-post-ifexpr`
Target design: `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected post-IfExpr Tranche 3A phase-family
boundary gap:

- finish the real design-delta `plan_phase.orc` and `work_item.orc`
  phase-family routes so promoted high-level boundaries do not expose
  `PhaseCtx` leaves, phase state roots, generated write roots, or retained
  YAML `state/` paths as normal public authored `.orc` inputs;
- keep the implementation-phase parent-callable WCC evidence as a regression
  guard, not fresh design work;
- preserve the completed WCC `IfExpr` prerequisite by proving the real
  work-item route has advanced past unsupported `IfExpr` and old private
  workflow export blockers before this boundary slice is judged;
- classify retained legacy state/path values as private compatibility bridge
  inputs with provenance in boundary projection, source maps, Semantic IR, and
  parity-facing artifacts;
- make generated helper/private workflow boundaries that carry phase-family
  context use accepted runtime-owned context transport instead of failing with
  `workflow_boundary_type_invalid` or equivalent helper-boundary diagnostics.

Out of scope for this slice:

- implementing WCC `IfExpr` support itself;
- adding a general `RunCtx` / `ItemCtx` / `DrainCtx` bootstrap beyond the
  bounded `PhaseCtx` direct-entry and helper-boundary rehabilitation needed by
  the real plan/work-item candidates;
- selector typed projection, variant-scoped output identity,
  resource-transition ownership, parent backlog-drain composition, or
  promotion parity;
- changing work-item run-state semantics, terminal classification semantics,
  selector routing, recovery decisions, or ledger update semantics;
- adding scripts, command adapters, runtime-native effects, report parsing,
  pointer-as-state behavior, or inline semantic Python/shell glue;
- weakening `low_level_state_path_in_high_level_module`; the implementation
  must make the public boundary accurate so the lint no longer sees private or
  compatibility bridge values as public high-level API.

The success condition is narrow: the selected phase-family routes advance past
post-IfExpr boundary failures while any remaining compile/runtime failure is
owned by another documented tranche.

## Problem Statement

The post-foundation target narrowed the dependency chain. WCC schema 2 is the
accepted route for new nested-control work, the implementation phase has
parent-callable compile and smoke evidence, and the selected work item states
that WCC `IfExpr` has cleared the real work-item route enough for Tranche 3A to
resume.

The remaining boundary problem is that real phase-family workflows still carry
YAML-era state choreography at boundaries that should be high-level Workflow
Lisp surfaces. In the real design-delta plan/work-item paths, values such as
`phase-ctx`, `selection_bundle_path`, `manifest_path`,
`architecture_bundle_path`, `progress_ledger_path`, and `run_state_path` mix
three authority classes:

1. runtime-owned phase context;
2. retained legacy YAML/workflow-family state paths needed only as
   compatibility bridges;
3. genuine public authored inputs such as documents, prompts, providers,
   reports, or artifact targets.

The current checkout already has partial substrate:

- `orchestrator/workflow_lisp/phase_family_boundary.py` defines conservative
  phase-family classification for selected `lisp_frontend_design_delta/*`
  workflows;
- `PrivateExecContextBinding`, `WorkflowBoundaryProjection`,
  `GeneratedInternalInput`, runtime context input filtering, compatibility
  bridge metadata, build artifact projection, and Semantic IR state-layout
  entries already exist;
- focused build-artifact tests already inspect plan-phase runtime context
  hiding and work-item compatibility bridge labels;
- the active feasibility test still treats the real work-item runtime and
  parent-call routes as blocked, and accepts only that old returned-variant,
  unsupported `IfExpr`, and private-workflow export blockers are absent.

This slice is therefore not "invent private context." It is the bounded
completion and proof pass that applies the existing metadata model to the real
phase-family routes, updates expected-failure tests into positive compile /
artifact / smoke evidence, and prevents later parent-drain work from treating
public state roots or synthetic `PhaseCtx` defaults as parent-callable parity.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`;
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/post_wcc_reconciliation_index.md`;
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  Sections 14.4A, 14.5, 14.6, 14.7, 18.2, 22, 25, and 29;
- `docs/design/workflow_lisp_frontend_specification.md` Sections 0, 19, 20,
  45, 47, 59, 74, 83, and the final design center;
- `docs/design/workflow_lisp_runtime_migration_foundation.md`;
- `docs/design/workflow_lisp_core_calculus_middle_end.md`;
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`;
- `docs/design/workflow_lisp_state_layout.md`;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/lisp_workflow_drafting_guide.md`;
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, and `specs/state.md`;
- the real design-delta candidates under
  `workflows/library/lisp_frontend_design_delta/`;
- runtime fixtures under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/`;
- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
- `tests/test_workflow_lisp_build_artifacts.py`;
- `tests/test_workflow_lisp_key_migrations.py`;
- `tests/test_workflow_lisp_wcc_characterization.py` and
  `tests/test_workflow_lisp_wcc_m4.py`.

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
- Do not relax `low_level_state_path_in_high_level_module`; make it consume the
  classified public boundary.
- Command-backed work-item helpers remain governed by
  `docs/design/workflow_command_adapter_contract.md`. This slice may preserve
  existing certified/declared adapter calls, but it must not add hidden command
  glue or use scripts to hide boundary transport.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The generated architecture index at
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The full listed corpus was scanned for scope,
ownership, and conflict patterns. Directly constraining slices read closely:

- `workflow-boundary-type-flattening`;
- `phase-context-stdlib`;
- `workflow-lisp-promoted-entry-hidden-reusable-call-binding`;
- `workflow-lisp-state-layout-path-allocator-foundation`;
- `workflow-lisp-wcc-ifexpr-work-item-route`;
- `workflow-lisp-imported-child-returned-variant-work-item-prerequisite`;
- `workflow-lisp-expression-traversal-prerequisite`;
- `workflow-lisp-lowering-core-family-decomposition`;
- `workflow-lisp-typecheck-family-decomposition`;
- `source-map-runtime-lineage`;
- `workflow-core-ast-lowering-structured-results`;
- `defproc-procedural-substrate`;
- `resume-or-start-reusable-state-validation`;
- `resource-drain-library`;
- `workflow-refs-compile-time-linking`.

### Decisions Reused

- Reuse `WorkflowBoundaryProjection` as the structured-to-flat boundary
  explanation and build-artifact surface.
- Reuse generated internal inputs with reason labels:
  `managed_write_root`, `runtime_owned_context`, and
  `compatibility_bridge`.
- Reuse `PrivateExecContextBinding` as the provenance record for hidden
  `PhaseCtx` transport.
- Reuse `compatibility_bridge_inputs` as the machine-readable label for
  retained legacy state/path values that are not normal public Workflow Lisp
  API.
- Reuse Stage 5 `RunCtx`, `PhaseCtx`, `with-phase`, and
  structural/capability context recognition. No second context record family
  is introduced.
- Reuse the WCC route discipline: new post-foundation compiler-lane behavior
  extends WCC or boundary projection around WCC output; it does not create a
  second helper/private-workflow lowering route.
- Reuse the command-adapter contract's distinction between certified adapter
  behavior and hidden semantic glue.

### New Decisions In This Slice

- Treat the selected `workflow-lisp-phase-family-boundary-rehabilitation`
  substrate as partial implementation evidence, not completion evidence, until
  the real work-item runtime and parent-call routes stop expecting a
  boundary-related compile failure.
- Add a post-IfExpr real-route readiness gate: acceptance tests must first
  prove unsupported `IfExpr`, returned-variant ambiguity, and old private
  workflow export blockers are absent, then prove the remaining boundary
  classes are either hidden runtime context, compatibility bridge, or another
  documented tranche.
- Keep phase-family classification explicitly selected to the design-delta
  family while this migration slice is open. Generalizing the classifier to
  arbitrary high-level phase workflows is a later private-context/bootstrap
  decision, not this slice.
- Require build-artifact and loaded-bundle inspection to show four distinct
  classes: public authored inputs, private runtime context bindings,
  compatibility bridge inputs, and generated internal write roots.
- Require the real runtime smoke tests to be updated from expected compile
  failure to positive execution only when shared validation and runtime binding
  consume those classes without user-provided synthetic `PhaseCtx` values.

### Conflicts Or Revisions

The older phase-family boundary architecture described the same target before
the selected post-IfExpr work item was generated. This slice narrows it:

- WCC `IfExpr` is treated as a completed prerequisite, not as work here.
- Existing phase-family classification code is treated as current substrate to
  preserve and finish, not as a greenfield design.
- The direct implementation-phase WCC route is a regression guard; this slice
  focuses on plan and work-item routes plus generated helper/private workflow
  context transport.

The promoted-entry hidden-binding slice focused on an entry workflow calling a
child workflow requiring `RunCtx` / `PhaseCtx`. This slice extends that decision
narrowly:

- a direct phase-family entry may itself require `PhaseCtx`;
- that top-level `PhaseCtx` can be satisfied as runtime-owned context for the
  selected phase-family route;
- synthetic top-level `PhaseCtx` defaults remain compatibility-only and do not
  count as parent-callable boundary evidence.

No shared concept is redefined. Core Workflow AST, Semantic Workflow IR,
Executable IR, TypeCatalog, SourceMap, pointer authority, variant proof,
command-step semantics, and runtime state authority remain with their existing
owners.

## Ownership Boundaries

This slice owns:

- selected phase-family boundary classification completion for real
  design-delta plan/work-item entry workflows;
- direct-entry `PhaseCtx` runtime-owned context projection where selected;
- compatibility bridge labeling for retained legacy `state/` path inputs in
  real design-delta phase-family candidates;
- generated helper/private workflow transport for phase-family `PhaseCtx`
  values;
- low-level-state lint integration with the public/private/compatibility
  boundary split;
- build-artifact, source-map, provenance, and Semantic IR coverage for the new
  classifications;
- focused feasibility, build-artifact, WCC regression, and smoke tests proving
  the selected routes clear the Tranche 3A diagnostics.

This slice intentionally does not own:

- semantic meaning of work-item run-state updates or recovery decisions;
- selector bundle typed projection;
- resource-transition or ledger-update replacement;
- parent drain composition or promotion gates;
- command adapter declaration ergonomics beyond preserving existing adapter
  certification rules;
- broad repo-wide lint enforcement for legacy YAML or unrelated `.orc`
  workflows.

## Current Checkout Facts And Feasibility

Current substrate present in the checkout:

- `phase_family_boundary.py` classifies selected phase-family flattened inputs
  into runtime-owned context inputs and compatibility bridge inputs.
- `lowering/core.py` and `wcc/defunctionalize.py` call the classifier and
  thread runtime context / compatibility bridge metadata.
- `loaded_bundle.workflow_public_input_contracts(...)` excludes runtime
  context and compatibility bridge inputs from public input contracts.
- `workflow_boundary_projection.json` serializes private runtime context
  bindings and private compatibility bridge inputs.
- `semantic_ir.py` emits state-layout entries for compatibility bridge inputs.
- `tests/test_workflow_lisp_build_artifacts.py` already has coverage for
  design-delta plan-phase hidden `PhaseCtx` and work-item bridge labels.

Current proof gap:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py` still
  expects real work-item runtime and parent-call routes to raise
  `LispFrontendCompileError`;
- the assertion now only requires that old blockers are absent and a distinct
  downstream diagnostic or successful compile exists;
- this slice must convert those expected failures into compile/shared
  validation/build-artifact evidence and then controlled fake-runtime smoke
  where fixtures already exist.

Feasibility proof:

- no runtime executor replacement is required because the needed public/private
  input filtering, runtime context binding, and compatibility bridge projection
  surfaces already exist;
- no new semantic command glue is needed because existing work-item helpers are
  already represented as command boundaries and remain governed by the adapter
  contract;
- the remaining work is to tighten eligibility, provenance, and call/helper
  context transport and to update real-route tests from expected failure to
  positive evidence.

## Proposed Architecture

### 1. Post-IfExpr Readiness Gate

Before changing boundary behavior, keep a characterization assertion that the
real work-item route is past the completed prerequisites:

- no `union_return_variant_ambiguous`;
- no `union_return_variant_incompatible`;
- no unsupported `IfExpr` WCC diagnostic;
- no old private-workflow `IfExpr` export blocker;
- any remaining diagnostic is either this slice's boundary issue or another
  documented tranche.

This prevents Tranche 3A from masking a regression in returned-variant,
IfExpr, or WCC route behavior.

### 2. Phase-Family Boundary Classification Completion

Continue using a conservative classifier over existing boundary projection
data:

```text
PhaseFamilyBoundaryClassification
  workflow_name
  runtime_owned_context_inputs
  compatibility_bridge_inputs
  generated_internal_inputs
  public_authored_inputs
  source_provenance
```

The classifier activates only for selected design-delta phase-family workflows
and generated/private children in that linked graph. It must not hide arbitrary
`state/` paths outside this selected route.

Classification rules:

- structurally recognized `PhaseCtx` flattened leaves are
  `runtime_owned_context`;
- selected legacy inputs such as `SelectionBundlePath`, `ProgressLedger`,
  `RunStatePath`, `StateFile`, and `StateFileExisting` are
  `compatibility_bridge` only when their root parameter name matches the real
  plan/work-item bridge role;
- managed write-root generated paths remain `generated_internal`;
- ordinary document, prompt, provider, plan, design, report, and artifact
  inputs remain `public_authored` unless another accepted design owns a
  reclassification.

If any low-level state/path input cannot be classified, the existing
`low_level_state_path_in_high_level_module` diagnostic remains blocking.

### 3. Direct Entry `PhaseCtx` Bootstrap

A selected direct phase-family entry workflow may declare `(phase-ctx PhaseCtx)`
while public boundary inspection hides its flattened leaves.

Implementation direction:

- derive flattened fields for the top-level `PhaseCtx` parameter using the
  existing boundary flattening logic;
- move those fields from public authored inputs to
  `GeneratedInternalInput(reason="runtime_owned_context")`;
- emit a `PrivateExecContextBinding` with `context_family="PhaseCtx"`,
  `bridge_class="runtime_owned_context"`, generated flattened input names,
  required capabilities, derived phase identity, and source provenance pointing
  to the `defworkflow` parameter and phase scope;
- keep runtime input contracts complete while public input helpers exclude
  the generated fields;
- preserve source-map and boundary-projection entries so diagnostics can still
  explain the hidden fields.

This is not a new public defaulting rule. Authored callers cannot rely on
synthetic `PhaseCtx` defaults as promotion evidence.

### 4. Compatibility Bridge Inputs For Legacy State Paths

Retained YAML-era values may survive only as compatibility bridge inputs:

- they remain executable/runtime inputs while the legacy migration route needs
  them;
- they are excluded from public high-level `.orc` input contracts;
- they appear in `private_compatibility_bridge_inputs`;
- they retain source provenance and path contracts;
- they do not become semantic authority for new high-level Workflow Lisp code;
- they do not count as parent-drain promotion evidence except as explicitly
  labeled migration bridge values.

The initial selected bridge roots are:

- `selection_bundle_path`;
- `manifest_path`;
- `architecture_bundle_path`;
- `progress_ledger_path`;
- `run_state_path`.

### 5. Helper/Private Workflow Phase Context Transport

Generated helper/private workflows used by the real work-item route must not
expose structured `PhaseCtx` through invalid public workflow boundaries.

Required behavior:

- if a generated/private workflow captures or receives phase-family context,
  represent flattened `PhaseCtx` leaves as runtime-owned generated inputs or
  explicit call bindings sourced from an ancestor runtime-owned context;
- preserve helper source-map origin, WCC scope, phase identity, and call-frame
  provenance;
- reject ambiguous phase-context capture with a phase-family diagnostic rather
  than falling back to a generic `workflow_boundary_type_invalid`;
- leave ordinary user-authored workflows subject to existing boundary type
  rules.

### 6. Lint, Shared Validation, And Artifact Inspection

Update consumers to inspect classified boundaries:

- public authored `state/` path inputs in high-level phase-family workflows
  still emit `low_level_state_path_in_high_level_module`;
- runtime-owned `PhaseCtx` fields do not emit that lint because they are no
  longer public authored inputs;
- compatibility bridge inputs do not emit that lint as public API, but they
  remain visible as migration debt;
- generated managed write roots remain internal and lint-exempt as public API.

Build-artifact acceptance should inspect:

- `workflow_boundary_projection.json`;
- `source_map.json`;
- loaded bundle public/runtime input helpers;
- Semantic IR state-layout entries for compatibility bridge and runtime
  context inputs.

### 7. Command Adapter Boundary

No new command behavior is introduced.

Existing work-item command-backed helpers remain under
`docs/design/workflow_command_adapter_contract.md`:

- certified adapter calls keep typed input/output/effect metadata;
- raw external-tool commands that mutate run state remain migration debt for
  later resource-transition ownership;
- this slice must not convert boundary classification into hidden command
  semantics.

## Proposed Code Footprint

Likely owned files:

- `orchestrator/workflow_lisp/phase_family_boundary.py`
  - tighten the selected-route classifier and expose any missing provenance
    helpers;
- `orchestrator/workflow_lisp/lowering/core.py`
  - apply direct-entry `PhaseCtx` classification and pass runtime context /
    compatibility bridge metadata into shared validation;
- `orchestrator/workflow_lisp/wcc/defunctionalize.py`
  - keep WCC route output aligned with the same classification model;
- `orchestrator/workflow_lisp/lowering/workflow_calls.py`
  - reuse/extend private `PhaseCtx` binding for helper/private workflow
    boundaries;
- `orchestrator/workflow_lisp/lowering/phase_scope.py` or
  `orchestrator/workflow_lisp/phase.py`
  - expose bounded phase identity derivation if direct entries and helper
    calls still duplicate it;
- `orchestrator/workflow_lisp/compiler.py` and
  `orchestrator/workflow_lisp/lints.py`
  - ensure `low_level_state_path_in_high_level_module` uses classified public
    inputs rather than raw flattened input names;
- `orchestrator/workflow_lisp/build.py` and
  `orchestrator/workflow_lisp/source_map.py`
  - ensure projection/source-map serialization covers real route metadata;
- `orchestrator/workflow/semantic_ir.py`
  - only if existing state-layout projection lacks a required entry for the
    real route.

Likely test files:

- `tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py`;
- `tests/test_workflow_lisp_build_artifacts.py`;
- `tests/test_workflow_lisp_key_migrations.py`;
- `tests/test_workflow_lisp_wcc_characterization.py`;
- `tests/test_workflow_lisp_wcc_m4.py`;
- fixtures under
  `tests/fixtures/workflow_lisp/valid/design_delta_work_item_runtime/` only
  when expected runtime inputs or artifact assertions need updating.

## Diagnostics

Reuse existing diagnostics where accurate:

- `low_level_state_path_in_high_level_module`;
- `workflow_boundary_type_invalid`;
- `workflow_boundary_projection_missing_origin`;
- existing promoted-entry context diagnostics.

Add narrow diagnostics only if existing codes cannot identify the selected
failure:

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

- Implementation-phase parent-callable compile/smoke tests continue to pass
  under WCC.
- WCC `IfExpr` characterization and work-item route tests still prove the
  route is past unsupported `IfExpr`.
- Returned-variant tests continue to prove work-item does not regress to
  `union_return_variant_ambiguous`.

### Boundary Classification Tests

- A direct phase entry with top-level `PhaseCtx` exposes runtime context fields
  in runtime inputs but not public inputs.
- `workflow_boundary_projection.json` lists private runtime context bindings
  for direct phase entries.
- Real `plan_phase.orc` no longer fails because `PhaseCtx` or phase state
  roots are public high-level inputs.
- Real `work_item.orc` no longer fails because `PhaseCtx`,
  `SelectionBundlePath`, `ProgressLedger`, `RunStatePath`, `StateFile`, or
  `StateFileExisting` are public high-level state-path inputs.
- Retained legacy state values appear in
  `private_compatibility_bridge_inputs`.

### Helper/Private Workflow Tests

- The approved-arm helper/private workflow route used by the real work-item
  candidate clears `workflow_boundary_type_invalid` or any replacement
  helper-boundary diagnostic when carrying phase-family context.
- Ambiguous helper phase-context capture fails with a phase-family diagnostic.

### Lint And Artifact Tests

- Public authored `state/` inputs outside the selected compatibility bridge
  route still fail with `low_level_state_path_in_high_level_module`.
- Compatibility bridge inputs are not presented as public inputs.
- Generated managed write roots remain excluded from public input contracts.
- Source maps and Semantic IR identify runtime context and compatibility
  bridge provenance.

### Smoke Tests

- Work-item complete and blocked-recovery route tests advance from expected
  compile failure to controlled fake-runtime smoke once the boundary gap is
  cleared.
- Parent-call work-item smoke tests advance past the phase-family boundary. If
  they still fail, they must fail with a diagnostic owned by a later tranche.

## Implementation Sequence

1. Keep or add a characterization test that proves the real work-item route is
   past returned-variant, WCC `IfExpr`, and old private-workflow export
   blockers.
2. Audit current `phase_family_boundary.py` behavior against the real
   plan/work-item flattened inputs and document any unclassified fields before
   changing lints.
3. Tighten direct-entry `PhaseCtx` runtime-owned context projection for the
   selected phase-family workflows.
4. Tighten selected legacy `state/` path compatibility bridge classification
   and serialization through boundary projection, source maps, and Semantic IR.
5. Wire helper/private workflow `PhaseCtx` transport through runtime-owned
   context bindings or ancestor call bindings rather than public workflow
   boundary fields.
6. Update the low-level-state lint to use classified public inputs.
7. Convert real design-delta work-item/plan expected-failure tests into
   compile/build-artifact assertions, then smoke assertions where runtime
   fixtures already exist.
8. Run focused tests first, then the Workflow Lisp regression band named in
   the check-command bundle.

## Acceptance Conditions

- The real design-delta implementation-phase candidate keeps parent-callable
  compile and smoke evidence under WCC.
- The real design-delta work-item candidate remains past unsupported WCC
  `IfExpr`, returned-variant ambiguity, and private-workflow export blockers.
- The remaining real design-delta `plan_phase.orc` and `work_item.orc`
  candidates no longer fail parent-callable compilation on
  `low_level_state_path_in_high_level_module`.
- The approved-arm helper/private workflow route introduced by work-item
  composition no longer fails on `workflow_boundary_type_invalid` or
  equivalent invalid phase-context boundary diagnostics.
- Public boundary inspection excludes `PhaseCtx` leaves, generated write
  roots, and retained compatibility `state/` values from public authored
  inputs.
- Boundary projection, source maps, loaded-bundle helpers, and Semantic IR
  identify runtime-owned context bindings and compatibility bridge inputs with
  source provenance.
- Any remaining compile failure after this slice is another documented tranche
  diagnostic, not boundary/path exposure or invalid phase-helper boundary type.
- No new command glue, report parsing, pointer authority, resource transition,
  or parent-drain semantics are introduced.

## Verification Plan

Implementation should verify with narrow selectors first:

```bash
python -m pytest --collect-only tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_key_migrations.py tests/test_workflow_lisp_wcc_characterization.py tests/test_workflow_lisp_wcc_m4.py -q
python -m pytest tests/test_workflow_lisp_design_delta_drain_migration_feasibility.py -k "work_item_candidate or parent_call_work_item or plan_phase_candidate or implementation_phase_candidate or wcc_ifexpr" -q
python -m pytest tests/test_workflow_lisp_build_artifacts.py -k "design_delta_work_item or design_delta_plan_phase_boundary or runtime_context_inputs or compatibility_bridge or public_inputs" -q
python -m pytest tests/test_workflow_lisp_key_migrations.py -k "runtime_context or public_inputs or promoted_entry" -q
python -m pytest tests/test_workflow_lisp_wcc_m4.py tests/test_workflow_lisp_wcc_characterization.py -q
git diff --check
```

If test names change during implementation, keep the same evidence roles:
collect-only for changed modules, design-delta phase-family compile/smoke,
boundary projection and public-input inspection, promoted-entry context
regression coverage, WCC regression coverage, and whitespace validation.
