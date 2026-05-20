# Resource And Drain Library Implementation Architecture

## Scope

This design gap covers only the Stage 6 resource/drain tranche selected by the
current drain state:

- add frontend-owned `resource-transition`, `finalize-selected-item`, and
  `backlog-drain` forms;
- add the minimal compile-time workflow-ref resolution those forms require for
  selector, selected-item, and gap-drafter orchestration;
- add the minimal bounded loop substrate needed to lower `backlog-drain`
  through the existing shared `repeat_until` surface;
- add the `ItemCtx` / `DrainCtx` contract checks and derived layout helpers
  needed by the selected forms;
- keep resource movement behind a certified command adapter in this tranche,
  with explicit source maps, typed outputs, and fixture obligations.

Out of scope for this tranche:

- runtime-native queue/resource transaction effects;
- generic first-class `WorkflowRef[...]` authoring, runtime workflow loading,
  or module/import/export work;
- a public general-purpose `loop/recur` surface outside the compiler-owned
  drain lowering substrate;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, queue semantics, or state
  schema;
- report parsing, pointer-as-state, inline semantic Python/shell glue, or
  uncataloged helper wrappers.

## Design Constraints

The implementation must stay consistent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  Sections 7.7, 13, 19, 20, 29, 30, 31, 56, 58, 86, 87, 90, 91, 104, 107,
  and 108;
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  deferred-feature and non-goal boundaries, especially the continued ban on
  runtime-native queue/resource primitives and broad higher-order workflow
  surfaces in the MVP lineage;
- `docs/design/workflow_command_adapter_contract.md`, which is authoritative
  for any adapter-backed lowering, command-step registration, source-map
  behavior, error taxonomy, and runtime-native promotion decision;
- `docs/design/workflow_lisp_stdlib_lowering.md`,
  `docs/design/workflow_lisp_state_layout.md`,
  and `docs/design/workflow_lisp_source_map.md` for the Stage 5-derived
  lowering/layout/source-map contracts this slice builds on;
- `docs/design/workflow_language_design_principles.md`, especially the rules
  that state paths are derived, resource movement is a transition, provider
  decisions yield structured authority, and higher-order workflow composition
  is allowed only when checked;
- `specs/dsl.md`, `specs/io.md`, `specs/providers.md`, `specs/state.md`, and
  `specs/queue.md` for the shared runtime surfaces this slice must lower
  through unchanged;
- the Stage 1-5 frontend pipeline and package ownership already established in
  prior implementation architectures;
- the current shared workflow substrate, especially `call`,
  `repeat_until`, `output_bundle`, `variant_output`, `pre_snapshot`,
  `select_variant_output`, `publishes`, and `requires_variant`.

Additional constraints:

- keep the frontend in `orchestrator/workflow_lisp/` and shared runtime
  semantics under `orchestrator/workflow/`;
- keep typed bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- derive item/drain state and artifact paths from typed contexts rather than
  requiring authored string concatenation;
- reuse existing shared validation instead of generating YAML text or adding a
  second validator;
