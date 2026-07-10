# Workflow Lisp Compile-Time Parametric Specialization

Status: superseded by `docs/design/workflow_lisp_parametric_type_system.md`
(2026-07-06); retained as a historical record, do not extend
Kind: Workflow Lisp language design / implementation architecture
Created: 2026-06-02

Related docs:

- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`
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
is a generic `.orc` definition with explicit constraints and compile-time
specialization. For the first implementation tranche, the accepted compiler
contract is concrete constraint checking plus instantiate-then-typecheck of the
monomorphic helper before Core AST lowering. Pre-instantiation generic-body
checking is deferred follow-on diagnostic work rather than a tranche-one gate.

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
  -> check explicit structural constraints
  -> instantiate monomorphic helper/private workflow
  -> typecheck the instantiated AST
  -> lower ordinary Core AST
```

Executable workflow state must not contain unresolved type parameters,
procedure type values, provider refs, prompt refs, or runtime-dispatched method
choices.

## First-Tranche Implementation Rule

This design distinguishes the long-term semantic direction from the first
compiler architecture that lands it.

The long-term direction is reusable generic `.orc` source with explicit
constraints and no runtime-dispatched type or procedure values. The first
implementation tranche does not require a separate proof that a generic body is
well-typed before instantiation. Instead it must:

```text
resolve concrete call-site types
  -> check explicit structural constraints against those concrete types
  -> instantiate a monomorphic helper/private workflow
  -> typecheck the instantiated helper
  -> lower through ordinary Core AST and shared validation
```

That shared pipeline is the authority consumed by
`workflow_lisp_review_revise_stdlib_parametric_integration.md` and
`workflow_lisp_structural_parametric_constraints.md`. If later work adds
pre-instantiation generic-body checking for better diagnostics or caching, that
is a follow-on extension and must not be described as the tranche-one contract.

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
  :forall (CompletedT InputsT)
  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]))
  :where
    ((CompletedT is-record)
     (InputsT is-record))
  -> ReviewLoopResult
  ...)
```

The compiler then specializes that definition for the concrete caller:

```text
review-revise-loop[ImplementationDraft, ImplementationInputs, ...]
  -> generated/private monomorphic helper
```

The lowered runtime still sees ordinary provider steps, command steps,
`match`, loop state, output bundles, and workflow artifacts.

For the long-term stable review/revise route, the authored semantic surface
should be an imported generic `defproc` in `std/phase.orc`. The active
migration-parity tranche still uses the accepted thin macro or equivalent
monomorphic-helper bridge and is not revised by this document. The first stable
generic `fix` hook is findings-only:
`ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]`. The loop should
return an exact stdlib-owned terminal protocol, and callers should project
workflow-specific terminal unions outside the loop using ordinary `match` with
refined match binders. Constructor `ProcRef` bridges or field-mapping
extensions are deferred, not parallel implementation targets.

The exact first-tranche `ReviewFindings` carrier, minimum
`ReviewFindings.v1` artifact envelope, and `ReviewDecision` /
`ReviewLoopResult` fields are owned by
`docs/design/workflow_lisp_review_revise_stdlib_parametric_integration.md`.
This document owns the compile-time machinery that specializes definitions using
those types; it does not define an alternate review-loop schema. In
particular, `ReviewFindings` means the exact owner-doc carrier:
`schema_version == "ReviewFindings.v1"`, `items_path` validated under
`artifacts/work` as the owner-doc minimum non-pointer object with top-level
`items` member, validation before publication to loop state, and validation
again before resume-time `fix` consumption. Workflow-specific finding-item
payload fields remain outside this compile-time specialization contract unless
another design or validator explicitly owns them.

## Type Parameters

Type parameters are compile-time-only names bound by a generic `defproc` in the
first tranche.

A future authored generic `defworkflow` surface is deferred. Private/generated
workflows may still be emitted after specialization, but they are lowering
targets for specialized `defproc` bodies rather than a second first-tranche
generic authoring surface.

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
For the first tranche, consuming docs should use exactly this clause order:
`:forall`, the ordinary parameter list, `:where`, then the return type.

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
from a type parameter. They should be explicit and small. The first-tranche
constraint vocabulary is owned by
`docs/design/workflow_lisp_structural_parametric_constraints.md`.

Initial constraint forms:

- **Record-field constraint:** `T has-field checks_report ChecksReportPath`
- **Union-variant constraint:** `T has-union-variant APPROVED (...)`
- **Shared-union-field constraint:** `T has-shared-union-field findings ReviewFindings`
- **Record/union kind constraints:** `T is-record`, `T is-union`

These forms prove structural capabilities, not arbitrary constructor mappings.
Consuming docs must not treat them as sufficient proof that a generic stdlib
definition can directly construct caller-owned terminal unions with renamed or
additional required fields.

For the first tranche, `has-shared-union-field` has one exact meaning from the
owner doc: every concrete union variant declares the named field with an
assignment-compatible type, which permits only branch-free projection of that
field. It does not establish variant proof and does not justify constructor
mapping into caller-owned terminal unions.

`ProcRef[...]` parameters whose signatures mention type parameters are checked
by ordinary parameter typing after type arguments resolve. In the first
tranche, `:where` does not bind ordinary term parameters.

Deferred follow-on extensions may add exact-type constraints, schema
shorthands, or trait aliases, but those are not part of the first stable
surface and should not appear as required first-tranche syntax in consuming
docs.

Example:

```lisp
(defproc carry-check-evidence
  :forall (ResultT)
  ((value ResultT))
  :where
    ((ResultT has-field checks_report ChecksReportPath)
     (ResultT has-field review_report ReviewReportPath))
  -> ResultT
  value)
