# Workflow Lisp Local ProcRef Bindings Delta

Status: proposed follow-on design delta
Extends: `workflow_lisp_proc_refs_partial_application.md`
Parent contract: `workflow_lisp_frontend_specification.md`
Primary feature: `let-proc` local compile-time procedure bindings
Non-goal: runtime closures, runtime first-class procedures, or bypassing unresolved effectful-composition lowering gaps

This draft assumes the accepted ProcRef / `bind-proc` delta remains the semantic base: `ProcRef[...]` targets named `defproc`s, `(proc-ref name)` is explicit, `bind-proc` is keyword-only partial application, specialization happens before Core AST / Semantic IR lowering, and executable/runtime artifacts must not contain unresolved procedure values.

It also keeps the parent frontend constraints intact: Workflow Lisp lowers through Core AST, shared validation, Semantic IR, and executable IR; it is not a runtime replacement, not a YAML text generator, and frontend forms are implementation-ready only when they can lower into the shared contracts. The effect and source-map constraints are likewise inherited: abstractions must not hide provider/command/state/artifact effects, and generated Core/Semantic/Executable nodes must remain source-mapped and diagnosable.

## 1. Summary

This document defines `let-proc`, a minimal compile-time lexical procedure-binding form for Workflow Lisp.

`let-proc` lets an author define a local procedure near the point of use and pass it through the accepted ProcRef mechanism:

```lisp
(let* ((impl-provider providers.implementation))

  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      (call implementation/run
        :selected selected
        :design design
        :plan plan
        :providers impl-provider))

    (call iter-proc
      :execute (proc-ref run-impl)
      :input selected)))
```

The local procedure is not a runtime closure. It is closure-converted by the compiler into a private generated `defproc`-equivalent, specialized with its explicit captures, then lowered through the same path as an ordinary authored `defproc`.

The core invariant is:

```text
If the equivalent ordinary generated defproc cannot lower,
let-proc cannot lower it either.
```

`let-proc` is lexical syntax over generated `defproc` plus existing ProcRef semantics. It is not a new lowering system.

## 2. Decision

Add `let-proc` as a near-term ergonomic layer over accepted ProcRef / `bind-proc`.

A V1 `let-proc` binding:

- introduces exactly one local procedure name;
- declares explicit residual parameters;
- declares an explicit return type;
- declares explicit identifier captures;
- contains one body expression;
- may be referenced only through `(proc-ref local-name)`;
- closure-converts to a private generated `defproc`-equivalent;
- lowers through ordinary `defproc` lowering;
- produces no runtime procedure value.

The generated procedure is private and compiler-internal. It may appear in diagnostics, source maps, or explain/debug output, but it is not importable, exportable, or author-referenceable by generated name.

## 3. Relationship To ProcRef / `bind-proc`

The accepted ProcRef delta remains the semantic authority for procedure references.

`let-proc` does not change these rules:

- `ProcRef[...]` is a compile-time procedure-reference type.
- `(proc-ref name)` is required when a procedure is passed as a value.
- Bare procedure names are not procedure values.
- `bind-proc` specializes a known procedure reference by binding named arguments.
- Specialization happens before Core AST / Semantic IR lowering.
- Executable IR must contain no unresolved procedure values.
- Procedure refs may not be stored in state, artifacts, records, unions, ledgers, result bundles, provider results, command results, or workflow outputs.

`let-proc` adds one new way to introduce a compile-time procedure reference:

```text
named defproc              -> (proc-ref implementation/run)
specialized named defproc  -> (bind-proc (proc-ref implementation/run) ...)
local generated defproc    -> (proc-ref run-impl) inside let-proc scope
```

The local case is still a ProcRef. It is not a different kind of value.

## 4. Dependency Boundary

V1 `let-proc` depends on a well-defined ordinary `defproc` lowering boundary.

It may ship before all Workflow Lisp effectful-composition gaps are fixed only if unsupported `let-proc` bodies are rejected with the same underlying composition/lowering diagnostics that an equivalent ordinary generated `defproc` would produce.

Full realistic `let-proc` bodies depend on the Workflow Lisp effectful-composition backlog, including:

- effectful `let*` bindings;
- effectful `match` arms;
- `with-phase` as a composable expression;
- same-file call bindings for locally constructed records;
- reusable workflow boundary handling for generated write roots.

