# Source Map Runtime Lineage Implementation Architecture

## Scope

This design gap covers only the bounded end-to-end source-map/runtime-lineage
slice selected for the Workflow Lisp frontend:

- define one implementation-ready source-map contract that carries authored
  `.orc` provenance through frontend compilation, lowering, validated workflow
  bundles, executable IR, runtime logs, and validation diagnostics;
- replace best-effort string matching for shared-validation remapping with a
  deterministic subject-reference bridge;
- persist source-map artifacts under the existing frontend build root with
  enough coverage metadata to validate what is implemented versus what remains
  deferred;
- extend runtime observability so compiled Workflow Lisp runs can explain both
  step execution and generated-node lineage using the persisted source-map
  sidecar;
- preserve the current shared runtime and validation seam instead of inventing
  a second execution path or fabricating fake Core AST / Semantic IR payloads.

Out of scope for this tranche:

- new frontend language forms, new stdlib forms, or changes to parsing,
  typing, macro semantics, procedure semantics, phase/resource/drain behavior,
  or workflow-ref resolution;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  pointer authority, variant proof, state persistence, queue semantics, or
  provider execution;
- new adapter kinds, legacy-adapter policy changes, runtime-native effect
  promotion, or command-boundary semantics beyond transporting existing
  certified-adapter provenance more explicitly;
- editor/LSP tooling, daemonized compile services, or a second diagnostics
  protocol outside the existing frontend/build/runtime surfaces.

This is an implementation architecture for the selected source-map/runtime-
lineage gap only. It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `44. Typed Frontend AST`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `72. Lowering Errors`
  - `74. Source Map Requirements`
  - `75. Runtime Observability`
  - `76. Build Artifacts`
  - `76.1 Editor And Lint Tooling Compatibility`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_lisp_source_map.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by prior
implementation-architecture documents and the current checkout:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation -> executable IR;
- reuse `SourcePosition`, `SourceSpan`, recursive syntax provenance, macro
  expansion stacks, `LispFrontendDiagnostic`, `LoweringOrigin`, and
  `LoweringOriginMap` rather than inventing a parallel provenance system;
- reuse the existing authored-mapping ->
  `elaborate_surface_workflow(...)` -> `lower_surface_workflow(...)` seam
  rather than generating YAML text or a second validator;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep command boundaries subject to the existing `external_tool` versus
  `certified_adapter` classification, including explicit source-map behavior
  for certified adapters where declared.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because this slice must preserve source lineage across `command-result`
boundaries and certified adapters without treating opaque scripts, pointer
files, or report text as semantic authority. This slice must not introduce:

- inline semantic shell or Python glue inside source-map generation;
- report parsing to recover provenance;
- hidden runtime rewrites of workflow meaning outside typed lowering;
- fake adapter lineage that is not declared by the adapter contract.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selector bundle, architecture target contract, and prior
implementation architectures remain the effective local steering surfaces.

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
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the existing staged frontend pipeline and package ownership split.
- Reuse the existing provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOrigin`,
  `LoweringOriginMap`,
  and `WorkflowProvenance`.
- Reuse the current build-root artifact model from the CLI/build slice rather
  than inventing a second persistence location for lineage data.
- Reuse the current validated-bundle and executable-IR runtime path instead of
  creating a `.orc`-only executor.
- Reuse the command-boundary contract, including certified-adapter metadata,
  instead of inventing a parallel provenance policy for commands.
- Reuse the existing honesty rule for deferred shared contracts:
  do not fabricate separate Core AST or Semantic IR artifacts when the current
  checkout does not expose them as independent serialized surfaces.

### New Decisions In This Slice

- Promote source mapping from a lowering-local helper into one dedicated
  frontend-owned source-map layer with stable origin keys and serialized
  schema.
- Extend the persisted `source_map.json` artifact from step/input/output/path
  origin notes into a fuller lineage index that also covers executable-node
  ancestry, validation-subject bindings, and coverage status.
- Introduce structured validation subject references so shared-validation
  errors can be remapped deterministically without message-text substring
  matching.
- Add source-map coverage validation as a build-time contract:
  compiled workflows must prove that generated steps, generated boundary
  fields, generated paths, executable nodes, and runtime-observable step ids
  all resolve to one authored origin.
- Keep Core AST and Semantic IR coverage explicit but deferred in the schema
  and manifest until the shared codebase exposes those surfaces as first-class
  serializable contracts.

### Conflicts Or Revisions

The CLI/build architecture already introduced `source_map.json`, but only as a
compact workflow/step/source-trace projection. This slice revises that
artifact narrowly:

- the path remains `source_map.json`;
- the schema becomes explicit and versioned;
- executable-node lineage, validation-subject bindings, and coverage metadata
  become part of the artifact instead of relying on ad hoc conventions.

The Stage 3 and defproc slices also relied on
`_remap_validation_message(...)` string matching over generated names. This
slice revises that implementation choice narrowly:

- shared validation still owns semantic checks;
- remapping no longer depends on message text when a structured subject
  reference is available;
- message-text matching remains only as a compatibility fallback during the
  transition and should be exercised by dedicated regression tests, not treated
  as the architecture's steady state.

The full design speaks in terms of Core AST and Semantic IR node coverage. The
current checkout still compiles through lowered authored mappings, validated
surface bundles, and executable IR without separately serialized Core AST or
Semantic IR packages. This slice therefore keeps the contract honest:

- reserve coverage slots for Core AST and Semantic IR;
- emit implemented lineage for frontend, lowered-surface, executable, runtime,
  and diagnostic surfaces now;
- mark unavailable shared-node surfaces as deferred shared contracts instead of
  fabricating fake nodes.

No prior slice is reversed on shared concepts such as spans, diagnostics, Core
Workflow AST, Semantic Workflow IR, TypeCatalog, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- one dedicated source-map data model and serialization layer for Workflow
  Lisp builds;
- deterministic origin-key assignment for generated steps, generated workflow
  boundary fields, generated paths, executable nodes, and validation subjects;
- the build-time source-map coverage validator and persisted coverage status;
- the bridge from lowered workflows and validated bundles into persisted
  `source_map.json`;
- the bridge from persisted source-map entries into runtime observability for
  compiled Workflow Lisp runs;
- the frontend-local remap layer that converts shared-validation errors with
  structured subject refs into source-mapped frontend diagnostics;
- focused tests for source-map serialization, coverage validation, runtime log
  rendering, and validation remapping.

This slice intentionally does not own:

- reader grammar, syntax-object semantics, macro expansion behavior, procedure
  lowering policy, phase/resource/drain stdlib behavior, or workflow-ref
  resolution;
- provider execution semantics, queue semantics, state persistence, or resume
  behavior;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog, or
  pointer-authority rules;
- new command-adapter certification rules beyond reusing existing metadata and
  source-map behavior fields;
- editor/LSP clients or a second lint/diagnostics transport.

## Current Checkout Facts

The current checkout already contains partial source-lineage plumbing:

- `orchestrator/workflow_lisp/lowering.py` defines `LoweringOrigin` and
  `LoweringOriginMap` for workflow, step, generated-input, generated-output,
  and generated-path origins.
- `orchestrator/workflow_lisp/build.py` already emits `source_map.json`, but
  the artifact currently records only `workflow_origin`, `step_ids`,
  `generated_inputs`, `generated_outputs`, and `generated_paths`.
- `orchestrator/workflow/surface_ast.py` already carries
  `WorkflowProvenance.frontend_kind`,
  `frontend_build_root`,
  `frontend_source_trace_path`,
  and `frontend_entry_workflow`.
- `orchestrator/runtime_observability.py` already persists
  `compiled_frontend` metadata into run state.
- `orchestrator/workflow/executor.py` already loads the persisted source trace
  and logs source/form data for compiled Workflow Lisp steps.
- `orchestrator/workflow_lisp/build.py` already parses certified-adapter
  `source_map_behavior` from the command-boundary manifest.
- `orchestrator/workflow_lisp/lowering.py` still remaps shared-validation
  failures by searching generated names inside error messages.
- no dedicated `source_map.py` package exists yet;
- no structured validation subject references exist in
  `orchestrator/exceptions.py`;
- no executable-node lineage index is currently persisted in `source_map.json`;
- `FrontendBuildManifest.artifact_status` already marks
  `core_workflow_ast` and `semantic_ir` as deferred shared contracts.

This slice should consolidate and complete that partial behavior, not replace
it with a new pipeline.

## Proposed Package Boundary

Extend the current packages with one dedicated source-map layer and narrow
shared-runtime metadata additions:

```text
orchestrator/
  exceptions.py                    # add optional structured validation subject refs
  runtime_observability.py         # persist source-map schema/version metadata
  workflow/
    elaboration.py                 # attach structured subject refs on validation errors
    executable_ir.py               # expose stable executable-node identity metadata
    executor.py                    # use executable-node/source-map lineage at runtime
    surface_ast.py                 # optional opaque frontend-origin metadata slots
  workflow_lisp/
    build.py                       # emit full source_map.json + coverage summary
    compiler.py                    # expose compiled provenance bundle to source-map builder
    diagnostics.py                 # add source-map validation/remap diagnostics
    lowering.py                    # generate stable origin keys and subject bindings
    source_map.py                  # new schema, serialization, validation helpers
