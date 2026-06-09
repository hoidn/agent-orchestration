# Core Statement Taxonomy Contract Implementation Architecture

Status: draft
Design gap id: `core-statement-taxonomy-contract`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded contract work needed to close the unified
design gap around the Core statement taxonomy:

- draft one current-implementation-aligned contract matrix for every shared
  validation-relevant Core statement family already represented in
  `orchestrator/workflow/core_ast.py`;
- define the matching "attached semantic facets" that the current repo carries
  on statement `common` payloads, executable configs, runtime-plan operations,
  and semantic-IR promotions rather than as standalone `CoreStmt` dataclasses;
- pin down, per family or facet:
  - inputs and outputs;
  - effect and contract authority;
  - proof and lexical-scope behavior;
  - state/write-root behavior;
  - source-map and observability obligations;
  - shared validation ownership and runtime ownership;
- preserve coherence with the already-implemented Core AST, Semantic IR,
  executable IR, runtime-plan, source-map, stdlib-lowering, and write-root
  slices without reopening their semantics.

This slice does not implement:

- new `CoreStmt` dataclasses, new executable node kinds, or new runtime-native
  effects;
- a redesign of `workflow_lisp_core_stmt_taxonomy.md` into a replacement
  product spec;
- changes to shared lowering/runtime behavior, adapter classification, pointer
  authority, report authority, or write-root allocation;
- new scripts, inline shell/Python glue, legacy adapters, or hidden semantic
  command shims.

The work stays bounded to one architecture gap. It is a contract-alignment
architecture for the statement taxonomy, not a code rewrite and not a broader
frontend redesign.

## Problem Statement

The selected target-design gap is no longer "invent a statement taxonomy."
This checkout already has concrete shared statement dataclasses and downstream
consumers:

- `orchestrator/workflow/core_ast.py` defines the current shared families:
  `CoreCommandStep`, `CoreProviderStep`, `CoreAdjudicatedProviderStep`,
  `CoreWaitForStep`, `CoreAssertStep`, `CoreSetScalarStep`,
  `CoreIncrementScalarStep`, `CoreMaterializeArtifactsStep`,
  `CoreSelectVariantOutputStep`, `CoreCallStep`, `CoreIf`, `CoreMatch`,
  `CoreForEach`, `CoreRepeatUntil`, plus structural blocks
  `CoreBranchBlock`, `CoreMatchCaseBlock`, and `CoreFinally`;
- `orchestrator/workflow/semantic_ir.py` already derives statement, effect,
  proof, prompt-surface, command-boundary, state-layout, and source-map bridge
  entries from those families plus attached step modifiers;
- `orchestrator/workflow/runtime_plan.py` already promotes publications,
  snapshot operations, and variant-selection operations from executable/common
  surfaces keyed back to statement `step_id`;
- `orchestrator/workflow_lisp/source_map.py` already validates Core-node and
  executable-node lineage for emitted build artifacts.

What is still missing is one bounded architecture document that states, in
current implementation terms, how each family and attached facet is supposed to
behave.

That gap matters because the older draft taxonomy doc is now only a partial
fit for the checkout:

- it still lists `CorePreSnapshot`, `CoreConsumeBundle`, `CorePublish`, and
  `CoreResourceTransitionCandidate` as standalone statement families even
  though current implementation carries those semantics as attached facets or
  promoted semantic effects;
- it does not inventory the now-real `CoreForEach` dataclass;
- it does not describe how command-boundary metadata, `variant_output`,
  `pre_snapshot`, `publishes`, managed jobs, reusable-boundary write roots, and
  source-map coverage compose with the base statement families.

The missing work is therefore a contract matrix over the implementation that
already exists:

```text
CoreStmt family
  + attached semantic facets
  -> shared validation expectations
  -> semantic IR projections
  -> runtime-plan / executable ownership
  -> source-map and observability obligations
```

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `34. Core Workflow AST Contract`
  - `35. Core Statement Taxonomy Contract`
  - `36. Semantic Workflow IR Contract`
  - `40. Effect Graph Contract`
  - `41. Proof Graph Contract`
  - `42. State Layout Contract`
  - `43. Source Map Contract`
  - `46. Acceptance Gate for Component Architecture`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `0. Prerequisites, Boundaries, And Missing Internal Specs`
  - `45. Core Workflow AST`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `48. Executable IR`
  - `53-58. Lowering rules touching provider, command, match, and stdlib forms`
  - `59. Validation Sequence`
  - `63-66. Variant, snapshot, pointer, and report-authority validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_core_workflow_ast.md`
