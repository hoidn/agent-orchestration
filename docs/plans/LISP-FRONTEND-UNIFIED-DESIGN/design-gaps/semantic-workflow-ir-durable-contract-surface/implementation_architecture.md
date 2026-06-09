# Semantic Workflow IR Durable Contract Surface Implementation Architecture

Status: draft
Design gap id: `semantic-workflow-ir-durable-contract-surface`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded work needed to close the remaining durable
design-surface gap around Workflow Lisp Semantic IR:

- promote the existing `docs/design/workflow_lisp_semantic_workflow_ir.md`
  document from draft internal notes to a current-checkout component contract;
- document the already-implemented `SemanticWorkflowIR` surface, including its
  typed catalogs, executable/runtime-plan bridges, source-map bridges, and
  validator ownership;
- add the minimum repo-level discoverability needed so Semantic IR is visible
  from `docs/index.md` alongside the other current Workflow Lisp component
  contracts;
- preserve coherence with the landed executable-IR durable surface, core
  statement taxonomy slice, reusable write-root policy, source-map lineage,
  standard-library lowering, and command-adapter contract.

This slice does not implement:

- new Semantic IR schema fields, validators, serialization formats, or
  runtime behavior;
- new executable node kinds, runtime closures, dynamic dispatch, or
  runtime-native effects;
- a direct frontend-to-semantic-IR compiler path that bypasses the current
  shared bundle/lowering flow;
- new helper scripts, inline Python or shell glue, report parsing, pointer
  authority changes, or command-boundary reinterpretation;
- a replacement umbrella specification for the whole Workflow Lisp frontend.

The work stays bounded to one documentation and contract-alignment gap. It is
an implementation architecture for the missing durable Semantic IR design
surface, not a new compiler/runtime implementation tranche.

## Problem Statement

The selected gap is no longer "implement Semantic IR." The current checkout
already has a real shared Semantic IR layer:

- `orchestrator/workflow/semantic_ir.py` defines
  `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`, `SemanticWorkflowIR`, the current
  typed entry dataclasses, `derive_workflow_semantic_ir(...)`,
  `validate_workflow_semantic_ir(...)`, and
  `workflow_semantic_ir_to_json(...)`;
- `orchestrator/workflow/loaded_bundle.py` exposes Semantic IR as the typed
  shared bundle field `LoadedWorkflowBundle.semantic_ir` and through the
  `workflow_semantic_ir(...)` helper;
- `orchestrator/workflow/lowering.py` derives Semantic IR during shared bundle
  assembly after executable validation and runtime-plan derivation;
- `orchestrator/workflow_lisp/build.py` emits `semantic_ir.json` as a durable
  frontend build artifact;
- `tests/test_workflow_semantic_ir.py` already locks current behavior for
  contracts, refs, effects, proofs, state layout, source-map bridges,
  executable/runtime-plan linkage, promoted adapter effects, and generated
  semantic effects;
- `tests/test_workflow_lisp_build_artifacts.py` already proves that
  `semantic_ir.json` is emitted and recorded in the build manifest.

What is still missing is the durable repo-level contract surface that matches
that implementation.

Today the Semantic IR contract is fragmented:

- `docs/design/workflow_lisp_semantic_workflow_ir.md` still says
  `Status: draft internal design` and remains much thinner than the current
  implementation;
- `docs/index.md` does not list the Semantic IR component doc, so readers have
  to infer its status from code, tests, or the umbrella spec;
- the current checkout already exceeds the historical autonomous-drain
  "shared-contract" tranche, but the durable current-checkout design surface
  has not yet been promoted accordingly.

The missing work is therefore docs-first and docs-mostly:

```text
current shared SemanticWorkflowIR implementation
  -> durable current-checkout component contract doc
  -> indexed/discoverable repo design surface
  -> coherent ownership boundary with executable IR and runtime plan
```

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `36. Semantic Workflow IR Contract`
  - `37. Executable IR Contract`
  - `38. Reference Catalog Contract`
  - `39. Type Catalog Contract`
  - `40. Effect Graph Contract`
  - `41. Proof Graph Contract`
  - `42. State Layout Contract`
  - `43. Source Map Contract`
  - `46. Acceptance Gate for Component Architecture`
  - `73. Recommended Sequence`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `59. Validation Sequence`
  - `63-66. Variant, snapshot, pointer, and report-authority validation`
  - `74. Source Map Requirements`
  - `76. Build Artifacts`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- `LoadedWorkflowBundle.semantic_ir` remains the durable typed semantic bundle
  surface for the current checkout, but it does not replace executable
  authority or runtime execution ownership;
- Semantic IR must continue to be derived from validated shared bundle
  surfaces, not from reports, pointer files, debug YAML, or ad hoc text
  reconstruction;
- contracts, refs, effects, proofs, state-layout entries, source-map bridges,
  call edges, prompt surfaces, command boundaries, and executable bridges must
  stay explicit and typed;
- command-boundary meaning remains governed by the command-adapter contract,
  not by reinterpreting shell text or adapter payloads in docs;
