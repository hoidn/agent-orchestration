# Semantic Workflow IR Shared Contract Implementation Architecture

## Scope

This design gap covers only the bounded shared Semantic Workflow IR slice
selected for the Workflow Lisp frontend full-design drain:

- define one shared `SemanticWorkflowIR` contract between validated workflow
  meaning and the existing executable/runtime bundle;
- construct and validate Semantic IR for workflows loaded through the shared
  loader path, covering both YAML-authored workflows and compiled Workflow Lisp
  workflows;
- serialize `semantic_ir.json` for compiled Workflow Lisp builds and stop
  treating `semantic_ir` as a deferred artifact;
- preserve the existing executable/runtime path and `runtime_plan` contract
  while adding Semantic IR as a first-class shared bundle surface;
- record command boundaries, contracts, refs, effects, proofs, state layout,
  and source-map references without interpreting shell text or reports as
  semantic authority.

Out of scope for this tranche:

- new frontend language forms, new stdlib forms, or revisions to parsing,
  modules, macros, procedures, workflow refs, phase/resource/drain lowering, or
  runtime execution behavior;
- a separately implemented Core Workflow AST package or serialized
  `core_workflow_ast.json` artifact;
- redesign of shared queue semantics, provider execution, pointer authority,
  snapshot semantics, or command-adapter certification policy;
- fabrication of fake Semantic IR from debug YAML, runtime logs, pointer files,
  or report parsing;
- replacing the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for exactly the selected
`semantic-workflow-ir-shared-contract` gap. It does not broaden into a general
runtime rewrite or a Core AST tranche.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `64. Snapshot Validation`
  - `65. Pointer Authority Validation`
  - `66. Report-Authority Validation`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by the earlier
implementation architectures and the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared workflow
  meaning, loader, executable lowering, and runtime bundle contracts under
  `orchestrator/workflow/`;
- reuse the current staged path:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck/effects -> lowering -> shared validation -> executable/runtime
  bundle;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse `LoadedWorkflowBundle`, `WorkflowStateProjection`,
  `WorkflowRuntimePlan`, `ValidationSubjectRef`, persisted `source_map.json`,
  and compiled-frontend provenance instead of creating parallel identity
  systems;
- keep command boundaries on the existing `external_tool` versus
  `certified_adapter` contract and carry only declared metadata into Semantic
  IR.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because Semantic IR must record workflow-semantic command boundaries without
reconstructing semantics from opaque shell text. This slice must not introduce:

- inline semantic shell or Python glue;
- report parsing as semantic authority;
- pointer-file recovery as workflow meaning;
- uncataloged runtime-native promotion hidden behind command serialization.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, architecture target contract, prior implementation
architectures, and current repo evidence remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline and package ownership split.
- Reuse `LoadedWorkflowBundle` as the shared loaded-workflow carrier and
  `WorkflowRuntimePlan` as the runtime-facing derived summary rather than
  inventing a second executor contract.
- Reuse the structured provenance bridge:
  `ValidationSubjectRef`,
  `WorkflowProvenance`,
  `LoweringOriginMap`,
  persisted `source_map.json`,
  and compiled-frontend runtime lineage.
- Reuse the honesty rule from the CLI/build and source-map slices:
  do not fabricate unavailable shared artifacts; keep `core_workflow_ast`
  deferred until a real shared contract exists.
- Reuse the current command-boundary classification and certified-adapter
  metadata without interpreting command text.

### New Decisions In This Slice

- Add one shared `SemanticWorkflowIR` contract under `orchestrator/workflow/`
  and make it a first-class field on `LoadedWorkflowBundle`.
- Derive Semantic IR from the validated shared bundle surfaces already owned by
  the runtime path:
  validated `SurfaceWorkflow`,
  `ExecutableWorkflow`,
  `WorkflowStateProjection`,
  imported bundle edges,
  and compiled-frontend provenance when present.
- Keep `SemanticWorkflowIR` authoritative for serialized workflow meaning while
  leaving existing executable/runtime consumption unchanged in this slice.
- Emit `semantic_ir.json` for compiled Workflow Lisp builds, mark
  `semantic_ir` as emitted in the build manifest, and change source-map
  coverage from `deferred_shared_contract` to `covered`.
