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
  with `has-union-variant` constraints and proof-gated `match` on constrained
  parameters.
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
  errors inside bodies the caller did not write.)
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

Type arguments are inferred from concrete call-site parameter types, including
the signatures of `ProcRef` arguments. Constraints do not drive inference;
they are checked after all type parameters are bound (see Constraint
Vocabulary, rule 3).

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
   field type against the bound parameter for assignment compatibility. A
   constraint referencing an unbound parameter (one that appears in no
   parameter or `ProcRef` signature position) is a compile-time error
   (`ambiguous type argument inference`), not an inference source. This rule
   is how cross-parameter contracts are expressed — e.g. "the run-item hook's
   payload parameter is the same type as the selector's `SELECTED.selection`
   field."
4. **Assignment compatibility** for constraint field types follows the type
   catalog's rules, including path-refinement narrowing.
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

If a future migration demonstrates a concrete need for exact-shape proof, the
extension is a new constraint form (e.g. `has-exact-union-variant`) proposed
against this document with the demonstrating fixture attached. Exactness must
not survive as Python-side validation for any migrated form.

### Deferred Extensions (with triggers)

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

**Checkpoint identity is independent of specialization.** Persisted checkpoint
and resume identity keys on authored program points (lexical checkpoint
points and the authored loop-step identity chosen by the semantic/executable
bridge), never on generated helper names or specialization cache keys. This is
implemented today via lexical checkpoint identity over authored positions and
must remain true for every migrated form.

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

Before runtime: all type parameters concrete; all hooks resolved to concrete
procedures; provider/prompt externs resolved inside the selected procedures;
no runtime state carries a `ProcRef`, provider ref, prompt ref, or type
parameter.

## Diagnostics Contract

Constraint and specialization failures are compile-time and must name:

1. the generic definition (module-qualified) and its source span;
2. the call site (module-qualified) and its source span;
3. for constraint failures: the failing `:where` clause and the concrete type
   that failed it;
4. for inference failures: the type parameter that could not be bound.

Diagnostic codes: unresolved type parameter; unsatisfied structural
constraint; ambiguous type argument inference; unsupported parametric boundary
type; specialization cycle; specialization identity collision; runtime-leaked
type parameter; runtime-leaked `ProcRef`; variant field access without proof.

A regression fixture must assert points 1–3 on at least one failing
constraint (not merely that compilation fails). This is the guard against
instantiate-then-typecheck degrading into errors that point inside substituted
bodies.

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
          (CtxT has-field manifest StateFileExisting)
          (CtxT has-field ledger Path.state-root)
          (SelectionT is-union)
          (SelectionT has-union-variant EMPTY)
          (SelectionT has-union-variant SELECTED (selection SelPayloadT))
          (SelectionT has-union-variant GAP (gap GapPayloadT))
          (SelectionT has-union-variant BLOCKED (reason String))
          (SelPayloadT is-record)
          (GapPayloadT is-record)
          (RunResultT has-union-variant CONTINUE (summary-path WorkReport))
          (RunResultT has-union-variant BLOCKED
            (progress-report-path WorkReport) (blocker-class BlockerClass))
          (GapResultT has-union-variant CONTINUE)
          (GapResultT has-union-variant BLOCKED
            (progress-report-path WorkReport) (blocker-class BlockerClass)))
  -> std/drain/DrainLoopTerminal
  ...)
```

The existing `backlog-drain` macro re-targets from the intrinsic to this proc;
callers do not change. The `SELECTED (selection SelPayloadT)` clause carries
the cross-hook payload contract that the intrinsic's Python validators enforce
today; the exact-field checks in those validators are dropped per Subset
Semantics.

Prerequisites, in order:

1. Minimal fixture proving type-parameter constraint field types (Constraint
   Vocabulary rule 3) end to end: constraint satisfaction, constraint failure
   diagnostics, and specialization. This capability is currently a design
   claim, not a proven one — it is the open feasibility gap of this design and
   gates everything below.
2. Diagnostics regression fixture (Diagnostics Contract).
3. Authored loop body in `std/drain.orc` using existing terminal helpers
   (`finalize-drain-terminal`, `consume-drain-terminal-effects`).
4. Parity: existing drain consumers (`lisp_frontend_design_delta/drain.orc`
   and fixture families) compile and pass their existing gates against the
   generic route; census/boundary/provider-metadata obligations move to
   shared validation surfaces, not into the generic body.
5. Retirement: the phase-drain lowerer, drain-terminal helper module's
   intrinsic-only paths, the form-specific monomorphizer, and the
   name-keyed validators (including the dead shadowed copies in
   `typecheck_dispatch.py`, which may be deleted immediately and
   independently of this tranche).

Expected residue on the order of the review loop's (registry entry, stdlib
contract, output-contract shaping). Residue materially above that is a signal
to stop and reassess against the per-form migration test rather than push
through.

## Acceptance Checks

- Generic definitions parse, constraint-check, specialize, and lower through
  the single pipeline with no consumer-name knowledge in the machinery.
- Constraint field types may be `:forall` parameters, with
  bound-parameter-comparison semantics and the unbound-parameter error.
- Subset semantics: a caller union with additional variants/fields satisfies
  the corresponding constraints; no exact-shape checking exists in Python for
  migrated forms.
- Diagnostics fixture asserts definition + call site + failing clause.
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
- The frontend specification remains the parent language contract; this
  document is a scoped delta to its type-system surface.
