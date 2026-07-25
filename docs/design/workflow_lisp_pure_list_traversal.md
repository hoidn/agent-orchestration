# Workflow Lisp Pure List Traversal

- **Status:** proposed (owner-directed 2026-07-25; design review pending)
- **Kind:** closed pure-expression surface extension
- **Owner:** Workflow Lisp frontend + pure evaluator
- **Motivating consumer:** runtime-cardinality fan-out — e.g. a review panel
  whose lens list is workflow input data, producing per-element provider
  calls in a bounded loop and accumulating typed results for synthesis.
  Today the closed operator catalog has no list operations, so a
  `List[T]` can be bound, validated, rendered into prompts, and passed
  through — but never traversed or built in-language, forcing static call
  sites wherever cardinality is data.
- **Related docs:**
  - `docs/design/workflow_lisp_frontend_specification.md` (§10.2 closed
    pure-expression surface)
  - `docs/design/workflow_language_design_principles.md` (principle 17 pure
    helpers, principle 27 deterministic runtime model, shared golden vectors)
  - `docs/design/workflow_lisp_state_layout.md` (loop state)

## Summary

Add one small operator family to `PURE_EXPR_OPERATOR_CATALOG`, a list
constructor expression, a pure comprehension binder form (`list/map`), a
pure rooted-path constructor (`path/join-under`), `List[T]` as a
loop-carried state type, and one stdlib effectful map (`std/list/map-proc`)
over first-order `ProcRef` values. All pure operators are total and
deterministic; no function values enter the language anywhere in this
design. This is the entire delta between "N is authored" and "N is data"
for sequential fan-out.

The design separates two maps with different obligations:

- **Pure mapping** (`list/map`) is total by construction — structural
  recursion over a finite list — so it carries no iteration bound and no
  exhaustion outcome.
- **Effectful mapping** (`std/list/map-proc`) spends provider budget, so it
  carries an authored `max_items` cap; exceeding the cap is a fail-closed
  node error with a named diagnostic (per design principle 28), matching
  the precedent that timeouts fail steps rather than returning routable
  variants. It returns plain `List[R]`; no result union exists unless a
  future consumer demonstrates a need to route on exhaustion.

## Contract

### Operators

| Operator | Type | Semantics |
| --- | --- | --- |
| `list/empty?` | `List[T] -> Bool` | true iff length zero |
| `list/head` | `List[T] -> Optional[T]` | first element; `none` on empty |
| `list/rest` | `List[T] -> List[T]` | all but first; empty on empty |
| `list/append` | `(List[T], T) -> List[T]` | new list with element appended |
| `list/length` | `List[T] -> Int` | element count |

Totality rules: no operator can fail at runtime on any well-typed input.
`list/head` returns `Optional[T]` and composes with the existing `some?` /
`or-else` operators rather than introducing a partial operation; there is no
indexing operator in this tranche.

### Constructor

`(list <expr> ...)` builds a `List[T]` from zero or more element
expressions of one unifying element type. The empty form `(list)` requires
the element type from its binding context (loop-state declaration, record
field, or annotated binding); an empty literal with no context type is a
compile error, not an inference guess.

### Pure comprehension: `list/map`

`(list/map ((<binder> <list-expr>)) <body-expr>)` evaluates the pure body
once per element with the binder in scope, producing a new list in order.
The binder is a syntactic binding position — the same device as
`loop/recur`'s `(fn (state) ...)` body — not a function value; the body is
one statically known pure expression. No iteration bound applies: pure
evaluation is total by construction. Compile-time folding and the runtime
evaluator share golden vectors as with every pure operator.

### Pure rooted-path construction: `path/join-under`

`(path/join-under "<literal-root>" <string-expr>)` produces a relpath value
under the literal root. The split of obligations is explicit:

- **containment is checked purely** — normalization plus prefix proof that
  the result cannot escape the literal root (rejecting `..`, absolute
  segments, and empty results) — and violations raise the named
  `pure_expr` diagnostic family; while
- **existence is not a pure question** and is deliberately left to the
  consuming boundary: `must-exist` path parameters validate at binding, and
  prompt-dependency resolution re-verifies at attempt time and fails the
  attempt on a missing file, exactly as today. `path/join-under` therefore
  types as the target path family's containment without asserting
  existence.