`let-proc` must not be used to bypass unresolved lowering gaps.

A `let-proc` body is valid only when the generated `defproc`-equivalent, used in the same enclosing workflow/procedure context, lowers to Core AST that passes the same shared validation path as an authored `defproc` would.

If the equivalent generated `defproc` cannot lower, the `let-proc` body must be rejected for the same underlying reason.

## 5. Motivation

The accepted ProcRef / `bind-proc` delta solves the safe higher-order procedure problem: reusable phase skeletons can accept statically known procedural behavior without adding runtime closures or dynamic dispatch.

However, explicit `bind-proc` is still awkward when the author wants to define a local phase behavior using values already in scope. Without `let-proc`, the author must either:

- create a named module-level wrapper `defproc`;
- write a verbose `bind-proc` specialization over an existing procedure;
- avoid reusable phase skeletons and keep threading context manually.

`let-proc` addresses only that ergonomic gap.

It should feel like local procedural structure, but compile like ordinary generated workflow procedure code:

```text
local syntax
-> generated private defproc-equivalent
-> ProcRef specialization
-> ordinary defproc lowering
-> shared validation
-> Semantic IR
-> executable IR
```

This gives authors local structure without weakening static effect analysis, source maps, validation, replay/resume assumptions, or runtime boundaries.

## 6. Non-Goals

The following are non-goals for this delta:

- runtime first-class procedures;
- runtime closures;
- arbitrary lexical capture;
- implicit broad closure conversion;
- provider-selected procedure values;
- model-selected procedure values;
- command-produced procedure values;
- dynamic dispatch in executable IR;
- procedure serialization;
- storing procedure references in records, unions, artifacts, state, ledgers, result bundles, workflow outputs, provider results, or command results;
- using `let-proc` to make currently invalid effectful compositions appear valid;
- a second lowering system;
- a second effect-analysis system;
- a second source-map system;
- a second semantic registry for procedure specializations.

The especially important non-goal is:

```text
If a body cannot lower as an ordinary generated defproc,
wrapping it in let-proc must not change that.
```

## 7. V1 Syntax

V1 supports exactly one local procedure binding per `let-proc`.

```lisp
(let-proc
  (name
    ((param ParamType) ...)
    -> ReturnType
    :captures (capture-name ...)
    body-form)

  body...)
```

Example:

```lisp
(let* ((impl-provider providers.implementation))

  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      (call implementation/run
        :selected selected
        :design design
        :plan plan
        :providers impl-provider))

    (call iter-proc
      :execute (proc-ref run-impl)
      :input selected)))
```

### 7.1 Capture Syntax

V1 captures must be simple identifiers.

Valid:

```lisp
:captures (design plan impl-provider)
```

Invalid in V1:

```lisp
:captures (providers.implementation)
```

Field selections must be named before capture:

```lisp
(let* ((impl-provider providers.implementation))
  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      ...)

    ...))
```

Capture aliases are deferred. This is invalid in V1:

```lisp
:captures ((impl-provider providers.implementation) design plan)
```

The field-selection restriction avoids ambiguous or invalid generated parameter names such as `providers.implementation`.

### 7.2 Local Procedure Reference

A local procedure may be passed only through explicit `(proc-ref local-name)`.

Valid:

```lisp
(call iter-proc
  :execute (proc-ref run-impl)
  :input selected)
```

Invalid:

```lisp
(call iter-proc
  :execute run-impl
  :input selected)
```

Bare local procedure names are not values.

### 7.3 Direct Call Sugar Deferred

V1 does not support direct calls to local procedures:

```lisp
(call run-impl :selected selected)
```

That form is deferred. V1 uses only `(proc-ref local-name)`.

## 8. V1 Body Boundary

In V1, a `let-proc` body may contain only forms currently supported by ordinary `defproc` lowering and shared workflow validation.

Unsupported effectful composition patterns must be rejected, including but not limited to:

- `match` as an intermediate effectful `let*` binding, when unsupported by ordinary `defproc` lowering;
- `with-phase` as an intermediate binding, when unsupported by ordinary `defproc` lowering;
- effectful `match` arms that do not lower cleanly;
- stdlib forms whose generated write roots cannot cross reusable workflow boundaries;
- same-file call bindings for locally constructed records, when unsupported by ordinary `defproc` lowering.

The diagnostic must preserve the original lowering cause and add local-procedure context.

