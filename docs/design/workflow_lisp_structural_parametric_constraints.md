# Workflow Lisp Structural Parametric Constraints

Status: draft design
Kind: Workflow Lisp type-system design direction
Created: 2026-06-02

Related docs:

- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`
- `docs/plans/LISP-MIGRATION-PARITY-DRAIN/design-gaps/workflow-lisp-review-loop-generic-effectful-composition/implementation_architecture.md`

## Purpose

This design clarifies the type-system direction needed to retire
`review-revise-loop` compiler-special validation without replacing it with
another macro-specific branch.

The broader parametric-specialization design says generic `.orc` definitions
should specialize into monomorphic helpers before lowering. This document
narrows the missing type feature: a generic definition must be able to require
that a caller-provided record or union has particular fields, variants, and
proof behavior.

This document is also the sole owner of the first-tranche structural-constraint
surface. Other design docs may consume these forms, but they should not invent
parallel spellings or additional first-tranche constraint kinds.

The exact first-tranche review/revise stdlib schemas are not owned here.
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
owns the concrete `ReviewFindings` carrier, the minimum `ReviewFindings.v1`
artifact envelope, and the exact `ReviewDecision` / `ReviewLoopResult` names
and fields. This document owns only the constraint vocabulary used around those
types.

## Problem

`review-revise-loop` currently accepts a caller-owned `:returns` union. The
compiler needs to know that union has usable terminal variants such as
`APPROVED`, `BLOCKED`, and `EXHAUSTED`, and that those variants contain the
fields the generated loop projection needs.

Today that structural validation is encoded directly in Python for one stdlib
form. That is type-system work, but it is not represented as a reusable
type-system feature. The result is a compiler-special review-loop path in
`expressions.py`, `typecheck.py`, `compiler.py`, and `lowering.py`.

The reviewed first-tranche constraint set only proves subset-style shape facts
such as required fields or variants. That is enough to typecheck generic access
and proof-gated matching, but it is not enough by itself to construct arbitrary
caller-owned terminal variants with renamed or additional required fields.

## Decision

Add structural parametric constraints as the long-term type-system mechanism
for caller-specific records and unions.

The compiler may specialize generic definitions at compile time, but the
constraints that justify specialization should be declared in `.orc` source and
checked by the type system. Lowering should receive only concrete monomorphic
definitions after those checks pass. In the first tranche, that means
constraint-check concrete call-site types, instantiate a monomorphic helper,
and typecheck the instantiated helper before lowering. Pre-instantiation
generic-body checking is deferred follow-on work.

This model should apply to arbitrary `.orc` library definitions, not only
`review-revise-loop`.

## Core Model

Structural constraints describe what a type parameter must provide:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT)
  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (max Int))
  :where
    ((CompletedT is-record)
     (InputsT is-record))
  -> ReviewLoopResult
  ...)
```

Syntax status: proposed. The concrete spelling can change, but the semantic
contract is that caller-specific shapes are declared as structural constraints,
not hidden in form-specific compiler code.

For the first tranche, consuming docs should use one consistent authored shape:
`:forall`, the ordinary parameter list, `:where`, then the return type.

In the first tranche, `:where` binds only type parameters introduced by
`:forall`. It is not a mixed constraint surface for ordinary term parameters
such as `review` or `fix`.

The first stable structural-constraint surface attaches to generic `defproc`
definitions. A later authored generic `defworkflow` surface is deferred; any
private/generated workflow target in the meantime consumes already-specialized
monomorphic helpers rather than introducing a second generic constraint owner.

## Initial Constraint Forms

The first stable constraint set should be deliberately small:

- `T has-field name Type`
- `T has-union-variant VARIANT`
- `T has-union-variant VARIANT (field Type ...)`
- `T has-shared-union-field name Type`
- `T is-record`
- `T is-union`

These forms define the first stable structural proof surface. They do not add
exact-type equality, field renaming, constructor mapping, or any other rule
that would let a consuming doc claim direct construction of arbitrary
caller-owned terminal unions from subset-style evidence alone.

`T has-shared-union-field name Type` is part of that first stable surface only
with the following exact rule: `T` must resolve to a non-empty concrete union,
every declared variant of that union must declare field `name`, and each such
field type must be assignment-compatible with `Type`. The proof it grants is
limited to branch-free projection of `name` from a value of type `T`; it does
not prove which variant is present and does not permit construction of new
variant values.

First-tranche consumers should use exactly those spellings. The following are
explicitly deferred extensions rather than initial surface area:

- exact-type constraints such as `T = SomeRecord`;
- alternate union spellings such as `has-variant` or `has-union-variants`;
- schema shorthand such as `T satisfies SomeSchema`;
- trait aliases.

Trait aliases may come later:

```lisp
(deftrait ReviewLoopResultLike (T)
  (T has-union-variant APPROVED (...))
  (T has-union-variant BLOCKED (...))
  (T has-union-variant EXHAUSTED (...)))
```

The initial implementation can use inline constraints without adding traits.

## Typechecking Rules

For the first tranche, constraint checking operates on resolved concrete
call-site types and feeds instantiate-then-typecheck specialization rather than
a separate pre-instantiation generic-body checker.

Constraint checking happens before specialization is accepted:

- every type parameter resolves to one concrete type at each call site;
- record-field constraints are satisfied by declared record fields;
- union-variant constraints are satisfied by declared variant fields;
- shared-union-field constraints are satisfied only when every concrete union
  variant declares the named field;
- field types must be assignment-compatible with the constraint;
- shared-union-field access typechecks only for the constrained shared field;
- ordinary parameter typing checks `ProcRef[...]` parameters against their
  declared signatures after type parameters resolve;
