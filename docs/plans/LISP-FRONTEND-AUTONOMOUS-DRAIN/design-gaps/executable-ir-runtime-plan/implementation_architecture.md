# Executable IR And Runtime Plan Implementation Architecture

## Scope

This design gap covers only the missing executable-IR/runtime-plan contract
needed to close the Workflow Lisp full-design pipeline after the existing
frontend, lowering, source-map, CLI, and migration slices:

- define one implementation-ready runtime contract between validated workflow
  meaning and the existing executor;
- formalize the shared executable IR surfaces the frontend already lowers into;
- add a deterministic runtime-plan artifact that summarizes step order,
  dependencies, artifact publication, snapshots, observability hooks, and
  resume checkpoints without becoming a second execution authority;
- keep the current shared loader/executor seam honest while the repo still
  lacks serialized Core AST and Semantic IR artifacts;
- make the future Semantic IR handoff explicit so this slice can be reused when
  the shared semantic contract lands.

Out of scope for this tranche:

- new frontend language forms, new stdlib forms, or revisions to parsing,
  modules, macros, procedures, workflow refs, phase stdlib, resource stdlib,
  or drain semantics;
- redesign of shared provider execution, queue semantics, state persistence, or
  command-adapter certification policy;
- runtime-native promotion of adapter-backed behavior or invention of new node
  kinds that the shared runtime cannot already execute;
- fabrication of fake `core_workflow_ast.json` or `semantic_ir.json` artifacts
  before those shared contracts exist in code;
- any replacement of the product design in
  `docs/design/workflow_lisp_frontend_specification.md`.

This is an implementation architecture for exactly the selected
`executable-ir-runtime-plan` gap. It does not reopen the rest of the frontend.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `49. Runtime Plan`
  - `59. Validation Sequence`
  - `64. Snapshot Validation`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `specs/state.md`
- `specs/queue.md`

The slice must also preserve the guardrails established by the existing
implementation architectures and the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared execution,
  state, resume, and observability semantics under `orchestrator/workflow/`;
- reuse the current staged path:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation -> executable bundle;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep `ExecutableWorkflow` authoritative for runtime step configuration and
  `WorkflowStateProjection` authoritative for persisted/reporting step
  identities and resume-facing compatibility keys;
- keep source-map lineage in the persisted frontend `source_map.json` sidecar
  rather than duplicating frontend spans into a second runtime-only provenance
  format;
- keep command boundaries on the existing `external_tool` versus
  `certified_adapter` contract and carry their metadata through runtime-plan
  summaries without interpreting shell text.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because this slice must summarize command steps, certified adapters,
source-map behavior, and resume-visible command boundaries without letting the
runtime plan become a loophole for hidden procedural semantics, report parsing,
pointer-as-state, or uncataloged runtime-native promotion.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, architecture target contract, progress ledger, and prior
implementation architectures remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
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

- Reuse the current staged frontend pipeline and the existing authored-mapping
  -> shared-validation -> executable-bundle seam.
- Reuse `ExecutableWorkflow` in `orchestrator/workflow/executable_ir.py` as
  the runtime-owned execution authority rather than inventing a frontend-local
  executor contract.
- Reuse `WorkflowStateProjection` in
  `orchestrator/workflow/state_projection.py` as the authority for persisted
  step ordering, presentation keys, loop/runtime step ids, and resume-facing
  compatibility lookups.
- Reuse `LoadedWorkflowBundle` as the loaded artifact passed through loader,
  CLI, runtime, imported-bundle linking, and compiled frontend build flows.
- Reuse the source-map lineage substrate:
  `WorkflowProvenance`,
  `LoweringOriginMap`,
  persisted `source_map.json`,
  validation-subject bindings,
  executable-node lineage,
  and runtime observability bridges.
- Reuse the existing command-boundary classification and certified-adapter
  metadata without inventing a second runtime-plan command taxonomy.

### New Decisions In This Slice

- Add one shared `WorkflowRuntimePlan` contract derived from
  `ExecutableWorkflow` plus `WorkflowStateProjection`.
- Treat the runtime plan as a deterministic indexed view over executable IR,
  not as a second execution authority and not as a substitute for future
  Semantic IR.