Example invalid V1 body:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (ctx providers)
    (let* ((attempt (call provider/run :ctx ctx :selected selected))
           (decision
             (match attempt
               ((OK value)    (call review/run :value value))
               ((ERR reason)  (call fix/run :reason reason)))))
      decision))

  (call iter-proc
    :execute (proc-ref run-impl)
    :input selected))
```

Expected diagnostic class:

```text
unsupported effectful composition inside local procedure body
```

not:

```text
ProcRef runtime transport violation
```

unless the actual failure is runtime transport of a procedure reference.

## 9. Nested `let-proc`

V1 rejects nested `let-proc`.

A `let-proc` body may not contain another `let-proc` form.

Invalid in V1:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)

    (let-proc
      (review-local
        ((attempt Attempt)) -> ReviewResult
        :captures (design)
        ...)

      ...))

  ...)
```

Rationale:

Nested local procedure bindings require additional rules for lexical procedure environments, capture visibility, source-map stacking, generated procedure identity, and collision behavior.

A later design may allow nested `let-proc` after V1 source maps, capture metadata, and name-resolution diagnostics are stable.

## 10. Multiple Bindings And Recursion

V1 supports one binding per `let-proc`.

This means V1 does not support sibling bindings:

```lisp
(let-proc
  ((run-impl ...)
   (review-impl ...))
  ...)
```

That syntax is invalid in V1.

V1 also rejects recursive local procedures. The local procedure body may not reference its own local name through `(proc-ref name)`.

Invalid:

```lisp
(let-proc
  (loop-impl
    ((x X)) -> Y
    :captures ()
    (call something
      :next (proc-ref loop-impl)
      :x x))

  ...)
```

Any specialization cycle involving a local procedure is rejected.

## 11. Name Resolution

`let-proc` introduces one name into the lexical procedure namespace.

Resolution of `(proc-ref name)` proceeds as follows:

1. Check the active V1 `let-proc` lexical procedure binding, if any.
2. If no lexical binding matches, resolve through the visible module/procedure catalog.
3. Reject references to the lexical procedure outside its lexical scope.
4. Reject same-scope collisions between the local procedure name and ordinary value names.
5. Reject authored references to generated procedure names.

The local procedure name is visible only in the body following the binding.

Example:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)
    ...)

  ;; visible here
  (call iter-proc
    :execute (proc-ref run-impl)
    :input selected))
```

Invalid outside the lexical body:

```lisp
(proc-ref run-impl)
```

V1 should reject same-scope name collisions even if the implementation has separate value/procedure namespaces.

Invalid:

```lisp
(let* ((run-impl some-value))
  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design)
      ...)
    ...))
```

## 12. Lowering Rule

`let-proc` closure conversion produces an ordinary generated `defproc`-equivalent node before effect analysis and procedure lowering.

From that point forward, the generated procedure must pass the same path as an authored `defproc`:

```text
let-proc source
-> lexical procedure discovery
-> capture validation
-> closure conversion
-> private generated defproc-equivalent node
-> ordinary defproc typechecking
-> ordinary effect analysis
-> ordinary defproc lowering
-> shared validation
-> Semantic IR
-> executable IR
```

No `let-proc`-specific body lowerer is allowed.

No special exemption is allowed for generated procedures.

No body form may lower inside `let-proc` unless the same body form can lower inside the equivalent ordinary generated `defproc`.

## 13. Internal Compiler Model

Author source:

```lisp
(let* ((impl-provider providers.implementation))

  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      (call implementation/run
        :selected selected
        :design design
        :plan plan
        :providers impl-provider))

    (call iter-proc
      :execute (proc-ref run-impl)
      :input selected)))