- Add one explicit executable bridge inside Semantic IR so every semantic
  statement, ref, and publication can be joined to existing executable node ids
  and projection keys without re-reading frontend syntax.

### Conflicts Or Revisions

The source-map/runtime-lineage and CLI/build slices explicitly kept
`semantic_ir` deferred. This slice revises those decisions narrowly:

- `semantic_ir.json` becomes a real emitted build artifact for compiled `.orc`
  entrypoints;
- source-map coverage now marks `semantic_ir` as `covered`;
- `orchestrate explain` no longer reports `semantic_ir` as deferred and should
  expose a Semantic IR section for compiled workflows.

The executable-IR/runtime-plan slice kept `LoadedWorkflowBundle` limited to:
`surface`, `ir`, `projection`, `runtime_plan`, `imports`, and `provenance`.
This slice revises that shape narrowly:

- add `semantic_ir` to the shared bundle;
- keep `runtime_plan` derivation and executor behavior unchanged in this slice.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, TypeCatalog, SourceMap, pointer authority, or variant proof. This
slice implements the missing shared Semantic IR contract rather than redefining
those concepts.

## Ownership Boundaries

This slice owns:

- the shared `SemanticWorkflowIR` schema, builder, validator, and serializer;
- shared catalog population for workflow signatures, contracts, refs, effects,
  proofs, state layout, source-map references, and executable bridge metadata;
- integration of Semantic IR into `LoadedWorkflowBundle`;
- Workflow Lisp build-artifact emission of `semantic_ir.json`;
- deterministic diagnostics and invariant checks for Semantic IR construction;
- focused tests for shared bundle construction, artifact emission, explain
  output, and provenance/coverage updates.

This slice intentionally does not own:

- frontend parsing, macro expansion, module resolution, typechecking, procedure
  lowering, workflow-ref linking, or phase/resource/drain semantics;
- a separately implemented Core Workflow AST package or any `core_workflow_ast`
  artifact;
- runtime executor scheduling, queue semantics, state persistence, or provider
  execution behavior;
- new command adapters, legacy adapters, or runtime-native effect promotion;
- redesign of the standalone source-map schema beyond updating coverage and
  joining Semantic IR refs to existing provenance keys.

## Current Checkout Facts

- there is no shared `orchestrator/workflow/semantic_ir.py` module in the
  current checkout;
- `orchestrator/workflow/loaded_bundle.py` already carries
  `surface`,
  `ir`,
  `projection`,
  `runtime_plan`,
  `imports`,
  and `provenance`, but not Semantic IR;
- `orchestrator/workflow/runtime_plan.py` already provides a shared derived
  runtime-plan contract, and the executor already consumes it;
- `orchestrator/workflow_lisp/build.py` already emits `runtime_plan.json` but
  still marks `semantic_ir` as `deferred_shared_contract` in the manifest;
- `orchestrator/workflow_lisp/source_map.py` still marks `semantic_ir` as a
  deferred coverage surface;
- `orchestrator/cli/commands/explain.py` still prints
  `Deferred artifacts: core_workflow_ast, semantic_ir`;
- `ValidationSubjectRef` already exists in `orchestrator/exceptions.py`, and
  the frontend lowering/source-map path already attaches structured subject refs
  for shared-validation remapping;
- the current gap is therefore not provenance or runtime-plan design from
  scratch. It is the missing shared semantic contract and emitted artifact that
  the existing frontend/build/runtime slices already reserved space for.

## Proposed Package Boundary

Introduce one shared Semantic IR module and thread it through the existing
bundle/build surfaces:

```text
orchestrator/workflow/
  semantic_ir.py          # new shared schema, builder, validator, serializer
  loaded_bundle.py        # add semantic_ir field + helper
  lowering.py             # derive semantic_ir during shared bundle construction
  runtime_plan.py         # unchanged runtime-plan derivation, reused bridge
  surface_ast.py          # reused validated surface authority
  elaboration.py          # reused validated authored-surface authority

orchestrator/workflow_lisp/
  build.py                # emit semantic_ir.json, update manifest status
  source_map.py           # semantic_ir coverage now covered
  diagnostics.py          # activate semantic_ir_invalid mapping

orchestrator/cli/commands/
  explain.py              # include Semantic IR in explain output
```

