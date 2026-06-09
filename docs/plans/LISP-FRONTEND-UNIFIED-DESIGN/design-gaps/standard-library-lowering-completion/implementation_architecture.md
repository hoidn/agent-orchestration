# Standard-Library Lowering Completion Implementation Architecture

Status: draft
Design gap id: `standard-library-lowering-completion`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded architecture needed to turn the current
Workflow Lisp standard-library lowering surfaces into one reviewed internal
contract layer:

- define one shared lowering-contract inventory for the nine currently
  supported stdlib forms:
  - `provider-result`
  - `command-result`
  - `run-provider-phase`
  - `produce-one-of`
  - `review-revise-loop`
  - `resume-or-start`
  - `resource-transition`
  - `finalize-selected-item`
  - `backlog-drain`
- pin down, per form:
  - generated statement families;
  - effect visibility and backend ownership;
  - state-root and generated-write-root policy;
  - artifact/path authority rules;
  - proof and branch-normalization behavior;
  - source-map expectations;
  - primary diagnostic ownership;
  - fixture and regression-test obligations;
- keep each form on the existing Stage 3 lowering path and shared validation
  pipeline rather than inventing a second stdlib runtime;
- preserve current helper-module ownership for phase, reusable-state,
  resource-transition, selected-item finalization, and drain lowering.

This slice does not implement:

- new author-facing stdlib syntax;
- new Core Workflow AST or Executable IR node kinds;
- new runtime-native effects for `resource-transition`, `resume-or-start`, or
  `backlog-drain`;
- replacement of existing lowering functions with a new executor or alternate
  validator;
- new inline shell/Python glue, hidden helper commands, or unreviewed adapter
  promotion;
- redesign of shared TypeCatalog, SourceMap, pointer authority, report
  authority, or runtime execution ownership.

The work stays bounded to the selected gap. It is an implementation
architecture for the missing stdlib lowering contract, not a replacement
product design and not a redesign of already-implemented baseline behavior.

## Problem Statement

The current checkout already implements all nine stdlib forms, but the
implementation contract remains scattered:

- `expressions.py` defines dedicated authored expression nodes for all stdlib
  forms;
- `typecheck.py` validates typed inputs, return types, and effect summaries for
  each form;
- `lowering.py` contains one lowering entrypoint per form;
- `phase_stdlib.py`, `resource_stdlib.py`, `drain_stdlib.py`, and `resource.py`
  already hold authored spec records and several form-specific invariants;
- `compiler.py` already installs the certified adapters used by
  `resume-or-start` and `resource-transition`;
- tests already cover many positive and negative cases in
  `tests/test_workflow_lisp_phase_stdlib.py`,
  `tests/test_workflow_lisp_lowering.py`,
  `tests/test_workflow_lisp_examples.py`,
  `tests/test_workflow_lisp_build_artifacts.py`, and
  `tests/test_subworkflow_calls.py`.

What is still missing is the reviewed internal contract that Section 30 of the
unified design calls for:

- there is no single inventory that states which generated statement families,
  state roots, proof obligations, and diagnostic owners belong to each stdlib
  form;
- the draft appendix `docs/design/workflow_lisp_stdlib_lowering.md` names the
  required forms and a template, but it is still an internal draft and not a
  bounded implementation architecture tied to the current checkout;
- per-form invariants currently live in function docstrings, helper modules,
  and tests, which makes drift likely when Stage 3 normalization changes;
- adapter-backed forms already rely on certified command boundaries, but the
  current implementation has no reviewed stdlib-level statement that ties those
  adapters back to the command-adapter contract and fixture obligations;
- there is no single acceptance matrix that shows how stdlib lowering reuses
  the landed effectful-composition, write-root, and reusable-boundary slices.

The selected gap is therefore not "add stdlib lowering." It is to make the
already-implemented stdlib surfaces cohere as one explicit lowering contract:

```text
typed stdlib form
  -> shared stdlib lowering contract entry
  -> existing typecheck + lowering helpers
  -> deterministic step-backed result
  -> shared validation / executable pipeline
  -> focused contract tests proving backend, authority, and provenance
```

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `21. Feature Summary`
  - `22. Current Gap`
  - `23. Design Goal`
  - `29. Reusable Workflow Boundary Write Roots`
  - `30. Standard-Library Lowering Completion`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `22. Provider Result`
  - `23. Command Result`
  - `24. Produced Outcome`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `28. resume-or-start`
  - `29. resource-transition`
  - `30. finalize-selected-item`
  - `31. backlog-drain`
  - `54-58. Lowering rules for provider/command/stdlib forms`
  - `59. Validation Sequence`
  - `74. Source Map Requirements`
  - `95. Lowering Tests`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- all stdlib forms must continue lowering through ordinary Stage 3 helpers and
  validated workflow bundles;
- reports remain views and structured bundles remain authority;
- command-backed forms must use explicit external-tool or certified-adapter
  bindings, never inline shell/Python text;
- generated write roots remain governed by the landed reusable-boundary policy;
- effectful-composition behavior remains owned by the landed `let*`, `match`,
  and `with-phase` slices rather than being reimplemented inside stdlib forms;
- compile-time-only values such as `ProcRef`, `WorkflowRef`, `bind-proc`, and
  generated local-procedure metadata remain erased before runtime artifacts.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-let-star-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/executable-ir-component-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/macro-acceptance-gate-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/reusable-workflow-boundary-write-root-policy/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/runtime-closure-disabled-profile-fixtures/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- additional internal design coherence reference:
  - `docs/design/workflow_lisp_stdlib_lowering.md`

### Decisions Reused

- Reuse the current authored expression surfaces and lowering entrypoints; no
  new author syntax node is needed for this slice.
- Reuse the `_TerminalResult` model, hidden-input accumulation, step-origin
  tracking, and output-ref projection already used by provider, command,
  conditional, match, loop, phase, and call lowering.
- Reuse the effectful-composition slices' rule that stdlib forms participate
  in ordinary binding, branch, and composed `with-phase` lowering rather than
  getting ad hoc expression-specific runtime treatment.
- Reuse the reusable-boundary write-root slice's caller-owned managed input
  policy for workflow calls emitted by `resume-or-start` and `backlog-drain`.
- Reuse the same-file call slice's record-binding and boundary-flattening rules
  for `backlog-drain`-generated workflow calls.
- Reuse the executable-IR slice's constraint that this work changes internal
  lowering contracts and acceptance tests, not runtime value strata or
  executable node kinds.
- Reuse the command-adapter contract as the authority for classifying:
  - `command-result` as an explicit command boundary;
  - `resource-transition` as a certified adapter boundary;
  - `resume-or-start` reusable-state validation and canonical-result loading as
    certified adapter boundaries.

### New Decisions In This Slice

- Introduce one compile-time-only `StdlibLoweringContract` inventory that names
  the lowering family, generated statement pattern, backend kind, state-root
  policy, authority model, proof model, diagnostics, and fixture obligations
  for each stdlib form.
- Partition the current forms into three reviewed lowering families:
  - structured-result producers;
  - review/reuse control forms;
  - resource/finalization/drain forms.
- Keep existing lowering code in `lowering.py`, but make the inventory the
  reviewed contract that those functions and their tests must satisfy.
- Treat the current helper modules as contract owners for their domains:
  - `phase_stdlib.py` for phase/reusable-state authored specs;
  - `resource_stdlib.py` and `resource.py` for resource/finalization contracts;
  - `drain_stdlib.py` for drain authored specs.
- Add focused acceptance tests that assert form-by-form contract facts, not
  only full lowered step snapshots.

### Conflicts Or Revisions

The current checkout effectively treats stdlib lowering correctness as the sum
of:

- per-function lowering docstrings;
- scattered helper-module invariants; and
- broad regression tests.

That is no longer enough for the selected target gap, because Section 30 asks
for a reviewed lowering architecture that explicitly pins down generated
statements, effects, state roots, authority, proofs, diagnostics, and
fixtures.

This slice revises that implementation assumption narrowly:

- keep the existing per-form lowering functions;
- add one explicit internal contract layer over them;
- keep adapter/runtime ownership exactly where it already belongs;
- make acceptance tests speak in terms of that explicit contract rather than
  implicit function behavior.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, Executable IR, TypeCatalog, SourceMap, pointer
authority, or variant proof.

## Ownership Boundaries