```

Conceptual compiler model:

1. Discover local procedure binding:

   ```text
   run-impl : ProcRef[SelectedItem -> ImplementationResult]
   ```

2. Generate private `defproc`-equivalent:

   ```text
   %let-proc/run-impl/<stable-id>
     captures:
       design
       plan
       impl-provider

     residual parameters:
       selected

     body:
       (call implementation/run
         :selected selected
         :design design
         :plan plan
         :providers impl-provider)
   ```

3. Specialize the generated procedure by binding captures:

   ```text
   bound:
     design = design
     plan = plan
     impl-provider = impl-provider

   residual:
     selected -> ImplementationResult
   ```

4. Resolve `(proc-ref run-impl)` to the specialized compile-time ProcRef.

5. Erase the local procedure binding before executable IR.

This is not author-facing desugaring.

The compiler must not introduce an ordinary runtime `let*` value named `run-impl`.

The compiler must not emit a runtime closure object.

The compiler must not emit executable IR containing a ProcRef.

## 14. Generated Procedure Privacy

A `let-proc` binding closure-converts to a private compiler-generated `defproc`-equivalent.

Generated local procedures are:

- not exportable;
- not importable;
- not addressable by authored `(proc-ref %generated-name)` forms;
- not visible in ordinary module/procedure lookup;
- not stable public API;
- not valid workflow entrypoints.

The generated name may appear in diagnostics, source maps, explain output, and debug metadata, but it is not an author-referenceable symbol.

Only the lexical name introduced by `let-proc` may be referenced, and only inside its lexical scope:

```lisp
(proc-ref run-impl)
```

Invalid:

```lisp
(proc-ref %let-proc/run-impl/abc123)
```

The generated procedure exists to reuse the ordinary `defproc` lowering path, not to create a new module-level procedure.

## 15. Type Rules

A `let-proc` binding has a residual ProcRef type derived from its declared parameter list and return type.

Example:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)
    ...)
  ...)
```

Local type:

```text
run-impl : ProcRef[SelectedItem -> ImplementationResult]
```

The captures are not part of the public residual signature.

The private generated procedure has an expanded internal signature:

```text
%let-proc/run-impl/<stable-id> :
  (Design, Plan, ImplementationProviderRole, SelectedItem)
  -> ImplementationResult
```

But the local procedure reference exposed to consumers remains:

```text
ProcRef[SelectedItem -> ImplementationResult]
```

Type validation must check:

- each parameter has an explicit type;
- return type is explicit;
- each capture name resolves to an in-scope value;
- each capture is a simple identifier in V1;
- duplicate captures are rejected;
- the body returns the declared return type;
- `(proc-ref local-name)` matches the expected ProcRef signature at use sites.

## 16. Capture Semantics

Captures are ordinary dataflow inputs to the generated private procedure.

They are not closure fields.

They are not serialized procedure environments.

They do not create runtime procedure values.

In V1:

- captures are explicit;
- captures are simple identifiers;
- captures are bound at specialization time;
- capture expressions are not evaluated by a special `let-proc` evaluator;
- field selections must be named before capture.

Valid:

```lisp
(let* ((impl-provider providers.implementation))
  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      ...)
    ...))
```

Invalid:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design providers.implementation)
    ...)
  ...)
```

Deferred:

```lisp
:captures ((impl-provider providers.implementation) design plan)
```

Capture aliases are useful, but not in V1.

## 17. Effect Rules

`let-proc` does not create runtime effects by itself.

Effects inside the generated procedure body are ordinary procedure effects and must be visible through the existing effect graph and shared validation path.

The rule is:

```text
If an ordinary generated defproc body would expose effect E,
then the equivalent let-proc body must expose effect E.
```

And conversely:

```text
If ordinary defproc lowering cannot represent effect E yet,
let-proc must not invent a representation for E.
```

Effects from a local procedure body must be included in the caller-visible summary after ProcRef resolution and specialization.

For V1, the expected positive effect case is intentionally simple:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)
    (call implementation/run
      :selected selected
      :design design
      :plan plan
      :providers impl-provider))

  (call iter-proc
    :execute (proc-ref run-impl)
    :input selected))
```

The effect summary must show the transitive effects of `implementation/run` after the local procedure is specialized and consumed.

## 18. Source Maps

Generated nodes must be source-mapped to:

- the `let-proc` form;
- the local procedure name;
- the parameter list;
- the return type;
- the capture list;
- the body expression;
- the `(proc-ref local-name)` consumer;
- the private generated `defproc`-equivalent node;
- generated Core AST nodes;
- generated Semantic IR nodes;
- executable nodes derived from the generated procedure.

The invariant is:

```text
A diagnostic from the generated procedure must explain both:
  - the original lowering/type/effect/source-map cause;
  - that the failure occurred inside local procedure <name>.
```

Example diagnostic shape:

```text
effectful_match_intermediate_binding_unsupported:
  `match` cannot currently lower as an intermediate effectful let* binding.

  inside local procedure:
    run-impl

  source:
    <source span of unsupported match>

  note:
    let-proc bodies use the same lowering path as ordinary generated defproc bodies.
```

