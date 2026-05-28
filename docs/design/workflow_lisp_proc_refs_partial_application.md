# Workflow Lisp ProcRef And Partial Application Delta

Status: accepted design delta / active implementation target
Extends: [Workflow Lisp Frontend Specification](workflow_lisp_frontend_specification.md)

This document defines the scoped language extension for compile-time procedure
references and explicit partial application in Workflow Lisp. The parent
frontend specification remains the umbrella language contract; this document is
the focused implementation target for the `ProcRef` / `bind-proc` tranche.

## Decision

Workflow Lisp will support higher-order procedural composition through
compile-time procedure references.

The accepted model is:

- `ProcRef[...]` types reference named `defproc` definitions.
- Procedure references resolve at parse/typecheck/module-link time.
- `(proc-ref name)` creates a compile-time reference to a visible `defproc`.
- `bind-proc` partially binds named arguments and produces a specialized
  compile-time procedure reference.
- Specialization happens before Core Workflow AST and Semantic IR lowering.
- Executable IR must contain no unresolved procedure values.
- Procedure references are not runtime values and may not be stored in state,
  artifacts, records, unions, ledgers, or result bundles.

Do not add runtime procedure values, general closures, provider-selected
procedures, dynamic dispatch, or procedure serialization in this tranche.

## Motivation

The current workflow stack repeatedly passes design documents, plans, provider
roles, prompt roles, check commands, target paths, state roots, and ledgers
through planning, implementation, review, and fix phases. The autonomous-drain
stack shows this concretely: selector, design-gap, work-item, plan, and
implementation calls repeatedly thread the same design, steering, ledger,
run-state, and provider-role inputs.

That explicit argument plumbing is lowerable, but it keeps reusable phase
skeletons from being expressed directly. A common pattern wants to abstract over
phase behavior while keeping the selected procedures statically visible:

```lisp
(call iter-proc
  :execute execute-proc
  :review review-proc
  :fix fix-proc
  :input input)
```

The procedure choices should be configurable by the caller but still known to
the compiler so the lowered workflow graph, effects, output contracts, and
source maps remain deterministic.

Macros are insufficient because this is semantic workflow behavior, not just
syntax rewriting. `WorkflowRef` is too coarse because these abstractions often
target `defproc` procedures that may lower inline or as private workflows.
Runtime first-class procedures are too broad because they would weaken static
graph identity, effect analysis, source maps, replay, and resume semantics.

`ProcRef` plus narrow `bind-proc` is therefore the first useful tranche: it
removes semantic boilerplate while preserving deterministic lowering, static
typechecking, effect visibility, source mapping, and existing runtime
boundaries.

## Syntax Delta

### Procedure Reference Types

`ProcRef` mirrors the `WorkflowRef` type shape but targets `defproc`.

```text
ProcRef[A -> B]
ProcRef[(A B) -> C]
ProcRef[() -> C]
```

The parameter list is the residual callable signature visible to the consumer.
Parameter names are not part of the `ProcRef` type, but named argument binding
uses the referenced procedure's declared parameter names.

### Procedure Reference Literal

Use an explicit literal form when a procedure is passed as a value:

```lisp
(proc-ref implementation/run)
```

Direct calls remain unchanged:

```lisp
(call implementation/run
  :ctx ctx
  :inputs inputs)
```

Bare procedure names are not `ProcRef` values in the first tranche. Requiring
`proc-ref` keeps procedure values visually distinct from ordinary calls and
gives diagnostics a single literal surface to target.

### Partial Application

`bind-proc` accepts a procedure reference and keyword bindings:

```lisp
(bind-proc (proc-ref implementation/run)
  :design design
  :plan plan
  :providers providers.implementation)
```

The result is a specialized compile-time `ProcRef` whose residual signature is
the original procedure signature with the bound parameters removed in original
parameter order.

Example:

```text
Original:
  implementation/run:
    (SelectedItem Design Plan Providers) -> ImplementationResult

Binding:
  (bind-proc (proc-ref implementation/run)
    :design design
    :plan plan
    :providers providers.implementation)

Residual:
  ProcRef[SelectedItem -> ImplementationResult]
```

Bindings are keyword-only in the first tranche. Positional binding, default
arguments, variadic keyword bags, and mixed positional/keyword binding are out
of scope.

## Typechecking Rules

The compiler must add a `ProcRefTypeRef` parallel to `WorkflowRefTypeRef`.

Validation rules:

- `(proc-ref name)` must resolve to a visible `defproc`.
- The referenced procedure's signature must match the expected `ProcRef`.
- `bind-proc` must receive a `ProcRef`.
- Every bound keyword must name a parameter in the referenced procedure.
- A parameter may be bound at most once.
- Each bound expression must typecheck against the corresponding parameter
  type.
- The residual signature preserves original parameter order for unbound
  parameters.
- A zero-argument residual procedure is allowed only where the expected type is
  `ProcRef[() -> R]`.
- Procedure references are compile-time values only and are rejected inside
  record fields, union fields, state bundles, artifacts, workflow outputs,
  provider results, command results, ledgers, and runtime loop state.

Named procedure refs may be forwarded through `defproc` parameters when the
parameter type is `ProcRef[...]`. They may not cross exported runtime workflow
boundaries as ordinary structured values.

## Module And Catalog Behavior

Procedure reference resolution uses the existing module and procedure catalog
authority:

- same-module `defproc` definitions are visible by local name;
- imported exported procedures are visible through their resolved module names
  or aliases;