- `docs/design/workflow_lisp_core_stmt_taxonomy.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- the actual shared dataclasses in `orchestrator/workflow/core_ast.py`, not an
  older umbrella doc list, are the implementation authority for base statement
  family identity;
- structured bundles remain authority, reports remain views, artifact values
  remain authority, and pointer files remain representations;
- command semantics stay explicit:
  `CoreCommandStep` is legal only for external tools or certified adapters and
  must keep adapter metadata visible through the shared bundle surfaces;
- no new runtime-native promotion, inline shell/Python semantics, or hidden
  report parsing may be introduced to make the taxonomy seem complete on paper;
- reusable-boundary write roots remain governed by the existing caller-owned
  policy and must not be redescribed as ad hoc statement-local behavior.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/standard-library-lowering-completion/implementation_architecture.md`
- historical shared-contract coherence references:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/semantic-workflow-ir-shared-contract/implementation_architecture.md`

### Decisions Reused

- Reuse the current ownership split:
  `orchestrator/workflow_lisp/` owns authoring/lowering provenance and
  `orchestrator/workflow/` owns shared Core AST, executable IR, runtime plan,
  and Semantic IR contracts.
- Reuse the already-implemented `CoreWorkflowAST`, `SemanticWorkflowIR`,
  `ExecutableWorkflow`, and `WorkflowRuntimePlan` surfaces as the authority
  layers this matrix must describe rather than replace.
- Reuse the effectful-composition slices' rule that composed `if`, `match`,
  loop, and stdlib forms lower through ordinary shared statement/runtime paths.
- Reuse the reusable-boundary write-root slice's managed-input policy and do
  not reinterpret generated write roots as a new standalone statement family.
- Reuse the stdlib-lowering slice's rule that adapter-backed forms such as
  `resource-transition` and reusable-state recovery remain ordinary lowering
  consumers of explicit command/adaptor boundaries.
- Reuse the executable-IR slice's rule that projections such as runtime plan,
  Semantic IR, and source map remain derived from validated shared artifacts.

### New Decisions In This Slice

- Define the taxonomy contract on two axes:
  - base statement families keyed to current shared dataclasses; and
  - attached semantic facets keyed to current modifier surfaces on statement
    `common`, executable configs, runtime-plan operations, and promoted
    semantic effects.
- Treat structural containers
  `CoreBranchBlock`, `CoreMatchCaseBlock`, and `CoreFinally`
  as contract-bearing nested blocks rather than flattening them into ordinary
  step rows or inventing new runtime nodes.
- Make the contract matrix explicitly map one base family to multiple attached
  facets when needed. Example:
  `CoreCommandStep + boundary facet + publication facet + write-root facet`.
- Keep the output of this slice docs/test focused. Do not introduce a new
  machine-readable registry module merely to satisfy the architecture wording.

### Conflicts Or Revisions

The older draft `docs/design/workflow_lisp_core_stmt_taxonomy.md` describes the
right problem space, but its family inventory no longer matches the checkout
literally. This slice revises that assumption narrowly:

- `CoreForEach` is a real shared family and belongs in the matrix;
- `publish`, `consume_bundle`, `variant_output`, and `pre_snapshot` are current
  attached semantic facets, not standalone shared dataclasses;
- `resource_transition` is currently represented through certified-adapter
  command boundaries plus promoted Semantic IR effects, not a
  `CoreResourceTransitionCandidate` dataclass;
- the contract matrix therefore inventories both base families and attached
  facets instead of forcing the current repo into a purely one-row-per-doc-name
  model.

No prior slice is revised on shared concepts such as spans, diagnostics,
TypeCatalog, SourceMap, pointer authority, variant proof, or runtime-plan
identity.

## Ownership Boundaries

This slice owns:

- the bounded architecture contract for how current shared statement families
  and attached semantic facets are inventoried;
- the mapping from each family/facet to validation, Semantic IR, runtime-plan,
  executable, and source-map ownership;
- the list of shared modules and tests a future implementation pass should
  verify when tightening taxonomy coverage;
- the documentation-level conflict resolution between the older draft taxonomy
  doc and the actual current implementation.

This slice intentionally does not own:

- changes to `core_ast.py`, `semantic_ir.py`, `runtime_plan.py`,
  `executable_ir.py`, or runtime behavior;
- creation of new adapter scripts, runtime-native promotion, or new command
  boundary types;
- redesign of the shared bundle pipeline, stdlib lowering, write-root
  allocation, or source-map artifact schema;
- any edit to progress ledgers, run state, backlog queues, or unrelated design
  docs.

## Current Checkout Facts

- `orchestrator/workflow/core_ast.py` already exists and exports
  `CORE_WORKFLOW_AST_SCHEMA_VERSION = "core_workflow_ast.v1"`,
  `CoreStmtMeta`, all current base statement dataclasses, the builder, the
  validator, and JSON serialization.
- `validate_core_workflow_ast(...)` already checks schema version, duplicate
  statement ids, source-map origin presence, and import-alias validity for
  call statements. It does not yet itself encode the full per-family matrix.
- `orchestrator/workflow/semantic_ir.py` already derives:
  - `SemanticStatement` rows keyed by statement `step_id`;
  - command-boundary entries;
  - prompt surfaces;
  - promoted adapter effects such as `resource_transition` and
    `ledger_update`;
  - promoted generated effects such as `snapshot_capture` and
    `pointer_materialization`.
- `orchestrator/workflow/runtime_plan.py` already emits publication and
  operation projections for `publishes`, `variant_output`, `pre_snapshot`,
  `materialize_artifacts`, and `select_variant_output` from executable/common
  surfaces keyed to node ids and step ids.
- `orchestrator/workflow_lisp/source_map.py` already validates Core-node
  coverage, executable-node coverage, generated-effect coverage, and frontend
  command-boundary lineage against emitted `source_map.json`.
- `orchestrator/workflow_lisp/build.py` already emits
  `core_workflow_ast.json`, `semantic_ir.json`, `executable_ir.json`, and
  `source_map.json`, so this gap is not missing build artifacts. It is missing
  the bounded architecture that states how the statement-family contracts fit
  together.

## Proposed Package Boundary

No new package is required. Future implementation work for this gap should stay
within the existing shared/runtime and build-verification surfaces:

```text
orchestrator/workflow/
  core_ast.py         # base statement-family dataclasses and validator
  semantic_ir.py      # effect/proof/boundary/source-map projections per family
  runtime_plan.py     # publication and operation projections keyed to statements
  executable_ir.py    # runtime operation/config surfaces consumed by facets
  loaded_bundle.py    # shared bundle carrier, unchanged authority boundary

