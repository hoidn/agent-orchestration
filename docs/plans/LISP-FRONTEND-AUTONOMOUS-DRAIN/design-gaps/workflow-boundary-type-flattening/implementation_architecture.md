# Workflow Boundary Type Flattening Implementation Architecture

## Scope

This design gap covers only the bounded workflow-boundary type-flattening
slice selected by the current drain state:

- preserve authored workflow parameters and returns as structured record/union
  types in the frontend pipeline and future Semantic Workflow IR;
- define the exact compatibility seam where flattening into current shared
  workflow `inputs` / `outputs` is still allowed;
- unify record-boundary flattening and union-return projection into one
  compiler-owned boundary-projection contract;
- require provenance and source-trace coverage for every generated flattened
  field that can appear in shared-validation errors or build artifacts;
- expose the projection mapping as an explicit compile/build artifact instead
  of leaving it implicit in generated field names and origin maps.

Out of scope for this tranche:

- new frontend language forms, new stdlib forms, or workflow-runtime behavior
  changes;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or runtime
  state persistence;
- new command-step, adapter, or runtime-native effect semantics;
- reclassification of `Provider`, `Prompt`, `Json`, or other non-boundary
  types beyond the existing frontend decisions;
- report parsing, pointer-as-state, inline semantic shell/Python glue, or
  YAML-text generation.

This is an implementation architecture for the selected flattening gap only.
It does not replace the product design in
`docs/design/workflow_lisp_frontend_specification.md`.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `45. Core Workflow AST`
  - `47. Semantic IR`
  - `50. defworkflow Lowering`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
  - `77. Compile`
  - `110. Type Flattening`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `7. Provider And Command Results`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
  - `14. Implementation Stages`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/9/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve the guardrails established by the earlier
implementation architectures and the current codebase:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and shared
  runtime semantics under `orchestrator/workflow/`;
- reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation -> build artifacts;
- keep `WorkflowSignature`, typed workflow bodies, and typed results as the
  semantic authority for workflow boundaries inside the frontend;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse existing command-boundary classification and certified-adapter rules
  unchanged; flattening must not become a loophole for command semantics.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
