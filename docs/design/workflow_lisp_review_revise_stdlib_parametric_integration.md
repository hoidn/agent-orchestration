# Workflow Lisp Review/Revise Stdlib Integration With Parametric Constraints

Status: draft design
Kind: incremental architecture / stdlib migration spec / consuming design for parametric Workflow Lisp
Created: 2026-06-03
Scope: `review-revise-loop` first; later reusable review/revise/fix orchestration forms with the same shape.

Related docs:

- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_structural_parametric_constraints.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/lisp_frontend_review_fix_loops.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/2026-06-01-review-revise-loop-stdlib-feasibility-proof.md`
- `specs/dsl.md`

## 1. Purpose

This document specifies the incremental architecture for moving
`review-revise-loop` from a compiler-special Workflow Lisp form into an
ordinary `.orc` standard-library component.

This document does not define a third, independent generic type-system design.
It is a consuming design for two existing type-system directions:

- `workflow_lisp_compile_time_parametric_specialization.md`, which owns generic
  `.orc` definition specialization into concrete monomorphic helpers before
  ordinary Core AST lowering. That design explicitly identifies
  `review-revise-loop` as the immediate pressure case, because the loop should
  become ordinary `.orc` code but currently needs specialization over
  caller-specific record and union shapes.
- `workflow_lisp_structural_parametric_constraints.md`, which owns structural
  record, union, variant, and `ProcRef` constraints. That design states that
  the missing type feature is the ability for a generic definition to require
  caller-provided records and unions to have particular fields, variants, and
  proof behavior.

This document owns only the review/revise-loop migration contract: the stdlib
surface, routing semantics, evidence-authority rules, loop exhaustion
projection, source-map obligations, fixture matrix, and removal path for the
compiler-special review-loop implementation.

## 2. Problem

`review-revise-loop` currently behaves like a high-level reusable workflow
abstraction, but the promoted path still depends on compiler logic that knows
the form by name. That creates three design problems.

First, the compiler contains review-loop-specific semantic knowledge that should
belong either in `.orc` stdlib code or in generic type-system machinery. The
structural-constraints design calls out the current issue directly:
`review-revise-loop` accepts a caller-owned result union, and the compiler
currently needs to know that the union contains terminal variants such as
`APPROVED`, `BLOCKED`, and `EXHAUSTED` with the fields needed by loop
projection. Today that validation is encoded directly in Python for one stdlib
form.

Second, the stdlib lowering contract says the default implementation path for
high-level library forms is ordinary `.orc` code through shared effectful
composition, and that bespoke compiler lowering should be reserved only for
forms explicitly accepted as primitives. It also states that, for the
key-workflow migration tranche, `review-revise-loop` is not accepted as a
compiler-special primitive; its parity path is ordinary stdlib/generic
composition emitting existing executable surfaces such as `repeat_until`,
structured provider results, `match`, projection/materialization, source maps,
and resume-safe loop state.

Third, review/revise/fix loops are semantically about workflow control, not
report text. The review/fix-loop design states that review decisions route
workflow control: `APPROVE` exits the loop, `REVISE` invokes the corresponding
revision/fix step, and loop exhaustion is terminal non-completion.

The desired architecture is therefore:

```text
review-revise-loop
  authored/imported as std/phase.orc code
  checked through generic structural constraints
  specialized into a monomorphic helper/private workflow
  lowered through ordinary Core AST and DSL surfaces
  validated by shared validation
  executed by the runtime as ordinary workflow control
```

Not:

```text
review-revise-loop
  recognized by Python as a magic form
  typechecked by review-loop-specific code
  lowered by a hand-built ReviewReviseLoopExpr branch
  treated by runtime or shared validation as a special concept
```

## 3. Decision

`review-revise-loop` will become an imported stdlib abstraction, preferably in
`std/phase.orc`, implemented over ordinary Workflow Lisp constructs plus the
generic mechanisms defined by the parametric-specialization and
structural-constraints designs.

The compiler may provide generic infrastructure:

- parse/import stdlib `.orc`;
- syntax expansion for macros, if any;
- explicit `:forall` type-parameter resolution;
- structural record/union/variant constraint checking;
- compile-time `ProcRef` resolution;
- monomorphic helper/private-workflow instantiation;
- ordinary typechecking of the instantiated helper;
- ordinary lowering of `loop/recur`, `match`, `provider-result`,
  `command-result`, records, unions, and projection;
- generated path allocation;
- source maps;
- shared validation handoff.

The compiler must not provide review-loop-specific behavior in the promoted
path:

- no `ReviewReviseLoopExpr` lowering path;
- no lowerer branch keyed to the literal name `review-revise-loop`;
- no typechecker branch that knows `APPROVED`/`BLOCKED`/`EXHAUSTED` only for
  this one form;
- no Python-built review/fix control tree;
- no hidden provider or command effects introduced by a macro template;
- no runtime `ProcRef`, provider ref, prompt ref, closure, type object, or
  runtime dispatch table.

A temporary bridge is allowed only if it remains generic in the right sense:

Allowed bridge:

- thin macro or helper generator;
- emits grammar-accepted `.orc` or monomorphic helper definitions;
- uses generic structural constraints;
- runs through ordinary typecheck/lowering/shared validation;
- preserves source maps and effect visibility.

Disallowed bridge:

- macro or compiler branch owns review/revise routing semantics;
- generated code bypasses generic constraints;
- generated provider/command effects are hidden;
- generated terminal result construction is validated only by form-specific
  Python.

The long-term route is preferred because compile-time parametric specialization
keeps reusable behavior in effectful `.orc` definitions rather than macro
templates; macros may remain ergonomic surface syntax, but they should expand
to calls of generic definitions rather than own semantic control flow.

## 4. Relationship To Existing Type-System Designs

### 4.1 Compile-Time Parametric Specialization Owns Monomorphic Helper Generation

This document depends on the following specialization pipeline:

```text
generic .orc definition
  -> infer concrete call-site types
  -> check explicit shape/trait constraints
  -> instantiate monomorphic helper/private workflow
  -> typecheck the instantiated AST
  -> lower ordinary Core AST
