# Workflow Lisp Core Calculus And Compiler Middle-End

Status: draft design
Kind: architecture decision / future-direction compilation architecture
Created: 2026-06-09
Updated: 2026-06-09
Scope: re-founding Workflow Lisp lowering on a minimal workflow core calculus
with a real compiler middle-end — ANF normalization, second-class join-point
control, scope/effect/proof analysis, and defunctionalization into the
existing validated flat workflow model — so that effectful composition holds
by construction and no surface form ever needs a one-off lowerer.

Authority:

- `docs/design/workflow_lisp_frontend_specification.md` remains the umbrella
  Workflow Lisp frontend contract; this document refines its compilation
  pipeline, not its language surface or authority rule.
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
  owns the near-term migration tranches; this document is the structural
  architecture its Tranche 1 should be implemented against once accepted.
- Normative DSL/runtime behavior remains in `specs/`.
- Shared validation and the existing runtime remain the execution authority;
  this document changes how lowered output is produced, not what validates or
  executes it.
- This document does not by itself promote any `.orc` workflow to primary
  surface.
- A behavior described here is implementation-complete only when the listed
  verification evidence passes.

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_post_foundation_composition_stdlib_migration.md`
- `docs/design/workflow_lisp_runtime_migration_foundation.md`
- `docs/design/workflow_lisp_unified_frontend_design.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_semantic_workflow_ir.md`
- `docs/design/workflow_lisp_executable_ir.md`
- `docs/design/workflow_lisp_state_layout.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_runtime_closures_boundary.md`
- `docs/design/workflow_language_design_principles.md`
- `docs/reports/2026-06-09-design-delta-drain-orc-migration-frontend-runtime-findings.md`
- `specs/dsl.md`
- `specs/io.md`
- `specs/state.md`

## 1. Purpose

The 2026-06-09 design-delta drain findings showed that Workflow Lisp's
composition failures are not isolated bugs. They share one root cause: the
compiler has a surface language (parser, types, macros, ProcRef
specialization) and a backend (the flat validated step runtime), but no
middle-end. Lowering goes form-by-form straight from typed surface syntax to
flat steps. Each structured form — `match`, `repeat_until`, `loop/recur`,
`review-revise-loop` — has its own lowerer that only knows how to emit
top-level shapes. The typechecker accepts nested compositions that lowering
cannot express, so well-typed programs die after shared validation with no
owned diagnostic.

The post-foundation composition target fixes the observed shapes. This
document proposes the structural fix: define a minimal workflow core calculus
(WCC) and compile every surface construct through one general route —
elaboration into the calculus, ANF normalization, scope/effect/proof
analysis, and defunctionalization of second-class join points into the flat
step graph the existing runtime already executes. The same transformation
family that gives `async/await` its state machines gives Workflow Lisp
arbitrary nesting over an unchanged runtime.

The payoff is categorical rather than incremental: composition regularity
holds by construction (anything that typechecks elaborates and lowers),
findings like F2/F3/F4/F8 become impossible to reintroduce, and future
surface forms are macros or stdlib `.orc` over the calculus rather than new
compiler branches.

## 2. Executive Decision

Adopt a four-layer compilation architecture and migrate the existing
lowering onto it incrementally, behind a flag, with dual-compile equivalence
evidence at every stage:

```text
surface .orc
  -> macro expansion, import expansion, ProcRef specialization (existing)
  -> typecheck: types + effect rows + variant proofs (extended)
  -> WCC elaboration: desugar all structured forms into the core calculus
  -> ANF normalization: atomize effectful subexpressions
  -> scope / effect / proof analysis over the normalized program
  -> defunctionalization: join points -> flat steps, jumps -> routing,
     environments -> StateLayout-allocated bindings
  -> flat Core AST (existing validated workflow model)
  -> shared validation (unchanged authority)
  -> Semantic IR / executable IR / source maps (projections, unchanged owners)
  -> existing runtime (unchanged)