even though this slice does not add new command forms. Boundary projection must
not absorb or obscure command-step semantics, adapter effects, or runtime-native
promotion decisions inside generated workflow `inputs` / `outputs`.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selector bundle, architecture target contract, and prior
implementation architectures remain the effective local steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`

### Decisions Reused

- Reuse the existing frontend provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax metadata,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  `LoweringOriginMap`,
  and the persisted `FrontendSourceTrace`.
- Reuse `WorkflowSignature` as the authoritative structured workflow-boundary
  contract inside the frontend instead of treating lowered `inputs` / `outputs`
  as the primary type surface.
- Reuse `orchestrator/workflow_lisp/contracts.py` as the owned boundary-contract
  module and `orchestrator/workflow_lisp/lowering.py` as the only lowering seam
  that may materialize flattened compatibility fields.
- Reuse `FlattenedContractField` for record-boundary leaf mappings and
  `UnionWorkflowBoundaryProjection` for union-return projection instead of
  inventing a second flattening vocabulary.
- Reuse the existing authored-mapping ->
  `elaborate_surface_workflow(...)` ->
  `lower_surface_workflow(...)` bridge and the existing build artifact layer in
  `orchestrator/workflow_lisp/build.py`.
- Reuse the Stage 6 rule that union return projection is legal only when
  variant-specific access still requires proof after the workflow call.

### New Decisions In This Slice

- Treat flattening as a bounded compatibility projection, not as the real
  frontend workflow-boundary type system.
- Keep structured workflow signatures authoritative in:
  workflow definitions,
  typed expressions,
  call checking,
  effect summaries,
  diagnostics,
  compile results,
  and any future Semantic Workflow IR.
- Localize compatibility flattening to four surfaces only:
  - lowered shared workflow `inputs` / `outputs`;
  - lowered `call` binding names and call-result field refs;
  - provenance entries for generated fields that can appear in shared
    validation or runtime/build artifacts;
  - one explicit compile/build artifact that records the projection mapping.
- Make record flattening and union-return projection part of one compiler-owned
  boundary-projection contract assembled from:
  `WorkflowSignature`,
  `FlattenedContractField`,
  and optional `UnionWorkflowBoundaryProjection` metadata.
- Separate authored boundary fields from generated internal write-root inputs:
  managed write roots remain generated lowering inputs, but they are not part
  of the authored workflow signature and must be labeled as internal in
  projection artifacts.
- Add a dedicated frontend artifact,
  `workflow_boundary_projection.json`, so downstream tools can inspect the
  structured-to-flat mapping without reverse-engineering generated names from
  `source_map.json`.

### Conflicts Or Revisions

Stage 3 framed flattening as a temporary workflow-boundary bridge and Stage 4
used one-off record projections to stay on a record-only boundary. The current
checkout now already supports recursive record flattening, union-return
projection, and origin metadata. This slice revises the architecture narrowly:

- the bounded compatibility seam is now explicit rather than described as
  informal temporary debt;
- Stage 4-style projection records become one instance of the general boundary
  projection model rather than a special-case translation trick;
- the build/CLI slice keeps `FrontendSourceTrace` provenance-focused while this
  slice adds a separate boundary-projection artifact for contract mapping.

This is not a revision of shared concepts such as Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- the frontend-local contract for projecting structured workflow signatures to
  the current shared flat boundary vocabulary;
- deterministic recursive flattening of record parameters and record returns;
- deterministic union-return projection metadata for workflow boundaries;
- separation between authored boundary fields and compiler-generated internal
  write-root inputs;
- source-trace and origin-map obligations for generated flattened fields;
- the build artifact that persists boundary projection metadata for compiled
  `.orc` workflows;
- focused tests for flattening, union projection, collision handling,
  provenance coverage, and build-artifact emission.

This slice intentionally does not own:

- the reader, macro expander, base typechecker, or workflow runtime;
- shared validation semantics, runtime state layout, queue semantics, or
  pointer authority rules;
- provider/prompt extern transport rules or command-boundary classification;
- new source-map infrastructure beyond extending existing frontend-owned origin
  and build-artifact surfaces;
- new runtime transport for structured workflow values.

## Current Checkout Facts

The current repo already exposes part of the needed substrate:

- `orchestrator/workflow_lisp/contracts.py` defines
  `FlattenedContractField`,
  `derive_workflow_signature_contracts(...)`,
  and `UnionWorkflowBoundaryProjection`;
- `orchestrator/workflow_lisp/lowering.py` already records generated input,
  output, and path provenance in `LoweringOriginMap`;
- `orchestrator/workflow_lisp/build.py` already persists a
  `FrontendSourceTrace`-backed `source_map.json` artifact, but not a dedicated
  boundary-projection artifact;
- `tests/test_workflow_lisp_structured_results.py` already exercises recursive
  flattening and origin metadata for flattened fields;
- `tests/test_workflow_lisp_workflows.py` and
  `tests/test_workflow_lisp_lowering.py` already exercise union workflow
  returns and projection-aware lowering.

The gap is therefore not “invent flattening from scratch.” The gap is to make
the boundary contract explicit, bounded, source-mapped, and inspectable as a
first-class architecture surface.

## Proposed Package Boundary

Keep ownership inside the existing frontend package:

```text
orchestrator/workflow_lisp/
  build.py
  compiler.py
  contracts.py
  diagnostics.py
  lowering.py
  workflows.py
```

Responsibilities:

- `contracts.py`
  - remain the single authority for workflow-boundary projection metadata;
  - derive record flattening and union-return projection from structured type
    refs;
  - detect and reject generated-name collisions deterministically.
- `workflows.py`
  - keep `WorkflowSignature` structured and canonical;
  - reject unsupported authored boundary types before projection;
  - expose enough signature metadata for build-artifact emission.
- `lowering.py`
  - consume projection metadata when emitting flat shared `inputs` / `outputs`
    and call bindings;
  - keep generated internal write-root inputs separate from authored boundary
    fields;
  - populate `LoweringOriginMap.generated_input_spans` and
    `generated_output_spans` for every flattened field.
- `build.py`
  - emit `workflow_boundary_projection.json`;
  - register the new artifact in the build manifest;
  - keep provenance and boundary-projection artifacts separate.
- `compiler.py`
  - thread projection metadata through compile results so it is available to
    build and explain surfaces without re-derivation.
- `diagnostics.py`
  - own any new frontend-local diagnostics needed for projection collisions or
    missing provenance coverage.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow/` shared validation and runtime modules