- keep workflow refs compile-time-only in v0.1;
- do not treat the empty `docs/steering.md` file in this checkout as implicit
  permission to widen scope.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/parser-syntax-frontend-core/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/typed-expressions-variant-proof/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`

### Decisions Reused

- Reuse the current staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation.
- Reuse `SourcePosition`, `SourceSpan`, `LispFrontendDiagnostic`,
  expansion-stack provenance, and `LoweringOriginMap` as the only frontend
  provenance channel.
- Reuse `FrontendTypeEnvironment`, Stage 2 proof scopes, Stage 3 structured
  provider/command result lowering, and Stage 5 phase stdlib lowering helpers.
- Reuse `EffectSummary` and the `defproc` call graph/effect propagation model
  rather than creating a second effect system for drain orchestration.
- Reuse `PhaseCtx`, `PhaseLayout`, generated fixed-output certified-adapter
  bindings, and the Stage 5 command-boundary contract model.
- Reuse `derive_structured_result_contract(...)` and the existing union-output
  helper shape already used by structured provider/command results and
  review-loop lowering.
- Reuse the authored-mapping lowering bridge to shared validation instead of
  inventing a frontend-only workflow executor.

### New Decisions In This Slice

- Add a dedicated resource/drain frontend layer with:
  `ItemCtx` / `DrainCtx` contract validation,
  derived item/drain layout helpers,
  `resource-transition`,
  `finalize-selected-item`,
  and `backlog-drain`.
- Keep workflow refs compile-time-only and restrict them to one
  compiler-supplied authority surface in this tranche:
  same-file workflow signatures plus explicitly registered precompiled imported
  bundles, usable only through the compiler-owned stdlib operand positions
  `:selector`, `:run-item`, and `:gap-drafter`.
- Add a compiler-owned drain loop substrate that lowers to `repeat_until`
  without exposing a general public `loop/recur` surface yet.
- Start `resource-transition` behind one named certified command adapter,
  `apply_resource_transition`, and explicitly defer runtime-native promotion.
- Keep `Provider` and `Prompt` out of ordinary workflow-boundary transport:
  provider-bearing workflow refs lower only through compile-time extern
  rebinding and generated specialized aliases/imported bundles, never through
  ordinary `call` inputs.
- Extend workflow signatures and call lowering to allow union workflow returns
  when the boundary can be projected through the existing structured-result
  contract machinery and shared validation seam.
- Make `orchestrator/workflow_lisp/contracts.py` the owned boundary-contract
  module for this slice's union workflow-return projection, with
  `workflows.py` and `lowering.py` consuming that metadata instead of
  inventing parallel projection logic.
- Treat the shorthand Stage 6 form examples in Sections 29-31 as incomplete
  surface summaries when they conflict with the end-to-end examples in
  Sections 90-91:
  this slice follows the richer end-to-end calling conventions where needed to
  preserve typed handoff and avoid hidden ambient state.

### Conflicts Or Revisions

The current Stage 3/5 implementation still assumes:

- workflow refs are not a frontend surface;
- workflow returns must be records at the call boundary;
- `backlog-drain` and `finalize-selected-item` do not yet exist;
- the only compiler-owned loop lowering is the phase-review loop.

This slice revises those assumptions narrowly:

- workflow refs remain non-runtime values, but selected stdlib forms may now
  resolve named workflows only through a compiler-supplied workflow-ref
  environment and signature-check them against one compiler-known role
  contract;
- provider-bearing workflow refs may not widen ordinary `call` boundary
  semantics:
  the compiler must instead specialize the chosen same-file alias or imported
  bundle with an extern rebinding plan before ordinary call lowering;
- `WorkflowSignature.return_type_ref` must expand from record-only to
  `RecordTypeRef | UnionTypeRef`, with union lowering confined to the existing
  structured-result/output-contract machinery rather than a new shared runtime
  type system;
- `repeat_until` reuse extends from review loops to drain orchestration through
  one compiler-owned accumulator plan;
- the resource/drain library becomes the only new owner of item/drain context
  validation, resource-transition adapter registration, workflow-ref authority
  resolution, and the bounded union workflow-boundary projection changes in
  `contracts.py`.

The full design text also contains one shorthand inconsistency:

- Section 30 illustrates `finalize-selected-item` with only
  `:ctx`, `:selected`, `:plan`, and `:implementation`;
- Section 90's end-to-end selected-item example additionally threads
  `:queue-transition` and `:roadmap`.

This slice treats Section 90 as the authoritative Stage 6 calling convention,
because finalization otherwise has no typed carrier for the earlier queue move
or roadmap outcome and would force hidden ambient state.

This is a frontend-local revision only. It does not redefine shared concepts
such as Core Workflow AST, Semantic Workflow IR, TypeCatalog, SourceMap,
pointer authority, or variant proof.

## Ownership Boundaries

This slice owns:

- frontend-local contract validation for authored `ItemCtx` and `DrainCtx`
  records;
- deterministic derivation of item/drain bundle paths, temp paths, summary
  targets, iteration roots, and named resource/drain state slots from those
  contexts;
- frontend AST, typing, diagnostics, and lowering for
  `resource-transition`,
  `finalize-selected-item`,
  and `backlog-drain`;
- compile-time workflow-ref authority assembly and role checking for the
  selected stdlib operands;
- compile-time provider/prompt extern rebinding for workflow-ref-specialized
  aliases and imported bundles;
- the compiler-owned drain loop accumulator plan and `repeat_until` lowering;
- the static `apply_resource_transition` certified-adapter binding template and
  backend script for this tranche;
- union workflow-return boundary contract derivation in
  `orchestrator/workflow_lisp/contracts.py` plus call-boundary projection
  through existing structured-result contract machinery;
- source-map expansion frames for generated resource/drain steps and helper
  workflows;
- focused tests and fixtures for context contracts, adapter registration,
  workflow-ref checks, union-return call lowering, drain-loop lowering, and
  runtime-equivalence regressions.

This slice intentionally does not own:

- construction syntax for `phase-ctx` / `item-ctx` / `drain-ctx`;
- generic module/import/export or public higher-order workflow-ref transport;
- runtime-native queue/resource transactions or ledger primitives;
- generic public `loop/recur` authoring beyond the drain lowering substrate;
- report parsing, pointer materialization policy, path-safety policy,
  provider execution semantics, or shared runtime state persistence;
- redesign of shared queue DSL semantics or the call-step substrate itself.

## Proposed Package Boundary

Extend the existing frontend package with one resource-context module, two
bounded stdlib modules, and one adapter backend:

```text
orchestrator/workflow_lisp/
  __init__.py
  adapters/
    __init__.py
    apply_resource_transition.py
  compiler.py
  contracts.py
  diagnostics.py
  drain_stdlib.py
  expressions.py
  lowering.py
  macros.py
  phase.py
  phase_stdlib.py
  resource.py
  resource_stdlib.py
  typecheck.py
  workflows.py
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_resource_stdlib.py
  test_workflow_lisp_drain_stdlib.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_lowering.py
  test_lisp_frontend_autonomous_drain_runtime.py
  test_neurips_steered_backlog_runtime.py
  fixtures/workflow_lisp/valid/resource_stdlib_transition.orc
  fixtures/workflow_lisp/valid/resource_stdlib_finalize_selected_item.orc
  fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc
  fixtures/workflow_lisp/invalid/item_ctx_contract_invalid.orc
  fixtures/workflow_lisp/invalid/drain_ctx_contract_invalid.orc
  fixtures/workflow_lisp/invalid/resource_transition_uncertified_adapter.orc
  fixtures/workflow_lisp/invalid/backlog_drain_workflow_ref_signature_invalid.orc
  fixtures/workflow_lisp/invalid/backlog_drain_union_call_boundary_invalid.orc
