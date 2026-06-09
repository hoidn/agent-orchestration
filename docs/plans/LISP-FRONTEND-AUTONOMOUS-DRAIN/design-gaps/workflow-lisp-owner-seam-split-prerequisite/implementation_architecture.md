# Workflow Lisp Owner-Seam Split Prerequisite Implementation Architecture

Status: draft
Design gap id: `workflow-lisp-owner-seam-split-prerequisite`
Target design: `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_mvp_specification.md`

## Scope

This slice covers exactly the bounded prerequisite selected by the current
drain state before more Track A or parametric/type-system work proceeds:

- split the current oversized public facades so the selected procedure-related
  seams no longer live only inside `compiler.py`, `typecheck.py`, or
  `lowering.py`;
- record one exact post-split owner module path for each required seam:
  procedure-call typechecking integration,
  specialization discovery/materialization integration,
  and procedure-call lowering/provenance/runtime-erasure;
- convert `orchestrator.workflow_lisp.lowering` from a single file into a
  package facade so procedure lowering can move behind a stable import surface
  without breaking existing callers;
- keep the work behavior-preserving: no authored `.orc` syntax changes, no
  runtime behavior changes, no source-map weakening, and no new workflow
  semantics;
- add only the characterization and architecture-boundary tests needed to prove
  the seam ownership move.

Out of scope for this slice:

- Track A form-registry expansion, denylist removal, or imported `.orc`
  expansion work;
- parametric `defproc`, structural constraints, loop exhaustion projection, or
  ordinary stdlib `review-revise-loop` authoring;
- broad refactors of unrelated typecheck, lowering, diagnostics, or stdlib
  families beyond what is necessary to establish the exact owner seams named
  here;
- shared runtime, validation, Core Workflow AST, Semantic Workflow IR,
  TypeCatalog, SourceMap, pointer-authority, or variant-proof redesign;
- new scripts, command adapters, runtime-native effects, or command-boundary
  policy changes.

This is a bounded implementation architecture for the owner-seam split
prerequisite only. It does not replace the parent frontend design, the MVP
baseline, or the broader review/revise stdlib integration design.

## Problem Statement

The target integration design makes one sequencing rule explicit: no new Track
A or parametric/type-system behavior should land while the affected procedure
seams still live only inside oversized public facades.

The current checkout still has that exact shape:

1. `typecheck.py` owns the `ProcedureCallExpr` branch inside the monolithic
   `_typecheck(...)` dispatcher and also owns generated-procedure typing used by
   review-loop specialization.
2. `compiler.py` owns procedure-definition typing orchestration, proc-ref
   specialization discovery, and the bridge that imports
   `_specialize_typed_procedure(...)` from lowering.
3. `lowering.py` owns procedure lowering, private-workflow eligibility,
   specialization materialization, provenance notes, and the practical
   runtime-erasure boundary for compile-time-only ProcRef and WorkflowRef data.
4. The three required seams therefore cross pass boundaries through private
   helper imports and duplicated local walkers instead of explicit owner
   modules.
5. The three facades are already well above the refactor-safe size target:
   `compiler.py` is 3,370 physical lines,
   `typecheck.py` is 6,026 physical lines,
   and `lowering.py` is 11,062 physical lines in the current checkout.

That is not only a cleanliness problem. It creates the concrete extension risk
called out by the target design:

- a new procedure-call typing rule can be added to `typecheck.py` while the
  specialization planner in `compiler.py` or runtime-erasure guard in lowering
  silently stays stale;
- a new specialization dimension can be added in lowering while compiler
  discovery still imports the old private helper path;
- a new lowering/provenance rule can land in `lowering.py` without one obvious
  owner module for source-map and runtime-erasure responsibilities.

The selected gap is therefore the smallest honest prerequisite before further
Track A or parametric work:

- establish exact owner modules for the named seams;
- move the current implementations behind those owners;
- leave the public facades as compatibility/coordinator surfaces rather than
  the only places where the semantics live.

## Design Constraints

The implementation must stay coherent with:

- `docs/index.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  - `8.1 Hard Preflight Before Track A`
  - `9.4 Split Oversized Public Facade Owner Seams Before New Type-System Work`
  - `24. Incremental Implementation Plan`
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
- `docs/design/workflow_lisp_refactor_architecture.md`
- `docs/plans/2026-06-02-workflow-lisp-low-hanging-refactor-plan.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/work_instructions.md`
- `docs/steering.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/prerequisite-selector/selection.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/architecture-targets.json`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/existing-architecture-index.md`
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json`

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse the existing provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  macro expansion stacks,
  `LispFrontendDiagnostic`,
  `LoweringOrigin`,
  and `LoweringOriginMap`;
- keep the move behavior-preserving:
  no authored `.orc` syntax changes,
  no runtime behavior changes,
  no relaxed diagnostics,
  and no hidden new execution path;
- keep ProcRef, WorkflowRef, provider refs, prompt refs, and future type
  parameters compile-time-only at the runtime boundary;
- keep structured bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations.

`docs/design/workflow_command_adapter_contract.md` is authoritative here even
though this slice introduces no new adapters. The selected seams already carry
`command-result` behavior, certified-adapter provenance, and output-contract
validation through procedure typechecking and lowering. The owner split must not
create a loophole where command semantics become hidden behind new helper
modules.

`docs/steering.md` is empty in this checkout. That is not permission to widen
scope. The selection bundle and target design remain the effective steering
surfaces.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

The full index in
`state/LISP-FRONTEND-AUTONOMOUS-DRAIN/drain/iterations/4/design-gap-architect/existing-architecture-index.md`
was reviewed for coherence. The directly reused slices for this gap are:

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/module-import-export-resolution/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/source-map-runtime-lineage/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/track-a-form-registry-elaboration-boundary/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-core-ast-lowering-structured-results/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-parametric-defproc-specialization-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-lisp-review-revise-preflight-hazard-fixes/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-refs-compile-time-linking/implementation_architecture.md`

### Decisions Reused

- Reuse the staged frontend pipeline and package ownership split.
- Reuse the current procedure substrate:
  `ProcedureDef`,
  `ProcedureSignature`,
  `TypedProcedureDef`,
  `ProcedureCatalog`,
  `ProcedureCallableSpecialization`,
  `ResolvedProcRefValue`,
  and `ResolvedWorkflowRef`.
- Reuse the existing source-map/runtime-lineage substrate:
  `LoweringOrigin`,
  `LoweringOriginMap`,
  and the persisted `source_map.json` bridge remain authoritative.
- Reuse the compile-time-only ProcRef and WorkflowRef rules from the
  workflow-ref and parametric-specialization slices:
  no runtime ref values,
  deterministic specialization naming,
  visible effect summaries,
  and compile-time cycle detection.
- Reuse the defproc substrate's split between compile-time procedure planning
  and runtime-visible workflow lowering rather than inventing a second executor
  or a new runtime procedure model.
- Reuse the preflight hazard-fix sequencing rule:
  this owner-seam move is still behavior-preserving and must not bundle in
  Track A or new type-system semantics.

### New Decisions In This Slice

- Establish one exact owner module for each required seam:
  - `orchestrator/workflow_lisp/procedure_typecheck.py`
  - `orchestrator/workflow_lisp/procedure_specialization.py`
  - `orchestrator/workflow_lisp/lowering/procedures.py`
- Convert `orchestrator.workflow_lisp.lowering` into a package facade so the
  lowering seam can move behind a stable import surface while preserving public
  imports.
- Move `_specialize_typed_procedure(...)` out of lowering and into the
  specialization owner module so compiler discovery no longer depends on a
  lowering-private helper import.
- Keep `compiler.py`, `typecheck.py`, and `orchestrator.workflow_lisp.lowering`
  as compatibility/coordinator facades only for these seams; new behavior on the
  named seams must land in the owner modules, not back in the facades.
- Add explicit runtime-erasure checks to the procedure-lowering owner module so
  later type-parameter work has one established runtime-boundary owner.

### Conflicts Or Revisions

The defproc substrate and later feature slices assumed the existing public
facades could continue owning procedure semantics directly. This slice revises
that implementation shape narrowly:

- the public facades remain valid import and orchestration surfaces;
- they stop being the only owner of the selected procedure seams;
- future Track A and parametric work must target the new owner modules instead
  of extending the facades directly.

