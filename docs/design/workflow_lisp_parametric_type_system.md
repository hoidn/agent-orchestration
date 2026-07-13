# Workflow Lisp Parametric Type System

Status: draft design (consolidates and supersedes
`workflow_lisp_compile_time_parametric_specialization.md` and
`workflow_lisp_structural_parametric_constraints.md`)
Kind: Workflow Lisp language design / implementation architecture
Created: 2026-07-06

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md` (parent language contract)
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
  (owns `ReviewFindings` / `ReviewDecision` / `ReviewLoopResult` schemas)
- `docs/design/workflow_lisp_type_catalog.md` (type-to-contract mapping)
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_macro_surface_contract.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_runtime_native_drain_authoring.md` (owns the
  concrete drain hook shape contracts consumed by Tranche 2)
- `docs/design/workflow_lisp_shared_owner_lane_prerequisites.md`

## Purpose

This document is the single owner of the Workflow Lisp parametric type-system
direction: the generic-definition surface, the structural-constraint
vocabulary, the specialization pipeline, and the policy governing which
compiler-known stdlib forms migrate onto that substrate. It replaces the two
2026-06-02 draft designs, which cross-owned this feature and duplicated its
pipeline contract.

Consuming docs must not restate the pipeline or invent parallel constraint
spellings; they reference this document and own only their domain schemas.

## Evidence Base

The first tranche of this direction is implemented and in production:

- `std/phase.orc` `review-revise-loop-proc`: generic `defproc` with
  `:forall (CtxT CompletedT InputsT)`, `:where` record constraints, `ProcRef`
  hook parameters whose signatures mention type parameters, and a stdlib-owned
  terminal union.
- `std/resource.orc` `finalize-selected-item-proc`: `:forall (PlanT ImplT)`
  with `has-union-variant` constraints and `match` with refined match binders
  on constrained parameters.
- Shared machinery with no knowledge of consumer names:
  `procedure_specialization.py` (instantiate-then-typecheck),
  `procedure_typecheck.py`, `parametric_constraints.py`,
  `specialization_typecheck.py`.
- A non-stdlib fixture family (`generic_stdlib_composition`) covering
  effectful generic bodies and union proof.

Measured outcome (2026-07-06 checkout): the migrated `review-revise-loop`
retains roughly 160–200 lines of residual name-associated Python; the
unmigrated `backlog-drain` intrinsic costs roughly 3,500 name-keyed lines,
including a form-specific monomorphizer that duplicates the shared
specialization engine and ~230 dead duplicated validator lines
(`typecheck_dispatch.py` shadows its imports from `typecheck_calls.py`).
That measured ratio is the standing justification for the migration policy in
this document.

## Decision

1. Compile-time parametric specialization with explicit structural constraints
   is the type-system mechanism for reusable `.orc` definitions over
   caller-specific records and unions.
2. Constraint field types may reference `:forall` parameters (see
   Constraint Vocabulary). This is the mechanism for cross-parameter type
   contracts and is required by the `backlog-drain` migration.
3. Structural constraints have subset semantics: they prove required shape and
   never forbid additional fields or variants. Exact-shape matching is not part
   of the constraint surface (see Subset Semantics).
4. Compiler-known stdlib forms are classified as permanent effect primitives or
   migration-destined forms; migration-destined forms move onto the generic
   substrate when they pass the per-form migration test (see Form
   Classification and Migration Policy).
5. No runtime dispatch, runtime type values, runtime closures, or
   runtime-transported procedure/provider/prompt references, in any tranche.
   This prohibition is load-bearing for checkpoint identity, effect
   visibility, census surfaces, and migration-parity gates, all of which
   compare compiled artifacts.

## Non-Goals

- No runtime multiple dispatch or method tables.
- No implicit structural inference of constraints from generic bodies:
  a generic definition's requirements are exactly its declared `:where`
  clauses plus its parameter types. (Rationale: inferred requirements make
  stdlib field accesses an unstable implicit API and degrade diagnostics to
  errors inside bodies the caller did not write.) This is enforced today by
  the body-side capability discipline: a generic-body access not justified by
  a declared constraint fails with `parametric_capability_undeclared`
  (`typecheck_proofs.py`), with an invalid fixture covering it.