This slice owns:

- the shared stdlib lowering-contract inventory for the nine supported forms;
- the classification of each form's lowering family, backend kind, and
  deterministic state-root policy;
- the mapping from each form to its primary typecheck, lowering, diagnostic,
  and fixture obligations;
- contract-focused regression tests that prove the current lowering functions
  satisfy the reviewed inventory;
- source-mapped documentation of how adapter-backed forms stay within the
  command-adapter contract.

This slice intentionally does not own:

- authored syntax, parser, or macro redesign for stdlib forms;
- new runtime-native effects or new executable node kinds;
- provider runtime behavior, command runtime behavior, or state persistence;
- redesign of reusable-state schema semantics beyond reusing the current
  `resume-or-start` contract helpers;
- new adapters, legacy adapters, or inline command glue;
- redesign of phase context construction, pointer-authority rules, or report
  authority.

## Proposed Package Boundary

Keep the work inside the existing frontend package, add one small shared
contract module, and reuse the current helper ownership boundaries:

```text
orchestrator/workflow_lisp/
  stdlib_contracts.py   # NEW shared stdlib lowering-contract inventory
  lowering.py           # existing per-form lowering entrypoints consume the inventory
  typecheck.py          # existing per-form typing/effect checks remain authoritative
  phase_stdlib.py       # phase/reusable-state authored specs and helper metadata
  resource_stdlib.py    # resource/finalization authored specs
  drain_stdlib.py       # drain authored specs
  resource.py           # item/drain layout and contract validators
  contracts.py          # generated structured-result and boundary contracts
  compiler.py           # certified adapter registration for resume/resource forms

tests/
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_examples.py
  test_workflow_lisp_build_artifacts.py
  test_subworkflow_calls.py
```

Primary responsibilities:

- `stdlib_contracts.py`
  - define one inventory entry per stdlib form;
  - record:
    - form name;
    - authored expression class;
    - lowering family;
    - backend kind;
    - generated statement families;
    - state-root policy;
    - authority model;
    - proof model;
    - primary diagnostic codes;
    - expected test surfaces;
  - remain compile-time only and never become a runtime registry.
- `lowering.py`
  - keep the actual `_lower_*` implementations;
  - optionally expose a narrow helper so tests can assert the inventory against
    emitted steps without snapshotting the whole workflow;
  - preserve existing step ids, hidden-input names, and source-map origins.
- `typecheck.py`
  - remain authoritative for typed inputs, return shapes, and effect summaries;
  - keep existing diagnostic families;
  - align any new contract assertions to existing diagnostics rather than
    inventing a second type system.
- `phase_stdlib.py`, `resource_stdlib.py`, `drain_stdlib.py`, `resource.py`
  - remain the owners of form-specific authored specs and helper metadata;
  - provide the facts consumed by lowering and by the new contract inventory.
- `compiler.py`
  - remain authoritative for installing the certified adapter bindings used by
    `resume-or-start` and `resource-transition`;
  - keep fixture ids, effects, and path-safety metadata attached there.

No new runtime package, helper script, or alternate lowering pipeline is
needed for this slice.

## Current Checkout Facts

Current implementation evidence shows that stdlib lowering already exists and
that the missing piece is the reviewed contract tying it together:

- `orchestrator/workflow_lisp/expressions.py`
  - already defines dedicated nodes for:
    - `ProviderResultExpr`
    - `CommandResultExpr`
    - `RunProviderPhaseExpr`
    - `ProduceOneOfExpr`
    - `ReviewReviseLoopExpr`
    - `ResumeOrStartExpr`
    - `ResourceTransitionExpr`
    - `FinalizeSelectedItemExpr`
    - `BacklogDrainExpr`
- `orchestrator/workflow_lisp/functions.py`
  - already classifies those forms as effectful and forbids them inside pure
    helpers.
- `orchestrator/workflow_lisp/typecheck.py`
  - already validates:
    - typed provider/command results;
    - `run-provider-phase` return shapes;
    - `produce-one-of` candidate contracts;
    - `review-revise-loop` phase/name invariants;
    - `resume-or-start` reusable-state contracts and certified adapter usage;
    - `resource-transition` context/resource/enum/backend requirements;
    - `finalize-selected-item` input and union-shape requirements;
    - `backlog-drain` context and workflow-ref signature requirements.