```

Responsibilities:

- `resource.py`
  - define `ItemCtx` / `DrainCtx` contract checkers;
  - derive deterministic `ItemLayout` / `DrainLayout` helper records;
  - validate required relpath roles for ledger, manifest, item state, drain
    state, and summary targets without expanding the global prelude again.
- `resource_stdlib.py`
  - define frontend-local dataclasses for
    `ResourceTransitionExpr`,
    `FinalizeSelectedItemExpr`,
    `ResourceTransitionSpec`,
    and finalization lowering plans;
  - centralize the full certified-adapter metadata for
    `apply_resource_transition`, including input contract, output type,
    declared effects, path-safety expectations, source-map behavior,
    fixture/negative-fixture identifiers, declared state writes, artifact
    contracts, stable failure taxonomy, and owner-module identity;
  - define typed normalization helpers for completed vs blocked selected-item
    outcomes.
- `drain_stdlib.py`
  - define `WorkflowRefAuthoritySource`, `WorkflowRefEnvironment`,
    `ResolvedWorkflowRef`, `WorkflowRefRequirement`,
    `WorkflowExternRebindingPlan`, `WorkflowRefCallPlan`,
    `DrainLoopPlan`, and the compiler-known selector/item/gap calling
    conventions;
  - centralize compile-time workflow-ref resolution, extern rebinding-plan
    derivation, and drain-loop plan generation shared by `typecheck.py` and
    `lowering.py`;
  - reject any target that cannot be satisfied by same-file lowering metadata
    or an explicitly registered imported-bundle handle.
- `expressions.py`
  - elaborate the new stdlib forms and their keyword sections;
  - keep unsupported generic workflow-ref or public loop syntax rejected.
- `typecheck.py`
  - validate `ItemCtx` / `DrainCtx` contract use;
  - validate workflow-ref role signatures, union-return eligibility, extern
    rebinding eligibility, and drain-loop result compatibility;
  - attach effect summaries for resource/drain forms and adapter-backed
    transitions.
- `workflows.py`
  - expand workflow signatures to allow record or union returns;
  - keep provider/prompt extern handling authoritative and expose the callee
    extern requirements that workflow-ref specialization consumes;
  - register the static `apply_resource_transition` certified adapter when
    needed, reject shadowing or uncertified substitutions, and validate that
    the generated binding presents the complete certified-adapter metadata
    surface required by this repo's frontend-owned adapter boundary;
  - own the lowering bridge from resolved workflow-ref targets to legal
    generated call aliases/imported bundle handles.
- `contracts.py`
  - extend `derive_workflow_signature_contracts(...)` so union workflow returns
    project through one bounded `WorkflowUnionBoundaryProjection` metadata
    shape;
  - keep ordinary scalar/relpath/record boundary flattening rules authoritative
    for non-workflow-ref calls;
  - reject any attempted provider/prompt boundary projection outside the
    compiler-owned extern rebinding path.
- `lowering.py`
  - lower `resource-transition` to an ordinary typed command step backed by
    the certified adapter plus structured output validation;
  - lower `finalize-selected-item` through match/proof plus typed bundle
    publication;
  - lower `backlog-drain` through `repeat_until`, `call`, `match`, and
    post-loop normalization;
  - specialize workflow-ref-generated aliases/imported bundles with the
    compile-time extern rebinding plan before emitting ordinary `call` steps;
  - lower union workflow returns and call outputs through the existing
    structured-result contract helpers, `WorkflowUnionBoundaryProjection`, and
    `requires_variant` proof surfaces.
- `compiler.py`
  - orchestrate resource/drain contract validation, workflow-ref resolution,
    imported-bundle registration, extern specialization, adapter registration,
    and shared-validation handoff.
- `adapters/apply_resource_transition.py`
  - implement the stable adapter backend for resource/queue movement and ledger
    update under the certified command-adapter contract;
  - own the stable command target
    `python -m orchestrator.workflow_lisp.adapters.apply_resource_transition`
    and the adapter's fixture-backed behavior;
  - emit one top-level typed `ResourceTransitionResult` bundle with stable
    error codes, declared state writes only, and no ambient report parsing or
    pointer-as-state side outputs.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/definitions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- shared workflow validation/runtime modules under `orchestrator/workflow/`

## Data Model

### `ItemCtx` / `DrainCtx` Contracts

This slice keeps the Stage 5 `RunCtx` contract unchanged and layers two new
context checkers on top:

- `ItemCtx`
  - `run: RunCtx`
  - `item-id: String`
  - `state-root: relpath under state`
  - `artifact-root: relpath under artifacts`
  - `ledger: relpath under state`
- `DrainCtx`
  - `run: RunCtx`
  - `state-root: relpath under state`
  - `manifest: relpath under state`
  - `ledger: relpath under state`

The checker validates field roles, relpath roots, and deterministic layout
eligibility. It does not require literal type names such as
`Path.state-existing`; authored path definitions may satisfy the role as long
as the contract is equivalent.

Derived helper records:

- `ItemLayout`
  - `item_state_bundle_path`
  - `item_temp_bundle_path`
  - `outcome_bundle_path`
  - `summary_target_path`
  - `phase_root_prefix`
- `DrainLayout`
  - `run_state_bundle_path`
  - `run_state_temp_bundle_path`
  - `iteration_root_prefix`
  - `summary_target_path`
  - `gap_request_path`

These helpers remain frontend-local lowering aids. They are not new shared IR
types.

### Resource Transition Contract

`resource-transition` returns the authored `ResourceTransitionResult` record
from the full design and lowers through one static certified adapter binding:

- adapter name: `apply_resource_transition`
- owner module: `orchestrator.workflow_lisp.adapters.apply_resource_transition`
- stable command:
  `python -m orchestrator.workflow_lisp.adapters.apply_resource_transition`
- output type name: `ResourceTransitionResult`
- declared effects:
  `resource_transition`,
  `ledger_update`
- source-map behavior:
  `step`, with the generated command step and its structured-output validation
  mapped back to the authored `resource-transition` span plus the stdlib
  expansion frame

The adapter binding must carry the complete frontend-owned certified-adapter
metadata surface already used elsewhere in the Lisp frontend:

- typed input contract
- typed output signature
- declared effects
- path-safety expectations
- source-map behavior
- fixture identifiers
- negative-fixture identifiers
- declared state writes
- artifact contracts
- stable error taxonomy
- owner-module identity

The adapter input contract is a typed record lowered from authored operands:

- transition name
- resource identifier or authored resource path
- `from` queue/state
- `to` queue/state
- ledger path
- item/drain state roots when needed for deterministic path derivation
- ledger event enum/string

Declared state writes:

- move exactly one resource from the authored `from` queue/state location to
  the authored `to` queue/state location;
- append or update exactly one event in the declared ledger path;
- materialize only the generated structured-result output bundle for
  `ResourceTransitionResult`.

Artifact contracts:

- the adapter publishes no markdown reports, pointer files, or sidecar
  artifacts;
- the only authored semantic output is the validated
  `ResourceTransitionResult` bundle consumed by ordinary structured-result
  lowering;
- `new-path` must resolve inside the destination queue/state root derived from
  the typed input contract.

Path-safety expectations:

- all file operands must remain workspace-relative and refine to the declared
  `state` roots supplied by `ItemCtx` or `DrainCtx`;
- the adapter may read and write only the authored source queue path, the
  authored destination queue path, the declared ledger path, and the generated
  structured-result output path;
- absolute paths, parent-directory escapes, artifact-root writes, ad hoc temp
  files, and pointer-materialization side effects are rejected before semantic
  state is committed.

Fixture coverage obligations:

- `fixture_ids`
  - `resource_transition_move_success`
  - `resource_transition_create_destination_success`
  - `resource_transition_ledger_append_success`
- `negative_fixture_ids`
  - `resource_transition_path_escape`
  - `resource_transition_missing_source`
  - `resource_transition_destination_conflict`
  - `resource_transition_ledger_update_failed`
  - `resource_transition_invalid_result`

Stable hard-failure codes must include at least:

- `resource_transition_path_escape`
- `resource_transition_missing_source`
- `resource_transition_destination_conflict`
- `resource_transition_ledger_update_failed`
- `resource_transition_invalid_result`

### Finalization Contract

`finalize-selected-item` owns the typed fan-in for the selected-item phase
stack. In this slice its authored surface is the richer example-driven one:

```text
:ctx
:selected
:queue-transition
:roadmap
:plan
:implementation
```

The form returns `SelectedItemResult` and may trigger one terminal resource
transition if the selected item must leave `in-progress` for a final queue.

Frontend-local lowering metadata:

- `FinalizeSelectedItemSpec`
  - typed selected-item context and layout
  - normalized queue-transition result
  - typed roadmap outcome handle
  - typed plan result
  - typed implementation result
  - result summary target
  - final queue routing policy

### Workflow Ref Roles

This slice does not add a public `WorkflowRef[...]` type parser or runtime
value surface. Instead it adds compile-time-only workflow-ref role resolution
for compiler-owned stdlib operands.

Frontend-local types:

- `WorkflowRefAuthoritySource`
  - `same_file`
  - `registered_imported_bundle`
- `WorkflowRefEnvironment`
  - `same_file_signatures_by_name`
  - `registered_imported_refs_by_name`
  - `extern_requirements_by_target`
- `WorkflowRefRequirement`
  - role name:
    `selector`,
    `run_item`,
    or `gap_drafter`
  - required parameter shape
  - allowed return type shape
  - required effect atoms
- `ResolvedWorkflowRef`
  - authored symbol name
  - authority source
  - resolved workflow signature
  - effect summary
  - lowered alias / imported bundle handle
  - extern requirement metadata
  - boundary projection metadata

Authority surface in this slice:

- same-file workflows already present in `WorkflowCatalog`;
- compiler-supplied imported workflow bundles passed into the compile API with
  stable alias names, signatures, effect summaries, and extern requirements;
- no authored import/module syntax, runtime filesystem lookup, or runtime
  workflow loading.

The compiler must reject any workflow-ref symbol that resolves nowhere or
resolves to more than one authority source.

Role contracts in this slice:

- `selector`
  - accepts `DrainCtx` plus the authored providers operand when present;
  - returns a union `SelectionResult`.
- `run_item`
  - accepts `ItemCtx`, the selected branch payload, and providers;
  - returns a union `SelectedItemResult`.
- `gap_drafter`
  - accepts `DrainCtx`, the gap branch payload, and providers;
  - returns a record or union result that the drain normalizer can convert to
    one continue branch or one blocked terminal branch.

Extern transport rule for these roles:

- `Provider` and `Prompt` remain illegal ordinary workflow-boundary values;
- the `:providers` operand is treated as a compile-time carrier for extern leaf
  references, not as a flattened `call` input bundle;
- `drain_stdlib.py` derives a `WorkflowExternRebindingPlan` that maps the
  callee's declared provider/prompt extern names to field paths on the authored
  providers record;
- `workflows.py` and `compiler.py` specialize the selected alias/imported
  bundle with that rebinding plan before `lowering.py` emits the ordinary
  `call` step;
- if a role target requires provider/prompt externs that the selected providers
  record cannot satisfy exactly, compilation fails before lowering.

### Drain Loop Substrate

The public `loop/recur` surface remains deferred. This slice instead adds one
compiler-owned loop plan used only by `backlog-drain`.

Frontend-local types:

- `DrainLoopPlan`
  - `max_iterations_expr`
  - `accumulator_type`
  - selector/item/gap call plans
  - terminal normalization plan
- `DrainAccumulator`
  - `items_processed: Int`
  - `last_run_state_path: relpath | None`
  - `blocked_stage: String | None`
  - `blocked_reason: String | None`
  - `blocked_summary_path: relpath | None`
  - `loop_status: enum`

`loop_status` is a frontend-local lowering control field, not a shared runtime
artifact contract.

### Union Workflow Boundary Projection

The selected forms need union-returning workflows. This slice therefore expands
workflow-boundary metadata without inventing a new shared runtime surface.

Frontend-local types:

- `WorkflowUnionBoundaryProjection`
  - discriminant output contract
  - shared field output contracts
  - variant field output contracts
  - call-site proof requirements

Implementation rule:

- keep the authored workflow return type authoritative as a union;
- derive boundary outputs in `contracts.py` from the same structured-result
  contract payload used for `provider-result` / `command-result`;
- surface the discriminant and field outputs as ordinary workflow outputs and
  ordinary call-step artifacts;
- keep the projection metadata as the single source of truth consumed by
  `workflows.py` when building workflow signature contracts and by
  `lowering.py` when materializing call output refs;
- require `match`-based proof before any variant-only field is referenced
  downstream.

No runtime-loaded workflow ref, no new shared IR union transport object, and
no YAML-text intermediate are introduced.

## Typing And Lowering Model

### `resource-transition`

Typechecking requirements:

- `:ctx` must resolve to `ItemCtx` or another explicitly supported resource
  scope owned by this slice;
- `:from` and `:to` must resolve to compatible queue/location enum values;
- `:ledger` must resolve to a relpath under `state`;
- the declared return type must resolve to `ResourceTransitionResult`;
- the active command binding must be a `CertifiedAdapterBinding` whose
  `output_type_name` is exactly `ResourceTransitionResult`.

Lowering shape:

- one generated `command` step using the certified adapter;
- one `output_bundle` contract for `ResourceTransitionResult`;
- optional `publishes` entries for any result artifact refs that later forms
  consume;
- full source-map entry from the stdlib form to the generated command step and
  bundle validation.

This slice must not lower `resource-transition` to inline `python -c`,
`bash -c`, or a shell wrapper.

### `finalize-selected-item`

Typechecking requirements:

- plan and implementation operands must resolve to typed phase results already
  legal under the Stage 5 phase stdlib;
- queue-transition must resolve to `ResourceTransitionResult`;
- any terminal resource move used during finalization must also resolve through
  the certified adapter contract;
- the form must type to the authored `SelectedItemResult` union.

Lowering shape:

- `match` over the typed phase results and any roadmap discriminator;
- zero or one additional generated resource-transition command step on the
  terminal route that moves the item out of `in-progress`;
- one generated bundle-materialization step for the authoritative selected-item
  outcome;
- one generated summary-publication step;
- typed terminal outputs that reuse the same structured-result contract
  machinery as other union-valued forms.

### `backlog-drain`

Typechecking requirements:

- `:ctx` must resolve to `DrainCtx`;
- `:selector`, `:run-item`, and `:gap-drafter` must resolve to named workflows
  that satisfy the compiler-known role contracts;
- `:max-iterations` must resolve to `Int`;
- the form must type to the authored `DrainResult` union.

Lowering shape:

- one compiler-owned `repeat_until` frame with an explicit accumulator;
- inside the loop body:
  - call selector;
  - match on `SelectionResult`;
  - `EMPTY` -> set terminal loop status and stop;
  - selected branch -> derive `ItemCtx`, call selected-item workflow, match on
    `SelectedItemResult`, update accumulator;
  - gap branch -> call gap-drafter, normalize continue vs blocked behavior,
    update accumulator;
- one post-loop typed normalization step that converts the accumulator into the
  authored `DrainResult`.

The loop substrate stays compiler-owned in this tranche. No user-authored
general `loop/recur` form becomes legal outside this lowering path.

### Union Workflow Returns And Calls

This slice widens workflow signatures from record-only to
`RecordTypeRef | UnionTypeRef`.

Typechecking changes:

- `call` of a union-returning workflow becomes legal;
- the resulting expression type is the authored union type;
- variant-only field access still requires proof via `match`, reusing the
  Stage 2 proof model.

Lowering changes:

- workflow output contracts for union returns are synthesized from
  `derive_structured_result_contract(...)` and the existing union-output helper
  shape;
- call-step output refs point at the generated discriminant/shared/variant
  field artifacts already surfaced by the callee;
- generated downstream references to variant-only call outputs carry
  `requires_variant` where the shared DSL needs explicit proof.

This revision is intentionally narrow:

- it applies to compile-time-known workflows validated in the same frontend
  pipeline;
- it does not introduce dynamic workflow loading;
- it does not change shared runtime call semantics beyond providing ordinary
  declared outputs.

### Command Adapter And Runtime-Native Promotion Policy

This slice adopts the full-design recommendation from Section 107:

- start with one certified adapter for `resource-transition`;
- measure the remaining semantic pain;
- promote to a runtime-native effect only if Stage 6 evidence shows repeated
  atomicity/resume/source-map limitations that the adapter cannot satisfy.

No runtime-native promotion is part of this tranche's implementation contract.

## Shared Workflow Handoff And Source Maps

The selected forms still hand off through the current authored workflow mapping
bridge:

- typed forms lower to authored mappings compatible with
  `elaborate_surface_workflow(...)`;
- shared validation continues to run on ordinary provider steps, command
  steps, `call`, `repeat_until`, `publishes`, `output_bundle`, and
  `variant_output` surfaces;
- any shared-validation failure on generated resource/drain steps remaps
  through `LoweringOriginMap` back to the authored stdlib form span.

Required source-map coverage:

- every generated resource-transition command step;
- every generated finalization match/projection step;
- every generated drain loop frame, selector/item/gap call, and post-loop
  normalization step;
- any generated union-return workflow boundary output projection.

This slice does not redefine the shared `SourceMap` contract. It extends the
frontend-local origin coverage so later shared source-map work has complete
inputs.

## Diagnostics

Add focused frontend diagnostics for:

- `item_context_invalid`
- `drain_context_invalid`
- `resource_transition_contract_invalid`
- `resource_transition_uncertified_adapter`
- `workflow_ref_unknown`
- `workflow_ref_signature_invalid`
- `workflow_ref_return_type_invalid`
- `workflow_union_boundary_invalid`
- `backlog_drain_contract_invalid`
- `backlog_drain_name_mismatch`
- `finalize_selected_item_contract_invalid`

These remain `LispFrontendDiagnostic` records with ordinary spans, form paths,
and expansion stacks.

## Test Strategy

### Frontend Unit Tests

- `ItemCtx` / `DrainCtx` contract acceptance and rejection;
- expression elaboration for the three new stdlib forms;
- workflow-ref resolution for valid and invalid selector/item/gap bindings;
- workflow-ref authority-source ambiguity and missing-target rejection;
- provider/prompt extern rebinding-plan acceptance and rejection for
  workflow-ref-specialized calls;
- adapter-registration and shadowing rules for `apply_resource_transition`;
- union workflow-signature acceptance plus existing invalid boundary rejection
  coverage where union projection is not legal.

### Lowering And Shared-Validation Tests

- `resource-transition` lowers to a certified adapter command step plus typed
  `output_bundle`;
- `finalize-selected-item` lowers through typed terminal normalization and
  summary publication without inline scripts;
- `backlog-drain` lowers through `repeat_until`, `call`, `match`, and
  post-loop result normalization;
- union-returning workflow calls validate through shared validation without
  YAML text or new runtime primitives;
- the union boundary projection and workflow-ref-specialized extern rebinding
  stay coherent across `contracts.py`, `workflows.py`, and `lowering.py`.

### Runtime And Regression Tests

- the autonomous drain fixture runtime continues to accept architecture-draft
  bundles and drain-state transitions;
- the NeurIPS steered backlog runtime smoke continues to cover queue movement,
  selected-item finalization, gap drafting, and downstream blocked/completed
  outcomes;
- phase stdlib, structured-result, macro, and `defproc` regressions still
  pass.

## Implementation Sequence

1. Add `ItemCtx` / `DrainCtx` contract checkers and layout helpers.
2. Add `resource-transition` elaboration, typing, adapter registration, and
   lowering.
3. Add `finalize-selected-item` typing and lowering on top of the resource
   transition and phase stdlib surfaces.
4. Expand workflow signatures plus `contracts.py` boundary projection for union
   workflow returns using existing structured-result contract helpers.
5. Add compile-time workflow-ref authority resolution, extern rebinding
   specialization, and the compiler-owned drain loop substrate.
6. Lower `backlog-drain` through `repeat_until` and validate it through shared
   validation.
7. Add focused fixtures and runtime-equivalence regressions.

## Acceptance Conditions

- `ItemCtx` and `DrainCtx` compile only when their relpath roles satisfy the
  selected slice's deterministic layout rules;
- `resource-transition` lowers only through the named certified adapter and
  never through inline semantic shell/Python glue;
- `finalize-selected-item` replaces handwritten selected-item fan-in with typed
  match/projection logic and authoritative structured outcome publication;
- `backlog-drain` lowers through a bounded compiler-owned `repeat_until`
  substrate with explicit typed accumulator state;
- workflow refs remain compile-time-only, are legal only in the selected
  stdlib operand positions, and resolve only from the compiler-supplied
  workflow-ref environment;
- provider/prompt-bearing workflow refs compile only through exact
  compile-time extern rebinding into specialized aliases/imported bundles and
  never widen ordinary workflow-boundary transport;
- union-returning selector/item/drain workflows can cross the call boundary
  through generated structured-result outputs and proof-aware call lowering,
  without inventing a second runtime type transport;
- shared validation continues to see only ordinary supported workflow surfaces;
- no runtime-native resource transition effect is introduced in this tranche;
- phase stdlib, structured-result, macro, and `defproc` behavior remains
  regression-tested.

## Verification Plan

The deterministic verification contract for this slice is the exact ordered
command list in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`.
Downstream planning and implementation should treat that file as the required
check suite:

```json
[
  "python -m pytest --collect-only tests/test_workflow_lisp_resource_stdlib.py tests/test_workflow_lisp_drain_stdlib.py -q",
  "python -m pytest tests/test_workflow_lisp_resource_stdlib.py -q",
  "python -m pytest tests/test_workflow_lisp_drain_stdlib.py -q",
  "python -m pytest tests/test_workflow_lisp_workflows.py tests/test_workflow_lisp_structured_results.py tests/test_workflow_lisp_lowering.py -q",
  "python -m pytest tests/test_workflow_lisp_phase_stdlib.py tests/test_workflow_lisp_procedures.py -q",
  "python -m pytest tests/test_lisp_frontend_autonomous_drain_runtime.py -q",
  "python -m pytest tests/test_neurips_steered_backlog_runtime.py -q"
]
```

These commands cover:

- collect-only on the new resource/drain test modules;
- focused stdlib typing, lowering, and workflow-ref coverage;
- union workflow-boundary and structured-result regressions;
- phase-stdlib and `defproc` regression safety for the reused substrate;
- one autonomous-drain smoke and one NeurIPS backlog smoke that exercise the
  translated drain path end to end.
