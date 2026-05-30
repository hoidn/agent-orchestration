# Workflow Lisp Unified Design for Unimplemented Surfaces

Status: draft unified future-design contract  
Scope: only the non-implemented, partial, or explicitly deferred portions of the Workflow Lisp design set  
Baseline: current Workflow Lisp frontend implementation, including compile-time `ProcRef` / `bind-proc`, is treated as fixed input and is not respecified here  
Supersedes-as-future-scope: the unimplemented portions of `workflow_lisp_frontend_specification.md`, `workflow_lisp_let_proc_local_proc_refs.md`, and `workflow_lisp_runtime_closures_boundary.md`  
Does not supersede: current implementation behavior, current tests, shared workflow validation, existing runtime semantics, or the accepted implemented `ProcRef` / `bind-proc` contract

---

## 0. Purpose

This document is the unified design for Workflow Lisp features that are **not yet implemented**, are **only partially implemented**, or are **explicitly deferred**.

It is intentionally **not** a full restatement of the current Workflow Lisp frontend. Existing implemented behavior is treated as the baseline substrate. This document exists to make the remaining design work coherent, ordered, and safe to implement without accidentally changing already-working semantics.

The central rule is:

```text
Future Workflow Lisp features may add authoring power only by lowering into the existing validated workflow model or into a separately accepted future runtime contract.
```

A feature described here is not considered implementation-ready merely because it appears in this document. Each section defines its own acceptance gate.

---

## 1. Fixed Baseline Assumptions

The following behavior is assumed to exist or to be otherwise outside this document's implementation scope.

### 1.1 Current frontend baseline

Workflow Lisp is a frontend compiler. It parses `.orc` source, typechecks it, lowers it to ordinary workflow dictionaries, and delegates execution to the existing workflow loader/runtime path.

This future-design document must not turn Workflow Lisp into a separate runtime, a YAML text generator, or an alternative executor.

### 1.2 Current procedure-composition baseline

The accepted/current procedure-composition baseline is:

- `defproc` exists as a reusable procedure definition surface.
- `ProcRef[...]` is a compile-time procedure-reference type.
- `(proc-ref name)` creates an explicit compile-time reference to a visible `defproc`.
- `bind-proc` partially applies a known procedure reference by statically binding named arguments.
- Specialization happens before runtime artifacts are produced.
- Executable/runtime artifacts must not contain unresolved procedure values.
- Runtime transport of `ProcRef` values and dynamic procedure dispatch remain forbidden.

This document does not redesign those rules. It uses them as the semantic base for `let-proc` and for runtime-closure boundary decisions.

### 1.3 Current validation authority

Shared workflow validation remains authoritative. The frontend may reject earlier and explain better, but it may not bypass or weaken shared validation.

### 1.4 Current runtime authority

The existing runtime owns:

- provider execution semantics;
- command execution semantics;
- state persistence;
- artifact lineage and publication;
- path safety enforcement;
- pointer authority;
- replay/resume behavior;
- observability and runtime event identity.

No future frontend feature may silently assume ownership of those semantics.

---

## 2. In-Scope Future Work

This unified design covers the following non-implemented or incomplete surfaces.

| Area | Status in this document | Implementation intent |
| --- | --- | --- |
| `let-proc` local procedure bindings | proposed near-term feature | implementable as compile-time syntax over generated private `defproc` plus existing `ProcRef` semantics |
| Effectful composition completion | partial/future compiler work | needed for realistic local procedure bodies and higher-level expression composition |
| Full component-contract architecture | future/internal architecture | promote or formalize Core AST, Semantic IR, Executable IR, effect graph, proof graph, state layout, source map, and standard-library lowering contracts |
| Full macro-system safety contract | future/finalization work | constrain any full `defmacro`/hygiene surface so expansion cannot hide effects or break source maps |
| Runtime closures | explicitly deferred | not implementation-ready; current required behavior is rejection |
| Runtime first-class procedures and dynamic dispatch | explicitly deferred | allowed only through a future runtime-closure acceptance gate |

---

## 3. Out-of-Scope Implemented Baseline

The following are not designed here except as constraints on future work:

- basic `.orc` parsing;
- existing expression typechecking;
- lowering to ordinary workflow dictionaries;
- current shared validation integration;
- current `defworkflow` and `defproc` behavior;
- current `ProcRef` and `bind-proc` behavior;
- existing procedure-reference diagnostics;
- current runtime execution.

If this document appears to contradict current code or tests for an implemented feature, treat this document as wrong for that implemented feature and revise it.

---

## 4. Cross-Cutting Future Invariants

Every future feature in this document must preserve these invariants.

### 4.1 No hidden runtime values

Compile-time abstractions must compile away before executable/runtime artifacts unless a future section explicitly accepts a runtime value type.

For now:

```text
ProcRef        -> compile-time only
bind-proc      -> compile-time only
let-proc       -> compile-time only
runtime closure -> rejected unless future acceptance gate is met
```

### 4.2 No hidden effects

No abstraction may hide:

- provider calls;
- command calls;
- workflow calls;
- state writes;
- ledger updates;
- resource transitions;
- artifact materialization or publication;
- snapshot creation;
- pointer materialization;
- generated write roots;
- runtime capabilities.

If a lower-level form would expose an effect, a future high-level form must expose the same effect after elaboration.

### 4.3 No second lowering path

A future ergonomic form may introduce syntax, binding structure, or generated private definitions. It must not introduce a private alternate lowerer that bypasses the ordinary procedure/workflow validation path.

### 4.4 Source maps are mandatory for generated structure

Any feature that generates procedures, statements, IR nodes, specializations, closure families, or runtime invocation nodes must preserve source maps back to the authored form.

Diagnostics must report the most actionable authored location, not only generated names.

### 4.5 Reports are views, not authority

Debug YAML, explain output, dashboard reports, rendered plans, and metadata summaries are projections. They may aid debugging but must not become the semantic source of truth.

### 4.6 Contracts may narrow, not widen

Frontend declarations and generated code may refine contracts into stricter forms. They must not widen runtime authority, artifact permissions, accepted output shapes, or variant availability.

---

# Part I — `let-proc` Local Compile-Time Procedure Bindings

## 5. Feature Summary

`let-proc` is the near-term future feature that lets an author define a local procedure near the point of use while retaining the existing compile-time `ProcRef` model.

It is not a runtime closure. It is not a runtime procedure value. It is not dynamic dispatch.

Conceptual lowering:

```text
let-proc source
  -> lexical local procedure binding
  -> capture validation
  -> private generated defproc-equivalent
  -> ordinary defproc typecheck/effect/lowering path
  -> existing ProcRef / bind-proc specialization
  -> shared validation
  -> no residual procedure value in runtime artifacts
```

The core invariant is:

```text
If the equivalent generated defproc cannot lower, the let-proc form cannot lower.
```

## 6. Motivation

`ProcRef` and `bind-proc` make higher-order procedural composition safe because selected procedures remain statically known. However, some reusable phase skeletons require short local behavior definitions that capture nearby values.

Without `let-proc`, authors must either:

- define a module-level wrapper `defproc` far away from its use;
- write verbose `bind-proc` forms over an existing procedure;
- avoid reusable skeletons and manually thread context.

`let-proc` addresses only that ergonomic gap.

## 7. Non-Goals

`let-proc` must not provide:

- runtime first-class procedures;
- runtime closures;
- arbitrary implicit lexical capture;
- provider-selected procedures;
- model-selected procedures;
- command-produced procedures;
- procedure serialization;
- procedure values stored in records, unions, state, ledgers, artifacts, provider results, command results, workflow outputs, or runtime loop state;
- dynamic dispatch in executable/runtime artifacts;
- a second effect-analysis system;
- a second source-map system;
- a special body lowerer that can lower things ordinary generated `defproc` cannot lower.

## 8. V1 Syntax

V1 supports exactly one local procedure binding per `let-proc`.

```lisp
(let-proc (name ((param ParamType) ...) -> ReturnType
             :captures (capture-name ...)
             body-form)
  body-form ...)
```

Example:

```lisp
(let* ((impl-provider providers.implementation))
  (let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
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

## 9. V1 Restrictions

V1 intentionally rejects the following:

- multiple local procedure bindings in one `let-proc`;
- nested `let-proc`;
- recursive local procedures;
- mutually recursive local procedures;
- direct calls to a local procedure by bare name;
- implicit captures;
- capture expressions;
- capture aliases;
- provider/model/command-produced procedure references;
- local procedure references escaping their lexical body.

### 9.1 Single binding only

Valid:

```lisp
(let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
             :captures (design plan)
             body)
  use-site)
```

Invalid in V1:

```lisp
(let-proc ((run-impl ...)
           (review-impl ...))
  use-site)
```

### 9.2 No nested `let-proc`

Invalid in V1:

```lisp
(let-proc (outer ((x X)) -> Y :captures ()
             (let-proc (inner ((z Z)) -> W :captures () inner-body)
               outer-body))
  use-site)
```

Nested local procedures require additional rules for lexical procedure environments, capture visibility, source-map stacking, generated identity, and collision behavior. They are deferred.

### 9.3 No recursion

Invalid:

```lisp
(let-proc (loop-impl ((x X)) -> Y
             :captures ()
             (call something :next (proc-ref loop-impl) :x x))
  use-site)
```

Any specialization cycle involving a local procedure is rejected.

### 9.4 Local procedure references require explicit `proc-ref`

Valid:

```lisp
(call iter-proc :execute (proc-ref run-impl) :input selected)
```

Invalid:

```lisp
(call iter-proc :execute run-impl :input selected)
```

Bare local procedure names are not values.

### 9.5 Direct local procedure calls are deferred

V1 does not support:

```lisp
(call run-impl :selected selected)
```

The only V1 use site is `(proc-ref local-name)` inside the lexical body.

## 10. Capture Semantics

Captures are explicit ordinary dataflow inputs to the generated private procedure.

They are not closure fields. They are not serialized procedure environments. They do not create runtime procedure values.

V1 captures:

- must be simple identifiers;
- must resolve to in-scope values;
- must be unique;
- must typecheck against generated procedure parameters;
- are bound at compile-time specialization/elaboration;
- must not be treated as runtime closure captures.

Valid:

```lisp
:captures (design plan impl-provider)
```

Invalid in V1:

```lisp
:captures (design providers.implementation)
```

Field selections must be named before capture:

```lisp
(let* ((impl-provider providers.implementation))
  (let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
               :captures (design plan impl-provider)
               body)
    use-site))
```

Capture aliases are deferred:

```lisp
:captures ((impl-provider providers.implementation) design plan)
```

## 11. Name Resolution

`let-proc` introduces one name into the lexical procedure namespace.

Resolution of `(proc-ref name)` inside a `let-proc` body proceeds as follows:

1. Check the active V1 lexical procedure binding.
2. If no lexical binding matches, resolve through the visible module/procedure catalog.
3. Reject references to the lexical procedure outside its lexical scope.
4. Reject same-scope collisions between the local procedure name and ordinary value names.
5. Reject authored references to generated procedure names.

Example:

```lisp
(let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
             :captures (design plan)
             body)
  ;; visible here
  (call iter-proc :execute (proc-ref run-impl) :input selected))
```

Invalid outside the lexical body:

```lisp
(proc-ref run-impl)
```

Same-scope collisions are rejected:

```lisp
(let* ((run-impl some-value))
  (let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
               :captures (design)
               body)
    use-site))
```

## 12. Type Rules

A local procedure has a residual `ProcRef` type derived from its declared parameter list and return type.

Example:

```lisp
(let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
             :captures (design plan impl-provider)
             body)
  use-site)
```

Local type:

```text
run-impl : ProcRef[SelectedItem -> ImplementationResult]
```

The private generated procedure has an expanded internal signature:

```text
%let-proc/run-impl/... : (Design, Plan, ImplementationProviderRole, SelectedItem) -> ImplementationResult
```

The capture parameters are not part of the residual callable signature exposed to consumers.

Validation must check:

- each residual parameter has an explicit type;
- return type is explicit;
- each capture resolves to an in-scope value;
- each capture is a simple identifier in V1;
- duplicate captures are rejected;
- capture names do not collide with residual parameters;
- the body returns the declared return type;
- `(proc-ref local-name)` matches expected `ProcRef[...]` signature at use sites;
- the generated procedure's expanded signature typechecks through the ordinary `defproc` path.

## 13. Lowering Rule

The compiler must closure-convert `let-proc` into a private generated `defproc`-equivalent before ordinary procedure effect analysis and lowering.

No `let-proc`-specific body lowerer is allowed.

Pipeline:

```text
let-proc source
  -> lexical procedure discovery
  -> capture validation
  -> generated private defproc-equivalent
  -> ordinary defproc typechecking
  -> ordinary effect analysis
  -> ordinary defproc lowering
  -> ProcRef specialization
  -> shared validation
  -> executable/runtime artifacts without procedure values
```

The generated procedure is private and compiler-internal. It may appear in diagnostics, source maps, or explain output, but it is not importable, exportable, or author-referenceable by generated name.

## 14. Generated Procedure Identity

Generated names must be deterministic and collision-resistant.

The stable identity should cover:

- source module identity;
- lexical source span;
- local procedure name;
- declared residual signature;
- explicit capture list;
- body source identity or normalized body hash;
- relevant imported procedure identities;
- compiler version or lowering schema version, if needed for replay/debug compatibility.

Recommended generated-name shape:

```text
%let-proc/<module>/<local-name>/<stable-hash>
```

Authored source must not be allowed to reference this generated name:

```lisp
(proc-ref %let-proc/my-module/run-impl/abc123) ; invalid
```

## 15. Effect Rules

`let-proc` introduces no runtime effects by itself.

Effects inside the local procedure body are effects of the generated private procedure and must be visible after specialization.

Rule:

```text
If an ordinary generated defproc body would expose effect E,
the equivalent let-proc body must expose effect E.
```

And:

```text
If ordinary defproc lowering cannot represent effect E yet,
let-proc must reject rather than invent a representation.
```

The caller-visible effect summary for a use site must include the transitive effects of the selected local procedure after capture specialization.

## 16. V1 Body Boundary

V1 `let-proc` bodies may contain only forms currently supported by ordinary `defproc` lowering and shared validation.

Unsupported effectful-composition patterns must be rejected, including but not limited to:

- `match` as an intermediate effectful `let*` binding, when ordinary `defproc` lowering does not support it;
- `with-phase` as a composable intermediate expression, when unsupported;
- effectful `match` arms that do not lower cleanly;
- standard-library forms whose generated write roots cannot cross reusable workflow boundaries;
- same-file call bindings for locally constructed records, when unsupported by ordinary procedure lowering.

The diagnostic must preserve the original body-lowering cause and add local-procedure context.

Invalid example:

```lisp
(let-proc (run-impl ((selected SelectedItem)) -> ImplementationResult
             :captures (ctx providers)
             (let* ((attempt (call provider/run :ctx ctx :selected selected))
                    (decision
                      (match attempt
                        ((OK value) (call review/run :value value))
                        ((ERR reason) (call fix/run :reason reason)))))
               decision))
  (call iter-proc :execute (proc-ref run-impl) :input selected))
