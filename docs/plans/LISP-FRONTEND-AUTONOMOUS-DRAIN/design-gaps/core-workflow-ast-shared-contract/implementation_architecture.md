# Core Workflow AST Shared Contract Implementation Architecture

## Scope

This design gap covers only the bounded shared Core Workflow AST slice selected
for the Workflow Lisp frontend full-design drain:

- define one shared `CoreWorkflowAST` contract between validated authored
  workflow surfaces and the existing shared lowering, Semantic IR, and runtime
  bundle layers;
- implement one shared Core AST schema, builder, validator, lowering entry
  point, and serializer under `orchestrator/workflow/`;
- thread Core AST through shared YAML loading and compiled Workflow Lisp build
  flows so `LoadedWorkflowBundle` carries a real shared Core AST surface;
- emit deterministic `core_workflow_ast.json` for compiled Workflow Lisp builds
  and stop treating `core_workflow_ast` as a deferred shared-contract artifact;
- preserve the current authored `SurfaceWorkflow` compatibility surface, shared
  `SemanticWorkflowIR`, shared `WorkflowRuntimePlan`, existing executable IR,
  and runtime execution semantics.

Out of scope for this tranche:

- new Workflow Lisp language forms, new stdlib forms, or revisions to parsing,
  modules, macros, procedures, workflow refs, phase/resource/drain behavior, or
  CLI entrypoint semantics beyond exposing the new artifact;
- redesign of shared queue semantics, provider execution, pointer authority,
  snapshot semantics, variant proof, or runtime state persistence;
- a replacement of `SurfaceWorkflow` as the authored validation surface for YAML
  or frontend-lowered workflow mappings;
- new command adapters, legacy adapters, report parsing, pointer-as-state
  recovery, or runtime-native effect promotion;
- fabrication of fake shared artifacts beyond the real Core AST contract this
  slice owns.

This is an implementation architecture for exactly the selected
`core-workflow-ast-shared-contract` gap. It does not reopen the rest of the
frontend or runtime design.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_core_workflow_ast.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by prior
implementation-architecture documents and the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared workflow
  meaning, validation, executable lowering, Semantic IR, runtime-plan, and
  runtime bundle contracts under `orchestrator/workflow/`;
- reuse the staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck/effects -> authored workflow mapping -> `SurfaceWorkflow` ->
  `CoreWorkflowAST` -> shared validation/lowering -> Semantic IR ->
  executable/runtime bundle;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse `LoadedWorkflowBundle`, `WorkflowProvenance`, `ValidationSubjectRef`,
  persisted `source_map.json`, shared `SemanticWorkflowIR`, shared
  `WorkflowRuntimePlan`, and executable/runtime observability joins instead of
  inventing parallel identity systems;
- keep command boundaries on the existing `external_tool` versus
  `certified_adapter` contract and carry only declared metadata into
  `CoreCommandStep` and downstream shared surfaces.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because the Core AST statement taxonomy must make command boundaries explicit
without reconstructing workflow semantics from opaque shell text. This slice
must not introduce:

- inline semantic shell or Python glue as a Core AST escape hatch;
- report parsing as workflow authority;
- pointer-file recovery as workflow meaning;
- uncataloged runtime-native promotion hidden behind a command-shaped node.

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
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the current staged frontend pipeline and the package ownership split
  between `orchestrator/workflow_lisp/` and `orchestrator/workflow/`.
- Reuse `SurfaceWorkflow` as the authored, validated compatibility surface for
  YAML workflows and frontend-lowered authored mappings instead of bypassing the
  shared elaboration seam.
- Reuse `LoadedWorkflowBundle` as the shared transport object for loader, CLI,
  runtime, imported-bundle linking, and compiled frontend build flows.
- Reuse `WorkflowProvenance`, `ValidationSubjectRef`, `LoweringOriginMap`, and
  persisted `source_map.json` as the provenance bridge rather than inventing a
  second source-trace system for Core AST nodes.
- Reuse the implemented shared `SemanticWorkflowIR` and `WorkflowRuntimePlan`
  contracts as downstream bundle surfaces that should now receive Core AST as an
  upstream shared input.
- Reuse the existing command-boundary classification and certified-adapter
  metadata without inventing a second command taxonomy.

### New Decisions In This Slice

- Add one shared `CoreWorkflowAST` contract under `orchestrator/workflow/` and
  make it a first-class field on `LoadedWorkflowBundle`.
- Treat `SurfaceWorkflow` as the authored compatibility layer and
  `CoreWorkflowAST` as the first syntax-neutral shared workflow substrate after
  authored elaboration.
