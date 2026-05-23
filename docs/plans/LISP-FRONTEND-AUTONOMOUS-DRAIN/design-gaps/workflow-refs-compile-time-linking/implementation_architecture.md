# Workflow Refs Compile-Time Linking Implementation Architecture

## Scope

This design gap covers only the bounded compile-time `WorkflowRef` tranche
selected by the current drain state:

- add a frontend-owned `WorkflowRef[...]` type surface for `defworkflow` and
  `defproc` parameter positions;
- resolve workflow-ref literals to same-file workflows, linked `.orc` module
  exports, or explicitly registered imported bundles through deterministic
  compile-time linking;
- validate workflow-ref signature compatibility, authority source, and
  compile-time-only usage rules for higher-order composition such as
  `backlog-drain`;
- specialize higher-order procedures and workflows at compile time so lowered
  workflows expose only ordinary runtime-callable boundaries;
- lower calls through workflow-ref parameters back onto the existing
  imported-bundle and shared-validation seam without runtime workflow loading.

Out of scope for this tranche:

- runtime workflow loading, dynamic code lookup, or runtime-carried
  `WorkflowRef` values;
- storing `WorkflowRef` inside records, unions, lists, maps, provider results,
  command results, workflow inputs, or workflow outputs;
- redesign of `backlog-drain`, `resource-transition`, `finalize-selected-item`,
  or queue/resource semantics beyond replacing their provisional workflow-ref
  plumbing with the generic layer owned here;
- a general authored extern-rebinding surface for provider/prompt transport;
- redesign of shared Core Workflow AST, Semantic Workflow IR, TypeCatalog,
  SourceMap, pointer authority, variant proof, runtime state persistence, or
  the existing command-adapter policy.

This is an implementation architecture for the selected compile-time linking
gap only. It does not authorize widening the work into runtime plugin-style
workflow loading or a broader higher-order value system.

## Design Constraints

The implementation must stay coherent with:

- `docs/design/workflow_lisp_frontend_specification.md`
  Sections 7.7, 14, 15, 52, 58, 74, and 108;
- `docs/design/workflow_lisp_frontend_mvp_specification.md`
  especially the deferred/non-goal boundaries around `WorkflowRef`,
  runtime code loading, and backlog-drain scope;
- `docs/design/workflow_command_adapter_contract.md`;
- `docs/steering.md`;
- the Stage 1-7 frontend package boundaries and lowering seam already
  established in prior implementation architectures.

The slice must also preserve these guardrails:

- keep `orchestrator/workflow_lisp/` as the frontend-owned package and keep
  shared runtime semantics under `orchestrator/workflow/`;
- reuse the staged frontend pipeline:
  read -> syntax -> macro expansion -> definitions/procedures/workflows ->
  typecheck -> lowering -> shared validation;
- reuse `SourcePosition`, `SourceSpan`, `LispFrontendDiagnostic`,
  macro-expansion provenance, and `LoweringOriginMap` as the only provenance
  channel;
- reuse module-link canonical callable keys, imported-bundle lowering, and the
  existing shared authored-mapping -> validation bridge instead of generating
  YAML text or a second validator;
- keep workflow refs compile-time-only in v0.1;
- keep typed bundles authoritative, reports as views, artifact values as
  authority, and pointer files as representations;
- keep provider/prompt transport on the existing extern model or a
  compiler-owned rebinding plan; do not invent runtime transport of provider or
  prompt values through `WorkflowRef` calls;
- do not treat the empty `docs/steering.md` file in this checkout as implicit
  permission to widen scope.