- compile-time-only values such as unresolved `ProcRef`, `let-proc`, syntax
  objects, and runtime-closure markers must not be redescribed as valid
  Semantic IR content;
- the slice must not reopen already-landed code/test behavior merely to make
  the docs read more like the parent design.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/core-statement-taxonomy-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-durable-contract-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-system-finalization-policy-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/runtime-closure-disabled-profile-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- historical coherence reference:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`

### Decisions Reused

- Reuse the shared ownership split already established across the current
  slices:
  `orchestrator/workflow_lisp/` owns authored frontend lowering/provenance and
  `orchestrator/workflow/` owns shared Core AST, executable IR, runtime plan,
  and Semantic IR contracts.
- Reuse the executable-IR durable slice's authority split:
  executable IR remains the executable authority, while Semantic IR is the
  typed semantic contract surface derived from validated shared bundle data.
- Reuse the core-statement-taxonomy slice's rule that Semantic IR inventories
  both base statement families and attached semantic facets promoted from
  current shared surfaces.
- Reuse the reusable-boundary write-root slice's rule that managed write roots
  stay caller-owned shared behavior and appear in Semantic IR only as typed
  layout entries, not as ad hoc statement-local policy.
- Reuse the standard-library lowering and effectful-composition slices' rule
  that promoted effects and command-boundary classifications remain explicit
  shared metadata rather than hidden frontend-only behavior.
- Reuse the runtime-closure-disabled and let-proc slices' invariant that
  compile-time-only callable abstractions must not survive into semantic or
  runtime artifacts.
- Reuse the command-adapter contract as the authority for external-tool versus
  certified-adapter meaning, fixture obligations, and runtime-native promotion
  criteria.

### New Decisions In This Slice

- Treat this gap as a promotion and discoverability pass over an already-landed
  implementation, not as a new schema/validator delivery.
- Keep the existing document path
  `docs/design/workflow_lisp_semantic_workflow_ir.md` and promote that file to
  the durable current-checkout contract instead of creating a second Semantic
  IR doc.
- Define the promoted contract in current-checkout terms around the real typed
  surface:
  `SemanticWorkflowIR`,
  `SemanticWorkflow`,
  `SemanticStatement`,
  `SemanticTypeEntry`,
  `SemanticContractEntry`,
  `SemanticRefEntry`,
  `SemanticEffectEntry`,
  `SemanticProofEntry`,
  `SemanticStateLayoutEntry`,
  `SemanticSourceMapBridgeEntry`,
  `SemanticCallEdge`,
  `SemanticPromptSurface`,
  `SemanticCommandBoundary`,
  and `SemanticExecutableBridge`.
- Add one `docs/index.md` entry for Semantic IR discoverability.
- Keep parent-spec edits out of scope unless a narrow wording correction is
  needed, because the umbrella frontend specification already links
  `workflow_lisp_semantic_workflow_ir.md` in its internal component-contract
  list.

### Conflicts Or Revisions

The historical autonomous-drain `semantic-workflow-ir-shared-contract` slice
assumed the current repo still lacked the shared module, bundle field, emitted
artifact, and validator surface. That is no longer true in this checkout:

- `orchestrator/workflow/semantic_ir.py` exists and is test-backed;
- `LoadedWorkflowBundle.semantic_ir` already exists;
- `semantic_ir.json` is already emitted in frontend builds;
- Semantic IR validation already rejects broken catalog, bridge, checkpoint,
  and source-map lineage states with `semantic_ir_invalid`.

This slice revises the next step narrowly:

- keep the earlier slice's ownership model and shared semantic categories;
- do not repeat its original code-delivery scope;
- finish the remaining gap by promoting the existing design doc and indexing it
  as a durable current-checkout component contract.

No prior slice is revised on shared concepts such as spans, diagnostics, Core
Workflow AST, TypeCatalog, SourceMap, pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- promotion of `docs/design/workflow_lisp_semantic_workflow_ir.md` into the
  durable current-checkout Semantic IR contract;
- the bounded written explanation of Semantic IR ownership over contracts,
  refs, effects, proofs, state layout, source-map bridges, call edges, prompt
  surfaces, command boundaries, and executable/runtime-plan linkage;
- the repo-index discoverability update needed to surface the promoted
  contract;
- focused docs/test audit expectations needed to keep the promoted contract
  truthful to the current checkout.

This slice intentionally does not own:

- changes to `orchestrator/workflow/semantic_ir.py`,
  `loaded_bundle.py`,
  `lowering.py`,
  `runtime_plan.py`,
  `executable_ir.py`,
  or runtime execution behavior by default;
- new semantic entry categories, new validation passes, or new command-boundary
  semantics;
- redesign of the TypeCatalog, EffectGraph, ProofGraph, StateLayout, or
  SourceMap component documents beyond referencing their current shared roles;
- new adapters, helper scripts, inline glue, backlog updates, queue changes,
  or unrelated design-doc rewrites.

## Current Checkout Facts

- `docs/design/workflow_lisp_semantic_workflow_ir.md` already exists, but it
  is still marked `Status: draft internal design`.
- `docs/index.md` currently has no dedicated Workflow Lisp entry for
  `workflow_lisp_semantic_workflow_ir.md`.
- `docs/design/workflow_lisp_frontend_specification.md` already links the
  Semantic IR document in its internal component-contract list, so this gap is
  missing durable status/discoverability, not missing a parent-spec pointer.
- `orchestrator/workflow/semantic_ir.py` already exports:
  - `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION = "workflow_semantic_ir.v1"`;
  - the current typed Semantic IR dataclasses;
  - `derive_workflow_semantic_ir(...)`;
  - `validate_workflow_semantic_ir(...)`;
  - `workflow_semantic_ir_to_json(...)`.
- `orchestrator/workflow/loaded_bundle.py` already exposes:
  - `LoadedWorkflowBundle.semantic_ir`;
  - `workflow_semantic_ir(...)`.
- `orchestrator/workflow/lowering.py` already derives Semantic IR during
  `build_loaded_workflow_bundle(...)` after executable validation and
  runtime-plan derivation.
- `orchestrator/workflow_lisp/build.py` already emits `semantic_ir.json`, and
  `tests/test_workflow_lisp_build_artifacts.py` already asserts emitted
  artifact status and filename coverage.
- `tests/test_workflow_semantic_ir.py` already verifies:
  - contract, ref, effect, proof, state-layout, and source-map bridge
    population;
  - executable bridge node/presentation-key/resume-checkpoint coverage;
  - command-boundary classification and prompt-surface/call-edge cataloging;
  - promoted certified-adapter effects for `resource_transition` and
    `ledger_update`;
  - promoted generated effects for `snapshot_capture` and
    `pointer_materialization`;
  - rejection of broken catalog entries, broken checkpoint bridges, and broken
    frontend source-map lineage via `semantic_ir_invalid`.
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently has no
  events, so no later ledger evidence overrides the code/test baseline.

## Proposed Documentation Boundary

Keep the implementation shape docs-first and docs-mostly:

```text
docs/design/
  workflow_lisp_semantic_workflow_ir.md   # promoted durable current-checkout contract

