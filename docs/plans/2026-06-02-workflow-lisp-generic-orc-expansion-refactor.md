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

1. Introduce a formal extension boundary before changing review-loop behavior.

   Add a form registry that classifies every recognized head. The registry
   should answer which forms are core language forms, core effect bridges,
   standard-library extensions, and temporary compiler intrinsics scheduled for
   deletion.

   Sketch:

   ```python
   class FormKind(Enum):
       CORE_SPECIAL = "core_special"
       CORE_EFFECT = "core_effect"
       STDLIB_EXTENSION = "stdlib_extension"
       TEMP_COMPILER_INTRINSIC = "temp_compiler_intrinsic"

   @dataclass(frozen=True)
   class FormSpec:
       name: str
       kind: FormKind
       owner: str
       introduced_in: str
       remove_by: str | None = None
       allowed_in_macro_definition: bool = True
       elaborator: str | None = None
       rationale: str = ""
   ```

   Initial classification should be explicit and reviewable:

   - `CORE_SPECIAL`: `record`, `let*`, `if`, `match`, `call`, `proc-ref`,
     `workflow-ref`, `loop/recur`, `continue`, `done`.
   - `CORE_EFFECT`: `provider-result`, `command-result`, and other runtime
     bridge forms that directly lower to workflow execution effects.
   - `STDLIB_EXTENSION`: `review-revise-loop`.
   - `TEMP_COMPILER_INTRINSIC`: high-level forms that still need compiler help,
     such as `run-provider-phase`, `produce-one-of`, `resume-or-start`,
     `resource-transition`, `finalize-selected-item`, and `backlog-drain`,
     until they have ordinary `.orc` routes.

   The exact classification may change, but the classification must exist. The
   registry should become the source for macro reserved names, expression
   elaborator dispatch, lint/denylist rules, and compiler-intrinsic docs.
   Parallel lists such as `_RESERVED_MACRO_NAMES` should be derived from the
   registry or checked against it.

2. Replace large ad hoc head dispatch with registry dispatch.

   Intermediate dispatch shape:

   ```python
   spec = FORM_REGISTRY.get(head.resolved_name)

   if spec is None:
       return elaborate_callable_or_name_reference(...)

   if spec.kind is FormKind.STDLIB_EXTENSION:
       return elaborate_stdlib_extension_reference(...)

   if spec.kind is FormKind.TEMP_COMPILER_INTRINSIC:
       warn_or_require_allowlisted_intrinsic(spec, datum)

   return spec.elaborator(...)
   ```

   The registry is not a new semantic engine. It is an extension boundary that
   forces each compiler-known head to declare why the compiler knows it.

3. Add regression guards that fail if review-loop-specific compiler artifacts
   remain as the semantic route:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - `__review-revise-loop__`;
   - `_lower_review_revise_loop`;
   - `_validate_review_loop_result_contract`;
   - typechecker or lowerer branches keyed directly to `review-revise-loop`.

   The old branch may remain temporarily only as a shape oracle for golden
   fixtures. It must not be the accepted semantic route.

4. Keep a temporary Python compatibility shim only as syntax.

   If public `(review-revise-loop ...)` cannot immediately become an imported
   macro because the current macro system reserves the name, a temporary shim
   may parse the old surface and emit ordinary syntax for an imported `.orc`
   call.

   Acceptable:

   ```python
   def expand_review_revise_loop_compat(form: SyntaxList) -> SyntaxList:
       return SyntaxList(
           [introduced_identifier("std.phase/review-revise-loop"), ...],
           span=form.span,
           expansion_stack=push_expansion_frame(...),
       )
   ```

   Unacceptable:

   ```python
   def expand_review_revise_loop_compat(form):
       return ReviewReviseLoopExpr(...)

   def lower_review_revise_loop(expr):
       return hand_built_match_loop_tree(...)
   ```

   The compatibility shim must have a registry `remove_by` condition. Once
   imported `.orc` macros can own the public name cleanly, remove the shim and
   unreserve `review-revise-loop`.

5. Introduce generic expansion metadata, not a lasting semantic AST node.

   If an internal representation is needed, use a generic expansion carrier
   such as `ExpandedOrcExpr` or `OrcExpansionExpr`, with fields for:
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

   Prefer this lifecycle:

   ```text
   Syntax / frontend AST from imported .orc
     -> expansion engine clones/substitutes with ExpansionFrame metadata
     -> returns ordinary ExprNode
     -> normal typecheck
     -> normal lowering
   ```

   Avoid a durable `ExpandedOrcExpr` semantic variant that downstream
   typechecking or lowering must dispatch on. A lasting wrapper can recreate
   the same special-case smell at one level of indirection.