```

Expected diagnostic class:

```text
unsupported effectful composition inside local procedure body
```

Not:

```text
ProcRef runtime transport violation
```

unless the actual failure is procedure-reference transport.

## 17. Source Maps for `let-proc`

Generated nodes must be source-mapped to:

- the `let-proc` form;
- the local procedure name;
- residual parameters;
- return type;
- capture list;
- body expression;
- `(proc-ref local-name)` use site;
- generated private `defproc` equivalent;
- generated Core/Semantic/Executable nodes, when those layers exist;
- lowered workflow dictionary nodes under the current implementation.

A diagnostic from the generated procedure must explain both:

1. the original lowering/type/effect cause; and
2. that the failure occurred inside local procedure `<name>`.

## 18. Diagnostics for `let-proc`

The first implementation should stabilize diagnostic codes rather than leaving them implementation-defined.

Required codes:

| Code | Meaning |
| --- | --- |
| `let_proc_syntax_invalid` | malformed `let-proc` form |
| `let_proc_multiple_bindings_unsupported` | V1 multiple local bindings rejected |
| `let_proc_nested_unsupported` | nested `let-proc` rejected |
| `let_proc_recursive_unsupported` | recursion or specialization cycle involving local proc |
| `let_proc_capture_unknown` | capture name not in scope |
| `let_proc_capture_duplicate` | duplicate capture name |
| `let_proc_capture_not_identifier` | V1 capture expression or field selection rejected |
| `let_proc_name_collision` | local procedure name collides with value/procedure binding |
| `let_proc_bare_name_invalid` | bare local procedure name used as value |
| `let_proc_scope_escape` | local procedure referenced outside lexical scope |
| `let_proc_generated_name_private` | authored reference to generated private name |
| `let_proc_body_lowering_unsupported` | body cannot lower through ordinary generated `defproc` path |
| `let_proc_return_type_invalid` | body return type does not match declared return type |
| `let_proc_proc_ref_signature_invalid` | local ProcRef does not match expected signature at use site |

Diagnostics should prefer the most specific ordinary diagnostic and add `let-proc` context. For example, a type mismatch in a capture expression should retain the ordinary type mismatch code if one already exists, with local-procedure context.

## 19. Explain / Debug Metadata for `let-proc`

The first implementation should emit minimal explain/debug metadata for generated local procedures:

```yaml
kind: let-proc-generated-procedure
local_name: run-impl
generated_name: "%let-proc/my-module/run-impl/abc123"
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
lowering_policy: generated-private-defproc
source_map_refs:
  let_proc_form: ...
  generated_defproc: ...
  proc_ref_consumer: ...
```

This metadata is not semantic authority. It must not become an alternate procedure registry or runtime dispatch table.

## 20. Acceptance Gate for `let-proc`

Do not mark `let-proc` implemented until all of the following pass.

Positive tests:

- simple local procedure with one residual parameter;
- explicit captures become generated private procedure parameters;
- `(proc-ref local-name)` passes to a consumer expecting `ProcRef[...]`;
- generated procedure uses ordinary `defproc` validation;
- transitive effects of the generated procedure are visible to the caller;
- generated name is deterministic;
- source maps point from generated diagnostics to authored `let-proc` locations;
- runtime artifacts contain no procedure value or generated closure object.

Negative tests:

- malformed syntax rejected;
- multiple bindings rejected;
- nested `let-proc` rejected;
- recursion rejected;
- unknown capture rejected;
- duplicate capture rejected;
- field-selection capture rejected;
- capture alias rejected;
- bare local procedure name rejected;
- local procedure scope escape rejected;
- generated name reference rejected;
- body-lowering limitation rejected with ordinary cause plus local context;
- provider/model/command-produced procedure reference rejected;
- attempt to store local procedure reference in runtime data rejected.

---

# Part II — Effectful Composition Completion

## 21. Feature Summary

Effectful composition completion is the compiler work needed so Workflow Lisp can compose higher-level effectful expressions without using ad hoc lowerers or hidden runtime behavior.

This work is partially independent of `let-proc`, but realistic `let-proc` bodies will depend on it.

The future compiler must provide a single representation for expression-level effect composition that can lower into validated workflow statements while preserving type, effect, proof, state, and source-map information.

## 22. Current Gap

Some future authoring patterns require effectful expressions to appear in places currently treated like pure expression composition.

Examples of future-needed patterns:

- effectful `let*` intermediate bindings;
- effectful `match` arms;
- `match` results used as intermediate values;
- `with-phase` as a composable expression;
- same-file call bindings for locally constructed records;
- standard-library forms with generated write roots crossing reusable workflow boundaries;
- reusable procedures whose bodies contain provider/command/resource effects and return structured values.

These should not be implemented case-by-case inside `let-proc`, macros, or standard-library forms. They need one shared lowering model.

## 23. Design Goal

The compiler should support effectful expression composition by translating it into an explicit statement/dataflow representation before shared validation.

Conceptual model:

```text
authored expression tree
  -> typed expression/effect tree
  -> effectful block normalization
  -> explicit statement/dataflow nodes
  -> proof/effect/source-map annotations
  -> shared validation
```

The normalized representation must make sequencing, data dependencies, control flow, variant proofs, write roots, and effects explicit.

## 24. Expression Categories

The compiler should classify expressions into at least these categories:

| Category | Meaning | Examples |
| --- | --- | --- |
| pure | no runtime effect; value computed from existing data | literals, field selections, pure record constructors |
| compile-time | erased before runtime | `proc-ref`, `bind-proc`, `let-proc` binding structure |
| effectful-single | produces value by one runtime statement | provider call, command call, workflow/procedure call after lowering |
| effectful-block | sequence/control expression that contains effects | effectful `let*`, effectful `match`, composable phase blocks |
| proof-producing | refines variant availability or type branch | `match`, `requires_variant`, typed variant checks |
| authority-producing | creates or refines artifact/path/state authority | materialization, snapshot, path contract refinement |

Lowering must reject any expression whose category cannot be represented in the target statement model.

## 25. Effectful `let*`

Future `let*` should allow effectful intermediate bindings when the compiler can normalize them into explicit ordered statements.

Example:

```lisp
(let* ((attempt (call provider/run :ctx ctx :input input))
       (review (call review/run :attempt attempt)))
  (make Result :attempt attempt :review review))
