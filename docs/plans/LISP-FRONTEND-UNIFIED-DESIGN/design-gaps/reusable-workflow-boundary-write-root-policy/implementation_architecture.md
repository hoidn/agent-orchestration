# Reusable Workflow Boundary Write-Root Policy Implementation Architecture

Status: draft
Design gap id: `reusable-workflow-boundary-write-root-policy`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice defines only the bounded Stage 3 architecture needed to make
generated write-root allocation and transport deterministic across reusable and
private workflow boundaries:

- classify generated write-root inputs for lowered reusable callees through one
  explicit frontend-owned contract instead of rediscovering them ad hoc at each
  call site;
- reuse that contract when lowering same-file workflow calls, private-workflow
  procedure calls, and loop-generated managed calls such as `backlog-drain`;
- preserve the current hidden-input and boundary-projection surfaces used by
  phase stdlib forms such as `run-provider-phase`, `produce-one-of`, and
  `review-revise-loop`;
- preserve deterministic caller-allocated path templates for generated bundle
  paths, including loop-scoped disambiguation;
- align `resume-or-start` bundle-path recovery with the same managed write-root
  boundary contract so reusable phase helpers recover canonical start-arm bundle
  locations through one rule.

This slice does not implement:

- new authored syntax, new type-system surfaces, or a new runtime value type;
- a runtime-native write-root primitive, new adapter boundary, or hidden helper
  script;
- changes to phase stdlib semantic behavior, provider semantics, command
  semantics, or shared validation ownership;
- redesign of private-workflow exportability rules, match proof rules, record
  flattening, or `with-phase` scope derivation;
- changes to the visible `__write_root__...` naming convention, imported-bundle
  managed-input compatibility, or runtime collision checks.

The work stays bounded to one missing boundary-policy seam. It is an
implementation architecture for deterministic generated write-root transport,
not a replacement write-root design for the runtime or the overall Workflow
Lisp frontend.

## Problem Statement

The current checkout already has most of the substrate required by the target
design:

- effectful lowering returns `_TerminalResult.hidden_inputs`, which already
  carries generated input names that later become authored hidden inputs for a
  lowered workflow;
- `lower_workflow_definitions(...)` already records those generated inputs in
  both the authored workflow mapping and
  `WorkflowBoundaryProjection.generated_internal_inputs` with reason
  `managed_write_root`;
- phase stdlib forms such as `run-provider-phase`, `produce-one-of`,
  `review-revise-loop`, and `resume-or-start` already generate stable
  `__write_root__...__result_bundle` inputs for canonical result-bundle paths;
- reusable call lowering already injects caller-owned path bindings for managed
  callee inputs in `_lower_call_expr(...)`, the private-workflow branch of
  `_lower_procedure_call_expr(...)`, and the drain-specific `_managed_call_step(...)`.

What is missing is a single reusable/private boundary contract that ties those
pieces together.

Today the policy exists, but it is split across multiple ad hoc seams:

- generated write-root requirements originate in `_TerminalResult.hidden_inputs`
  and in finalized boundary projection metadata;
- same-file call lowering rediscovers requirements by scanning lowered callee
  inputs for `__write_root__` prefixes;
- imported-bundle call lowering uses a separate helper against validated bundle
  surface inputs;
- loop-generated managed calls format a slightly different path template by
  hand;
- `resume-or-start` bundle recovery separately reconstructs the expected hidden
  input name for a workflow start arm.

That leaves a concrete implementation gap between current capabilities and the
selected target:

- reusable/private calls already transport generated write-root paths, but the
  transport contract is implicit;
- phase stdlib forms already depend on those generated paths, but there is no
  single lowering helper that defines discovery, allocation, loop scoping, and
  bundle-path recovery together;
- tests already prove isolated happy paths, but the implementation still relies
  on repeated prefix scans and duplicated path formatting logic.

The selected gap is therefore not whether generated write roots are allowed.
It is a bounded normalization problem:

```text
lowered reusable callee
  -> expose generated write-root requirements through one boundary contract
  -> allocate caller-owned paths through one deterministic helper
  -> bind those paths at same-file, private-workflow, and loop call sites
  -> recover canonical start-arm bundle paths through that same contract
```

If a reusable callee cannot describe its generated write-root requirements
through the existing lowered boundary metadata or imported-bundle surface, the
call must still reject.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `29. Reusable Workflow Boundary Write Roots`
  - `30. Standard-Library Lowering Completion`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `16. Effect System`
  - `19. Context Types`
  - `20. Canonical State Layout`
  - `21. Phase Context`
  - `26. run-provider-phase`
  - `27. review-revise-loop`
  - `28. resume-or-start`
  - `51. defproc Lowering`
  - `57. review-revise-loop Lowering`
  - `74. Source Map Requirements`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- generated write roots stay runtime-managed path slots, not authored semantic
  state;