- Build Core AST from validated shared structures only:
  `SurfaceWorkflow`,
  imported bundle metadata,
  normalized contracts,
  and existing provenance metadata.
- Lower executable IR and derive downstream semantic surfaces from Core AST
  rather than treating `SurfaceWorkflow` as the long-term shared semantic
  boundary.
- Emit `core_workflow_ast.json` for compiled Workflow Lisp builds, mark
  `core_workflow_ast` as emitted in the build manifest, and change source-map
  coverage from `deferred_shared_contract` to `covered`.
- Extend explain and source-trace surfaces so Core AST nodes are observable by
  stable node ids and source-map origin keys, not only by lowered step ids and
  executable node ids.

### Conflicts Or Revisions

The CLI/build, source-map/runtime-lineage, executable-IR/runtime-plan, and
semantic-IR slices all explicitly kept `core_workflow_ast` deferred. This slice
revises those decisions narrowly:

- `core_workflow_ast.json` becomes a real emitted build artifact for compiled
  `.orc` entrypoints;
- build-manifest `artifact_status["core_workflow_ast"]` becomes `emitted`;
- source-map coverage now marks `core_workflow_ast` as `covered`;
- `orchestrate explain` no longer prints a deferred-artifact banner for
  `core_workflow_ast` and instead exposes a Core AST section.

The Stage 3 workflow-lowering slice used the authored-mapping ->
`elaborate_surface_workflow(...)` -> `lower_surface_workflow(...)` seam as a
temporary bridge because the shared Core AST package did not exist. This slice
revises that bridge narrowly:

- keep authored-mapping elaboration into `SurfaceWorkflow` unchanged;
- insert a real shared Core AST after elaboration;
- keep a compatibility `lower_surface_workflow(...)` shim only if needed so
  existing call sites remain stable while runtime-owned lowering migrates to
  `lower_core_workflow_ast(...)`.

The semantic-IR slice implemented `SemanticWorkflowIR` using
`surface + ir + projection + runtime_plan` as the available shared substrate.
This slice narrows that upstream dependency:

- Core AST becomes the shared statement and contract authority for downstream
  semantic indexing;
- `SurfaceWorkflow` may remain available as authored-compatibility context
  where existing shared contracts still reference provenance or authored names;
- the semantic-IR schema itself is not redesigned in this slice.

No prior slice is revised on shared concepts such as spans, diagnostics,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof. This slice implements the missing shared Core Workflow AST contract
rather than redefining those concepts.

## Ownership Boundaries

This slice owns:

- the shared `CoreWorkflowAST` schema, statement taxonomy bindings, builder,
  validator, lowerer entry point, and serializer;
- integration of Core AST into `LoadedWorkflowBundle`;
- one shared derivation path from validated `SurfaceWorkflow` into Core AST for
  both YAML-loaded and compiled Workflow Lisp workflows;
- the shift of downstream shared bundle construction so Core AST is the
  authoritative upstream statement/contract catalog for executable lowering and
  Semantic IR derivation;
- Core AST build-artifact emission, explain output, source-map coverage, and
  per-node lineage additions needed to make `core_workflow_ast` honestly
  covered;
- focused tests for shared bundle construction, YAML/frontend parity, artifact
  emission, explain output, and provenance coverage updates.

This slice intentionally does not own:

- frontend parsing, macro expansion, module resolution, typechecking, procedure
  lowering, workflow-ref linking, or phase/resource/drain lowering semantics;
- redesign of `SurfaceWorkflow` as the authored validation surface or changes to
  authored YAML syntax;
- runtime executor scheduling, queue semantics, provider execution behavior, or
  state persistence;
- new command adapters, legacy adapters, or runtime-native effect promotion;
- redesign of `SemanticWorkflowIR`, `WorkflowRuntimePlan`, executable node
  kinds, or the standalone diagnostic taxonomy beyond the narrow additions
  needed to validate Core AST construction.

## Current Checkout Facts

- `docs/steering.md` is empty in this checkout and does not broaden scope.
- There is no shared `orchestrator/workflow/core_ast.py` or comparable Core AST
  implementation module in the current checkout.
- `orchestrator/workflow/loaded_bundle.py` already carries
  `surface`,
  `semantic_ir`,
  `ir`,
  `projection`,
  `runtime_plan`,
  `imports`,
  and `provenance`, but not a Core AST field.
- `orchestrator/loader.py` still loads YAML through
  raw mapping -> `elaborate_surface_workflow(...)` ->
  `build_loaded_workflow_bundle(surface, imports=...)`.