```

That pipeline is already stated in
`workflow_lisp_compile_time_parametric_specialization.md`. It also states that
executable workflow state must not contain unresolved type parameters,
procedure type values, provider refs, prompt refs, or runtime-dispatched method
choices.

This document does not redefine:

- `:forall` syntax;
- type-argument resolution;
- specialization identity;
- monomorphic helper naming;
- runtime erasure of type parameters;
- compile-time-only `ProcRef` treatment;
- source-map obligations for generated specializations.

It only says `review-revise-loop` is a first major consuming use case of that
mechanism.

### 4.2 Structural Parametric Constraints Own Shape And Proof Requirements

This document depends on structural constraints for caller-specific records and
unions. The first useful constraint set is deliberately small:

```text
T has-field name Type
T has-union-variant VARIANT
T has-union-variant VARIANT (field Type ...)
T has-shared-union-field name Type
T is-record
T is-union
P ProcRef[(A B) -> R]
```

Those initial forms are already proposed by
`workflow_lisp_structural_parametric_constraints.md`, which also says
constraint checking happens before specialization is accepted, every type
parameter resolves to one concrete type at each call site, `ProcRef`
constraints resolve to compile-time procedure references only, and unresolved
type parameters must not appear in lowered Core AST, Semantic IR, Executable
IR, runtime state, artifact contracts, output bundles, or provider/command
payloads.

This document does not redefine:

- `has-field` semantics;
- `has-union-variant` semantics;
- `has-shared-union-field` semantics;
- `is-record` / `is-union` semantics;
- `ProcRef` signature constraints;
- variant-proof preservation;
- constraint diagnostics;
- trait aliases.

It only says which constraints `review-revise-loop` needs.

### 4.3 This Document Owns The Review/Revise Migration Contract

This document specifies:

- the `std/phase.orc` `review-revise-loop` API shape;
- review/fix routing semantics;
- `APPROVE` / `REVISE` / `BLOCKED` / `EXHAUSTED` terminal behavior;
- `loop/recur` exhaustion projection requirements;
- evidence identity and carried-artifact authority;
- effect visibility through review/fix `ProcRef`s;
- source-map and state-layout obligations for generated loop state;
- diagnostics specific to misuse of review/revise stdlib;
- fixtures required before removing `ReviewReviseLoopExpr`;
- promotion evidence required before YAML primary deprecation.

## 5. Goals

- Make `review-revise-loop` ordinary imported stdlib code rather than a
  compiler primitive.
- Preserve review decisions as workflow-control authority.
- Preserve typed state and validated artifacts as semantic authority.
- Allow caller-specific records and result unions without compiler branches
  keyed to review-loop names.
- Keep `ProcRef`, provider refs, prompt refs, type parameters, and
  helper-generation details compile-time-only.
- Preserve provider and command effects after specialization.
- Preserve source-map provenance for authored code, imported stdlib code,
  generated helpers, generated paths, and selected `ProcRef` bodies.
- Make loop exhaustion an explicit typed terminal result, not failed hidden
  control flow.
- Keep runtime execution Lisp-agnostic: the runtime executes generated DSL
  surfaces, not a special review-loop primitive.
- Provide an incremental path that can coexist with the current bridge until
  parity fixtures pass.

These goals align with the migration architecture's stated goals to keep
structured state and validated artifacts as authority, support typed terminal
outcomes for real review/revise/fix loops, make review/revise/fix loops
ordinary `.orc` code rather than compiler-special forms, and require compile,
validation, dry-run, smoke/targeted integration, and parity evidence before
YAML deprecation.

## 6. Non-Goals

This design does not add:

- runtime closures;
- runtime procedure values;
- runtime type values;
- runtime multiple dispatch;
- provider refs in runtime state;
- prompt refs in runtime state;
- implicit structural duck typing at workflow runtime;
- report parsing as semantic state;
- pointer-file choreography as semantic state;
- hidden command adapters for review/revise routing.

It also does not require the current migration-parity slice to stop using the
existing review-loop bridge immediately. The structural-constraints doc
explicitly allows the current bridge to remain while migration parity work
continues, then reimplement `review-revise-loop` over the generic mechanism and
remove review-loop-specific compiler branches after parity fixtures pass.

## 7. Architecture Invariants

A promoted stdlib review loop must satisfy these invariants:

- Structured bundles and typed artifacts are authority.
- Reports, debug YAML, stdout, pointer files, and source maps are views unless a
  specific contract says otherwise.
- Review decisions route workflow control.
- `REVISE` is not completion.
- `EXHAUSTED` is explicit typed non-completion.
- Evidence identities are carried by state or inputs.
- Review-provider output cannot redirect carried evidence identity.
- All generated effects are visible.
- All generated statements and paths are source-mapped.
- All generated paths are deterministic and collision-safe.
- No runtime `ProcRef`, provider ref, prompt ref, type parameter, closure, or
  type object exists.
- The runtime executes generic DSL surfaces, not Lisp-specific review-loop
  behavior.
- Shared validation remains authoritative after lowering.

The migration architecture already names several of these invariants:
structured bundles and typed artifacts are authority, reports/debug
YAML/stdout/pointer files/source maps are views unless contracted otherwise,
`REVISE` is not completion, exhausted review loops are explicit
non-completion, and source maps must preserve authored-to-generated provenance.

## 8. Target Compilation Architecture

The target architecture is:

```text
caller .orc
  imports std/phase.orc
  defines caller-owned review and fix procedures
  calls review-revise-loop with proc-ref hooks
        |
        v