- Extend `LoadedWorkflowBundle` to carry `runtime_plan` alongside `surface`,
  `ir`, `projection`, `imports`, and `provenance`.
- Add one shared derivation function that computes runtime-plan ordering,
  dependencies, artifact/snapshot summaries, observability hooks, and resume
  checkpoints from the existing executable bundle surfaces.
- Add one persisted `runtime_plan.json` build artifact for compiled Workflow
  Lisp entrypoints.
- Keep frontend provenance out of the shared runtime-plan schema:
  runtime-plan entries reference node ids, step ids, and projection keys;
  Workflow Lisp joins those ids to authored spans through `source_map.json`.
- Keep the current checkout honest about missing serialized Semantic IR:
  runtime-plan derivation uses `LoadedWorkflowBundle.ir` and
  `LoadedWorkflowBundle.projection` now, but its schema is constrained so a
  future `SemanticWorkflowIR` may become the upstream source without changing
  the persisted runtime-plan shape.

### Conflicts Or Revisions

The CLI/build architecture already emits `executable_ir.json` and
`source_map.json`, and the source-map/runtime-lineage slice already covers
executable-node lineage. This slice revises those surfaces narrowly:

- add `runtime_plan.json` as a new build artifact;
- keep `executable_ir.json` as the full runtime configuration artifact;
- keep `source_map.json` provenance-focused instead of duplicating execution
  order or checkpoint semantics there.

The full design treats Semantic IR as the authoritative bridge to executable IR
and runtime plan. The current checkout still marks `semantic_ir` as a deferred
shared contract. This slice does not reverse that rule. It defines a bounded
compatibility bridge:

- current derivation source:
  validated `LoadedWorkflowBundle.ir` plus `LoadedWorkflowBundle.projection`;
- future derivation source:
  validated `SemanticWorkflowIR` lowered into the same shared executable and
  runtime-plan contract.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- one shared runtime-plan schema derived from existing executable/runtime
  bundle surfaces;
- one shared derivation helper from
  `ExecutableWorkflow + WorkflowStateProjection -> WorkflowRuntimePlan`;
- extension of `LoadedWorkflowBundle` to carry runtime-plan data;
- build-artifact emission of `runtime_plan.json` for compiled Workflow Lisp
  entrypoints;
- narrow executor, observability, and resume integration points that should
  consume runtime-plan summaries instead of reconstructing equivalent indexes
  ad hoc;
- focused tests for runtime-plan derivation, serialization, frontend build
  artifact emission, observability joins, and resume-checkpoint behavior.

This slice intentionally does not own:

- frontend parsing, syntax, macro expansion, procedure lowering, phase/resource
  stdlib lowering, workflow-ref resolution, or boundary flattening;
- redesign of executable node kinds, shared step execution semantics, queue
  policy, state-manager storage, or provider invocation behavior;
- command-adapter certification rules, runtime-native promotion, or new hidden
  command semantics;
- fabrication of serialized Core AST or Semantic IR artifacts before the
  shared runtime exposes them as real contracts;
- a second provenance format that bypasses `WorkflowProvenance` and
  `source_map.json`.

## Current Checkout Facts

- `orchestrator/workflow/executable_ir.py` already defines the shared immutable
  executable-node and executable-workflow dataclasses used by the runtime.
- `orchestrator/workflow/state_projection.py` already defines the projection
  tables the runtime uses for persisted step identities, presentation keys,
  loop step ids, call-boundary step ids, and execution ordering.
- `orchestrator/workflow/lowering.py` already lowers validated surface
  workflows to `(ExecutableWorkflow, WorkflowStateProjection)`.
- `orchestrator/workflow/loaded_bundle.py` already packages `surface`, `ir`,
  `projection`, `imports`, and `provenance` as the loaded execution bundle.
- `orchestrator/workflow/executor.py` already derives ordered execution,
  current-step presentation, compiled-frontend source context, and resume
  restart logic from `ir`, `projection`, and provenance-loaded source maps.
- `orchestrator/workflow_lisp/build.py` already emits `executable_ir.json`,
  `source_map.json`, and `workflow_boundary_projection.json`, but not a
  `runtime_plan.json` artifact.