- typed bundles remain authority and reports remain views;
- reusable/private workflows must keep caller-owned write-root allocation
  rather than hard-coding DSL-managed roots internally;
- no provider, command, workflow, state, or adapter effect may be hidden by
  the boundary helper;
- the command-adapter contract remains authoritative for any command-backed
  step inside a reusable callee. This slice must not introduce wrapper scripts,
  inline Python/shell glue, or hidden adapter shims just to move generated
  bundle paths across a call.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/effectful-match-arm-normalization/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/same-file-call-bindings-for-locally-constructed-records/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- Additional historical coherence references:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/phase-context-stdlib/implementation_architecture.md`

### Decisions Reused

- Reuse the current Stage 3 lowering pipeline and package ownership split; the
  policy stays in `orchestrator/workflow_lisp/`, not in a new runtime layer.
- Reuse `_TerminalResult.hidden_inputs` as the producer-side lowering surface
  for generated write-root requirements.
- Reuse `WorkflowBoundaryProjection.generated_internal_inputs` and the existing
  `GeneratedInternalInput(reason="managed_write_root")` metadata as the
  same-file lowered-callee authority surface.
- Reuse imported-bundle compatibility through the validated bundle surface and
  `workflow_managed_write_root_inputs(...)`.
- Reuse the current caller-owned path layout under
  `.orchestrate/workflow_lisp/calls/...` and the current `${loop.index}`
  disambiguation convention for loop-generated call sites.
- Reuse prior-slice decisions that `with-phase`, effectful `match`, same-file
  record bindings, and generated private workflows must all flow through the
  existing step-backed lowering path rather than inventing a parallel boundary.

### New Decisions In This Slice

- Treat generated write-root transport as an explicit reusable-boundary
  lowering contract instead of a repeated `__write_root__` string-scan pattern.
- Make same-file workflow calls, private-workflow procedure calls, and managed
  loop call sites use one shared helper to discover callee requirements and
  one shared helper to allocate caller-owned binding paths.
- Prefer `boundary_projection.generated_internal_inputs` as the same-file
  lowered-callee authority surface whenever a lowered callee is available, and
  use raw authored-input prefix scans only as a compatibility fallback.
- Make `resume-or-start` start-arm bundle recovery reuse the same managed
  write-root discovery and path-allocation helpers for workflow calls instead
  of reconstructing equivalent logic separately.
- Keep generated input names, visible path layout, and reason labels unchanged;
  the new slice centralizes the contract without changing the external shape.

### Conflicts Or Revisions

Prior slices repeatedly said that reusable/private workflow write-root policy
remains unchanged. That remains true semantically, but the current
implementation still encodes the policy through duplicated discovery and
allocation logic.

This slice revises that implementation assumption narrowly:

- prefix-based discovery is no longer the preferred same-file authority when
  richer boundary-projection metadata is already available;
- call sites stop formatting their own managed-write-root bindings directly and
  instead consume one shared helper;
- the policy remains the same from the runtime's perspective: caller-owned
  hidden bundle paths are bound deterministically and must still satisfy the
  existing collision and path-safety checks.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- lowering-time discovery of generated managed write-root requirements for
  lowered same-file callees, generated private workflows, and imported bundles;
- one shared deterministic allocator for caller-owned managed write-root paths
  across reusable/private workflow call sites;
- bundle-path recovery alignment for `resume-or-start` workflow-call start
  arms;
- source-mapped diagnostics when reusable call lowering cannot recover a stable
  managed write-root requirement set;
- focused regression tests that prove the policy remains deterministic across
  phase stdlib reuse, generated private workflows, loop-managed calls, and
  imported-bundle compatibility.

This slice intentionally does not own:

- creation of generated write-root requirements inside provider, command, or
  phase stdlib lowering beyond consuming the existing `hidden_inputs` surface;
- redesign of reusable/private workflow exportability checks;
- runtime collision detection, runtime path-safety enforcement, or reusable
  workflow execution semantics in `orchestrator/workflow/`;
- new adapters, scripts, or runtime-native effects;
- state-layout redesign, pointer-authority rules, or report-authority rules.

## Proposed Package Boundary

Keep the work inside the existing frontend package and confine changes to the
boundary-discovery and call-lowering seam:

```text
orchestrator/workflow_lisp/
  lowering.py       # shared managed-write-root discovery and caller binding allocation
  contracts.py      # existing GeneratedInternalInput / WorkflowBoundaryProjection reused as-is

