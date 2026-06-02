# Workflow Lisp Structural Parametric Constraints

Status: draft design
Kind: Workflow Lisp type-system design direction
Created: 2026-06-02

Related docs:

- `docs/design/workflow_lisp_compile_time_parametric_specialization.md`
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

## Problem

`review-revise-loop` currently accepts a caller-owned `:returns` union. The
compiler needs to know that union has usable terminal variants such as
`APPROVED`, `BLOCKED`, and `EXHAUSTED`, and that those variants contain the
fields the generated loop projection needs.

Today that structural validation is encoded directly in Python for one stdlib
form. That is type-system work, but it is not represented as a reusable
type-system feature. The result is a compiler-special review-loop path in
`expressions.py`, `typecheck.py`, `compiler.py`, and `lowering.py`.

## Decision

Add structural parametric constraints as the long-term type-system mechanism
for caller-specific records and unions.

The compiler may specialize generic definitions at compile time, but the
constraints that justify specialization should be declared in `.orc` source and
checked by the type system. Lowering should receive only concrete monomorphic
definitions after those checks pass.

This model should apply to arbitrary `.orc` library definitions, not only
`review-revise-loop`.

## Core Model

Structural constraints describe what a type parameter must provide:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT ResultT)
  :where
    ((ResultT has-union-variants
       (APPROVED
         (review_report ReviewReportPath)
         (findings ReviewFindings))
       (BLOCKED
         (blocker_class String)
         (findings ReviewFindings))
       (EXHAUSTED
         (last_review_report ReviewReportPath)
         (findings ReviewFindings)
         (reason String)))))
  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT])
   (max Int))
  -> ResultT
  ...)
```

Syntax status: proposed. The concrete spelling can change, but the semantic
contract is that caller-specific shapes are declared as structural constraints,
not hidden in form-specific compiler code.

## Initial Constraint Forms

The first useful constraint set should be deliberately small:

- `T has-field name Type`
- `T has-union-variant VARIANT`
- `T has-union-variant VARIANT (field Type ...)`
- `T has-shared-union-field name Type`
- `T is-record`
- `T is-union`
- `P ProcRef[(A B) -> R]`

Trait aliases may come later:

```lisp
(deftrait ReviewLoopResultLike (T)
  (T has-union-variant APPROVED (...))
  (T has-union-variant BLOCKED (...))
  (T has-union-variant EXHAUSTED (...)))
```

The initial implementation can use inline constraints without adding traits.

## Typechecking Rules

Constraint checking happens before specialization is accepted:

- every type parameter resolves to one concrete type at each call site;
- record-field constraints are satisfied by declared record fields;
- union-variant constraints are satisfied by declared variant fields;
- field types must be assignment-compatible with the constraint;
- `ProcRef` constraints resolve to compile-time procedure references only;
- unsatisfied constraints fail at compile time with diagnostics pointing to the
  generic definition and the call site.

No unresolved type parameter may appear in Core AST, Semantic IR, Executable IR,
runtime state, artifact contracts, output bundles, or provider/command payloads.

## Variant Proof

Structural constraints do not weaken variant proof.

Inside a generic definition:

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

## Review Loop Application

For `review-revise-loop`, this design means the compiler should no longer need
a private function that knows the result contract by name.

Instead:

- `std/phase.orc` declares a generic review-loop definition or thin macro that
  calls one;
- the result union requirement is expressed as structural constraints;
- review and fix hooks are compile-time `ProcRef` parameters;
- the compiler specializes the generic definition for the caller's concrete
  `CompletedT`, `InputsT`, and `ResultT`;
- lowering sees ordinary generated helpers, `loop/recur`, `provider-result`,
  `command-result`, `match`, records, unions, and projections.

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
3. Add a constrained union fixture proving match/projection proof survives
   specialization.
4. Add an effectful fixture with `ProcRef` parameters and provider/command
   effects.
5. Reimplement `review-revise-loop` over the generic mechanism.
6. Remove review-loop-specific compiler branches after parity fixtures pass.

## Acceptance Checks

- generic `.orc` definitions can declare structural record and union
  constraints;
- unsatisfied constraints fail before lowering;
- specialization emits monomorphic helpers with no runtime type values;
- variant-specific fields remain proof-gated after specialization;
- one non-review-loop fixture uses the same mechanism;
- `review-revise-loop` can be expressed without compiler branches keyed to the
  literal `review-revise-loop` or `phase-review-loop` names.
