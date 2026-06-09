# Same-File Call Bindings For Locally Constructed Records Implementation Architecture

Status: draft
Design gap id: `same-file-call-bindings-for-locally-constructed-records`
Target design: `docs/design/workflow_lisp_unified_frontend_design.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds only the bounded Stage 3 lowering support required for
same-file calls whose record-typed arguments are supplied as locally
constructed record values instead of only direct workflow-input refs:

- allow same-file `CallExpr` bindings for record-typed workflow parameters to
  lower from authored `RecordExpr` values and from local record-shaped aliases
  built earlier in the same lexical scope;
- allow the same record-valued argument shape when a `ProcedureCallExpr`
  lowers through the existing private-workflow boundary;
- preserve the current flattening of structured boundary inputs into
  `call.with` leaf bindings;
- preserve the current lowering rule that each emitted leaf must still resolve
  to an already-authoritative ref value supported by the runtime call boundary;
- keep typechecking, source maps, private-workflow analysis, and shared
  validation ownership unchanged.

This slice does not implement:

- generic effectful-composition completion for arbitrary call arguments;
- runtime transport of structured records as first-class call payloads;
- new workflow or procedure syntax;
- new command adapters, scripts, legacy adapters, or runtime-native effects;
- runtime closures, dynamic dispatch, or workflow/procedure loading changes;
- widening of call-leaf authority to arbitrary literals, ad hoc JSON payloads,
  pointer files, or report-derived state.

The work stays bounded to the selected lowering gap. It is an implementation
architecture for one missing call-binding seam, not a redesign of the frontend
or runtime call contract.

## Problem Statement

The current checkout already has most of the substrate needed for this gap:

- `typecheck.py` accepts record-typed call bindings for both workflows and
  procedures when the authored binding expression matches the parameter type;
- `lowering.py` already knows how to flatten record-typed boundary parameters
  with `_flatten_boundary_leaf_paths(...)`;
- local record-shaped values already exist in two forms:
  - authored `RecordExpr` trees;
  - nested local-value mappings produced by `_build_output_step_local_value(...)`
    and related helpers for step-backed results;
- same-file procedure calls already support inline lowering by threading
  `_resolve_inline_expr_value(...)` results into child local environments.

What is missing is the call-boundary renderer for record-valued arguments.
Today both same-file workflow calls and private-workflow procedure calls funnel
record parameters through `_render_call_binding_ref(...)`, which only succeeds
when the selected leaf is already a plain string ref returned by
`_resolve_expr_local_value(...)`.

That leaves a concrete mismatch in the current implementation:

- the typechecker accepts a binding such as `(record ImplementationContext ...)`;
- local bindings can already hold record-shaped values;
- boundary flattening already knows the leaf paths to emit;
- lowering still rejects the call because the leaf renderer does not recurse
  through an authored record value.

The selected gap is therefore not a new calling model. It is a bounded
normalization problem:

```text
record-typed call argument
  -> resolve local value or authored record tree
  -> walk each declared boundary leaf path
  -> lower each leaf through the existing authoritative ref renderer
  -> emit ordinary flattened `call.with` bindings