```

This commits the strategic choice that the post-foundation target's Tranche 1
left open between two routes: this document selects the flattening route
(route 1, lowering nested structured control into the existing validated
model with explicit scopes). The authority-inversion route (a
nesting-preserving executable IR that the runtime executes directly) is
explicitly deferred, and the calculus is designed so that route remains
reachable later without rework: WCC is exactly the representation such a
runtime would execute.

The migration is incremental and oracle-checked. The legacy per-form lowering
route remains the default until each construct class passes dual-compile
equivalence; per-form lowerers are deleted only after the generic route
covers them and a denylist prevents their return.

## 3. Relationship To The Post-Foundation Target

These two documents must not fork. The division of labor is:

- The post-foundation target
  (`workflow_lisp_post_foundation_composition_stdlib_migration.md`) owns
  *what must work and when*: the migration tranches, acceptance fixtures,
  private context bridge, certified adapters, typed projection, parity
  evidence, and the parent-callable family goal.
- This document owns *how lowering produces it*: the calculus, the pipeline,
  the normalization and defunctionalization contracts, and the equivalence
  policy for replacing the legacy lowering route.

Concretely:

- Post-foundation Tranche 1's "composition-normalized structured control
  graph" is, under this architecture, the ANF-normalized WCC program plus its
  scope analysis. Implementing Tranche 1 against this document satisfies that
  tranche; implementing a bespoke scope graph instead would create a second
  middle-end and is prohibited once this document is accepted.
- The post-foundation acceptance fixture (the nested implementation phase) is
  also this document's Tranche 3/4 gate.
- Post-foundation Tranche 2's union-normalization rule (returned variant
  decides output identity) is enforced here by construction: variant
  introduction (`inject`) is a distinct calculus construct from variant
  elimination (`case`), so the matched source case cannot leak into output
  identity.
- The composition-regularity invariant added to the post-foundation target is
  the theorem this architecture is designed to make true mechanically.

If this document is not accepted, the post-foundation target stands alone and
its Tranche 1 may choose either route. If this document is accepted, it
becomes the required implementation architecture for that tranche.

## 4. Authority And Dependency Direction

### 4.1 This document consumes

- `workflow_lisp_frontend_specification.md` owns the surface language, the
  authority rule (`.orc` lowers into the existing validated workflow model),
  and the compiler's public contract.
- `workflow_lisp_post_foundation_composition_stdlib_migration.md` owns the
  migration tranche sequence, acceptance fixtures, readiness labels, and
  parity policy this architecture must satisfy.
- `workflow_lisp_runtime_migration_foundation.md` owns command/provider
  structured-output authority, private value transport, strict gates, and the
  StateLayout/PathAllocator boundary the defunctionalizer allocates through.
- `workflow_lisp_state_layout.md` owns generated path identity, run
  isolation, and resume-identity rules; environment and frame allocation here
  must satisfy them.
- `workflow_lisp_proc_refs_partial_application.md` and
  `workflow_lisp_compile_time_parametric_specialization.md` own the
  compile-time procedure/specialization substrate that runs before
  elaboration.
- `workflow_lisp_runtime_closures_boundary.md` owns the decision that runtime
  closures stay deferred; second-class join points are designed to respect
  it.
- `workflow_lisp_semantic_workflow_ir.md` and
  `workflow_lisp_executable_ir.md` own the projection surfaces that consume
  middle-end metadata.
- `workflow_language_design_principles.md` owns the cross-frontend semantic
  authority rules.

### 4.2 This document owns

- the workflow core calculus: its construct set, typing/effect/proof rules,
  and the second-class join-point restriction;
- the elaboration contract: every surface structured form desugars into the
  calculus with no per-form lowering to flat steps;
- the elaboration totality invariant: a program that typechecks (types,
  effect rows, variant proofs) elaborates and normalizes without
  post-lowering rejection;
- the ANF normalization contract;
- the scope/effect/proof analysis contract over normalized programs;
- the defunctionalization contract: join points to steps, jumps to routing,
  environments to StateLayout allocations, and the stable-identity rules for
  generated steps;
- the lowering schema version and resume-compatibility policy for the new
  route;
- the dual-compile equivalence policy used to retire the legacy route; and
- the staged migration plan from per-form lowerers to the single generic
  route.

### 4.3 This document does not own

- surface syntax, the macro system, or stdlib semantics;
- shared validation authority or the runtime execution model;
- StateLayout/PathAllocator identity rules (consumed, not redefined);
- the private executable context bridge, certified adapter surface, typed
  projection, or resource-transition contracts (post-foundation target);
- migration parity gates, readiness labels, or promotion policy;
- runtime closures or any first-class continuation surface; and
- the authority-inversion (nesting-preserving executable runtime) decision,
  which stays deferred.

## 5. Target And Prohibited Dependency Directions

Target:

```text
typed surface form
  -> elaboration into WCC (total on typechecked programs)
  -> ANF-normalized WCC with scopes, effect rows, proofs, source frames
  -> defunctionalization through StateLayout allocation
  -> flat validated step graph
  -> shared validation (authority unchanged)
```

Prohibited:

```text
typed surface form
  -> form-specific Python lowerer emits flat steps directly
  -> nesting handled (or rejected) per form
  -> typechecker and lowerer disagree about the language boundary
  -> well-typed program rejected after lowering
```

Also prohibited:

```text
WCC or middle-end metadata
  -> serialized into runtime state, artifacts, or provider/command results
  -> treated as a second semantic authority beside shared validation