The root must be a literal so containment is decidable at the call site;
runtime-chosen roots are rejected at compile time.

### Loop-carried lists

`List[T]` (for transportable `T`) becomes a valid `loop/recur` state slot
type. Explicit bounded recursion remains available to authors, and is the
implementation substrate for the stdlib map below:

```lisp
(loop/recur
  :max 32
  :state (loop-state
           (remaining List[Lens] lenses)
           (reviews   List[ProducedLensReview] (list)))
  :on-exhausted (variant PanelOutcome EXHAUSTED :reason "lens_cap")
  (fn (state)
    (if (list/empty? state.remaining)
      (done (variant PanelOutcome DONE :reviews state.reviews))
      (let* ((lens (or-else (list/head state.remaining) …))
             (review (run-lens lens doc)))
        (continue
          :remaining (list/rest state.remaining)
          :reviews (list/append state.reviews
                     (record ProducedLensReview
                       :name lens.name
                       :report review.report)))))))
```

`loop/recur`'s authored `:max` remains the sole iteration bound; list length
never bypasses it. Exhaustion semantics are unchanged.

### Stdlib effectful map: `std/list/map-proc`

One generic stdlib procedure — composed entirely from shipped mechanisms
(`:forall` procedures, `ProcRef` parameters with post-specialization effect
recomputation as in `std/phase` and `std/drain`, `bind-proc` partial
application, `loop/recur`) plus the operators above:

```lisp
(defproc map-proc
  :forall (T R)
  ((f ProcRef[(T) -> R])
   (items List[T])
   (max_items Int))
  -> List[R]
  :lowering inline
  ;; loop/recur over (remaining, results); exceeding max_items raises the
  ;; named fail-closed node error list_map_proc_cap_exceeded rather than
  ;; returning a routable variant.
  ...)
```

Multi-argument mapped procedures use existing `bind-proc` partial
application to freeze loop-invariant arguments; no lambda or capture
mechanism is introduced. Each mapped invocation is an ordinary loop-scoped
attempt with its own identity, snapshot, and evidence, and resuming
mid-list is ordinary mid-loop resume.

## Semantics and invariants

- **One semantics, twice.** Every operator is implemented in the runtime
  evaluator and mirrored by compile-time constant folding, with shared
  golden vectors extended to cover the family — including empty-list,
  single-element, and order-preservation cases (principle 27).
- **Checkpoints and identity.** List values are already transportable and
  already appear in persisted bindings; loop-state lists persist under the
  existing binding-schema/value-digest rules. No new checkpoint content
  kind is introduced.
- **Fail-closed typing.** Element-type mismatches surface as the existing
  `pure_expr_operand_type_mismatch` family with the operator and offending
  operand named (principle 28: refusals name their rule).

## Non-goals

- No function values anywhere: `list/map`'s binder is a syntactic binding
  position, and `map-proc`'s `f` is a compile-time `ProcRef`; nothing in
  this design may introduce a lambda literal, a runtime callable, or a
  capture mechanism beyond existing `bind-proc`.
- No `filter`/`fold` operators or comprehension guards until a consumer
  justifies each.
- No exhaustion result union on `map-proc`: the cap is a spend guard and
  fails closed; routable exhaustion returns only with a demonstrated
  consumer.
- No indexing (`list/nth`), slicing, sorting, or concatenation of two lists;
  each would need its own justified consumer.
- No `Map[K,V]` operators; the map type's traversal is a separate delta if
  a consumer ever appears.
- No unbounded recursion and no change to `:max` semantics.

## Feasibility notes

The pure layer already validates and coerces list values element-wise
(`pure_expr.py` list-kind descriptor and coercion paths); the catalog has an
established extension pattern (`string/concat`). The novel surface area is
loop-state collection slots and the empty-literal context-typing rule; both
should get RED coverage before implementation.

## Implementation handoff

One small plan: catalog + evaluator + folding + golden vectors; frontend
typecheck for the constructor and loop-state slots; RED tests for the
empty-literal rule and a runtime-N fixture exercising the canonical
traversal shape end to end (compile, run with a deterministic provider
double, resume mid-list). Schedulable as an independent small delta after
the Stage 7 v1.1 selector closes; it has no dependency on Stage 8.