frontend import resolver
  loads stdlib .orc source
  records imported-definition provenance
        |
        v
macro expansion, if any
  expands only to grammar-accepted .orc
  does not own hidden provider/command effects
  does not own runtime semantics
        |
        v
generic type checker
  resolves concrete CompletedT / InputsT / ResultT
  checks structural record/union/variant constraints
  checks ProcRef signatures and effects
  preserves variant proof through match
        |
        v
generic specialization
  emits monomorphic helper/private workflow
  records specialization identity
  records source-map frames
        |
        v
ordinary typecheck and lowering
  loop/recur
  match
  provider-result / command-result
  record/union construction
  materialization/projection
        |
        v
YAML-shaped Core DSL workflow
        |
        v
shared validation / Semantic IR / Executable IR
        |
        v
runtime
  executes repeat_until, provider steps, command steps, match, output contracts
```

The compiler sees the generated helper as ordinary monomorphic Workflow Lisp.
The runtime sees ordinary DSL.

## 9. Stdlib Surface

### 9.1 First Tranche: Concrete Review Decision And Findings, Generic Completed/Input/Result

The smallest useful first implementation should avoid over-generalizing every
part of the loop. It can keep review decision and findings as stdlib-owned
concrete types while allowing caller-owned completed/input records and
caller-owned terminal result unions.

Illustrative stdlib types:

```lisp
(defrecord ReviewFindings
  ((summary String)
   (items ReviewFindingList)))

(defunion ReviewDecision
  (APPROVE
    (review_report ReviewReportPath)
    (findings ReviewFindings))

  (REVISE
    (review_report ReviewReportPath)
    (findings ReviewFindings))

  (BLOCKED
    (review_report ReviewReportPath)
    (findings ReviewFindings)
    (blocker_class String)
    (reason String)))
```

Illustrative generic stdlib definition:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)

     (ResultT has-union-variant APPROVED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings ReviewFindings))

     (ResultT has-union-variant BLOCKED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings ReviewFindings)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant EXHAUSTED
       (completed CompletedT)
       (last_review_report ReviewReportPath)
       (findings ReviewFindings)
       (reason String))

     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
     (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (max_iterations Int))

  -> ResultT

  ...)
```

This shape directly follows the structural-constraints design's review-loop
application model: `std/phase.orc` declares a generic review-loop definition or
thin macro that calls one; the result-union requirement is expressed as
structural constraints; review and fix hooks are compile-time `ProcRef`
parameters; the compiler specializes for concrete caller types; and lowering
sees ordinary generated helpers, `loop/recur`, `provider-result`,
`command-result`, `match`, records, unions, and projections.

### 9.2 Extended Model: Generic Decision And Findings

A later version may parameterize the decision and findings types too:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT DecisionT FindingsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)

     (DecisionT has-union-variant APPROVE
       (review_report ReviewReportPath)
       (findings FindingsT))

     (DecisionT has-union-variant REVISE
       (review_report ReviewReportPath)
       (findings FindingsT))

     (DecisionT has-union-variant BLOCKED
       (review_report ReviewReportPath)
       (findings FindingsT)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant APPROVED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings FindingsT))

     (ResultT has-union-variant BLOCKED
       (completed CompletedT)
       (review_report ReviewReportPath)
       (findings FindingsT)
       (blocker_class String)
       (reason String))

     (ResultT has-union-variant EXHAUSTED
       (completed CompletedT)
       (last_review_report ReviewReportPath)
       (findings FindingsT)
       (reason String))

     (review ProcRef[(CompletedT InputsT) -> DecisionT])
     (fix ProcRef[(CompletedT InputsT FindingsT) -> CompletedT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> DecisionT])
   (fix ProcRef[(CompletedT InputsT FindingsT) -> CompletedT])
   (max_iterations Int))

  -> ResultT

  ...)
```

This should not be the first required milestone unless a concrete caller needs
custom findings. The first tranche should implement only the polymorphism
needed to retire review-loop-specific compiler validation.

### 9.3 Bridge Model: Terminal-Constructor ProcRefs

If direct generic construction of caller-owned result-union variants is not
ready, the stdlib loop may accept terminal-constructor `ProcRef`s as a bridge:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT ResultT)
  :where
    ((CompletedT is-record)
     (InputsT is-record)
     (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
     (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
     (on-approved ProcRef[(CompletedT ReviewReportPath ReviewFindings) -> ResultT])
     (on-blocked ProcRef[(CompletedT ReviewReportPath ReviewFindings String String) -> ResultT])
     (on-exhausted ProcRef[(CompletedT ReviewReportPath ReviewFindings String) -> ResultT]))

  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (on-approved ProcRef[(CompletedT ReviewReportPath ReviewFindings) -> ResultT])
   (on-blocked ProcRef[(CompletedT ReviewReportPath ReviewFindings String String) -> ResultT])
   (on-exhausted ProcRef[(CompletedT ReviewReportPath ReviewFindings String) -> ResultT])
   (max_iterations Int))

  -> ResultT

  ...)
```