```

WCC is a compiler-internal representation. After defunctionalization it
exists only as provenance (source maps, Semantic IR projections), never as
runtime semantics.

## 6. Problem

Five concrete defects trace to the missing middle-end:

1. Nested structured control fails after lowering (F2): `match` and
   `repeat_until` lowerers only emit top-level shapes, and shared validation
   has no scope notion for branch-local generated steps.
2. Union translation is keyed on the matched case (F3): because elimination
   and introduction are not separate constructs in lowering, the lowerer
   reused the source variant name to normalize the output.
3. Output field identity is globally flat (F4): without scoped environments,
   lowered artifact names share one namespace, forcing globally unique field
   names across variants.
4. Stdlib abstractions are not first-class (F8): `review-revise-loop` lowers
   correctly only where its lowerer happens to support, rather than wherever
   a typed effectful procedure is valid.
5. Every new form costs a new lowerer: maintenance grows linearly in surface
   forms, and each lowerer re-implements path allocation, naming, source
   maps, and routing conventions with drift risk.

A locally scoped fix can patch shapes 1-4. Only a single general lowering
route eliminates class 5 and prevents recurrence of 1-4 in future forms.

## 7. Goals

- Define a minimal core calculus expressive enough for all current and
  planned Workflow Lisp control: sequencing, variant elimination and
  introduction, bounded loops, effectful operations, compile-time-resolved
  calls, and terminal results.
- Make elaboration total on typechecked programs: composition regularity by
  construction, with all unsupported-feature rejection at typecheck.
- Compile all structured control through join points: second-class labeled
  continuations that defunctionalize to flat steps and routing, preserving
  the no-runtime-closures boundary.
- Route every generated step identity, environment binding, and write root
  through StateLayout/PathAllocator with stable semantic identity and resume
  scopes.
- Preserve full provenance: every WCC node, generated step, and environment
  binding carries source frames through to source maps and Semantic IR.
- Keep shared validation and the runtime unchanged as authority; the new
  route emits the same validated model, better.
- Replace per-form lowerers with elaboration rules, deleting the lowerers and
  denylisting their return.
- Migrate incrementally behind a flag with dual-compile equivalence and
  behavioral oracles, never breaking existing workflows or resume identity
  for in-flight runs.
- Leave the authority-inversion route reachable: WCC is the representation a
  future nesting-preserving runtime would execute.

## 8. Non-Goals

- Do not change surface `.orc` syntax or semantics; this is a compilation
  architecture, not a language revision.
- Do not add runtime closures, first-class continuations, or dynamic
  dispatch; join points are second-class by design.
- Do not replace shared validation or the runtime; do not introduce a second
  execution authority.
- Do not adopt durable-execution/replay semantics (see Section 16).
- Do not invert authority to a nesting-preserving executable runtime in this
  document (deferred; see Section 16).
- Do not redesign StateLayout identity rules, the private context bridge,
  certified adapters, typed projection, or parity gates; this route plugs
  into them.
- Do not require a formal mechanized semantics before implementation; the
  calculus is specified rigorously but engineering-grade.
- Do not migrate all existing workflows' resume identity to the new lowering
  schema; in-flight and legacy-compiled runs keep their schema.

## 9. Architecture Invariants

- One lowering route: after migration completes, no surface form lowers to
  flat steps except through WCC elaboration, normalization, and
  defunctionalization. Per-form flat-step lowerers are denylisted.
- Elaboration totality: a program that passes typecheck (types, effect rows,
  variant proofs) elaborates, normalizes, and defunctionalizes without
  rejection. Any restriction is a typecheck-time diagnostic naming the
  restriction.
- Join points are second-class: they cannot be stored, returned, captured, or
  compared; they can only be defined and jumped to. This makes
  defunctionalization total and preserves the runtime-closures boundary.
- Variant introduction and elimination are distinct constructs: output
  variant identity comes only from `inject`; `case` contributes proof for
  field access, never output identity.
- Environments are scoped: every binding has a defining scope, and a
  reference is valid only where its definition dominates it. Lowered identity
  for bindings is scoped by `(owner chain, scope, name)`, never by flat name
  alone.
- All loops are bounded: every recursive join point carries an explicit
  budget, and exhaustion is a typed outcome, never a runtime crash.
- Effect rows are closed-vocabulary and align with the post-foundation effect
  summary classes; elaboration may not introduce effects absent from the
  surface program's checked row.
- WCC and middle-end metadata never appear in runtime state, artifacts,
  workflow outputs, or provider/command results.
- Every WCC node, generated step, environment binding, and allocation carries
  source-frame provenance into source maps and Semantic IR.
- Generated identity is semantic, not positional: formatting-only edits do
  not change step identity or resume identity; semantic ownership changes do.
- Lowering schema is versioned: runs record the schema they started with and
  resume under it; mixed-schema resume is rejected with a typed diagnostic.
- Dual-compile equivalence evidence, not inspection, gates each migration
  stage and the deletion of each legacy lowerer.

## 10. The Workflow Core Calculus

### 10.1 Constructs

WCC is deliberately small. Target construct count is ten; additions require
amending this document.

| Construct | Shape | Role |
| --- | --- | --- |
| `atom` | literals, variable refs, record construction, field projection | pure values; never lowered to steps |
| `inject` | `inject Union.Variant {field: atom, ...}` | variant introduction; sole source of output variant identity |
| `let` | `let x : T = <op> in body` | sequencing; in ANF, `<op>` is a single operation or atom |
| `perform` | `perform class.op(atoms) : T ! row` | effectful operation: provider call, command call, adapter call, workflow call, resource transition, projection, view materialization |
| `case` | `case x of Union.V1(binds) -> body1 \| ...` | variant elimination; opens a proof scope per arm; arms must be exhaustive or carry a typed default |
| `join` | `join k(params: T...) = body in scope` | second-class labeled continuation (join point) |
| `jump` | `jump k(atoms)` | transfer to a join point in scope |
| `rec-join` | `join rec k(params, budget: Bound) = body in scope` | bounded recursive join point; the only loop construct |
| `call` | `call f[spec](atoms) : T ! row` | compile-time-resolved procedure call; `f[spec]` is a specialized `defproc`/ProcRef body, inlined or cloned during elaboration |
| `halt` | `halt atom` | terminal workflow/procedure result |

Notes:

- There is no lambda, no first-class function, no store. The only "function
  space" is compile-time-resolved `call` plus second-class `join`. This is
  the smallest extension of straight-line code that expresses arbitrary
  branching and bounded iteration, and it is exactly what defunctionalizes
  to a flat step graph (join-point style, as in modern compiler middle-ends).
- `rec-join` budgets lower to the same exhaustion semantics the DSL's
  `repeat_until` already defines: budget exhaustion produces a typed
  `EXHAUSTED`-class variant routed like any other case, never a crash.
- `perform` operation classes are the closed effect vocabulary. Adding a
  class is a design change here and in the post-foundation effect summaries
  together.

### 10.2 Typing, effects, and proofs

- Every construct carries a type and an effect row. `atom` and `inject` are
  pure. `perform` and `call` carry rows from their declarations. `let`,
  `case`, `join`, and `jump` propagate rows by union.
- `case` arm bodies typecheck with the arm's variant proof in scope; field
  access on the scrutinee outside a proving arm is a type error.
- A branch returning union type `T` must end in `inject T.V {...}`, a `jump`
  to a join point whose parameters carry `T`, a `call` returning `T`, or
  `halt`. The returned `inject` (or the called procedure's returns) decides
  the variant — eliminating F3 by construction.
- `jump` arity and types must match the join point's parameters; join-point
  parameters are how values flow out of branches and around loop iterations,
  replacing ad hoc "branch projection" rules with ordinary binding.
- Effect rows are checked against declared procedure signatures before
  elaboration; elaboration and normalization may reorganize control but may
  not change a program's row.

### 10.3 Elaboration of surface forms

All surface structured forms become calculus programs. Representative rules:

- `let*` chains elaborate to nested `let`.
- Surface `match` elaborates to `case`, with a fresh join point as the
  continuation when the match is in non-tail position:

```text
;; surface
(let ((r (match attempt
           (COMPLETED ...big body...)
           (BLOCKED   ...other body...))))
  (use r))

