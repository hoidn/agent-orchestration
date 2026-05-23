# Rich Semantic Effect Graph Implementation Architecture

## Scope

This design gap covers only the bounded Workflow Lisp effect-modeling slice
selected by the current drain state:

- extend the frontend-local effect taxonomy so the selected semantic effect
  classes are explicit rather than collapsed into generic command or state
  usage;
- thread those effect facts through lowering and persisted frontend provenance
  for the selected classes only:
  resource transition, ledger update, snapshot capture, and pointer
  materialization;
- project the richer effect facts into the already-implemented shared
  `SemanticWorkflowIR` without redefining Core Workflow AST, runtime plan, or
  pointer-authority rules;
- add validation that the promoted effect entries stay honest to the declared
  command-adapter contract and to the validated lowered workflow surfaces.

Out of scope for this tranche:

- new frontend authoring forms, new resource/drain semantics, or changes to
  queue behavior, pointer authority, snapshot runtime behavior, or ledger
  persistence;
- a repo-wide YAML effect-inference rewrite;
- runtime-native resource, ledger, snapshot, or pointer effects;
- redesign of shared `CoreWorkflowAST`, `SemanticWorkflowIR`,
  `WorkflowRuntimePlan`, `SourceMap`, `TypeCatalog`, diagnostics, or variant
  proof;
- promoting every certified-adapter effect string into a shared semantic
  effect kind in one step;
- report parsing, pointer-as-state recovery, inline shell/Python glue, or
  other behavior banned by
  `docs/design/workflow_command_adapter_contract.md`.

This is an implementation architecture for exactly the selected
`rich-semantic-effect-graph` gap. It does not reopen the full frontend or
runtime design.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `46. Validated Core Workflow AST`
  - `47. Semantic IR`
  - `59. Validation Sequence`
  - `61. Effect Validation`
  - `65. Pointer Authority Validation`
  - `74. Source Map Requirements`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  - `6. Lowering Contract`
  - `9. Source Spans And Diagnostics`
  - `10. Validation`
- `docs/design/workflow_lisp_effect_graph.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/steering.md`

The slice must also preserve the guardrails established by earlier
implementation architectures and by the current checkout:

- keep `orchestrator/workflow_lisp/` frontend-owned and keep shared semantic
  meaning under `orchestrator/workflow/`;
- reuse the current staged path:
  read -> syntax -> macro expansion -> definitions/functions/procedures/
  workflows -> typecheck/effects -> lowering -> shared validation ->
  shared Core AST / Semantic IR / runtime plan;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse the current shared `CoreWorkflowAST`, shared `SemanticWorkflowIR`,
  `WorkflowRuntimePlan`, `ValidationSubjectRef`, and persisted `source_map.json`
  rather than inventing a parallel effect-only IR;
- keep command-boundary semantics on the `external_tool` versus
  `certified_adapter` split, and only promote adapter effects that were already
  declared in the certified command-adapter contract.

`docs/design/workflow_command_adapter_contract.md` is authoritative here
because this slice promotes adapter-declared semantic behavior into explicit
effect entries. It must not:

- infer semantic effects by parsing shell text;
- treat pointer files as semantic authority;
- treat reports as state;
- smuggle runtime-native semantics behind a command-shaped step;
- promote undeclared adapter behavior into the effect graph.