```

Normalization:

```text
stmt_1 = call provider/run(ctx, input) -> attempt
stmt_2 = call review/run(attempt) -> review
result = make Result(attempt, review)
```

Rules:

- Binding order is sequential.
- Each effectful binding receives a stable generated statement id.
- Later bindings may depend on earlier outputs.
- Pure bindings may remain expression-level or be lifted for source-map clarity.
- Generated state/write roots must be deterministic.
- Effect summaries include all lifted effectful bindings.

Reject if:

- an effectful binding is used in a context that requires compile-time evaluation;
- generated write roots are ambiguous;
- a binding would hide provider/command/workflow effects;
- a binding creates runtime procedure values;
- source maps cannot identify the authored binding.

## 26. Effectful `match`

Future `match` should support effectful arms when the compiler can represent branch-specific statements and proof contexts.

Example:

```lisp
(match attempt
  ((OK value)
    (call review/run :value value))
  ((ERR reason)
    (call fix/run :reason reason)))
```

Normalization must create:

- a discriminant evaluation;
- branch proof contexts;
- branch-local bindings;
- branch-specific effect summaries;
- a joined result type;
- explicit source maps for each arm;
- shared validation proof that each arm's variant-specific fields are available only inside the corresponding proof context.

Rules:

- All arms must return a compatible joined type.
- Each arm's effects remain visible.
- Variant-specific references require proof from the active arm.
- Generated write roots must be deterministic per arm.
- Branch effects are conservatively summarized at the match site.

Reject if:

- arms have incompatible return types;
- a variant-specific field escapes its proof context;
- branch write-root allocation is ambiguous;
- an arm returns or stores a compile-time-only value;
- effects in one arm are hidden from the joined summary.

## 27. `with-phase` as Composable Expression

Future `with-phase` may be allowed inside expression composition only if it lowers to explicit phase-scoped statements with clear state/write-root identity.

Rules:

- Phase identity must be deterministic.
- Generated state roots must derive from context, not author-managed strings.
- Phase-scoped provider/command/resource effects must remain visible.
- Nested phase composition must preserve source maps.
- Reusable procedures must receive phase roots through explicit generated parameters or validated context, not hidden globals.

Reject if:

- phase state roots depend on unstable expression identity;
- repeated invocation cannot allocate deterministic roots;
- a phase block crosses a reusable workflow boundary without a root policy;
- source maps collapse generated phase nodes into an opaque block.

## 28. Same-File Call Bindings for Locally Constructed Records

Future compiler behavior should allow local record construction followed by same-file procedure calls when type and lowering order are clear.

Example:

```lisp
(let* ((ctx (make ImplementationContext
              :design design
              :plan plan
              :providers providers))
       (result (call implementation/run :ctx ctx :selected selected)))
  result)
```

Rules:

- Locally constructed records must have fully resolved schemas.
- The call signature must accept the constructed type exactly or by valid narrowing.
- Lowering must preserve the data dependency from construction to call.
- No generated YAML/text serialization step may become authority.

Reject if:

- the record type is ambiguous;
- construction relies on runtime-only procedure values;
- a downstream call requires a broader contract than the constructed value proves;
- source maps cannot link field-level construction errors to authored fields.

## 29. Reusable Workflow Boundary Write Roots

Reusable procedures/workflows that contain effectful operations need deterministic write-root allocation.

Future design must answer:

- whether write roots are derived from the caller, callee, call-site id, iteration index, phase id, or explicit generated policy;
- how repeated calls are disambiguated;
- how private generated procedures receive roots;
- how branch-specific roots are allocated;
- how resume reconstructs the same root identities;
- how source maps expose generated roots.

Minimum rule:

```text
If generated write roots cannot be made deterministic and source-mapped, the form is rejected.
```

## 30. Standard-Library Lowering Completion

High-level standard-library forms must lower through the same effectful composition model.

In-scope future forms include:

- `provider-result`;
- `command-result`;
- `produce-one-of`;
- `run-provider-phase`;
- `resume-or-start`;
- `review-revise-loop`;
- `resource-transition`;
- `finalize-selected-item`;
- `backlog-drain`.

Each form needs a lowering contract specifying:

- input type requirements;
- output contract;
- generated statements;
- effects;
- state roots;
- artifact/path authority;
- variant proof behavior;
- source-map points;
- failure diagnostics;
- fixtures.

No standard-library form may hide a provider/command call or encode semantic authority in rendered text.

## 31. Acceptance Gate for Effectful Composition

Do not mark effectful composition complete until tests cover:

Positive cases:

- effectful `let*` with sequential calls;
- pure and effectful bindings mixed in order;
- effectful `match` with compatible arm return types;
- variant proof available only inside the correct arm;
- composable `with-phase` with deterministic state roots;
- same-file constructed record passed to a local call;
- reusable procedure call with deterministic generated write roots;
- source maps for lifted statements;
- effect summaries containing every lifted call.

Negative cases:

- hidden provider call rejected;
- hidden command call rejected;
- incompatible match arm types rejected;
- variant-specific field escape rejected;
- ambiguous generated write root rejected;
- runtime procedure value in effectful block rejected;
- unsupported standard-library lowering rejected with form-specific diagnostic;
- source-map missing for lifted effectful binding rejected in compiler tests.

---

# Part III — Future Component-Contract Architecture

## 32. Feature Summary

The broader frontend design describes a richer internal architecture than the current implementation fully exposes. This future work formalizes internal component contracts so high-level Workflow Lisp features can lower through stable semantic layers rather than ad hoc dictionary generation.

This part is not required to preserve current behavior. It is required before claiming full runtime-integrated support for the broader north-star architecture.

## 33. Target Pipeline

Future architecture may promote the pipeline to explicit internal layers:

```text
.orc source
  -> frontend syntax tree
  -> macro/procedure elaboration
  -> Core Workflow AST
  -> shared validation
  -> Semantic Workflow IR
  -> Executable IR
  -> existing runtime