- `orchestrator/workflow/lowering.py` still lowers `SurfaceWorkflow` directly to
  `ExecutableWorkflow + WorkflowStateProjection`.
- `orchestrator/workflow/semantic_ir.py` still derives Semantic IR directly from
  `SurfaceWorkflow` plus runtime bundle surfaces.
- `orchestrator/workflow_lisp/build.py` emits
  `semantic_ir.json`,
  `runtime_plan.json`,
  `source_map.json`,
  and other build artifacts, but not `core_workflow_ast.json`.
- `orchestrator/workflow_lisp/build.py` still marks
  `core_workflow_ast` as `deferred_shared_contract` in the build manifest.
- `orchestrator/workflow_lisp/source_map.py` still marks
  `core_workflow_ast` as `deferred_shared_contract` in coverage metadata.
- `orchestrator/cli/commands/explain.py` still prints
  `Deferred artifacts: core_workflow_ast`.
- Existing tests in
  `tests/test_workflow_lisp_build_artifacts.py`,
  `tests/test_runtime_observability.py`,
  and `tests/test_runtime_observability_cli.py`
  still assert that `core_workflow_ast` is deferred.

The current gap is therefore not “invent another debug serialization.” It is
the missing shared Core AST contract that earlier slices explicitly reserved but
could not honestly fabricate.

## Proposed Package Boundary

Introduce one shared Core AST module and thread it through the existing shared
bundle/build surfaces:

```text
orchestrator/workflow/
  core_ast.py                 # shared CoreWorkflowAST schema, builder, validator, serializer
  loaded_bundle.py            # add core_workflow_ast field + helper accessor
  lowering.py                 # build core AST, lower core AST, compatibility shim for surface callers
  semantic_ir.py              # derive semantic statements/contracts from core AST
  runtime_plan.py             # unchanged contract, downstream consumer only
  surface_ast.py              # unchanged authored compatibility surface

orchestrator/workflow_lisp/
  build.py                    # emit core_workflow_ast.json + updated manifest status
  source_map.py               # add core-node lineage + mark core coverage covered

orchestrator/cli/commands/
  explain.py                  # show Core Workflow AST payload and drop deferred banner

tests/
  test_workflow_core_ast.py
  test_workflow_ir_lowering.py
  test_loader_validation.py
  test_workflow_lisp_build_artifacts.py
  test_workflow_lisp_cli.py
  test_runtime_observability.py
  test_runtime_observability_cli.py
```

Compatibility policy for existing call sites:

- `build_loaded_workflow_bundle(...)` becomes the canonical shared constructor
  that always produces
  `surface + core_workflow_ast + semantic_ir + ir + projection + runtime_plan`.
- `lower_surface_workflow(...)` may remain as a compatibility wrapper that
  internally builds Core AST and forwards to `lower_core_workflow_ast(...)`,
  but no new shared bundle construction may bypass Core AST.
- Workflow Lisp build rewrapping must preserve the already-derived
  `core_workflow_ast` when attaching updated provenance and runtime-plan
  enrichment, instead of reconstructing a bundle that silently drops the new
  shared surface.

## Data Model

### `CoreWorkflowAST`

The bounded initial shared contract should be one versioned root object:

```text
CoreWorkflowAST(
  schema_version,
  workflow_name,
  version,
  provenance,
  imports,
  inputs,
  outputs,
  artifacts,
  providers,
  statements,
  finalization,
  source_map_bridge,
)
```

Required properties:

- syntax-neutral and shared between YAML and Workflow Lisp after authored
  elaboration;
- immutable and deterministic;
- built only from validated authored/shared structures, not from debug YAML or
  runtime logs;
- explicit about workflow boundary contracts, imported workflow aliases,
  statement ordering, and source-map lineage anchors;
- stable enough to serialize as `workflow_core_ast.v1`.

For this bounded slice, contract leaf payloads and imported-workflow metadata
may be carried through existing normalized shared structures rather than
re-inventing a second contract parser. The shared boundary is the new root and
statement taxonomy, not a second independent contract-definition language.

### Statement Taxonomy

Core statement families must match the closed taxonomy already documented in
`docs/design/workflow_lisp_core_stmt_taxonomy.md`. The initial implementation
must cover the step kinds already supported by `SurfaceStepKind` and the shared
runtime:

- command
- provider
- adjudicated provider
- wait-for
- assert
- set-scalar
- increment-scalar
- materialize-artifacts
- select-variant-output
- for-each
- repeat-until
- call
- if
- match
- finalization block

