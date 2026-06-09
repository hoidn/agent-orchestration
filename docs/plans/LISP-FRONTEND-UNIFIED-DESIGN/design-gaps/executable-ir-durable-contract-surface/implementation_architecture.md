# Executable IR Durable Contract Surface Implementation Architecture

Status: draft
Design gap id: `executable-ir-durable-contract-surface`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded work needed to close the remaining durable
design-surface gap around Workflow Lisp Executable IR:

- add one repo-level Executable IR component-contract document under
  `docs/design/` that describes the current implemented `ExecutableWorkflow`
  surface;
- connect that document to the repo’s durable documentation map so it is
  discoverable from `docs/index.md` and the umbrella frontend contract;
- keep the documented authority boundary aligned with the current shared
  implementation:
  `LoadedWorkflowBundle.ir` is authoritative, while `runtime_plan`,
  `semantic_ir`, `source_map`, `workflow_boundary_projection`, and debug YAML
  remain derived projections;
- preserve coherence with the already-drafted executable-IR component-contract
  slice, core-statement taxonomy slice, source-map rules, write-root policy,
  and command-adapter contract.

This slice does not implement:

- new executable node kinds, validators, serializers, runtime-plan behavior,
  semantic-IR behavior, or runtime execution logic;
- a direct frontend-to-executable-IR compiler path;
- runtime closures, dynamic dispatch, runtime callable transport, or new
  runtime-native effects;
- helper scripts, inline Python/shell glue, legacy adapters, or report-parsing
  semantics;
- a replacement umbrella spec for the whole frontend.

The work stays bounded to one documentation gap. It is an implementation
architecture for the missing durable Executable IR design surface, not a new
runtime/compiler implementation tranche.

## Problem Statement

The selected gap is no longer "implement Executable IR." The current checkout
already has a real shared executable layer:

- `orchestrator/workflow/executable_ir.py` defines
  `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION`, `ExecutableWorkflow`, executable
  node/config/address dataclasses, JSON serialization, and
  `validate_executable_workflow(...)`;
- `orchestrator/workflow/lowering.py` validates executable IR before deriving
  `WorkflowRuntimePlan` and `SemanticWorkflowIR`;
- `orchestrator/workflow/loaded_bundle.py` exposes executable IR as the
  authoritative `LoadedWorkflowBundle.ir`;
- `orchestrator/workflow/runtime_plan.py` and `semantic_ir.py` derive
  runtime-facing and semantic projections from validated executable IR;
- `orchestrator/workflow_lisp/compiler.py` revalidates executable bundles at
  the frontend `executable` pass after shared validation;
- `orchestrator/workflow_lisp/build.py` emits `executable_ir.json`,
  `runtime_plan.json`, `semantic_ir.json`, and `source_map.json`;
- tests already lock executable schema/version, validator behavior, emitted
  artifacts, and post-shared-validation remap behavior.

What is still missing is the durable repo-level contract document that Section
37 of the unified future design expects.

Today that contract is still fragmented across code, tests, and older planning
artifacts:

- the authoritative runtime-facing behavior exists in code and fixtures, but
  not as one stable design document under `docs/design/`;
- `docs/index.md` can route readers to Core AST, Semantic IR, and source-map
  material, but there is no dedicated Executable IR component-contract entry;
- `docs/design/workflow_lisp_frontend_specification.md` describes Executable IR
  conceptually in Part VIII/Section 48, yet Section 0’s internal component
  contract list still has no standalone Executable IR component document.

The missing work is therefore documentation and contract-surface alignment over
an implementation that already exists:

