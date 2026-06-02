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

## Refactoring Approach

1. Add regression guards that fail if review-loop-specific compiler artifacts
   remain as the semantic route:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - `__review-revise-loop__`;
   - typechecker or lowerer branches keyed directly to `review-revise-loop`.

2. Introduce a generic expansion representation, such as
   `ExpandedOrcExpr` or `StdlibExpansionExpr`, with fields for:
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

   The `std/phase.orc` definition should express the loop in ordinary language terms:
   provider/procedure calls, `match`, `repeat_until` or the accepted typed loop
   form, revise/fix routing, exhaustion projection, and final typed result
   projection.

4. Keep public syntax ergonomic through a thin macro only if needed.

   A macro may rewrite:

   ```lisp
   (review-revise-loop ...)
   ```

   into an explicit call to an imported `.orc` procedure or workflow. It must not hide
   effects or cause the compiler to synthesize review-loop semantics in Python.

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

## Acceptance Checks

- Public `(review-revise-loop ...)` syntax still works for supported examples.
- Disabling any review-loop-specific compiler branch does not break the generic
  `.orc` route.
- Generated workflow nodes are ordinary Core AST nodes accepted by shared
  validation.
- Source maps identify the authored call site, imported definition, macro
  expansion if any, and generated nodes.
- Effects introduced by the imported definition are visible to validation and
  runtime planning.
- No caller-visible generated write-root input is required for promoted
  entrypoints.
- Review-loop tests cover approve, revise-then-approve, blocked, and exhausted
  paths through the generic route.

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