- `orchestrator/workflow_lisp/source_map.py` already marks `executable_ir`
  coverage as implemented and `semantic_ir` as `deferred_shared_contract`.
- there is no shared `runtime_plan.py` contract in the current checkout;
- there is no serialized `semantic_ir.json` build artifact in the current
  checkout.

The gap is therefore not executable lowering from scratch. The gap is to make
the runtime-facing contract explicit, shared, serializable, and future-proof
for the eventual Semantic IR handoff.

## Proposed Package Boundary

Introduce one shared runtime-plan module and thread it through the existing
bundle/build surfaces:

```text
orchestrator/workflow/
  executable_ir.py
  state_projection.py
  runtime_plan.py          # new
  loaded_bundle.py
  lowering.py
  executor.py

orchestrator/workflow_lisp/
  build.py
  source_map.py
```

Responsibilities:

- `orchestrator/workflow/runtime_plan.py`
  - define the shared runtime-plan schema;
  - derive runtime-plan entries from executable IR and state projection;
  - validate internal plan invariants such as stable node coverage, dependency
    closure, and checkpoint uniqueness.
- `orchestrator/workflow/loaded_bundle.py`
  - extend `LoadedWorkflowBundle` with `runtime_plan`;
  - keep bundle helpers runtime-compatible for YAML and compiled frontend
    workflows alike.
- `orchestrator/workflow/lowering.py`
  - derive `WorkflowRuntimePlan` immediately after executable lowering;
  - keep executable IR authoritative and avoid parallel lowering logic.
- `orchestrator/workflow/executor.py`
  - prefer runtime-plan summaries for ordered-node traversal,
    presentation-name lookups, checkpoint registration, and observability
    displays where that avoids reconstructing equivalent indexes.
- `orchestrator/workflow_lisp/build.py`
  - emit `runtime_plan.json`;
  - record it in the build manifest alongside the existing artifacts.
- `orchestrator/workflow_lisp/source_map.py`
  - keep node-id lineage aligned with runtime-plan node ids;
  - continue to own authored-source provenance rather than runtime-plan data.

Planned test surface:

```text
tests/
  test_workflow_ir_lowering.py
  test_workflow_state_projection.py
  test_resume_command.py
  test_runtime_observability.py
  test_workflow_lisp_build_artifacts.py
```

## Data Model

### `ExecutableWorkflow` Remains The Runtime Authority

`ExecutableWorkflow` continues to own the executable step configuration:

- node kinds;
- ordered body and finalization regions;
- provider/command/call/materialization/select-variant config payloads;
- routed transfers and fallthrough edges;
- bound contracts for inputs, outputs, and published artifacts.

This slice does not duplicate those payloads into a second mutable executor
shape. The runtime plan references executable node ids and summarises
execution-relevant structure; the executor still executes against
`ExecutableWorkflow`.

### `WorkflowStateProjection` Remains The Compatibility Authority

`WorkflowStateProjection` continues to own:

- compatibility execution indexes;
- persisted/reporting presentation keys;
- node-id to step-id mappings;
- loop iteration step-key and runtime-step-id formatters;
- call-boundary runtime-step-id rules;
- structured `if` and `match` branch/case projection metadata.

Resume logic, persisted state compatibility, and reporting surfaces remain
anchored to this projection. The runtime plan copies only the summaries needed
for inspection and checkpoint planning.

### `WorkflowRuntimePlan`

Add one shared derived record:

```python
WorkflowRuntimePlan(
    workflow_name: str,
    ordered_node_ids: tuple[str, ...],
    nodes: Mapping[str, RuntimePlanNode],
    artifacts: Mapping[str, RuntimeArtifactPlan],
    snapshots: tuple[RuntimeSnapshotPlan, ...],
    resume_checkpoints: tuple[RuntimeResumeCheckpoint, ...],
    observability: RuntimeObservabilityPlan,
)
```

Required properties:

- deterministic for a given executable workflow and projection;
- references executable node ids instead of copying full execution configs;
- serializable for build artifacts and explain/debug use;
- usable by runtime observability and resume planning without depending on
  frontend-only packages.

### `RuntimePlanNode`

