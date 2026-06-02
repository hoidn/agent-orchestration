# Workflow Lisp Compile-Time Parametric Specialization

Status: draft design
Kind: Workflow Lisp language design / implementation architecture
Created: 2026-06-02

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_macro_surface_contract.md`
- `docs/design/workflow_lisp_proc_refs_partial_application.md`
- `docs/plans/2026-06-02-workflow-lisp-generic-orc-expansion-refactor.md`

## Purpose

This design clarifies a future Workflow Lisp type-system direction: compile-time
parametric `.orc` definitions with concrete specialization.

The immediate pressure comes from `review-revise-loop`. The loop should be
ordinary `.orc` code, but the current migration slice needs a thin macro or
equivalent specialization layer because imported `defproc` definitions are
monomorphic and caller workflows pass distinct record and union shapes.

That macro bridge should not become the long-term model. The principled model
is a generic `.orc` definition that is checked once against explicit
constraints, then instantiated into a monomorphic helper for each concrete call
site before Core AST lowering.

## Decision

Adopt compile-time parametric specialization as the long-term direction for
reusable `.orc` definitions.

Do not adopt Julia-style runtime multiple dispatch, runtime type objects,
runtime procedure values, or open-ended method tables. The useful lesson from
Julia is concrete specialization of generic source, not dynamic dispatch at
workflow runtime.

In Workflow Lisp terms:

```text
generic .orc definition
  -> infer concrete call-site types
  -> check explicit shape/trait constraints
  -> instantiate monomorphic helper/private workflow
  -> typecheck the instantiated AST
  -> lower ordinary Core AST
```

Executable workflow state must not contain unresolved type parameters,
procedure type values, provider refs, prompt refs, or runtime-dispatched method
choices.

## Non-Goals

- No runtime multiple dispatch.
- No runtime closures.
- No runtime-transported procedure, provider, prompt, or type values.
- No implicit broad type inference as a workflow-runtime contract.
- No weakening of effect visibility, source maps, structured result validation,
  or migration parity gates.
- No requirement to implement this before the current review-loop rescue can
  complete.

## Motivation

Workflow Lisp already has reusable procedures, workflow refs, procedure refs,
macro expansion, typed records/unions, and generic-looking library goals. The
current weak point is reusable effectful code over caller-specific structured
types.

For example, a review loop should not need one hand-written implementation for
each caller-specific `Completed` and `Inputs` record. It also should not rely on
a Python compiler branch that knows `review-revise-loop` by name.

A compile-time parametric model lets authors write one definition:

```lisp
(defproc review-revise-loop
  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecisionT])
   (fix ProcRef[(CompletedT InputsT ReviewFindingsT) -> CompletedT]))
  :where ((CompletedT HasReviewArtifacts)
          (InputsT HasReviewInputs)
          (ReviewDecisionT ReviewDecisionLike)
          (ReviewFindingsT ReviewFindingsLike))
  -> ReviewLoopResultT
  ...)
```

The compiler then specializes that definition for the concrete caller:

```text
review-revise-loop[ImplementationDraft, ImplementationInputs, ...]
  -> generated/private monomorphic helper
```

The lowered runtime still sees ordinary provider steps, command steps,
`match`, loop state, output bundles, and workflow artifacts.

## Type Parameters

Type parameters are compile-time-only names bound by a generic `defproc` or
`defworkflow`.

Proposed syntax:

```lisp
(defproc name
  :forall (T U ResultT)
  ((value T)
   (next ProcRef[(T) -> U]))
  :where ((T SomeConstraint)
          (U OtherConstraint))
  -> ResultT
  body)
```

Syntax status: proposed.

Semantic contract:

- type parameters are resolved before executable IR;
- each concrete instantiation is monomorphic;
- type parameters may appear in parameter types, return types, `ProcRef`
  signatures, record/union constructors, and local type annotations;
- unresolved type parameters are illegal in lowered Core AST, Semantic IR,
  Executable IR, runtime state, artifact contracts, and debug YAML intended for
  execution.

## Constraints

Constraints describe the compile-time capabilities a generic definition needs
from a type parameter. They should be explicit and small.

Initial constraint forms:

- **Exact type constraint:** `T = SomeRecord`
- **Record-field constraint:** `T has-field checks_report ChecksReportPath`
- **Union-variant constraint:** `T has-variant APPROVED (...)`
- **Path/schema constraint:** `T satisfies ReviewFindingsV1`
- **Procedure signature constraint:** `P ProcRef[(A B) -> R]`
- **Trait alias:** `T HasReviewArtifacts`, where the trait expands to a set of
  structural constraints.

Trait aliases are compile-time contracts, not runtime interfaces.

Example:

```lisp
(deftrait HasReviewArtifacts (T)
  (has-field T checks_report ChecksReportPath)
  (has-field T review_report ReviewReportPath))