Do not collapse unrelated body-lowering failures into generic proc-ref diagnostics.

## 19. Explain / Debug Metadata

The first implementation should emit minimal explain/debug metadata for generated local procedures:

- local procedure name;
- private generated procedure name;
- source span;
- residual signature;
- explicit capture list;
- generated lowering policy;
- source-map links for generated nodes.

This metadata is not a semantic registry.

It must not become an alternate authority for:

- lowering;
- effect analysis;
- procedure resolution;
- runtime behavior;
- replay/resume;
- state layout;
- artifact identity;
- workflow call identity.

The semantic authority remains the generated Core AST, Semantic IR, effect graph, source map, and shared validation pipeline.

Suggested minimal internal shape:

```yaml
kind: let-proc-generated-procedure
local_name: run-impl
generated_name: "%let-proc/run-impl/<stable-id>"
source_span: ...
residual_signature:
  params:
    - name: selected
      type: SelectedItem
  return: ImplementationResult
captures:
  - name: design
    type: Design
    source_span: ...
  - name: plan
    type: Plan
    source_span: ...
  - name: impl-provider
    type: ImplementationProviderRole
    source_span: ...
lowering_policy: inline
source_map_refs:
  let_proc_form: ...
  generated_defproc: ...
  proc_ref_consumer: ...
```

This schema is illustrative, not a public stable manifest.

## 20. Diagnostics

Diagnostics for `let-proc` must preserve the original failure cause.

A body-lowering failure should use the ordinary lowering diagnostic, with local-procedure context added.

Example:

```text
effectful_match_intermediate_binding_unsupported:
  `match` cannot currently lower as an intermediate effectful let* binding.

  inside local procedure:
    run-impl
```

Not:

```text
proc_ref_runtime_transport_forbidden
```

unless the actual failure is procedure-reference transport.

### 20.1 Diagnostic Classes

V1 should include these diagnostic classes. Exact diagnostic-code names may be implementation-defined.

Name resolution:

- unknown local procedure;
- local ProcRef outside lexical scope;
- local procedure/value name collision;
- generated procedure name referenced by author;
- generated procedure export/import attempt.

Capture validation:

- missing capture list;
- unknown capture;
- duplicate capture;
- non-identifier capture.

Type validation:

- missing parameter type;
- missing return type;
- body return type mismatch;
- ProcRef signature mismatch.

Lowering/effect/source-map validation:

- unsupported effectful composition in local procedure body;
- specialization cycle;
- missing generated-node source map;
- missing effect summary;
- ProcRef escaped into runtime representation;
- runtime procedure value emitted into executable IR.

## 21. Validation Rules

The compiler must reject:

- missing parameter type;
- missing return type;
- missing `:captures`;
- unknown capture;
- duplicate capture;
- non-identifier capture;
- field-selection capture in V1;
- capture alias in V1;
- body return type mismatch;
- bare local procedure name used as a value;
- `(proc-ref local-name)` outside lexical scope;
- direct `(call local-name ...)` in V1;
- nested `let-proc` in V1;
- multiple sibling `let-proc` bindings in V1;
- recursive local procedure in V1;
- generated procedure name referenced by authored source;
- generated procedure exported or imported;
- unsupported effectful composition in the body;
- storing local ProcRef in record, union, artifact, state, ledger, result bundle, workflow output, provider result, or command result;
- provider/model/command-produced procedure refs;
- dynamic dispatch in executable IR;
- runtime procedure values in executable IR;
- missing source-map/explain metadata for generated nodes.

## 22. V1 Restrictions

V1 allows:

- one local `let-proc` binding;
- explicit `:captures`;
- identifier captures only;
- explicit parameter types;
- explicit return type;
- use through `(proc-ref local-name)`;
- closure conversion to a private generated `defproc`-equivalent;
- ordinary `defproc` lowering only;
- simple provider/command/workflow-call bodies already supported by ordinary `defproc` lowering.

V1 rejects:

- nested `let-proc`;
- multiple sibling local procedure bindings;
- recursive local procedures;
- capture inference;
- field-selection captures;
- capture aliases;
- direct `(call local-proc ...)` sugar;
- author references to generated procedure names;
- exporting or importing generated local procedures;
- unsupported effectful composition in the body;
- runtime procedure values;
- storing local ProcRefs in records, unions, artifacts, state, ledgers, or outputs;
- provider/model/command-produced procedure refs;
- dynamic dispatch in executable IR.

