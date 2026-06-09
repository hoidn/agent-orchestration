# Executable IR Component Contract Implementation Architecture

Status: draft
Design gap id: `executable-ir-component-contract`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded component-contract work required to make
Workflow Lisp's executable IR a reviewed, durable runtime-facing contract:

- designate the shared `ExecutableWorkflow` surface as the authoritative
  executable artifact emitted after shared validation;
- add one explicit shared executable-IR schema/version and validator contract
  instead of treating executable shape checks as incidental runtime behavior;
- define the compatibility path from the current Workflow Lisp lowering flow
  through validated workflow bundles into `executable_ir.json`;
- define how `runtime_plan`, `semantic_ir`, `source_map`, and
  `workflow_boundary_projection` relate to executable IR without becoming a
  second authority surface;
- add focused test and diagnostic expectations so executable-node lineage,
  bridge integrity, and compile-time-value erasure remain stable.

This slice does not implement:

- a direct frontend-to-executable-IR compiler path;
- new executable node kinds, new runtime value types, or runtime closures;
- runtime executor behavior changes, new adapter semantics, or runtime-native
  promotion beyond the existing command-adapter policy;
- redesign of Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap,
  pointer authority, or state-layout concepts beyond their executable-bridge
  contract;
- new scripts, helper commands, inline shell/Python glue, or YAML-shaped
  runtime shims.

The work stays bounded to one component-contract seam. It is an implementation
architecture for the executable-IR authority boundary, not a replacement
architecture for the whole Workflow Lisp frontend or runtime.

## Problem Statement

The current checkout already has a substantial executable substrate:

- `orchestrator/workflow/executable_ir.py` defines shared executable node,
  address, and step-config dataclasses used by the runtime;
- `orchestrator/workflow/lowering.py` builds `ExecutableWorkflow` and
  `WorkflowStateProjection` from the shared validated workflow surface;
- `orchestrator/workflow/loaded_bundle.py` treats executable IR, runtime plan,
  semantic IR, and Core Workflow AST as typed bundle surfaces;
- `orchestrator/workflow/runtime_plan.py` and `semantic_ir.py` already derive
  runtime-facing and semantic bridge layers from executable IR;
- `orchestrator/workflow_lisp/build.py` already emits `executable_ir.json`,
  `runtime_plan.json`, `semantic_ir.json`, and `source_map.json`;
- `tests/test_workflow_ir_lowering.py`,
  `tests/test_workflow_semantic_ir.py`, and
  `tests/test_workflow_lisp_build_artifacts.py` already exercise executable
  nodes, runtime-plan bridges, and build-artifact emission.

What is missing is the contract layer that makes those pieces durable and
reviewable.

Today the executable surface is real, but its architecture is still implicit:

- `ExecutableWorkflow` has no dedicated shared schema/version constant or
  validator contract analogous to Core AST and Semantic IR;
- the Workflow Lisp stage-3 `executable` validation pass currently re-runs
  source-map lineage with validated bundles present, but it does not define a
  separate executable-IR validation checkpoint;
- `build.py` emits `executable_ir.json` and `runtime_plan.json`, but the build
  manifest only records explicit emitted status for Core AST and Semantic IR;
- the current design docs describe the intended role of executable IR, but no
  bounded implementation architecture states which layer is authoritative and
  how the current lowered-workflow compatibility bridge is allowed to work.

The selected gap is therefore not "invent executable IR." The repo already has
it. The gap is to formalize the runtime-facing contract:

```text
Workflow Lisp typed frontend
  -> lowered workflow dictionaries
  -> shared validation / loaded bundle
  -> authoritative ExecutableWorkflow
  -> derived runtime plan / semantic IR / source map projections
```

without letting projections, build artifacts, or compile-time-only surfaces
become competing executable authorities.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `33. Target Pipeline`
  - `36. Semantic Workflow IR Contract`
  - `37. Executable IR Contract`
  - `42. State Layout Contract`
  - `43. Source Map Contract`
  - `45. Debug YAML Renderer Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `45. Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `49. Runtime Plan`
  - `59. Validation Sequence`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative for executable runtime semantics;