Responsibilities:

- `orchestrator/workflow/semantic_ir.py`
  - define `SemanticWorkflowIR` and the minimal shared catalog/value types it
    needs;
  - derive Semantic IR from validated shared workflow surfaces and imported
    bundles;
  - validate referential integrity, coverage, and command-boundary invariants;
  - serialize the shared artifact to plain JSON-compatible data.
- `orchestrator/workflow/loaded_bundle.py`
  - add `semantic_ir` to `LoadedWorkflowBundle`;
  - add a typed helper `workflow_semantic_ir(...)`.
- `orchestrator/workflow/lowering.py`
  - derive Semantic IR after executable lowering and before the shared bundle is
    returned;
  - keep executable IR and runtime-plan derivation unchanged.
- `orchestrator/workflow_lisp/build.py`
  - write `semantic_ir.json`;
  - include the artifact path in the manifest;
  - update artifact status so `semantic_ir` is emitted while
    `core_workflow_ast` remains deferred.
- `orchestrator/workflow_lisp/source_map.py`
  - update coverage metadata to mark `semantic_ir` covered;
  - keep `core_workflow_ast` deferred.
- `orchestrator/workflow_lisp/diagnostics.py`
  - map shared Semantic IR builder failures to `semantic_ir_invalid`.
- `orchestrator/cli/commands/explain.py`
  - expose a serialized Semantic IR view for compiled workflows;
  - reduce the deferred-artifact banner to `core_workflow_ast` only.

Shared components intentionally reused, not owned here:

- `WorkflowProvenance` in `orchestrator/workflow/surface_ast.py`
- `WorkflowStateProjection` in `orchestrator/workflow/state_projection.py`
- `WorkflowRuntimePlan` in `orchestrator/workflow/runtime_plan.py`
- `ValidationSubjectRef` in `orchestrator/exceptions.py`
- frontend-owned provenance structures in `orchestrator/workflow_lisp/source_map.py`

## Semantic IR Contract

### Top-Level Shape

Keep the top-level contract aligned with the full design and the internal
Semantic IR note:

- `schema_version`
- `workflows`
- `types`
- `contracts`
- `refs`
- `effects`
- `proofs`
- `state_layout`
- `source_map`

The initial implementation may keep these supporting catalogs as lightweight
shared dataclasses inside `semantic_ir.py` instead of splitting them into
independent public modules. That keeps the scope bounded while preserving the
full-design names and ownership boundaries.

### `SemanticWorkflow`

Each workflow entry should record:

- workflow name and imported-call identity;
- structured inputs and outputs as semantic signature refs;
- statement ids in authored order;
- call-graph edges to imported or local workflows;
- provider prompt-contract surfaces;
- command validation surfaces and command-boundary class;
- artifact publication plan;
- executable bridge ids that join semantic statements to executable node ids and
  projection presentation keys.

### Type And Contract Catalogs

`types` and `contracts` are shared semantic catalogs, not frontend AST dumps.
Populate them from existing validated surfaces:

- input/output contract definitions on `SurfaceWorkflow`;
- `output_bundle` and `variant_output` schemas;
- publication contracts and expected output contracts;
- flattened workflow-boundary projection contracts already materialized by the
  current shared/runtime seam.

The catalog must preserve stable keys so:

- Semantic IR serialization is deterministic;
- call edges and publication refs can refer to contracts by id;
- imported bundles and compiled Workflow Lisp builds use the same shared
  contract vocabulary.

### Reference Catalog

`refs` should unify the semantic identities the current repo already exposes
piecemeal:

- workflow input/output refs;
- step result refs;
- artifact publication refs;
- imported workflow aliases and call-boundary refs;
- validation-subject refs;
- executable bridge refs;
- runtime checkpoint refs.

The builder must not infer refs from log strings, pointer files, or report
content. Every ref must come from validated workflow structures or declared
compiled-frontend provenance.

### Effect Graph

`effects` should record the semantic effect surface already implied by validated
workflow steps and frontend effect summaries:

- provider calls;
- command calls, tagged as `external_tool` or `certified_adapter`;
- workflow calls;
- artifact publication;
- state writes and snapshot writes;
- pointer materialization only when the validated workflow explicitly carries
  it as representation, not as authority.

For command boundaries, Semantic IR records only declared facts:

- boundary kind;
- stable command/adaptor name;
- output validation surface;
- source-map behavior when declared.

Semantic IR must not parse shell text to guess hidden effects.

### Proof Graph

`proofs` should record variant availability and proof-carrying surfaces using
the existing validated workflow semantics:

- `match`-established branch proofs;
- `requires_variant` constraints;
- `variant_output` and `select_variant_output` result availability;
- workflow-call result proof requirements where current lowering already exposes
  them.

The proof graph should point to statement ids and ref ids, not authored syntax
objects. Source-map joins remain separate.

### State Layout

`state_layout` should record only semantic state facts needed by downstream
tools:

- managed write-root inputs;
- canonical bundle paths and state files referenced by validated workflows;
- snapshot owners and selection-relevant candidates;
- projection-backed presentation keys and resume checkpoints;
- published artifact roots.

This is not a new state manager. It is the shared semantic index over the state
layout the runtime already executes.

### Source-Map Bridge

The `source_map` section in Semantic IR is a bridge, not a duplicate of
`source_map.json`.

For compiled Workflow Lisp bundles, it should carry:

- stable semantic ids -> `ValidationSubjectRef` bindings;
- semantic ids -> frontend origin keys when those origin keys already exist in
  the persisted source map;
- coverage metadata showing that Semantic IR participates in the provenance
  bridge.

For YAML workflows, the bridge may be empty while the rest of Semantic IR
remains fully populated.

## Construction Pipeline And Ownership

Semantic IR construction should be shared and deterministic:

1. Shared elaboration and validation produce a validated `SurfaceWorkflow`.
2. Shared lowering produces `ExecutableWorkflow` and `WorkflowStateProjection`.
3. The new shared Semantic IR builder receives:
   - validated surface workflow;
   - executable IR;
   - state projection;
   - imported bundles;
   - workflow provenance.
4. The builder derives stable workflow, statement, contract, ref, effect, proof,
   and state-layout ids from those validated inputs.
5. The builder validates referential integrity and bridge coverage.
6. `LoadedWorkflowBundle` stores:
   - `surface`
   - `semantic_ir`
   - `ir`
   - `projection`
   - `runtime_plan`
   - `imports`
   - `provenance`
7. Workflow Lisp build emission serializes `semantic_ir.json` from the selected
   bundle without re-deriving it in frontend code.

This keeps Semantic IR shared rather than frontend-private, and it keeps the
Workflow Lisp build artifact honest: the artifact reflects the shared loaded
bundle rather than a second serializer over typed frontend state.

## Validation And Error Model

Shared Semantic IR validation owns these invariant checks:

- every workflow, statement, contract, ref, effect, proof, and state-layout key
  is unique and deterministic;
- every catalog reference resolves to an existing entry;
- every executable bridge node id exists in `ExecutableWorkflow`;
- every projection presentation key and resume checkpoint ref exists in
  `WorkflowStateProjection` or `WorkflowRuntimePlan`;
- every command boundary tagged as `certified_adapter` carries declared adapter
  metadata and never relies on shell-text inspection;
- every compiled-frontend source-map reference points to an existing subject ref
  or origin key when such provenance is declared;
- `semantic_ir.json` serialization is stable and lossless for the shared
  dataclasses.

Failure surfacing:

- shared builder failures should surface as deterministic shared validation
  failures tagged `semantic_ir_invalid`;
- when structured subject refs exist, attach them to the failure so the
  frontend source-map remap path can preserve authored provenance;
- the Workflow Lisp validation pipeline should classify these as
  `phase=semantic_ir`, `validation_pass=semantic_ir`,
  `authority_layer=shared`;
- YAML loader failures should surface through the existing validation error path
  rather than a frontend-only exception type.

This slice activates `semantic_ir_invalid` as a real implemented error class.
Earlier slices reserved it while the shared contract was absent.