## 23. Positive Example

```lisp
(let* ((impl-provider providers.implementation))

  (let-proc
    (run-impl
      ((selected SelectedItem)) -> ImplementationResult
      :captures (design plan impl-provider)
      (call implementation/run
        :selected selected
        :design design
        :plan plan
        :providers impl-provider))

    (call iter-proc
      :execute (proc-ref run-impl)
      :input selected)))
```

Expected properties:

- `run-impl` resolves as a lexical local procedure.
- `(proc-ref run-impl)` has type `ProcRef[SelectedItem -> ImplementationResult]`.
- captures are `design`, `plan`, and `impl-provider`.
- residual signature excludes captures.
- private generated `defproc`-equivalent is created.
- generated procedure is not exportable/importable/author-referenceable.
- generated procedure lowers through ordinary `defproc` lowering.
- effects from `implementation/run` are visible.
- generated nodes are source-mapped.
- executable IR contains no procedure values.

## 24. Negative Examples

### 24.1 Bare Local Procedure Value

Invalid:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)
    ...)

  (call iter-proc
    :execute run-impl
    :input selected))
```

Reason:

Bare local procedure names are not values. Use `(proc-ref run-impl)`.

### 24.2 Field Capture

Invalid in V1:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan providers.implementation)
    ...)
  ...)
```

Reason:

V1 captures must be simple identifiers. Bind field selections before capture.

### 24.3 Nested `let-proc`

Invalid in V1:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (design plan impl-provider)

    (let-proc
      (review-local
        ((attempt Attempt)) -> ReviewResult
        :captures (design)
        ...)
      ...))

  ...)
```

Reason:

Nested `let-proc` is deferred.

### 24.4 Unsupported Effectful Composition

Invalid until ordinary `defproc` lowering supports the same shape:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (ctx providers)
    (let* ((attempt (call provider/run :ctx ctx :selected selected))
           (decision
             (match attempt
               ((OK value)    (call review/run :value value))
               ((ERR reason)  (call fix/run :reason reason)))))
      decision))

  (call iter-proc
    :execute (proc-ref run-impl)
    :input selected))
```

Expected diagnostic:

```text
unsupported effectful composition inside local procedure body
```

with an added note:

```text
inside local procedure: run-impl
```

### 24.5 Generated Name Reference

Invalid:

```lisp
(proc-ref %let-proc/run-impl/abc123)
```

Reason:

Generated local procedures are private compiler-internal definitions and are not author-referenceable.

## 25. Acceptance Tests

### 25.1 V1 Positive Acceptance

V1 must prove:

1. One local `let-proc` with explicit identifier captures compiles.
2. The local procedure is passed via `(proc-ref local-name)`.
3. The binding closure-converts to a private generated `defproc`-equivalent.
4. The generated procedure is not exportable, importable, or author-referenceable.
5. The residual signature excludes captures.
6. Effects from a simple provider or command call are visible.
7. Generated nodes have source-map/explain metadata.
8. Compiled output contains no runtime procedure values.
9. The generated body follows ordinary `defproc` lowering.

### 25.2 V1 Negative Acceptance

V1 must reject:

1. Body using unsupported effectful composition, with the ordinary composition/lowering diagnostic plus local-procedure context.
2. Local procedure stored in records, unions, artifacts, state, ledgers, or workflow outputs.
3. `(proc-ref local-name)` outside scope.
4. Bare local procedure name used as an ordinary value.
5. Nested `let-proc`.
6. Multiple sibling local procedure bindings.
7. Generated procedure name referenced by authored `(proc-ref ...)`.
8. Generated procedure exported or imported.
9. Unknown capture.
10. Duplicate capture.
11. Non-identifier capture.
12. Field-selection capture.
13. Body return type mismatch.
14. Runtime procedure value appearing in executable IR.
15. Missing source-map/explain metadata for generated nodes.

### 25.3 Post-Effectful-Composition Acceptance

After ordinary effectful-composition lowering is fixed or explicitly expanded, add tests where a `let-proc` body:

- binds a provider result in `let*`;
- matches on the resulting union;
- runs review/fix behavior only inside the successful branch;
- uses `with-phase`;
- uses same-file call bindings for locally constructed records;
- crosses reusable workflow boundaries only through supported generated write-root handling;
- passes the same shared validation path as an authored `defproc`.