- executable IR may contain only runtime-executable values, never unresolved
  `ProcRef`, `WorkflowRef`, `let-proc`, syntax, typed frontend AST, or debug
  projections;
- `runtime_plan`, `semantic_ir`, `source_map`, and debug YAML remain derived
  layers and must not redefine execution semantics;
- command and adapter behavior in executable nodes must remain governed by the
  certified command-adapter contract, not by opaque inline glue;
- imported YAML bundles and compiled `.orc` bundles must enter reusable-call
  boundaries as validated `LoadedWorkflowBundle` instances, not as ad hoc
  executable-IR payloads;
- no new runtime-native effect or executable node kind may be added in this
  slice merely to compensate for missing frontend or adapter clarity.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`

### Decisions Reused

- Reuse the current rule from the `let-proc` slice that compile-time-only
  callable abstractions must be erased before runtime artifacts are produced.
- Reuse the effectful-composition slices' rule that new authoring power must
  lower through the existing shared workflow and runtime path instead of
  inventing a second executor.
- Reuse the reusable-boundary slice's explicit generated-input and
  write-root-projection discipline; executable IR consumes validated boundary
  results, it does not rediscover them from authored strings.
- Reuse the current shared ownership split where frontend modules may validate
  earlier and explain better, but shared workflow/runtime modules own runtime
  semantics.
- Reuse the command-adapter contract as the authority for command-boundary
  classification, adapter metadata, and runtime-native promotion criteria.

### New Decisions In This Slice

- Treat `orchestrator.workflow.executable_ir.ExecutableWorkflow` and its node,
  config, and bound-address dataclasses as the authoritative runtime-facing IR
  contract.
- Introduce one explicit shared executable-IR validator and schema/version
  contract, and require the Workflow Lisp `executable` pass to invoke it
  rather than acting only as a lineage checkpoint.
- Treat `WorkflowRuntimePlan`, `SemanticWorkflowIR`, Workflow Lisp
  `source_map`, and `workflow_boundary_projection` as derived bridge layers
  that must reference validated executable-node identities without redefining
  execution.
- Accept the current lowered-workflow compatibility bridge as the approved
  current architecture:
  - `.orc` lowers to ordinary workflow dictionaries;
  - the shared loader/runtime path validates those surfaces;
  - the resulting `LoadedWorkflowBundle.ir` is the executable authority.
- Require build-manifest emission and artifact export to make executable IR and
  runtime plan first-class emitted artifacts rather than implicit side outputs.

### Conflicts Or Revisions

The current implementation uses the pass id `executable`, but that pass does
not yet define a dedicated executable-IR contract. It currently validates
source-map lineage with validated bundles attached.

This slice revises that assumption narrowly:

- keep the current pass ordering and validated-bundle dependency;
- redefine the `executable` pass as a true executable-IR checkpoint that runs
  shared executable validation and then verifies executable-node lineage;
- keep source-map bridge validation as part of that pass, but no longer as the
  only executable-facing check.

The broader baseline/frontend design also describes a future direct pipeline
from frontend forms through Core AST, Semantic IR, and Executable IR. The
current checkout still reaches executable IR through lowered workflow
dictionaries and shared loader validation. This slice accepts that as the
current compatibility path rather than treating it as an architectural defect.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- the shared executable-IR contract shape, validation rules, and schema
  versioning policy;
- the boundary between authoritative executable IR and derived runtime-plan,
  semantic-IR, source-map, and build-artifact projections;
- the Workflow Lisp frontend checkpoints that validate and export executable IR
  from validated bundles;
- focused regression tests for executable-node integrity, bridge integrity,
  manifest emission, and compile-time-value erasure.

This slice intentionally does not own:

- frontend parsing, macro expansion, typechecking, or effect inference;
- new executable node kinds or runtime execution behavior in the executor;
- command-adapter certification rules, legacy-adapter policy, or runtime-native
  promotion decisions beyond consuming their existing metadata;
- redesign of runtime state layout, pointer authority, report authority, or
  workflow surface schemas;
- runtime closures, dynamic dispatch, or procedure/workflow transport at
  runtime.

## Proposed Package Boundary

Keep the work within the existing shared runtime and frontend-build packages:

```text
orchestrator/workflow/
  executable_ir.py   # authoritative executable schema, version, validator
  lowering.py        # build ExecutableWorkflow and invoke validator before bundle assembly
  loaded_bundle.py   # typed bundle continues exposing validated executable IR
  runtime_plan.py    # derived summary over validated executable IR
  semantic_ir.py     # executable bridge over validated executable IR