Each runtime-plan node summary records:

- `node_id`
- `step_id`
- `presentation_key`
- `display_name`
- `kind`
- `region`
- `execution_index`
- `lexical_scope`
- `fallthrough_node_id`
- `routed_transfer_targets`
- `dependency_node_ids`
- `nested_body_node_ids`
- `call_alias` when the node is a call boundary
- `command_boundary_kind` and `command_boundary_name` when the node executes a
  command or certified adapter

`dependency_node_ids` is derived, not authored. It exists so the runtime plan
can express one stable execution graph without forcing consumers to reverse
engineer nested control flow from raw node fields.

### Artifact, Snapshot, And Resume Summaries

`RuntimeArtifactPlan` records the runtime-visible publication contract for one
artifact or bundle-emitting surface:

- artifact or bundle name;
- source node id;
- contract name and kind;
- publication mode:
  `publishes`, `expected_output`, `output_bundle`, or `variant_output`.

`RuntimeSnapshotPlan` records every snapshot-sensitive executable boundary:

- owner node id;
- snapshot operation kind;
- related candidate or selection surfaces;
- whether the snapshot participates in selection or only evidence capture.

`RuntimeResumeCheckpoint` records every restartable boundary:

- checkpoint kind:
  `top_level_node`,
  `call_boundary`,
  `repeat_until_frame`,
  `for_each_frame`,
  or `finalization_node`;
- node id and step id;
- persisted presentation key;
- runtime-step-id policy when loop iteration qualification is required.

The runtime plan does not invent new resume semantics. It serializes the
checkpoint surfaces already implied by `WorkflowStateProjection`,
call-boundary projections, and loop projections.

### Observability Summary

`RuntimeObservabilityPlan` records only runtime-owned observability facts:

- workflow provenance summary;
- top-level execution order;
- per-node display name and presentation key;
- whether frontend source-trace lineage is available through provenance;
- command-boundary summaries for command/adapters that should be surfaced in
  logs.

Frontend spans, authored form paths, and expansion stacks remain in
`source_map.json`. Runtime plan references the same node ids and step ids so
the frontend bridge can join them without duplicating source provenance here.

## Compilation And Handoff Pipeline

The bounded implementation path becomes:

```text
.orc source
  -> frontend syntax / typed workflows / lowering
  -> authored workflow mappings
  -> shared validation and elaboration
  -> ExecutableWorkflow + WorkflowStateProjection
  -> WorkflowRuntimePlan
  -> LoadedWorkflowBundle(surface, ir, projection, runtime_plan, provenance)
  -> existing executor
```

For shared workflows loaded from YAML, the same shared lowerer derives:

```text
validated surface workflow
  -> ExecutableWorkflow + WorkflowStateProjection
  -> WorkflowRuntimePlan
  -> LoadedWorkflowBundle(...)
```

This keeps runtime-plan semantics shared and keeps Workflow Lisp from owning a
special executor contract.

## Derivation Rules

### Execution Order

- top-level order comes from
  `WorkflowStateProjection.ordered_execution_node_ids()`;
- each ordered node summary also records its `region` and stable
  `execution_index`;
- nested `repeat_until` and `for_each` bodies are recorded in
  `nested_body_node_ids`, but their top-level restart surface remains the frame
  node plus the projection-owned runtime step-id policy.

### Dependencies

`dependency_node_ids` is derived from:

- predecessor ordering implied by `ordered_execution_node_ids()`;
- explicit `fallthrough_node_id`;
- `routed_transfers` targets;
- nested container membership for loop and branch marker/join nodes;
- call-boundary placement relative to its surrounding top-level or nested frame.

The runtime plan must not infer semantics from prompt text, shell text, or
report contents.

### Artifact And Snapshot Surfaces

Artifact and snapshot summaries are derived only from executable configuration:

- `publishes`
- `expected_outputs`
- `output_bundle`
- `variant_output`
- `pre_snapshot`
- `select_variant_output`
- `materialize_artifacts`

If a command step carries semantic behavior through a certified adapter, the
runtime plan records only the adapter identity and boundary kind already
declared by the command-boundary manifest. It does not inspect command text.