Future fixture shape:

```lisp
(let-proc
  (run-impl
    ((selected SelectedItem)) -> ImplementationResult
    :captures (ctx providers review-policy)
    (with-phase ctx 'implementation
      (let* ((attempt
               (call provider/run
                 :ctx ctx
                 :selected selected
                 :providers providers.implementation)))
        (match attempt
          ((COMPLETED result)
           (call review/run
             :ctx ctx
             :result result
             :policy review-policy
             :providers providers.review))
          ((BLOCKED blocker)
           (call fix/run
             :ctx ctx
             :blocker blocker
             :providers providers.fix))))))

  (call iter-proc
    :execute (proc-ref run-impl)
    :input selected))
```

This belongs after ordinary effectful composition supports the same shape.

## 26. Implementation Order

Recommended implementation order:

1. Define and enforce the current ordinary `defproc` lowering boundary.
2. Finish/verify ProcRef + `bind-proc` specialization and effect summaries.
3. Add minimal generated-procedure explain metadata.
4. Add V1 `let-proc`:
   - one binding;
   - explicit identifier captures;
   - no nesting;
   - explicit `(proc-ref local-name)`;
   - private generated `defproc`-equivalent;
   - ordinary `defproc` lowering only.
5. Expand ordinary effectful-composition lowering:
   - effectful `let*`;
   - effectful `match`;
   - `with-phase`;
   - same-file record call bindings;
   - reusable workflow generated write roots.
6. Add richer `let-proc` bodies once the equivalent ordinary `defproc` bodies lower correctly.
7. Add field capture aliases and direct-call sugar.
8. Add richer manifest/debug output only if real diagnostics require it.
9. Consider capture inference only after effectful composition and source maps are stable.

This order allows a narrow V1 to ship before all effectful-composition work is complete, but only if unsupported bodies are clearly rejected.

## 27. Deferred Features

Defer:

- capture aliases;
- field-selection captures;
- direct `(call local-proc ...)` sugar;
- nested `let-proc`;
- multiple sibling local procedure bindings;
- recursive local procedures;
- capture inference;
- static procedure-choice tables;
- public specialization manifests;
- runtime first-class procedure values;
- runtime closures.

### 27.1 Field Capture Aliases

Future syntax:

```lisp
:captures ((impl-provider providers.implementation)
           design
           plan)
```

This should be added only after V1 capture diagnostics and generated-name/source-map behavior are stable.

### 27.2 Direct Call Sugar

Future syntax:

```lisp
(call run-impl :selected selected)
```

This should lower to a direct call of the specialized local procedure, but only after the `(proc-ref local-name)` path is stable.

### 27.3 Nested `let-proc`

Future nested local procedures require explicit rules for:

- lexical procedure environment stacking;
- capture visibility across nested scopes;
- generated procedure identity;
- source-map expansion stack;
- name collision behavior;
- specialization cycle detection.

### 27.4 Capture Inference

Future capture inference may allow:

```lisp
:captures infer
```

or omitted captures. That is deferred until source maps, effect summaries, and explain output are strong enough to make inferred captures auditable.

## 28. Open Questions

These are intentionally not V1 blockers unless implementation discovers they affect the minimal feature:

1. Should generated procedure names be stable across whitespace-only source changes?
2. Should explain/debug metadata be emitted only in debug mode, or always as a sidecar for frontend-compiled workflows?
3. Should a local procedure be allowed to shadow an imported procedure name in a later version?
4. Should same-scope value/procedure namespace collisions remain forbidden permanently, or only in V1?
5. Should direct call sugar use ordinary `(call name ...)` syntax, or a distinct form to preserve visual separation from module-level calls?
6. Should field capture aliases support arbitrary expressions later, or only field selections?

## 29. Final Invariant

The controlling rule for this delta is:

```text
let-proc is lexical syntax over generated defproc plus existing ProcRef semantics.
It must not create runtime procedure values.
It must not create a second lowering path.
It must not make invalid effectful compositions valid.
```

Equivalently:

```text
local syntax
-> private generated defproc-equivalent
-> existing ProcRef specialization
-> ordinary defproc lowering
-> ordinary effect analysis
-> ordinary shared validation
-> no runtime procedure values
```