This slice does not revise shared concepts such as Core Workflow AST, Semantic
Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant proof. It
also does not claim that all remaining unrelated code in `compiler.py` or
`typecheck.py` is now fully decomposed; it only makes the selected seams stop
living exclusively there.

## Ownership Boundaries

This slice owns:

- the exact post-split owner module paths for the three required seams;
- the lowering package-facade conversion needed to create a stable owner path
  under `orchestrator.workflow_lisp.lowering`;
- mechanical extraction of procedure-call typing, specialization planning, and
  procedure lowering/provenance/runtime-erasure into those owner modules;
- compatibility re-exports and delegating wrappers that preserve the current
  public import surfaces;
- focused tests that prove the owner seams moved without behavior changes.

This slice intentionally does not own:

- Track A imported `.orc` expansion, stdlib extension de-specialization, or
  review-loop bridge removal;
- generic `defproc`, structural constraints, or loop exhaustion semantics;
- broad remaining decomposition of unrelated branches in `compiler.py`,
  `typecheck.py`, or lowering after the selected seams are extracted;
- shared runtime/validation redesign or new command-adapter policy.

## Current Checkout Facts

The current checkout confirms the selected prerequisite directly:

- `orchestrator/workflow_lisp/compiler.py` is 3,370 physical lines and owns:
  `_typecheck_procedure_definitions(...)`,
  `_procedure_catalog_with_specializations(...)`,
  `_bound_proc_ref_request(...)`,
  and `_discover_proc_ref_specializations(...)`.
- `compiler.py` imports `_specialize_typed_procedure(...)` from lowering,
  which means specialization materialization currently depends on a
  lowering-private helper.
- `orchestrator/workflow_lisp/typecheck.py` is 6,026 physical lines and owns
  the `ProcedureCallExpr` branch inside `_typecheck(...)`, along with
  `_typecheck_generated_procedure(...)` and generated-local-procedure plumbing
  used by review-loop specialization and `let-proc`.
- `typecheck.py` still relies on multiple module-global active-context
  structures such as `_ACTIVE_PROC_REF_VALUE_ENV`,
  `_ACTIVE_GENERATED_LOCAL_PROCEDURES`,
  `_ACTIVE_FUNCTION_CATALOG`,
  and `_ACTIVE_LOOP_CONTEXT`.
- `orchestrator/workflow_lisp/lowering.py` is 11,062 physical lines and owns:
  `_resolve_procedure_lowering(...)`,
  `_lower_procedure_call_expr(...)`,
  `_specialize_typed_procedure(...)`,
  `_private_workflow_from_procedure(...)`,
  `_procedure_provenance_notes(...)`,
  and the private-workflow boundary/body analysis helpers.
- import inventory shows external callers already import through the stable
  facade path `orchestrator.workflow_lisp.lowering`; the current public path is
  therefore package-convertible as long as `__init__.py` preserves the exported
  names and test-visible helper re-exports.
- `form_registry.py` already exists, so later Track A work will have a natural
  consumer for the split seams once they stop living only in the facades.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` still contains no
  events, so no later recorded implementation state supersedes this selected
  prerequisite.

## Feasibility Proof

This slice changes ownership boundaries, not language semantics. The move is
feasible on the current checkout for three concrete reasons:

1. The required data types already exist.
   `procedures.py`, `procedure_refs.py`, and `workflow_refs.py` already define
   the procedure and specialization dataclasses this split needs; no new
   semantic schema is required to move the owner seams.
2. The public lowering path is already facade-shaped.
   Current callers import `orchestrator.workflow_lisp.lowering`, not
   `lowering.py` by filename. Converting that module path into a package facade
   preserves the public import contract while allowing internal ownership to
   move.
3. The current compiler/lowering interaction is already explicit enough to
   extract.
   `compiler.py` today imports `_specialize_typed_procedure(...)` as a private
   helper from lowering. Replacing that with a dedicated
   `procedure_specialization.py` owner is a mechanical dependency cleanup, not a
   new semantic feature.

The architecture therefore requires no speculative runtime capability. It
reuses existing typed procedure objects, existing provenance data, and the
existing authored-mapping -> shared-validation seam.

## Proposed Package Boundary

The exact post-split owner modules for this slice are:

```text
orchestrator/workflow_lisp/
  compiler.py                       # public compile coordinator facade
  procedure_typecheck.py            # NEW owner: procedure-call typing + generated procedure typing
  procedure_specialization.py       # NEW owner: specialization discovery + materialization
  typecheck.py                      # public expression-typecheck facade
  lowering/
    __init__.py                     # NEW public lowering facade preserving existing imports
    core.py                         # moved non-procedure lowering entrypoints/context
    procedures.py                   # NEW owner: procedure lowering/provenance/runtime-erasure