- `orchestrator/workflow_lisp/lowering.py`
  - already contains one lowering entrypoint per stdlib form:
    - `_lower_provider_result(...)`
    - `_lower_command_result(...)`
    - `_lower_run_provider_phase(...)`
    - `_lower_produce_one_of(...)`
    - `_lower_review_revise_loop(...)`
    - `_lower_resume_or_start(...)`
    - `_lower_resource_transition(...)`
    - `_lower_finalize_selected_item(...)`
    - `_lower_backlog_drain(...)`
- `orchestrator/workflow_lisp/contracts.py`
  - already derives generated `output_bundle` / `variant_output` contracts and
    workflow-boundary flattening used by several stdlib forms.
- `orchestrator/workflow_lisp/phase_stdlib.py`
  - already carries reusable-state and produced-variant helper records used by
    `produce-one-of` and `resume-or-start`.
- `orchestrator/workflow_lisp/resource_stdlib.py`,
  `orchestrator/workflow_lisp/resource.py`, and
  `orchestrator/workflow_lisp/drain_stdlib.py`
  - already carry authored specs plus context/layout validators for the
    resource/finalization/drain forms.
- `orchestrator/workflow_lisp/compiler.py`
  - already installs certified adapter bindings for:
    - `validate_reusable_phase_state`
    - `load_canonical_phase_result__<ReturnType>`
    - `apply_resource_transition`
  - with declared effects, output type names, path-safety expectations, and
    fixture ids.
- test coverage already exists:
  - `tests/test_workflow_lisp_phase_stdlib.py` for phase/reuse forms;
  - `tests/test_workflow_lisp_lowering.py` for lowered step shapes;
  - `tests/test_workflow_lisp_examples.py` for integrated examples;
  - `tests/test_workflow_lisp_build_artifacts.py` for effect/source-map/build
    artifacts;
  - `tests/test_subworkflow_calls.py` for reusable-boundary write-root
    behavior.

That means the missing work is not a new lowering backend. It is one reviewed
contract layer that makes those existing surfaces explicit and testable as a
family.

## Internal Lowering Contract

### 1. Shared Inventory Shape

Add one compile-time-only inventory entry shape, conceptually:

```text
StdlibLoweringContract
  form_name
  expr_type
  family
  backend_kind
  generated_statement_families
  state_root_policy
  authority_model
  proof_model
  primary_diagnostics
  test_surfaces
```

Rules:

- the inventory is descriptive and validating, not executable;
- it must not become a runtime registry or an alternate lowering path;
- lowering continues to happen through the existing `_lower_*` functions;
- tests may assert inventory facts against emitted steps, hidden inputs, and
  source maps without snapshotting unrelated workflow structure.

Recommended enums:

- `family`
  - `structured_result_producer`
  - `review_reuse_control`
  - `resource_finalize_drain`
- `backend_kind`
  - `provider`
  - `external_tool`
  - `certified_adapter`
  - `workflow_call`
  - `materialize_only`
- `state_root_policy`
  - `generated_hidden_bundle_input`
  - `active_phase_bundle`
  - `active_phase_bundle_plus_snapshot`
  - `repeat_until_generated_bundle`
  - `managed_reusable_boundary_inputs`
  - `item_or_drain_layout_projection`

### 2. Structured-Result Producer Family

This family covers:

- `provider-result`
- `command-result`
- `run-provider-phase`
- `produce-one-of`

Shared contract:

- result authority is a validated structured bundle, never report text;
- the lowering result is step-backed and exportable through `_TerminalResult`;
- all generated paths come from either:
  - an explicit hidden write-root input; or
  - an active phase scope / snapshot root;
- union results rely on existing variant proof rules and expose no variant-only
  fields outside later `match` / proof contexts.

Per-form generated statement families:

- `provider-result`
  - provider step;
  - generated `output_bundle` or `variant_output`;
  - optional phase prompt-input prelude when lowered under the current
    implementation-attempt phase special case.
- `command-result`
  - command step;
  - generated `output_bundle` or `variant_output`;
  - explicit command boundary from the registered binding.
