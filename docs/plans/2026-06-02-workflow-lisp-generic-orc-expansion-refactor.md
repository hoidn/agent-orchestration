# Workflow Lisp Generic `.orc` Expansion Refactor

Status: draft refactoring approach
Created: 2026-06-02
Related docs:
- `docs/design/workflow_lisp_key_migration_parity_architecture.md`
- `docs/design/workflow_lisp_stdlib_lowering.md`
- `docs/design/workflow_lisp_frontend_specification.md`
- `docs/lisp_workflow_drafting_guide.md`

## Goal

Refactor `review-revise-loop` away from review-loop-specific compiler lowering
and toward the same grammar-fed expansion pipeline used by any `.orc` source.

The target is not merely to rename the special case. The target is that every
`.orc` source surface--user modules, project modules, generated/private
modules, and standard-library modules--passes through the same parser,
expansion, typechecking, specialization, source-map, and lowering machinery.
Standard-library forms may be reusable and ergonomic, but they must not receive
hidden compiler branches keyed to their domain names.

## Principle

Python may implement generic language machinery:

- parsing grammar-accepted `.orc`;
- deterministic macro expansion;
- effectful procedure/workflow specialization;
- compile-time reference specialization;
- hygienic generated names and paths;
- source-map propagation;
- typechecking and lowering of ordinary Core AST nodes.

Python should not encode review-loop domain control flow. In particular, the
compiler should not contain a branch whose semantics are effectively:

```text
if form_name == "review-revise-loop":
    hand-build the review loop AST
```

## Desired Pipeline

```text
user .orc / project .orc / generated .orc / standard-library .orc
  -> grammar parser
  -> frontend AST
  -> macro/procedure expansion
  -> compile-time ref and type specialization
  -> ordinary Core AST
  -> shared validation
  -> executable workflow DSL
```

`review-revise-loop` should become one client of this pipeline, currently
exported from `std/phase.orc`, not a separate lowering lane.

## Current Smell

Large Python blocks that directly construct nested `MatchExpr`, `MatchArm`,
`DoneExpr`, `UnionVariantExpr`, and field projections for
`review-revise-loop` are a warning sign. Those nodes are legitimate Core AST
building blocks, but the review-loop-shaped tree should come from parsed `.orc`
source or a generic typed template mechanism available to arbitrary `.orc`, not
from a review-loop-specific compiler function.

The decisive review question is:

> Is this a generic `.orc` expansion/specialization mechanism used by arbitrary
> `.orc` code, or a review-loop-specific compiler branch with a new name?

If the answer is the latter, the refactor has not achieved the architecture.

## Boundary Smells To Remove

Domain AST node:

```text
ReviewReviseLoopExpr(
  review_provider=...,
  fix_provider=...,
  review_prompt=...,
  fix_prompt=...,
  checks_report=...,
  progress_report=...
)
```

Language AST nodes:

```text
ProcedureCall
Match
Loop / repeat_until
UnionVariant
Record
Projection
ProviderResult / CommandResult
Materialize
ProcRef specialization
```

The language should know about the second set. It should not know that a review
provider and a fix provider form a particular product workflow.

Other smells:

- lowerer code hand-authors review-loop semantics instead of lowering ordinary
  AST;
- typechecker branches encode `APPROVED`, `BLOCKED`, `EXHAUSTED`, or
  review-loop field requirements as a private schema;
- macro expansion becomes the hook for Python-authored review-loop semantics;
- generated names, bundle paths, or write roots are allocated locally for one
  feature instead of through a generic allocator;
- source maps identify only the user call site, with no real imported `.orc`
  definition provenance;
- review provider outputs can replace consumed evidence identities such as
  `checks_report`.

The target dependency direction is:

```text
public syntax
  -> optional thin macro
  -> imported std/phase.orc definition
  -> generic macro/procedure expansion
  -> generic typechecking
  -> ordinary Core AST
  -> shared validation
  -> executable workflow DSL
```

not:

```text
public syntax
  -> parser recognizes review-revise-loop
  -> ReviewReviseLoopExpr
  -> review-loop-specific typechecker branch
  -> review-loop-specific lowerer hand-builds match/loop/projection tree
  -> executable workflow DSL
```

## Refactoring Approach

1. Add regression guards that fail if review-loop-specific compiler artifacts
   remain as the semantic route:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - `__review-revise-loop__`;
   - `_lower_review_revise_loop`;
   - `_validate_review_loop_result_contract`;
   - typechecker or lowerer branches keyed directly to `review-revise-loop`.

   The old branch may remain temporarily only as a shape oracle for golden
   fixtures. It must not be the accepted semantic route.