`docs/steering.md` is empty in this checkout. That does not widen scope. The
selector bundle, target contract, current shared implementation, and prior
architecture slices remain the effective steering surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defschema-reusable-field-schemas/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-cli-artifact-emission/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/if-conditionals-pure-proven-values/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/loop-recur-bounded-loops/implementation_architecture.md`
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

- Reuse the existing frontend package ownership split and staged compiler
  pipeline rather than centralizing frontend effect inference under
  `orchestrator/workflow/`.
- Reuse the current source lineage substrate:
  `SourcePosition`,
  `SourceSpan`,
  `LispFrontendDiagnostic`,
  `LoweringOriginMap`,
  `ValidationSubjectRef`,
  and persisted `source_map.json`.
- Reuse the shared `CoreWorkflowAST`, `SemanticWorkflowIR`, and
  `WorkflowRuntimePlan` already present in the checkout instead of proposing a
  second effect-only semantic bundle.
- Reuse the certified-adapter contract surface already carried by
  `CertifiedAdapterBinding`, including declared `effects`,
  `path_safety`, `source_map_behavior`, `fixture_ids`, and
  `negative_fixture_ids`.
- Reuse the Stage 5 and Stage 6 lowering shapes for
  `produce-one-of`,
  `run-provider-phase`,
  `review-revise-loop`,
  `resource-transition`,
  `finalize-selected-item`,
  and `backlog-drain`.
- Reuse shared runtime ownership of pointer-authority enforcement, snapshot
  execution, and ledger persistence; this slice only makes those effects more
  explicit in compile-time and semantic surfaces.

### New Decisions In This Slice

- Add four explicit promoted effect classes for the selected gap:
  `moves_resource`,
  `updates_ledger`,
  `captures_snapshot`,
  and `materializes_pointer`.
- Keep the existing generic effect entries
  `provider_call`,
  `command_call`,
  and `workflow_call`;
  promoted effects augment them and do not replace the execution-boundary
  record.
- Extend frontend provenance so lowering can persist deterministic semantic
  effect lineage for generated snapshot-capture and pointer-materialization
  steps, and can persist adapter-declared effect names for certified command
  boundaries.
- Extend shared Semantic IR validation so promoted effects must correspond to
  real validated surfaces:
  `pre_snapshot` for snapshot capture,
  `materialize_artifacts.values[*].pointer.path` for pointer materialization,
  and certified-adapter declarations for resource/ledger effects.
- Keep promoted effect inference narrowly allowlisted:
  only `resource_transition` and `ledger_update` adapter declarations become
  shared semantic effect kinds in this slice; other adapter effect strings stay
  visible in adapter metadata but do not yet become first-class shared effect
  entries.

### Conflicts Or Revisions

There is one explicit `stale_duplicate` inconsistency across prior slices and
the current checkout:

- older implementation-architecture documents for shared Core AST and Semantic
  IR describe those surfaces as future work;
- the current checkout already contains `orchestrator/workflow/core_ast.py`,
  `orchestrator/workflow/semantic_ir.py`, and the matching build/runtime
  plumbing.

This slice follows the current implemented contract, not the stale future-tense
wording. The revision is narrow:

- do not reopen the shared Core AST or Semantic IR creation problem;
- treat the missing work as richer effect classification and validation inside
  the existing shared surfaces;
- state the conflict explicitly so downstream plans do not keep assuming those
  shared modules are deferred.

This slice does not redefine spans, diagnostics, TypeCatalog, SourceMap,
pointer authority, variant proof, or runtime-plan ownership.

## Ownership Boundaries

This slice owns:

- the frontend-local effect taxonomy additions for the selected promoted
  classes;
- typechecking/inference changes where authored forms already expose the
  selected semantics directly, especially `resource-transition`;
- lowering-owned semantic-effect lineage for generated snapshot and pointer
  surfaces;
- source-map serialization for promoted-effect provenance;
- shared Semantic IR entry-shape extensions and validation for the selected
  promoted effect kinds;
- focused tests for effect parsing, inference, lowering provenance, Semantic IR
  projection, and validation failures.

This slice intentionally does not own:

- new adapter backends or changes to adapter fixture semantics;
- new runtime-native effects or changes to queue, snapshot, pointer, or ledger
  execution behavior;
- generic inference of all certified-adapter effect strings into shared effect
  kinds;
- the state manager, pointer-authority checker, or runtime artifact registry;
- YAML-authored workflow refactors unrelated to the selected effect classes;
- redesign of shared `CoreWorkflowAST`, `WorkflowRuntimePlan`, or the broader
  `SemanticWorkflowIR` contract beyond the narrow effect-entry extension.

## Current Checkout Facts

The selected gap remains real in the current checkout, but it is narrower than
the selector summary alone suggests:

- `orchestrator/workflow_lisp/effects.py` defines only
  `ReadEffect`,
  `WriteEffect`,
  `PublishEffect`,
  `UsesProviderEffect`,
  `UsesCommandEffect`,
  `CallsWorkflowEffect`, and
  `UpdatesStateEffect`;
  there are no explicit atoms for resource moves, ledger updates, snapshot
  capture, or pointer materialization.
- `orchestrator/workflow_lisp/typecheck.py` currently infers
  `resource-transition` as only `UsesCommandEffect(("apply_resource_transition",))`,
  even though the adapter binding declares semantic effects
  `resource_transition` and `ledger_update`.
- `orchestrator/workflow_lisp/compiler.py` already registers certified adapter
  metadata for `apply_resource_transition` and reusable-state validators, but
  that metadata is not promoted into the frontend effect summary or shared
  Semantic IR.
- `orchestrator/workflow_lisp/lowering.py` already emits
  `materialize_artifacts` steps with pointer paths for prompt-input and summary
  compatibility shims, and already emits `pre_snapshot` for structured variant
  selection flows, but those generated semantic actions are not recorded as
  explicit effect lineage.
- `orchestrator/workflow_lisp/source_map.py` already persists
  `command_boundaries`, `core_nodes`, `validation_subjects`, and
  `executable_nodes`, but it does not persist promoted semantic effect lineage
  or adapter-declared effect names.
- `orchestrator/workflow/semantic_ir.py` already exists, but it currently emits
  only generic
  `workflow_call`,
  `provider_call`, and
  `command_call`
  effect entries, while treating snapshots and managed write roots mostly as
  `state_layout` or runtime-plan facts.
- `orchestrator/workflow/runtime_plan.py` already derives snapshot-sensitive
  plan entries for `pre_snapshot`, `select_variant_output`, and
  `materialize_artifacts`, so runtime-observable structure exists and should be
  reused rather than reinvented.

The honest missing contract is therefore not “build Semantic IR.” It is
“promote selected semantic side effects out of coarse command/state buckets and
validate them end-to-end.”

## Proposed Package Boundary

Extend the current implementation through existing modules rather than adding a
new standalone effect package:

```text
orchestrator/workflow_lisp/
  effects.py          # extend effect atoms, parsing, rendering, normalization
  typecheck.py        # infer promoted effects for authored forms in scope
  lowering.py         # record generated promoted-effect lineage
  source_map.py       # serialize command-boundary effect metadata and generated effects
  compiler.py         # validate adapter effect allowlist during compile setup
  build.py            # carry the richer source-map payload unchanged

