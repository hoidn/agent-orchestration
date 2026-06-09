# Workflow Lisp Promoted-Entry Hidden Reusable-Call Binding Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-promoted-entry-hidden-reusable-call-binding`
Target design: `docs/design/workflow_lisp_key_migration_parity_architecture.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice covers exactly the selected promoted-entry prerequisite gap:

- define how a promoted Workflow Lisp entry workflow satisfies required
  internal `RunCtx` / `PhaseCtx` call bindings without exposing those values as
  public workflow inputs;
- add one compiler-owned hidden-binding route for reusable internal workflow
  calls, including `resume-or-start :start` branches that call union-returning
  reusable wrappers;
- make the executable proof route explicit so the promoted-entry bootstrap
  fixture passes because runtime-owned hidden bindings satisfy the internal call
  contract, not because imported `PhaseCtx` defaults happen to exist;
- reuse the existing generated-internal-input, managed-write-root, workflow
  call-lowering, and phase-layout substrates instead of inventing a new runtime
  executor path.

Out of scope for this slice:

- redefining the public promoted-entry workflow boundary, which is already
  hidden enough for this prerequisite and is treated here as a reused decision;
- general `ItemCtx` / `DrainCtx` entry construction, new author-facing
  context-construction forms, or a broader entrypoint-context-bootstrap
  redesign;
- removing synthetic top-level `PhaseCtx` defaults globally from
  `orchestrator/workflow_lisp/contracts.py`;
- changing `resume-or-start`, reusable-state summaries, review-loop lowering,
  wrapper union construction, command-result bundle ownership, or migration
  promotion policy beyond reusing their existing decisions;
- new runtime-native effects, new command adapters, report parsing,
  pointer-authority exceptions, or family-specific review-loop workarounds;
- widening the solution into standalone imported-bundle transport for hidden
  context metadata outside the linked `compile_stage3_entrypoint(...)` compile
  graph used by the prerequisite proof.

This is a bounded implementation architecture for one selected prerequisite
gap. It does not replace the parent migration architecture or reopen the full
Workflow Lisp frontend contract.

## Problem Statement

The selected target migration design already narrowed the remaining blocker:

- the reusable-result wrapper prerequisite is complete;
- promoted entry public inputs are already expected to exclude
  `phase-ctx__*`, `run-id`, `state-root`, `artifact-root`, and managed
  write-root inputs;
- the remaining missing capability is the hidden reusable-call binding that
  satisfies required internal context parameters once a promoted entry actually
  calls the reusable wrapper.

The current checkout still falls short in four concrete ways:

1. `workflow_public_input_contracts(...)` and the command-result parity slice
   already hide managed write roots, but runtime/public input helpers do not
   yet model a second class of runtime-owned generated inputs for context
   bootstrap.
2. `_apply_workflow_input_defaults(...)` in
   `orchestrator/workflow_lisp/contracts.py` still synthesizes convenience
   defaults for top-level imported `PhaseCtx` leaves, which allows compile and
   runtime success without proving a runtime-owned hidden binding route.
3. `CallExpr` typecheck and `_lower_call_expr(...)` still treat missing
   `RunCtx` / `PhaseCtx` bindings as either explicit authored bindings or
   ordinary default omission; there is no compiler-owned third path for a
   promoted entry workflow.
4. The current promoted-entry fixture in
   `tests/test_workflow_lisp_key_migrations.py` proves that public inputs are
   hidden, but it does not yet prove that the first reusable internal call is
   satisfied by runtime-owned bindings rather than by imported defaulted
   `PhaseCtx` fields.

The gap is therefore not “invent context records” and not “hide more public
inputs.” The missing piece is one explicit compiler/runtime-owned route that
binds required internal `RunCtx` / `PhaseCtx` leaf inputs on promoted-entry
calls and one proof fixture that shows the reusable-wrapper path actually uses
that route.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
  - `Required Changes By Gap`
  - `Newly Exposed Prerequisite Gaps`
  - `Required Generic .orc Support`
  - `Dependencies And Sequencing`
  - `Evidence And Implementation Boundaries`
  - `Success Criteria`
  - `Stop / Revise Criteria`
- `docs/design/workflow_lisp_frontend_specification.md`
  - Sections 14, 16, 19, 20, 21, 28, 45, 50, 52, 59, 61, 65, 74, 95, 103
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/lisp_workflow_drafting_guide.md`
- `specs/dsl.md`
- `specs/state.md`
- `state/LISP-MIGRATION-PARITY-DRAIN/progress_ledger.json`
- `state/LISP-MIGRATION-PARITY-DRAIN/drain/run_state.json`
- `docs/steering.md`