This bridge is acceptable only if:

- constructor hooks are compile-time `ProcRef`s;
- constructor hook effects are visible;
- constructor hook bodies are ordinary `.orc`;
- constructor hook return type is concrete after specialization;
- constructor hooks do not introduce runtime procedure values;
- the bridge is documented as temporary or as an ergonomic wrapper, not as a
  substitute for structural result constraints.

Preferred long-term model:

```text
review-revise-loop directly constructs ResultT variants justified by structural constraints.
```

Allowed bridge model:

```text
review-revise-loop delegates terminal construction to compile-time ProcRefs
while direct generic union construction matures.
```

Disallowed model:

```text
Python compiler branch constructs ResultT variants because it knows review-revise-loop by name.
```

## 10. Review/Revise Semantic Contract

The stdlib loop has four terminal routes.

### 10.1 APPROVE

```text
review(completed, inputs) returns APPROVE
  -> loop exits
  -> terminal result is ResultT.APPROVED
  -> completed state is the current completed value
  -> review_report and findings come from the approving review decision
```

### 10.2 REVISE

```text
review(completed, inputs) returns REVISE
  -> fix(completed, inputs, findings) runs
  -> completed becomes fix result
  -> loop continues
  -> REVISE is not completion
```

The review/fix-loop design emphasizes this point: a provider writing `REVISE`
must drive deterministic workflow control to the revise/fix step, rather than
allowing the work-item layer to mark the item completed.

### 10.3 BLOCKED

```text
review(completed, inputs) returns BLOCKED
  -> loop exits
  -> terminal result is ResultT.BLOCKED
  -> completed state is the current completed value
  -> review_report, findings, blocker_class, and reason come from the blocking review decision
```

### 10.4 EXHAUSTED

```text
loop reaches max_iterations without APPROVE or BLOCKED
  -> loop exits through explicit exhaustion projection
  -> terminal result is ResultT.EXHAUSTED
  -> completed state is the latest completed value
  -> last_review_report and findings come from the last completed review frame
  -> reason is a deterministic workflow-owned value such as "max_iterations_exhausted"
```

Exhaustion is not a hidden control-flow failure. It is a typed non-completion
result.

## 11. Loop State Model

The generated monomorphic helper should lower to an explicit loop-frame state.
A conceptual frame is:

```lisp
(defrecord ReviewLoopFrame
  ((completed CompletedT)
   (decision_status ReviewDecisionStatus)
   (latest_review_report ReviewReportPath)
   (latest_findings ReviewFindings)
   (latest_blocker_class OptionalString)
   (latest_reason OptionalString)
   (iteration Int)))
```

After specialization, `CompletedT` is concrete. No type parameter appears in
lowered Core AST, Semantic IR, executable state, output contracts, provider
payloads, or command payloads.

The frame is semantic state. It must not carry:

- `ProcRef` values;
- provider refs;
- prompt refs;
- type parameters;
- runtime closure environments;
- unvalidated report text as structured findings;
- evidence identities invented by review output.

## 12. Evidence Authority

Review-provider output is decision evidence, not carried-artifact identity
authority.

For implementation review, consumed evidence such as `checks_report` must be
carried by inputs or loop state. The review provider may consume, inspect, and
judge that evidence, but it must not return a replacement `checks_report` path
that becomes authoritative.

Required rule:

```text
final_result.checks_report, or any equivalent carried evidence field,
must be copied from inputs/state, not from ReviewDecision.
```

The stdlib lowering document is explicit: consumed evidence artifacts such as
`checks_report` are loop inputs/consumes, not review-provider output fields;
route and final projection steps carry evidence refs from loop inputs/state;
and negative validation should catch any lowering where provider output can
replace consumed evidence identity.

Required negative case:

```text
A review ProcRef returns a decision bundle containing a checks_report field.
The generic loop attempts to use that returned field as terminal evidence.
Compilation or shared validation fails with evidence_authority_violation.
```

## 13. Effects Contract

A specialized review loop's effect summary is the union of visible effects from
the loop and all selected `ProcRef` hooks:

```text
effects(review-revise-loop[...])
  =
    effects(review)
  ∪ effects(fix)
  ∪ effects(on-approved), if bridge model is used
  ∪ effects(on-blocked), if bridge model is used
  ∪ effects(on-exhausted), if bridge model is used
  ∪ effects(loop/recur)
  ∪ effects(match)
  ∪ effects(materialization/projection)
```

A macro or specialization that hides provider or command effects is invalid.

Compile-time specialization with procedure references must satisfy the existing
boundary:

```text
before runtime:
  all type parameters are concrete
  review and fix point to concrete named procedures
  provider and prompt externs used by those procedures are resolved inside those procedures
  no runtime state carries ProcRef, provider ref, prompt ref, or type parameter
```

The compile-time specialization design already states those `ProcRef`
interaction rules.

## 14. Lowering Contract

A specialized stdlib review loop should lower to existing DSL surfaces. The
representative generated shape is:

```text
generated/private review-loop helper
  repeat_until ReviewLoop:
    outputs:
      completed
      decision_status
      latest_review_report
      latest_findings
      latest_blocker_class
      latest_reason

    condition:
      self.outputs.decision_status in ["APPROVE", "BLOCKED"]

    max_iterations:
      max_iterations

    on_exhausted.outputs:
      decision_status = "EXHAUSTED"
      latest_reason = "max_iterations_exhausted"

    steps:
      ReviewOnce:
        call specialized review ProcRef
        produces ReviewDecision

      RouteReviewDecision:
        match ReviewDecision.discriminant
          APPROVE:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "APPROVE"

          REVISE:
            call specialized fix ProcRef
            materialize completed = fix result
            materialize latest_review_report
            materialize latest_findings
            set decision_status = "REVISE"

          BLOCKED:
            materialize completed unchanged
            materialize latest_review_report
            materialize latest_findings
            materialize latest_blocker_class
            materialize latest_reason
            set decision_status = "BLOCKED"

  FinalReviewLoopProjection:
    match ReviewLoop.outputs.decision_status
      APPROVE:
        construct ResultT.APPROVED
      BLOCKED:
        construct ResultT.BLOCKED
      EXHAUSTED:
        construct ResultT.EXHAUSTED
```

The final projection must use loop-frame outputs. It must not reach into only
the first review step or into a body-local step that is not materialized onto
the loop frame. Existing review-loop phase documentation already contains this
class of bug guard: for plan phase outputs, the phase output review decision
must come from finalization, not from the first review step.

## 15. Loop Exhaustion Projection

The DSL already has `repeat_until.on_exhausted.outputs`, but it is intentionally
narrow: it maps declared loop-frame output names to literal scalar overrides
only when the body succeeds, outputs resolve, the condition evaluates false,
and `max_iterations` is exhausted. Without `on_exhausted`, exhausting
`max_iterations` remains a failed loop with `error.type:
repeat_until_iterations_exhausted`; body-step failures, output-resolution
failures, and predicate failures are still failures.

Therefore, `loop/recur` needs a generic frontend-level exhaustion projection:

```text
loop/recur :on-exhausted
  -> repeat_until.on_exhausted.outputs for scalar markers
  -> final typed projection from last materialized loop-frame outputs
```

Required behavior:

```text
if max_iterations exhausts after a completed iteration:
  set scalar marker decision_status = EXHAUSTED
  preserve last completed loop-frame outputs
  construct typed ResultT.EXHAUSTED in final projection

if body fails:
  ordinary failure, not EXHAUSTED

if output resolution fails:
  ordinary failure, not EXHAUSTED

if predicate evaluation fails:
  ordinary failure, not EXHAUSTED

if no explicit exhaustion projection exists:
  preserve DSL behavior: repeat_until_iterations_exhausted
```

This is a generic loop feature, not a review-loop compiler branch.

## 16. Source Maps And State Layout

Generated loop state, bundle paths, temp paths, pointer paths, and artifact
roots should be requested semantically and derived by `StateLayout`.

`StateLayout` owns canonical bundle paths, temporary bundle paths, snapshot
storage paths, phase/item/drain state namespaces, optional pointer
materialization paths, and observability labels. It is intended to keep
high-level frontend code from hand-managing state paths.

The review-loop stdlib implementation must source-map:

- caller call site;
- imported stdlib definition;
- macro expansion frame, if any;
- specialization arguments;
- generated monomorphic helper/private workflow;
- generated `repeat_until` frame;
- generated match cases;
- generated projection steps;
- generated state paths;
- generated bundle roots;
- selected review `ProcRef` definition;
- selected fix `ProcRef` definition;
- selected terminal-constructor `ProcRef`s, if bridge model is used.

High-level `.orc` code should request semantic layout targets such as:

```lisp
(phase-state phase_ctx "review-loop-frame")
(phase-target phase_ctx "review-report")
(phase-target phase_ctx "review-findings")
```

The layout layer derives concrete paths. Exact paths are design choices, not
frontend syntax. The state-layout doc makes this ownership boundary explicit.

Missing source-map origin for any generated step, boundary field, or generated
path is a compile-time failure.

## 17. Macro Boundary

Macros remain syntax expansion. They do not own runtime semantics.

Allowed:

```text
(review-revise-loop ...)
  expands to a call of a generic stdlib definition
```

or:

```text
(review-revise-loop ...)
  expands to a generated monomorphic .orc helper
  whose generated source then typechecks and lowers ordinarily
```

Disallowed:

- macro expansion owns hidden provider/command effects;
- macro expansion bypasses shared validation;
- macro expansion creates runtime procedure values;
- macro expansion creates source-map gaps;
- macro expansion encodes review/revise terminal behavior outside ordinary
  `.orc`.

The compile-time specialization design already distinguishes macro expansion
from parametric specialization: macros are syntax expansion, while parametric
specialization is type-aware definition instantiation. It also states
macro-origin restrictions: no hidden provider/command effects, no macro-owned
runtime semantics, no bypass around shared validation, and no loss of
source-map provenance.

## 18. Generic Specialization Identity

Every generated specialization must have a deterministic identity:

- source module;
- definition name;
- source definition digest;
- concrete type argument identities;
- compile-time `ProcRef` identities;
- target DSL version;
- language/compiler version;
- generated-name schema version;
- call-site identity, when needed for source-map or path obligations.

Equivalent call sites may share a specialization only if doing so preserves
source-map and generated-path obligations. Otherwise, the compiler should
generate per-call-site helpers.

The compile-time specialization and structural-constraints docs both require
specialization identity to include source module/name, source definition digest,
concrete type arguments, compile-time `ProcRef` identities, target DSL version,
language/compiler version, and generated-name schema version; they also require
source maps to identify the generic definition, call site, specialization
arguments, generated helpers, and generated path/write-root provenance.