`docs/design/workflow_command_adapter_contract.md` remains authoritative even
though this slice should not add new adapter behavior. Higher-order linking must
not create a loophole where dynamic workflow selection smuggles uncertified
command boundaries past the existing compile-time classification.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/core-workflow-ast-shared-contract/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defun-pure-helper-surface/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/executable-ir-runtime-plan/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-required-lints/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/frontend-validation-diagnostics-pipeline/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/hygienic-defmacro-system/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/lisp-frontend-cli-diagnostics-surface/implementation_architecture.md`
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

### Decisions Reused

- Reuse the existing staged frontend pipeline and package ownership split.
- Reuse the Stage 1-7 provenance substrate:
  `SourcePosition`,
  `SourceSpan`,
  recursive syntax objects,
  `LispFrontendDiagnostic`,
  macro expansion stacks,
  and `LoweringOriginMap`.
- Reuse `FrontendTypeEnvironment`, `EffectSummary`, the procedure/workflow
  catalogs, and the current same-file/imported-bundle callable model rather
  than inventing a parallel higher-order execution path.
- Reuse the canonical callable key and module-link rules from the
  module/import/export slice:
  imported workflow targets resolve to module-qualified callable identities
  before typechecking or lowering.
- Reuse the validation-pipeline and required-lints ownership split:
  workflow-ref-specific errors remain frontend-owned diagnostics and lint
  coverage, not a new shared-validation category or runtime warning surface.
- Reuse Stage 3 and later lowering through the existing authored mapping ->
  `elaborate_surface_workflow(...)` -> `lower_surface_workflow(...)` shared
  seam.
- Reuse the current union workflow-call boundary projection and Stage 2 proof
  rules when a resolved workflow ref returns a union.
- Reuse the resource/drain slice's role semantics for `selector`, `run-item`,
  and `gap-drafter` as a consumer of workflow refs, not as a second workflow-ref
  system.
- Reuse the source-map/runtime-lineage contract for specialized callable
  provenance and keep Core AST, Semantic IR, and runtime-plan ownership
  unchanged because all workflow-ref parameters must disappear before those
  shared bundle surfaces are constructed.

### New Decisions In This Slice

- Add a public frontend `WorkflowRef[...]` type surface, but keep it legal only
  in compile-time-specialized parameter positions for `defworkflow` and
  `defproc`.
- Add one frontend-owned workflow-ref linker/specializer layer that resolves
  concrete workflow targets and removes workflow-ref parameters before the
  lowered runtime boundary is constructed.
- Treat `WorkflowRef` arguments as compile-time literals or forwarded
  compile-time bindings only; they are not ordinary data values and must never
  cross a runtime workflow boundary.
- Generalize the provisional drain-specific workflow-ref metadata into a shared
  frontend layer consumed by ordinary higher-order calls and by stdlib forms
  such as `backlog-drain`.
- Separate workflow-ref compatibility into two checks:
  structural signature compatibility and extern-closure compatibility.
- Keep generic authored workflow-ref use closed over provider/prompt externs in
  v0.1. Library-owned forms such as `backlog-drain` may additionally provide a
  compiler-owned extern rebinding plan, but this slice does not introduce a
  user-authored extern-mapping surface.
- Make workflow-ref specialization deterministic and source-mapped by deriving a
  stable specialization key from the callee identity plus resolved workflow-ref
  bindings.

### Conflicts Or Revisions

The Stage 6 resource/drain slice intentionally kept workflow refs narrow:

- workflow refs were not a public frontend type surface;
- only compiler-owned stdlib operand positions could consume them;
- drain-specific metadata in `resource.py` and `typecheck.py` owned resolution
  directly.

This slice revises those assumptions narrowly:

- `WorkflowRef[...]` becomes a first-class frontend type in parameter
  positions;
- the generic workflow-ref layer becomes the sole authority for compile-time
  workflow-ref resolution and specialization;
- `backlog-drain` continues to enforce selector/run-item/gap-drafter role
  shapes, but it does so on top of the generic layer rather than through a
  parallel resolver.

The Stage 3 workflow-lowering slice also assumed all workflow parameters were
runtime-boundary-lowerable types. This slice narrows that assumption rather
than discarding it:

- non-`WorkflowRef` parameters still lower through the existing boundary
  projection rules;
- `WorkflowRef` parameters are compile-time-only and must be stripped by
  specialization before runtime-boundary flattening runs.

No prior slice is reversed on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- parsing and resolved-type representation for `WorkflowRef[...]` in
  `defworkflow` and `defproc` signatures;
- compile-time elaboration of workflow-ref literal expressions and forwarded
  workflow-ref bindings;
- workflow-ref authority resolution against same-file workflows, linked module
  exports, and explicitly registered imported bundles;
- compile-time structural signature checks for workflow-ref compatibility;
- compile-time extern-closure validation and the generic representation of any
  compiler-owned extern rebinding plan;
- specialization planning and deterministic callable-key generation for
  higher-order procedures and workflows;
- lowering of `call` through workflow-ref parameters into ordinary direct-call
  lowering after specialization;
- source-map/origin tracking for generated specialized callables and calls;
- focused tests and fixtures for workflow-ref typing, linking, specialization,
  diagnostics, and drain/Stage 7 regressions.

This slice intentionally does not own:

- runtime workflow loading, new loader APIs, or a second workflow executor;
- generic first-class higher-order values beyond compile-time workflow refs in
  parameter positions;
- queue/resource semantics, command-adapter behavior, or reusable-state
  validation logic already owned by other slices;
- new provider/prompt transport semantics at runtime;
- redesign of shared validation/runtime modules under `orchestrator/workflow/`.

## Current Checkout Facts

The current checkout already contains provisional workflow-ref machinery:

- `orchestrator/workflow_lisp/resource.py` defines drain-scoped types such as
  `WorkflowRefAuthoritySource`, `ResolvedWorkflowRef`, `WorkflowRefCallPlan`,
  and `WorkflowRefEnvironment`;
- there is still no dedicated generic
  `orchestrator/workflow_lisp/workflow_refs.py` authority layer;
- `orchestrator/workflow_lisp/typecheck.py` enforces selector/run-item/gap
  signature checks directly for `backlog-drain`;
- `orchestrator/workflow_lisp/workflows.py` already carries
  `workflow_ref_*` diagnostics and union-return boundary support;
- `orchestrator/workflow_lisp/modules.py` already provides canonical callable
  keys and linked import/export resolution;
- `tests/test_workflow_lisp_drain_stdlib.py` and Stage 7 fixtures already lock
  down the provisional drain-specific behavior.
- `state/LISP-FRONTEND-AUTONOMOUS-DRAIN/progress_ledger.json` is still empty,
  so there is no later recorded implementation event that supersedes the
  selected compile-time-linking obligation.

This slice should consolidate that behavior, not duplicate it. The drain layer
must end up as a consumer of generic workflow-ref linking rather than its own
authority source.

## Proposed Package Boundary

Extend the current frontend package with one new dedicated workflow-ref layer
and targeted updates to existing compilation modules:

```text
orchestrator/workflow_lisp/
  compiler.py
  expressions.py
  lowering.py
  modules.py
  procedures.py
  resource.py
  resource_stdlib.py
  type_env.py
  typecheck.py
  workflow_refs.py
  workflows.py