6. Build a generic imported `.orc` expansion/specialization substrate.

   The central operation should be generic:

   ```python
   expand_inline_procedure_call(
       call: ProcedureCallExpr,
       callee: TypedProcedureDef,
       ctx: ExpansionContext,
   ) -> ExprNode
   ```

   It should:

   - clone an already parsed/elaborated `.orc` body;
   - substitute value parameters hygienically;
   - substitute compile-time `ProcRef` parameters as resolved procedure refs;
   - allocate generated names and paths through a shared allocator;
   - push source-map frames for call site and imported definition;
   - return ordinary `ExprNode`;
   - re-typecheck the expanded expression through the normal typechecker.

   `review-revise-loop` becomes one caller of this mechanism, not the reason the
   mechanism is review-loop-shaped.

7. Move the review-loop control structure into `.orc` source.

   The `std/phase.orc` definition should express the loop in ordinary language
   terms: provider/procedure calls, `match`, `repeat_until` or the accepted
   typed loop form, revise/fix routing, exhaustion projection, and final typed
   result projection.

8. Keep public syntax ergonomic through a thin macro only if needed.

   A macro may rewrite:

   ```lisp
   (review-revise-loop ...)
   ```

   into an explicit call to an imported `.orc` procedure or workflow. It must
   not hide effects or cause the compiler to synthesize review-loop semantics
   in Python.

9. Implement generic capabilities only as they are needed by the `.orc` route:
   - compile-time `ProcRef` hook specialization;
   - effect visibility through imported `.orc` definitions;
   - generated bundle/path allocation without public hidden inputs;
   - source maps across authored call site, imported definition, macro expansion,
     and generated nodes;
   - typed structured result projection after loops.

10. Migrate incrementally with fixtures:
   - a tiny imported `.orc` procedure;
   - an imported `.orc` procedure that emits provider or command steps;
   - an imported `.orc` procedure using `match`;
   - an imported `.orc` procedure using the accepted loop form;
   - an imported `.orc` procedure accepting compile-time procedure refs;
   - finally, `review-revise-loop`.

11. Delete or quarantine the old semantic branch after the generic route passes:
   - `ReviewReviseLoopExpr`;
   - `_elaborate_review_revise_loop`;
   - review-loop-specific typechecker branches;
   - review-loop-specific lowerer branches;
   - review-loop-specific compiler visitor logic;
   - reserved macro treatment that prevents a real `.orc` implementation;
   - orphaned review-loop helpers.

## Two-Track Migration

Track A: architectural substrate.

1. Add `FormKind` / `FormSpec` registry.
2. Derive macro reserved names from the registry.
3. Route expression elaboration through the registry.
4. Add architectural denylist tests.
5. Add generic inline-procedure expansion for one tiny imported `.orc`
   procedure.
6. Add source-map frames for imported expansions.
7. Add generic effect visibility through imported expansions.
8. Add generic `ProcRef` specialization.

Track B: review-loop compatibility.

1. Keep existing review-loop behavior only as a golden oracle.
2. Add a public syntax compatibility shim that emits ordinary imported `.orc`
   call syntax.
3. Implement skeletal `std/phase.orc` `review-revise-loop` using ordinary
   forms.
4. Compare lowered output against old golden cases.
5. Delete `ReviewReviseLoopExpr`.
6. Delete `_elaborate_review_revise_loop`.
7. Remove `review-revise-loop` from core reserved macro names.
8. Remove typecheck/lowering imports and branches.

Track A must land first. Otherwise Track B risks becoming another hand-coded
migration path.

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

Architectural tests:

- `test_no_review_loop_expr_in_core_ast_union`
- `test_review_revise_loop_not_reserved_core_macro_name`
- `test_review_revise_loop_not_elaborated_by_head_name`
- `test_typecheck_does_not_import_review_loop_expr`
- `test_lowering_does_not_import_review_loop_expr`
- `test_stdlib_expansion_source_map_has_callsite_and_callee`
- `test_imported_inline_proc_effects_are_visible`
- `test_imported_inline_proc_with_match_typechecks`
- `test_imported_inline_proc_with_loop_recur_typechecks`
- `test_imported_inline_proc_with_proc_ref_specializes`
- `test_review_revise_loop_public_syntax_compiles_via_stdlib_route`

Success criterion:

```text
review-revise-loop may appear in stdlib source, tests, docs, and compatibility
notes; it must not appear as a semantic branch in the core compiler.
```

Future high-level `.orc` abstractions should normally be added by adding:

```text
std/foo.orc
tests
maybe an exported macro
```

and not by editing:

```text
expressions.py
typecheck.py
lowering.py
compiler.py
macros.py reserved-head lists
```

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