```

Under current behavior, lowering to ordinary workflow dictionaries is the practical runtime boundary. A future IR pipeline must preserve compatibility with that boundary or replace it only through an explicitly reviewed migration.

## 34. Core Workflow AST Contract

The Core Workflow AST is the syntax-neutral representation shared by YAML-like authoring and Workflow Lisp.

It must define:

- workflow definitions;
- procedure/private-workflow definitions;
- statements;
- calls;
- provider steps;
- command steps;
- materialization;
- snapshots;
- variant outputs;
- variant selection;
- resource transitions;
- loops/retries;
- generated statements;
- source-map references.

Acceptance questions:

- What exact data shape crosses from frontend lowering into shared validation?
- Which fields are semantic authority?
- Which fields are projections/debug-only?
- How are generated nodes identified?
- How does dictionary lowering map into this AST during migration?

## 35. Core Statement Taxonomy Contract

The statement taxonomy must enumerate every executable or validation-relevant statement family.

At minimum:

- pure value binding;
- provider step;
- command step;
- workflow call;
- procedure/private-workflow call;
- branch/match;
- loop/recur;
- materialize artifact;
- pre-snapshot;
- variant output;
- select variant output;
- resource transition;
- backlog drain;
- finalization;
- runtime-closure invocation, if ever accepted.

For each statement family, define:

- inputs;
- outputs;
- effects;
- contracts;
- proof behavior;
- state/write-root behavior;
- source-map fields;
- shared validation owner;
- runtime owner.

## 36. Semantic Workflow IR Contract

Semantic IR is the validated, type-rich layer.

It must record:

- resolved type references;
- input/output contracts;
- artifact/path authority;
- variant proof graph references;
- effect graph references;
- reference catalog entries;
- state layout references;
- source-map references;
- generated procedure identities;
- validation results.

Semantic IR is not an authoring format. It is an internal authority layer for validated semantics.

## 37. Executable IR Contract

Executable IR is the runtime-facing representation.

It must record only executable semantics that the runtime can validate and execute.

Rules:

- No unresolved `ProcRef` values.
- No unresolved `let-proc` bindings.
- No runtime closures unless the runtime-closure acceptance gate has been satisfied.
- No debug-only YAML/text authority.
- All effects, contracts, state roots, and source-map ids required for runtime behavior must be explicit.

If a future feature requires an Executable IR extension, implementation may not start until the extension is specified and reviewed.

## 38. Reference Catalog Contract

The Reference Catalog must unify references for:

- workflow inputs;
- workflow outputs;
- procedure outputs;
- artifact refs;
- snapshot refs;
- provider results;
- command results;
- exit codes;
- variant-specific fields;
- generated procedure outputs;
- closure values, if ever accepted.

It must answer:

- what identity each reference carries;
- what proof is required to use it;
- which references may cross workflow boundaries;
- which references may be persisted;
- which are compile-time-only;
- how diagnostics name them.

## 39. Type Catalog Contract

The Type Catalog maps Workflow Lisp types to runtime contracts.

It must define:

- primitive types;
- records;
- enums;
- tagged unions;
- path/artifact types;
- output bundles;
- variant outputs;
- `WorkflowRef` types;
- `ProcRef` types as compile-time-only;
- `Closure[...]` types only if future runtime closures are accepted.

The catalog must prevent compile-time-only types from entering runtime schemas.

## 40. Effect Graph Contract

The Effect Graph records runtime-visible effects.

It must represent:

- reads;
- writes;
- provider calls;
- command calls;
- workflow calls;
- procedure/private-workflow calls;
- state updates;
- ledger updates;
- resource moves;
- snapshots;
- artifact materialization;
- pointer materialization;
- runtime closure creation/invocation, if ever accepted.

Effect graph rules:

- Macros cannot hide effects.
- `let-proc` cannot hide effects.
- `bind-proc` cannot hide effects of selected procedures.
- Effectful composition must lift effects into explicit nodes.
- Runtime closure invocation, if ever accepted, must expose every possible target effect.

## 41. Proof Graph Contract

The Proof Graph records why a type, variant, output, artifact, or field is valid in a particular context.

It must support:

- `match` branch proofs;
- `requires_variant` proofs;
- `select_variant_output` proofs;
- variant-specific artifact references;
- proof joining after branches;
- proof invalidation outside scope;
- diagnostics for missing proofs.

No generated high-level form may access a variant-specific field without a proof path.

## 42. State Layout Contract

The State Layout contract defines how state paths, artifact roots, bundle paths, temporary paths, phase roots, and pointer paths are derived.

Rules:

- State paths derive from typed contexts, not hand-managed strings.
- Generated roots must be deterministic.
- Repeated calls and loops must disambiguate roots predictably.
- Reusable workflow/procedure boundaries must receive root policy explicitly.
- Resume must reconstruct the same layout.
- Source maps must explain generated roots.

## 43. Source Map Contract

Source maps must cover the full path from authored source to runtime diagnostics.

Required mappings:

- source syntax node;
- macro-expanded node;
- generated `defproc`/`let-proc` node;
- specialized `ProcRef` node;
- Core AST node;
- Semantic IR node;
- Executable IR node;
- lowered workflow dictionary node;
- runtime event/log node;
- diagnostic location.

Generated code must not collapse diagnostics into opaque generated filenames or synthetic names without authored context.

## 44. Legacy Adapter Contract

Legacy adapters are allowed only as explicit quarantine boundaries.

They may wrap old scripts, pointer conventions, or markdown parsing when migration is not yet complete.

Rules:

- Adapter use must be visible in generated workflow semantics.
- Adapter inputs/outputs must have typed contracts.
- Hidden markdown parsing must not become semantic authority.
- Adapter boundaries must be lintable.
- Adapter replacement/promotion criteria must be documented.

## 45. Debug YAML Renderer Contract

A debug YAML renderer may exist only as a projection.

It must not be:

- an authoring authority;
- the semantic lowering target;
- a runtime contract;
- the only source map for generated nodes;
- the only explanation of artifact/path authority.

## 46. Acceptance Gate for Component Architecture

Do not claim full component-contract architecture until:

- each component contract has a reviewed schema;
- ownership between frontend/shared validation/runtime is explicit;
- current dictionary lowering has a migration/compatibility path;
- shared validation consumes or checks the new authoritative layer;
- source maps span all layers;
- explain/debug output is explicitly non-authoritative;
- fixtures show accepted and rejected examples for every statement family.

---

# Part IV — Full Macro-System Safety Contract

## 47. Feature Summary

Current compiler infrastructure may include macro expansion, but the full future macro language must be treated as incomplete until hygiene, effect visibility, source maps, and validation ownership are specified.

This part governs any future `defmacro` or general macro surface.

## 48. Macro Principles

Macros are syntax expansion tools. They are not semantic loopholes.

A macro may:

- introduce repeated syntax;
- generate common workflow patterns;
- abstract over boilerplate;
- improve local readability;
- generate source-mapped high-level forms that later lower normally.

A macro must not:

- hide provider/command/state/artifact effects;
- introduce runtime procedure values;
- bypass typechecking;
- bypass shared validation;
- create dynamic dispatch;
- inspect runtime values at compile time;
- generate untracked state paths;
- generate unsource-mapped statements;
- depend on ambient filesystem state;
- make rendered text into semantic authority.

## 49. Hygiene Requirements

A future full macro system must define:

- generated symbol identity;
- capture rules;
- intentional capture syntax, if allowed;
- import/export behavior;
- module-qualified expansion;
- collision diagnostics;
- generated-name source maps;
- explain output for expansion.

Unintentional capture must be rejected or impossible by construction.

## 50. Macro Effect Visibility

Macro expansion must happen before effect analysis.

Any effectful form produced by a macro must be visible to the same effect graph as authored syntax.

Rule:

```text
A macro-expanded provider call is still a provider call.
A macro-expanded command call is still a command call.
A macro-expanded state write is still a state write.
```

No macro may mark generated effectful forms as pure.

## 51. Macro Source Maps

Macro-generated syntax must map diagnostics to:

- the macro call site;
- the macro definition, when relevant;
- generated subform locations;
- expanded semantic nodes;
- runtime events derived from expansion.

Diagnostics should distinguish:

- invalid macro call syntax;
- invalid macro expansion shape;
- type errors inside expanded forms;
- effects introduced by expansion;
- shared validation failures in expanded nodes.

## 52. Macro Acceptance Gate

Do not mark full macros implemented until tests cover:

Positive cases:

- hygienic generated binding;
- intentional explicit capture, if supported;
- generated effectful form visible in effect summary;
- generated branch/source maps;
- nested macro expansion with stable diagnostics.

Negative cases:

- unintentional capture rejected;
- hidden provider call rejected;
- hidden command call rejected;
- generated runtime procedure value rejected;
- generated unsource-mapped statement rejected;
- macro expansion depending on runtime value rejected;
- macro-generated invalid workflow rejected by shared validation.

---

# Part V — Runtime Closures Boundary

## 53. Feature Summary

Runtime closures are explicitly deferred. They are not implementation-ready.

This document includes them only to prevent near-term compile-time features from drifting into unsafe runtime callable values.

The split is:

```text
ProcRef / bind-proc = compile-time procedure references and specialization
let-proc             = compile-time lexical syntax over generated defproc + ProcRef
runtime closures     = future runtime-owned callable values with explicit runtime semantics
```

Current required behavior:

```text
runtime closure syntax/value -> reject
```

## 54. Closure Conformance Profiles

Runtime closure support has three profiles.

### 54.1 Disabled Profile

This is the current required behavior.

The compiler/runtime must reject authored or runtime closure values with a stable diagnostic such as:

```text
runtime_closure_not_enabled
```

Design fixtures may describe closure syntax or metadata, but they must not execute closures or serialize closure values as ordinary data.

### 54.2 Design-Fixture Profile

Allowed before execution support.

The compiler/runtime may validate rejected examples, registry shapes, diagnostics, and source-map metadata.

It must still reject closure execution.

### 54.3 Minimum Executable Profile

The first profile that may execute runtime closures.

Implementation must not begin until all prerequisites in Section 72 are satisfied.

## 55. Runtime Closure Contract

If added later, runtime closures are typed runtime-owned callable values.

They are not:

- `ProcRef`;
- `bind-proc` results;
- `let-proc` generated procedures;
- ordinary serialized user data;
- Python function objects;
- procedure-name strings;
- provider-produced executable code.

A runtime closure value must carry:

- nominal sealed closure family;
- call signature;
- effect bound;
- capability bound;
- typed capture schema;
- executable-bundle code identity;
- source-map identity;
- replay/resume compatibility metadata.

Conceptual type shape:

```lisp
Closure[
  family RunImplementation,
  (SelectedItem) -> ImplementationResult,
  :effects (uses_provider writes_artifact updates_ledger),
  :capabilities (implementation_provider)
]
```

The closure family, not the structural signature alone, is the unit that makes the callable universe closed.

## 56. Forbidden Runtime Closure Shortcuts

Do not implement any of these as a small closure feature:

- runtime `ProcRef`;
- runtime `let-proc`;
- provider-produced procedure values;
- command-produced procedure values;
- model-produced procedure values;
- procedure-name strings interpreted as callable values;
- opaque serialized callable payloads;
- Python function objects or host-language closures in state;
- dynamic imports or runtime code loading;
- executable IR nodes that dispatch without a closed target universe;
- closures stored in artifacts, ledgers, provider results, command results, or workflow outputs in the first tranche;
- closures that bypass effect checking;
- closures that bypass capability checking;
- closures that bypass source-map checking;
- closures that bypass deterministic write-root checking;
- closures that silently rebind to changed source on resume.

Runtime closures must not be introduced as a workaround for unresolved `ProcRef`, `let-proc`, effectful-composition, or lowering gaps.

## 57. Minimum Executable Surface

The first executable runtime-closure tranche, if ever accepted, must be intentionally narrow.

Allowed:

- closure values created only by authored frontend/workflow forms;
- closure families declared statically in the compiled executable bundle;
- by-value captures of immutable typed data only;
- dynamic invocation only through a checked executable IR node;
- closure values stored only in runtime-managed state, if storage is needed;
- source-mapped diagnostics for creation, capture, invocation, and resume.

Rejected:

- provider/model/command-produced closures;
- provider/model/command-produced closure family ids;
- provider/model/command-produced code ids;
- closure captures;
- provider role captures in V1;
- mutable state captures;
- live context object captures;
- artifact publication of closures;
- workflow-output transport of closures;
- cross-bundle resume without explicit migration metadata.

## 58. Closure Family Registry

A closure type must include a nominal sealed family identity.

A structural signature alone is insufficient:

```lisp
Closure[(SelectedItem) -> ImplementationResult :effects (uses_provider)]
```

Unrelated closures may share the same signature and effect bound while belonging to different semantic families.

A future executable bundle must own a closure-family registry:

```yaml
closure_families:
  RunImplementation:
    accepted_code_ids:
      - closure/run-impl-a/abc123
      - closure/run-impl-b/def456
    signature:
      params:
        - SelectedItem
      return: ImplementationResult
    effect_bound:
      - uses_provider
      - writes_artifact
    capability_bound:
      - implementation_provider
    capture_schema_ids:
      - capture-schema/run-impl-a/456def
      - capture-schema/run-impl-b/789abc
