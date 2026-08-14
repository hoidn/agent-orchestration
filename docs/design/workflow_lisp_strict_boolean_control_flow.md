# Workflow Lisp Strict Boolean Control Flow

## Metadata

- **Status:** accepted; implementation unselected
- **Kind:** feature and frontend architecture decision
- **Owner:** repository owner
- **Created:** 2026-08-14
- **Last material update:** 2026-08-14
- **Related:**
  [`workflow_lisp_frontend_specification.md`](workflow_lisp_frontend_specification.md),
  [`workflow_lisp_proof_graph.md`](workflow_lisp_proof_graph.md),
  [`workflow_language_design_principles.md`](workflow_language_design_principles.md),
  [`specs/versioning.md`](../../specs/versioning.md)
- **Implementation target:** Workflow Lisp target DSL 2.26; state schema 2.1
  and existing Semantic/Executable IR envelope versions remain unchanged

## Summary

Workflow Lisp `if` and the new `cond` form accept any ordinary language
expression whose final static type is exactly `Bool`. Conditions may contain
provider calls, command calls, workflow or procedure calls, comparisons,
Boolean operators, nested conditionals, and other effects valid in the
enclosing context. Authors do not have to bind an effect result before using it
as part of a condition.

Effects in conditions execute left to right and at most once. `and` and `or`
short-circuit, so skipped operands do not execute or create state. The compiler
recursively normalizes effectful conditions into existing effect nodes,
recorded Boolean projections, and structured `if` nodes. `cond` is frontend
sugar for nested `if`; no new runtime control form is introduced.

Union values expose their canonical read-only `.variant` discriminant.
Comparisons such as `(= attempt.variant COMPLETED)` contextually resolve the
unbound `COMPLETED` tag from `attempt`'s union type and establish sound
branch-local variant proof. This makes ordinary `if` and `cond` sufficient for
authored union routing while retaining runtime variant guards. Existing
`match` remains supported for compatibility.

## Context And Authority

Current Workflow Lisp already provides the runtime pieces this design composes:

- `if` lowers to structured control with effectful branch subgraphs;
- effect results can be bound by `let*` and reused by a later condition;
- pure computed Boolean conditions lower through generated
  `pure_projection` boundaries;
- provider, command, and workflow effects have checkpoint and resume
  contracts;
- union bundles use `variant` as their canonical discriminant; and
- `match` proof retains a runtime `requires_variant` guard.

The fixture
`tests/fixtures/workflow_lisp/valid/native_bool_provider_branch.orc` and
`test_provider_root_bool_result_drives_branching_persists_and_resumes` already
prove the manually desugared provider-result -> binding -> `if` -> effectful
branch path, including resume. The missing capability is generic frontend
normalization and predicate-derived proof, not a new runtime primitive.

This design changes the current frontend rule that an `if` condition must be
pure and that only `match` creates authored variant proof. Until target 2.26 is
implemented, the current frontend specification and capability matrix remain
the authority for runnable source.

## Problem

Current source must split an effectful decision from its use:

```lisp
(let* ((approved
         (provider-result providers.review
           :prompt prompts.review
           :returns Bool)))
  (if approved
      (call accept ...)
      (call revise ...)))
```

The restriction is not semantic: the runtime already executes and records the
provider result before routing. It is a frontend condition-shape restriction.
The restriction becomes more awkward when a provider returns an enum or record
that participates in a Boolean comparison.

Union routing has a separate ergonomic problem. `match` currently owns variant
proof, forcing pattern syntax even when ordinary Lisp `if` or `cond` expresses
the decision more clearly. Removing `match` proof without a replacement would
be unsound, because a Boolean route alone cannot authorize a variant-only field.

## Goals And Non-Goals

Goals:

- Admit every expression valid in its enclosing context when its final static
  type is exactly `Bool`.
- Permit effects anywhere inside a condition expression without requiring an
  authored pre-binding.
- Preserve left-to-right, exactly-once, short-circuit execution.
- Add standard expression-oriented `cond` syntax.
- Let typed discriminant comparisons establish sound union proof.
- Preserve fail-closed result validation, effect visibility, source maps,
  checkpoints, and resume behavior.
- Reuse existing runtime and IR control surfaces.

Non-goals:

- Lisp truthiness or implicit conversion to `Bool`.
- Runtime `eval`, dynamic code, or an open-ended condition evaluator.
- Multiple sequential expressions in one `cond` clause; authors use `let*`
  when sequencing is needed.
