# Workflow Lisp Semantic Workflow IR

Status: current-checkout component contract
Scope: shared semantic-layer contract implemented in this repository for Workflow Lisp and imported workflow bundles

## Purpose

This document records the durable Semantic IR contract that the current
checkout already implements.

Semantic IR is the typed semantic contract surface for validated workflows. It
captures semantic structure in durable typed form for provenance, diagnostics,
build artifacts, and cross-layer inspection without turning reports or debug
views into authority.

In current code, that surface is anchored by:

- `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`
- `SemanticWorkflowIR`
- `SemanticWorkflow`
- `SemanticStatement`
- `SemanticTypeEntry`
- `SemanticContractEntry`
- `SemanticRefEntry`
- `SemanticEffectEntry`
- `SemanticProofEntry`
- `SemanticStateLayoutEntry`
- `SemanticSourceMapBridgeEntry`
- `SemanticCallEdge`
- `SemanticPromptSurface`
- `SemanticCommandBoundary`
- `SemanticExecutableBridge`
- `derive_workflow_semantic_ir(...)`
- `validate_workflow_semantic_ir(...)`
- `workflow_semantic_ir_to_json(...)`
- `LoadedWorkflowBundle.semantic_ir`
- `workflow_semantic_ir(...)`

## Authority Boundary

Semantic IR is the durable typed semantic contract surface for the current
checkout, but validated executable IR remains executable authority.

In current code, executable authority means `LoadedWorkflowBundle.ir`
containing validated executable structure. Semantic IR does not replace that
authority, and it does not own runtime execution semantics.

Semantic IR must be derived from the shared bundle path. It must not be
reconstructed from reports, debug YAML, pointer files, shell text, adapter
payload prose, dashboards, or summary documents.

Structured semantic data is authority for the semantic layer. Reports and
projections are views.

## Relationship To Adjacent Layers

The current shared pipeline is:

```text
frontend source / YAML surface
  -> frontend-specific loading or Workflow Lisp WCC/schema-2 lowering
  -> Core Workflow AST
  -> shared validation and lowering
  -> validated executable IR
  -> derived runtime plan and state projection
  -> derived Semantic IR
  -> loaded bundle / build artifacts / existing runtime
```

Workflow Lisp lowers through WCC/schema 2 into the same shared bundle path as
imported YAML workflows. The frontend does not bypass shared lowering to build
Semantic IR directly, and WCC metadata is consumed only as provenance,
scope/proof/effect, and source-map input for the ordinary projections.

The boundary with adjacent layers is:

- `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` remain executable
  authority.
- `LoadedWorkflowBundle.semantic_ir` is the typed semantic projection exposed
  on the shared bundle.
- `runtime_plan`, build summaries, dashboards, and debug YAML are derived
  views and do not redefine semantic authority.
- source maps are traceability artifacts, not competing semantic or runtime
  authority.

## Current Semantic Surface

The current contract is implemented in
`orchestrator/workflow/semantic_ir.py`.

- `SemanticWorkflowIR` is the top-level typed semantic payload versioned by
  `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`.
- `SemanticWorkflow` records per-workflow semantic structure, including input,
  output, and artifact contract bindings, authored statement order, and the
  `SemanticExecutableBridge`.
- `SemanticStatement` records statement identity, authored step identity,
  executable-node linkage, referenced semantic entries, and attached effect
  identifiers.
- `SemanticTypeEntry`, `SemanticContractEntry`, and `SemanticRefEntry` record
  the typed catalog for types, contracts, and resolved references.
- `SemanticEffectEntry` records explicit effects, including promoted generated
  or adapter-backed effects that survive as shared semantic metadata.
- `SemanticProofEntry` records semantic proof surfaces such as variant or other
  checked proof obligations.
- `SemanticStateLayoutEntry` records typed state-layout and presentation-key
  linkage instead of leaving runtime-facing layout meaning implicit.
- `SemanticSourceMapBridgeEntry` records traceability bridges from semantic
  subjects back to authored or generated origins.
- `SemanticCallEdge` records workflow-call lineage.
- `SemanticPromptSurface` records provider prompt-delivery surfaces relevant to
  semantic inspection.