;; calculus
join k(r: PhaseResult) = (use r) in
case attempt of
  ImplementationAttempt.COMPLETED(..) -> ...big body... ; jump k(result1)
  ImplementationAttempt.BLOCKED(..)   -> ...other body...; jump k(result2)
```

- Surface loops (`loop/recur`, `repeat_until` semantics) elaborate to
  `rec-join` with the loop state as parameters and the bound as budget.
- Stdlib abstractions such as `review-revise-loop` are ordinary imported
  `.orc` procedures; after specialization they elaborate like any user code.
  No stdlib name reaches the middle-end.

Because elaboration targets the calculus rather than flat steps, nesting is
trivially compositional: a `rec-join` inside a `case` arm inside another
`case` arm is just a calculus program. The implementation-phase fixture from
the design-delta findings elaborates without any special handling:

```text
let attempt : ImplementationAttempt = perform provider.call(...) in
case attempt of
  COMPLETED(..) ->
    let checks = perform command.call(...) in
    let loop_result = call review-revise-loop[spec](...) in
    case loop_result of
      APPROVED(..)  -> inject ImplementationPhaseResult.COMPLETED {...}
      EXHAUSTED(..) -> inject ImplementationPhaseResult.REVIEW_EXHAUSTED {...}
      BLOCKED(..)   -> inject ImplementationPhaseResult.BLOCKED {...}
  BLOCKED(..) -> inject ImplementationPhaseResult.BLOCKED {...}