```

Trait status: proposed. If traits are too much for the first implementation,
the same model can start with inline structural constraints and add trait
aliases later.

## Specialization

Specialization creates a generated monomorphic definition for one concrete set
of type arguments and compile-time refs.

Specialization identity must include:

- source module and definition name;
- source definition digest;
- concrete type argument identities;
- compile-time `ProcRef` identities;
- relevant compiler/language version;
- target DSL version;
- generated-name schema version.

Two equivalent call sites may share a specialization only if they have the same
identity and doing so preserves source-map and generated-path obligations.
Otherwise the compiler should generate per-call-site helpers.

Generated helper names are implementation details. Source maps and debug
projection must show the authored generic definition, the call site, and the
instantiation arguments.

## Interaction With Macros

Macros remain syntax expansion. Parametric specialization is type-aware
definition instantiation.

Current macro bridge:

```text
thin macro
  -> emits monomorphic helper/call for caller-specific shapes
```

Long-term parametric route:

```text
generic defproc/defworkflow
  -> compiler instantiates monomorphic helper from type parameters
```

The long-term route is preferred because it keeps reusable behavior in
effectful `.orc` definitions instead of macro templates. Macros may still
provide ergonomic surface syntax, but they should expand to calls of generic
definitions rather than owning semantic control flow.

Macro-origin restrictions still apply:

- no hidden provider or command effects introduced only by macro templates;
- no macro-owned runtime semantics;
- no bypass around shared validation;
- no loss of source-map provenance.

## Interaction With Procedure References

`ProcRef` values remain compile-time references to named `defproc`
definitions. A parametric procedure may accept `ProcRef` parameters whose
signatures mention type parameters.

Example:

```lisp
(defproc retry-until-approved
  :forall (StateT DecisionT)
  ((state StateT)
   (review ProcRef[(StateT) -> DecisionT])
   (fix ProcRef[(StateT DecisionT) -> StateT]))
  :where ((DecisionT ReviewDecisionLike))
  -> ReviewLoopResult
  ...)
```

Before runtime:

- `StateT` and `DecisionT` are concrete;
- `review` and `fix` point to concrete selected procedures;
- provider and prompt externs used by those procedures are resolved inside the
  selected procedures;
- no runtime state carries a `ProcRef`, provider ref, prompt ref, or type
  parameter.

## Union Proof

Parametric specialization must preserve variant proof. A generic definition may
route on a union parameter with `match`, but variant-specific fields are
available only inside proof-bearing branches.

This is similar in spirit to union splitting, but it is compile-time workflow
proof, not runtime method dispatch.

Required behavior:

- branch-local field access requires selected-variant proof;
- final projection cannot expose fields that were not materialized by the
  selected branch or loop frame;
- output bundles cannot be treated as variant-proof surfaces unless a
  validator/projection step creates equivalent proof.

## Failure Modes

New diagnostics should be specific and compile-time:

- unresolved type parameter;
- unsatisfied structural constraint;
- ambiguous type argument inference;
- unsupported parametric boundary type;
- specialization cycle;
- specialization identity collision;
- runtime-leaked type parameter;
- runtime-leaked `ProcRef`;
- variant field access without proof.

Shared validation remains the authority for generated executable workflow
contracts after specialization.

## Adoption Plan

This is not required for the current key-migration rescue.

Recommended sequence:

1. Keep the current migration slice focused on generic `.orc` expansion and the
   thin macro or equivalent monomorphic helper bridge.
2. Add a design-gap/backlog item for compile-time parametric `.orc`
   specialization.
3. Implement the smallest useful syntax: `:forall` plus inline structural
   constraints for `defproc`.
4. Add one pure `defproc` fixture using a type parameter.
5. Add one effectful `defproc` fixture using a type parameter and `ProcRef`.
6. Add one union-proof fixture where a generic procedure matches on a
   parameterized union.
7. Replace the review-loop macro bridge with a parametric definition only after
   those generic fixtures pass.

## Acceptance Checks

- Generic `.orc` definitions parse and typecheck with explicit type parameters.
- Specialization produces monomorphic helper definitions before Core AST
  lowering.
- Lowered workflow artifacts contain no type parameters or runtime type values.
- Source maps identify generic definition, call site, specialization arguments,
  and generated nodes.
- `ProcRef` specialization remains compile-time-only.
- Unsatisfied constraints fail before runtime.
- Variant-specific fields remain proof-gated after specialization.
- A non-review-loop fixture proves the machinery is generic.
- A review-loop fixture uses the same machinery without compiler recognition of
  the literal `review-revise-loop` name.

## Relationship To Current Migration Architecture

The current key-migration architecture intentionally rejects requiring
parametric imported `defproc` support in the active rescue slice. That remains
correct.

This design names the follow-on language feature that should replace the macro
specialization bridge once the immediate migration is stable.