orchestrator/workflow_lisp/
  source_map.py       # core-node/executable-node/facet lineage validation
  build.py            # emitted artifact and coverage surfaces

tests/
  test_workflow_core_ast.py
  test_workflow_semantic_ir.py
  test_loader_validation.py
  test_workflow_lisp_build_artifacts.py
  test_workflow_lisp_diagnostics.py
  test_runtime_observability.py
  test_runtime_observability_cli.py
```

Primary responsibilities:

- `core_ast.py`
  - remains the authority for base statement-family names, base fields, nested
    block topology, and Core-level structural validation.
- `semantic_ir.py`
  - remains the authority for effect, proof, command-boundary, prompt-surface,
    and promoted semantic-facet projection.
- `runtime_plan.py`
  - remains the authority for publication, snapshot, and operation projections
    keyed back to statement/runtime node identity.
- `source_map.py`
  - remains the authority for per-family/facet lineage coverage requirements.

## Contract Model

### 1. Base Statement Family Rows

Every row in the taxonomy matrix must be keyed to one of the current shared
families:

| Family | Primary role | Nested scope/proof behavior |
| --- | --- | --- |
| `CoreCommandStep` | external tool or certified adapter boundary | no nested scope; proof only through attached facets |
| `CoreProviderStep` | provider call boundary | no nested scope; prompt-surface and contract injection facets apply |
| `CoreAdjudicatedProviderStep` | adjudicated provider boundary | no nested scope; adjudication facet applies |
| `CoreWaitForStep` | wait/poll gate | no nested scope |
| `CoreAssertStep` | assertion gate | no nested scope |
| `CoreSetScalarStep` | scalar update | no nested scope |
| `CoreIncrementScalarStep` | scalar increment/update | no nested scope |
| `CoreMaterializeArtifactsStep` | artifact value materialization | no nested scope |
| `CoreSelectVariantOutputStep` | durable evidence variant selection | no nested scope |
| `CoreCallStep` | workflow/import call boundary | no nested scope; reusable-boundary write-root facet may apply |
| `CoreIf` | branch container over condition | introduces branch blocks, but not variant proof |
| `CoreMatch` | branch container over proved variant/state match | introduces match-case proof context |
| `CoreForEach` | bounded repeated nested statement container | introduces loop body scope |
| `CoreRepeatUntil` | bounded loop with typed outputs | introduces loop body scope and exhaustion routing |

Structural nested blocks are part of the contract surface:

- `CoreBranchBlock` carries branch-local statements and outputs for `CoreIf`;
- `CoreMatchCaseBlock` carries case-local statements and outputs for
  `CoreMatch`;
- `CoreFinally` carries finalization statements that always execute after the
  main body.

### 2. Attached Semantic Facets

Because the current implementation does not model every validation-relevant
surface as a standalone statement class, the taxonomy contract must also track
these attached facets:

| Facet | Current carrier | Meaning |
| --- | --- | --- |
| Publication facet | `common.publishes`, `common.variant_output` | artifact publication and variant-aware publication authority |
| Consumption facet | `common.consumes`, `common.consume_bundle`, provider prompt consume fields | lineage and prompt/input dependency surfaces |
| Snapshot facet | `common.pre_snapshot`, `CoreSelectVariantOutputStep`, runtime-plan operations | durable evidence and variant-selection support |
| Boundary facet | command `boundary_kind`/`boundary_name`, provider `managed_jobs` | explicit command/provider backend semantics |
| Proof facet | `common.requires_variant`, `CoreMatch` cases | proof obligations and variant-scoped availability |
| Write-root facet | generated internal inputs, imported managed write-root inputs | deterministic caller-owned output/root allocation |
| Source-map facet | `CoreStmtMeta.origin_key`, frontend command-boundary metadata, runtime node ids | authored lineage and observability coverage |
| Promoted semantic-effect facet | Semantic IR promoted effect entries | current place where adapter and generated effects become typed semantic facts |

### 3. Required Matrix Fields

Each family/facet row in the future implementation inventory must answer:

1. What authored/shared inputs define the row?
2. What direct outputs or derived projections does it publish?
3. Which effect classes can it emit, and where are they recorded?
4. Which contract surfaces are authoritative?
5. Does it create proof or only consume proof?
6. How are state paths or managed write roots allocated?
7. Which source-map keys, runtime node ids, or validation subjects must exist?
8. Which shared module validates it, and which runtime/shared module executes
   or projects it?

## Statement-Family Contract Matrix

| Family or facet | Inputs | Outputs / projections | Effects | Proof / scope | State / write roots | Source-map fields | Ownership |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `CoreCommandStep` | `command`, `common`, boundary metadata | executable command node, Semantic IR command boundary, publications via attached facets | `command_call`; adapter-promoted `resource_transition` / `ledger_update` only when certified | consumes attached `requires_variant`; no new proof | may consume managed write roots from caller or materialize outputs via `common` | `meta.id`, `meta.step_id`, `meta.origin_key`, command-boundary source-map behavior | validate: `core_ast.py`, `semantic_ir.py`; runtime/projection: `executable_ir.py`, `runtime_plan.py` |
| `CoreProviderStep` | provider config, prompt inputs, `common` | executable provider node, prompt surface, publications via attached facets | `provider_call` | consumes attached `requires_variant`; no new proof | standard runtime roots; managed jobs stay explicit | `meta.*`, prompt surface, executable node ids | validate/projection: `core_ast.py`, `semantic_ir.py`, `runtime_plan.py` |
| `CoreAdjudicatedProviderStep` | adjudication config, `common` | executable adjudicated provider node, prompt/publication projections | `provider_call` with adjudication | no new proof | standard runtime roots | `meta.*`, executable node ids | shared validation/runtime as provider family |
| `CoreWaitForStep` | `wait_for`, `common` | executable wait node | wait/poll runtime effect | no proof | no special write-root policy | `meta.*` + node ids | validate: `core_ast.py`; runtime: `executable_ir.py` |
| `CoreAssertStep` | predicate, `common` | executable assert node | assertion gate | no proof creation | no special policy | `meta.*` + node ids | validate: shared surface + `core_ast.py`; runtime: `executable_ir.py` |
| `CoreSetScalarStep` | scalar payload, `common` | executable scalar-set node | state/scalar update | no proof | runtime-managed scalar state | `meta.*` + node ids | validate/runtime: shared lowering + executable/runtime plan |
| `CoreIncrementScalarStep` | increment payload, `common` | executable scalar-increment node | state/scalar update | no proof | runtime-managed scalar state | `meta.*` + node ids | validate/runtime: shared lowering + executable/runtime plan |
| `CoreMaterializeArtifactsStep` | materialization payload, `common` | executable materialization node, runtime-plan artifact operation | `pointer_materialization` only through promoted generated effect path | no proof | may touch managed artifact targets but not semantic authority | `meta.*`, runtime-plan operation ids | validate: `core_ast.py`, `semantic_ir.py`; runtime/projection: `runtime_plan.py` |
| `CoreSelectVariantOutputStep` | selection payload, durable evidence refs, `common` | executable select-variant node, runtime-plan selection operation | variant-selection / snapshot-driven routing | consumes evidence, no new proof | uses snapshot evidence, not mtime | `meta.*`, runtime-plan operation ids | validate: `core_ast.py`, `semantic_ir.py`; runtime/projection: `runtime_plan.py` |
| `CoreCallStep` | call alias and bindings, `common` | executable call node, call-edge projection | `workflow_call` | no proof creation | reusable-boundary managed write roots may apply | `meta.*`, call-edge ids, node ids | validate: `core_ast.py`, `semantic_ir.py`; runtime: call lowering/runtime bundle |
| `CoreIf` + `CoreBranchBlock` | condition, branch blocks | branch-local statements, joined runtime nodes | branch-conservative union of child effects | branch scope only; no variant proof | branch-local write roots follow child statements | parent `meta.*` plus nested child origin keys | validate: `core_ast.py`; projections derive from nested children |
| `CoreMatch` + `CoreMatchCaseBlock` | match ref, case blocks | case-local statements, joined runtime nodes | branch-conservative union of child effects | creates case proof context and scoped availability | case-local write roots follow child statements | parent `meta.*` plus nested child origin keys | validate: `core_ast.py`, `semantic_ir.py`; projections derive from nested children |
| `CoreForEach` | items/items_from, nested statements | repeated nested runtime nodes | union of child effects across bounded loop body | loop scope only | loop-scoped write-root disambiguation from existing policy | `meta.*` plus nested child origin keys and node ids | validate: `core_ast.py`; runtime/projection: executable/runtime plan |
| `CoreRepeatUntil` | condition, max iterations, nested statements, typed outputs | repeated runtime nodes, loop outputs, exhaustion route | union of child effects across bounded loop | loop scope only | loop-scoped write-root disambiguation from existing policy | `meta.*`, nested child origins, node ids | validate: `core_ast.py`, `semantic_ir.py`; runtime/projection: executable/runtime plan |
| `CoreFinally` | finalization statements | finalization runtime nodes only | union of child effects | finalization scope only | child-statement policy only | finalization step id plus child origins | validate: `core_ast.py`; runtime/projection from nested children |

Attached semantic facets must be checked against the base row they decorate:

- publication facet:
  - authority lives in typed contracts and runtime-plan publication entries, not
    in rendered reports;
- snapshot facet:
  - authority lives in `pre_snapshot` + `select_variant_output` durable
    evidence, not in mtime or prose;
- boundary facet:
  - `CoreCommandStep` boundary metadata must stay aligned with
    `workflow_command_adapter_contract.md`;
- write-root facet:
  - call and producer families must continue using caller-owned managed inputs,
    not ad hoc local path reconstruction;
- promoted semantic-effect facet:
  - `resource_transition`, `ledger_update`, `snapshot_capture`, and
    `pointer_materialization` remain derived semantic facts and must not be
    back-filled from report text or hidden shell behavior.

## Verification Strategy

Future implementation work for this slice should verify the matrix through
focused shared tests rather than broad snapshot-only coverage:

- `tests/test_workflow_core_ast.py`
  - family inventory, statement-id uniqueness, origin-key coverage, nested
    block lineage, command-boundary carry-through;
- `tests/test_workflow_semantic_ir.py`
  - per-family effect, proof, boundary, prompt-surface, and promoted-effect
    projections;
- `tests/test_loader_validation.py`
  - family-specific shared validation failures where the matrix requires them;
- `tests/test_workflow_lisp_build_artifacts.py`
  - emitted Core AST / Semantic IR / executable IR / source-map coherence;
- `tests/test_workflow_lisp_diagnostics.py`
  - stable diagnostics for missing lineage or invalid shared statement usage;
- `tests/test_runtime_observability.py` and
  `tests/test_runtime_observability_cli.py`
  - runtime-plan and observability alignment for statement ids, node ids, and
    publications.

## Acceptance Conditions

Do not treat this gap as closed until:

- one bounded architecture explicitly inventories current base statement
  families and attached semantic facets;
- the required `Relationship To Existing Implementation Architectures` section
  is present;
- the architecture states how the older draft taxonomy doc differs from the
  current checkout;
- `docs/design/workflow_command_adapter_contract.md` remains an explicit
  authority input for command/adaptor/runtime-native-promotion concerns;
- the draft bundle points to the prescribed architecture, context, check, and
  plan-target paths.