```

Responsibilities:

- `procedure_typecheck.py`
  - own the `ProcedureCallExpr` typecheck branch;
  - own generated-procedure typing used by review-loop specialization and
    `let-proc`;
  - own procedure-definition typing orchestration currently embedded in
    `compiler.py`;
  - receive explicit context objects or explicit parameters from `typecheck.py`
    and `compiler.py` rather than owning public entrypoints.
- `procedure_specialization.py`
  - own proc-ref and workflow-ref specialization discovery;
  - own `_specialize_typed_procedure(...)` materialization;
  - own procedure-catalog augmentation helpers related to specialization;
  - own lowering-mode planning and private-workflow eligibility analysis needed
    during specialization.
- `lowering/procedures.py`
  - own `_lower_procedure_call_expr(...)`;
  - own private-workflow wrapper synthesis for procedures;
  - own procedure provenance-note generation;
  - own runtime-erasure guards that assert no compile-time-only procedure
    bindings leak into lowered workflow state, call bindings, output contracts,
    or source-map payloads.
- `compiler.py`
  - stay the pipeline coordinator only;
  - delegate procedure typing and specialization work to the owner modules.
- `typecheck.py`
  - stay the top-level expression dispatcher and compatibility wrapper for the
    current active-context plumbing;
  - delegate procedure-call typing and generated-procedure typing to
    `procedure_typecheck.py`.
- `lowering/__init__.py`
  - preserve the public `orchestrator.workflow_lisp.lowering` import path and
    re-export the existing public/test-visible symbols that callers already use.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/procedures.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/workflow_refs.py`