## Build Artifact And CLI Integration

For compiled Workflow Lisp builds:

- emit `semantic_ir.json` alongside
  `frontend_ast.json`,
  `expanded_frontend_ast.json`,
  `typed_frontend_ast.json`,
  `lowered_workflows.json`,
  `executable_ir.json`,
  `runtime_plan.json`,
  `source_map.json`,
  and `diagnostics.json`;
- record the new artifact in `FrontendBuildManifest.artifact_paths`;
- set `artifact_status` to:
  - `core_workflow_ast: deferred_shared_contract`
  - `semantic_ir: emitted`
- update `source_map_coverage` so:
  - `semantic_ir: covered`
  - `core_workflow_ast: deferred_shared_contract`

`orchestrate explain` should:

- keep operating on implemented surfaces;
- add a Semantic IR section derived from the emitted shared artifact or in-memory
  bundle;
- reduce the deferred-artifact banner to `core_workflow_ast` only.

Runtime observability does not gain a second provenance channel in this slice.
It continues to use `source_map.json` plus `runtime_plan`, but the persisted
coverage metadata should now report that Semantic IR is implemented.

## Test Strategy

Add or extend focused tests in these areas:

- shared Semantic IR derivation and validation:
  `tests/test_workflow_semantic_ir.py`
- shared bundle integration and loader behavior:
  `tests/test_workflow_ir_lowering.py`,
  `tests/test_loader_validation.py`
- Workflow Lisp build artifacts and manifest updates:
  `tests/test_workflow_lisp_build_artifacts.py`
- Workflow Lisp diagnostics and shared validation classification:
  `tests/test_workflow_lisp_diagnostics.py`
- explain surface updates:
  `tests/test_workflow_lisp_cli.py`
- runtime/source-map coverage regressions:
  `tests/test_runtime_observability.py`

Required assertions:

- `LoadedWorkflowBundle` exposes `semantic_ir` for shared YAML and compiled
  Workflow Lisp workflows;
- `semantic_ir.json` is emitted and round-trips deterministically;
- `semantic_ir` is no longer marked deferred in build manifests, explain
  output, or source-map coverage;
- command-boundary metadata in Semantic IR preserves the declared
  `external_tool` versus `certified_adapter` split without shell parsing;
- Semantic IR validation failures surface with `semantic_ir_invalid` and, when
  available, structured subject refs.

## Acceptance Conditions

- `orchestrator/workflow/semantic_ir.py` defines a real shared
  `SemanticWorkflowIR` contract and validator.
- `LoadedWorkflowBundle` carries `semantic_ir` in addition to
  `surface`,
  `ir`,
  `projection`,
  `runtime_plan`,
  `imports`,
  and `provenance`.
- shared bundle construction derives Semantic IR from validated shared surfaces
  and executable/runtime bundle metadata without reading frontend syntax,
  runtime logs, reports, or pointer files.
- compiled Workflow Lisp builds emit `semantic_ir.json`, and the build manifest
  marks `semantic_ir` emitted while `core_workflow_ast` remains deferred.
- source-map coverage and runtime-observability metadata report
  `semantic_ir` as covered.
- `orchestrate explain` no longer treats `semantic_ir` as deferred.
- Semantic IR records command boundaries, contracts, refs, effects, proofs,
  state layout, and executable bridge metadata using declared validated
  structures only.
- semantic builder failures surface deterministically as
  `semantic_ir_invalid` with shared subject refs when available.

## Verification Plan

- `python -m pytest --collect-only tests/test_workflow_semantic_ir.py -q`
- `python -m pytest tests/test_workflow_semantic_ir.py -q`
- `python -m pytest tests/test_workflow_ir_lowering.py tests/test_loader_validation.py -k "semantic_ir or loaded_bundle" -q`
- `python -m pytest tests/test_workflow_lisp_build_artifacts.py tests/test_workflow_lisp_cli.py -k "semantic_ir or explain or build_artifacts" -q`
- `python -m pytest tests/test_workflow_lisp_diagnostics.py tests/test_runtime_observability.py -k "semantic_ir or source_map_coverage or compiled_frontend" -q`