- unsatisfied constraints fail at compile time with diagnostics pointing to the
  generic definition and the call site.

No unresolved type parameter may appear in Core AST, Semantic IR, Executable IR,
runtime state, artifact contracts, output bundles, or provider/command payloads.

## Variant Proof

Structural constraints do not weaken variant proof.

Inside a generic definition:

- a shared-union-field constraint allows branch-free projection only of that
  named field;
- a match on a constrained union parameter establishes selected-variant proof;
- variant-specific fields are available only inside proof-bearing branches;
- final projections may use only values materialized by the chosen branch or by
  loop-frame outputs;
- an `output_bundle` containing a discriminant is not a proof surface unless a
  validator/projection step creates variant-proof-compatible state.

After specialization, the proof model should look exactly like proof over an
ordinary concrete union.

## Specialization

Specialization instantiates the generic definition into a concrete helper before
ordinary lowering:

```text
generic definition + concrete type args + compile-time refs
  -> check structural constraints
  -> instantiate monomorphic helper
  -> typecheck instantiated helper
  -> lower ordinary expressions
```

That is the shared first-tranche pipeline consumed by the integration and
specialization docs. It preserves ordinary proof-gated union behavior in the
instantiated helper while avoiding new review-loop-specific compiler branches.

Specialization identity must include:

- source module and definition name;
- source definition digest;
- concrete type arguments;
- compile-time `ProcRef` identities;
- target DSL version;
- language/compiler version;
- generated-name schema version.

Source maps must identify the generic definition, call site, specialization
arguments, generated helpers, and generated path/write-root provenance.

Persisted checkpoint identity for generated loops is a separate shared-runtime
contract. Structural specialization may influence helper generation and source
maps, but resume lookup must stay keyed to the authored loop-step identity
selected by the semantic/executable bridge rather than to generated helper
names.

## Review Loop Application

For `review-revise-loop`, this design means the compiler should no longer need
a private function that knows the result contract by name.

Instead:

- the active parity tranche may keep a thin macro bridge, but the follow-on
  route replaces that bridge with a generic `std/phase.orc` review-loop
  definition;
- the first stable loop returns an exact stdlib-owned terminal protocol;
- `ReviewDecision` means the exact stdlib-owned union from the integration doc:
  `APPROVE`, `REVISE`, and `BLOCKED`, with blocked carrying
  `blocker_class BlockerClass`;
- `ReviewFindings` means the exact validated carrier from the integration doc:
  `schema_version == "ReviewFindings.v1"`, `items_path` validated under
  `artifacts/work` as the owner-doc minimum non-pointer object with top-level
  `items` member, validation before publication, and validation again before
  resume-time `fix` consumption;
- workflow-specific finding-item payload fields remain outside this structural
  constraint surface and must be owned by the producing/consuming review
  contract if stricter guarantees are needed;
- review and fix hooks are compile-time `ProcRef` parameters;
- the first stable `fix` hook is findings-only:
  `ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]`;
- the compiler specializes the generic definition for the caller's concrete
  `CompletedT` and `InputsT`;
- lowering sees ordinary generated helpers, `loop/recur`, `provider-result`,
  `command-result`, `match`, records, unions, and projections.

The first stable terminal-union contract does not require the returned
`ReviewLoopResult` to embed `completed CompletedT`. The latest `CompletedT`
remains typed loop state and surrounding workflow authority. If a caller needs
to publish carried completed identity or workflow-specific terminal field
names, it should project that from surrounding typed state or carried artifact
refs in ordinary caller code rather than requiring the stdlib loop to
construct an arbitrary caller-owned terminal union.

This allows caller-specific result unions without encoding
`review-revise-loop` as a language primitive.

## Non-Goals

This design does not add:

- runtime type values;
- runtime multiple dispatch;
- runtime closures or runtime procedure values;
- provider refs or prompt refs in runtime state;
- implicit structural duck typing at workflow runtime;
- hidden command adapters, report parsing, or pointer-as-state compatibility.

It also does not require current migration-parity slices to stop consuming the
existing `review-revise-loop` specialization bridge.

## Adoption Plan

1. Keep the current review-loop bridge while migration parity work continues.
2. Add a tiny pure parametric `defproc` fixture with one field constraint.
3. Add a constrained union fixture proving both shared-union-field projection
   and match/projection proof survive specialization.
4. Add an effectful fixture with `ProcRef` parameters and provider/command
   effects.
5. Reimplement `review-revise-loop` over the generic mechanism after the active
   thin-macro parity bridge is stable or explicitly superseded.
6. Remove review-loop-specific compiler branches after parity fixtures pass.

## Acceptance Checks

- generic `.orc` definitions can declare structural record and union
  constraints;
- unsatisfied constraints fail before lowering;
- specialization emits monomorphic helpers with no runtime type values;
- variant-specific fields remain proof-gated after specialization;
- one non-review-loop fixture uses the same mechanism;
- first-tranche docs and fixtures use this document's owned spellings
  (`has-field`, `has-union-variant`, `has-shared-union-field`, `is-record`,
  `is-union`) rather than parallel aliases;
- `has-shared-union-field` is implemented with the owner-doc rule: every
  variant declares the field, the field type is assignment-compatible, and only
  that branch-free field access is implied;
- first-tranche consuming docs do not treat subset-style structural
  constraints as sufficient justification for arbitrary caller-owned terminal
  union construction;
- `review-revise-loop` can be expressed without compiler branches keyed to the
  literal `review-revise-loop` or `phase-review-loop` names.