docs/
  index.md                                # discoverability entry

orchestrator/workflow/
  semantic_ir.py                          # evidence owner, unchanged by default
  loaded_bundle.py                        # evidence owner, unchanged by default
  lowering.py                             # evidence owner, unchanged by default
  runtime_plan.py                         # adjacent derived-layer evidence
  executable_ir.py                        # adjacent executable-layer evidence

orchestrator/workflow_lisp/
  build.py                                # emitted-artifact evidence

tests/
  test_workflow_semantic_ir.py            # contract evidence
  test_workflow_lisp_build_artifacts.py   # emitted-artifact evidence
```

Responsibilities:

- `docs/design/workflow_lisp_semantic_workflow_ir.md`
  - restate the current checkout's Semantic IR contract in repo terms;
  - explain the semantic authority lane without claiming runtime execution
    ownership;
  - record the current bundle/build/test evidence surface.
- `docs/index.md`
  - make the Semantic IR contract discoverable alongside the other Workflow
    Lisp component docs.
- shared code and tests
  - remain the evidence source for contract truth;
  - change only if a focused audit proves the promoted doc would otherwise be
    false.

## Expected Durable Contract Shape

The promoted Semantic IR document should describe the current checkout using
sections that mirror the durable Executable IR contract where relevant, while
staying specific to Semantic IR ownership:

- purpose and authority boundary;
- relationship to Core AST, executable IR, runtime plan, and source maps;
- current semantic surface and typed catalog inventory;
- validation ownership and `semantic_ir_invalid` failure scope;
- executable/runtime-plan linkage through `SemanticExecutableBridge` and
  state-layout entries;
- command-boundary constraints and dependence on
  `docs/design/workflow_command_adapter_contract.md`;
- build artifacts and current evidence surfaces;
- out-of-scope boundaries that forbid inventing new runtime semantics.

The promoted doc should name the current code-level anchors directly:

- `SemanticWorkflowIR`
- `WORKFLOW_SEMANTIC_IR_SCHEMA_VERSION`
- `derive_workflow_semantic_ir(...)`
- `validate_workflow_semantic_ir(...)`
- `workflow_semantic_ir_to_json(...)`
- `LoadedWorkflowBundle.semantic_ir`
- `workflow_semantic_ir(...)`

## Verification Impact

Normal-path implementation should remain docs-only.

Verification should focus on proving:

- the drafted implementation architecture exists at the prescribed path;
- the required `Relationship To Existing Implementation Architectures` section
  is present;
- the work-item context includes
  `docs/design/workflow_command_adapter_contract.md` in authoritative inputs;
- the draft bundle matches the selected gap and output paths.

If a docs audit uncovers a real contract mismatch, only the narrow owner module
or evidence test should change, starting with the smallest relevant Semantic IR
selectors rather than broader runtime/frontend suites.