orchestrator/workflow_lisp/
  compiler.py        # executable validation checkpoint in stage-3 pipeline
  build.py           # emitted executable_ir/runtime_plan artifact and manifest contract
  source_map.py      # executable-node lineage validation against validated bundles

tests/
  test_workflow_ir_lowering.py
  test_workflow_semantic_ir.py
  test_workflow_lisp_build_artifacts.py
  test_workflow_lisp_diagnostics.py
```

Primary responsibilities:

- `orchestrator/workflow/executable_ir.py`
  - define one explicit schema/version constant for the executable structure;
  - add `validate_executable_workflow(...)` or the equivalent shared validator;
  - reject unresolved compile-time-only values, dangling node references,
    incompatible node/config pairs, and invalid contract address bindings.
- `orchestrator/workflow/lowering.py`
  - continue building executable IR through the shared surface/runtime path;
  - invoke executable validation before deriving `WorkflowRuntimePlan` and
    `SemanticWorkflowIR`.
- `orchestrator/workflow_lisp/compiler.py`
  - keep the pass order unchanged;
  - make the `executable` pass call the shared executable validator and then
    run executable-node lineage coverage checks.
- `orchestrator/workflow_lisp/build.py`
  - continue serializing the exact validated bundle IR;
  - make manifest status/reporting treat `executable_ir` and `runtime_plan` as
    first-class emitted artifacts.
- `orchestrator/workflow_lisp/source_map.py`
  - keep executable-node lineage derived from validated bundles only;
  - validate that any claimed executable coverage refers to validated node ids
    and not guessed lowered-step ids.

No new package, script, adapter, or alternative executable serializer is
needed for this slice.

## Current Checkout Facts

Current implementation evidence shows the exact seam this slice must formalize:

- `orchestrator/workflow/executable_ir.py`
  - defines node kinds, bound-address dataclasses, step-config unions, and the
    top-level `ExecutableWorkflow`;
  - does not define a dedicated executable-IR schema constant or validator.
- `orchestrator/workflow/lowering.py`
  - `_IRBuilder.build()` constructs `ExecutableWorkflow` directly from the
    shared validated workflow surface;
  - immediately derives `WorkflowRuntimePlan` and `SemanticWorkflowIR` from
    that IR before returning a `LoadedWorkflowBundle`.
- `orchestrator/workflow/loaded_bundle.py`
  - exposes `ir`, `runtime_plan`, `semantic_ir`, and `core_workflow_ast` as
    sibling typed bundle surfaces.
- `orchestrator/workflow_lisp/build.py`
  - writes `executable_ir.json`, `runtime_plan.json`, `semantic_ir.json`,
    `source_map.json`, and `workflow_boundary_projection.json`;
  - currently records explicit manifest artifact status only for
    `core_workflow_ast` and `semantic_ir`, even though executable IR and
    runtime plan are also emitted.
- `orchestrator/workflow_lisp/source_map.py`
  - claims `executable_ir` coverage in the persisted source-map document;
  - validates executable-node lineage only when validated bundles are present.
- `orchestrator/workflow_lisp/compiler.py`
  - already reserves the pass order `source_map -> shared_validation -> executable`;
  - currently uses the `executable` pass to include validated bundles in
    source-map lineage checks, not to run a distinct executable-IR validator.
- tests already prove the shared executable surface is real:
  - `tests/test_workflow_ir_lowering.py` checks node kinds, topology, runtime
    plan, and semantic-IR bridges;
  - `tests/test_workflow_semantic_ir.py` checks executable bridges,
    checkpoints, and semantic/runtime alignment;
  - `tests/test_workflow_lisp_build_artifacts.py` checks emitted
    `executable_ir.json`, `runtime_plan.json`, and source-map/runtime lineage;
  - `tests/test_workflow_lisp_diagnostics.py` checks executable pass ordering
    and `semantic_ir_invalid`/source-map bridge remapping.

That means the implementation gap is not "generate executable IR." It is to
turn existing executable behavior into a reviewed contract with explicit
authority and validation ownership.

## Internal Executable IR Contract

### 1. Authoritative Executable Surface

`LoadedWorkflowBundle.ir` is the authoritative executable workflow artifact.

Rules:

- `build.py` must serialize `validated_bundle.ir` exactly; it must not
  reconstruct executable IR from lowered workflows, source maps, or runtime
  plans.
- `runtime_plan`, `semantic_ir`, `source_map`, and debug YAML are projections
  over the validated executable IR plus other shared surfaces; they are not
  independent executable authorities.
- imported YAML bundles and compiled Workflow Lisp bundles cross reusable call
  boundaries as validated `LoadedWorkflowBundle` values only.
- a future direct frontend-to-executable path is allowed only if it still
  produces the same shared `ExecutableWorkflow` contract and validator output
  as the current shared loader/runtime pipeline.

### 2. Schema, Versioning, And Value-Strata Rules

Add one shared schema/version marker and validator contract for executable IR.

Recommended shared contract:

```text
WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"
validate_executable_workflow(ir: ExecutableWorkflow) -> None
```

Rules the validator must enforce:

- every `node_id` is unique and region membership is internally coherent;
- `body_region`, `finalization_region`, and `finalization_entry_node_id`
  reference known nodes and valid region placement;
- each node dataclass matches its declared `ExecutableNodeKind` and execution
  config family;
- fallthrough and routed-transfer targets reference known nodes when present;
- bound addresses reference only supported address families and known node ids;
- workflow input/output/artifact contracts reference only executable addresses
  or `None` as permitted by the current runtime contract;
- compile-time-only values do not appear in executable IR, including
  unresolved `ProcRef`, `WorkflowRef`, `let-proc` metadata, syntax objects,
  source spans, debug YAML payloads, or typed frontend nodes.

The `ExecutableWorkflow.version` field should continue to record the workflow
DSL version. The new schema/version contract distinguishes executable-IR shape
evolution from DSL version evolution.

### 3. Compatibility Path From Workflow Lisp

This slice codifies the current approved compatibility path:

```text
typed Workflow Lisp frontend
  -> lowered workflow dictionaries
  -> shared WorkflowLoader / LoadedWorkflowBundle validation path
  -> authoritative ExecutableWorkflow
  -> derived runtime plan / semantic IR / source map / build artifacts