## 19. Incremental Implementation Plan

### Stage 0 - Document And Guard The Architecture Boundary

Tasks:

- add this document;
- add reciprocal related-doc links where missing;
- mark `ReviewReviseLoopExpr` path as legacy/bridge-only;
- add regression guard that promoted stdlib review-loop tests cannot use
  literal-name compiler special casing;
- add static or unit-level check for lowerer/typechecker branches keyed to
  `review-revise-loop` in promoted mode.

Acceptance:

- legacy review-loop fixture still works only under legacy/bridge mode;
- new stdlib fixture fails for explicit missing generic feature, not unknown
  parser/lowerer behavior;
- test suite can disable `ReviewReviseLoopExpr` for promoted fixtures.

### Stage 1 - Generic Stdlib Import/Expansion Substrate

Tasks:

- load `std/phase.orc` through normal reader/parser/import resolution;
- allow stdlib `defproc`/`defworkflow` helper definitions;
- record imported definition provenance;
- ensure macros expand only to grammar-accepted `.orc`;
- add non-review stdlib helper fixture proving the path is generic.

Acceptance:

- non-review stdlib helper imports and lowers through the same path;
- generated steps source-map to caller and stdlib definition;
- no review-loop-specific compiler code is involved.

### Stage 2 - Generic `loop/recur :on-exhausted`

Tasks:

- add authoring surface for `loop/recur` exhaustion projection;
- lower scalar markers to `repeat_until.on_exhausted.outputs`;
- add final typed projection from loop-frame outputs;
- preserve DSL failure behavior for body/output/predicate failures;
- reject direct non-scalar `on_exhausted` overrides.

Acceptance:

- generic loop fixture returns typed `EXHAUSTED` result;
- exhaustion without explicit projection still fails as
  `repeat_until_iterations_exhausted`;
- body failure during final iteration remains ordinary failure;
- non-scalar `on_exhausted` override is rejected.

### Stage 3 - Compile-Time `ProcRef` Calls Inside Loops

Tasks:

- resolve `ProcRef` arguments before lowering;
- specialize selected review/fix procedures into callable helper/private
  workflow form;
- preserve provider and command effects from selected procedures;
- reject `ProcRef` values in runtime state;
- reject provider/prompt refs in runtime state;
- detect specialization cycles.

Acceptance:

- generic retry-loop fixture calls review/fix `ProcRef`s inside a loop;
- effect graph includes provider/command effects from hooks;
- runtime state contains no `ProcRef`/provider/prompt/type values;
- specialization cycle produces compile-time diagnostic.

### Stage 4 - Minimal Structural Generics

Tasks:

- parse `:forall` on `defproc`;
- parse inline `:where` structural constraints;
- support `is-record` and `is-union` constraints;
- support `has-field` constraints;
- support `has-union-variant` constraints;
- support `ProcRef` signature constraints with type parameters;
- instantiate monomorphic helper before ordinary lowering;
- typecheck instantiated helper;
- preserve variant proof through `match`.

Acceptance:

- pure generic `defproc` fixture passes;
- generic record-field fixture passes;
- generic union-match fixture passes;
- effectful generic `ProcRef` fixture passes;
- unsatisfied constraint fails before lowering;
- variant field access without proof fails before lowering.

### Stage 5 - Implement `std/phase.orc` `review-revise-loop`

Tasks:

- define stdlib `ReviewDecision` and `ReviewFindings`, unless already defined;
- define generic `review-revise-loop` in `std/phase.orc`;
- accept caller-owned `CompletedT`, `InputsT`, `ResultT`;
- express `ResultT` terminal variants as structural constraints;
- accept review/fix as compile-time `ProcRef` parameters;
- lower through `loop/recur`, `match`, `provider-result`/`command-result`,
  materialization, and projection;
- carry evidence identity through inputs/state;
- add source-map fixtures.

Acceptance:

- `APPROVE` first pass returns `ResultT.APPROVED`;
- `REVISE -> fix -> APPROVE` returns `ResultT.APPROVED` with fixed completed
  state;
- `BLOCKED` returns `ResultT.BLOCKED`;
- `REVISE` until `max_iterations` returns `ResultT.EXHAUSTED`;
- fix receives findings from the immediately preceding `REVISE` decision;
- terminal outputs come from loop frame/projection, not first review step;
- carried evidence cannot be redirected by `ReviewDecision` output.

### Stage 6 - Optional Terminal-Constructor Bridge

Use this only if direct generic result-union construction is not ready.

Tasks:

- add `on-approved`/`on-blocked`/`on-exhausted` `ProcRef` bridge surface;
- ensure constructor `ProcRef`s are compile-time only;
- ensure constructor effects are visible;
- ensure constructor return types specialize to concrete `ResultT`;
- mark bridge as migration-compatible but not the preferred long-term model.

Acceptance:

- review loop compiles without direct generic `ResultT` construction;
- runtime state still contains no constructor `ProcRef` values;
- source maps include constructor hooks;
- promotion remains blocked until either direct construction lands or bridge is
  accepted as stable stdlib API.

### Stage 7 - Remove Promoted Dependency On Compiler-Special Review Loop

Tasks:

- remove `ReviewReviseLoopExpr` from promoted expression table;
- remove or quarantine `_lower_review_revise_loop`;
- remove or quarantine review-loop-only typecheck branch;
- keep legacy fixtures explicitly marked legacy;
- ensure stdlib fixtures compile with special path disabled.

Acceptance:

- promoted review loop compiles without `ReviewReviseLoopExpr`;
- regression guard fails if lowerer recognizes literal `review-revise-loop`;
- generated workflow contains ordinary `repeat_until`/`match`/provider/command/
  projection surfaces.

### Stage 8 - Promotion Evidence

Tasks:

- compile stdlib review-loop candidate;
- run shared validation;
- run dry-run;
- run targeted fake-provider integration for `APPROVE`;
- run targeted fake-provider integration for `REVISE -> APPROVE`;
- run targeted fake-provider integration for `BLOCKED`;
- run targeted fake-provider integration for `EXHAUSTED`;
- run evidence-redirection negative test;
- run source-map provenance test;
- generate parity report;
- compute `non_regressive` mechanically.

YAML primary deprecation remains blocked until the relevant `.orc` parity report
is non-regressive. The migration architecture defines `non_regressive` as true
only when compile, shared validation, dry-run, required smoke/targeted
integration, baseline characterization, output contract parity, terminal state
parity, artifact parity, resume parity, and deprecated-mechanic
replacement/waiver requirements are all satisfied; missing required fields or
manual assertion of `non_regressive=true` force it false.

## 20. Diagnostics

Add precise diagnostics. Avoid generic "type error" where the failure is
architectural.

- `stdlib_special_form_disallowed`: compiler recognized `review-revise-loop` by
  name in promoted mode.
- `review_loop_special_lowerer_used`: promoted fixture attempted to use
  `ReviewReviseLoopExpr` or equivalent legacy branch.
- `unresolved_type_parameter`: type parameter escaped specialization.
- `ambiguous_type_argument`: call-site types do not determine one concrete type
  argument.
- `unsatisfied_structural_constraint`: concrete type lacks required field, union
  variant, or compatible field type.
- `unsupported_parametric_boundary`: generic type appeared where a monomorphic
  workflow boundary is required.
- `specialization_cycle`: generic/proc-ref specialization recursively depends
  on itself.
- `proc_ref_not_compile_time`: `ProcRef` argument did not resolve to a named
  `defproc` at compile time.
- `runtime_leaked_proc_ref`: `ProcRef` appears in lowered runtime state or
  contract.
- `runtime_leaked_provider_ref`: provider ref appears in lowered runtime state
  or contract.
- `runtime_leaked_prompt_ref`: prompt ref appears in lowered runtime state or
  contract.
- `runtime_leaked_type_parameter`: type parameter appears in Core AST, Semantic
  IR, Executable IR, artifact contract, output bundle, or provider/command
  payload.
- `hidden_macro_effect`: macro introduced provider/command effect not visible
  in expanded AST.
- `variant_field_without_proof`: generic body accessed a variant-only field
  outside proof-bearing match branch.
- `non_exhaustive_review_match`: review decision match does not cover
  `APPROVE`, `REVISE`, and `BLOCKED`.
- `exhaustion_projection_missing`: `loop/recur` needs typed `EXHAUSTED` result
  but no on-exhausted projection exists.
- `invalid_exhaustion_projection`: on-exhausted attempted to override
  non-scalar loop output directly.
- `loop_frame_projection_missing`: final result projection reads a value not
  materialized onto the loop frame.
- `evidence_authority_violation`: reviewer-produced field attempts to replace
  carried evidence identity.
- `source_map_origin_missing`: generated helper, step, field, path, or
  projection lacks source-map provenance.

## 21. Fixture Matrix

### 21.1 Generic Language Fixtures

- `generic_pure_identity.orc`
- `generic_record_field_constraint.orc`
- `generic_union_variant_constraint.orc`
- `generic_union_match_projection.orc`
- `generic_proc_ref_effectful_loop.orc`
- `generic_specialization_source_map.orc`
- `generic_specialization_cycle_negative.orc`
- `generic_ambiguous_type_argument_negative.orc`
- `runtime_leaked_type_parameter_negative.orc`
- `runtime_leaked_proc_ref_negative.orc`
- `variant_field_without_proof_negative.orc`
- `hidden_macro_effect_negative.orc`

### 21.2 Loop/Exhaustion Fixtures

- `loop_recur_exhausted_projection.orc`
- `loop_recur_exhausted_without_projection_negative.orc`
- `loop_recur_body_failure_not_exhausted_negative.orc`
- `loop_recur_output_resolution_failure_not_exhausted_negative.orc`
- `loop_recur_non_scalar_on_exhausted_negative.orc`
- `loop_recur_source_map.orc`

### 21.3 Review-Loop Stdlib Fixtures

- `phase_stdlib_review_loop_approve.orc`
- `phase_stdlib_review_loop_revise_approve.orc`
- `phase_stdlib_review_loop_blocked.orc`
- `phase_stdlib_review_loop_exhausted.orc`
- `phase_stdlib_review_loop_malformed_decision_negative.orc`
- `phase_stdlib_review_loop_malformed_findings_negative.orc`
- `phase_stdlib_review_loop_evidence_redirection_negative.orc`
- `phase_stdlib_review_loop_missing_bundle_negative.orc`
- `phase_stdlib_review_loop_no_special_lowerer_negative.orc`
- `phase_stdlib_review_loop_source_map.orc`
- `phase_stdlib_review_loop_resume_checkpoint_identity.orc`
- `phase_stdlib_review_loop_proc_ref_effects.orc`
- `phase_stdlib_review_loop_runtime_leak_negative.orc`

### 21.4 Migration/Parity Fixtures

