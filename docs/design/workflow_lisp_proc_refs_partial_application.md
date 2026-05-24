# Workflow Lisp Procedure References And Partial Application

Status: design note

This note records a recommended direction for higher-order procedural
composition in Workflow Lisp.

## Recommendation

Add compile-time procedure references and explicit partial application.

Do not add runtime procedure values or general closures as the next step.

The target feature is:

- `ProcRef[...]` types for passing named `defproc` procedures as arguments;
- `bind-proc` or an equivalent form for binding repeated context once;
- compile-time specialization before lowering;
- normal static workflow output after specialization.

This gives authors a way to write reusable phase skeletons without passing the
same `design`, `plan`, provider, prompt, and context arguments through every
call manually.

## Motivation

The current workflow stack repeatedly passes design documents, plans, provider
roles, prompt roles, check commands, and target paths through planning,
implementation, review, and fix phases.

That is explicit and lowerable, but it makes higher-level phase orchestration
hard to read. A common pattern wants to abstract over the phase behavior:

```lisp
(call iter-proc
  :execute execute-proc
  :review review-proc
  :fix fix-proc
  :input input)
```

The procedure choices should be configurable, but still statically known to the
compiler so the lowered workflow graph, effects, output contracts, and source
maps remain deterministic.

## Target Model

`ProcRef` is a compile-time reference to a named procedure with a declared
signature.

Example shape:

```lisp
(defproc iter-proc
  ((execute ProcRef[PhaseInput -> PhaseAttempt])
   (review  ProcRef[PhaseAttempt -> ReviewResult])
   (fix     ProcRef[ReviewResult -> PhaseInput])
   (input   PhaseInput))
  -> PhaseResult

  ...)
```

The callee passed to `execute`, `review`, or `fix` must be known at compile or
module-link time. The compiler specializes `iter-proc` before lowering.

## Partial Application

To avoid repeatedly passing large context records, add a partial-application
form such as `bind-proc`.

Example shape:

```lisp
(let* ((run-impl
         (bind-proc implementation/run
           :design design
           :plan plan
           :providers providers.implementation)))

  (call iter-proc
    :execute run-impl
    :review implementation/review
    :fix implementation/fix
    :input selected))
```

`bind-proc` does not create a runtime closure. It creates a specialized
compile-time procedure reference with some arguments already bound.

The generated procedure is hidden/internal, source-mapped to the `bind-proc`
form, and visible to effect analysis.

## Lowering Model

The compiler should lower this feature in four stages:

1. Resolve named procedure references through the module/procedure catalog.
2. Check each `ProcRef[...]` argument against the expected signature.
3. Specialize procedures and partial applications into concrete hidden
   procedures or inline procedure bodies.
4. Lower the specialized graph through the existing `defproc` lowering path.

After specialization, executable IR should contain no unresolved procedure
values.

## Constraints

The first tranche should be intentionally limited:

- procedure refs are compile-time only;
- refs cannot be produced by providers or commands;
- refs cannot be stored in state, artifacts, records, or unions;
- refs cannot cross runtime workflow boundaries as ordinary values;
- no arbitrary lexical closures;
- no runtime dispatch on procedure values;
- no untyped `**kwargs` argument passing.

Use typed records for context instead of variadic keyword bags.

## Non-Goals

Do not implement:

- runtime first-class procedures;
- closures over arbitrary locals;
- procedure serialization;
- provider-selected procedure values;
- dynamic dispatch in executable IR;
- storing procedure values in ledgers or result bundles.

Those features would require a broader runtime design for graph identity,
effect validation, source maps, replay, and resume semantics.

## Relationship To WorkflowRef

This feature should reuse the architectural shape of `WorkflowRef`:

- references resolve at compile/module-link time;
- signatures are checked statically;
- specialization happens before runtime;
- generated nodes preserve source maps;
- effect summaries remain visible.

The difference is that `ProcRef` targets `defproc`, not `defworkflow`.

## Estimated Effort

Relative to the completed Workflow Lisp frontend implementation:

- plain compile-time `ProcRef`: about 5-10%;
- `ProcRef` plus `bind-proc`: about 12-20%;
- true runtime first-class procedures: 35-70% or more.

The recommended direction is `ProcRef` plus `bind-proc`.

## Acceptance Sketch

A first implementation should prove:

- a `defproc` can accept a `ProcRef[...]` parameter;
- a named procedure can be passed to that parameter;
- signature mismatches produce source-mapped diagnostics;
- `bind-proc` can bind a subset of arguments and produce a specialized
  procedure reference;
- the specialized output has static lowered workflow structure;
- effect summaries include the selected and bound procedure behavior;
- no runtime state or artifact contains a procedure value.