- `orchestrator/workflow_lisp/source_map.py`
- `orchestrator/workflow_lisp/contracts.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Internal Coordination Model

This slice introduces only small internal coordination records so the new owner
modules can accept explicit inputs without forcing a full `TypecheckContext`
redesign now.

### `ProcedureTypecheckContext`

`procedure_typecheck.py` should own one small internal context object carrying
the current procedure-related typecheck dependencies:

- `type_env`
- `value_env`
- `proof_scope`
- `workflow_catalog`
- `procedure_catalog`
- `function_catalog`
- `extern_environment`
- `command_boundary_environment`
- `procedure_effects_by_name`
- `workflow_effects_by_name`
- `proc_ref_resolution_context`
- active proc-ref/value-expression/generated-procedure handles currently stored
  in `typecheck.py`

`typecheck.py` remains responsible for compatibility with the current
module-global wrappers, but the owner module receives one explicit object rather
than reaching back into unrelated branches.

### `ProcedureSpecializationRequest`

`procedure_specialization.py` should own one small request object describing a
single specialization operation:

- base `TypedProcedureDef`
- workflow-ref bindings
- proc-ref bindings
- value bindings
- remaining params
- workflow path
- type environment
- typed procedures by name
- origin span/form path

This is compile-time-only metadata. It must never cross into lowered runtime
structures.

### `ProcedureLoweringPlan`

`lowering/procedures.py` should own one resolved lowering plan for a procedure
call site:

- selected `TypedProcedureDef`
- resolved argument list after any compile-time specialization
- chosen lowering mode:
  `inline` or `private-workflow`
- provenance note payload
- runtime-erasure proof inputs for the selected specialization

The plan is internal to lowering. It does not create a second semantic IR.

## Proposed Architecture

### 1. Procedure-Call Typechecking Owner

Move the procedure-call branch out of the giant `_typecheck(...)` body and into
`procedure_typecheck.py`.

The owner module should expose narrow helpers such as:

- `typecheck_procedure_call_expr(...)`
- `typecheck_procedure_definition(...)`
- `typecheck_generated_procedure(...)`
- `drain_generated_local_procedures(...)`

`typecheck.py` continues to:

- dispatch on expression families;
- manage the current compatibility wrappers for active proc-ref/function/loop
  state;
- call back into existing non-procedure branches unchanged.

All future edits involving:

- direct procedure-call arity/type/effect checking,
- bound ProcRef call handling,
- forwarded generic ProcRef handling,
- generated helper procedure typing,
- procedure-call-specific diagnostics,

must land in `procedure_typecheck.py`, not back in `typecheck.py`.

### 2. Specialization Discovery And Materialization Owner

Create `procedure_specialization.py` as the only owner of compile-time procedure
specialization planning.

Move these responsibilities behind it:

- `_procedure_catalog_with_specializations(...)`
- `_bound_proc_ref_request(...)`
- `_discover_proc_ref_specializations(...)`
- `_specialize_typed_procedure(...)`
- procedure lowering-mode planning and private-workflow eligibility analysis
  used while materializing specialized procedures

This move is the key dependency cleanup:

- `compiler.py` stops importing specialization behavior from lowering;
- later parametric specialization extends the specialization owner module
  instead of threading new logic across compiler and lowering simultaneously;
- workflow-ref and ProcRef specialization share one compile-time materialization
  owner before generic type-parameter specialization is added.

### 3. Procedure Lowering / Provenance / Runtime-Erasure Owner

Create `orchestrator/workflow_lisp/lowering/procedures.py` as the runtime-side
owner for procedure lowering.

Move these responsibilities behind it:

- `_lower_procedure_call_expr(...)`
- `_private_workflow_from_procedure(...)`
- `_procedure_provenance_notes(...)`
- inline child-context creation for procedure bodies
- runtime-erasure checks for compile-time-only specialization payloads

The owner module must make runtime erasure explicit instead of incidental.
Before emitting a call step or a private-workflow wrapper, it should assert that
the selected procedure specialization has already erased compile-time-only data
from runtime-visible surfaces:

- no ProcRef value in lowered workflow state;
- no WorkflowRef value in lowered workflow state;
- no provider or prompt ref value transported as runtime data;
- no future type-parameter placeholder surviving into lowered workflow
  contracts, source-map payloads, or runtime call bindings.

This owner remains responsible for source-map provenance notes because it is the
last frontend boundary before runtime-shaped workflow dictionaries exist.

### 4. Lowering Facade Conversion

This slice includes the pure ownership move required to make the lowering owner
module path stable:

- rename the current `lowering.py` implementation body into
  `lowering/core.py`;
- add `lowering/__init__.py` as the public facade;
- move procedure-specific lowering logic into `lowering/procedures.py`;
- keep public/test-visible imports working through the package facade.

The facade must preserve the current import contract for:

- `LoweredWorkflow`
- `LoweringOrigin`
- `LoweringOriginMap`
- `lower_workflow_definitions(...)`
- `validate_lowered_workflows(...)`
- any currently exercised test-visible helper re-exports that remain in use
  during the transition

### 5. Facade Rules After The Split

After this slice lands:

- `compiler.py`, `typecheck.py`, and `orchestrator.workflow_lisp.lowering`
  remain compatibility facades and coordinators;
- the selected seams may call through those facades, but the facades are no
  longer the only owner of the behavior;
- future Track A or parametric changes must cite the owner module paths from
  this document instead of naming only the public facades.

## Diagnostics And Tests

The split is behavior-preserving, so verification should focus on ownership
movement and unchanged observable behavior.

Required test coverage:

- procedure-call typing regressions in
  `tests/test_workflow_lisp_procedures.py`
- lowering/provenance regressions in
  `tests/test_workflow_lisp_lowering.py`
- workflow-ref specialization regressions in
  `tests/test_workflow_lisp_workflow_refs.py`
- review-loop generated-procedure regressions in
  `tests/test_workflow_lisp_phase_stdlib.py`

Required new assertions:

- `orchestrator.workflow_lisp.lowering` remains importable as a package facade;
- compiler specialization no longer imports `_specialize_typed_procedure(...)`
  from lowering;
- procedure call typechecking still preserves direct, bound-proc-ref, forwarded
  proc-ref, and workflow-ref argument behavior;
- specialization naming and origin spans remain deterministic across the moved
  owner module;
- lowered workflows still preserve procedure call-site and definition
  provenance notes;
- runtime-erasure checks fail closed if compile-time-only procedure data reaches
  runtime-visible lowering surfaces.

Architectural denylist checks for this slice should be narrow:

- no new procedure specialization helper may be added back to `compiler.py`;
- no new procedure-call typing branch may be added directly to `typecheck.py`
  outside delegation glue;
- no new procedure runtime-erasure check may be added directly to
  `lowering/core.py`.

## Verification Scope Boundary

This gap's acceptance evidence is intentionally narrower than a full
module-family health sweep. Required completion evidence for this slice is:

- the new owner-boundary tests introduced for the package facade, compiler
  specialization ownership, delegating compatibility surfaces, provenance, and
  runtime-erasure ownership;
- the reused focused regressions named in the execution plan for procedure
  typing, specialization, lowering provenance, workflow-ref forwarding, and
  generated review-loop helper typing;
- `pytest --collect-only` for the touched test modules;
- `python -m compileall orchestrator/workflow_lisp`;
- the narrow compile -> lower -> shared-validation integration slice named in
  the execution plan;
- `git diff --check`.

Broader module-wide suites over the touched test files may still be run as a
drift audit, but they are not the acceptance gate for this bounded
prerequisite. If such an audit fails, the implementer must classify each
failure explicitly:

- selected-seam regression
  : block this slice because the failure contradicts the claimed owner-seam
    move or behavior-preserving contract;
- unrelated touched-surface failure
  : record the exact selector, command, and reason in the progress report and
    defer it outside this gap unless fixing it is strictly required to restore
    the owner-seam contract;
- pre-existing unrelated failure
  : record the exact selector, command, and reason in the progress report and
    do not widen this gap.

This classification rule is required because the selected prerequisite is about
exact seam ownership, not complete phase-stdlib or reusable-phase-state health.
An unrelated failure found by a broad audit must not silently redefine this
slice into a wider repair tranche.

## Implementation Sequence

1. Convert `orchestrator.workflow_lisp.lowering` into a package facade with no
   behavior changes.
2. Extract `procedure_specialization.py` and move specialization discovery /
   materialization / lowering-mode planning behind it.
3. Extract `procedure_typecheck.py` and delegate procedure-related typing from
   `compiler.py` and `typecheck.py`.
4. Extract `lowering/procedures.py` and route procedure lowering, provenance,
   and runtime-erasure through it.
5. Add focused characterization and architecture-boundary tests.
6. Update `orchestrator/workflow_lisp/README.md` so the package ownership map
   records the new seam owners.

This order matters:

- specialization leaves lowering first so compiler stops reaching into lowering
  internals early;
- typecheck and lowering then converge on explicit owner modules before any new
  type-parameter or imported-stdlib behavior lands.

## Acceptance Conditions

This prerequisite is complete when:

- the architecture records the exact post-split owner module path for each
  required seam:
  `procedure_typecheck.py`,
  `procedure_specialization.py`,
  and `lowering/procedures.py`;
- `orchestrator.workflow_lisp.lowering` remains the public import facade after a
  package conversion;
- compiler specialization no longer depends on a lowering-private helper import;
- procedure-call typing, specialization planning/materialization, and procedure
  lowering/provenance/runtime-erasure no longer live only inside the oversized
  public facades;
- the move is behavior-preserving on the focused procedure, workflow-ref,
  review-loop-generated-procedure, and lowering provenance regressions named by
  this gap's execution plan;
- the required completion evidence from `Verification Scope Boundary` is
  recorded and passes;
- any additional broad module-suite failures are explicitly classified and
  recorded as selected-seam regressions or out-of-scope drift findings rather
  than silently widening the slice;
- future Track A and parametric plans can cite the landed owner modules instead
  of extending `compiler.py`, `typecheck.py`, or `lowering.py` directly.

## Verification Plan

Before declaring the slice ready for implementation, record deterministic checks
that prove:

- the required architecture, context, checks, and bundle files exist;
- the architecture contains the required
  `Relationship To Existing Implementation Architectures` section;
- the work-item context records
  `docs/design/workflow_command_adapter_contract.md`
  as an authoritative input;
- the architecture names the exact owner modules:
  `procedure_typecheck.py`,
  `procedure_specialization.py`,
  and `lowering/procedures.py`;
- the architecture cites both the target design and the MVP baseline.