```

A runtime closure is valid only if its code identity appears in the executable bundle's registry for its declared family.

## 59. Closure Value Shape

Conceptual closure value:

```yaml
closure:
  schema: workflow_lisp_runtime_closure/v1
  family: RunImplementation
  code_id: closure/run-impl-a/abc123
  executable_bundle_id: bundle/2026-05-29/example/789abc
  type:
    params:
      - SelectedItem
    return: ImplementationResult
  effects:
    - uses_provider
    - writes_artifact
  capabilities:
    - implementation_provider
  capture_schema_id: capture-schema/run-impl-a/456def
  captures:
    design:
      mode: value
      type: DesignDoc
      value: {}
    plan:
      mode: value
      type: ImplementationPlan
      value: {}
  source_map_ref: source-map/closure/run-impl-a
  effect_summary_ref: effect/run-impl-a
```

Every field affecting invocation, validation, replay, source mapping, or authority must be typed and inspectable.

## 60. Capture Contract

The closure design must distinguish capture modes.

| Mode | Meaning | First tranche? |
| --- | --- | --- |
| by value | immutable serialized snapshot stored with closure | allowed for simple typed data |
| by reference | stable runtime reference re-resolved on resume | deferred |
| by capability | authority carried by closure | deferred/rejected in first tranche |

First tranche may allow only immutable by-value captures:

- typed scalar values;
- typed records and unions with stable schemas;
- workflow input values represented as immutable data;
- pure path or context descriptors only if replay behavior is defined.

First tranche must reject:

- provider role captures;
- closure captures;
- mutable state references;
- live context objects;
- arbitrary runtime handles;
- provider/model/command-produced closure identities.

## 61. Capability Captures

Provider roles and similar authority-bearing references are capability captures, not ordinary data.

V1 runtime closures must reject provider-role captures categorically.

A later capability-capture tranche must prove:

- the closure was created with that capability;
- the invocation site explicitly accepts that capability;
- replay/resume preserves the same authority semantics;
- the closure cannot smuggle authority into a context that did not declare it.

Invocation requires the intersection of:

```text
captured closure capabilities
AND invocation-site accepted capabilities
AND executable-bundle capability policy
```

A closure must not carry provider, command, filesystem, artifact, workflow, or ledger authority into a dynamic invocation site that did not explicitly accept that authority.

## 62. Invocation Contract

Runtime closures require an explicit checked executable IR invocation node.

Conceptual node:

```text
InvokeClosure {
  accepted_families: [RunImplementation],
  closure_value_ref: ...,
  args: ...,
  result_type: ImplementationResult,
  accepted_effect_bound: ...,
  accepted_capability_bound: ...,
  write_root_policy: ...,
  invocation_site_id: ...,
  source_map_ref: ...
}
```

The node is valid only if every possible target accepted at that site satisfies:

- closure-family membership;
- signature compatibility;
- effect bound;
- capability bound;
- deterministic write-root rules;
- deterministic resource-scope rules;
- source-map obligations;
- replay/resume compatibility rules.

A call site may accept a narrower target set than the closure family globally permits.

Executable IR must reject any dynamic closure call whose callable universe is not closed and validated.

## 63. Effect and Write-Root Contract for Closures

Constructing a closure value is pure if all captured values already exist and no state is written.

Persisting a closure into workflow state is a state write.

Invoking a closure has the effects of the selected closure body.

Dynamic invocation must also prove deterministic write-root behavior for every possible target.

The compiler/runtime must know:

- what write roots may be touched;
- whether roots are derived from invocation site, closure creation site, or explicit allocation policy;
- how repeated invocations are disambiguated;
- how reusable workflow boundaries receive generated write roots;
- how resume reconstructs the same root allocation.

Runtime closure invocation must not hide provider calls, command calls, state mutation, resource movement, artifact publication, or ledger updates.

## 64. Provider and Model Selection

Provider or model output may influence ordinary validated dataflow branches that select among statically known closures only if the resulting callable universe remains closed and validated.

Allowed future shape:

```lisp
(match provider-choice
  ((UseA) closure-a)
  ((UseB) closure-b))
