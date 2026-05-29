# ProcRef Bind-Proc Specialization And Lowering Implementation Architecture

Status: draft
Design gap id: `procref-bind-proc-specialization-lowering`
Target design: `docs/design/workflow_lisp_proc_refs_partial_application.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice implements the remaining compile-time ProcRef path required by the
accepted delta:

- `bind-proc` keyword-only partial application;
- residual `ProcRef[...]` signature computation;
- calling through lexical ProcRef bindings and parameters;
- deterministic specialized `defproc` generation before executable lowering;
- effect-summary preservation for selected and partially bound procedures;
- lowering-time elimination of unresolved ProcRef call targets;
- source-map and diagnostic coverage for specialization artifacts.

This slice does not implement:

- runtime first-class procedures, closures, or serialization;
- arbitrary computed callee expressions;
- positional partial application, defaults, or variadic keyword bags;
- ProcRef transport through records, unions, workflow boundaries, artifacts,
  ledgers, or loop-carried runtime state;
- command adapters, helper scripts, or runtime-native effects.

The scope is bounded to the selected design gap. It extends the existing static
ProcRef surface; it does not reopen unrelated frontend work.

## Problem Statement

The current frontend already supports the prerequisite static ProcRef surface:

- `ProcRef[...]` parses and resolves through `type_expressions.py`,
  `type_env.py`, and `procedure_refs.py`;
- `(proc-ref name)` elaborates and typechecks as a compile-time reference;
- runtime-transport rejection is enforced in `type_env.py`, `workflows.py`,
  and `loops.py`.

What is still missing is the path that makes ProcRef useful as reusable
workflow behavior:

- there is no `bind-proc` form;
- ordinary list-call elaboration only recognizes same-file named procedures, so
  a bound ProcRef parameter cannot be invoked inside a `defproc`;
- procedure-call effect summaries assume the callee is a catalog name, not a
  compile-time ProcRef value;
- existing procedure specialization in `lowering.py` is workflow-ref-specific
  and happens too late to satisfy the delta's effect-summary and source-map
  requirements;
- executable lowering still requires concrete procedure names and therefore
  cannot eliminate unresolved ProcRef call targets.

The selected gap is therefore not just syntax sugar. It needs one coherent
compile-time specialization pipeline spanning elaboration, typechecking, effect
inference, and lowering while preserving the baseline rule that executable IR
contains no runtime procedure values.

## Design Constraints

The architecture must preserve the accepted frontend and command-boundary
contracts:

- ProcRef values are compile-time only and never become runtime data.
- Specialization must happen before Core AST / Semantic IR lowering.
- `defproc :lowering` remains authoritative after specialization.
- Source maps must retain authored spans for the original `defproc`,
  `proc-ref`, `bind-proc`, and consuming call site.
- Effect visibility must remain explicit; specialization cannot hide provider,
  command, workflow, or state effects.
- Existing shared concepts such as Core AST, Semantic IR, TypeCatalog,
  SourceMap, pointer authority, and variant proof are not redefined here.

The command-adapter contract was reviewed as an authority check. This slice
must not introduce inline shell/Python glue, named scripts, certified command
adapters, or runtime-native effects to fake ProcRef semantics.

## Proposed Architecture

### 1. Add `bind-proc` as a frontend expression and allow lexical ProcRef callees

Extend `orchestrator/workflow_lisp/expressions.py` with a new `BindProcExpr`:

- `base_expr`: `ProcRefLiteralExpr` or forwarded `NameExpr`;
- `bindings`: ordered keyword/value pairs in authored order;
- authored span, form path, and expansion stack.

Elaboration rules:

- `(bind-proc <proc-ref-expr> :name value ...)` is a dedicated special form;
- the base expression is elaborated with ordinary expression rules so forwarded
  ProcRef bindings remain source-mapped;
- keywords remain keyword-only and duplicates are preserved for later targeted
  diagnostics rather than normalized away during parsing.

To make specialized ProcRefs callable, widen procedure-call elaboration in one
specific way:

- if a list head is a known same-file/imported procedure name, keep the current
  `ProcedureCallExpr` path;
- otherwise, if the head is a lexical bound name, also elaborate it as
  `ProcedureCallExpr` rather than rejecting it immediately;
- typechecking becomes the authority for deciding whether that bound name is a
  callable ProcRef, an invalid non-callable value, or an unknown procedure.

This keeps the surface minimal. The language still does not allow arbitrary
callee expressions such as `((bind-proc ...) arg)` or provider-selected call
targets.

### 2. Represent partially bound ProcRefs as compile-time specialization plans

Extend `orchestrator/workflow_lisp/procedure_refs.py` from static resolution
into the shared ProcRef specialization authority module.

Add owned data shapes:

- `BoundProcArg`
  Captures one bound parameter name, the authored expression, its resolved
  type, and stable source identity used in specialization hashing.
- `ResolvedBoundProcRef`
  Represents a compile-time ProcRef value after following forwarded names and
  optional `bind-proc` layers. It includes the base `ResolvedProcRef`, ordered
  bound arguments, residual parameter list, residual `ProcRefTypeRef`, and a
  deterministic specialization key.
- `ProcRefSpecializationRequest`
  The compiler/lowering-facing request to materialize or reuse a specialized
  `TypedProcedureDef`.

Add owned helper behavior:

- `resolve_proc_ref_value(...)`
  Recursively resolves a ProcRef value from a literal, forwarded name, or
  `BindProcExpr`.
- `validate_bind_proc_bindings(...)`
  Enforces known keyword names, duplicate rejection, and per-parameter type
  compatibility.
- `residual_proc_ref_type(...)`
  Computes the residual `ProcRef[...]` signature after removing bound params in
  original parameter order.
- `proc_ref_specialization_name(...)`
  Produces a deterministic hidden procedure name of the form
  `%proc-ref.<module>.<procedure>.<stable-hash>`.

Stable-hash inputs must cover:

- the resolved base procedure identity;
- bound parameter names in declaration order;
- stable source identities for the bound expressions;
- the residual signature.

This keeps specialization deterministic without creating any runtime procedure
registry.

### 3. Typecheck `bind-proc` and ProcRef call sites through compile-time value environments

Extend `orchestrator/workflow_lisp/typecheck.py` with a ProcRef value layer
parallel to the existing value/type environment.

Required behavior:

- `BindProcExpr` typechecks only if its base expression resolves to a ProcRef
  value;
- each bound keyword must name a declared parameter in the referenced
  procedure, appear at most once, and typecheck against that parameter type;
- the result type of `BindProcExpr` is the residual `ProcRefTypeRef`;
- a zero-arg residual specialization is valid only when the residual type is
  `ProcRef[() -> R]`.

For `ProcedureCallExpr`, typechecking must branch by callee authority:

- if `expr.callee_name` names a lexical binding whose type is `ProcRefTypeRef`,
  resolve the compile-time ProcRef value and treat the call as a specialization
  request against the selected base procedure;
- otherwise keep the current direct named-procedure path.

This branch is where the delta's effect rule becomes enforceable. The call site
must merge:

- argument expression effects;
- the specialized callee's transitive effects, including any procedures chosen
  by ProcRef bindings;
- ordinary procedure-call graph edges for the specialized callee name.

Diagnostic ownership for this step:

- `proc_ref_literal_required` when a required ProcRef position receives neither
  a literal nor a forwarded/bound ProcRef value;
- `proc_ref_binding_unknown` for unknown `bind-proc` keywords;
- `proc_ref_binding_duplicate` for repeated keywords;
- `proc_ref_binding_type_invalid` for mismatched bound argument types;
- `proc_ref_signature_invalid` when the supplied ProcRef does not satisfy the
  expected ProcRef type.

### 4. Move procedure specialization from a lowering-only trick to a compiler-owned pass

The current helper `_specialize_typed_procedure()` in `lowering.py` is useful
but too narrow: it only specializes workflow-ref parameters, it stores
workflow-ref-only metadata, and it runs after effect summaries are already
fixed.

This slice should promote procedure specialization into a compiler-owned pass
used both by effect inference and by lowering.

Recommended implementation shape:

- keep workflow-ref specialization semantics unchanged;
- add a generalized callable-specialization helper that can represent
  workflow-ref bindings, ProcRef bindings, and ordinary bound argument
  expressions;
- materialize specialized `TypedProcedureDef` values during
  `_infer_stage3_effect_summaries()` in `compiler.py`, not only during
  lowering.

Compiler pass behavior:

1. Typecheck authored procedures as today.
2. Discover ProcRef specialization requests from:
   - `BindProcExpr` values that survive into lexical bindings;
   - `ProcedureCallExpr` sites whose callee authority is a ProcRef binding.
3. Materialize deterministic specialized procedures in a registry keyed by the
   specialization name.
4. Re-run effect-summary validation across authored plus specialized
   procedures until the existing fixpoint converges.

Specialized procedures should:

- reuse the base procedure body and source origin;
- drop bound parameters from `definition.params` and `signature.params`;
- carry explicit specialization metadata describing:
  - base procedure name;
  - bound workflow refs, if any;
  - bound ProcRef values;
  - bound ordinary argument expressions;
  - specialization request origin spans.

This is still compile-time lowering preparation, not runtime code loading.

### 5. Detect specialization cycles at the specialization graph level

The parent delta requires rejection when specialization would make a procedure
depend on a specialized version of itself through a ProcRef chain.

Extend cycle validation in `compiler.py` to operate on specialization requests
as well as authored procedure names:

- direct authored recursion remains `proc_lowering_cycle`;
- ProcRef-triggered specialization recursion raises
  `proc_ref_specialization_cycle`;
- the diagnostic should point first to the most actionable authored form:
  the `bind-proc` or proc-ref-consuming call site that introduced the cycle.

This keeps existing authored recursion behavior intact while adding the delta's
required ProcRef-specific failure mode.

### 6. Lower specialized procedures by substituting compile-time bindings, not runtime values

Extend `orchestrator/workflow_lisp/lowering.py` so every ProcRef call target is
concrete before executable steps are emitted.

Lowering rules:

- when lowering a `ProcedureCallExpr` whose callee is a ProcRef binding, resolve
  the same `ResolvedBoundProcRef` specialization request used by typechecking;
- fetch or materialize the specialized `TypedProcedureDef` from the compiler
  registry instead of leaving a local ProcRef name in executable lowering;
- then continue through the existing `defproc` lowering path for inline or
  private-workflow lowering.

Binding substitution model:

- seed inline/private-workflow lowering environments with the specialized
  procedure's compile-time bound values;
- ordinary bound parameter expressions remain compile-time substitutions, not
  runtime inputs;
- bound ProcRef values remain compile-time references and can themselves be
  resolved transitively if the specialized body invokes them.

This preserves the baseline rule:

- executable IR, runtime plans, debug YAML projections, state bundles, and
  artifacts contain no unresolved ProcRef values.

### 7. Respect `defproc :lowering` after specialization

The accepted delta and baseline both require specialization to happen before
the standard `defproc` lowering policy is applied.

After a ProcRef specialization is materialized:

- `inline` specializes first, then inlines;
- `private-workflow` specializes first, then emits a deterministic hidden
  private workflow if the existing shared-validation seam rules still hold;
- `auto` specializes first, then chooses between inline and private workflow
  using the same boundary/body checks already used for authored procedures.

No new backend or command adapter is introduced. The private workflow remains
the same kind of compiler-generated workflow wrapper already used by the
baseline frontend.

### 8. Preserve source maps and explainability across specialization artifacts

Specialization metadata must be rich enough for diagnostics and future explain
artifacts to expose:

- the original `defproc` definition;
- the `proc-ref` literal, if present;
- the `bind-proc` form, if present;
- the call site that consumed the ProcRef value;
- generated specialized procedure names;
- generated private workflow names, if specialization lowers that way.

Implementation consequence:

- specialization metadata belongs on `TypedProcedureDef.specialization`;
- provenance-note helpers in `lowering.py` should render bind-proc and proc-ref
  origins in addition to the existing procedure definition/call-site notes;
- no generated node may lose the authored span of the form that chose the
  procedure target.

## Owned Components

This slice owns changes in:

- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedure_refs.py`
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py`
- `orchestrator/workflow_lisp/lowering.py`
- `orchestrator/workflow_lisp/procedures.py` as needed for specialization
  metadata carried on typed procedures
- focused ProcRef tests in:
  - `tests/test_workflow_lisp_procedures.py`
  - `tests/test_workflow_lisp_modules.py`
  - `tests/test_workflow_lisp_workflows.py`
  - `tests/test_workflow_lisp_collection_types.py`
  - new or updated ProcRef-specialization coverage near existing workflow-ref
    lowering tests if separation is clearer

## Intentionally Not Owned

This slice does not own or redefine:

- Core Workflow AST
- Semantic Workflow IR
- runtime execution
- workflow-call semantics outside reused workflow-ref specialization helpers
- command adapters, scripts, or runtime-native effects
- ProcRef runtime transport rules outside the already-owned rejection seams
- product-design changes to the broader Workflow Lisp language

## Diagnostics

This slice must add or activate:

- `proc_ref_binding_unknown`
- `proc_ref_binding_duplicate`
- `proc_ref_binding_type_invalid`
- `proc_ref_specialization_cycle`

This slice must preserve and continue using:

- `proc_ref_unknown`
- `proc_ref_literal_required`
- `proc_ref_signature_invalid`
- `proc_ref_runtime_transport_forbidden`
- `proc_ref_private_import_invalid`

If a bound lexical call head is not actually a ProcRef value, the diagnostic
should stay at the authored call site rather than degrading into a lowering
error.

## Test Strategy

Add focused tests proving:

- `bind-proc` binds a subset of parameters and exposes the correct residual
  `ProcRef[...]` signature;
- duplicate, unknown, and mistyped `bind-proc` keywords raise the required
  diagnostics;
- a procedure can invoke a ProcRef parameter through a lexical call head and
  preserve type safety;
- forwarded `bind-proc` values can be passed through intermediate `defproc`
  parameters without becoming runtime data;
- specialized procedures preserve selected transitive effects during the stage 3
  effect-summary fixpoint;
- specialization naming is deterministic for the same base procedure, bindings,
  and residual signature;
- a specialized procedure can lower inline;
- a specialized procedure can lower as a private workflow when the requested
  lowering mode and existing boundary checks allow it;
- emitted lowered workflows and provenance artifacts contain no unresolved
  ProcRef values and retain bind-proc/proc-ref/call-site lineage;
- specialization cycles raise `proc_ref_specialization_cycle`.

Keep these tests narrow and reuse the existing workflow-ref specialization
fixtures where possible instead of introducing a parallel fixture system.

## Relationship To Existing Implementation Architectures

Existing slices reviewed:

- `docs/plans/LISP-PROC-REFS-PARTIAL-APPLICATION/design-gaps/procref-static-surface-and-resolution/implementation_architecture.md`

Decisions reused:

- `procedure_refs.py` remains the compile-time ProcRef authority module;
- ProcRef transport remains forbidden across runtime seams;
- module import/export resolution and canonical callable keys remain the source
  of procedure visibility;
- specialization is compile-time only and must not create runtime procedure
  values;
- source-map ownership stays on authored forms rather than generated runtime
  shims.

New decisions in this slice:

- add `BindProcExpr` and keyword-only partial application as authored syntax;
- allow lexical bound names in procedure-call position so ProcRef parameters can
  actually be invoked;
- introduce compiler-owned ProcRef specialization requests and deterministic
  specialized procedure naming;
- move procedure specialization earlier so effect summaries and lowering both
  operate on the same concrete compile-time callable identity;
- carry ordinary bound argument expressions and ProcRef bindings in procedure
  specialization metadata, not only workflow-ref bindings.

Conflicts or revisions:

- this slice does not revise the static-surface slice's decisions;
- it extends the earlier slice's explicit deferral of lowering by adding the
  first lowering-aware ProcRef path now that specialization is the selected
  work item;
- no revision is made to shared runtime, Semantic IR, pointer authority,
  variant proof, or command-adapter ownership boundaries.