```

If a leaf cannot lower to the existing call-boundary ref model, the call must
still reject.

## Design Constraints

The architecture must preserve the governing repo and design invariants:

- `docs/design/workflow_lisp_unified_frontend_design.md`
  - `21. Feature Summary`
  - `22. Current Gap`
  - `23. Design Goal`
  - `25. Effectful let*`
  - `28. Same-File Call Bindings for Locally Constructed Records`
  - `29. Reusable Workflow Boundary Write Roots`
  - `31. Acceptance Gate for Effectful Composition`
- `docs/design/workflow_lisp_frontend_specification.md`
  - `7.4 Records`
  - `10. Sequential Binding: let*`
  - `14. Workflow Calls`
  - `50. defworkflow Lowering`
  - `52. call Lowering`
- `docs/design/workflow_command_adapter_contract.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/work_instructions.md`

The slice must also preserve the current implementation guardrails:

- shared validation remains authoritative;
- the runtime call step still receives flattened leaf bindings, not structured
  runtime record values;
- artifact values remain authority and pointer files remain representations;
- no provider, command, workflow, state, or adapter effect may be hidden by
  the new binding support;
- reusable/private workflow write-root policy remains unchanged;
- the command-adapter contract remains authoritative for any adapter-backed
  behavior inside callees. This slice must not introduce helper scripts or
  hidden command shims just to carry structured arguments across a call.

## Relationship To Existing Implementation Architectures

### Existing Slices Reviewed

- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/let-proc-compile-time-local-proc-bindings/implementation_architecture.md`
- `docs/plans/LISP-FRONTEND-UNIFIED-DESIGN/design-gaps/with-phase-composable-expression/implementation_architecture.md`
- Additional historical slices reviewed for coherence:
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/defproc-procedural-substrate/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/workflow-boundary-type-flattening/implementation_architecture.md`
  - `docs/plans/LISP-FRONTEND-AUTONOMOUS-DRAIN/design-gaps/first-phase-translation-neurips-implementation/implementation_architecture.md`

### Decisions Reused

- Reuse the current authored surfaces: `RecordExpr`, `CallExpr`,
  `ProcedureCallExpr`, `LetStarExpr`, and the existing typed call signatures.
- Reuse `_flatten_boundary_leaf_paths(...)` as the authority for boundary leaf
  enumeration instead of defining a second flattening scheme.
- Reuse `_resolve_inline_expr_value(...)`, `_resolve_inline_field_value(...)`,
  `_build_output_step_local_value(...)`, and the nested local-value mapping
  shape as the existing representation of record-shaped locals.
- Reuse the current private-workflow procedure lowering seam rather than
  inventing a separate procedure-call transport layer.
- Reuse existing provenance and diagnostic ownership in `lowering.py`; no new
  Core AST, Semantic IR, TypeCatalog, SourceMap, pointer-authority, or
  variant-proof concept is introduced.

### New Decisions In This Slice

- Add one structure-aware call-binding lowering helper that can read a record
  argument from either an authored `RecordExpr` tree or an already-resolved
  local record mapping.
- Keep `_render_call_binding_ref(...)` or an equivalent successor as the
  leaf-level authority boundary; record support is added by decomposition, not
  by widening the accepted leaf kinds.
- Make same-file workflow calls and private-workflow procedure calls use the
  same record-binding helper so the two call paths cannot drift.
- Keep inline procedure calls unchanged because they already thread local
  record values directly inside the caller's lowering context instead of
  crossing the runtime call boundary.
- Keep the rejection surface under existing frontend diagnostics, with more
  specific field-path messages where needed, instead of inventing a new error
  family.

### Conflicts Or Revisions

The current Stage 3 lowering path assumes that a same-file call binding is
already reduced to a plain ref by the time it reaches the runtime call-step
emission path. That assumption now conflicts with the accepted target design
and with the current typechecker, which already accepts record-valued call
bindings.

This slice revises that assumption narrowly:

- record-valued call bindings may remain structured until call-boundary
  flattening;
- call-boundary flattening becomes responsible for walking the declared record
  shape and rendering each leaf;
- the runtime boundary itself remains flattened and ref-based.

No prior slice is revised on shared concepts such as Core Workflow AST,
Semantic Workflow IR, TypeCatalog, SourceMap, pointer authority, or variant
proof.

## Ownership Boundaries

This slice owns:

- lowering-time rendering of record-typed same-file call bindings;
- shared helper logic that projects locally constructed record values into
  flattened `call.with` leaf bindings;
- parity between same-file workflow calls and private-workflow procedure calls
  for record-valued arguments;
- focused diagnostics for rejected record-binding leaves;
- regression tests proving the selected gap is closed.

This slice intentionally does not own:

- call expression parsing or typechecking redesign;
- generic lowering of arbitrary structured literals across runtime boundaries;
- inline procedure semantics;
- reusable/private-workflow write-root allocation policy;
- shared runtime call-step schema, provider execution, command execution, or
  state persistence;
- new scripts, adapters, or runtime-native effects.

## Proposed Package Boundary

Keep the work inside the existing frontend package and confine code changes to
the current call-lowering seam:

```text
orchestrator/workflow_lisp/
  lowering.py       # record-aware same-file call binding rendering

tests/
  test_workflow_lisp_lowering.py
  test_workflow_lisp_procedures.py
  test_workflow_lisp_examples.py