```

Only if:

- `closure-a` and `closure-b` are statically declared closure values;
- both belong to accepted families at the invocation site;
- branch selection is ordinary dataflow;
- no provider/model output produces new code identity;
- effect/capability bounds cover both branches.

Rejected:

```lisp
(call-provider choose-procedure) ; returns procedure/closure/code id
```

Provider/model output must not create new callable identities.

## 65. Storage and Transport

First executable runtime-closure tranche may store closures only in runtime-managed state if storage is needed.

First tranche must reject closure values in:

- artifacts;
- ledgers;
- provider results;
- command results;
- workflow outputs;
- exported record fields;
- exported union fields;
- external serialized bundles not owned by runtime state.

A later transport tranche would need a separate design for schema, authority, replay, versioning, and migration.

## 66. Replay and Resume

Runtime closure replay/resume requires stable executable-bundle identity.

A resumed closure must not silently bind to changed source.

The runtime must validate:

- executable bundle id;
- closure family id;
- code id;
- capture schema id;
- source-map id;
- effect/capability policy version;
- runtime migration metadata, if any.

If any identity is incompatible, resume must fail with a stable diagnostic rather than reinterpreting the closure.

## 67. Closure Diagnostics

Required diagnostic codes:

| Code | Meaning |
| --- | --- |
| `runtime_closure_not_enabled` | disabled profile rejects closure syntax/value/execution |
| `closure_family_unknown` | closure family not in executable bundle registry |
| `closure_code_id_invalid` | closure code id not accepted by family |
| `closure_signature_invalid` | closure signature does not match invocation site |
| `closure_effect_bound_invalid` | target effects exceed invocation-site bound |
| `closure_capability_bound_invalid` | target capabilities exceed invocation-site bound |
| `closure_capture_schema_invalid` | captures do not match typed schema |
| `closure_capture_mode_forbidden` | unsupported capture mode |
| `closure_provider_capture_forbidden` | provider role/capability capture rejected in V1 |
| `closure_runtime_transport_forbidden` | closure stored/exported through forbidden channel |
| `closure_write_root_ambiguous` | deterministic write-root policy cannot be proven |
| `closure_resume_bundle_mismatch` | closure cannot resume under current executable bundle |
| `closure_resume_code_mismatch` | closure code identity changed or is not accepted |
| `closure_source_map_missing` | closure creation/invocation lacks required source map |
| `closure_dynamic_code_forbidden` | provider/model/command-produced code/procedure rejected |

## 68. Runtime Closure Source Maps

Source maps must cover:

- closure creation site;
- each capture expression;
- closure family declaration;
- closure code body;
- invocation site;
- accepted family list;
- effect/capability bound declarations;
- generated write-root policy;
- runtime execution events;
- replay/resume validation.

Diagnostics must identify both the closure creation site and invocation site when relevant.

## 69. Runtime Closure Fixtures

Before any executable runtime-closure implementation, the repo must include design-fixture tests proving forbidden shapes are rejected.

Required forbidden fixtures:

- runtime `ProcRef` stored in state;
- `let-proc` compiled to runtime closure;
- provider-produced closure;
- command-produced closure;
- closure stored in artifact;
- closure exported as workflow output;
- closure captures provider role;
- closure captures mutable state;
- closure captures another closure;
- closure invoked without accepted family;
- closure with effect bound exceeding call-site bound;
- closure with capability bound exceeding call-site bound;
- closure with ambiguous write root;
- closure resume under mismatched bundle;
- closure source map missing.

## 70. Runtime Closure Minimum Executable Tests

If the executable profile is ever accepted, tests must prove:

Positive cases:

- closure family declared in executable bundle;
- closure value created by authored frontend form;
- immutable by-value captures validated against schema;
- checked invocation through `InvokeClosure`;
- invocation effects visible in effect graph;
- deterministic write roots for repeated invocation;
- source maps for creation and invocation;
- resume succeeds under identical bundle identity.

Negative cases:

- unknown family rejected;
- invalid code id rejected;
- signature mismatch rejected;
- effect bound violation rejected;
- capability bound violation rejected;
- provider role capture rejected in V1;
- mutable capture rejected;
- workflow-output transport rejected;
- closure hidden in artifact rejected;
- resume bundle mismatch rejected;
- dynamic provider/model/command-generated closure rejected.

## 71. Relationship to `let-proc`

`let-proc` must remain compile-time-only even if runtime closures are later added.

A future runtime-closure feature may introduce separate syntax, or may define explicit closure-producing forms, but it must not reinterpret existing `let-proc` forms as runtime closures.

The following must remain true:

```text
let-proc -> generated private defproc-equivalent -> ProcRef specialization -> erased before runtime
```

Any change that leaves `let-proc` procedure values in runtime artifacts is a breaking semantic change and requires a separate design.

## 72. Runtime Closure Acceptance Gate

Runtime closure implementation may not start until the following are complete or explicitly bounded:

- `ProcRef` and `bind-proc` semantics are stable;
- `let-proc` semantics are stable, if used as closure motivation;
- a concrete executable IR extension point for checked dynamic invocation exists;
- a closure-family registry design is owned by executable bundles;
- source-map format can describe closure creation and invocation;
- effect/capability model can reject authority smuggling;
- deterministic write-root allocation model exists for repeated dynamic invocation;
- replay/resume compatibility policy is accepted;
- forbidden-shape fixtures pass in disabled/design-fixture profile;
- provider/model/command-produced callable identities are rejected;
- no fallback exists to dynamic Python objects, procedure-name strings, serialized code, or unchecked executable dispatch.

---

# Part VI — Implementation Ordering

## 73. Recommended Sequence

The remaining design work should be implemented in this order.

### Stage 1: Document-status cleanup

- Mark implemented baseline docs as historical or current as appropriate.
- Mark this document as covering only future/unimplemented surfaces.
- Ensure `ProcRef` / `bind-proc` docs say accepted/current rather than future-only.
- Ensure runtime closures remain explicitly deferred.

### Stage 2: `let-proc` V1, narrow body boundary

Implement only simple `let-proc` forms whose generated private `defproc` body already lowers through the ordinary path.

Reject effectful-composition gaps rather than solving them inside `let-proc`.

### Stage 3: Effectful composition normalization

Add shared normalization for effectful `let*`, effectful `match`, composable `with-phase`, same-file call bindings, and generated write-root policies.

This stage benefits `let-proc`, standard-library forms, and future macro expansion.

### Stage 4: Standard-library lowering completion

Move high-level forms onto the shared effectful-composition and component-contract model.

Each form must have fixtures, source maps, effects, and write-root policy.

### Stage 5: Component-contract promotion

Formalize Core AST, Semantic IR, Executable IR, Effect Graph, Proof Graph, Reference Catalog, Type Catalog, State Layout, Source Map, Legacy Adapter, and Debug YAML Renderer contracts.

Do this before claiming full north-star architecture implementation.

### Stage 6: Macro-system finalization

Finalize full macro hygiene and effect/source-map policy.

Do not let macros become the escape hatch for unresolved standard-library or effectful-composition problems.

### Stage 7: Runtime closure disabled/design-fixture profile

Add rejection fixtures and registry-shape experiments while closures remain non-executable.

### Stage 8: Runtime closure executable profile, only if accepted

Begin only after the runtime closure acceptance gate is satisfied.

## 74. Dependency Graph

```text
current frontend baseline
  |
  +-- current ProcRef / bind-proc baseline
        |
        +-- let-proc V1
        |     |
        |     +-- richer let-proc bodies after effectful composition
        |
        +-- runtime-closure guardrails