orchestrator/workflow/
  semantic_ir.py      # ingest promoted-effect lineage, extend validation, emit JSON
  core_ast.py         # reused validated statement authority, no taxonomy rewrite
  runtime_plan.py     # reused runtime summary authority, no schema rewrite
```

Planned test surface:

```text
tests/
  test_workflow_lisp_effects.py
  test_workflow_lisp_resource_stdlib.py
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_source_map.py
  test_workflow_semantic_ir.py
  fixtures/workflow_lisp/valid/resource_transition_effects.orc
  fixtures/workflow_lisp/valid/phase_snapshot_effects.orc
  fixtures/workflow_lisp/valid/pointer_materialization_effects.orc
  fixtures/workflow_lisp/invalid/command_boundary_effect_promotion_invalid.orc
  fixtures/workflow_lisp/invalid/pointer_effect_lineage_invalid.orc
```

## Data Model

### Frontend Effect Atoms

Extend `orchestrator/workflow_lisp/effects.py` with four new frontend-local
atoms:

- `MovesResourceEffect`
  - `subject`
  - `from_queue`
  - `to_queue`
- `UpdatesLedgerEffect`
  - `subject`
  - `event_name`
- `CapturesSnapshotEffect`
  - `subject`
  - `snapshot_kind`
  - `candidate_names`
- `MaterializesPointerEffect`
  - `subject`
  - `pointer_path`
  - `representation_role`

Rules:

- the new atoms participate in `EffectSummary` exactly like existing atoms;
- `render_effect_atom(...)` and effect-mismatch diagnostics must print them
  deterministically;
- declared-effect parsing may accept the authored spellings
  `moves-resource`,
  `updates-ledger`,
  `captures-snapshot`, and
  `materializes-pointer`,
  but authored use is still bounded by the forms that can honestly infer them
  in the current tranche.

### Persisted Promoted-Effect Lineage

Extend the persisted Workflow Lisp source-map payload with two narrow metadata
surfaces:

- extend `CommandBoundaryLineage` with:
  - `declared_effects: tuple[str, ...]`
- add `GeneratedSemanticEffectLineage`:
  - `effect_key`
  - `step_id`
  - `effect_kind`
  - `origin_key`
  - `details`

`GeneratedSemanticEffectLineage` is not a second effect graph. It is a
frontend-owned provenance supplement for semantic effects introduced by
lowering:

- `captures_snapshot` for generated `pre_snapshot` surfaces;
- `materializes_pointer` for generated pointer writes in
  `materialize_artifacts`;
- optional future generated effect classes only if a later slice explicitly
  owns them.

Deterministic key rule:

- `effect_key` must be unique within one workflow source-map section;
- the key must derive from stable authored/lowered identifiers, such as
  `snapshot:<step_id>:<name>` or `pointer:<step_id>:<value_name>`,
  never from list order alone.

### Shared Semantic Effect Entry Extension

Extend `SemanticEffectEntry` in `orchestrator/workflow/semantic_ir.py` with one
bounded details channel:

- `details: Mapping[str, Any] = empty_frozen_mapping()`

Use `details` only for the selected promoted effects:

- `resource_transition`
  - `from_queue`
  - `to_queue`
- `ledger_update`
  - `event_name`
- `snapshot_capture`
  - `snapshot_kind`
  - `candidate_names`
- `pointer_materialization`
  - `pointer_path`
  - `representation_role`

Existing fields remain authoritative for generic execution-boundary semantics:

- `boundary_kind`
- `boundary_name`
- `call_target`
- `output_validation_surface`
- `source_map_behavior`
- `ref_ids`

This keeps the effect entry schema additive rather than introducing one new
record type per effect kind.

## Effect Derivation And Lowering Model

### 1. Authored Effect Inference

Only authored forms that already expose the selected behavior directly gain
new inferred atoms in this slice.

`resource-transition`:

- keep the existing `UsesCommandEffect(("apply_resource_transition",))`;
- also infer:
  - `MovesResourceEffect`
  - `UpdatesLedgerEffect`

Why both layers remain:

- `UsesCommandEffect` records the command boundary dependency;
- the new atoms record the workflow-semantic behavior that the certified
  adapter carries explicitly under the command-adapter contract.

No other authored form is required to infer promoted atoms at typecheck time in
this tranche. Snapshot capture and pointer materialization are generated
lowering behaviors and should be modeled at that seam instead of inventing
fake authored syntax.

### 2. Lowering-Owned Promoted Effects

`lowering.py` becomes the owner of promoted-effect lineage for generated
surfaces:

- when lowering emits `pre_snapshot`, record one
  `GeneratedSemanticEffectLineage(effect_kind="snapshot_capture", ...)`;
- when lowering emits `materialize_artifacts.values[*].pointer.path`, record
  one
  `GeneratedSemanticEffectLineage(effect_kind="pointer_materialization", ...)`;
- the recorded details must contain only validated structural data already
  known at lowering time;
- the lowering context records the origin key from the same authored span that
  already owns the generated step or path.

Selection rule:

- `pre_snapshot` is effectful because it captures durable evidence;
- `select_variant_output` is not promoted as a new effect kind in this slice,
  because it consumes prior evidence instead of creating a new side effect;
- ordinary `materialize_artifacts` entries without `pointer.path` are not
  promoted by this slice.

### 3. Command-Boundary Promotion

Certified adapters already declare `effects` as strings. This slice introduces
one narrow normalization rule:

- `resource_transition` -> shared semantic effect kind `resource_transition`
- `ledger_update` -> shared semantic effect kind `ledger_update`

All other declared adapter effects remain adapter metadata only for now.

Promotion preconditions:

- boundary kind must be `certified_adapter`;
- the binding must come from a validated `CertifiedAdapterBinding`;
- the declared effect name must be in the explicit allowlist above;
- the step must still receive the generic `command_call` effect entry.

`external_tool` bindings never produce promoted semantic effects in this slice.

### 4. Shared Semantic IR Projection

`derive_workflow_semantic_ir(...)` should merge four sources of effect facts in
stable order:

1. generic shared step-kind effects:
   `workflow_call`,
   `provider_call`,
   `command_call`;
2. command-boundary promoted effects from source-map command lineage;
3. lowering-generated promoted effects from source-map generated-effect
   lineage;
4. existing proof and state-layout indexing, unchanged except for any new
   effect refs.

ID policy:

- keep the current `effect:<workflow>:<step_id>:<effect_kind>` shape when one
  effect of that kind exists for the statement;
- append `:<effect_key>` when a statement may own multiple entries of the same
  promoted kind, especially pointer materialization.

YAML compatibility rule:

- YAML workflows continue to receive only the shared effects that can be
  derived honestly from shared validated surfaces;
- this slice does not add speculative pointer or ledger inference for generic
  YAML command steps.

## Validation Model

Validation responsibilities split across existing ownership lines.

### Frontend Validation

`orchestrator/workflow_lisp/` validates:

- new effect spellings parse only in valid effect clauses;
- `resource-transition` inferred promoted atoms remain consistent with the
  certified adapter binding;
- generated promoted-effect lineage references existing generated step ids and
  origin keys;
- only allowlisted adapter effect strings are promoted into persisted lineage.

### Shared Semantic IR Validation

`orchestrator/workflow/semantic_ir.py` validates:

- every promoted effect entry references a real statement id in the workflow;
- `resource_transition` and `ledger_update` effects appear only on statements
  that also have a matching `command_call` effect and a
  `certified_adapter` boundary kind;
- `snapshot_capture` effects correspond to actual validated `pre_snapshot`
  surfaces;
- `pointer_materialization` effects correspond to actual
  `materialize_artifacts.values[*].pointer.path` payloads;
- promoted pointer effects remain representational metadata and never replace
  ordinary artifact or bundle refs as semantic authority;
- effect ids remain unique and deterministic.

### Reused Shared Authority

This slice does not reimplement:

- pointer-authority conflict detection;
- path-safety enforcement;
- snapshot capture runtime execution;
- queue movement semantics;
- ledger file persistence.

Those checks remain shared runtime or loader responsibilities. The effect graph
only makes the selected semantic actions more explicit and more queryable.

## Test Strategy

### Frontend Unit Tests

- `effects.py`
  - parse/render new effect kinds
  - effect-summary merge behavior
- `typecheck.py`
  - `resource-transition` infers `MovesResourceEffect` and
    `UpdatesLedgerEffect`
  - effect-mismatch diagnostics include new labels
- `lowering.py` / `source_map.py`
  - `pre_snapshot` emits snapshot-capture lineage
  - pointer-emitting `materialize_artifacts` emits pointer-materialization
    lineage
  - non-pointer materialization does not emit promoted pointer effects

### Shared Semantic IR Tests

- promoted effects appear in `SemanticWorkflowIR.effects` with stable ids and
  expected details;
- resource and ledger promoted effects coexist with generic `command_call`;
- YAML workflows without frontend lineage remain on the coarse shared effect
  surface;
- invalid lineage raises `semantic_ir_invalid`.

### Regression Tests

- selected-item / drain lowering still passes current resource/drain regression
  coverage;
- phase stdlib lowering still passes current snapshot-driven structured-result
  coverage;
- build/source-map emission remains JSON-serializable and deterministic.

## Implementation Sequence

1. Extend frontend effect atoms, renderers, and declared-effect parsing in
   `orchestrator/workflow_lisp/effects.py`.
2. Update `typecheck.py` so `resource-transition` infers
   `MovesResourceEffect` and `UpdatesLedgerEffect`.
3. Extend `source_map.py` and `lowering.py` to persist:
   - command-boundary declared effect names;
   - generated snapshot-capture lineage;
   - generated pointer-materialization lineage.
4. Extend `semantic_ir.py` to:
   - ingest the richer source-map lineage;
   - emit promoted effect entries;
   - validate the promoted-effect allowlist and structural correspondence.
5. Add focused tests for frontend inference, lowering provenance, Semantic IR
   projection, and negative validation cases.

## Acceptance Conditions

- the frontend effect taxonomy contains explicit promoted kinds for resource
  movement, ledger update, snapshot capture, and pointer materialization;
- `resource-transition` no longer collapses entirely into a generic
  `UsesCommandEffect`;
- compiled Workflow Lisp builds persist enough lineage to reconstruct promoted
  snapshot and pointer effects without parsing shell text or reports;
- shared Semantic IR exposes promoted
  `resource_transition`,
  `ledger_update`,
  `snapshot_capture`, and
  `pointer_materialization`
  entries where the selected lowering surfaces actually exist;
- promoted pointer effects remain representational metadata and do not weaken
  pointer-authority rules;
- generic `provider_call`, `command_call`, and `workflow_call` entries remain
  present and unchanged;
- no new runtime-native effect, no new hidden adapter, and no new pointer-as-
  authority escape hatch is introduced.

## Verification Plan

At architecture-drafting time, verify only the required artifacts and contracts
for this slice:

- the implementation architecture document exists and includes
  `Relationship To Existing Implementation Architectures`;
- the work-item context lists
  `docs/design/workflow_command_adapter_contract.md`
  as an authoritative input;
- the deterministic `check_commands.json` exists and parses;
- the draft bundle parses and points at real artifact paths.

Implementation-time verification belongs in the later execution plan and should
add targeted frontend and Semantic IR tests for the promoted effect classes.
