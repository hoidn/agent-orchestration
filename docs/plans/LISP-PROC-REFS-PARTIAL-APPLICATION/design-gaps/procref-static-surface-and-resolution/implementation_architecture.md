# ProcRef Static Surface And Resolution Implementation Architecture

Status: draft
Design gap id: `procref-static-surface-and-resolution`
Target design: `docs/design/workflow_lisp_proc_refs_partial_application.md`
Baseline compatibility: `docs/design/workflow_lisp_frontend_specification.md`

## Scope

This slice adds the compile-time `ProcRef` surface that the ProcRef delta
depends on:

- `ProcRef[...]` type parsing and resolved type references;
- `(proc-ref name)` expression literals;
- compile-time resolution of visible `defproc` signatures through the existing
  module import/export and procedure catalog machinery;
- transport rejection for runtime boundaries and other persisted surfaces;
- targeted diagnostics and source-mapped authored spans for the static surface.

This slice does not implement:

- `bind-proc`;
- residual-signature specialization;
- calling through procedure-reference values;
- lowering specialized procedures;
- runtime procedure values, serialization, or dynamic dispatch.

Those behaviors stay in later ProcRef gaps. This architecture is intentionally
bounded to the prerequisite static surface named by the selector.

## Problem Statement

The current frontend already has a full compile-time `WorkflowRef` path:

- `WorkflowRef[...]` parsing in `type_expressions.py`;
- `WorkflowRefTypeRef` and runtime-transport guards in `type_env.py`,
  `workflows.py`, and `loops.py`;
- `(workflow-ref ...)` literals in `expressions.py`;
- signature resolution and validation in `workflow_refs.py`;
- caller-side typechecking and lowering-time specialization hooks.

There is no equivalent surface for procedures. The target delta requires a
compile-time-only procedure-reference mechanism that reuses existing frontend
authority:

- procedure identity comes from the procedure catalog and module export surface;
- authoring uses explicit literals instead of bare names;
- unresolved procedure values never reach runtime state or workflow outputs.

The selected gap is the smallest slice that establishes those invariants
without prematurely implementing specialization or a second callable-runtime
model.

## Design Constraints

The architecture must preserve the baseline frontend rules:

- compile-time references are not runtime values;
- module import/export surfaces remain the authority for visibility;
- source maps stay attached to authored syntax nodes rather than generated
  runtime shims;
- macros do not hide effects;
- Core AST, Semantic IR, runtime execution, and command-adapter behavior are
  not redefined here.

The command-adapter contract was reviewed as a cross-cutting constraint. This
slice does not add scripts, command steps, legacy adapters, or runtime-native
effects.

## Proposed Architecture

### 1. Add a dedicated ProcRef type family parallel to WorkflowRef

Extend `orchestrator/workflow_lisp/type_expressions.py` with a new
`ProcRefTypeExpr` and parse branch for `ProcRef[...]`.

Key parsing rules:

- preserve the existing `WorkflowRef[...]` grammar unchanged;
- allow `ProcRef[A -> B]`, `ProcRef[(A B) -> C]`, and `ProcRef[() -> C]`;
- keep zero-parameter parsing exclusive to `ProcRef`; do not weaken current
  `WorkflowRef` parsing;
- reuse the existing top-level-arrow parsing and parameter splitting logic
  rather than inventing a second mini-parser.

The implementation should extract the current workflow-ref parameter parsing
into a small shared callable-ref helper with a mode flag:

- `WorkflowRef`: one or more parameters required;
- `ProcRef`: zero or more parameters allowed.

This keeps the grammar aligned while preserving the current workflow-ref
contract.

### 2. Add a resolved ProcRef type to the frontend type environment

Extend `orchestrator/workflow_lisp/type_env.py` with `ProcRefTypeRef` and add
it to `TypeRef`.

`ProcRefTypeRef` should contain:

- stable rendered `name`;
- ordered `param_type_refs`;
- `return_type_ref` as generic `TypeRef`, not restricted to record/union.

Differences from `WorkflowRefTypeRef` are intentional:

- a procedure reference may have zero residual parameters;
- procedure returns follow ordinary `defproc` signature rules instead of
  workflow-boundary rules.

Transport rules remain strict:

- `ProcRef` cannot appear inside records, unions, workflow outputs, provider or
  command results, ledgers, artifacts, or loop-carried runtime state;