current lowering / validation baseline
  |
  +-- effectful composition normalization
        |
        +-- standard-library lowering completion
        +-- macro-system safety finalization
        +-- reusable boundary write-root policy

component-contract architecture
  |
  +-- future executable IR extension points
        |
        +-- runtime closure executable profile
```

---

# Part VII — Unified Test Matrix

## 75. Test Categories

Every future feature must add tests in these categories:

- parser/syntax tests;
- typechecking tests;
- lowering tests;
- shared validation tests;
- source-map tests;
- effect-summary tests;
- generated-name determinism tests;
- runtime-artifact absence/presence tests;
- negative forbidden-shape tests;
- explain/debug projection tests.

## 76. Runtime Artifact Invariants

For `let-proc` and compile-time future features:

- no `ProcRef` values in runtime artifacts;
- no `let-proc` binding objects in runtime artifacts;
- no generated runtime closure objects;
- no procedure-name strings used for dispatch;
- no hidden procedure registries in runtime plans.

For runtime closures, if ever accepted:

- closure values appear only in the accepted typed runtime shape;
- invocation uses only checked executable IR nodes;
- all closure identities appear in the executable bundle registry.

## 77. Source-Map Fixtures

Fixtures must cover:

- authored source error;
- generated local procedure error;
- generated specialization error;
- lifted effectful binding error;
- branch proof error;
- standard-library generated statement error;
- macro-generated error;
- runtime closure creation error;
- runtime closure invocation error;
- replay/resume closure mismatch error.

## 78. Effect Fixtures

Fixtures must prove that generated abstractions expose effects:

- `let-proc` body provider effect visible at call site;
- `bind-proc` selected procedure effect visible after specialization;
- effectful `let*` sequence exposes all effects;
- effectful `match` exposes branch effects conservatively;
- macro-generated provider call exposes provider effect;
- runtime closure invocation exposes every possible target effect.

## 79. Forbidden Transport Fixtures

Compile-time-only values must be rejected in:

- records;
- unions;
- state;
- ledgers;
- artifacts;
- provider results;
- command results;
- workflow outputs;
- runtime loop state;
- external serialized bundles.

This applies to:

- `ProcRef`;
- `bind-proc` result;
- local `let-proc` reference;
- generated procedure identity;
- runtime closure value until and unless a specific transport channel is accepted.

---

# Part VIII — Open Decisions

## 80. `let-proc` Direct Calls

Should V2 allow direct calls to local procedures?

Possible future syntax:

```lisp
(call run-impl :selected selected)
```

Risks:

- blurs procedure/value namespace;
- may imply runtime dispatch;
- complicates diagnostics for ordinary call vs local procedure call.

Recommendation: keep deferred until V1 source maps and local procedure identity are stable.

## 81. Capture Aliases

Should V2 allow capture aliases?

Possible syntax:

```lisp
:captures ((impl-provider providers.implementation) design plan)
```

Risks:

- generated parameter naming;
- source-map complexity;
- capture expression evaluation order;
- accidental effectful capture expressions.

Recommendation: allow only pure capture expressions, if any, and lower aliases into explicit pre-capture bindings.

## 82. Nested Local Procedures

Should nested `let-proc` be allowed?

Risks:

- lexical procedure environments;
- capture-of-capture behavior;
- recursive cycles;
- generated-name stability;
- source-map stack depth.

Recommendation: require explicit V2 design and tests before enabling.

## 83. Runtime Closure Syntax

If runtime closures are ever accepted, should they reuse `let-proc` syntax?

Recommendation: no. Use distinct syntax so compile-time local procedures and runtime callable values remain visually and semantically separate.

## 84. Executable IR Migration

Should the implementation introduce explicit Core AST / Semantic IR / Executable IR layers, or continue lowering directly to workflow dictionaries with enriched validation metadata?

Recommendation: decide based on implementation pressure from effectful composition and runtime closure work. Do not introduce IR layers as nominal wrappers without new validation authority.

## 85. Macro Expansion Power

Should macros be allowed to generate arbitrary effectful workflow forms?

Recommendation: yes only after effectful composition and source-map contracts are stable. Before then, macros should be constrained to forms the compiler can already validate and source-map.

---

# Part IX — Document Cleanup Plan

## 86. Existing Design Docs

Recommended status updates:

| Existing doc | Recommended status |
| --- | --- |
| `workflow_lisp_frontend_mvp_specification.md` | historical MVP / implementation baseline context |
| `workflow_lisp_frontend_specification.md` | umbrella north-star / partially implemented / future sections superseded by this document |
| `workflow_lisp_proc_refs_partial_application.md` | accepted/current baseline; not part of future-only scope except as dependency |
| `workflow_lisp_let_proc_local_proc_refs.md` | superseded by Part I of this document |
| `workflow_lisp_runtime_closures_boundary.md` | superseded by Part V of this document |
| component-contract docs | future architecture appendices until implemented/reviewed |

## 87. Header Template for Future Docs

Every future design doc should start with:

```text
Status:
Implementation status:
Baseline assumptions:
In scope:
Out of scope:
Depends on:
Blocks:
Acceptance gate:
Supersedes:
Superseded by:
```

## 88. Status Vocabulary

Use these status labels consistently:

| Label | Meaning |
| --- | --- |
| `implemented/current` | represented by current code and tests |
| `accepted/current baseline` | design accepted and treated as baseline for future work |
| `partial` | some implementation exists, but full design contract is not complete |
| `proposed` | implementable design, not yet implemented |
| `deferred` | intentionally not implementation-ready |
| `design fixture only` | rejected/metadata fixtures allowed, no execution |
| `historical` | retained for context, not current authority |
| `superseded` | replaced by a newer contract |

---

# Part X — Final Unified Rule

The remaining Workflow Lisp design work should be governed by one sentence:

```text
Implement only future features that either compile away into the existing validated workflow model, or pass a separate explicit runtime acceptance gate before introducing new runtime values.
```

Applied to the current future set:

```text
let-proc             -> compile away through generated private defproc + ProcRef
Effectful composition -> normalize into explicit validated workflow statements
Macros               -> expand into source-mapped validated forms
Component contracts  -> formalize internal semantic authority before broader runtime claims
Runtime closures     -> reject until the runtime acceptance gate is satisfied
```