- `run-provider-phase`
  - prompt-input materialization prelude;
  - provider step;
  - active phase bundle path derived from phase scope.
- `produce-one-of`
  - prompt-input materialization prelude;
  - `pre_snapshot`;
  - producer step;
  - `select_variant_output`;
  - final `match` normalization step.

Command/backend rules:

- `provider-result` and `run-provider-phase` are provider-backed only;
- `command-result` is the explicit external-tool/certified-command boundary and
  must stay within the command-adapter contract;
- `produce-one-of` may currently use a provider producer, but its variant
  authority must come from snapshot evidence plus validated selection, not from
  prose or mtime.

### 3. Review And Reuse Control Family

This family covers:

- `review-revise-loop`
- `resume-or-start`

Shared contract:

- control flow is still typed and step-backed;
- loop/branch decisions must come from structured state, not parsed reports;
- any reusable-state decision must stay explicit at the command-adapter
  boundary and normalize back to the same typed return shape as a fresh branch;
- managed write roots across reusable workflow boundaries must reuse the landed
  caller-owned policy.

Per-form generated statement families:

- `review-revise-loop`
  - generated `repeat_until`;
  - review provider step with a generated decision bundle;
  - branch routing `match` over structured review decision;
  - optional fix-provider step in the revise branch;
  - final result-normalization `match`.
- `resume-or-start`
  - certified validator command step;
  - reuse loader command step;
  - branch normalization `match`;
  - optional start-branch lowering through an already-supported expression,
    including workflow calls that use shared managed write-root helpers.

Adapter/backend rules:

- `review-revise-loop` uses provider backends only and must keep the review
  decision in structured state;
- `resume-or-start` must use the certified adapters registered in
  `compiler.py`;
- this slice does not promote reusable-state validation to a runtime-native
  effect and does not add new adapters beyond those already defined.

### 4. Resource, Finalization, And Drain Family

This family covers:

- `resource-transition`
- `finalize-selected-item`
- `backlog-drain`

Shared contract:

- resource movement or queue/drain routing must stay explicit as typed
  transitions;
- pointer files, summary reports, and published summaries remain
  representations or views, not semantic authority;
- workflow-call boundaries must continue using deterministic managed
  write-root bindings and flattened call inputs.

Per-form generated statement families:

- `resource-transition`
  - one certified-adapter command step;
  - validated structured result bundle;
  - optional `when` predicate.
- `finalize-selected-item`
  - match/materialize fan-in over plan and implementation unions;
  - published summary artifact materialization;
  - result-normalization match.
- `backlog-drain`
  - generated `repeat_until`;
  - managed workflow calls for selector / run-item / gap-drafter;
  - accumulator materialization and route steps;
  - deterministic loop-scoped managed write-root bindings for called
    workflows.

Adapter/backend rules:

- `resource-transition` must continue lowering through the certified
  `apply_resource_transition` adapter until a separately accepted runtime
  promotion exists;
- `finalize-selected-item` is materialize/match/publish only and introduces no
  hidden adapter or provider boundary;
- `backlog-drain` remains a workflow-call/loop lowering surface and introduces
  no hidden command boundary.

### 5. Source Maps, Diagnostics, And Effect Visibility

Every inventory entry must record the primary diagnostic owners and source-map
expectations for its form.

Bounded rules:

- keep existing diagnostics authoritative;
- do not invent stdlib-only diagnostic families when an existing typecheck,
  lowering, boundary, or source-map diagnostic already owns the failure;
- preserve form-origin spans on all generated steps and hidden-input paths;
- keep adapter-backed forms source-mapped to the high-level stdlib form and
  the specific generated command step.

Expected primary diagnostic ownership examples:

- `provider-result`, `command-result`
  - existing provider/command result validation diagnostics;
- `run-provider-phase`, `produce-one-of`
  - phase-scope and candidate-contract diagnostics;
- `review-revise-loop`
  - phase-name mismatch or exportability diagnostics;
- `resume-or-start`
  - `resume_or_start_contract_invalid`
  - `resume_or_start_resume_path_invalid`
  - `resume_or_start_uncertified_backend`
- `resource-transition`
  - `resource_transition_contract_invalid`
- `finalize-selected-item`
  - `finalize_selected_item_contract_invalid`
  - `workflow_return_not_exportable`