```text
current shared implementation
  -> durable repo-level Executable IR contract doc
  -> indexed/discoverable component-contract surface
  -> coherent parent-language references
```

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `33. Target Pipeline`
  - `37. Executable IR Contract`
  - `42. State Layout Contract`
  - `43. Source Map Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
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

- `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` remains the only executable
  authority;
- `runtime_plan`, `semantic_ir`, `source_map`, and debug YAML remain derived
  projections and must not be documented as competing semantic authorities;
- executable IR may contain only runtime-executable values, never unresolved
  `ProcRef`, `WorkflowRef`, `let-proc`, syntax objects, source spans, or other
  compile-time-only payloads;
- executable command and adapter surfaces remain governed by the command
  adapter contract, not by hidden inline command semantics;
- imported YAML bundles and compiled `.orc` bundles continue to cross reusable
  boundaries as validated `LoadedWorkflowBundle` instances rather than ad hoc
  executable payloads;
- the slice must not reopen already-landed code/test behavior merely to make
  the docs look cleaner.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/core-statement-taxonomy-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/runtime-closure-disabled-profile-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-system-finalization-policy-surface/implementation_architecture.md`

### Decisions Reused

- Reuse the executable-IR component-contract slice’s authority split:
  validated `ExecutableWorkflow` is the runtime-facing contract and derived
  layers must not redefine execution.
- Reuse the core-statement-taxonomy slice’s distinction between base shared
  statement families and attached semantic facets carried through executable
  configs, runtime-plan projections, and Semantic IR.
- Reuse the reusable-boundary write-root slice’s rule that generated write
  roots are deterministic, caller-owned projections, not executable-IR-local
  ad hoc strings.
- Reuse the runtime-closure-disabled slice’s invariant that compile-time-only
  callable values must not enter executable/runtime artifacts.
- Reuse the command-adapter contract as the authority for executable command
  boundary meaning, certification, and runtime-native promotion criteria.

### New Decisions In This Slice

- Treat this gap as docs-first and docs-mostly: the missing deliverable is one
  durable design surface, not a new implementation seam.
- Create one dedicated design document, recommended path:
  `docs/design/workflow_lisp_executable_ir.md`, that describes the current
  checkout’s executable contract in repo terms rather than as aspirational IR
  vocabulary.
- Update the documentation index so the new Executable IR contract is
  discoverable alongside the other Workflow Lisp component-contract documents.
- Add one narrow umbrella-spec cross-reference so readers of the baseline
  frontend specification can find the durable Executable IR component doc
  without treating Part VIII alone as the full component contract.

### Conflicts Or Revisions

The earlier `executable-ir-component-contract` slice assumed code and test
changes were still required to make Executable IR a reviewed contract. The
current checkout has already landed that implementation substrate:

- schema versioning, serializer, validator, bundle assembly, runtime-plan
  derivation, semantic-IR derivation, emitted artifacts, and frontend
  revalidation now exist in source and tests.

This slice revises the next step narrowly:

- keep the earlier slice’s authority model and ownership split;
- do not repeat its code-level implementation scope;
- finish the remaining gap by documenting the current surface durably and
  linking it into the repo’s design map.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- the durable repo-level Executable IR component-contract document;
- the documentation index and umbrella-spec references needed to make that
  document discoverable and coherent;
- the bounded written explanation of authority, validation ownership, derived
  projections, and error/fixture expectations for the current checkout.

This slice intentionally does not own:

- `orchestrator/workflow/executable_ir.py` implementation behavior;
- runtime-plan, semantic-IR, source-map, or executor code changes;
- new tests unless a focused docs-alignment audit exposes a real mismatch in
  current repo behavior;
- command-adapter certification rules, runtime-native promotion, or runtime
  execution semantics;
- backlog state, progress ledgers, queue items, or unrelated design docs.

## Current Checkout Facts

- No existing `docs/design/*` document in this checkout is dedicated to the
  shared Executable IR component contract.
- `orchestrator/workflow/executable_ir.py` already exports:
  - `WORKFLOW_EXECUTABLE_IR_SCHEMA_VERSION = "workflow_executable_ir.v1"`;
  - `workflow_executable_ir_to_json(...)`;
  - `validate_executable_workflow(...)`.
- `orchestrator/workflow/lowering.py` already validates executable IR while
  building `LoadedWorkflowBundle`, before `derive_workflow_runtime_plan(...)`
  and `derive_workflow_semantic_ir(...)`.
- `orchestrator/workflow_lisp/compiler.py` already revalidates executable IR
  for linked bundles during the frontend `executable` validation pass and keeps
  remap behavior distinct from the initial `shared_validation` checkpoint.