```

Responsibilities:

- `workflow_lisp/source_map.py`
  - define the serialized source-map schema;
  - normalize origin entries, executable-node lineage entries, and validation
    subject bindings;
  - validate coverage and produce deterministic diagnostics for missing or
    ambiguous lineage.
- `workflow_lisp/lowering.py`
  - assign stable origin keys to every lowered workflow surface owned by the
    frontend;
  - export validation-subject bindings instead of only free-form origin notes;
  - keep `LoweringOriginMap` authoritative for lowering-time provenance, but
    enrich it with serialized-key support.
- `workflow_lisp/build.py`
  - assemble full per-workflow source-map documents from compiled/lowered
    workflows and validated bundles;
  - emit coverage metadata and reserved deferred-contract sections;
  - write the updated `source_map.json` artifact and include schema/version in
    the build manifest.
- `workflow_lisp/diagnostics.py`
  - add source-map-specific diagnostic codes and JSON serialization.
- `orchestrator/exceptions.py` and `workflow/elaboration.py`
  - carry structured validation subject references without teaching shared
    validation anything about `.orc`.
- `workflow/executor.py`
  - consume persisted executable-node/step lineage for runtime logs and
    diagnostic notes.
- `runtime_observability.py`
  - persist the source-map schema/version or coverage summary needed by
    operators to interpret compiled frontend runs.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/modules.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- `orchestrator/workflow_lisp/resource.py`
- `orchestrator/workflow_lisp/resource_stdlib.py`
- `orchestrator/workflow_lisp/drain_stdlib.py`
- shared provider/runtime/state modules outside the narrow provenance hooks
  listed above

## Data Model

### Stable Origin Keys

Every serialized lineage entry needs one opaque deterministic identity so later
phases can refer to it without re-parsing prose. Add one frontend-owned stable
origin-key scheme with these properties:

- scoped by canonical workflow name;
- deterministic from lowered structure, not runtime timestamps;
- unique across:
  workflow roots,
  generated step ids,
  generated boundary inputs,
  generated boundary outputs,
  generated internal inputs,
  generated paths,
  executable nodes,
  validation subjects.

The architecture does not require a human-friendly string format, but the
format must be:

- sortable;
- stable across equivalent recompiles;
- namespace-separated by entity kind.

### Source Map Entry

`workflow_lisp/source_map.py` should expose one normalized authored-origin
record rather than ad hoc dict payloads:

```text
SourceMapEntry(
  origin_key,
  entity_kind,
  workflow_name,
  source_file,
  span,
  form_path,
  module_name,
  expansion_stack,
  notes,
  generated_name_origin?,
)
```

This is the authoritative authored-origin payload for Workflow Lisp source
maps. It reuses existing spans, form paths, and expansion provenance rather
than redefining them.

### Validation Subject Reference

Add one shared-but-generic subject-ref carrier on validation errors:

```text
ValidationSubjectRef(
  subject_kind,
  subject_name,
  workflow_name?,
)
```

Examples of subject kinds:

- `step_id`
- `generated_input`
- `generated_output`
- `generated_path`
- `workflow`

Shared validation remains oblivious to `.orc`. It only reports the generated
subject it is already validating. The frontend remap layer resolves that
subject through the source-map index to the authored origin.

### Executable Node Lineage

Persist executable-node ancestry as a first-class section in `source_map.json`.
For each executable node that may surface in runtime logs, tracebacks, or
observability state, record:

```text
ExecutableNodeLineage(
  node_id,
  workflow_name,
  executable_kind,
  region,
  surface_step_id?,
  origin_key,
)
```

This keeps runtime lineage deterministic even when one authored step lowers to
multiple executable nodes or when the runtime is executing finalization or
control-flow bookkeeping nodes rather than the original authored step name.

### Coverage Status

The source-map artifact must declare implemented versus deferred coverage
explicitly. Keep one top-level coverage section such as:

```text
coverage:
  frontend_ast: covered
  lowered_surface: covered
  shared_validation_subjects: covered
  executable_ir: covered
  runtime_logs: covered
  core_workflow_ast: deferred_shared_contract
  semantic_ir: deferred_shared_contract