```

Primary responsibilities:

- `lowering.py`
  - add one shared helper that resolves a record argument and renders the
    flattened boundary leaf refs;
  - call that helper from `_lower_call_expr(...)`;
  - call that helper from the private-workflow branch of
    `_lower_procedure_call_expr(...)`;
  - keep inline procedure calls unchanged;
  - preserve current origin-note and step-id behavior for the generated call
    step.
- `tests/*`
  - add focused coverage for workflow calls, private-workflow procedure calls,
    and one integration-style compile path using a local record binding.

No new package, module, or helper script is needed for this slice.

## Current Checkout Facts

Current implementation evidence in `orchestrator/workflow_lisp/lowering.py`
shows the exact seam this slice must change:

- `_lower_call_expr(...)`
  - flattens record parameters with `_flatten_boundary_leaf_paths(...)`;
  - renders each leaf through `_render_call_binding_ref(...)`.
- `_lower_procedure_call_expr(...)`
  - uses the same leaf renderer when a procedure lowers through its generated
    private workflow boundary;
  - does not need changes for inline procedures.
- `_render_call_binding_ref(...)`
  - resolves direct names and field accesses through `_resolve_expr_local_value(...)`;
  - rejects anything that does not already collapse to a string ref with
    `workflow_signature_mismatch`.
- `_resolve_inline_expr_value(...)` and `_resolve_inline_field_value(...)`
  - already know how to walk nested `RecordExpr` values and local record-shaped
    mappings.

That means the missing behavior is not type information or flattening logic. It
is record-aware leaf extraction during call binding emission.

## Internal Lowering Contract

### 1. Record-Aware Call Binding Helper

Add one shared helper in `lowering.py` that owns the structured-to-flattened
translation for one record-typed call argument.

Recommended shape:

```python
def _render_record_call_bindings(
    param_name: str,
    param_type: RecordTypeRef,
    value_expr: Any,
    *,
    local_values: Mapping[str, Any],
) -> dict[str, Any]:
    ...
```

Contract:

- resolve the top-level argument through `_resolve_inline_expr_value(...)`;
- for each declared boundary leaf from `_flatten_boundary_leaf_paths(...)`:
  - recover the corresponding nested leaf value from either:
    - the resolved local mapping; or
    - the authored `RecordExpr` tree;
  - lower that leaf through the existing leaf-authority renderer;
- return the ordinary flattened `call.with` mapping for that parameter.

This helper must not invent a new boundary representation. Its only job is to
bridge authored/local structured values back onto the existing flattened
runtime call contract.

### 2. Leaf Rendering Stays Narrow

Leaf rendering must stay governed by the current authoritative surfaces already
accepted at the runtime call boundary.

In practice:

- if the leaf is already a string ref from workflow inputs, prior outputs, or
  other existing approved local refs, emit `{"ref": ...}` exactly as today;
- if the leaf is an authored expression that can reduce to one of those refs
  through the existing inline/local-value helpers, reduce it and emit the ref;
- otherwise reject.

This slice must not widen call leaves to arbitrary literals, opaque mappings,
  pointer-file paths, markdown-derived fields, or hidden temporary files.

### 3. Workflow Calls And Private-Workflow Procedure Calls Share The Helper

Both runtime-boundary call paths must use the same record-binding helper:

- `_lower_call_expr(...)` for same-file workflow calls;
- the private-workflow branch of `_lower_procedure_call_expr(...)`.

That keeps workflow and procedure behavior coherent and avoids one path
accepting structured record aliases while the other still rejects them.

### 4. Inline Procedure Calls Stay Unchanged

Inline procedure lowering already injects `_resolve_inline_expr_value(...)`
results into child locals instead of emitting a runtime call step. This slice
must not disturb that path.

Bounded rule:

- if a procedure lowers inline, existing record-valued argument behavior is
  preserved as-is;
- if a procedure lowers as a private workflow, it uses the new shared
  record-binding helper because it crosses the same runtime call boundary as an
  authored workflow call.

### 5. Diagnostics

Keep diagnostics under the current frontend families:

- `workflow_signature_mismatch` for call-binding leaves that cannot lower to a
  supported ref shape;
- `workflow_return_not_exportable` only when the failure is really about
  step-backed exportability elsewhere in the lowering path;
- existing type errors remain owned by `typecheck.py`.

The new helper should improve message precision by naming the failing record
field path when practical, for example:

```text
record call binding `ctx.providers.execute` must lower from workflow inputs or prior outputs
```

No new shared-validation error class is needed.

## Test And Acceptance Surface

Implementation should add focused tests proving both the positive and negative
contracts of this slice.

Primary test targets:

- `tests/test_workflow_lisp_lowering.py`
- `tests/test_workflow_lisp_procedures.py`
- `tests/test_workflow_lisp_examples.py`

Required positive coverage:

- same-file workflow call where a record-typed parameter is supplied as a
  direct authored `RecordExpr`;
- same-file workflow call where the record argument is first bound in `let*`
  and then passed by name;
- private-workflow procedure call where a record-typed parameter is supplied as
  a direct authored record or local record alias;
- one integration-style `compile_stage3_module(..., validate_shared=True)`
  scenario proving the selected gap works end-to-end through current lowering.

Required negative coverage:

- one record leaf that does not resolve to a supported ref shape still fails
  under `workflow_signature_mismatch`;
- nested record paths that do not match the declared record structure still
  fail deterministically;
- inline procedure behavior remains unchanged.

Acceptance conditions:

- same-file workflow and private-workflow procedure calls both flatten locally
  constructed record values into ordinary `call.with` bindings;
- the generated runtime call shape stays flattened and ref-based;
- no new runtime value type, helper script, adapter, or write-root policy is
  introduced;
- diagnostics stay source-mapped to the authored binding site.

## Verification Expectations

When this slice is implemented, verification should include:

- focused `pytest` selectors for the lowering and procedure suites;
- `pytest --collect-only` for any test modules that add or rename tests;
- at least one integration-style compile check that exercises a same-file call
  with a local record binding under shared validation;
- no workflow smoke run is required beyond compilation because this slice does
  not change runtime execution semantics, provider contracts, or adapter
  behavior.