```

Planned test and fixture surface:

```text
tests/
  test_workflow_lisp_workflow_refs.py
  test_workflow_lisp_modules.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_workflows.py
  test_workflow_lisp_lowering.py
  test_workflow_lisp_drain_stdlib.py
  test_workflow_lisp_stage7_translation.py
  fixtures/workflow_lisp/valid/workflow_refs_same_file.orc
  fixtures/workflow_lisp/valid/workflow_refs_forwarding.orc
  fixtures/workflow_lisp/modules/valid/workflow_refs/imported_entry.orc
  fixtures/workflow_lisp/modules/valid/workflow_refs/imported_helper.orc
  fixtures/workflow_lisp/invalid/workflow_ref_literal_required.orc
  fixtures/workflow_lisp/invalid/workflow_ref_runtime_transport_invalid.orc
  fixtures/workflow_lisp/invalid/workflow_ref_signature_invalid.orc
  fixtures/workflow_lisp/invalid/workflow_ref_specialization_cycle.orc
  fixtures/workflow_lisp/invalid/workflow_ref_extern_unsatisfied.orc
```

Responsibilities:

- `type_env.py`
  - add `WorkflowRefTypeRef`;
  - keep ordinary scalar/path/record/union types authoritative for non-ref
    surfaces;
  - reject `WorkflowRef` use in record fields, union fields, workflow returns,
    and other runtime-boundary contexts.
- `workflow_refs.py`
  - own `WorkflowRefBinding`, `ResolvedWorkflowRef`,
    `WorkflowRefSpecializationKey`, `WorkflowRefInstantiationPlan`, and
    compatibility helpers;
  - centralize structural signature checks, authority lookup, extern-closure
    checks, and specialization planning;
  - provide one authority surface consumed by `typecheck.py`, `lowering.py`,
    `resource.py`, and `resource_stdlib.py`.
- `workflows.py`
  - accept workflow parameter type expressions that may resolve to
    `WorkflowRefTypeRef`;
  - distinguish compile-time workflow-ref parameters from runtime-boundary
    parameters;
  - register specializable higher-order workflow signatures.
- `procedures.py`
  - mirror the same parameter-type and specialization support for `defproc`;
  - keep procedure lowering-mode policy authoritative for specialized
    procedures.
- `expressions.py`
  - elaborate explicit workflow-ref literals when needed;
  - allow bare or qualified workflow names to resolve as workflow-ref literals
    in positions where a `WorkflowRefTypeRef` is expected;
  - allow `call` heads to be lexical workflow-ref bindings.
- `typecheck.py`
  - validate workflow-ref literal use, forwarding, and higher-order call
    compatibility;
  - reject runtime transport or computed/dynamic workflow-ref values;
  - keep union proof rules authoritative after workflow-ref call typing.
- `lowering.py`
  - specialize higher-order workflows/procedures before emitted runtime
    boundaries are built;
  - lower workflow-ref calls as ordinary direct `call` steps against canonical
    callable keys or imported bundles;
  - preserve provenance for specialized callable generation and rebound calls.
- `modules.py`
  - expose imported workflow exports and canonical callable keys to the generic
    workflow-ref resolver without introducing a second import mechanism.
- `resource.py` and `resource_stdlib.py`
  - consume the generic workflow-ref layer for selector/run-item/gap-drafter
    role validation and drain-loop call planning;
  - stop owning independent workflow-ref authority records.
- `compiler.py`
  - orchestrate resolution, specialization order, imported-bundle dependency
    wiring, and shared-validation handoff.

Shared components intentionally reused, not owned here:

- `orchestrator/workflow_lisp/spans.py`
- `orchestrator/workflow_lisp/syntax.py`
- `orchestrator/workflow_lisp/reader.py`
- `orchestrator/workflow_lisp/macros.py`
- `orchestrator/workflow_lisp/effects.py`
- `orchestrator/workflow_lisp/phase.py`
- `orchestrator/workflow_lisp/phase_stdlib.py`
- shared validation/runtime modules under `orchestrator/workflow/`

## Data Model

### `WorkflowRefTypeRef`

Add a frontend-local resolved type:

- `WorkflowRefTypeRef`
  - `param_type_refs: tuple[TypeRef, ...]`
  - `return_type_ref: RecordTypeRef | UnionTypeRef`

Rules:

- legal only in `defworkflow` and `defproc` parameter positions;
- not legal in record fields, union fields, workflow returns, provider results,
  command results, `Optional[...]`, `List[...]`, `Map[...]`, or path contracts;
- may appear in lexical environments only when derived from an allowed
  parameter or an explicit workflow-ref literal.

`WorkflowRefTypeRef` is a frontend-only compile-time type. It does not map to a
shared runtime contract.

### Resolved Workflow Ref Authority

Add generic resolution metadata:

- `WorkflowRefBinding`
  - authored symbol
  - declared `WorkflowRefTypeRef`
  - source span/form path
- `ResolvedWorkflowRef`
  - authored symbol
  - canonical callable key
  - resolved workflow signature
  - authority source:
    `same_file`,
    `linked_module_export`,
    or `registered_imported_bundle`
  - imported bundle handle, if applicable
  - extern-closure status
  - optional compiler-owned extern rebinding plan

Authority rules:

- same-file workflows resolve through the current workflow catalog;
- linked imported `.orc` workflows resolve through module-export surfaces and
  canonical callable keys;
- explicitly registered imported bundles remain valid migration debt when they
  also provide compile-time signature metadata;
- ambiguous or multiply-resolved targets are rejected before lowering.

### Workflow Ref Specialization

Add one deterministic specialization layer:

- `WorkflowRefSpecializationKey`
  - higher-order callable key
  - ordered `(param_name, resolved_workflow_key)` bindings
- `WorkflowRefInstantiationPlan`
  - specialization key
  - specialized callable key
  - runtime-boundary parameter list
  - resolved workflow-ref bindings
  - nested specialization dependencies
  - origin metadata

Rules:

- specialization happens before workflow-boundary flattening or imported-bundle
  registration for the caller;
- specialized callable keys must be deterministic, stable across runs, and
  source-mappable;
- recursion through the same specialization key is rejected with a dedicated
  workflow-ref specialization diagnostic;
- one specialized callable may be reused by multiple call sites when the
  specialization key is identical.

## Author-Facing Surface

### Type Positions

The selected surface is the full-design `WorkflowRef[...]` type, but it remains
frontend-local:

```text
WorkflowRef[DrainCtx -> SelectionResult]
WorkflowRef[(ItemCtx SelectionPayload) -> SelectedItemResult]
```

Implementation rule:

- the signature parser in `workflows.py` and `procedures.py` must treat
  workflow-ref types as structured type expressions rather than ordinary plain
  identifiers;
- the exact tokenization stays frontend-local and must not require shared
  runtime changes.

### Expression Positions

Two authored forms are allowed:

- bare or qualified workflow names in positions where a `WorkflowRefTypeRef` is
  already expected;
- an explicit `(workflow-ref target-name)` form when no expected type is
  available yet.

Examples:

```lisp
(call backlog/drain
  :ctx ctx
  :selector selector/run
  :run-item selected-item/run
  :gap-drafter gap/draft
  :max-iterations max)