The slice must preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime execution/state authority under `orchestrator/workflow/`;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- reuse the existing staged pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation -> executable runtime;
- treat runtime-owned hidden context binding as a generated internal-input
  concern, not as a new public workflow parameter surface;
- keep `resume-or-start` on the already-selected typed reusable-state and
  certified-adapter contract; hidden context binding must not become a shortcut
  around that contract;
- keep command-boundary rules from
  `docs/design/workflow_command_adapter_contract.md` authoritative even though
  this slice should not add new adapter behavior;
- do not treat the empty `docs/steering.md` file as permission to widen scope.

`docs/design/workflow_command_adapter_contract.md` remains authoritative here
because the selected promoted-entry proof still traverses `resume-or-start` and
command-backed structured results. This slice must not “solve” missing context
binding by adding opaque scripts, report parsing, or inline semantic glue.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- Full coherence inventory reviewed via:
  `state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/existing-architecture-index.md`
- Slices read closely because they directly govern this gap:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resume-or-start-reusable-state-validation/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/resource-drain-library/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/remaining-neurips-migration-experiment/implementation_architecture.md`
  - `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-command-result-compiler-owned-bundle-paths/implementation_architecture.md`
  - `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-defworkflow-input-default-parity/implementation_architecture.md`
  - `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`
  - `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-reusable-result-wrapper-construction/implementation_architecture.md`

### Decisions Reused

- Reuse Stage 5 `RunCtx`, `PhaseCtx`, and `with-phase` as the only context and
  phase-layout authority for this slice; no second context model is introduced.
- Reuse the command-result parity slice’s public/internal compiled-workflow
  input split and its rule that runtime-owned generated inputs remain off the
  public API.
- Reuse `GeneratedInternalInput.reason` in
  `orchestrator/workflow_lisp/contracts.py` and the existing
  `internal_generated_input_reasons` plumbing in `lowering.py` instead of
  inventing a parallel hidden-input registry.
- Reuse `_managed_write_root_requirements_for_callable(...)`,
  `_managed_write_root_binding_step(...)`, and the general call-lowering path
  as the model for compiler-owned call-site transport.
- Reuse Stage 5 `resume-or-start` and the reusable-state validator/loader
  route unchanged.
- Reuse the reusable-result wrapper slice’s decision that ordinary `.orc` code
  can already construct the required wrapper unions; this slice does not reopen
  wrapper authoring.
- Reuse the source-map/runtime-lineage slice’s requirement that generated
  hidden bindings remain source-mapped and explainable.

### New Decisions In This Slice

- Add one new generated-internal-input reason,
  `runtime_owned_context`, for promoted-entry bootstrap values.
- Add one compiler-owned eligibility contract for omitted internal
  `RunCtx` / `PhaseCtx` bindings on promoted-entry workflow calls.
- Make hidden promoted-entry context binding explicit in lowered `call.with`
  entries; success must no longer depend on imported defaulted `PhaseCtx`
  omission.
- Keep the first implementation slice intentionally narrow:
  it supports linked `.orc` workflows compiled in the same
  `compile_stage3_entrypoint(...)` graph, with `PhaseCtx` eligibility derived
  from the callee’s own Workflow Lisp body rather than from a new user-facing
  annotation.

### Conflicts Or Revisions

The input-default parity slice intentionally kept synthetic top-level `PhaseCtx`
defaults as a compatibility fallback. This slice narrows that assumption:

- synthetic defaults may remain available as a convenience surface for
  isolated compile/dry-run fixtures;
- they no longer count as parity evidence for promoted-entry bootstrap;
- promoted-entry lowering must prefer explicit runtime-owned hidden bindings
  over default omission when an eligible internal reusable call requires
  `RunCtx` or `PhaseCtx`.

The command-result parity slice also framed generated internal inputs primarily
as managed write roots. This slice revises that boundary narrowly:

- managed write roots remain unchanged;
- a second generated-internal-input reason is added for runtime-owned context
  transport;
- public input helpers and runtime-owned entry binding must handle both
  internal-input classes without exposing either to users.

No shared concepts are redefined. Core Workflow AST, Semantic IR, Executable
IR, TypeCatalog, SourceMap, pointer authority, variant proof, and command-step
semantics remain with their existing owners.

## Ownership Boundaries

This slice owns:

- compile-time eligibility detection for promoted-entry hidden context binding
  in linked Workflow Lisp workflows;
- promoted-entry call typecheck/lowering rules that allow eligible omitted
  `RunCtx` / `PhaseCtx` bindings and synthesize explicit hidden `call.with`
  entries;
- runtime-owned entry binding for hidden context inputs, including deterministic
  allocation, resume-stable reuse, and override rejection;
- the public/runtime input helper changes needed so hidden context inputs stay
  internal;
- source-map/build-artifact coverage for generated context-binding inputs;
- focused fixtures and tests proving the dedicated promoted-entry
  reusable-wrapper path.

This slice intentionally does not own:

- new author-facing context-construction syntax;
- generalized context bootstrap for arbitrary imported precompiled bundles
  outside the linked entrypoint compile graph;
- redesign of `resume-or-start`, reusable-state writer/validator behavior,
  wrapper union construction, or review-loop specialization;
- changing workflow runtime call semantics beyond compiler-owned hidden input
  binding and runtime-owned entry allocation;
- new command adapters, runtime-native effects, or family-specific wrappers.

## Current Checkout Facts

The current checkout already contains most of the substrate this slice should
reuse:

- `phase.py` and Stage 5 fixtures already make `RunCtx` / `PhaseCtx` ordinary
  authored record contracts.
- `lowering.py` already records generated internal inputs by reason through
  `context.internal_generated_input_reasons`.
- command-result parity already added runtime-owned entry binding for managed
  write roots in `WorkflowExecutor._ensure_entry_managed_write_root_bindings`.
- `workflow_public_input_contracts(...)` already hides one class of internal
  inputs, `managed_write_root_inputs`.
- `_lower_call_expr(...)` already auto-binds generated internal inputs for one
  call-site concern, managed write roots.
- the promoted-entry reusable-wrapper fixture already exists:
  `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc`.

The same checkout also shows the exact missing capability:

- `workflow_public_input_contracts(...)` only knows about managed write roots,
  not hidden runtime context inputs.
- `_apply_workflow_input_defaults(...)` still auto-attaches synthetic defaults
  for top-level `PhaseCtx` leaf inputs.
- `test_compile_stage3_entrypoint_omits_imported_defaulted_call_bindings` in
  `tests/test_workflow_lisp_lowering.py` proves that imported defaulted inputs
  are omitted from `call.with`, which is exactly the behavior that currently
  masks the missing hidden context route.
- the promoted-entry bootstrap test in
  `tests/test_workflow_lisp_key_migrations.py` verifies hidden public inputs
  and runtime success, but it does not yet assert that the internal call
  actually receives explicit hidden context bindings.

This makes the slice feasible without a new runtime executor or new context
syntax. The missing work is to extend the existing internal-input ownership
model from managed write roots to runtime-owned context bindings and make the
promoted-entry reusable-call path use that explicit route.

## Proposed Architecture

### 1. Add One New Internal-Input Class For Runtime-Owned Context Values

Keep the command-result parity model and extend it by one bounded reason:

- `managed_write_root`
- `runtime_owned_context`

Implementation direction:

- continue using `GeneratedInternalInput` in
  `orchestrator/workflow_lisp/contracts.py`;
- continue recording internal inputs in
  `_LoweringContext.internal_generated_input_reasons`;
- add one runtime-owned context tuple to runtime-facing provenance metadata so
  public/runtime input helpers can distinguish these names without relying only
  on prefix scans.

Required shared-surface additions:

- `orchestrator/workflow/surface_ast.py`
  - add `runtime_context_inputs: tuple[str, ...] = ()` to
    `WorkflowProvenance`;
- `orchestrator/workflow/core_ast.py`,
  `orchestrator/workflow/elaboration.py`,
  `orchestrator/workflow/semantic_ir.py`,
  and bundle-construction helpers
  - thread the new tuple through the existing provenance-compatible path
    without redefining semantic ownership;
- `orchestrator/workflow/loaded_bundle.py`
  - add `workflow_runtime_context_inputs(...)`;
  - make `workflow_public_input_contracts(...)` exclude both
    managed write roots and runtime context inputs;
  - keep `workflow_runtime_input_contracts(...)` as the full executable input
    view.

This slice does not require a fully generic “all generated internal inputs”
runtime API. It needs one second explicit runtime-owned class so public input
helpers and entry binding behave correctly.

### 2. Derive One Eligibility Contract For Hidden Promoted-Entry Context Binding

Add a frontend-local eligibility record for omitted internal context bindings:

```text
PromotedEntryHiddenContextRequirement
  param_name
  context_kind   # RunCtx | PhaseCtx
  phase_name     # required for PhaseCtx, absent for RunCtx