- `orchestrator/workflow_lisp/build.py` already emits executable/runtime
  artifacts and manifest status entries for `executable_ir` and `runtime_plan`.
- `tests/test_workflow_ir_lowering.py`,
  `tests/test_workflow_lisp_build_artifacts.py`, and
  `tests/test_workflow_lisp_diagnostics.py` already provide the key evidence
  surface for the durable contract.
- `docs/steering.md` is empty in this checkout, so it does not add scope.
- `state/LISP-FRONTEND-UNIFIED-DESIGN/progress_ledger.json` currently has no
  events, so there is no later recorded design-implementation evidence to
  override the code/test baseline.

## Proposed Documentation Boundary

Keep the implementation footprint explicitly documentation-focused:

```text
docs/design/
  workflow_lisp_executable_ir.md          # new durable component-contract doc

docs/
  index.md                                # new discovery entry

docs/design/
  workflow_lisp_frontend_specification.md # narrow cross-reference only
```

Recommended responsibility split:

- `docs/design/workflow_lisp_executable_ir.md`
  - defines the durable current-checkout Executable IR contract surface;
  - states what the authoritative executable artifact is;
  - states what projections are derived and non-authoritative;
  - records validation ownership, source-map/observability obligations, command
    boundary constraints, and fixture expectations.
- `docs/index.md`
  - exposes the new document through the normal documentation hub so future
    drains and reviewers can find it without repo archaeology.
- `docs/design/workflow_lisp_frontend_specification.md`
  - adds a narrow pointer from the umbrella/baseline contract to the new
    component doc without reopening the broader baseline design.

## Durable Contract Outline

The new durable Executable IR doc should be implementation-aligned and
structured around the current checkout, not around speculative future runtime
work. At minimum it should cover:

1. Purpose and scope boundary
   Explain that this is the current shared runtime-facing contract for
   validated executable workflows, not a replacement runtime or public author
   surface.

2. Authority boundary
   State explicitly that `LoadedWorkflowBundle.ir` / `ExecutableWorkflow` is
   authoritative and that `runtime_plan`, `semantic_ir`, `source_map`,
   `workflow_boundary_projection`, and debug YAML are derived layers.

3. Current schema and shape
   Document schema version, node ids, regions, node kinds, config families,
   bound addresses, contracts, and imported-bundle compatibility.

4. Validation ownership
   Explain the two checkpoints already present in the checkout:
   shared bundle-construction validation and later frontend `executable`
   revalidation/remap.

5. Derived-layer relationships
   Record how runtime plan, Semantic IR, source map, and observability consume
   validated executable nodes without redefining execution semantics.

6. Command-boundary and adapter obligations
   Point back to `docs/design/workflow_command_adapter_contract.md` for command
   semantics and keep inline semantic glue explicitly out of scope.

7. Runtime-value boundary
   State that compile-time-only values such as `ProcRef`, `WorkflowRef`,
   `let-proc`, syntax objects, and runtime closures do not appear in
   executable/runtime artifacts.

8. Evidence and fixture expectations
   Cite the existing shared-lowering, build-artifact, and diagnostic tests that
   prove the contract already exists in code.

## Verification Strategy

This slice should use deterministic documentation checks, not new runtime
tests, unless a documentation audit exposes a real implementation mismatch.

Minimum checks:

- the selected architecture, work-item context, check-command list, execution
  plan, and draft bundle exist;
- the implementation architecture includes the required
  `Relationship To Existing Implementation Architectures` section;
- the work-item context lists
  `docs/design/workflow_command_adapter_contract.md` in authoritative inputs;
- the architecture and context explicitly reference the durable Executable IR
  doc path and bounded docs-first scope.

## Acceptance Conditions

- one bounded implementation architecture is drafted for exactly
  `executable-ir-durable-contract-surface`;
- the architecture stays scoped to the missing durable design surface and does
  not reopen already-landed executable/runtime implementation work;
- the future work item clearly creates one durable Executable IR contract doc
  and indexes it;
- the command-adapter contract remains authoritative anywhere executable
  command boundaries or runtime-native promotion are discussed;
- the draft bundle points to the prescribed architecture, context, check, and
  plan target paths.