2. Introduce a generic expansion representation, such as `ExpandedOrcExpr` or
   `OrcExpansionExpr`, with fields for:
   - parsed expansion AST;
   - authored call-site source;
   - library definition source;
   - specialization bindings;
   - generated-name/path allocator identity;
   - expansion stack and source-map provenance.

   This representation must not contain review-loop-specific fields such as
   `review_provider`, `fix_provider`, `checks_report`, or `progress_report`.
   Those belong in `.orc` records, unions, procedure parameters, and library
   definitions.

3. Move the review-loop control structure into `.orc` source.

   The `std/phase.orc` definition should express the loop in ordinary language
   terms: provider/procedure calls, `match`, `repeat_until` or the accepted
   typed loop form, revise/fix routing, exhaustion projection, and final typed
   result projection.

4. Keep public syntax ergonomic through a thin macro only if needed.

   A macro may rewrite:

   ```lisp
   (review-revise-loop ...)
   ```

   into an explicit call to an imported `.orc` procedure or workflow. It must
   not hide effects or cause the compiler to synthesize review-loop semantics
   in Python.

5. Implement generic capabilities only as they are needed by the `.orc` route:
   - compile-time `ProcRef` hook specialization;
   - effect visibility through imported `.orc` definitions;
   - generated bundle/path allocation without public hidden inputs;
   - source maps across authored call site, imported definition, macro expansion,
     and generated nodes;
   - typed structured result projection after loops.

6. Migrate incrementally with fixtures:
   - a tiny imported `.orc` procedure;
   - an imported `.orc` procedure that emits provider or command steps;
   - an imported `.orc` procedure using `match`;
   - an imported `.orc` procedure using the accepted loop form;
   - an imported `.orc` procedure accepting compile-time procedure refs;
   - finally, `review-revise-loop`.

7. Delete or quarantine the old semantic branch after the generic route passes:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - review-loop-specific typechecker branches;
   - review-loop-specific lowerer branches;
   - review-loop-specific compiler visitor logic;
   - reserved macro treatment that prevents a real `.orc` implementation;
   - orphaned review-loop helpers.

## Acceptance Checks

- Public `(review-revise-loop ...)` syntax still works for supported examples.
- Disabling any review-loop-specific compiler branch does not break the generic
  `.orc` route.
- Generated workflow nodes are ordinary Core AST nodes accepted by shared
  validation.
- The lowerer dispatches on Core language constructs, not on the domain name
  `review-revise-loop`.
- The typechecker validates declared record/union/procedure contracts
  generically, not a hardcoded review-loop result schema.
- Source maps identify the authored call site, imported definition, macro
  expansion if any, and generated nodes.
- Effects introduced by the imported definition are visible to validation and
  runtime planning.
- No caller-visible generated write-root input is required for promoted
  entrypoints.
- Review provider output cannot replace consumed evidence identities such as
  `checks_report`; those refs must come from loop input, state, or a declared
  materializer/producer.
- Review-loop tests cover approve, revise-then-approve, blocked, and exhausted
  paths through the generic route.

Concrete fixture ladder:

- static denylist for semantic use of review-loop-specific compiler artifacts;
- tiny imported `.orc` procedure with source maps for call site and imported
  definition;
- imported `.orc` procedure that emits provider or command effects visible to
  validation;
- imported `.orc` procedure that matches a union and uses ordinary variant
  proof;
- imported `.orc` procedure that uses the accepted loop form and terminal
  exhaustion projection;
- imported `.orc` procedure accepting compile-time `ProcRef` hooks without
  runtime closures;
- evidence-identity negative test;
- no public hidden write-root input test;
- public `(review-revise-loop ...)` parity suite through the generic route.

## Non-Goals

- Do not implement runtime closures or runtime-transported procedure values.
- Do not turn `.orc` source into generated YAML text.
- Do not accept a review-loop-specific compiler primitive as the migration
  solution.
- Do not rely on report prose, pointer files, or stdout JSON as semantic
  authority.

## Implementation Notes

The first useful implementation slice is an audit and guard test that proves
where the current review-loop semantics live. If semantics still live in
review-loop-specific Python lowering, the next slice should extract the smallest
generic expansion/specialization mechanism needed to move one simple `.orc`
procedure through the ordinary `.orc` pipeline.