- No weakening of effect visibility, source maps, structured result
  validation, shared validation, or migration-parity gates.
- No monomorphic-stdlib fallback for reusable definitions: fixed stdlib
  payload records with caller adapters force typed caller data through
  file round-trips (pointer-as-state), which the frontend specification
  prohibits.

## Core Model

A generic definition is a `defproc` with compile-time type parameters:

```lisp
(defproc name
  :forall (T U)
  ((value T)
   (next ProcRef[(T) -> U]))
  :where ((T is-record)
          (U has-union-variant DONE (report WorkReport)))
  -> ResultType
  body)
```

Clause order is fixed: `:forall`, ordinary parameter list, `:where`, return
type. `:where` binds only type parameters introduced by `:forall`; it is not a
constraint surface for ordinary term parameters.

Semantic contract:

- type parameters are compile-time-only names, resolved before executable IR;
- each concrete instantiation is monomorphic;
- type parameters may appear in parameter types, return types, `ProcRef`
  signatures, record/union constructors, local annotations, and constraint
  field types;
- unresolved type parameters are illegal in Core AST, Semantic IR, Executable
  IR, runtime state, artifact contracts, output bundles, and provider/command
  payloads.

Type-argument binding rules:

- **Binding sources.** Type arguments are inferred from concrete call-site
  parameter types, including the signatures of `ProcRef` arguments.
  Constraints do not drive inference; they are checked after all type
  parameters are bound (see Constraint Vocabulary, rule 3). There is no
  explicit type-application syntax (see Deferred Extensions).
- **Exact agreement.** When a type parameter binds from more than one
  position, every occurrence must resolve to the same semantic type
  (refinements included); a conflict is a compile-time error
  (`parametric_type_binding_ambiguous`). This matches the implemented
  behavior (`procedure_typecheck.py` compares repeat bindings with
  semantic-equality `type_refs_compatible`).
- **Definition-site coverage.** Every `:forall` parameter must appear in at
  least one parameter or `ProcRef`-signature position of the definition.
  This is a property of the definition, checked when the generic definition
  is compiled — not an inference failure surfaced at some caller's first
  use. (Implemented as `procedure_type_param_unbindable` during definition
  typechecking.) A consequence: return-only type parameters are inexpressible
  by construction; see Deferred
  Extensions (explicit type application).

## Caller Surface

Callers never write type arguments: inference binds every parameter from the
concrete types of ordinary arguments and hook signatures, so the call site
stays keyword-labeled and self-describing. This document is the primary
interface for autonomous caller-authors, who work by imitating worked
examples; the canonical minimal consumer is
`tests/fixtures/workflow_lisp/valid/drain_stdlib_backlog_drain.orc` (98
lines: one caller-owned selection union, three hook workflows, one call) and
is normatively blessed as the exemplar to imitate. The call itself:

```lisp
(backlog-drain neurips
  :ctx ctx
  :selector selector-run
  :run-item run-selected-item
  :gap-drafter gap-draft
  :max-iterations 4)
```