- private procedures from other modules are not referenceable;
- procedure names that collide with functions, workflows, schemas, records, or
  macros are rejected by the existing callable-name collision rules.

`ProcRef` entries do not create runtime registry entries. The compiler may use a
reference/specialization environment during compilation, but there must be no
runtime procedure-value catalog.

## Specialization Rules

Specialization happens before ordinary `defproc` lowering.

The compiler must:

1. Resolve the base procedure reference.
2. Typecheck and record the bound arguments.
3. Compute the residual signature.
4. Create a deterministic hidden specialized procedure.
5. Substitute bound values at the specialized call site.
6. Continue through the existing `defproc` lowering path.

Generated names must be deterministic and collision-resistant. A recommended
shape is:

```text
%proc-ref.<module>.<procedure>.<stable-hash>
```

The stable hash should cover:

- resolved base procedure identity;
- bound parameter names;
- source identities for bound expressions where available;
- residual signature.

Specialization cycles are invalid. A procedure may not require a specialized
version of itself through a `ProcRef` chain unless the existing procedure-cycle
analysis can prove it is non-recursive after specialization.

## Lowering Rules

After specialization, lowering sees only ordinary concrete procedure calls.

`defproc :lowering` policy applies after specialization:

- `inline` specializes and then inlines the resulting body;
- `private-workflow` specializes and then emits a hidden private workflow;
- `auto` may choose inline or private workflow using the existing lowering
  policy.

Executable IR, runtime plans, debug YAML projections, run state, and artifact
bundles must not contain unresolved `ProcRef` values.

## Effect Rules

`proc-ref` and `bind-proc` do not introduce runtime effects by themselves.

The caller-visible effect summary for a procedure that accepts or calls a
`ProcRef` must include the selected procedure's transitive effects after
specialization. Bound values do not hide effects: if a bound value was produced
by an earlier effectful expression, that producer remains visible in normal
dataflow; if the specialized procedure later uses the bound value, the
procedure's reads/writes/calls/provider/command effects remain visible in the
specialized summary.

Effect checking must happen after procedure references are resolved and before
lowering commits generated nodes.

## Source Maps And Diagnostics

Generated specialized procedures must preserve provenance for:

- the original `defproc` definition;
- the `proc-ref` literal;
- the `bind-proc` form, if present;
- the call site that consumes the specialized reference;
- generated Core AST and Semantic IR nodes.

Diagnostics should point first to the most actionable authored form:

- unknown procedure: `(proc-ref name)`;
- signature mismatch: the argument that supplies the ref;
- bad binding name or duplicate binding: the `bind-proc` keyword;
- bad bound value type: the bound expression;
- runtime transport violation: the record/union/output/state field attempting
  to carry the `ProcRef`.

Required diagnostic codes:

- `proc_ref_unknown`
- `proc_ref_literal_required`
- `proc_ref_signature_invalid`
- `proc_ref_runtime_transport_forbidden`
- `proc_ref_binding_unknown`
- `proc_ref_binding_duplicate`
- `proc_ref_binding_type_invalid`
- `proc_ref_specialization_cycle`
- `proc_ref_private_import_invalid`

## Relationship To WorkflowRef

This feature deliberately reuses the architectural shape of `WorkflowRef`:

- references resolve at compile/module-link time;
- signatures are checked statically;
- specialization happens before runtime;
- generated nodes preserve source maps;
- effect summaries remain visible;
- runtime state cannot carry reference values.

The difference is target identity: `WorkflowRef` targets `defworkflow`;
`ProcRef` targets `defproc`.

## Non-Goals

Do not implement:

- runtime first-class procedures;
- closures over arbitrary locals;
- procedure serialization;
- provider-selected procedure values;
- dynamic dispatch in executable IR;
- storing procedure values in ledgers or result bundles;
- untyped `**kwargs` argument passing;
- procedure references inside records or unions;
- positional partial application;
- default argument semantics.

Those features require a broader runtime design for graph identity, effect
validation, source maps, replay, and resume semantics.

## Acceptance Tests

A first implementation must include positive tests proving:

- a `defproc` can accept a `ProcRef[...]` parameter;
- `(proc-ref name)` can pass a visible named procedure to that parameter;
- an imported exported `defproc` can be referenced;
- `bind-proc` binds a subset of arguments and exposes the correct residual
  signature;
- a specialized procedure can lower inline;
- a specialized procedure can lower as a private workflow when policy requires;
- effect summaries include selected and bound procedure behavior;
- source-map/explain artifacts expose the original `defproc`, `proc-ref`,
  `bind-proc`, specialization, and lowered nodes;
- executable IR and runtime plans contain no unresolved procedure values.

Negative tests must prove:

- unknown procedure reference is rejected;
- signature mismatch is rejected;
- duplicate bound argument is rejected;
- unknown bound argument is rejected;
- bad bound value type is rejected;
- private imported procedure reference is rejected;
- specialization cycle is rejected;
- provider/command outputs cannot produce `ProcRef`;
- records, unions, workflow outputs, artifacts, ledgers, and runtime state cannot
  contain `ProcRef`.

## Estimated Effort

Relative to the completed Workflow Lisp frontend implementation:

- plain compile-time `ProcRef`: about 5-10%;
- `ProcRef` plus `bind-proc`: about 12-20%;
- true runtime first-class procedures: 35-70% or more.

The implementation target for this tranche is `ProcRef` plus `bind-proc`.