- `SemanticCommandBoundary` records typed command-boundary metadata rather than
  leaving command meaning embedded in shell text.
- `SemanticExecutableBridge` records the semantic-to-executable linkage for
  node ids, presentation keys, and resume-checkpoint identities.

This surface is current-checkout inventory, not an aspirational schema wish
list.

## Validation Ownership

Semantic IR validation is owned by the shared workflow layer, not by ad hoc
report parsing or frontend-only conventions.

In current code:

- `derive_workflow_semantic_ir(...)` constructs the typed semantic projection
  from validated shared bundle inputs.
- `validate_workflow_semantic_ir(...)` enforces schema-version, catalog,
  bridge, and lineage invariants before the layer is treated as valid.
- `workflow_semantic_ir(...)` exposes the validated semantic payload from a
  loaded bundle when present.

This contract narrows the authority lane: workflows may come from different
authoring surfaces, but semantic authority is recognized only through the
shared derived-and-validated `SemanticWorkflowIR` surface.

## Executable And Runtime-Plan Linkage

Semantic IR is derived from shared executable and runtime-facing bundle
surfaces; it is not a replacement for them.

Current linkage rules:

- `SemanticExecutableBridge` ties each semantic workflow to executable node
  ids, presentation keys, and resume-checkpoint identities.
- semantic statements can point at executable node ids without redefining the
  executable contract itself.
- `runtime_plan` remains a derived runtime-facing summary used for ordering,
  presentation, and checkpoint linkage.
- build summaries, dashboards, and debug YAML may summarize these surfaces,
  but they do not become semantic or executable authority.

If executable structure or runtime-plan linkage changes in the future, the
semantic projection must be revised through a separate reviewed contract rather
than by implication from this document.

## Command Boundary Constraints

Command and provider semantics remain governed by
[Workflow Command Adapter Contract](workflow_command_adapter_contract.md).

Semantic IR may record command boundaries and promoted adapter-backed effect
metadata through `SemanticCommandBoundary` and `SemanticEffectEntry`, but this
document does not create a second command-semantics authority source.

Command/provider meaning must not be inferred by reinterpreting shell text,
inline glue, or adapter payload prose. The command-adapter contract and shared
runtime/code paths remain authoritative for those semantics.

## Compile-Time Erasure And Source-Map Bridges

Semantic and runtime artifacts must not retain compile-time-only authoring
values.

Compile-time-only values such as unresolved `ProcRef`, `let-proc` metadata,
syntax objects, macro-expansion leftovers, and runtime-closure markers must
not survive into semantic/runtime artifacts.

Source-map bridges must preserve traceability from semantic entries back to
authored or generated subjects. `SemanticSourceMapBridgeEntry` exists to keep
that lineage explicit for diagnostics, audits, and generated-structure review.

This preserves the Workflow Lisp rule that authoring-time abstractions compile
away before durable semantic or executable artifacts are produced.

## Build Artifacts And Evidence

The current checkout emits durable Semantic IR evidence through the shared
build path.

- `workflow_semantic_ir_to_json(...)` serializes the semantic artifact.
- `orchestrator/workflow_lisp/build.py` emits `semantic_ir.json` and records
  it in build outputs alongside adjacent artifacts.
- `tests/test_workflow_semantic_ir.py` provides current evidence for catalog
  population, source-map and executable bridges, command-boundary coverage,
  promoted effects, and `semantic_ir_invalid` rejection behavior.
- `tests/test_workflow_lisp_build_artifacts.py` provides current evidence for
  `semantic_ir.json` emission, schema-version locking, and build-manifest
  lineage.

Those artifacts are durable evidence for the implemented surface. They do not
change the rule that Semantic IR is derived from shared validated structures
rather than from reports or other projections.

## Out Of Scope

This document does not define new Semantic IR schema fields, new validators,
new runtime behavior, new executable node kinds, runtime closures, dynamic
dispatch, or a frontend-owned direct lowerer that bypasses the shared bundle
path.

Future schema, validator, or runtime-surface changes require a separate
reviewed contract and must not be implied by this promotion pass.