- A first-class runtime or Semantic IR `cond` node.
- Removal or migration of existing `match` source.
- Proof from arbitrary Boolean-returning functions, provider judgments, strings,
  or payload conventions.
- Proof carried across workflow boundaries or loop iterations beyond existing
  contracts.

## Decision

Target 2.26 generalizes `if`, adds `cond` as nested-`if` sugar, recursively
normalizes effects in condition expressions, and extends the proof checker with
facts derived only from typed comparisons against a union's `.variant`
discriminant.

Rejected alternatives:

- A `cond` node that survives typed frontend normalization adds parallel WCC,
  lowering, state, and observability machinery without changing behavior. A
  parser/elaboration-local clause container or missing-else marker is allowed
  solely to support type-aware expansion and must be erased before WCC.
- Generated predicates such as `(COMPLETED? attempt)` collide when unions reuse
  variant names.
- A generic `(variant? attempt COMPLETED)` operator duplicates the existing
  canonical `variant` field and ordinary equality.
- Cosmetic `match` sugar does not provide arbitrary Boolean conditions.
- Generalized occurrence typing is broader than the required closed
  discriminant-proof rules.

Lowering `cond` to nested `if` makes cond-native runtime visualization harder.
Authored clause spans remain source-mapped; a first-class IR node is warranted
only if future tooling demonstrates that the source map is insufficient.

## Surface Contract

### `if`

`if` retains exactly three operands:

```lisp
(if condition then-expression else-expression)
```

`condition` may be any expression valid in the enclosing workflow or procedure
whose final inferred type is exactly `Bool`. Existing expression-specific
effect, capability, contract, and placement rules still apply; `if` adds no
condition-specific purity or shape restriction.

For example:

```lisp
(if (= (provider-result providers.review
          :prompt prompts.review
          :returns ReviewDecision)
       ReviewDecision.APPROVE)
    (call accept ...)
    (call revise ...))
```

Both branches must retain the existing compatible-result-type rule. Only the
selected branch executes.

### `cond`

Each clause contains exactly one condition and one result expression. The final
fallback uses `else` and also contains exactly one expression:

```lisp
(cond
  ((< attempts max-attempts)
   (call retry ...))
  ((provider-result providers.stop-check :returns Bool)
   (call stop ...))
  (else
   (call exhaust ...)))
```

Clauses evaluate in authored order. Evaluation stops at the first true
condition. An `else` clause is required unless a clause condition statically
folds to true or typed variant facts prove the clauses exhaustive. Every result
expression must have a compatible type.

Exhaustiveness is resolved during type-aware recursive condition normalization.
When a no-`else` form's residual false environment is unreachable, all
reachable effects and short-circuit branch boundaries in the final condition
are retained. Only an effect-free condition, or a pure terminal test whose
result is forced after its reachable effect prefixes, may be erased. The
normalized true and impossible-false continuations then converge on the final
clause's result expression through ordinary nested `if` structure. If the
residual environment remains reachable, compilation fails. No synthetic
unreachable branch reaches WCC or runtime. A parser/elaboration-local clause
container or missing-else marker may carry the form only until this type-aware
rewrite.

For example, if prior facts already prove `attempt` is `BLOCKED`, this final
condition is exhaustive but its provider call remains observable:

```lisp
(or (provider-result providers.last-check :returns Bool)
    (= attempt.variant BLOCKED))
```

The compiler may omit the forced terminal equality after a false provider
result, but it must still execute the provider once and preserve the `or`
short-circuit boundary before entering the clause body.

At target 2.26, `cond` is reserved as a frontend form. Targets below 2.26 retain
their existing name-resolution behavior.

### Strict Boolean Rule

The final condition type must be exactly `Bool`. No value is implicitly false
or true, and no non-Boolean value is compared with an implicit truth value.
Static rejection occurs before lowering or effect execution.

## Recursive Condition Normalization

The compiler normalizes the complete condition tree, not only its root.
Conceptually:

```lisp
(if (= (provider-result providers.review :returns ReviewDecision)
       ReviewDecision.APPROVE)
    accepted-work
    revision-work)
```

becomes:

```lisp
(let* (($decision
         (provider-result providers.review :returns ReviewDecision))
       ($condition
         (= $decision ReviewDecision.APPROVE)))
  (if $condition accepted-work revision-work))
```