```

This reuses the existing honesty policy from build manifests rather than
pretending unavailable shared-node surfaces are implemented.

## Compile-Time And Build Flow

The compile/build path for source mapping becomes:

1. Frontend parsing, expansion, typing, and lowering keep using the existing
   provenance substrate.
2. Lowering assigns stable origin keys while producing `LoweringOriginMap`.
3. Shared validation and executable-IR lowering proceed through the existing
   authored-mapping seam.
4. The frontend build layer constructs one canonical `WorkflowLispSourceMap`
   document by joining:
   - lowering origins,
   - validated-bundle workflow metadata,
   - executable IR node ids and kinds,
   - validation-subject refs,
   - selected-entry-workflow status,
   - deferred shared-contract status.
5. The source-map validator checks coverage before the build artifact is
   written.
6. `build.py` persists the validated `source_map.json` sidecar and records its
   schema/version in the build manifest and runtime provenance.

This slice must not re-open or re-lower workflows solely to synthesize source
maps. The source map is a byproduct of the existing compile and validation
pipeline, not a second compiler.

## Shared-Validation Diagnostic Bridge

The steady-state remap flow should be:

1. shared validation emits `ValidationError` plus zero or more
   `ValidationSubjectRef` entries;
2. the frontend remap layer resolves those refs through the source-map index;
3. the remapped `LispFrontendDiagnostic` uses the authored span, form path,
   expansion stack, and notes from the resolved entry;
4. only if no subject ref exists does the compatibility fallback consult the
   old generated-name substring search.

Add focused source-map diagnostics for this slice:

- `source_map_missing`
- `source_map_duplicate_key`
- `source_map_validation_ref_missing`
- `source_map_executable_node_unmapped`
- `source_map_runtime_trace_invalid`

The compatibility fallback should remain test-covered but explicitly treated as
temporary debt. New lineage features must use structured subject refs instead
of extending message-text parsing.

## Runtime Observability Bridge

Runtime observability should consume the persisted source-map sidecar, not
re-run frontend compilation.

Required runtime behavior:

- when `WorkflowProvenance.frontend_kind == "workflow_lisp"`, the executor
  loads the persisted source-map artifact once;
- runtime step display resolves authored provenance by executable node id
  first, then by surface step id as a compatibility path;
- log output continues to show generated step ids, but also includes authored
  source location and form path where available;
- run state records enough compiled-frontend metadata to tell operators which
  source-map schema/version and build root were used.

This slice does not require runtime logs to expose every internal node by
default. It requires that when a node is surfaced in logs or diagnostics, the
runtime can explain its authored origin deterministically.

## Command And Adapter Lineage

This slice must preserve command-boundary transparency without widening command
semantics:

- `external_tool` commands inherit the authored `command-result` origin unless
  the workflow already exposes finer generated-path lineage through structured
  outputs;
- `certified_adapter` commands may contribute adapter-specific source-map
  behavior only through declared manifest metadata such as
  `source_map_behavior`;
- the source-map artifact may record adapter identity and source-map behavior
  as metadata, but must not parse adapter reports or inspect arbitrary stdout
  to reconstruct provenance;
- missing certified-adapter source-map declarations remain an adapter-contract
  problem, not a reason for the frontend to invent hidden semantics.

## Testing And Verification

Focused implementation tests should cover:

- deterministic source-map serialization for multiple workflows and shared
  display names;
- executable-node lineage emission and runtime lookup;
- validation-remap behavior using structured subject refs;
- compatibility fallback coverage while legacy message-text matching still
  exists;
- persisted build manifest/source-map coverage status;
- runtime observability logging for compiled Workflow Lisp runs;
- certified-adapter provenance metadata transport without report parsing.

Primary test modules for this slice:

- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_diagnostics.py`
- `tests/test_runtime_observability.py`
- `tests/test_runtime_observability_cli.py`

## Implementation Order

1. Add the dedicated source-map schema and serializer in
   `orchestrator/workflow_lisp/source_map.py`.
2. Extend lowering to emit stable origin keys and validation-subject bindings.
3. Extend shared validation error plumbing with structured subject refs.
4. Extend build artifact emission and coverage validation.
5. Extend executor/runtime observability to consume executable-node lineage.
6. Add focused tests and one compile smoke command that proves the emitted
   source-map artifact covers the selected entry workflow.

## Risks And Mitigations

- Risk: this slice quietly redefines shared validation or executable IR
  contracts.
  Mitigation: keep shared additions opaque and generic; the frontend still owns
  authored remapping and persisted source-map schema.

- Risk: runtime lineage stays step-name-based and misses control-flow or
  finalization nodes.
  Mitigation: executable-node lineage is a first-class artifact section, not a
  later optional enhancement.

- Risk: build artifacts claim Core AST or Semantic IR coverage that the
  checkout does not implement.
  Mitigation: preserve explicit deferred coverage status in both the source-map
  artifact and build manifest.

- Risk: adapter/source-map metadata becomes a loophole for hidden semantic
  scripts.
  Mitigation: keep command-adapter metadata declarative and governed by the
  existing command adapter contract.