- `backlog-drain`
  - `backlog_drain_contract_invalid`
  - existing workflow-ref signature and call-boundary diagnostics.

Effect visibility rules:

- provider-backed forms must expose provider effects;
- command-backed forms must expose command effects and certified-adapter
  metadata;
- call-backed forms must expose workflow-call effects and managed write-root
  requirements;
- no stdlib helper may hide resource transitions, ledger updates, snapshots,
  pointer materialization, or summary publication.

### 6. Command-Adapter Contract Integration

This slice explicitly adopts `docs/design/workflow_command_adapter_contract.md`
for stdlib forms that cross command boundaries.

Required mapping:

- `command-result`
  - classify as `external_tool` unless the bound command is a certified
    adapter;
  - the lowering contract must still record explicit typed outputs and source
    maps.
- `resource-transition`
  - classify as `certified_adapter`;
  - authoritative backend is `apply_resource_transition`;
  - effects must remain `resource_transition` plus `ledger_update`.
- `resume-or-start`
  - validator and canonical-result loader classify as
    `certified_adapter`;
  - reusable-state semantics may not be hidden in inline command text,
    markdown parsing, or pointer-as-state conventions.

This slice does not introduce runtime-native promotion criteria of its own. If
future work revisits adapter promotion, it must do so through the command-
adapter contract's existing promotion rules.

## Test And Acceptance Surface

Implementation should add or realign tests so the reviewed contract becomes a
first-class acceptance surface.

Primary test targets:

- `tests/test_workflow_lisp_phase_stdlib.py`
- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_examples.py`
- `tests/test_workflow_lisp_build_artifacts.py`
- `tests/test_subworkflow_calls.py`

Required positive coverage:

- one positive contract assertion for each of the nine forms;
- one family-level regression per lowering family proving the shared contract
  fields:
  - backend kind;
  - generated statement families;
  - state-root policy;
  - authority model;
  - source-map coverage;
- one shared-validation compile path for:
  - structured-result producer forms;
  - `review-revise-loop` / `resume-or-start`;
  - `resource-transition` / `finalize-selected-item` / `backlog-drain`;
- one adapter-focused regression proving the stdlib inventory still points to
  certified adapter metadata for `resource-transition` and `resume-or-start`;
- one build-artifact regression proving the reviewed contract did not create
  new runtime artifacts, registries, or hidden sidecar authorities.

Required negative coverage:

- command-backed forms still reject uncertified or misclassified semantic
  backends under existing diagnostics;
- `produce-one-of` still rejects invalid candidate declarations;
- `resume-or-start` still rejects invalid reusable-state contracts and resume
  paths;
- `resource-transition` still rejects missing certified adapter metadata;
- `finalize-selected-item` still rejects invalid plan/implementation union
  shapes;
- `backlog-drain` still rejects invalid context or workflow-ref signatures;
- no stdlib contract helper may emit inline shell/Python glue or hidden helper
  commands.

## Acceptance Conditions

- the architecture stays bounded to `standard-library-lowering-completion`;
- the implementation architecture explicitly reuses the landed effectful-
  composition and reusable-boundary slices instead of redefining them;
- the architecture names one shared stdlib lowering-contract inventory and
  keeps it compile-time only;
- all nine stdlib forms are classified with generated statement families,
  backend kind, state-root policy, authority model, proof model, diagnostics,
  and test obligations;
- adapter-backed forms explicitly cite the command-adapter contract;
- the architecture includes the required
  `Relationship To Existing Implementation Architectures` section;
- the work-item context records
  `docs/design/workflow_command_adapter_contract.md` in the authoritative
  inputs.

## Verification Expectations

Deterministic commands are recorded in:

- `state/LISP-FRONTEND-UNIFIED-DESIGN/drain/iterations/2/design-gap-architect/check_commands.json`

Those checks should prove:

- the architecture, context, check-command list, and draft bundle exist at the
  prescribed paths;
- the draft bundle matches the selected design gap and target paths;
- the implementation architecture includes the required relationship section;
- the work-item context records
  `docs/design/workflow_command_adapter_contract.md` in the authoritative
  input set;
- the drafted architecture explicitly names the selected
  `standard-library-lowering-completion` gap.