- `review_loop_compile_pass`
- `review_loop_shared_validation_pass`
- `review_loop_dry_run_pass`
- `review_loop_fake_provider_approve_pass`
- `review_loop_fake_provider_revise_approve_pass`
- `review_loop_fake_provider_blocked_pass`
- `review_loop_fake_provider_exhausted_pass`
- `review_loop_output_contract_parity_pass`
- `review_loop_terminal_state_parity_pass`
- `review_loop_artifact_parity_pass`
- `review_loop_resume_parity_pass`
- `review_loop_non_regressive_report_pass`

## 22. Acceptance Checks

Before removing the promoted-path compiler-special review-loop branch, all of
the following must pass:

- generic `.orc` definitions can declare structural record and union
  constraints;
- unsatisfied constraints fail before lowering;
- specialization emits monomorphic helpers with no runtime type values;
- variant-specific fields remain proof-gated after specialization;
- `ProcRef` hooks are compile-time only;
- provider/command effects from `ProcRef` hooks are visible;
- one non-review fixture uses the same generic mechanism;
- `review-revise-loop` imports from `std/phase.orc`;
- `review-revise-loop` compiles with `ReviewReviseLoopExpr` disabled;
- `review-revise-loop` lowers to ordinary `repeat_until`, `match`,
  provider/command, materialization, and projection surfaces;
- `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, and `EXHAUSTED` behavior pass;
- `EXHAUSTED` is typed non-completion;
- `REVISE` is not completion;
- review-provider output cannot replace carried evidence identity;
- source maps identify caller, stdlib, specialization, generated helper,
  `ProcRef`s, and generated paths;
- runtime state contains no `ProcRef`, provider ref, prompt ref, closure, or
  type parameter;
- shared validation accepts generated workflow;
- parity report computes `non_regressive` mechanically.

These checks are consistent with the structural-constraints doc's acceptance
criteria: generic `.orc` definitions declare structural constraints,
unsatisfied constraints fail before lowering, specialization emits monomorphic
helpers with no runtime type values, variant-specific fields remain
proof-gated, one non-review-loop fixture uses the same mechanism, and
`review-revise-loop` can be expressed without compiler branches keyed to
literal review-loop names.

## 23. Compatibility And Migration Policy

Existing YAML workflows remain valid and primary until promotion evidence
passes.

Existing compiler-special review-loop support may remain temporarily as a
legacy bridge, but:

- legacy bridge fixtures must be marked legacy;
- promoted stdlib fixtures must run with the special path disabled;
- new review/revise feature work should target `std/phase.orc` plus generic
  constraints;
- no new caller should depend on `ReviewReviseLoopExpr` as the intended
  architecture.

Migration is additive:

1. Add stdlib `.orc` implementation.
2. Add generic constraints/specialization support needed by that implementation.
3. Add fixtures and negative tests.
4. Compile and validate.
5. Run dry-run and targeted fake-provider integrations.
6. Generate parity report.
7. Let promotion tooling compute `non_regressive`.
8. Only then mark `.orc` primary or remove YAML primary.

## 24. Open Questions

- Should the first stable API expose only `CompletedT`, `InputsT`, and
  `ResultT`, while keeping `ReviewDecision` and `ReviewFindings` as
  stdlib-owned concrete types?
- Should generic `DecisionT` and `FindingsT` wait until a concrete caller needs
  custom decision/findings schemas?
- Should fix receive only `ReviewFindings`, or the entire `REVISE` variant
  payload?
- Should terminal result construction use structural constraints from the
  start, or should constructor `ProcRef`s be accepted as a temporary bridge?
- If existing caller result unions use phase-specific field names, should the
  type system support trait aliases with field-name mapping, or should callers
  normalize to stdlib protocol field names?
- Should `review-revise-loop` be a `defproc`, `defworkflow`, or macro that
  expands to a call to a generic `defproc`?
- How much generic body checking should occur before monomorphic
  instantiation? The minimal implementation can typecheck instantiated helpers
  first, but better diagnostics require generic checking against constraints.
- What is the stable generated-name schema for specializations whose identity
  includes call-site provenance?
- How should resume checkpoint identity be assigned when a stdlib loop is
  imported, specialized, and lowered to a generated/private workflow?
- Which promotion gate should decide that the terminal-constructor bridge is
  stable enough, if direct generic union construction remains incomplete?

## 25. Summary Recommendation

Proceed in this order:

1. Add this integration doc and guardrails against promoted review-loop special
   casing.
2. Add generic stdlib import/expansion substrate.
3. Add generic `loop/recur` exhaustion projection.
4. Add compile-time `ProcRef` specialization inside loops.
5. Add minimal structural generics: `:forall`, `is-record`, `has-field`,
   `has-union-variant`, `ProcRef` constraints.
6. Implement `std/phase.orc` `review-revise-loop` using direct structural
   result constraints where possible.
7. Use terminal-constructor `ProcRef`s only as a bridge if direct generic union
   construction is not ready.
8. Prove `APPROVE`, `REVISE->APPROVE`, `BLOCKED`, `EXHAUSTED`, source-map,
   resume, and evidence-authority fixtures.
9. Remove `ReviewReviseLoopExpr` from the promoted path.
10. Gate migration through machine-computed parity evidence.

The key architectural move is not to move the existing Python branch into a
macro. The key move is to make the generic type system expressive enough that
`review-revise-loop` is just one ordinary effectful stdlib definition over
caller-owned typed state, caller-owned terminal results, compile-time procedure
hooks, structural result constraints, proof-preserving `match`, and generic
loop exhaustion projection.