(let* ((selector-ref (workflow-ref selector/run)))
  (call backlog/drain
    :ctx ctx
    :selector selector-ref
    ...))
```

Both forms remain compile-time-only. They must resolve to named workflows before
lowering.

### `call` Surface

`call` may now target either:

- a direct workflow name as before; or
- a lexical binding whose resolved type is `WorkflowRefTypeRef`.

No other dynamic callee expressions become legal in this slice.

## Linking And Resolution Model

### Resolution Order

When a workflow-ref literal is resolved, use this authority order:

1. same-file workflow catalog;
2. imported workflow binding through the linked module scope;
3. explicitly registered imported-bundle metadata passed through the compile
   API.

The resulting target always normalizes to one canonical callable key before
typechecking or lowering.

### Signature Compatibility

Compatibility is structural, not stringly:

- parameter count must match exactly;
- each parameter type must be structurally compatible with the declared
  `WorkflowRefTypeRef` parameter type;
- return type must be structurally compatible with the declared
  `WorkflowRefTypeRef` return type;
- if the resolved target returns a union, existing union workflow-boundary
  projection rules remain authoritative and downstream variant access still
  requires proof.

This lets the generic layer consume imported bundles or linked exports without
requiring every target to share one local type name.

### Extern Closure

Workflow refs must also satisfy compile-time extern rules:

- generic higher-order calls are legal only when the resolved target is closed
  over provider/prompt externs under the caller's compile-time environment;
- compiler-owned stdlib forms may additionally provide an exact extern rebinding
  plan, reusing the existing resource/drain approach;
- this slice does not introduce a user-authored extern-mapping surface.

If externs cannot be satisfied exactly, compilation fails before specialization.

## Typing And Specialization Model

### Higher-Order Parameters

`defworkflow` and `defproc` signatures may include workflow-ref parameters.

Typechecking requirements:

- workflow-ref parameters are tracked separately from runtime-boundary
  parameters;
- higher-order call sites must supply compile-time-known workflow-ref values;
- forwarding a workflow-ref parameter into another higher-order callable is
  legal only when the declared `WorkflowRefTypeRef` matches exactly;
- workflow-ref values may not be returned, materialized, serialized, or stored
  in ordinary data structures.

### Higher-Order Calls

When a call site targets a higher-order workflow or procedure:

1. resolve all workflow-ref arguments to `ResolvedWorkflowRef` values;
2. build a deterministic `WorkflowRefSpecializationKey`;
3. instantiate or reuse a specialized callable with workflow-ref parameters
   removed from the runtime boundary;
4. typecheck the instantiated body with lexical workflow-ref bindings resolved
   to concrete targets;
5. lower any call through those bindings as ordinary direct calls.

### Cycle Policy

Specialization cycles are rejected:

- direct or indirect recursion through the same higher-order specialization key
  is a compile-time error;
- non-cyclic reuse of the same specialization key is memoized and lowered once.

This keeps the selected surface compatible with the current imported-bundle
runtime model, which requires concrete callees before lowering.

## Lowering And Shared Handoff

Lowering rules:

- no unresolved `WorkflowRefTypeRef` may survive into the lowered runtime
  workflow signature;
- specialized workflows and procedures lower through the existing authored
  mapping and imported-bundle seam;
- a `call` through a resolved workflow ref lowers exactly like an ordinary call
  to the resolved canonical callable key or imported bundle handle;
- workflow-boundary flattening continues to apply only to the remaining
  runtime-boundary parameters;
- union workflow-return handling, `requires_variant`, and structured-result
  projection remain unchanged and are reused for resolved workflow-ref targets.

Source-map requirements:

- every specialized callable must preserve the original definition span plus
  the call-site span that caused specialization;
- calls lowered from a workflow-ref binding must record both the lexical
  workflow-ref origin and the resolved target identity in `LoweringOriginMap`;
- diagnostics from generated specialized callables must remap to the authored
  higher-order definition or call site, not only the generated callable key.

## Diagnostics

Reuse existing diagnostics where they already fit:

- `workflow_signature_mismatch`
- `workflow_ref_unknown`
- `workflow_ref_signature_invalid`
- `workflow_ref_return_type_invalid`
- `variant_ref_unproved`
- module diagnostics such as `module_export_missing` and
  `module_import_ambiguous`

Add dedicated frontend-local diagnostics where the current codes are too coarse:

- `workflow_ref_type_invalid`
  - illegal `WorkflowRef` use in a non-parameter or runtime-boundary position;
- `workflow_ref_literal_required`
  - a higher-order call argument is not a compile-time-known workflow target;
- `workflow_ref_runtime_transport_forbidden`
  - attempted workflow-ref return, record storage, or runtime-boundary
    transport;
- `workflow_ref_extern_rebinding_unsatisfied`
  - resolved target requires provider/prompt externs the caller cannot satisfy;
- `workflow_ref_specialization_cycle`
  - higher-order specialization recurs through the same specialization key.

Diagnostics must point at the authored workflow-ref use site, preserve
module/source provenance, and include the resolved target when that clarifies
the failure.

## Test Strategy

Add one dedicated workflow-ref regression module and extend the existing
frontend suites:

- `tests/test_workflow_lisp_workflow_refs.py`
  - same-file workflow-ref typechecking;
  - explicit `(workflow-ref ...)` elaboration;
  - compile-time-only transport rejections;
  - specialization reuse and cycle rejection;
  - extern-closure rejection.
- `tests/test_workflow_lisp_modules.py`
  - imported workflow-ref resolution through canonical callable keys;
  - export/ambiguity failures surfaced from workflow-ref use sites.
- `tests/test_workflow_lisp_procedures.py`
  - higher-order `defproc` specialization and forwarding.
- `tests/test_workflow_lisp_workflows.py`
  - higher-order `defworkflow` specialization and signature checks;
  - union-returning workflow refs preserving proof requirements.
- `tests/test_workflow_lisp_lowering.py`
  - specialized callable-key determinism and source-map remapping.
- `tests/test_workflow_lisp_drain_stdlib.py`
  - drain role validation consuming the generic layer rather than a parallel
    resolver.
- `tests/test_workflow_lisp_stage7_translation.py`
  - selected-item and remaining-drain translation still compile through the new
    workflow-ref layer.

Add one focused runtime or translation smoke after the compile-time suites so
the higher-order specialization path is exercised through a real drain-shaped
workflow.

## Implementation Sequence

1. Add `WorkflowRefTypeRef` and the signature-side parsing/elaboration support
   in `workflows.py`, `procedures.py`, and `type_env.py`.
2. Add `workflow_refs.py` with generic authority resolution, signature
   compatibility checks, extern-closure metadata, and specialization keys.
3. Update `expressions.py` and `typecheck.py` so workflow-ref literals,
   workflow-ref-typed lexical bindings, and higher-order `call` typing become
   legal while runtime transport remains rejected.
4. Update `lowering.py` and `compiler.py` so higher-order callables specialize
   before runtime-boundary flattening and lower through existing imported-bundle
   surfaces.
5. Refactor `resource.py` / `resource_stdlib.py` / drain typechecking to
   consume the generic workflow-ref layer.
6. Add focused fixtures and tests, then run the compile-time and drain/Stage 7
   verification set.

## Acceptance Conditions

This slice is complete when:

1. `WorkflowRef[...]` is a frontend-recognized parameter type for
   `defworkflow` and `defproc`.
2. Compile-time workflow-ref literals resolve to same-file workflows, linked
   module exports, or explicitly registered imported bundles with deterministic
   diagnostics on ambiguity or missing exports.
3. Higher-order workflows and procedures specialize away workflow-ref
   parameters before runtime-boundary lowering.
4. Calls through workflow-ref parameters lower to ordinary direct calls on the
   existing imported-bundle/shared-validation seam.
5. Generic workflow-ref use remains compile-time-only and cannot cross runtime
   workflow boundaries.
6. The drain/resource stack consumes the generic workflow-ref layer instead of
   maintaining a parallel resolver.
7. Stage 7 drain-shaped translation continues to compile through the revised
   layer.
8. Source maps and diagnostics for specialized callables remain attributable to
   authored higher-order forms.

## Verification Plan

The implementation plan for this slice should at minimum run:

1. workflow-ref collect/typecheck/lowering regressions;
2. module-linking regressions for imported workflow refs;
3. procedure/workflow higher-order specialization regressions;
4. drain stdlib regressions that exercise selector/run-item/gap-drafter through
   the generic layer;
5. one Stage 7 or runtime smoke covering drain-shaped specialization end to
   end.