tests/
  test_workflow_lisp_phase_stdlib.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_examples.py
  test_workflow_lisp_build_artifacts.py
  test_subworkflow_calls.py
```

Primary responsibilities:

- `lowering.py`
  - add one internal helper that discovers managed write-root requirements from
    a lowered callee or imported bundle;
  - add one internal helper that allocates caller-owned binding paths for those
    requirements with optional loop-scope disambiguation;
  - make `_lower_call_expr(...)`, the private-workflow branch of
    `_lower_procedure_call_expr(...)`, and `_managed_call_step(...)` use those
    helpers;
  - make `_resume_start_bundle_ref(...)` reuse the same requirement discovery
    and path recovery for workflow-call start arms.
- `contracts.py`
  - remain the authority for the generated internal-input metadata shape;
  - optionally expose a tiny helper for filtering `managed_write_root`
    projection entries if sharing that logic outside `lowering.py` improves
    coherence, but no schema change is introduced.
- `tests/*`
  - add focused coverage for same-file reusable calls, generated private
    workflows, loop-managed call sites, build-artifact projection metadata, and
    imported-bundle compatibility.

No new package, module, or helper script is needed for this slice.

## Current Checkout Facts

Current implementation evidence shows both the existing substrate and the
duplication this slice must remove:

- `orchestrator/workflow_lisp/lowering.py`
  - `lower_workflow_definitions(...)` promotes terminal `hidden_inputs` into
    authored hidden inputs and records reason `managed_write_root` in
    `boundary_projection.generated_internal_inputs`;
  - `_lower_run_provider_phase(...)`, `_lower_produce_one_of(...)`,
    `_lower_review_revise_loop(...)`, provider/command-result lowering, and the
    `resume-or-start` loader path all generate `__write_root__...` names;
  - `_lower_call_expr(...)` and the private-workflow branch of
    `_lower_procedure_call_expr(...)` each scan managed inputs and build
    `.orchestrate/workflow_lisp/calls/...` bindings inline;
  - `_managed_call_step(...)` in drain lowering duplicates that path-allocation
    logic again with `${loop.index}` in the path;
  - `_resume_start_bundle_ref(...)` and `_call_result_bundle_input_name(...)`
    recover workflow-call bundle paths separately from normal call lowering.
- `orchestrator/workflow_lisp/contracts.py`
  - already defines `GeneratedInternalInput` and
    `WorkflowBoundaryProjection.generated_internal_inputs`.
- `tests/test_workflow_lisp_phase_stdlib.py`
  - already proves `review-revise-loop` and composed `with-phase` reuse
    preserve generated write-root inputs and projection metadata.
- `tests/test_workflow_lisp_examples.py`
  - already proves reusable review-phase call sites receive generated
    `__write_root__` bindings under `.orchestrate/workflow_lisp/calls/...`.
- `tests/test_subworkflow_calls.py`
  - already proves the runtime rejects hard-coded DSL-managed write roots and
    colliding write-root bindings.

That means the missing behavior is not a new runtime capability. It is one
frontend-owned boundary contract that keeps discovery and allocation coherent.

## Internal Boundary Contract

### 1. Managed Write-Root Requirement Discovery

Add one lowering-only concept:

```text
ManagedWriteRootRequirement
  generated_name
  source_kind        # lowered_same_file | private_workflow | imported_bundle
  reason             # currently managed_write_root
```

Rules:

- For a lowered same-file callee, requirements come from
  `lowered_callee.boundary_projection.generated_internal_inputs` filtered to
  `reason == "managed_write_root"`.
- For a generated private workflow callee, use the same lowered-workflow path;
  private-workflow status does not create a second discovery model.
- For an imported bundle, continue using
  `workflow_managed_write_root_inputs(...)` from the validated runtime surface.
- For lowered same-file callees only, a raw authored-input prefix scan remains
  a compatibility fallback when projection metadata is unavailable, but the
  preferred authority is the projection metadata because it already carries the
  source-mapped reason.

This keeps the typed boundary transport explicit without widening runtime
semantics.

### 2. Deterministic Caller Allocation Helper

Add one shared allocation helper that receives:

- caller workflow name;
- generated call step name;
- callee callable name;
- discovered managed requirement names;
- optional iteration scope token.

It returns ordinary `with` bindings using the current deterministic layout:

```text
.orchestrate/workflow_lisp/calls/<caller>/<call-step>/<callee>/<generated-input>.json
```

or, when an iteration scope token is present:

```text
.orchestrate/workflow_lisp/calls/<caller>/<call-step>/<iteration-scope>/<callee>/<generated-input>.json
```

Rules:

- same-file workflow calls and private-workflow procedure calls pass no
  iteration scope token;
- `backlog-drain` and other loop-managed reusable call sites pass the current
  loop token `${loop.index}` exactly as today;
- the helper sorts requirement names deterministically before binding emission;
- the helper does not change the visible naming convention or the caller-owned
  root prefix.

This centralizes the policy that prior slices kept semantically unchanged while
removing the repeated string formatting logic.

### 3. Call-Site Consumers

The following lowering paths must consume the shared discovery and allocation
helpers:

- `_lower_call_expr(...)`
  - discover managed requirements from the lowered callee or imported bundle;
  - append allocated bindings into `step["with"]` after ordinary authored
    parameter flattening;
  - keep ordinary call output projection unchanged.
- the private-workflow branch of `_lower_procedure_call_expr(...)`
  - discover managed requirements from the generated private workflow boundary
    projection;
  - allocate bindings through the same helper used by workflow calls;
  - keep inline procedure calls unchanged because they do not cross a runtime
    workflow boundary.
- `_managed_call_step(...)`
  - stop formatting paths itself;
  - use the shared helper with `iteration_scope="${loop.index}"`.

This preserves the current runtime call boundary and the current loop-scoped
disambiguation rule while removing policy drift across call-site families.

### 4. Resume-Or-Start Bundle Recovery Alignment

`resume-or-start` already needs the canonical bundle path for a workflow-call
start arm. This slice makes that recovery use the same managed write-root
boundary contract:

- keep phase-scoped `run-provider-phase`, `produce-one-of`, and provider-result
  bundle-path handling unchanged;
- when the start arm is a workflow call, recover the relevant generated bundle
  input name through the same managed requirement discovery path used by normal
  call lowering;
- derive the bundle path with the same caller/call-step/callee allocation
  helper rather than reconstructing a parallel path rule.

This keeps reusable phase recovery aligned with ordinary reusable call
transport.

### 5. Diagnostics And Provenance

Prefer existing diagnostic families where possible:

- keep `proc_private_workflow_boundary_invalid` authoritative when a procedure
  still cannot cross the reusable/private boundary at all;
- keep `resume_or_start_contract_invalid` authoritative when a workflow-call
  start arm cannot prove one canonical bundle path;
- reuse `workflow_boundary_projection_missing_origin` or a similarly narrow
  projection diagnostic if lowered same-file boundary metadata is internally
  inconsistent.

No new runtime diagnostic family is required. The important change is that the
same-file boundary authority moves from repeated prefix scans toward the
existing source-mapped projection metadata.

## Test Strategy

Add or update focused tests that prove the contract across the current pressure
points:

- `tests/test_workflow_lisp_phase_stdlib.py`
  - existing reusable review-loop/private-workflow regression continues to pass;
  - add a reusable helper around `run-provider-phase` that lowers through a
    private workflow and receives generated write-root bindings through the
    shared helper.
- `tests/test_workflow_lisp_lowering.py`
  - assert same-file workflow-call lowering and private-workflow procedure-call
    lowering both allocate managed write-root bindings through the same visible
    path layout;
  - keep current result-bundle path assertions for `resume-or-start` aligned
    with the shared helper.
- `tests/test_workflow_lisp_examples.py`
  - keep the current review-phase example proving reusable workflow calls bind
    generated write roots under `.orchestrate/workflow_lisp/calls/...`.
- `tests/test_workflow_lisp_build_artifacts.py`
  - keep proving `boundary_projection.generated_internal_inputs` records
    `reason == "managed_write_root"`.
- `tests/test_subworkflow_calls.py`
  - keep runtime guardrails proving hard-coded or colliding write-root bindings
    are still rejected; this slice must not weaken those checks.

## Acceptance Conditions

- generated write-root requirements for same-file reusable callees flow through
  one explicit boundary contract instead of repeated raw input-name scans;
- same-file workflow calls, private-workflow procedure calls, and loop-managed
  reusable call sites allocate caller-owned write-root bindings through one
  deterministic helper;
- `review-revise-loop` and `run-provider-phase` remain reusable inside private
  workflows without adding bespoke call-site write-root logic;
- `resume-or-start` workflow-call start arms recover canonical bundle paths
  through the same managed write-root policy;
- imported-bundle compatibility and current `.orchestrate/workflow_lisp/calls`
  path layout remain intact;
- no new runtime value type, adapter, helper script, or runtime-native effect
  is introduced.
