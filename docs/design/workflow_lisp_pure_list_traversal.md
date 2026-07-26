# Workflow Lisp Pure List Traversal

- **Status:** implemented at target 2.18; source interstage complete
  (2026-07-25)
- **Design review:** ordered `LIST_DESIGN_SPEC_APPROVED` then
  `LIST_DESIGN_QUALITY_APPROVED`
- **Kind:** closed pure-expression surface extension plus one bounded
  effectful binder
- **Owner:** Workflow Lisp frontend + pure evaluator
- **Minimum target:** `(:target-dsl "2.18")`
- **Motivating consumer:** runtime-cardinality fan-out — for example, a
  review panel whose ordered lens names are workflow input data, whose
  provider calls each return a review-report path, and whose synthesis call
  consumes the ordered list of paths. Before target 2.18, `List[T]` could
  cross selected contracts but could not be constructed or traversed
  in-language, so authors had to duplicate static call sites whenever
  cardinality was data.
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md` (§10.2 closed
    pure-expression surface and §10.3 bounded list traversal)
  - `docs/design/workflow_language_design_principles.md` (principles 17,
    27, 28, and 29)
  - `docs/design/workflow_lisp_state_layout.md` (loop state)
  - `docs/design/workflow_lisp_native_transportable_returns.md`

## Decision summary

Target 2.18 adds:

- the list constructor `(list ...)`;
- five total list operators;
- the pure binder `list/map`;
- the bounded effectful binder `list/map-effect`;
- the pure rooted-path constructor `path/join-under`; and
- collection-contract-expressible `List[T]` values as `loop/recur` state.

The surface remains constraint-first. It uses the existing structural
`List[T]` type and the shared transportability predicate; it adds no nominal
list hierarchy. `path/join-under` names a path family because its rooted
containment and existence policy are load-bearing contracts, which is the
specific nominal case retained by principle 29.

Both maps are binder forms, not function values. Their bodies reference
enclosing values through ordinary lexical scope. This design introduces no
lambda value, runtime callable, capture object, or `ProcRef` mapping surface.

The implementation adds versioned pure-payload expression kinds and one
generic repeat-exhaustion diagnostic field. It does **not** add a Core,
Executable IR, runtime-plan, scheduling, or checkpoint node kind.

Independent review first rejected the unversioned proposal's Optional-head
lowering, collection-carriage, empty-list-context, path-family, and cap-error
assumptions. The amended contract above resolved those findings, aligned
collection support with the shared whole-list predicate, and added an
operator-local malformed-root refusal. Ordered specification and quality
rereviews then approved this design.

## Version and compatibility contract

All new source forms require target DSL 2.18. Lower targets do not reserve
their names and fail through the existing target/surface diagnostic if the
forms are used.

Pure payload schema behavior is additive and selective:

- payloads containing only the pre-2.18 surface remain
  `pure_expr_schema_version: 1` byte-for-byte;
- any payload containing a list constructor, a 2.18 list operator,
  `list/map`, `path/join-under`, or the compiler-owned nonempty extraction
  uses `pure_expr_schema_version: 2`;
- the runtime accepts and validates schemas 1 and 2 independently and fails
  closed on every other version or on a node unavailable in the declared
  version; and
- the selected schema and canonical payload remain part of projection,
  executable, checkpoint, and resume identity exactly as schema 1 is today.

WCC lowering remains schema 2. Core Workflow AST, Workflow Semantic IR,
Workflow Executable IR, runtime-plan, source-map, and persisted state schema
versions do not change: their existing extensible metadata and step shapes
carry this delta without a new node kind. Existing schema-1 payloads and
checkpoints remain resumable.

## Collection eligibility

This tranche does not broaden the runtime collection contract. A list is
eligible at a pure-projection boundary, callable return, `list/map` result,
`list/map-effect` source/result, or loop-state slot exactly when:

```text
is_transportable_result_type(List[T]) == true
```

This whole-list test, rather than a test of `T` alone, is authoritative. At
the time of this design it admits nested `List`, `Optional`, and
string-keyed `Map` collection shapes whose recursively described leaves are
existing scalar, enum, or path contract types. It rejects record/union
elements, `Json`, `Provider`, `Prompt`, and reference values. In particular,
`List[SomeRecord]` is deliberately outside this tranche even though
`SomeRecord` alone is transportable.

Unsupported use fails with `list_collection_contract_unsupported`, naming
the complete rejected list type. Future recursive record/union collection
contracts require their own consumer and design; they are not implicit in
this proposal.

## Pure list surface

### Operators

| Operator | Type | Semantics |
| --- | --- | --- |
| `list/empty?` | `List[T] -> Bool` | true exactly when the list has no elements |
| `list/head` | `List[T] -> Optional[T]` | first element, or `none` when empty |
| `list/rest` | `List[T] -> List[T]` | all but the first element; empty remains empty |
| `list/append` | `(List[T], T) -> List[T]` | a new list with the element appended |
| `list/length` | `List[T] -> Int` | exact element count |

These public operators are total on every well-typed input and never mutate
their input. Operand/type failures use
`pure_expr_operand_type_mismatch`, with the operator and rejected type
identified. `list/head` composes with the existing `some?` and `or-else`
surface; no public partial head or indexing operator is introduced.

### Constructor and empty-list typing

`(list <expr> ...)` evaluates its element expressions left-to-right and
constructs an ordered `List[T]`. A nonempty constructor synthesizes `T` from
the first element and requires all remaining elements to be compatible with
that exact type.

The empty form `(list)` is checked only where the enclosing syntax already
owns one exact expected `List[T]`:

- a loop-state slot initializer;
- a record or union field value;
- a direct callable argument;
- a declared workflow or procedure return; or
- an `if` or `match` branch to which one of those expected types is
  propagated.

No new annotated-`let*`, general type-ascription, Hindley-Milner inference,
or default `List[Value]` rule is introduced. A standalone `(list)`, one
bound by an unannotated `let*`, or any other empty literal without an exact
expected list type fails with `list_empty_type_context_required`.

### Pure binder: `list/map`

```lisp
(list/map ((<binder> <list-expr>)) <pure-body-expr>)
```

The binder list must contain exactly one `(symbol expression)` pair.
`list-expr` is pure, has an eligible `List[T]` type, and is evaluated
exactly once. The body is checked with the binder at type `T`, must be pure,
and is evaluated once for each element in input order. The output is an
eligible `List[R]`.

Finite structural traversal terminates; errors raised by an otherwise
well-typed pure body, including containment rejection from
`path/join-under`, propagate with their existing coded diagnostics. The
form has no authored bound and no exhaustion outcome. A runtime-dependent
map lowers to one pure-projection step and therefore one projection
checkpoint; a completely constant form may fold at compile time. Folding
and runtime evaluation use the same schema-2 evaluator and golden vectors.

Malformed binders fail with `list_map_binder_invalid`; an effectful body
fails with `list_map_body_effect_forbidden`.

### Pure rooted path: `path/join-under`

```lisp
(path/join-under <PathType> <child-string-expr>)
```

`PathType` is a resolved prelude, local, or imported `PathTypeRef`, not a
runtime expression. It supplies the exact nominal result type and its
literal `defpath :under` root. This avoids declaration search or
consumer-driven guessing when multiple path families share a root. Authors
who do not need a narrower contract may use the general prelude families
`Path.state-root` and `Path.artifact-root`; a bespoke family is not required.

The child expression is evaluated once and must produce `String`.
Construction uses `PurePosixPath`-equivalent lexical semantics only:

1. the operator validates the declared `under` root as nonempty, normalized,
   workspace-relative, not `"."`, and free of empty, `.` and `..` segments;
2. the child must be nonempty and relative, and each segment must be
   neither empty, `.` nor `..`;
3. the result is the POSIX join of the declared root and child; and
4. a final lexical `relative_to(root)` containment proof must succeed.

No filesystem read, resolution, symlink traversal, or existence claim occurs
during pure evaluation. The result has the named `PathType`; its existing
`must_exist` policy is validated at the consuming binding boundary and
revalidated at an attempt boundary where the existing contract requires it.

An unresolved or non-path first operand fails with
`path_join_under_type_invalid`. A selected family's malformed `under`
declaration fails locally with `path_join_under_root_invalid`; this form does
not retroactively strengthen or reject unrelated existing `defpath`
declarations. An invalid child fails with `path_join_under_child_invalid`;
an absolute or escaping child fails with `path_join_under_escape`. The
diagnostic names the selected path family and rejected root or child. There
is no ambiguous-family path because the family is explicit.

## Loop-carried lists

An eligible `List[T]` becomes a valid `loop/recur` state and result
projection. The list is carried as one flattened collection-contract field,
serialized as one canonical JSON array, and restored as the exact same
`List[T]`. It is not flattened into index-addressed fields or routed through
report/pointer artifacts.

The loop projection stores the complete list descriptor in its contract and
identity material. Empty-list placeholders are `[]`. Seed, iteration,
checkpoint, and resume validation use the same element coercion and
collection contract; a descriptor mismatch, non-array value, invalid
element, or payload/checkpoint digest mismatch fails closed before the body
continues.

The rule that makes `List[T]` projectable is the shared whole-list
transportability predicate above. A supported list may therefore contain
nested optional or map shapes. Top-level `Optional[T]` and `Map[K,V]` loop
state remain unchanged and unsupported by this tranche.

## Bounded effectful binder: `list/map-effect`

```lisp
(list/map-effect
  ((<binder> <list-expr>))
  :max <positive-int-literal>
  <effectful-call-expr>)