Each core statement carries stable metadata:

```text
CoreStmtMeta(
  statement_id,
  step_id,
  step_name,
  statement_kind,
  lexical_scope_id,
  source_origin_key,
  generated_by,
)
```

The goal is not to invent new executable behavior. The goal is to represent the
already-supported workflow semantics in one shared, validated, source-mapped
form that both YAML and Workflow Lisp can target.

### Command Boundary Entries

`CoreCommandStep` must preserve the command-boundary facts already enforced by
the command-adapter contract:

- `boundary_kind`: `external_tool` or `certified_adapter`
- `boundary_name`
- stable command identity/path metadata when declared
- output-validation surface
- declared `source_map_behavior` when the adapter exposes it

Core AST must never treat opaque command text as semantic authority. If a
workflow-semantic command boundary lacks declared adapter metadata, Core AST
validation must fail deterministically rather than serializing a generic shell
wrapper as a meaningful shared node.

### Source-Map Bridge

Core AST must carry stable lineage anchors so source maps can honestly mark Core
coverage as implemented. The narrow source-map extension needed by this slice is
one per-workflow `core_nodes` section keyed by core node id and origin key. This
is additive to the existing source-trace artifact and should not replace:

- workflow origin
- generated inputs/outputs/paths
- validation-subject bindings
- executable-node lineage

The Core AST bridge is the missing middle layer between authored lowering
origins and downstream executable/runtime lineage.

## Construction And Validation Pipeline

The shared bundle path becomes:

```text
raw YAML or frontend-lowered authored mapping
  -> elaborate_surface_workflow(...)
  -> SurfaceWorkflow
  -> build_core_workflow_ast(...)
  -> validate_core_workflow_ast(...)
  -> lower_core_workflow_ast(...)
  -> ExecutableWorkflow + WorkflowStateProjection
  -> derive_workflow_runtime_plan(...)
  -> derive_workflow_semantic_ir(...)
  -> LoadedWorkflowBundle
```

Responsibilities by layer:

1. `SurfaceWorkflow`
   Preserves authored-shape validation and compatibility semantics already owned
   by shared elaboration. This slice does not replace it.

2. `build_core_workflow_ast(...)`
   Converts the validated authored surface into a syntax-neutral shared
   statement tree with explicit contracts, imports, providers, and source-map
   anchors.

3. `validate_core_workflow_ast(...)`
   Rejects:
   - unsupported or unsourced statement kinds;
   - command boundaries that violate the adapter contract;
   - missing imported alias metadata;
   - invalid block structure or statement-id collisions;
   - source-map gaps for core nodes;
   - serialization-unsafe payloads.

4. `lower_core_workflow_ast(...)`
   Produces executable/runtime-owned surfaces from Core AST. The runtime-facing
   contract still ends at executable IR and runtime plan, but Core AST is now
   the authoritative shared lowering input.

5. `derive_workflow_semantic_ir(...)`
   Reads Core AST as the shared statement and contract authority, with runtime
   bundle surfaces and provenance as auxiliary inputs. This keeps semantic IR
   aligned to the new shared boundary without redesigning its schema here.

## Shared Bundle And Artifact Surfaces

### `LoadedWorkflowBundle`

Extend the shared bundle to carry Core AST:

```text
LoadedWorkflowBundle(
  surface,
  core_workflow_ast,
  semantic_ir,
  ir,
  projection,
  runtime_plan,
  imports,
  provenance,
)
```

Add one compatibility helper in `loaded_bundle.py`:

- `workflow_core_workflow_ast(workflow_or_bundle) -> CoreWorkflowAST | None`

This mirrors the existing runtime-plan and semantic-IR accessors and keeps the
shared bundle API explicit.

### `core_workflow_ast.json`

Compiled Workflow Lisp builds must emit one deterministic serialized Core AST
artifact for the selected entry workflow:

```json
{
  "schema_version": "workflow_core_ast.v1",
  "workflow_name": "neurips/entry::orchestrate",
  "workflow": { "...": "..." }
}
```

The build surface remains honest and bounded:

- emit the selected workflow’s Core AST, matching the current selected-bundle
  artifact pattern used by `semantic_ir.json` and `runtime_plan.json`;
- do not silently bundle imported workflows into the same artifact unless the
  build contract is later widened explicitly;
- keep `lowered_workflows.json` as the authored-lowering inspection artifact,
  not as a substitute for Core AST.

### Manifest And Explain Revisions

`manifest.json` must record:

- `artifact_paths["core_workflow_ast"]`
- `artifact_status["core_workflow_ast"] == "emitted"`
- existing `semantic_ir` and `runtime_plan` statuses unchanged

`orchestrate explain` must:

- stop printing `Deferred artifacts: core_workflow_ast`;
- render a dedicated `Core Workflow AST:` section for the selected form;
- keep typed, lowered, executable, semantic-IR, and source-trace sections.

## Source Map And Observability Impact

This slice should not redesign the source-map system, but it must make Core AST
coverage honest.

Required narrow revisions:

- `SOURCE_MAP_COVERAGE["core_workflow_ast"]` becomes `covered`;
- each workflow entry in `source_map.json` gains `core_nodes` lineage for core
  workflow root and core statement ids;
- `semantic_ir` and executable-node lineage remain downstream joins, not
  replacements for Core node lineage;
- compiled-frontend runtime observability continues to publish the existing
  source-map sidecar path and coverage metadata, now showing
  `core_workflow_ast: covered`.

The runtime does not need to execute Core AST directly. It only needs the
source-trace contract to stay internally consistent across:

- authored forms,
- core nodes,
- validation subjects,
- executable nodes,
- runtime logs.

## Test Strategy

### Shared Core AST Tests

Add focused shared tests that cover:

- Core AST construction from validated YAML workflows;
- Core AST construction from compiled Workflow Lisp workflows;
- stable statement ids, workflow ids, and serialization shape;
- command-boundary classification in core statements;
- deterministic failure on unsourced or invalid core nodes.

### Bundle And Lowering Regression Tests

Extend shared bundle tests so:

- YAML loader returns `LoadedWorkflowBundle.core_workflow_ast`;
- compiled Workflow Lisp bundles also carry `core_workflow_ast`;
- compatibility `lower_surface_workflow(...)` behavior remains unchanged at the
  executable/runtime-plan level while now passing through Core AST internally.

### Build And Explain Tests

Extend frontend build/CLI coverage so:

- `core_workflow_ast.json` is emitted;
- manifest status changes from deferred to emitted;
- source-map coverage marks `core_workflow_ast` as covered and includes
  `core_nodes`;
- explain output shows Core AST and no longer reports it deferred.

### Runtime Observability Tests

Keep runtime-observability coverage narrow:

- compiled frontend metadata reports `core_workflow_ast: covered`;
- source-trace lineage joins remain deterministic after adding `core_nodes`;
- no executor behavior or queue semantics change is required.

## Implementation Sequence

1. Add the shared Core AST module and serialization contract under
   `orchestrator/workflow/`.
2. Extend `LoadedWorkflowBundle` and shared bundle construction so YAML and
   compiled frontend flows carry Core AST.
3. Move shared lowering to consume Core AST, keeping a compatibility shim for
   surface callers if needed.
4. Re-anchor Semantic IR derivation on Core AST without redesigning the
   semantic-IR schema.
5. Emit `core_workflow_ast.json`, update manifest/explain surfaces, and add
   source-map `core_nodes` coverage.
6. Run focused shared, frontend-build, CLI, and observability verification.

## Acceptance Conditions

- the repo has a real shared Core AST module under `orchestrator/workflow/`;
- `LoadedWorkflowBundle` carries `core_workflow_ast`;
- YAML loader and compiled Workflow Lisp builds both produce real Core AST
  bundle surfaces;
- compiled Workflow Lisp builds emit `core_workflow_ast.json`;
- build manifest and source-map coverage stop treating `core_workflow_ast` as
  deferred;
- `source_map.json` records Core node lineage in addition to existing authored
  and executable lineage;
- `orchestrate explain` shows a Core AST section and no longer prints
  `Deferred artifacts: core_workflow_ast`;
- command-boundary facts in Core AST remain declared-only and consistent with
  `docs/design/workflow_command_adapter_contract.md`;
- executable/runtime behavior remains unchanged apart from carrying the new
  shared intermediate contract and updated lineage metadata.

## Verification Plan

Target verification should stay narrow and deterministic:

- collect and run a dedicated `tests/test_workflow_core_ast.py` module;
- run focused shared bundle and lowering regressions in
  `tests/test_workflow_ir_lowering.py` and `tests/test_loader_validation.py`;
- run focused Workflow Lisp build/CLI assertions for
  `core_workflow_ast.json`, manifest status, source-map coverage, and explain
  output;
- run one frontend compile smoke command against the existing imported-bundle
  fixture stack to prove the emitted artifact set includes
  `core_workflow_ast.json`.