### Semantic IR Compatibility Bridge

The full design says runtime plan should follow Semantic IR. The current repo
does not yet serialize or persist `SemanticWorkflowIR`. This slice therefore
defines one compatibility rule:

- `WorkflowRuntimePlan` is derived today from the validated executable bundle
  surfaces the shared runtime already owns;
- when a real shared Semantic IR implementation lands, it must lower into the
  same `ExecutableWorkflow`, `WorkflowStateProjection`, and
  `WorkflowRuntimePlan` contract without changing the runtime-plan schema.

This preserves the full-design direction without fabricating a fake semantic
artifact today.

## Runtime Consumption Model

The executor remains driven by the shared executable bundle, but should
gradually consume runtime-plan summaries where they replace duplicated
reconstruction logic:

- ordered top-level node traversal;
- presentation-name selection;
- command-boundary display hints;
- call-boundary and loop checkpoint metadata;
- finalization ordering for status/reporting views.

Resume planning continues to use the projection-backed persisted state model.
The runtime plan is an inspection and indexing aid, not a replacement for the
projection tables or persisted state schema.

## Diagnostics And Observability

- build-time runtime-plan validation failures emit deterministic frontend
  diagnostics when the bundle came from Workflow Lisp and ordinary validation
  errors otherwise;
- compiled-frontend runtime logs continue to resolve authored spans through
  `source_map.json`;
- runtime-plan node ids, step ids, and command-boundary summaries must line up
  exactly with source-map executable-node lineage and validation-subject
  bindings;
- `runtime_plan.json` remains source-map-adjacent but not provenance-owning.

## Test Strategy

Shared runtime tests:

- verify runtime-plan ordering matches projection ordering and finalization
  ordering;
- verify dependency closure for plain linear flows, call boundaries,
  `repeat_until`, `for_each`, `if`, and `match`;
- verify snapshot and artifact summaries are derived from executable configs
  only;
- verify resume checkpoint summaries align with projection-owned runtime step-id
  rules.

Frontend/build tests:

- verify `runtime_plan.json` is emitted for compiled `.orc` entrypoints;
- verify build-manifest artifact paths include the runtime plan;
- verify runtime-plan node ids match executable-node lineage in
  `source_map.json`;
- verify compiled-frontend observability still resolves step displays and
  command-boundary metadata correctly.

Regression tests:

- re-run projection and resume tests that already guard loop and call-boundary
  restart behavior;
- re-run compiled-frontend observability tests so runtime-plan adoption does
  not regress authored-source displays.

## Implementation Sequence

1. Add `orchestrator/workflow/runtime_plan.py` with shared dataclasses,
   derivation helpers, and plan validation.
2. Extend shared lowering to derive `WorkflowRuntimePlan` immediately after
   `ExecutableWorkflow` and `WorkflowStateProjection`.
3. Extend `LoadedWorkflowBundle` and loader/front-end validation bridges to
   carry the runtime plan.
4. Emit `runtime_plan.json` from `orchestrator/workflow_lisp/build.py`.
5. Update executor and observability helpers to consume runtime-plan summaries
   where they currently rebuild equivalent indexes.
6. Add focused shared-runtime, resume, observability, and frontend build
   artifact tests.

## Acceptance Conditions

- there is one shared runtime-plan schema derived from executable IR and state
  projection, with no second executor contract;
- `LoadedWorkflowBundle` carries runtime-plan data for validated workflows;
- compiled Workflow Lisp builds emit `runtime_plan.json` beside
  `executable_ir.json` and `source_map.json`;
- runtime-plan node ids, step ids, and checkpoint summaries align with shared
  projection logic and compiled-frontend source-map lineage;
- command/adapters remain represented only through existing declared boundary
  metadata;
- the design stays honest about missing serialized Semantic IR while keeping a
  stable bridge point for when that shared contract lands.

## Verification Plan

- collect and run focused executable-IR, state-projection, resume,
  observability, and build-artifact tests first;
- run at least one compiled Workflow Lisp build smoke command that proves
  `runtime_plan.json` is emitted;
- run one `.orc` dry-run smoke command so runtime-plan changes remain aligned
  with the live executor path rather than only artifact serialization.