```

Ownership:

- `orchestrator/workflow_lisp/workflows.py`
  - extend `WorkflowSignature` with
    `hidden_context_requirements: Mapping[str, PromotedEntryHiddenContextRequirement]`;
- `orchestrator/workflow_lisp/phase.py`
  - expose the bounded derivation helper for `PhaseCtx`-eligible workflows.

Eligibility rules for this slice:

- `RunCtx`
  - eligible when the callee parameter type is exactly `RunCtx`;
- `PhaseCtx`
  - eligible only when the callee body establishes one unambiguous phase scope
    from that parameter through ordinary Workflow Lisp syntax already owned by
    Stage 5;
  - for this slice, the compiler may require the callee body to contain one
    top-level `with-phase` using that parameter and one concrete phase symbol;
  - if the callee’s `PhaseCtx` use is ambiguous or not derivable, hidden
    promoted-entry binding is unavailable and the compiler must keep treating
    the parameter as an ordinary required call binding.

Non-goals:

- no new user annotation such as `:runtime-owned`;
- no global inference for arbitrary context-shaped records;
- no claim that imported precompiled bundles outside the linked source compile
  graph already preserve this metadata.

### 3. Extend Call Typecheck And Lowering With One Compiler-Owned Third Path

Promoted-entry call handling now has three binding modes:

1. explicit authored binding;
2. ordinary default omission;
3. compiler-owned hidden promoted-entry context binding.

Typecheck changes:

- `orchestrator/workflow_lisp/typecheck.py`
  - when a required call binding is missing, consult the callee signature’s
    `hidden_context_requirements`;
  - allow omission only when:
    - the current caller workflow is the selected promoted entry or one of its
      generated private wrappers;
    - the missing parameter is covered by a
      `PromotedEntryHiddenContextRequirement`;
    - the omission does not rely solely on imported `PhaseCtx` defaults.

Lowering changes:

- `orchestrator/workflow_lisp/lowering.py`
  - before raising `workflow_signature_mismatch` for a missing required
    binding, synthesize explicit flattened `call.with` entries for every leaf
    of the eligible `RunCtx` or `PhaseCtx` parameter;
  - generate deterministic hidden input names on the promoted entry workflow,
    keyed by:
    - caller workflow name,
    - call step id,
    - callee parameter name,
    - context kind;
  - mark those hidden input names with reason `runtime_owned_context`;
  - keep managed write-root binding behavior unchanged and compose both
    concerns on the same call step.

Required behavioral rule:

- when hidden promoted-entry binding is selected, lowering must emit explicit
  `call.with` bindings for the callee’s flattened context leaves even if the
  callee’s imported workflow signature also has compatibility defaults.

That rule is the core executable proof requirement. The promoted-entry fixture
must pass because the call step carries explicit hidden bindings, not because
the callee quietly defaulted them.

### 4. Runtime-Owned Entry Binding Reuses The Managed-Input Pattern

Add one executor-owned binder parallel to managed write roots:

- `WorkflowExecutor._entry_runtime_context_bindings(...)`
- `WorkflowExecutor._ensure_entry_runtime_context_bindings(...)`

Responsibilities:

- allocate deterministic runtime-owned values for every hidden context input on
  the entry workflow before execution;
- reuse the same values on resume;
- reject user-provided or mutated overrides with a dedicated contract reason;
- persist the bound internal values into run state the same way managed
  write-root bindings are persisted today.

Value derivation rules:

- derive the run id from `StateManager.run_id`;
- derive all roots as workspace-relative paths under the existing `state/` and
  `artifacts/` authorities;
- derive the `PhaseCtx.phase-name` value from the compiler-recorded
  hidden-context requirement for that call site;
- keep the phase root derivation consistent with the Stage 5 phase-layout
  contract rather than hard-coding a second path policy in runtime code.

This slice does not require the runtime to understand Workflow Lisp syntax.
The runtime only needs the generated hidden input names plus the bounded
context-binding policy attached to the compiled entry bundle.

### 5. Synthetic `PhaseCtx` Defaults Become Compatibility Only For This Path

Do not remove `_apply_workflow_input_defaults(...)` in this slice. Narrow its
role instead:

- compile/dry-run convenience for isolated fixtures remains allowed;
- promoted-entry parity proof may not depend on those defaults;
- hidden promoted-entry call binding takes precedence when both routes are
  available.

Testing rule:

- the dedicated promoted-entry fixture must inspect the lowered `call.with`
  payload and prove the reusable-wrapper call binds the flattened `phase-ctx`
  leaves explicitly from runtime-owned hidden inputs.

That is the line between compatibility convenience and parity evidence.

### 6. Diagnostics

Add dedicated diagnostics for this slice:

- `promoted_entry_hidden_context_binding_invalid`
  - the compiler found an omitted `RunCtx` / `PhaseCtx` binding but the caller
    is not eligible for the hidden promoted-entry route;
- `promoted_entry_hidden_phase_ctx_ambiguous`
  - the callee requires `PhaseCtx`, but the compiler cannot derive one
    unambiguous phase symbol for runtime-owned binding;
- `promoted_entry_hidden_context_override`
  - runtime detected a user-provided or mutated bound input for a
    runtime-owned context name;
- `promoted_entry_hidden_context_metadata_missing`
  - lowering/runtime expected hidden-context metadata for a generated internal
    input but the compiled bundle metadata is incomplete.

When the compiler still falls back to the ordinary missing-binding path, keep
the existing `workflow_signature_mismatch` behavior. The new diagnostics apply
only when the hidden promoted-entry route was intended but invalid.

## Proposed Code Footprint

Frontend-owned:

- `orchestrator/workflow_lisp/workflows.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/contracts.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/compiler.py`

Shared runtime/bundle plumbing reused but extended narrowly:

- `orchestrator/workflow/surface_ast.py`
- `orchestrator/workflow/core_ast.py`
- `orchestrator/workflow/elaboration.py`
- `orchestrator/workflow/semantic_ir.py`
- `orchestrator/workflow/loaded_bundle.py`
- `orchestrator/workflow/executor.py`

Focused verification surface:

- `tests/test_workflow_lisp_key_migrations.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/fixtures/workflow_lisp/valid/phase_stdlib_resume_or_start_promoted_entry_bootstrap.orc`
- `tests/fixtures/workflow_lisp/valid/library/phase_stdlib_resume_or_start_promoted_entry_bootstrap_helper.orc`

## Test Strategy

Required coverage:

- compile-time call checking:
  - promoted-entry omission of eligible `PhaseCtx`/`RunCtx` bindings is
    accepted only on the hidden route;
  - ordinary workflows still require explicit bindings or real defaults;
- lowering:
  - the promoted-entry reusable-wrapper call emits explicit `phase-ctx__*`
    `call.with` bindings sourced from runtime-owned hidden inputs;
  - managed write-root bindings and hidden context bindings coexist without
    collision;
- build/runtime input surfaces:
  - hidden context inputs are absent from the public input view;
  - hidden context inputs remain present in the runtime input view;
- runtime execution:
  - the executor allocates deterministic hidden context values for entry runs;
  - resume reuses those values;
  - manual overrides fail deterministically;
- regression:
  - synthetic `PhaseCtx` defaults may still exist, but the promoted-entry
    proof fixture no longer depends on them for success.

Preferred new or revised tests:

- extend
  `tests/test_workflow_lisp_key_migrations.py::test_promoted_entry_resume_or_start_fixture_bootstraps_hidden_context`
  so it:
  - asserts the call step includes explicit flattened `phase-ctx` bindings;
  - executes the reusable-wrapper route successfully;
  - proves the entry bundle exposes no public context/root inputs;
- add one lowering-focused test that fails if the promoted-entry call again
  omits those bindings and succeeds only through imported defaults;
- add one runtime override test parallel to the managed-write-root override
  regression.

## Implementation Sequence

1. Add signature-level hidden-context eligibility metadata and the bounded
   `PhaseCtx` derivation helper.
2. Add runtime-facing hidden context input metadata and public/runtime input
   helper support.
3. Extend call typecheck and lowering to synthesize explicit promoted-entry
   hidden bindings.
4. Add executor-owned runtime binding and override rejection.
5. Tighten the promoted-entry fixture and add lowering/build regressions.

## Acceptance Conditions

- the promoted-entry reusable-wrapper fixture exposes only its authored
  business inputs as public inputs;
- no public `phase-ctx__*`, `run-id`, `state-root`, `artifact-root`, or
  runtime-owned hidden context inputs appear on the promoted entry boundary;
- the lowered reusable-wrapper call includes explicit flattened `phase-ctx`
  bindings sourced from generated internal inputs, not silent default omission;
- runtime execution of the promoted-entry fixture succeeds through the real
  `resume-or-start :valid-when (APPROVED)` route without explicit or defaulted
  authored `PhaseCtx` fallback wiring;
- overriding one runtime-owned hidden context input fails deterministically;
- synthetic `PhaseCtx` defaults remain compatibility-only and are not the
  reason the promoted-entry proof passes.

## Verification Plan

The implementation plan for this slice should use the deterministic commands
recorded in:

`state/LISP-MIGRATION-PARITY-DRAIN/drain/iterations/0/design-gap-architect/check_commands.json`

At minimum they should cover:

- collect-only over the focused lowering/build/migration test modules;
- the dedicated promoted-entry reusable-wrapper proof in
  `tests/test_workflow_lisp_key_migrations.py`;
- one lowering-focused regression that inspects explicit hidden context
  `call.with` bindings;
- one build/runtime-input regression that proves hidden context inputs are
  internal and runtime-owned.