Generated bindings are compiler-owned and have stable identities derived from
the authored condition, operand position, and enclosing form path. Normalization
must not hoist an effect across a short-circuit or branch boundary.

Rules:

- ordinary operands evaluate left to right;
- a completed effect result is bound once and reused by the remaining pure
  computation;
- the final Boolean is represented by a literal, existing typed Boolean ref, or
  generated `pure_projection` result before structured routing;
- `and` evaluates each later operand only after all prior operands are true;
- `or` evaluates each later operand only after all prior operands are false;
- `not` evaluates its operand once and inverts the result;
- nested `if` and `cond` retain their own branch boundaries; and
- skipped operands emit no effect node, checkpoint, provider attempt, command
  attempt, or result state.

`cond` expansion retains clause-level source provenance and then uses this same
normalization path. Its temporary frontend representation is erased before WCC;
there is no cond-only evaluator or runtime node.

## Contextual Union Tags And Proof

Every union value has a compiler-owned read-only `.variant` discriminant. Its
compiler-internal type is nominal to that union and is not an independently
nameable source type in this tranche.

Inside `=` or `!=`, an otherwise-unbound identifier paired with a union
discriminant is resolved against that union's declared variants:

```lisp
(= attempt.variant COMPLETED)
(!= attempt.variant BLOCKED)
```

Normal lexical name resolution wins. Contextual tag resolution occurs only for
an otherwise-unbound identifier. The comparison is symmetric, so a tag may
appear on either side when the other operand provides an unambiguous union-tag
type. Missing context, an unknown tag, or operands from different union types
is a compile error.

Comparing two compatible discriminant values is an ordinary Boolean comparison
but establishes no specific-variant proof. Comparing a discriminant to a
resolved tag establishes these facts:

- `=`, true path: the subject has that variant;
- `=`, false path: the subject does not have that variant;
- `!=`, true path: the subject does not have that variant; and
- `!=`, false path: the subject has that variant.

For a closed union, excluding every variant except one proves the remaining
variant. Proof authorizes variant-only fields only for a stable named subject,
such as `attempt`. An arbitrary inline comparison may route without providing a
name that later field access can use.

### Closed Fact Algebra

Proof environments are keyed by resolved lexical binding identity, never by
identifier spelling. For each union binding, an environment stores the closed
set of variants still possible on that path. A fresh binding starts with every
variant declared by its union. Shadowed bindings have distinct identities, and
a `let*` alias is a distinct binding; first-tranche proof does not propagate
between aliases.

An environment is unreachable when any binding's possible set becomes empty.
Joining alternative reachable paths unions their possible sets per binding;
unreachable alternatives do not participate. This join may discard useful
cross-binding correlation, but it cannot invent proof. A field is statically
available only when its binding's possible set is the singleton containing the
field's declaring variant.

Condition analysis is `analyze(condition, environment) -> (when_true,
when_false)`:

- literal `true` returns `(environment, unreachable)`;
- literal `false` returns `(unreachable, environment)`;
- `x.variant = V` intersects `x` with `{V}` on true and removes `V` on
  false;
- `x.variant != V` swaps those equality refinements;
- an arbitrary Boolean expression returns `(environment, environment)` and
  therefore routes without narrowing;
- `not A` swaps `A`'s two results;
- `A and B` analyzes `B` under `A`'s true environment, returns `B`'s true
  environment for the whole true path, and joins `A`-false with `B`-false for
  the whole false path; and
- `A or B` analyzes `B` under `A`'s false environment, joins `A`-true with
  `B`-true for the whole true path, and returns `B`'s false environment for the
  whole false path.

Variadic `and` and `or` apply those binary rules left to right. Later operands
are typechecked under the environment in which short-circuit evaluation reaches
them, so the second operand here admits the completed-only field:

```lisp
(and (= attempt.variant COMPLETED)
     (valid? attempt.execution_report))
```

Joins, contradictions, remaining-variant inference, and exhaustiveness all
follow from the same possible-set operations rather than separate heuristics.

Each `cond` clause is analyzed under the residual false environment from all
prior clauses. Its body is checked under its true environment. A no-`else`
`cond` is exhaustive only when a pure statically true condition or typed
variant refinement makes the final false environment unreachable. General
Boolean exhaustiveness is not guessed.