```

Consequences:

- Workflow Lisp does not own executable lowering semantics directly in this
  tranche; it owns earlier authoring-time structure and later artifact/export
  checks.
- the executable contract is shared across YAML and Workflow Lisp surfaces;
- imported bundle support remains compatibility-oriented and bundle-typed, not
  JSON-sidecar-oriented.

### 4. Derived Bridge Layers

Derived layers must stay aligned to validated executable IR:

- `WorkflowRuntimePlan`
  - derived from validated executable IR plus state projection;
  - summarizes execution ordering, dependencies, checkpoints, artifacts, and
    observability;
  - must never be executable authority.
- `SemanticWorkflowIR`
  - carries executable bridge node ids, presentation keys, and checkpoint ids;
  - must validate those bridges against the same executable node universe.
- Workflow Lisp `source_map`
  - may claim `executable_ir` coverage only when every serialized executable
    node lineage entry maps to a validated executable node id;
  - must not infer executable coverage from lowered step ids alone.
- `workflow_boundary_projection` and debug YAML
  - remain explanatory build artifacts;
  - must not become a runtime contract or a substitute executable schema.

### 5. Frontend Executable Validation Pass

Keep the current stage-3 pass order, but narrow the executable checkpoint to a
real contract:

1. `shared_validation` produces validated bundles.
2. `executable` invokes shared executable-IR validation on each bundle IR.
3. `executable` then validates executable-node lineage and bridge coverage
   against the validated bundle set.

Diagnostics:

- structural executable failures should surface as `executable_ir_invalid`;
- bridge mismatches between executable IR and semantic/source-map/runtime-plan
  layers should preserve their current bridge-oriented diagnostic classes when
  possible;
- Workflow Lisp diagnostic remapping should keep authored `.orc` origins
  visible.

### 6. Command Boundary And Runtime-Native Constraints

Executable IR may encode command and provider runtime configuration, but it may
not weaken the command-adapter contract.

Rules:

- command-backed executable nodes may only reflect already-declared command
  boundaries, boundary kinds, and source-map behavior;
- executable IR must not encode hidden inline Python/shell semantics, nested
  helper-command behavior, or report-parsing authority;
- new executable node kinds or runtime-native transitions are out of scope for
  this slice and must follow the command-adapter promotion criteria and a
  separate accepted design.

### 7. Build Artifact And Manifest Contract

The frontend build surface must treat executable IR and runtime plan as
first-class artifacts.

Rules:

- `executable_ir.json` and `runtime_plan.json` are canonical build artifacts,
  not optional debug spillover;
- the build manifest should record emitted status for `executable_ir` and
  `runtime_plan` alongside existing Core AST and Semantic IR status entries;
- convenience exports must copy canonical artifact bytes from the build root,
  not regenerate executable projections independently;
- source-map and semantic-IR artifacts must continue to reference the selected
  entry workflow's executable node ids exactly.

## Test And Acceptance Surface

Implementation should add or update focused tests that prove the executable
contract, not just its current incidental behavior.

Primary test targets:

- `tests/test_workflow_ir_lowering.py`
- `tests/test_workflow_semantic_ir.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_diagnostics.py`

Required positive coverage:

- shared executable validation accepts currently valid IR emitted by the YAML
  loader and by Workflow Lisp builds;
- Workflow Lisp `executable` pass runs shared executable validation after
  shared validation and before executable-node lineage assertions finish;
- build artifacts and manifest record `executable_ir.json` and
  `runtime_plan.json` as first-class emitted artifacts;
- semantic IR executable bridges, runtime-plan node ids, and source-map
  executable-node lineage all match the same validated node set;
- compiled runtime artifacts contain no unresolved compile-time-only callable
  or syntax values.

Required negative coverage:

- invalid executable node references or address bindings raise
  `executable_ir_invalid`;
- a bundle whose source map claims executable coverage for an unknown node id
  still fails with the current source-map bridge diagnostics;
- a semantic IR bridge pointing at an unknown executable node still fails with
  `semantic_ir_invalid`;
- no helper script, inline shell/Python glue, or adapter loophole is
  introduced to make executable validation work.

Acceptance conditions:

- Workflow Lisp has a reviewed executable-IR contract aligned to the current
  shared implementation instead of only an implicit artifact shape;
- shared executable validation exists as a first-class checkpoint;
- build/export surfaces and bridge layers all treat validated executable IR as
  the only executable authority;
- the architecture stays bounded to the selected executable-IR component gap.

## Verification Expectations

When this slice is implemented, verification should include:

- `pytest --collect-only` for any test modules that add or rename tests;
- focused shared/runtime selectors for executable IR, semantic IR, and build
  artifacts;
- at least one Workflow Lisp compile/build integration check that emits
  `executable_ir.json`, `runtime_plan.json`, `semantic_ir.json`, and
  `source_map.json` for a selected entry workflow;
- evidence that imported compiled bundles and same-file Workflow Lisp bundles
  both continue to cross reusable boundaries as validated `LoadedWorkflowBundle`
  values, not as ad hoc executable sidecars.