- nested `ProcRef` inside `Optional`, `List`, or `Map` is rejected;
- `ProcRef` cannot appear inside `WorkflowRef` signatures or vice versa unless a
  later design gap explicitly permits that.

The simplest implementation is to generalize the existing workflow-ref
containment helpers into a compile-time-callable-ref helper that detects both
`WorkflowRefTypeRef` and `ProcRefTypeRef`, while preserving the existing
diagnostic behavior for workflow refs.

Required diagnostics for this slice:

- `proc_ref_runtime_transport_forbidden`
- `proc_ref_signature_invalid`

Existing workflow-ref diagnostics remain unchanged.

### 3. Add an authored `(proc-ref ...)` literal expression

Extend `orchestrator/workflow_lisp/expressions.py` with:

- `ProcRefLiteralExpr`;
- elaboration for `(proc-ref name)`;
- source-mapped span, form path, and expansion-stack preservation identical to
  `WorkflowRefLiteralExpr`.

The literal must resolve the authored symbol through the existing
`_ACTIVE_PROCEDURE_NAME_RESOLVER` so imported exported procedures canonicalize
to the same callable key used everywhere else.

This slice does not change procedure-call syntax. Bare names remain ordinary
procedure call heads, not procedure-reference values.

### 4. Resolve ProcRef literals through the procedure catalog, not a runtime registry

Add a new helper module:

- `orchestrator/workflow_lisp/procedure_refs.py`

It should mirror the narrow authority role of `workflow_refs.py`, but for
`defproc` instead of `defworkflow`.

Owned data shapes:

- `ProcRefAuthoritySource`
- `ResolvedProcRef`
- `ProcRefRequirement`

Owned helper behavior:

- `proc_ref_type_from_signature(signature)`
- `validate_proc_ref_signature(expected, actual_signature, ...)`
- `resolve_proc_ref_name(...)`
- `resolve_proc_ref_expr(...)`
- `proc_ref_target_name(...)`

Resolution inputs:

- `ProcedureCatalog` for visible signatures;
- optional import-visibility context when the literal used a qualified imported
  name.

Resolution outputs:

- canonical procedure name;
- ordered signature parameter types;
- resolved return type;
- authority source metadata for diagnostics and future specialization;
- no runtime registry entries.

This module deliberately does not own lowering or specialization. It only
creates a compile-time resolved reference object that later gaps can consume.

### 5. Preserve module/export authority and emit a targeted private-import diagnostic

The parent delta requires imported exported procedures to be referenceable and
private imported procedures to be rejected distinctly.

Current procedure resolution already canonicalizes exported/imported procedure
names through `ModuleImportScope` and `_procedure_name_resolver`, but a private
import currently degrades into a generic unknown-local lookup.

This slice should tighten that behavior for `proc-ref` literals only:

- if the authored literal names an explicitly imported module-qualified
  procedure that is not exported in that module’s `ModuleExportSurface`,
  resolution raises `proc_ref_private_import_invalid`;
- if the module path is visible and the procedure is exported, resolution uses
  the existing canonical callable key;
- if the target does not exist at all, resolution raises `proc_ref_unknown`.

That distinction belongs in `procedure_refs.py`, not in a new runtime catalog.
It can be implemented by threading import-scope visibility metadata into
ProcRef resolution while leaving ordinary procedure calls unchanged.

### 6. Typecheck ProcRef literals and forwarded bindings as compile-time values

Extend `orchestrator/workflow_lisp/typecheck.py` with logic parallel to the
workflow-ref helpers:

- direct `ProcRefLiteralExpr` typechecks to `ProcRefTypeRef` using the resolved
  procedure signature;
- a `NameExpr` already bound to `ProcRefTypeRef` is treated as a forwarded
  compile-time proc ref, not a runtime value;
- when a procedure parameter expects `ProcRefTypeRef`, the caller may supply
  only a `proc-ref` literal or a forwarded `ProcRef` binding;
- any other expression in that position raises `proc_ref_literal_required`.

This slice does not add `bind-proc`, calling through a `ProcRef`, or any
procedure-reference specialization step. The only supported authored values are
literal references and forwarded bindings.

### 7. Reject runtime transport at the same seams that already reject WorkflowRef

