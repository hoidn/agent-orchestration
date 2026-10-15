# Workflow Lisp Semantic Workflow IR

Status: retained typed analysis and historical-reader contract
Scope: Semantic IR catalogs, validation and lineage; historical flat executable projections

## Purpose

This document records retained Semantic IR data/validation contracts. Current
checked-program artifacts and the evaluated memo own executable behavior; this
projection cannot authorize a flat build or old-profile replay.

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

<a id="authority-boundary"></a>
<a id="relationship-to-adjacent-layers"></a>

The flat executable-IR authority and linkage pipeline are historical; retained Semantic IR is an analysis/read projection, never current executable authority. See the [preserved record](../reports/documentation-history/workflow_lisp_semantic_workflow_ir-history.md#authority-boundary).

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
  or adapter-backed effects that survive as shared semantic metadata. Historical flat projections include generated `pure_projection` effects that carry
  payload digest, pure-expression schema version, result-type descriptor, and
  private output-bundle lineage, generated `materialize_view` effects that
  carry renderer id/version/schema, value-type descriptor, authority class, and
  target/allocation lineage, plus generated `resource_transition` effects that
  carry transition name, backend kind, resource kind, and private
  `resource_state` / `transition_audit` lineage for runtime-native declared
  transitions. Adapter-backed compatibility routes may still contribute
  `resource_transition` / `ledger_update` effects through
  `SemanticCommandBoundary`.
- `SemanticProofEntry` records semantic proof surfaces such as variant or other
  checked proof obligations.
- `SemanticStateLayoutEntry` records typed state-layout and presentation-key
  linkage instead of leaving runtime-facing layout meaning implicit. That
  includes `pure_projection_bundle`, `materialized_value_view`, entrypoint
  managed write-root, and managed write-root-input entries for generated
  projection/view bundles.
- `SemanticSourceMapBridgeEntry` records traceability bridges from semantic
  subjects back to authored or generated origins.
- `SemanticCallEdge` records workflow-call lineage.
- `SemanticPromptSurface` records provider prompt-delivery surfaces relevant to
  semantic inspection. When Workflow Lisp `provider-result` declares typed
  prompt dependencies, this surface carries the validated
  `CompilerPromptDependencyContract`; the contract contains required/optional
  binding refs, position, instruction digest, and its source-origin key. A
  target-2.20 fragment-backed call additionally carries the paired
  `CompilerPromptFragmentContract` and
  `compiled_prompt_fragment_identity`. Its document fills use the
  `workflow_lisp_prompt_fragment` dependency origin, while its exact template,
  declaration-ordered rendered slots, selected renderers, and closed value
  sources remain in the fragment contract. Semantic validation rejects an
  absent, malformed, or mismatched contract/identity pair and rejects
  disagreement with the corresponding executable provider configuration. The
  adjacent source map owns authored declaration/application/fill lineage. The
  semantic surface does not carry dependency bodies, resolved runtime values,
  final rendered prompt bytes, or attempt evidence.
  Target-2.21 prompt output positions use
  `compiled_prompt_fragment_identity.v2` and
  `compiler_prompt_fragment_contract.v2`; the carrier's declaration-ordered
  `output_positions[*].expected_output` objects are pair-validated against
  the executable provider configuration's exact `expected_outputs` rows.
  Q1-only calls retain exact v1 carriage. Missing, extra, reordered,
  malformed, or unequal v2 carriage fails semantic validation before provider
  preparation.
- `SemanticCommandBoundary` records typed command-boundary metadata rather than
  leaving command meaning embedded in shell text.
- `SemanticExecutableBridge` records the semantic-to-executable linkage for
  node ids, presentation keys, and resume-checkpoint identities.

This is retained data-model inventory. Generated flat effects and executable
bridges describe historical artifacts; their presence in a schema or reader is
not admission to evaluated execution.

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

<a id="executable-and-runtime-plan-linkage"></a>

Historical flat executable/runtime-plan linkage; current execution is owned by the checked closed program and memo. See the [preserved record](../reports/documentation-history/workflow_lisp_semantic_workflow_ir-history.md#executable-and-runtime-plan-linkage).

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

<a id="build-artifacts-and-evidence"></a>

Historical flat build-emission evidence. These records prove their original surfaces, not present flat build availability. See the [preserved record](../reports/documentation-history/workflow_lisp_semantic_workflow_ir-history.md#build-artifacts-and-evidence).

## Out Of Scope

This document does not define new Semantic IR schema fields, new validators,
new runtime behavior, new executable node kinds, runtime closures, dynamic
dispatch, or a frontend-owned direct lowerer that bypasses the shared bundle
path.

Future schema, validator, or runtime-surface changes require a separate
reviewed contract and must not be implied by this promotion pass.