```

## 11. The Middle-End Pipeline

### 11.1 ANF normalization

Normalization brings elaborated programs to administrative normal form:

- every `perform` and `call` result is bound by a `let` to a fresh or
  authored name;
- compound arguments are atomized (bound first, then referenced);
- `case` scrutinees are atoms;
- non-tail `case`/`rec-join` results flow through join points rather than
  implicit expression results; and
- normalization preserves types, rows, proofs, and source frames node by
  node.

After ANF, control structure is fully explicit: a program is a tree of
scopes whose leaves are straight-line `let` sequences ending in `jump`,
`inject`-then-`jump`, or `halt`.

### 11.2 Scope, effect, and proof analysis

Over the normalized program the middle-end computes, per scope:

- binding table (name, type, defining construct, source frame);
- dominance: which bindings each reference may legally see;
- live-out sets per join point (which bindings cross into which jumps);
- effect summary (union of rows, per the closed vocabulary);
- active variant proofs; and
- allocation requests (write roots, bundle paths, view paths) attributed to
  the requesting scope and frame.

This analysis is the artifact the post-foundation target calls the
"composition-normalized structured control graph": `scope_id`, parent scope,
entering control node, active proof, loop/call-frame identity, produced and
projected values, declared effects, and requested allocations all fall out of
ANF structure plus this pass.

### 11.3 Defunctionalization

Join points are second-class, so defunctionalization is total and simple:

- each join point becomes a flat step label; each `rec-join` becomes a step
  participating in the existing loop/exhaustion machinery with its budget;
- each `jump` becomes a routing edge; `case` becomes the existing
  variant-routing surface over its scrutinee;
- each straight-line `let` sequence of `perform`s becomes the corresponding
  provider/command/adapter/workflow/transition/projection steps;
- join-point parameters and live-out bindings become the step environment:
  values persisted across routing edges through existing state/binding
  mechanics, with paths and identities allocated via
  StateLayout/PathAllocator;
- linear jump chains may be fused into single steps as an optimization;
  fusion must be deterministic and provenance-preserving; and
- the emitted flat graph is ordinary lowered output: shared validation sees
  steps, routes, contracts, and effects exactly as it does today, plus the
  scope metadata it needs to check branch-local visibility.

### 11.4 Identity and resume

Step and binding identity is semantic:

```text
step_identity = (workflow/module id,
                 owner chain of procedures and join points,
                 join point or operation name,
                 specialization identity,
                 loop-frame role)
```

- Source spans are provenance only; formatting edits do not move identity.
- Resume scopes follow StateLayout's existing vocabulary (`run`,
  `call_frame`, `loop_frame`, `loop_iteration`, `step_visit`); a `rec-join`
  iteration maps to `loop_iteration`, a `call` body to `call_frame`.
- The new route stamps `lowering_schema_version: 2` into compile artifacts
  and run state at start. Runs resume under their recorded schema; resuming a
  schema-1 run with schema-2 lowering (or vice versa) is rejected with a
  typed diagnostic naming both versions. Legacy workflows keep schema 1
  until recompiled and re-run.

## 12. Incremental Migration Tranches

Each tranche is flag-gated (`WCC route` off by default until its acceptance
passes), oracle-checked, and individually shippable.

### 12.1 Tranche M0: characterization oracle

Contract: before any route change, freeze current behavior. Build a fixture
corpus of representative `.orc` workflows (value-only, straight-line
effectful, top-level match, top-level loops, review-revise plan phase, the
design-delta leaves) with golden lowered-output snapshots (structural, not
byte-level) and behavioral run records (terminal states, outputs, artifacts,
state rows) using fake providers.

Acceptance:

- the corpus compiles and runs green under the legacy route;
- snapshot comparison tooling distinguishes structural identity, declared
  renames, and real divergence; and
- the corpus covers every construct class the migration will move.

### 12.2 Tranche M1: calculus and pure subset

Contract: implement the WCC data model, elaboration for atoms, records,
`inject`, `let`/`let*`, and ANF normalization. Dual-compile value-only
workflows.

Acceptance:

- value-only corpus fixtures produce structurally identical lowered output
  under both routes;
- elaboration totality holds on the subset (no post-typecheck rejection);
- source frames survive elaboration and normalization node by node.

### 12.3 Tranche M2: straight-line effects

Contract: elaborate `perform` for provider/command/adapter/workflow calls and
`call` for specialized procedures; defunctionalize straight-line programs.
Effect rows checked at typecheck flow through unchanged.

Acceptance:

- straight-line effectful fixtures pass dual-compile equivalence (Level A
  where step naming is unchanged, Level B behavioral equivalence where
  renames are declared; see Section 13.4);
- StateLayout allocation requests from the new route match the legacy
  route's families for the same fixtures;
- no effect row differs between typecheck and lowered effect summaries.

### 12.4 Tranche M3: case and join points

Contract: elaborate `match` to `case` plus join points, including non-tail
and nested `match`. Shared validation receives scope metadata for
branch-local steps. This is where nested `match`-in-`match` first compiles.

Acceptance:

- top-level match fixtures pass dual-compile equivalence;
- nested `match`-in-`match` fixtures (no legacy equivalent) compile,
  validate, and smoke under the new route;
- union-to-union translation fixtures pass: `inject` decides output variants
  for all three design-delta mappings, with no `KeyError` path;
- branch-local ref leakage negative fixtures fail at the right layer with
  owned diagnostics.

### 12.5 Tranche M4: loops and the full fixture

Contract: elaborate `rec-join` for loops and `repeat_until` semantics,
including nesting under `case` arms; route stdlib `review-revise-loop`
(already ordinary `.orc` after specialization) through the generic route.

Acceptance:

- top-level loop fixtures pass dual-compile equivalence;
- the post-foundation Tranche 1 acceptance fixture (implementation phase:
  provider attempt, `COMPLETED` branch runs checks plus review loop,
  `BLOCKED` branch terminal) compiles, validates, source-maps, and smokes as
  one workflow under the new route;
- loop exhaustion lowers to typed outcomes with stable
  `loop_frame`/`loop_iteration` resume identity;
- APPROVE / REVISE->APPROVE / BLOCKED / EXHAUSTED review-loop fixtures pass
  nested under a `case` arm.

### 12.6 Tranche M5: route flip and lowerer deletion

Contract: make the WCC route the default for new compiles; delete per-form
flat-step lowerers whose construct classes are covered; add architectural
denylist tests preventing direct surface-to-step lowering from returning.

Acceptance:

- full corpus green under the new route as default;
- each deleted lowerer has a corresponding passing generic-route fixture and
  a denylist test;
- legacy schema-1 resume still works for pre-existing runs; mixed-schema
  resume is rejected with the typed diagnostic;
- variant-scoped field identity (post-foundation Tranche 2) is implemented
  on the new route's scoped environments.

## 13. Design Details

### 13.1 WCC node contract

Every node carries:

```text
node_id
construct kind
type
effect_row
scope_id
source_frame_stack          ; authored form, macro frames, import frames,
                            ; specialization frames