## Boundary Model

### Structured Authority

Inside the frontend, workflow boundaries stay structured:

- authored parameters remain named parameters with structured type refs;
- authored return types remain record or union type refs;
- `call` typechecking binds against structured signatures, not flattened field
  dictionaries;
- future Semantic Workflow IR must preserve the same structured signature and
  treat flat field names only as a lowering compatibility detail.

Implementation rule:

- never use flattened names as the authority for typechecking, effect
  propagation, match proof, or authored diagnostics;
- always derive flattened names from structured metadata, never the reverse.

### Compatibility Projection Seam

Flattening is allowed only where the current shared workflow surface still
requires flat names:

1. lowered workflow `inputs`;
2. lowered workflow `outputs`;
3. lowered `call.with` bindings and downstream `ref` targets;
4. build/explain artifacts that must show how authored structure became flat
   compatibility names.

Flattening is forbidden as semantic authority in:

- `WorkflowSignature`;
- typed workflow bodies and typed expressions;
- provider-result / command-result structured output contracts;
- report content, pointer files, or sidecar state;
- future Semantic Workflow IR.

### Boundary-Lowerable Types

This slice preserves the earlier boundary rules:

- scalar and relpath leaves remain boundary-lowerable;
- records may cross the boundary only by recursive projection to lowerable
  leaves;
- union returns may cross the boundary only through the existing
  `UnionWorkflowBoundaryProjection` contract;
- `Provider`, `Prompt`, and `Json` remain non-boundary authored types except
  for the existing compiler-known extern paths that never become ordinary
  workflow `inputs`.

## Projection Metadata

### Record Flattening

`FlattenedContractField` remains the leaf-level projection unit:

- `generated_name`
- `source_path`
- `contract_definition`

Rules:

- nested records flatten recursively using the existing `__` separator;
- `source_path` remains structured and authored, for example
  `("input", "summary", "report")`;
- collisions after flattening must be rejected with a dedicated frontend
  diagnostic rather than silently overwriting fields.

Recommended new diagnostic:

- `workflow_boundary_projection_collision`

### Union Workflow Returns

`UnionWorkflowBoundaryProjection` remains the union-return projection unit:

- one discriminant field;
- zero or more shared fields;
- zero or more variant-only fields grouped by variant.

Rules:

- generated discriminant naming stays deterministic as `return__variant`;
- shared fields appear once;
- variant-only fields may be surfaced on the flat boundary, but downstream
  typed access still requires `match` proof over the union result;
- the projection metadata, not the flat names alone, is the authority that
  tells explain/build tooling which fields are shared vs variant-specific.

### Internal Generated Inputs

Generated managed write-root inputs are not authored boundary fields.

Rules:

- they keep their current lowering role for shared validation/runtime
  compatibility;
- they must be recorded separately from authored flattened parameters in both
  `LoweringOriginMap` and the build artifact;
- they must be labeled `generated_internal` or equivalent in serialized
  projection data so tools do not misreport them as authored workflow params.

## Provenance And Source-Map Obligations

Every generated flattened field that can appear in shared-validation or build
artifacts must have:

- one `LoweringOriginMap` entry;
- one persisted source-trace entry;
- one projection-artifact entry that includes its authored `source_path`.

Minimum requirements:

- `generated_input_spans` covers flattened authored inputs and internal
  generated write-root inputs separately;
- `generated_output_spans` covers flattened record-return and union-projection
  outputs;
- remapped diagnostics mention the authored workflow form path and span, not
  only the generated flat field name;
- projection artifact entries include enough provenance to explain both:
  - where the field came from in authored structure;
  - which shared field name was generated.

This slice does not redefine the shared future `SourceMap`. It strengthens the
frontend-owned bridge already used by `LoweringOriginMap` and
`FrontendSourceTrace`.