Transport guards must be extended at the existing runtime-seam boundaries:

- `type_env.py` for record/union/collection transport rejection;
- `workflows.py` for runtime workflow boundaries;
- `loops.py` for `loop/recur` state and result transport.

The baseline rule is unchanged: compile-time reference values do not cross into
runtime-persisted state.

For this gap, workflows may not accept top-level `ProcRef` parameters at all.
That keeps the static surface bounded to compile-time procedure composition and
avoids inventing runtime procedure transport before specialization exists.

### 8. Lowering behavior stays explicitly deferred

No new lowering path is introduced in this slice.

Why:

- `bind-proc` and residual-signature computation are selected as later gaps;
- calling through a `ProcRef` requires specialization before lowering;
- executable IR must contain no unresolved procedure values.

Implementation consequence:

- stage 3 may typecheck authored `ProcRef` values and procedure signatures;
- any executable path that would require procedure-reference specialization
  before lowering must fail early with a targeted lowering diagnostic, using
  the existing lowering error taxonomy rather than inventing runtime fallback.

This keeps the compiler honest: the static surface exists, but no runtime or
hidden adapter is introduced to fake unsupported semantics.

## Owned Components

This slice owns changes in:

- `orchestrator/workflow_lisp/type_expressions.py`
- `orchestrator/workflow_lisp/type_env.py`
- `orchestrator/workflow_lisp/expressions.py`
- `orchestrator/workflow_lisp/procedure_refs.py` (new)
- `orchestrator/workflow_lisp/typecheck.py`
- `orchestrator/workflow_lisp/compiler.py` only as needed to thread resolvers
  and imported-procedure visibility metadata
- `orchestrator/workflow_lisp/workflows.py` and `orchestrator/workflow_lisp/loops.py`
  only for transport guards
- focused tests covering the new static surface

## Intentionally Not Owned

This slice does not own or redefine:

- Core Workflow AST
- Semantic Workflow IR
- runtime execution
- command adapters or runtime-native effects
- `bind-proc`
- specialization naming and lowering of procedure refs
- workflow-call lowering semantics outside existing runtime-transport guards

## Diagnostics

This slice should add or activate:

- `proc_ref_unknown`
- `proc_ref_literal_required`
- `proc_ref_signature_invalid`
- `proc_ref_runtime_transport_forbidden`
- `proc_ref_private_import_invalid`

It should not add `bind-proc` diagnostics yet. Those belong to the partial
application and specialization gaps.

## Test Strategy

Add focused tests proving:

- `ProcRef` type parsing supports one-arg, multi-arg, and zero-arg forms;
- a `defproc` parameter can resolve a local visible `(proc-ref local-proc)`;
- an imported exported `defproc` can resolve through canonical module keys;
- a private imported `defproc` literal fails with
  `proc_ref_private_import_invalid`;
- a proc-ref literal with the wrong signature fails with
  `proc_ref_signature_invalid`;
- non-literal/non-forwarded proc-ref arguments fail with
  `proc_ref_literal_required`;
- `ProcRef` transport is rejected from records, unions, workflow boundaries,
  collections, and `loop/recur` carried state.

Keep the tests narrow and reuse the existing workflow-ref fixture patterns where
possible instead of inventing a separate fixture architecture.

## Relationship To Existing Implementation Architectures

Existing slices reviewed:

- none; the generated architecture index lists zero prior implementation
  architecture documents for this drain.

Decisions reused:

- canonical callable keys from `modules.py`;
- procedure visibility from `ModuleExportSurface` and `ModuleImportScope`;
- compile-time reference authority pattern already used by `workflow_refs.py`;
- source-map ownership on authored expression/type nodes;
- runtime-transport rejection pattern already used for `WorkflowRef`.

New decisions in this slice:

- introduce a dedicated `ProcRef` type/literal/resolution path parallel to, but
  separate from, `WorkflowRef`;
- allow zero-argument callable signatures only for `ProcRef`;
- keep `ProcRef` compile-time-only and reject all runtime transport;
- emit `proc_ref_private_import_invalid` instead of collapsing imported-private
  references into a generic unknown-procedure failure.

Conflicts or revisions:

- none to prior architecture slices, because none exist;
- no revision to shared runtime, source-map, Semantic IR, or command-adapter
  ownership boundaries.