proof_context               ; active variant proofs
allocation_requests         ; StateLayout semantic requests, if any
```

Join points additionally carry:

```text
join_name (hygienic, owner-chain qualified)
parameters (name, type)
recursive? and budget, for rec-join
live_in / live_out binding sets (filled by analysis)
defunctionalized step identity (filled by defunctionalization)
```

### 13.2 Environment-to-state mapping

Join-point parameters and live-out bindings that cross routing edges are the
program's environment. The defunctionalizer maps each crossing binding to a
state-carried value through existing runtime binding mechanics:

- scalar/relpath/record/collection values use the foundation's private typed
  value transport;
- binding identity is `(owner chain, scope, name)` allocated via StateLayout
  with the appropriate resume scope;
- bindings never become public inputs; the post-foundation private context
  bridge and boundary inspection apply unchanged; and
- environments are explained in source maps and Semantic IR as generated
  bindings with their defining scope and frames.

### 13.3 Diagnostics contract

All language-boundary rejection happens at or before typecheck:

- a feature the calculus cannot express is a surface/typecheck diagnostic
  naming the restriction (there are intentionally few: first-class
  procedure values, unbounded recursion, effects outside the closed
  vocabulary);
- elaboration, normalization, and defunctionalization failures on
  typechecked programs are compiler defects by definition and must say so in
  their error text, with node provenance; and
- shared-validation failures on generic-route output are likewise compiler
  defects unless the workflow violates a contract the typechecker does not
  own (path safety against the live filesystem, for example).

### 13.4 Dual-compile equivalence policy

Two levels, used per fixture class:

- Level A (structural): the lowered flat graphs are isomorphic up to a
  declared, mechanical rename map (step labels, generated input names).
  Required for fixtures whose legacy output is already well-shaped.
- Level B (behavioral): fake-provider runs produce equal terminal states,
  outputs, artifacts, and state rows modulo the same rename map and
  schema-version fields. Required where the new route legitimately emits
  different graph shape (fused steps, join-point naming).

Equivalence evidence is machine-checked and recorded with the fixture; "looks
the same on inspection" is prohibited evidence.

### 13.5 What the runtime sees

Nothing new. The runtime executes the same validated flat model: steps,
routes, contracts, loop budgets, structured-output bindings, StateLayout-
allocated paths. The middle-end is invisible at execution time except through
provenance projections. This is the central property that keeps the overhaul
incremental: all risk is concentrated at compile time, where dual-compile
oracles can catch it.

## 14. Contracts And Interfaces

### 14.1 Typechecker

- Owns the full language boundary: types, effect rows, variant proofs,
  exhaustiveness, join arity (post-elaboration check), boundedness of loops.
- Emits the restriction diagnostics that used to surface as post-lowering
  failures.

### 14.2 Elaborator

- One elaboration rule per surface form, producing WCC only.
- Total on typechecked programs.
- Preserves source frames per node; macro/import/specialization frames stack.

### 14.3 Normalizer and analyzer

- ANF normalization preserving types, rows, proofs, frames.
- Produces the scope graph (binding tables, dominance, live sets, effect
  summaries, allocation attribution) consumed by defunctionalization, shared
  validation metadata, source maps, and Semantic IR.

### 14.4 Defunctionalizer

- Join points to steps, jumps to routes, environments to StateLayout-backed
  bindings, budgets to loop/exhaustion machinery.
- Allocates exclusively through StateLayout/PathAllocator.
- Emits flat Core AST plus scope metadata; never bypasses shared validation.

### 14.5 Shared validation

- Authority unchanged; gains scope-aware ref checking (producer dominance)
  driven by middle-end metadata, per the post-foundation target.

### 14.6 Projections

- Source maps gain join-point, environment-binding, and fusion entries.
- Semantic IR gains state-layout entries for environments and frames derived
  from allocation metadata, consistent with existing ownership.

## 15. Alternatives Considered

- Per-shape patches (extend each lowerer to handle the observed nestings):
  rejected as the long-term route; it preserves the per-form architecture
  that produced the findings and grows quadratically (forms x contexts). It
  remains acceptable as a stopgap only if this document is rejected.
- Nesting-preserving executable IR with runtime execution (authority
  inversion): deferred, not rejected. It removes flattening but rebuilds the
  runtime, shared validation, and resume semantics — the highest-risk
  surface in the system. WCC keeps this path open: such a runtime would
  execute WCC. Revisit after the flattening route has proven the calculus on
  a real promoted family.
- Durable execution / journal replay (Temporal-style): rejected for this
  system. It trades away static effect visibility, validation-before-commit,
  and machine-diffable parity evidence — the repo's core authority
  principles — for composition generality this architecture achieves at
  compile time.
- Runtime closures to express composition: rejected; explicitly owned and
  deferred by `workflow_lisp_runtime_closures_boundary.md`, and unnecessary
  given second-class join points plus compile-time specialization.

## 16. Deferred Work

- Authority inversion: executing WCC (or an IR derived from it) directly in
  a future runtime, making YAML the lowered view. Revisit only after one
  real family is promoted through the flattening route.
- Optimization passes beyond linear jump fusion (dead-binding elimination,
  step deduplication across arms): defer until equivalence tooling is
  mature; every pass must preserve provenance and equivalence evidence.
- A formal (mechanized) semantics for WCC: valuable, not gating.
- Surface-language conveniences enabled by the calculus (early return,
  guard-style matching): macro-layer work after M5, not middle-end work.

## 17. Work Blocked And Not Blocked

Blocked until this document's route covers the relevant construct class:

- deleting any per-form lowerer;
- accepting new surface structured-control forms that would need a new
  flat-step lowerer (they should wait and land as elaboration rules or
  macros);
- implementing post-foundation Tranche 1 via a bespoke scope graph parallel
  to this middle-end (prohibited once this document is accepted).

Explicitly not blocked by this document:

- all post-foundation tranches other than Tranche 1's substrate choice:
  private context bridge, certified adapters, typed projection,
  resume-or-start, parity labels, helper classification;
- the design-delta leaf candidates and bridge records;
- foundation-owned surfaces.

## 18. Evidence And Implementation Boundaries

### 18.1 Required evidence

- The calculus exists as a typed data model with elaboration rules for every
  surface form in the migrated class, and totality is enforced by tests that
  sweep typechecked fixtures through the full pipeline.
- Dual-compile equivalence (Level A or declared Level B) is machine-checked
  per fixture class before any default-route change.
- The post-foundation acceptance fixture passes end to end under the generic
  route (M4).
- Deleted lowerers have denylist tests.
- Resume-schema versioning has fixtures for same-schema resume, cross-schema
  rejection, and legacy-run continuation.

### 18.2 Prohibited evidence

- A nested fixture that compiles only because a per-form lowerer learned one
  more special case.
- Equivalence claimed by inspection, or by byte-comparing debug YAML.
- A typechecked program rejected by elaboration/normalization being treated
  as a language restriction rather than a defect.
- WCC metadata observed in runtime state, artifacts, or outputs.
- Route-flip (M5) justified while any corpus fixture still requires the
  legacy route.

## 19. Compatibility And Migration

- Existing `.orc` workflows are unaffected until M5, and after M5 compile to
  equivalent-or-better lowered output under schema 2; their surface source
  does not change.
- Existing YAML workflows are untouched; YAML does not pass through the
  middle-end.
- In-flight and historical runs resume under their recorded lowering schema.
- The post-foundation target's tranches, fixtures, and parity policy apply
  unchanged; this document only fixes how Tranche 1's substrate is built.
- If this document is rejected or stalls after M2, the system is left
  strictly better: the characterization corpus (M0) and pure/effect subsets
  (M1-M2) are useful hardening regardless, and the legacy route remains
  default throughout.

## 20. Verification Strategy

Calculus and elaboration tests:

- construct-level golden tests: each surface form's elaboration output;
- totality sweep: every typechecked corpus fixture passes elaboration,
  normalization, and defunctionalization or the build fails;
- hygiene tests: join names and bindings are owner-chain qualified; no
  capture across import/specialization boundaries;
- proof tests: scrutinee field access outside a proving arm fails typecheck;
  `inject` decides output variants for cross-union translation.

Normalization and analysis tests:

- ANF shape invariants (atom arguments, bound effect results);
- dominance and live-set correctness on branching/loop fixtures;
- effect-row preservation end to end;
- source-frame preservation node by node.

Defunctionalization tests:

- join-to-step identity stability under formatting edits;
- identity change under semantic ownership change;
- environment bindings allocated via StateLayout with correct resume scopes;
- collision-proofing across repeated calls, arms, and iterations;
- jump-chain fusion determinism and provenance.

Migration tests:

- M0 corpus snapshots and behavioral records;
- per-tranche dual-compile equivalence (Levels A/B);
- post-foundation acceptance fixture under the generic route;
- denylist tests for deleted lowerers;
- schema-version resume fixtures (same-schema, cross-schema rejection,
  legacy continuation).

## 21. Declarative Acceptance Scenarios

### 21.1 Nesting by construction

Initial state: the implementation-phase fixture (provider attempt; completed
branch runs checks plus `review-revise-loop`; blocked branch terminal).

Entrypoint: compile under the WCC route, shared validation, fake-provider
smoke.

Expected result: the fixture elaborates to `let`/`case`/`call`/`inject` plus
join points with no form-specific handling, defunctionalizes to a flat graph
that shared validation accepts, and runs with stable branch-scoped resume
identity.

Forbidden result: any code path that recognizes `match`, `repeat_until`, or
`review-revise-loop` by name during lowering.

### 21.2 Typecheck owns the boundary

Initial state: a fixture using a deliberately unsupported feature (a
procedure value escaping as data).

Entrypoint: compile.

Expected result: a typecheck diagnostic naming the restriction.

Forbidden result: the fixture typechecks and then fails during elaboration,
lowering, or shared validation.

### 21.3 Equivalence-gated route flip

Initial state: full M0 corpus; WCC route candidate for default.

Entrypoint: dual-compile and behavioral oracle run over the corpus.

Expected result: every fixture passes Level A or declared Level B
equivalence; the flip is recorded with the evidence; legacy lowerers for
covered classes are deleted with denylist tests.

Forbidden result: route flip with any fixture still on the legacy route, or
equivalence asserted without machine-checked records.

### 21.4 Resume schema safety

Initial state: a run started under lowering schema 1; the workflow is
recompiled under schema 2.

Entrypoint: `orchestrator resume <run_id>`.

Expected result: the run resumes under schema 1 semantics, or fails with a
typed diagnostic naming both schema versions and the remedy.

Forbidden result: a schema-2 graph silently adopts a schema-1 run's step
state.

## 22. Success Criteria

- WCC exists with at most ten constructs, typed, with effect rows and proof
  scopes, and every migrated surface form elaborates into it.
- Elaboration totality holds: the corpus contains no typechecked program
  rejected after typecheck.
- The post-foundation Tranche 1 acceptance fixture, nested
  `match`-in-`match`, loops under branches, and stdlib review loops in
  branches all compile, validate, and smoke through the single generic
  route.
- Cross-union translation and variant-scoped binding identity hold by
  construction on the new route.
- Per-form flat-step lowerers for migrated classes are deleted and
  denylisted.
- Dual-compile equivalence evidence exists for every migrated fixture class;
  the route flip is recorded with that evidence.
- Resume identity is schema-versioned with same-schema continuation and
  cross-schema rejection proven by fixtures.
- Shared validation, the runtime, StateLayout ownership, and all
  post-foundation contracts are unchanged in authority.

## 23. Summary Recommendation

Accept this as the structural fix the composition findings point at, and
implement post-foundation Tranche 1 against it rather than as a bespoke
scope graph. Sequence it as M0-M5 behind a flag with the characterization
corpus as the safety net: the first two tranches are low-risk hardening that
pays for itself even if the migration stalls, and from M3 onward each tranche
retires a whole class of composition failures rather than a list of observed
shapes.

The strategic property to protect is concentration of risk at compile time:
the runtime, shared validation, and parity machinery stay exactly as they
are, so every middle-end defect is catchable by dual-compile oracles before
any workflow runs. The strategic option to preserve is authority inversion:
WCC is precisely what a future nesting-native runtime would execute, so this
route is a step toward that future rather than a detour from it.