### Proof Carriage And Runtime Guards

Typechecking acceptance is not sufficient proof carriage. The typed frontend
must retain each branch's resolved binding identity, union identity, possible
variant set, producer/discriminant identity, and source span until WCC lowering.
The representation may be a compiler side table or an internal extension to
the existing WCC conditional node; it is not a new public Semantic/Executable
IR envelope or runtime form.

When a branch reads a variant-only field under a singleton environment, WCC
lowering uses the same producer/discriminant identity and guard-construction
path as `match` to attach the existing `requires_variant` contract to the
consuming runtime step. The corresponding lexical checkpoint retains the
existing proof descriptor needed for resume. Proof ends at the branch boundary
unless ordinary result typing exports a new value; it does not leak through the
conditional join.

Static proof does not replace runtime validation. A missing guard is a compiler
error, and every emitted guard fails closed if runtime or persisted state
contradicts the proof.

## Failure, State, And Resume Semantics

- A non-`Bool` condition fails compilation.
- Malformed `cond`, missing required `else`, invalid contextual tags, and
  incompatible branch result types fail compilation.
- An executed provider, command, call, or other condition effect that fails or
  returns an invalid contract fails normally. Failure is never coerced to
  false, and no branch is selected.
- Each executed condition effect uses its ordinary checkpoint and completed
  result-reuse contract.
- The final Boolean is recorded before branch selection. Resume reuses completed
  effects and the recorded/provably replayable Boolean rather than choosing a
  different branch.
- Untaken branches and short-circuited operands have no runtime state.
- Existing effect declarations, provider/command contracts, permissions,
  security boundaries, and failure routing remain authoritative.

Generated effects, projections, nested `if` nodes, and branch nodes retain
source ownership back to the exact authored condition or `cond` clause.
Generated debug or source-map views are evidence, not branch authority.

## Diagnostics

Target 2.26 retains the existing exact-`Bool` and branch-type diagnostics and
removes the purity/projectability refusals for otherwise valid conditions.
Stable diagnostics must distinguish at least:

- condition result is not exact `Bool`;
- malformed `cond` clause or misplaced/non-final `else`;
- non-exhaustive `cond` without `else`;
- contextual variant tag lacks a union context;
- tag is not declared by the contextual union;
- discriminant operands belong to incompatible unions;
- variant-only field lacks proof or is used under the wrong proof; and
- condition effect/runtime contract failure.

Diagnostics for generated nodes point to the authored subexpression or clause,
not a compiler-generated binding name.

## Compatibility And Versioning

- The surface is gated at target DSL 2.26.
- State schema remains 2.1 because normalized effects, projections, structured
  conditionals, proofs, and checkpoints reuse existing state families.
- Existing Semantic IR, Executable IR, core AST, and runtime-plan envelope
  versions remain unless implementation discovers an actual representational
  gap. Such a gap triggers design revision rather than a silent version change.
- Source targeting below 2.26 retains current pure/projectable `if` behavior,
  current `match` proof ownership, and current `cond` name resolution.
- Existing `match` source remains valid at and after 2.26. No automatic source
  rewrite or migration is required.
- The drafting guide must not recommend the new style until capability evidence
  marks target 2.26 implemented and copy-safe.

## Feasibility Boundary

The existing manually desugared provider-Boolean branch and resume test proves
that normal effects, typed Boolean refs, effectful branches, and resume already
compose. Existing pure-operator typechecking also retains operand effect
summaries. It does not prove the accepted generic mechanism: current WCC
pure-operator elaboration may prefix operand effects eagerly, and current WCC
conditionals do not carry branch proof.

The implementation plan therefore begins with four executable feasibility
fixtures before claiming no runtime or public-IR change:

1. **Linear extraction:** normalize an inline provider effect beneath `=`,
   lower through existing structured `if`, preserve effect/source/checkpoint
   identity, and show clean/resume equivalence with the authored `let*` form.
2. **Short circuit:** place counted provider or command effects in later `and`
   and `or` operands and prove skipped operands create no attempt, checkpoint,
   or step state on clean execution or resume. This must bypass or correct any
   eager WCC operand-effect prefixing.
3. **Nested control value:** use an effectful nested `if` as an operand of a
   larger Boolean expression and prove that only its selected effects execute
   before the outer route.