A caller authors three things: its concrete types (the selection union and
payload records satisfying the definition's `:where` clauses), its hook
procedures (ordinary `defproc`/workflow definitions whose signatures drive
inference), and one keyword-labeled call. Nothing else — no instantiation
syntax, no adapters, no stdlib payload round-trips.

## Constraint Vocabulary

This document owns the constraint surface. The stable forms:

- `T is-record`
- `T is-union`
- `T has-field name Type`
- `T has-union-variant VARIANT`
- `T has-union-variant VARIANT (field Type ...)`
- `T has-shared-union-field name Type`

Rules:

1. **Subset proof only.** Each form proves that a concrete type provides the
   named capability. No form forbids additional fields or variants, proves
   exact shape, or justifies constructing caller-owned union variants the
   generic body does not otherwise have proof for.
2. **`has-shared-union-field`** requires: `T` resolves to a non-empty concrete
   union; every declared variant declares the named field; each field type is
   assignment-compatible with the constraint type. The granted proof is
   branch-free projection of that field only — no variant proof, no
   construction.
3. **Type-parameter field types.** The `Type` position in `has-field`,
   `has-union-variant`, and `has-shared-union-field` may be another `:forall`
   parameter:

   ```lisp
   :forall (SelectionT SelPayloadT)
   ...
   :where ((SelectionT has-union-variant SELECTED (selection SelPayloadT)))
   ```

   Semantics: by constraint-check time every type parameter is already bound
   from call-site parameter types; the check compares the concrete variant
   field type against the bound parameter for assignment compatibility
   (rule 4). A constraint referencing a parameter that appears in no
   parameter or `ProcRef` signature position is already illegal at
   definition time (Core Model, definition-site coverage); constraints are
   never an inference source. This rule is how cross-parameter contracts are
   expressed — e.g. "the run-item hook's payload parameter is the same type
   as the selector's `SELECTED.selection` field." Implementation status: a
   type-parameter-named field type must be resolved as a type-parameter
   placeholder, not looked up against the registered type environment, at
   every point a generic definition's `:where` clauses are processed —
   per-clause constraint checking, the provisional pass that types match
   arms against a `:where`-declared union, and variant-field projection
   typechecking inside the generic body. An eager, non-parameter-aware
   resolution at any one of these fails closed with `type_unknown`.
4. **Assignment compatibility, directional.** A field-type check passes when
   the concrete field type is assignable **to** the constraint's field type
   (source to sink: the generic body projects the field and passes the value
   into positions typed by the constraint type). Compatibility follows the
   type catalog's rules, including path-refinement narrowing — a
   caller-owned refined `defpath` satisfies a base path-family constraint
   over the same root. Implementation status: the landed check
   (`parametric_constraints.py`) uses assignment compatibility, including
   the refined-path case required by Tranche 2 consumer drain contexts.
5. **Owned spellings only.** Consuming docs and fixtures use exactly these
   forms. `has-variant`, `has-union-variants`, `T = SomeType`,
   `T satisfies Schema`, and trait aliases are not first-tranche surface.

### Subset Semantics (adjudicated)

The retired Python validators for `backlog-drain` enforced exact variant field
sets (`EMPTY` with exactly no fields, `BLOCKED` with exactly `reason`). That
exactness is intentionally **not** ported:

- the generic body only projects fields it has proof for, so extra caller
  fields cannot be read accidentally;
- caller-surface obligations (what a caller may publish or expose) are owned
  by the caller's own `:publish` contracts and shared validation, not by the
  stdlib definition's parameter constraints;
- exactness in the constraint language would make every caller union addition
  a breaking change against stdlib definitions that never read the new field.

One exception to that growth story: under `has-shared-union-field`, adding a
variant that lacks the shared field breaks the constraint — abruptly and
correctly, since the granted branch-free projection would otherwise be
unsound. Union-evolution guidance must not read subset semantics as "adding
variants is always non-breaking."

**Constraint-referenced names are frozen vocabulary.** Every variant and
field name a stdlib `:where` clause mentions (`EMPTY`/`SELECTED`/`GAP`/
`BLOCKED`, `selection`, `gap`, `reason`, `summary-path`, `blocker-class`, …)
is public contract a caller cannot rename — even though the definitions live
in the caller's own types. Subset semantics makes additions safe; it does
nothing for renames. Structural matching here is by-name, with no mapping or
renaming layer (see Deferred Extensions, generic type definitions).

If a future migration demonstrates a concrete need for exact-shape proof, the
extension is a new constraint form (e.g. `has-exact-union-variant`) proposed
against this document with the demonstrating fixture attached. Exactness must
not survive as Python-side validation for any migrated form.

### Deferred Extensions (with triggers)

- **Generic type definitions** (parameterized records/unions, e.g. a
  stdlib-owned `Selection[SelPayloadT GapPayloadT]` type constructor):
  rejected for the current tranches. Genericity is `defproc`-only; no
  type-constructor machinery exists (`type_env.py` scopes type parameters to
  procedure signatures only). Rationale: structural constraints let
  pre-existing caller-owned types satisfy a generic retroactively, while
  type constructors would force callers onto stdlib-owned nominal types and
  add real type-constructor machinery. Cost accepted knowingly: each drain
  caller restates its selection union structurally, and variant names
  (`EMPTY`/`SELECTED`/`GAP`/`BLOCKED`) are by-name stdlib contract
  vocabulary with no renaming or mapping. Trigger for revisiting: a second
  migration-destined form whose callers must each restate a stdlib-shaped
  union of three or more variants.
- **Explicit type application** (and return-type-driven inference): no
  escape hatch exists for binding a type parameter that inference cannot
  reach; return-only type parameters are inexpressible by construction
  (Core Model, definition-site coverage). Trigger: the first generic
  definition whose natural signature carries a type parameter appearing
  only in return position.
- **Trait aliases** (`deftrait` bundling constraint sets): deferred until at
  least three generic definitions share a substantially identical constraint
  block. Trait aliases must expand to the owned forms above, not introduce a
  second constraint language.
- **Exact-shape constraints**: trigger as described under Subset Semantics.
- **Authored generic `defworkflow`**: deferred; private/generated workflows
  remain lowering targets for specialized `defproc` bodies. Any future authored
  surface is sugar over the same specialization substrate.
- **Pre-instantiation generic-body checking**: deferred follow-on diagnostics
  work; the tranche contract is instantiate-then-typecheck. Trigger for
  revisiting: generic stdlib definitions or call-site count grows enough that
  post-instantiation diagnostics measurably degrade authoring (see
  Diagnostics Contract).
- **`has-shared-union-field` against `:forall`-typed fields**: the
  multi-variant shared-field resolution path is untested against
  type-parameter-named field types.

## Specialization Pipeline

The single normative pipeline (consuming docs reference, never restate):

```text
resolve concrete call-site types (parameters + ProcRef signatures)
  -> check structural constraints against resolved concrete types
  -> instantiate a monomorphic helper (substitute type parameters)
  -> typecheck the instantiated helper
  -> lower through ordinary Core AST and shared validation
```

Specialization identity includes: source module and definition name; source
definition digest; concrete type argument identities; compile-time `ProcRef`
identities; language/compiler version; target DSL version; generated-name
schema version. Equivalent call sites may share a specialization only when
identity matches and source-map/generated-path obligations are preserved.

Generated helper names are implementation details. Source maps and debug
projection must identify the authored generic definition, the call site, the
instantiation arguments, and generated nodes.

**Checkpoint identity across migration is a proof obligation, not a given.**
Resume lookup keys on `workflow_name` + `checkpoint_id`
(`lexical_checkpoints.py`), and `derive_checkpoint_id` digests the program
point id, an executable identity (`wcc_node_id`/`wcc_scope_id` plus lowered
`step_id`), the lowering schema version, and the storage scope. The program
point's `origin_key` is itself `workflow::step_id::<lowered step id>`. None
of these inputs reference specialization cache keys or generated helper
names directly — but the wcc identities and lowered step ids are products of
the lowering route, so swapping a form's intrinsic lowerer for
generic-inline lowering changes checkpoint ids unless the generic route
deliberately reproduces the same generated-step identities or an explicit,
reviewed identity-migration step remaps persisted records. Every migration
of a form with persisted checkpoints must therefore demonstrate identity
preservation by compiled-artifact comparison (the lexical checkpoint points
of consuming workflows before and after the route swap), or land a reviewed
remap. This obligation appears as an explicit Tranche 2 prerequisite.

## Union Proof

Structural constraints do not weaken variant proof:

- a `match` on a constrained union parameter establishes selected-variant
  proof; variant-specific fields are available only inside proof-bearing
  branches;
- `has-shared-union-field` grants branch-free projection of exactly that
  field;
- final projections may use only values materialized by the chosen branch or
  loop-frame outputs;
- an output bundle containing a discriminant is not a proof surface unless a
  validator/projection step creates variant-proof-compatible state.

After specialization the proof model is identical to proof over ordinary
concrete unions.

## Effects of Generic Definitions

A generic definition's declared effects cover its **body's direct effects
only**. Hook effects belong to the resolved procedures the caller passes;
they are not folded into the generic's declared or specialized summaries
(specialization copies `direct_effect_summary`/`transitive_effect_summary`
verbatim from the definition — `procedure_specialization.py`).

The mechanism that keeps effect visibility and census truthful anyway is
**inline lowering**: specialized procedures lower with
`resolved_lowering_mode = INLINE`, so the resolved hooks' concrete
provider/command calls surface structurally in the lowered artifact, and
census, effect visibility, and parity gates see reality rather than
summaries. This is normative, not incidental: effectful generic definitions
are inline-lowered, and any future non-inline lowering mode for generics
must add an explicit effect-summary join (folding resolved hook summaries
into the specialization) before it is admissible. `std/phase.orc`
`review-revise-loop-proc` (`:lowering inline`) is the shipped precedent.

## Interaction With Macros and ProcRef

Macros remain syntax expansion and may provide ergonomic call surfaces
(default seeds, argument shaping) that expand to calls of generic
definitions. Macros must not own semantic control flow, introduce hidden
effects, bypass shared validation, or lose source-map provenance.

`ProcRef` values remain compile-time references to named `defproc`
definitions. Generic definitions accept `ProcRef` parameters whose signatures
mention type parameters; those signatures are ordinary parameter types checked
after type-argument resolution, and they are the primary binding source for
type parameters that do not appear in first-order parameter positions.

**`ProcRef` signature matching is invariant.** Parameter and return positions
both require semantic type equality (`type_refs_compatible` in
`procedure_refs.py`); there is no contravariant-parameter/covariant-return
subtyping. This is a decision, not an accident of implementation: `ProcRef`
signatures are a primary inference source, and invariance keeps
type-argument binding deterministic and order-independent.

**Generic definitions calling generic definitions.** Under
instantiate-then-typecheck, a generic body's call to another generic
resolves while typechecking the already-monomorphic specialized helper, so
nested instantiation needs no additional inference machinery; recursive
specialization is rejected (`parametric_specialization_cycle`, landed in
`compiler.py`). No shipped generic exercises nesting yet: any migration
whose generic body calls a generic helper must extend the Tranche 2
prerequisite-1 fixture with a nested-instantiation case first. The Tranche 2
flagship body does not need this — it calls only monomorphic terminal
helpers.

Before runtime: all type parameters concrete; all hooks resolved to concrete
procedures; provider/prompt externs resolved inside the selected procedures;
no runtime state carries a `ProcRef`, provider ref, prompt ref, or type
parameter.

## Diagnostics Contract

The landed constraint-failure path sets the bar: the caller's span
(file:line:column), the diagnostic code, the rendered failing clause, the
inferred concrete type, a mismatch detail ("has type A instead of B"), and a
note carrying the definition-side declaration location
(`parametric_constraints.py`). Every parametric failure path must meet that
anatomy — the fix must be derivable from the message alone, without
re-reading either source file. A representative rendered failure (message
and note shapes verbatim from the implementation; span attaches to the
caller's call site):

```text
parametric_constraint_unsatisfied:
procedure `std/drain/backlog-drain-proc` requires
`(SelectionT has-union-variant SELECTED (selection SelPayloadT))` for
`SelectionT`, but the inferred concrete type `MySelection` does not satisfy
it: variant `SELECTED` field `selection` has type `MyOtherPayload` instead
of `SelPayloadT`
note: constraint declared at .../std/drain.orc:<line>:<column>
```

Constraint and specialization failures are compile-time and must name:

1. the generic definition (module-qualified) and its source span;
2. the call site (module-qualified) and its source span;
3. for constraint failures: the failing `:where` clause and the concrete type
   that failed it;
4. for inference failures: the type parameter that could not be bound;
5. for hook signature mismatches: the expected and actual `ProcRef`
   signatures and the first mismatching position. (Implemented in
   `procedure_refs.py`; messages preserve the `does not match` prefix while
   rendering expected/actual signatures and the first mismatch.)

When a call site fails multiple `:where` clauses, **all failing clauses are
reported together**, not just the first. (Implemented by accumulating
clause-scoped parametric diagnostics at the call site.)

Diagnostic codes, landed (verified 2026-07-06 checkout):
`procedure_type_param_clause_invalid`, `procedure_type_param_duplicate`,
`procedure_type_param_unknown`, `procedure_type_param_unbindable`,
`parametric_constraint_malformed`, `parametric_constraint_unknown`,
`parametric_constraint_unsatisfied`, `parametric_type_binding_unresolved`,
`parametric_type_binding_ambiguous`, `parametric_capability_undeclared`,
`parametric_specialization_cycle`, `loop_state_unresolved_type_parameter`.

Reserved (contract obligations without dedicated codes yet): specialization
identity collision; unsupported parametric boundary type. Runtime leakage of
type parameters and `ProcRef` values is enforced by the existing boundary
validation surfaces rather than parametric-specific codes.

A regression fixture must assert points 1–3 on at least one failing
constraint (not merely that compilation fails), plus one hook signature
mismatch asserting point 5, plus one typecheck failure **inside an
instantiated body** asserting the call site survives into the rendered
diagnostics — the specialization request threads `origin_span`
(`specialization_typecheck.py`) and specialized-body diagnostics render an
`instantiated from ...` note. These are the guards against
instantiate-then-typecheck degrading into errors that point inside
substituted bodies.

## Form Classification and Migration Policy

Compiler-known stdlib forms are classified once and recorded in the form
registry taxonomy:

**Permanent effect primitives** — the forms `.orc` bodies bottom out in.
They encapsulate runtime effects or compiler-generated state that has no
meaningful `.orc` expression, and they are not migration debt:
`resource-transition`, `materialize-view`, `resume-or-start`,
`run-provider-phase`, `produce-one-of`, and generated-seed intrinsics.

**Migration-destined forms** — forms whose semantics are workflow control
flow and typing that the language can express: `backlog-drain` /
`backlog-drain-callable-boundary`, `with-phase` / `phase-scope` composition
surfaces, and any future form added as a temporary bridge. `review-revise-loop`
and `finalize-selected-item` have already migrated and serve as the reference
precedents.

**Per-form migration test.** A migration-destined form migrates when all of:

1. its `.orc` expression (generic definition body plus any vocabulary delta)
   is demonstrably smaller and clearer than its intrinsic implementation;
2. the migration retires the form's name-keyed typechecking, lowering, and
   bespoke specialization paths, leaving at most registry/contract residue;
3. behavior parity is machine-checked (existing parity/fixture gates for the
   form's consumers pass unchanged, or with reviewed contract deltas);
4. checkpoint/resume identity for existing runs of consuming workflows is
   preserved.

The registry classification replaces the `TEMP_COMPILER_INTRINSIC` framing:
"temporary" applies only to migration-destined forms, and permanent
primitives stop carrying an implied rescue obligation.

## Tranche 2: backlog-drain Migration (flagship)

Target: author the drain loop as a generic `defproc` in `std/drain.orc` and
retire the intrinsic.

Signature shape (normative for the migration; body elided):

```lisp
(defproc backlog-drain-proc
  :forall (CtxT SelectionT SelPayloadT GapPayloadT RunResultT GapResultT)
  ((ctx CtxT)
   (selector    ProcRef[(CtxT) -> SelectionT])
   (run-item    ProcRef[(std/context/ItemCtx SelPayloadT) -> RunResultT])
   (gap-drafter ProcRef[(CtxT GapPayloadT) -> GapResultT])
   (max-iterations Int))
  :where ((CtxT is-record)
          (CtxT has-field run std/context/RunCtx)
          (CtxT has-field state-root Path.state-root)
          (CtxT has-field manifest Path.state-root)
          (CtxT has-field ledger Path.state-root)
          (SelectionT is-union)
          (SelectionT has-union-variant EMPTY)
          (SelectionT has-union-variant SELECTED (selection SelPayloadT))
          (SelectionT has-union-variant GAP (gap GapPayloadT))
          (SelectionT has-union-variant BLOCKED (reason String))
          (SelPayloadT is-record)
          (SelPayloadT has-field item-id String)
          (SelPayloadT has-field item-state-root Path.state-root)
          (GapPayloadT is-record)
          (RunResultT has-union-variant CONTINUE (summary-path WorkReport))
          (RunResultT has-union-variant BLOCKED
            (summary-path WorkReport) (blocker-class BlockerClass))
          (GapResultT has-union-variant CONTINUE)
          (GapResultT has-union-variant BLOCKED
            (progress-report-path WorkReport) (blocker-class BlockerClass)))
  -> std/drain/DrainLoopTerminal
  ...)
```

The `RunResultT` clauses match `std/resource` `SelectedItemResult`
(`CONTINUE (summary-path)`, `BLOCKED (summary-path blocker-class)`); the
`GapResultT` clauses match `std/drain` `GapResult` — the two field
vocabularies differ deliberately and must not be conflated. The two
`SelPayloadT has-field` clauses are the G2 amendment raised by the
backlog-drain generic migration plan
(`docs/plans/2026-07-06-backlog-drain-generic-migration-plan.md`, Task 4
Step 1): the generic body projects exactly the selection-payload fields the
intrinsic reads when building the item context —
`selection.item-id` and `selection.item-state-root`
(`lowering/phase_drain.py`, `_phase_stdlib_lower_backlog_drain_impl`,
`item_ctx_value` construction). The ctx
path-field clauses name base path families; consumer contexts satisfy them
through rule 4 assignment compatibility (e.g. `DesignDeltaDrainCtx.manifest`
is the consumer-refined `StateFileExisting`, which narrows
`Path.state-root`). The intrinsic's current ctx check
(`ensure_drain_context_type`) is likewise refinement-tolerant ("path field
under `state`"), so rule 4 — not strict equality — is what preserves
"callers do not change."

The `run-item` first parameter is the concrete `std/context/ItemCtx`; the
production consumer's hook already takes exactly that type. If parity
(prerequisite 5) surfaces a consumer whose hook takes a structurally
conforming but distinct item-context record — which the intrinsic accepts
today — the parameter generalizes to an `ItemCtxT` with `has-field`
constraints rather than forcing that caller to change.

The existing `backlog-drain` macro re-targets from the intrinsic to this proc;
callers do not change. Concretely, the caller-facing compatibility contract
is the macro keyword surface — `(backlog-drain <name> :ctx … :selector …
:run-item … :gap-drafter … :max-iterations …)` — which is **frozen** across
the migration: existing call sites remain byte-stable. The
`SELECTED (selection SelPayloadT)` clause carries the cross-hook payload
contract that the intrinsic's Python validators enforce today; the
exact-field checks in those validators are dropped per Subset Semantics.

Prerequisites, in order:

1. Minimal fixture proving the two landed constraint capabilities end to end
   — constraint satisfaction, constraint failure diagnostics, and
   specialization for each: (a) type-parameter constraint field types
   (Constraint Vocabulary rule 3); (b) directional assignment compatibility
   for constraint field types, including refined-path narrowing and
   refinement survival through substitution (rule 4). These feasibility
   prerequisites are implemented and covered by focused fixtures.
2. Diagnostics regression fixture (Diagnostics Contract), including
   report-all constraint failures and the definition-site coverage check
   (implemented).
3. Authored loop body in `std/drain.orc` using existing terminal helpers
   (`finalize-drain-terminal`, `consume-drain-terminal-effects`).
4. Checkpoint-identity preservation demonstrated by compiled-artifact
   comparison: the lexical checkpoint points (checkpoint ids) of consuming
   workflows are unchanged across the intrinsic-to-generic route swap, or an
   explicit reviewed identity-migration step remaps persisted records (see
   Specialization Pipeline). This is the riskiest item in the migration and
   must not be discovered downstream of retirement.
5. Parity: existing drain consumers (`lisp_frontend_design_delta/drain.orc`
   and fixture families) compile and pass their existing gates against the
   generic route; census/boundary/provider-metadata obligations move to
   shared validation surfaces, not into the generic body.
6. Retirement: the phase-drain lowerer, drain-terminal helper module's
   intrinsic-only paths, the form-specific monomorphizer, and the
   name-keyed validators (including the dead shadowed copies in
   `typecheck_dispatch.py`, which may be deleted immediately and
   independently of this tranche).

Current status (2026-07-12): prerequisites 3–6 are landed. The authored
`std/drain` generic body runs on the ordinary imported/specialized/WCC route,
the reviewed checkpoint-identity remap is recorded, and consumer parity plus
shared obligation relocation (including the F5 parent-owned inline-route
contract) are green. Phase 2 retired the intrinsic lowering, form-specific
specialization, AST/typecheck dispatch, and name-keyed validators, preserved
only the sanctioned registry/contract/output-shaping residue, and recorded
fresh non-regressive parity. The separately bounded Design Delta
primary-promotion handoff and independent joint proof are recorded in
`docs/plans/2026-07-07-drain-migration-g8-retirement.md`; Gate P3 is satisfied.
The current selector is drain Phase 3 Task 3.1. Task 3.2+, Phase 4, typed result
guidance, and YAML archive remain later work.

Expected residue on the order of the review loop's (registry entry, stdlib
contract, output-contract shaping). Residue materially above that is a signal
to stop and reassess against the per-form migration test rather than push
through.

## Acceptance Checks

- Generic definitions parse, constraint-check, specialize, and lower through
  the single pipeline with no consumer-name knowledge in the machinery.
- Constraint field types may be `:forall` parameters, with
  bound-parameter-comparison semantics and the definition-site coverage
  error.
- Constraint field-type checks are directional assignment compatibility: a
  refined-path field satisfies a base path-family constraint over the same
  root, and refinements survive substitution into specialized bodies.
- Repeat type-parameter bindings require exact semantic agreement;
  conflicting bindings fail with `parametric_type_binding_ambiguous`.
- Effectful generic definitions lower inline; census and effect-visibility
  surfaces for a consuming workflow are equivalent to those of the
  hand-monomorphized program (no hook effect hidden behind a copied
  summary).
- Subset semantics: a caller union with additional variants/fields satisfies
  the corresponding constraints; no exact-shape checking exists in Python for
  migrated forms.
- Diagnostics fixture asserts definition + call site + failing clause, one
  hook-mismatch rendering, and call-site anchoring of one
  instantiated-body failure.
- Every stdlib generic definition has a minimal-caller fixture whose types
  provide exactly the declared constraints and nothing more. This is the
  mechanical enforcement of the Non-Goals claim that a generic's
  requirements are exactly its declared clauses: an undeclared-capability
  use fails at stdlib-edit time, not at the first unlucky consumer.
  (`generic_stdlib_composition` half-plays this role today, but nothing
  requires minimality, so drift can hide behind generous fixture types.)
- Checkpoint/resume identity for consuming workflows is unchanged across
  intrinsic-to-generic migration of a form.
- Form-registry taxonomy distinguishes permanent effect primitives from
  migration-destined forms; no form is labeled temporary without a migration
  destiny.
- `backlog-drain` compiles and passes consumer gates via the generic route
  with no compiler branches keyed to its name.
- Lowered artifacts contain no type parameters, runtime type values, or
  `ProcRef` values.

## Relationship To Other Docs

- Supersedes `workflow_lisp_compile_time_parametric_specialization.md` and
  `workflow_lisp_structural_parametric_constraints.md`; those documents remain
  in-tree as historical records with supersession notices and must not be
  extended.
- `workflow_lisp_review_revise_stdlib_parametric_integration.md` continues to
  own the review/revise schemas (`ReviewFindings.v1` envelope,
  `ReviewDecision`, `ReviewLoopResult`) and their validation obligations;
  nothing here redefines them.
- `workflow_lisp_type_catalog.md` owns type-to-contract mapping and
  assignment-compatibility rules consumed by Constraint Vocabulary rule 4.
- `workflow_lisp_runtime_native_drain_authoring.md` (with
  `workflow_lisp_shared_owner_lane_prerequisites.md`) owns the concrete
  selector/run-item/gap-drafter hook shape contracts and the drain's runtime
  behavior. This document owns only the parameterized signature and
  constraint vocabulary that Tranche 2 layers over those shapes; when
  Tranche 2 lands, the concrete shapes remain owned there, and a conflict
  between the concrete contracts and the flagship signature is resolved
  against the drain-authoring doc (the signature adapts, not the shapes).
- The frontend specification remains the parent language contract; this
  document is a scoped delta to its type-system surface.