```

The binder/source rules match `list/map`; the source expression is pure and
evaluated exactly once. In this first tranche the body is one existing
effectful provider, command, workflow, or procedure call expression after
specialization. Its arguments may be arbitrary already-supported pure
expressions over the binder and enclosing lexical bindings. Nested
`loop/recur`, nested `list/map-effect`, live-provider group forms, and
effectful control composition inside the body are rejected with
`list_map_effect_body_unsupported`; later widening requires a demonstrated
consumer.

The call returns `R` directly and each successful result is appended once,
in input order, to an eligible `List[R]`. `:max` must be a positive integer
literal; malformed, zero, negative, or computed values fail with
`list_map_effect_max_invalid`.

### Erasure and cardinality

After specialization, the form erases to existing generated pure-projection
steps plus the existing `repeat_until` loop shape:

- state contains `remaining: List[T]` and `results: List[R]`;
- an empty input returns `[]` without executing the authored body;
- a nonempty iteration obtains one compiler-validated head, calls the body,
  computes `tail`, and appends the committed result;
- if `tail` is empty, that same iteration returns `done` rather than
  requiring an extra empty-check iteration;
- otherwise it returns `continue` with `tail` and the new results.

Consequently cardinality `N <= max` succeeds with exactly `N` body calls,
including `N == max`. If `N > max`, exactly `max` body calls commit and the
existing repeat loop then fails closed before a `(max + 1)`th call.

The compiler-generated nonempty extraction is a schema-2 pure-payload node,
not an author-visible form. It is emitted only in the generated nonempty
branch, carries the resolved `T`, and maps back to the authored
`list/map-effect` span. Runtime validation repeats the nonempty precondition;
an impossible violation fails with `list_nonempty_invariant_broken`. No
fallback `T`, flow-sensitive Optional inference, public partial head, or
synthetic union is used.

### Exhaustion diagnostic

The underlying runtime failure retains:

```text
error.type = repeat_until_iterations_exhausted
```

and the generated map adds:

```text
error.code = list_map_effect_cap_exceeded
```

To carry that code generically, repeat-loop surface/Core/executable/runtime
configuration gains optional compiler-owned
`exhaustion_diagnostic_code`. It participates in executable and checkpoint
identity, is validated as inert diagnostic metadata, and is emitted only
when the existing exhaustion transition occurs. It does not change
scheduling, settlement, `on_exhausted`, or state-projection recognition of
the generic failure type. Authored `loop/recur` without the metadata remains
byte-for-byte and behaviorally unchanged.

### Effects, checkpoints, and resume

Each body call remains an ordinary loop-scoped attempt with stable
loop/iteration identity, snapshot, evidence, and existing retry behavior.
The accumulator projection follows the committed body boundary. An
interruption after the body effect commits but before the accumulator
projection commits resumes from the validated body boundary: it must not
replay the call, duplicate the result, skip an element, or reorder the
list. Body failure propagates unchanged and does not append a result.

Source maps retain the authored binder/body span and associate all generated
seed, branch, body, tail, append, and exhaustion metadata with that form.

## Pure payload schema 2

Schema 2 adds only the expression representation needed by this surface:

- `list` — an element descriptor and ordered item expressions;
- `list_map` — source, one lexical binder descriptor, body, and result
  element descriptor;
- `path_join_under` — the resolved path descriptor/root and child
  expression; and
- compiler-owned `list_nonempty_head` — source plus exact element
  descriptor and invariant diagnostic.

The five ordinary list operators remain `op` nodes whose catalog entries are
available only in schema 2. Lexical binder values are evaluator-local and
cannot collide with top-level resolved bindings. Schema validation rejects
duplicate/reserved binders, out-of-scope references, descriptor mismatch,
unsupported node/version pairs, and compiler-owned nodes missing their
compiler marker. Node-count accounting includes every nested item and body
node; the existing maximum-node rule remains in force.

No schema-2 node is persisted outside the already content-addressed pure
payload and its existing projections/checkpoint references.

## Required diagnostics

The implementation must provide stable coded refusals for both frontend and
runtime validation:

| Code | Refusal |
| --- | --- |
| `list_map_binder_invalid` | binder shape/name is invalid |
| `list_map_body_effect_forbidden` | `list/map` body is not pure |
| `list_map_effect_max_invalid` | `:max` is absent or not a positive integer literal |
| `list_map_effect_body_unsupported` | effectful body exceeds the first-tranche call shape |
| `list_collection_contract_unsupported` | complete list type fails the shared transport predicate |
| `list_empty_type_context_required` | `(list)` has no exact expected `List[T]` |
| `list_nonempty_invariant_broken` | compiler-owned nonempty extraction observed an empty list |
| `list_map_effect_cap_exceeded` | bounded effectful traversal exhausted |
| `path_join_under_type_invalid` | selected type is unresolved or not a path family |
| `path_join_under_root_invalid` | selected family's declared root is not safe for this operator |
| `path_join_under_child_invalid` | child is empty or lexically malformed |
| `path_join_under_escape` | child is absolute or escapes the declared root |

Existing operator/type mismatch, target-version, schema-mismatch, contract,
body-call, checkpoint, and resume diagnostics remain authoritative where
their rules apply.

## Verification contract

Implementation follows TDD and must cover both directions:

1. schema-1 payloads and target-2.17 workflows remain byte-identical while
   2.18 forms emit schema 2 and lower targets reject them;
2. shared golden vectors exercise evaluator and compile-time folding parity
   for constructor/operator/map/path success and every refusal above;
3. empty construction succeeds in every enumerated checked context and
   fails in standalone and unannotated-`let*` contexts;
4. list carriage covers empty, one, nested supported list, tampered element,
   tampered descriptor, and clean plus interrupted/resumed loop execution;
5. `list/map-effect` covers empty, one, `N == max`, `N > max`, body failure,
   and interruption after committed body effect but before accumulator
   commit;
6. cap failure preserves generic `error.type` and exact map-specific
   `error.code`, while ordinary `loop/recur` identity/behavior is unchanged;
7. `path/join-under` covers both prelude families, a narrower local/imported
   family, exact output typing, deferred existence, an accepted legacy
   `defpath` with an operator-rejected malformed root, malformed child,
   absolute child, and escape attempts; and
8. an end-to-end deterministic-provider fixture takes a runtime list,
   produces ordered path results, synthesizes them, and proves no replay or
   duplication after resume.

New or renamed test modules run `pytest --collect-only` before execution.
Focused frontend/evaluator/loop/build/resume selectors precede the existing
broad suite. No test asserts literal prompt wording.

### Maintained runtime-cardinality proof

The maintained target-2.18 consumer is
`tests/fixtures/workflow_lisp/valid/list_map_effect_runtime_cardinality_provider.orc`.
Its focused proof consists of exactly three tests, including two
deterministic-provider end-to-end tests, in
`tests/test_workflow_lisp_list_traversal.py`:

1. runtime `List[Int]` input binding compiles to qualified per-iteration
   provider checkpoint authority;
2. a clean deterministic run emits ordered rooted review-report paths and
   passes that ordered list to one synthesis provider; each review derives its
   returned path from the injected binder value, while synthesis consumes the
   injected ordered list to write its report bytes before returning its
   declared rooted path; the values use the existing family-profile-selected
   typed-prompt-input lane; and
3. an interruption after the first review provider commits resumes from the
   validated prior boundary, matches the clean outputs and provider event
   identities, and neither replays nor duplicates that review.

This proof does not promote automatic `List[T]` rendering for unselected
`provider-result :inputs`; that list prompt-transport surface remains outside
this tranche. Generic scalar, record, and relpath carriage is governed
separately by the private-runtime-state and consumer-value-flow design.

The focused selector for these three tests passes in the implementation
checkout. Broad-suite counts and ordered final implementation-review verdicts
are plan-level execution evidence and are intentionally not restated in this
durable design.

## Non-goals

- no function values, lambda literals, runtime callables, capture objects,
  higher-order operators, or `ProcRef` map;
- no record/union elements in list contracts in this tranche;
- no `filter`, `fold`, comprehension guard, index, slice, sort, two-list
  concatenation, or `Map[K,V]` traversal;
- no routable exhaustion union or authored failure-channel design;
- no filesystem existence check in pure evaluation;
- no nested effectful map/control body in the first tranche;
- no unbounded effectful recursion and no change to authored `loop/recur`
  cap semantics; and
- no mandatory type taxonomy: generic list and prelude path contracts remain
  valid author choices, while narrower contracts are opt-in.

## Implementation closure

The target-2.18 source interstage is complete. Its implementation plan owned
the delta in these ordered RED/GREEN slices:

1. target/schema contracts and diagnostic RED tests;
2. schema-2 pure kernel, catalog, evaluator, folding, and golden vectors;
3. frontend constructor/binder/path forms plus exact expected-type handling;
4. collection-valued loop projection and resume validation;
5. generic repeat exhaustion diagnostic metadata;
6. `list/map-effect` WCC erasure, source maps, and checkpoint identity; and
7. deterministic-provider clean/resume integration, docs, and broad
   verification.

The implementation did not expand the accepted surface. The interstage remains
independent of Stage 8; final suite totals and ordered implementation-review
artifacts remain in the implementation plan rather than becoming semantic
authority here.