## Compile And Build Artifact Surface

Add one build artifact:

- `.orchestrate/build/<fingerprint>/workflow_boundary_projection.json`

Purpose:

- expose the structured-to-flat boundary mapping as deterministic data;
- let `orchestrate explain` and future lint/LSP tooling inspect projection
  rules without scraping generated workflow YAML-like surfaces;
- keep `source_map.json` focused on provenance instead of overloading it with
  full contract mapping.

Recommended shape:

```json
{
  "schema_version": "workflow_lisp_boundary_projection.v1",
  "entry_workflow": "neurips/entry::orchestrate",
  "workflows": [
    {
      "workflow_name": "provider_attempt",
      "params": [
        {
          "name": "input",
          "type_kind": "record"
        }
      ],
      "return_kind": "union",
      "flattened_inputs": [
        {
          "generated_name": "input__summary__report",
          "source_path": ["input", "summary", "report"],
          "contract_definition": {"kind": "relpath", "type": "relpath"}
        }
      ],
      "flattened_outputs": [
        {
          "generated_name": "return__variant",
          "source_path": ["return", "variant"],
          "contract_definition": {"kind": "scalar", "type": "enum"}
        }
      ],
      "generated_internal_inputs": [
        "__write_root__provider_attempt__attempt__result_bundle"
      ]
    }
  ]
}
```

Implementation rules:

- build manifest must list the new artifact path and status;
- the artifact must be derived from compiler-owned projection metadata, not by
  reparsing emitted surface workflows;
- when shared Semantic Workflow IR artifacts exist later, they may reference
  this same projection model, but this slice must not fabricate a fake
  Semantic IR file now.

## Diagnostics

Reuse existing codes where the meaning already matches:

- `workflow_boundary_type_invalid`
- `workflow_signature_mismatch`
- `json_surface_unsupported`
- `source_map_missing`

Add frontend-local codes only where the current taxonomy has no precise fit:

- `workflow_boundary_projection_collision`
- `workflow_boundary_projection_missing_origin`

Diagnostic requirements:

- collisions report the authored signature field paths that generated the same
  flat name;
- missing-origin failures report the generated field name and the workflow in
  which provenance coverage was incomplete;
- shared-validation failures on flat boundary names continue to remap through
  `LoweringOriginMap`.

## Test Strategy

Extend focused tests only:

- `tests/test_workflow_lisp_structured_results.py`
  - recursive flattening of nested record params/returns;
  - union projection metadata shape;
  - collision rejection;
  - separation between authored flattened fields and internal generated
    write-root inputs.
- `tests/test_workflow_lisp_workflows.py`
  - supported and unsupported boundary types remain checked on structured
    signatures, not on flat fields;
  - union call typing still requires proof.
- `tests/test_workflow_lisp_lowering.py`
  - lowered workflow `inputs` / `outputs` and `call.with` bindings reuse the
    projection metadata deterministically;
  - provenance remapping covers projected fields.
- `tests/test_workflow_lisp_build_artifacts.py`
  - `workflow_boundary_projection.json` is emitted deterministically;
  - manifest lists the new artifact;
  - projection artifact stays stable for identical structured signatures.

Prefer narrow pytest selectors first. If new tests or renamed tests are added,
run `pytest --collect-only` on the touched modules.

## Implementation Sequence

1. Formalize boundary projection ownership in `contracts.py` and thread the
   metadata through compile results.
2. Tighten lowering so authored flattened fields and internal generated inputs
   are tracked separately but consistently.
3. Extend provenance checks and diagnostics for projection coverage.
4. Emit `workflow_boundary_projection.json` from `build.py` and register it in
   the build manifest.
5. Extend explain/build tests and focused workflow/contract/lowering tests.

## Bottom Line

The workflow boundary remains structured in authored source, typed frontend
artifacts, and future Semantic Workflow IR. Flattening survives only as a
compiler-owned compatibility projection for the current shared runtime surface.
That projection must be deterministic, source-mapped, collision-checked, and
persisted as an explicit build artifact rather than hidden inside generated
field names.