4. **Proof-to-guard carriage:** compile a discriminant predicate whose selected
   branch consumes a variant-only field; prove the consuming step contains the
   existing `requires_variant` guard, a contradictory runtime discriminant
   fails closed, and resume restores the bound proof descriptor.

A fifth compile/runtime fixture covers no-`else` exhaustive `cond` with an
observable provider or command effect before a proof-forced terminal test. It
proves the effect still executes exactly once, short-circuit behavior is
preserved on clean run and resume, and the temporary frontend marker is erased
into ordinary nested `if` before WCC.

An internal WCC conditional proof field or compiler side table is within the
accepted design. If the fixtures require a condition-specific runtime node, a
new public IR envelope, a new state family, or eager evaluation of
short-circuited effects, stop and revise this design.

## Verification Strategy

Focused compile and typecheck coverage must prove:

- literals, refs, pure expressions, direct effects, calls, nested comparisons,
  and nested conditionals are admitted exactly when their final type is `Bool`;
- non-Boolean conditions remain rejected;
- `cond` syntax, ordered evaluation, one-expression clauses, result typing,
  `else`, typed exhaustiveness, and preservation of reachable effects in an
  exhaustive no-`else` clause;
- contextual tag resolution, lexical-binding precedence, unknown/mismatched
  tag rejection, and compatible discriminant equality;
- positive and negative proof through `=`, `!=`, `and`, `or`, and `not`;
- unsound proof paths and unproved/wrong-variant fields remain rejected; and
- source maps retain authored subexpression and clause provenance.

Runtime integration coverage must use deterministic fake providers/commands
with invocation counters to prove:

- effectful condition operands execute left to right and at most once;
- `and`, `or`, and `cond` skip unneeded effects;
- only the selected result branch executes;
- an invalid or failed condition effect fails before branch selection;
- clean and resumed runs produce the same selected branch and outputs; and
- completed condition effects are reused without duplicate attempts.

The primary acceptance scenario is an inline provider call returning a typed
review decision, compared inside `if`, followed by distinct effectful accept
and revise branches. A forced failure after condition settlement and before
branch completion must resume without repeating the provider or changing the
selected branch. A companion union scenario must route with `cond`, access
variant-only fields in proven clauses, and omit `else` only when every variant
is statically covered.

After narrow selectors, collect any new test modules explicitly and run the
repository's broad suite with:

```sh
pytest -q -n 16 --dist=worksteal
```

The broad run belongs in tmux. Tests assert behavior, contracts, lineage,
effect counts, and source ownership, not prompt wording or incidental serialized
compiler structure.

## Documentation Impact

Implementation updates:

- `docs/design/workflow_lisp_frontend_specification.md` condition and proof
  sections;
- `docs/design/workflow_lisp_proof_graph.md` proof sources and flow rules;
- `docs/lisp_workflow_drafting_guide.md` normal authoring guidance;
- `docs/capability_status_matrix.md` status and copy-safety evidence;
- `specs/versioning.md` and `specs/index.md` target-2.26 routing; and
- relevant frontend reference/form catalogs.

This design and the documentation indexes may advertise the surface as
designed, not runnable.

## Implementation Handoff

The implementation plan should keep one vertical path:

1. run the five feasibility fixtures above and stop on a public-IR/runtime/state
   gap;
2. add target/version gating, contextual tag typing, and binding-identity
   possible-set analysis;
3. recursively normalize effects through existing `let*`, projection, and
   structured-`if` machinery, then erase temporary `cond` structure without
   discarding reachable effect prefixes or short-circuit boundaries;
4. carry branch proof through WCC into existing runtime guards and resume proof
   descriptors; and
5. complete runtime/source-map evidence and governing-doc updates.

Likely frontend owners include `expressions.py`, `typecheck_dispatch.py`,
`typecheck_pure_ops.py`, `typecheck_proofs.py`, `conditionals.py`, and the WCC
control lowerers. The plan must first trace every `IfExpr`, `PureOpExpr`, and
proof-scope traversal rather than adding a schema-1-only or workflow-specific
branch.

No cond-specific node may survive typed frontend normalization. Do not
introduce a new runtime execution form, a second proof graph, a public IR
envelope change, or a new state family unless the feasibility fixtures disprove
the accepted composition. Any such need reopens this design.

## Open Questions

None. Core syntax, typing, evaluation order, short-circuit behavior, failure,
proof, exhaustiveness, compatibility, and verification semantics are decided.