```

If later ergonomics justify trait aliases, they should expand to the structural
forms owned by the structural-constraints design rather than inventing a second
constraint language.

## Specialization

Specialization creates a generated monomorphic definition for one concrete set
of type arguments and compile-time refs.

For the first tranche, specialization is accepted only after structural
constraints succeed on resolved concrete types, and the instantiated helper is
the surface that ordinary typechecking and lowering consume. The generic source
remains the semantic authoring surface, but pre-instantiation generic-body
checking is deferred.

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

Specialization identity is not itself the runtime resume key. Persisted
checkpoint identity for generated loops is owned by the shared
semantic/executable bridge and must remain anchored to the authored loop-step
identity chosen by the consuming design, not to generated helper names or cache
keys. Call-site provenance may require per-call-site helpers or richer
debug/source-map metadata, but it does not by itself change the persisted
checkpoint key for the same authored loop site.

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
generic defproc
  -> compiler instantiates monomorphic helper from type parameters
```

The long-term route is preferred because it keeps reusable behavior in
effectful `.orc` definitions instead of macro templates. Macros may still
provide ergonomic surface syntax, but they should expand to calls of generic
definitions rather than owning semantic control flow. A generic `defworkflow`
may still be useful as a generated/private lowering target, but it is not the
first stable authored review/revise API. Any future authored generic
`defworkflow` surface should be follow-on sugar over the same specialization
substrate, not part of the initial parametric implementation target.

Macro-origin restrictions still apply:

- no hidden provider or command effects introduced only by macro templates;
- no macro-owned runtime semantics;
- no bypass around shared validation;
- no loss of source-map provenance.

## Interaction With Procedure References

`ProcRef` values remain compile-time references to named `defproc`
definitions. A parametric procedure may accept `ProcRef` parameters whose
signatures mention type parameters. Those signatures are ordinary parameter
types, not separate `:where` constraints.

For the first stable review/revise route, a fully generic `DecisionT` remains a
deferred extension. The concrete route binds those signatures to the stdlib
`ReviewDecision` union owned by the integration doc, including its `BLOCKED`
variant with `blocker_class BlockerClass`.

Example:

```lisp
(defproc review-revise-loop
  :forall (CompletedT InputsT)
  ((completed CompletedT)
   (inputs InputsT)
   (review ProcRef[(CompletedT InputsT) -> ReviewDecision])
   (fix ProcRef[(CompletedT InputsT ReviewFindings) -> CompletedT]))
  :where
    ((CompletedT is-record)
     (InputsT is-record))
  -> ReviewLoopResult
  ...)
```

Before runtime:

- `CompletedT` and `InputsT` are concrete;
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
7. Replace the review-loop macro bridge with an imported generic `defproc` only
   after those generic fixtures pass.

## Acceptance Checks

- Generic `.orc` definitions parse and typecheck with explicit type parameters.
- Specialization produces monomorphic helper definitions before Core AST
  lowering.
- Lowered workflow artifacts contain no type parameters or runtime type values.
- Source maps identify generic definition, call site, specialization arguments,
  and generated nodes.
- `ProcRef` specialization remains compile-time-only.
- Unsatisfied constraints fail before runtime.
- Variant-specific fields remain proof-gated after specialization. For the
  author-facing/internal terminology pairing, see "Pattern Matching" in
  `docs/design/workflow_lisp_frontend_specification.md`.
- A non-review-loop fixture proves the machinery is generic.
- A review-loop fixture uses the same machinery without compiler recognition of
  the literal `review-revise-loop` name.
- First-tranche consumers use the structural-constraints doc's owned
  vocabulary rather than alternate spellings such as `has-variant` or separate
  schema shorthand constraints.

## Relationship To Current Migration Architecture

The current key-migration architecture intentionally rejects requiring
parametric imported `defproc` support in the active rescue slice. That remains
correct.

This design names the follow-on language feature that should replace the macro
specialization bridge once the immediate migration is stable.
